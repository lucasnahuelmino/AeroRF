"""
api/routes/ws.py
───────────────
WebSocket channel for live aircraft updates (spec §48).

``/ws/flights`` pushes position updates to connected clients.

The spec is explicit about not flooding the frontend, so the design is:

* **Change-based, not timer-based.** A poll result is compared with the
  last state broadcast; an aircraft is only sent when its position,
  heading, altitude or on-ground flag actually moved. A parked aircraft
  produces no traffic at all.
* **Backed by the shared cache.** The broadcaster uses the same
  ``/states/all`` cache as the REST endpoint, so a page refresh does not
  spend a second credit for data the poller already fetched.
* **Honours the backoff gate.** On a 429 the poller pauses and tells
  clients the feed is throttled, rather than retrying in a loop.
* **Client-driven subscriptions.** A client sends
  ``{"action": "track", "icao24": ["abc123"]}`` to narrow the feed to the
  aircraft it is following, cutting payload further.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.logging import flight_log
from app.database.database import SessionLocal
from app.models.flight import FlightSelection, FlightSession
from app.services.cache import RateLimitedError
from app.services.flight_service import (
    SESSION_RECORDING,
    SLOT_COLORS,
    record_sample,
    tracked_icao24s,
)
from app.services.opensky_service import (
    OpenSkyError,
    OpenSkyNotConfigured,
    get_opensky_service,
)

router = APIRouter(tags=["WebSocket"])


# ─── Per-connection state ────────────────────────────────────────────────────

class FlightSubscription:
    """One connected frontend client."""

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.icao24s: list[str] = []
        self.last: dict[str, dict] = {}
        self.slot_colors: dict[str, str] = {}
        self.alive = True
        #: Last status text pushed to this client, so an unchanged condition
        #: is not re-sent on every poll (spec §48: no flooding).
        self.last_status: Optional[str] = None

    def wants(self, icao24: str) -> bool:
        return not self.icao24s or icao24 in self.icao24s

    def changed(self, state: dict) -> bool:
        """True when this aircraft's state differs from the last broadcast.

        This is the flood guard: an unchanged aircraft returns ``False``
        and is never sent.
        """
        code = state.get("icao24")
        if not code:
            return False
        previous = self.last.get(code)
        current = _fingerprint(state)
        if previous == current:
            return False
        self.last[code] = current
        return True

    async def send(self, payload: dict) -> bool:
        try:
            await self.websocket.send_json(payload)
            return True
        except Exception:
            self.alive = False
            return False

    async def send_status(self, status: str, **fields: Any) -> None:
        """Send a status message only when it differs from the last one."""
        if status == self.last_status:
            return
        self.last_status = status
        await self.send({"type": "status", "opensky": status, **fields})

    async def send_throttled(self, message: str, retry_after_s: float) -> None:
        """Send a rate-limit notice only when the retry delay changes."""
        marker = f"throttled:{retry_after_s:.0f}"
        if self.last_status == marker:
            return
        self.last_status = marker
        await self.send(
            {
                "type": "throttled",
                "message": message,
                "retry_after_s": round(retry_after_s, 1),
            }
        )

    def clear_status(self) -> None:
        self.last_status = None


def _fingerprint(state: dict) -> dict:
    """The fields whose change makes an update worth sending."""
    return {
        "p": (round(state["latitude"], 5), round(state["longitude"], 5))
        if state.get("latitude") is not None
        and state.get("longitude") is not None
        else None,
        "a": _r(state.get("altitude")),
        "h": _r(state.get("heading")),
        "v": _r(state.get("velocity")),
        "g": state.get("on_ground"),
        "c": state.get("callsign"),
        "t": state.get("time_position"),
    }


def _r(value, digits: int = 1):
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


# ─── Registry ────────────────────────────────────────────────────────────────

class Hub:
    """Tracks connected clients and owns the single polling task."""

    def __init__(self) -> None:
        self.clients: set[FlightSubscription] = set()
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def connect(self, sub: FlightSubscription) -> None:
        async with self._lock:
            self.clients.add(sub)

    async def disconnect(self, sub: FlightSubscription) -> None:
        async with self._lock:
            self.clients.discard(sub)
        if not self.clients and self._task:
            self._task.cancel()
            self._task = None

    @property
    def client_count(self) -> int:
        return len(self.clients)

    async def broadcast(self, payload: dict) -> None:
        dead = []
        for sub in list(self.clients):
            if not sub.alive or not await sub.send(payload):
                dead.append(sub)
        for sub in dead:
            async with self._lock:
                self.clients.discard(sub)

    async def start_polling(self) -> None:
        async with self._lock:
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _poll_loop(self) -> None:
        """Poll OpenSky and push only genuine changes."""
        settings = get_settings()
        service = get_opensky_service()
        interval = max(5, settings.live_poll_interval_s)

        flight_log.info(
            "ws.poll_started", "live polling started",
            interval_s=interval, configured=service.configured,
        )

        while True:
            try:
                await self._tick(service)
            except asyncio.CancelledError:
                flight_log.info("ws.poll_stopped", "live polling stopped")
                raise
            except Exception as exc:  # keep the feed alive
                flight_log.error(
                    "ws.poll_error", "poll iteration failed", error=str(exc)
                )
            await asyncio.sleep(interval)

    async def _tick(self, service) -> None:
        # Only the tracked aircraft: one serial query, one credit.
        #
        # If nothing is being followed, do not poll at all. Querying with
        # an empty watchlist means ``icao24`` is omitted, which turns the
        # request into a *global* query costing 4 credits — for data
        # nobody asked for. Measured cost of that oversight: 24 credits
        # per hour, every hour, with the browser open and nothing tracked.
        db = SessionLocal()
        try:
            tracked = tracked_icao24s(db)
            slot_colors = _slot_colors(db)
        finally:
            db.close()

        if not tracked:
            for sub in list(self.clients):
                await sub.send_status(
                    "idle",
                    message=(
                        "Sin aeronaves en seguimiento: no se consulta "
                        "OpenSky para ahorrar créditos."
                    ),
                )
            return

        if not service.configured:
            for sub in list(self.clients):
                await sub.send_status(
                    "not_configured",
                    message=(
                        "OpenSky no está configurado. Defina "
                        "OPENSKY_CLIENT_ID y OPENSKY_CLIENT_SECRET en el .env."
                    ),
                )
            return

        try:
            data = await service.get_states(icao24=tracked or None)
        except RateLimitedError as exc:
            for sub in list(self.clients):
                await sub.send_throttled(str(exc), exc.retry_after_s)
            return
        except (OpenSkyNotConfigured, OpenSkyError) as exc:
            for sub in list(self.clients):
                await sub.send({"type": "error", "message": str(exc)})
            return

        states = data.get("states") or []
        changed_payloads: list[dict] = []
        # A tracked aircraft that stopped transmitting drops out of the
        # response; tell the client rather than leaving a marker stale.
        returned = {s.get("icao24") for s in states}
        missing = [code for code in tracked if code not in returned]
        for code in missing:
            for sub in list(self.clients):
                if sub.wants(code):
                    await sub.send(
                        {
                            "type": "lost",
                            "icao24": code,
                            "message": (
                                "OpenSky no devuelve esta aeronave: puede no "
                                "transmitir, o haber salido de su cobertura."
                            ),
                        }
                    )

        for sub in list(self.clients):
            updates = []
            for state in states:
                if not sub.wants(state["icao24"]):
                    continue
                if not sub.changed(state):
                    continue
                enriched = {
                    **state,
                    "color": sub.slot_colors.get(state["icao24"])
                    or _color_for(state["icao24"], slot_colors),
                    "slot": slot_colors.get(state["icao24"]),
                }
                updates.append(enriched)
                changed_payloads.append(enriched)

            if updates:
                # Data is flowing again: allow a later status change to be
                # reported instead of being suppressed as a repeat.
                sub.clear_status()
                await sub.send(
                    {
                        "type": "states",
                        "time": data.get("time"),
                        "time_utc": _iso(data.get("time")),
                        "count": len(updates),
                        "states": updates,
                        "from_cache": data.get("from_cache"),
                    }
                )

        # Record into any open session (spec §24).
        if changed_payloads:
            await self._record(changed_payloads)

    async def _record(self, states: list[dict]) -> None:
        """Append new positions to any active recording session."""
        db = SessionLocal()
        try:
            open_sessions = {
                s.icao24: s
                for s in db.query(FlightSession)
                .filter(FlightSession.status == SESSION_RECORDING)
                .all()
            }
            if not open_sessions:
                return
            for state in states:
                session = open_sessions.get(state["icao24"])
                if session is None:
                    continue
                try:
                    record_sample(db, session.id, state)
                except Exception as exc:
                    flight_log.error(
                        "session.record_failed", "could not record sample",
                        session_id=session.id, icao24=state["icao24"],
                        error=str(exc),
                    )
        finally:
            db.close()


def _slot_colors(db) -> dict[str, int]:
    return {r.icao24: r.slot for r in db.query(FlightSelection).all()}


def _color_for(icao24: str, slots: dict[str, int]) -> str:
    slot = slots.get(icao24)
    if slot is None:
        return SLOT_COLORS[0]
    return SLOT_COLORS[slot % len(SLOT_COLORS)]


def _iso(ts: Optional[int]) -> Optional[str]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


hub = Hub()


# ─── Endpoint ────────────────────────────────────────────────────────────────

@router.websocket("/ws/flights")
async def flights_socket(websocket: WebSocket):
    """Live aircraft feed.

    Client → server:
        ``{"action": "track", "icao24": ["abc123", "def456"]}``
        ``{"action": "untrack"}``  — widen back to everything
        ``{"action": "ping"}``

    Server → client:
        ``{"type": "hello",   ...}``  handshake with limits and config
        ``{"type": "states",  ...}``  changed aircraft only
        ``{"type": "throttled", ...}`` rate-limit notice
        ``{"type": "error",   ...}``
    """
    await websocket.accept()
    sub = FlightSubscription(websocket)
    settings = get_settings()

    await sub.send(
        {
            "type": "hello",
            "max_tracked": settings.max_tracked_aircraft,
            "poll_interval_s": settings.live_poll_interval_s,
            "opensky_configured": get_opensky_service().configured,
            "server_time": datetime.now(timezone.utc).isoformat(),
            "note": (
                "Solo se envían los cambios: un avión cuyo estado no se ha "
                "movido no genera tráfico."
            ),
        }
    )

    await hub.connect(sub)
    await hub.start_polling()

    receiver = asyncio.create_task(_receive(websocket, sub))
    try:
        while sub.alive:
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        receiver.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await receiver
        await hub.disconnect(sub)


async def _receive(websocket: WebSocket, sub: FlightSubscription) -> None:
    """Handle inbound control messages."""
    try:
        while True:
            message = await websocket.receive_json()
            action = (message or {}).get("action")

            if action == "track":
                codes = message.get("icao24") or []
                if isinstance(codes, str):
                    codes = [codes]
                sub.icao24s = [
                    str(c).strip().lower() for c in codes if str(c).strip()
                ]
                sub.slot_colors = message.get("colors") or sub.slot_colors
                await sub.send(
                    {
                        "type": "subscribed",
                        "icao24": sub.icao24s,
                        "watching": "specific" if sub.icao24s else "all",
                    }
                )
            elif action == "untrack":
                sub.icao24s = []
                await sub.send({"type": "subscribed", "icao24": [], "watching": "all"})
            elif action == "ping":
                await sub.send({"type": "pong"})
            else:
                await sub.send(
                    {"type": "error", "message": f"Unknown action: {action!r}"}
                )
    except (WebSocketDisconnect, RuntimeError):
        sub.alive = False
    except asyncio.CancelledError:
        raise
    except Exception:
        sub.alive = False
