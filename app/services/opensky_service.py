"""
services/opensky_service.py
───────────────────────────
`OpenSkyService` — the only component that talks to OpenSky (spec §19).

Design constraints taken from the OpenSky REST documentation:

* **Three independent credit buckets** (``states``, ``tracks``,
  ``flights``). Spending on one does not affect the others, so the cache
  is partitioned per pool and the pools never share entries.
* **Track and flight cost scales with day partitions crossed** — 4 credits
  for a live/under-24 h window, 30 for 1–2 partitions, then 60×N and up.
  :func:`estimate_track_credits` exposes that so the UI can warn before
  an expensive query, and :func:`clamp_track_window` keeps windows tight.
* **Track waypoints are not one per second.** They are selected per
  OpenSky's own rules (at least every 15 min, a turn beyond 2.5°, an
  altitude change beyond 100 m, an on-ground change). The parser therefore
  preserves real waypoint timestamps and reports the actual temporal
  density rather than pretending to 1 Hz data.
* **404 means "no flights found"**, not failure. It is translated into an
  empty result so the UI shows "no data" instead of an error.
* **429 carries** ``X-Rate-Limit-Retry-After-Seconds`` and trips the
  backoff controller.
"""

from __future__ import annotations

import asyncio
import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence

import httpx

from app.core.config import get_settings
from app.core.logging import opensky_log, timed
from app.core.time import from_unix
from app.services.cache import (
    POOL_FLIGHTS,
    POOL_STATES,
    POOL_TRACKS,
    BackoffController,
    CreditAwareClient,
    RateLimitedError,
)
from app.services.opensky_client import (
    OpenSkyAuthError,
    OpenSkyTokenManager,
    get_token_manager,
)

# ─── State vector column indices (OpenSky REST) ─────────────────────────────
SV_ICAO24 = 0
SV_CALLSIGN = 1
SV_ORIGIN_COUNTRY = 2
SV_TIME_POSITION = 3
SV_LAST_CONTACT = 4
SV_LONGITUDE = 5
SV_LATITUDE = 6
SV_BARO_ALTITUDE = 7
SV_ON_GROUND = 8
SV_VELOCITY = 9
SV_TRUE_TRACK = 10
SV_VERTICAL_RATE = 11
SV_SENSORS = 12
SV_GEO_ALTITUDE = 13
SV_SQUAWK = 14
SV_SPI = 15
SV_POSITION_SOURCE = 16
SV_CATEGORY = 17

#: **Verified against a live response on 2026-09-25** (13 360 aircraft):
#: the default ``/states/all`` payload has **17** fields, indices 0-16.
#: ``category`` (index 17) is only present when the request sets
#: ``extended=1``. The documentation lists all 18 fields in one table,
#: which describes the *extended* shape — a parser that requires 18
#: silently rejects every aircraft ever published.
SV_MIN_FIELDS = 17
SV_MIN_FIELDS_EXTENDED = 18

#: Human labels for ``position_source``.
POSITION_SOURCES = {0: "ADS-B", 1: "ASTERIX", 2: "MLAT", 3: "FLARM"}

#: Minimal named aircraft classes (OpenSky category 0..20).
AIRCRAFT_CATEGORIES = {
    0: "Sin información", 1: "Categoría desconocida",
    2: "Ligero (< 7 032 kg)", 3: "Pequeño (7 032–34 019 kg)",
    4: "Grande (34 019–136 078 kg)", 5: "Gran plasma (p. ej. B-757)",
    6: "Pesado (> 136 078 kg)", 7: "Alto rendimiento",
    8: "Rotores", 9: "Planeador / velero", 10: "Más ligero que el aire",
    11: "Paracaidista", 12: "Ultraliviano", 13: "Reservado",
    14: "Vehículo aéreo no tripulado", 15: "Espacial / transatmosférico",
    16: "Vehículo de superficie", 17: "Vehículo de servicio",
    18: "Punto de obstáculo", 19: "Conjunto de obstáculos",
    20: "Obstáculo lineal",
}

#: OpenSky hard limits on request windows.
MAX_FLIGHTS_ALL_WINDOW_S = 2 * 3600        # 2 hours
#: Widest window `/flights/aircraft` accepts, measured rather than assumed.
#:
#: The comment used to say "2 days" and the value said 48 h, but OpenSky
#: rejects anything from 47 h upward and answers 25 h without complaint. Probed
#: against the live API: 1, 6, 12, 23, 24 and 25 h succeed; 47, 48, 49, 50 and
#: 72 h return 400. The endpoint's real ceiling sits between 25 and 47 h, so a
#: window of 24 h is used: it works, and it keeps every request inside a single
#: UTC day for all but a few hours, which keeps the credit estimate low.
#:
#: Clamping to 48 h was not conservative, it was out of range: the request went
#: out and OpenSky rejected it, and a flight list for yesterday could not be
#: built at all.
MAX_FLIGHTS_AIRCRAFT_WINDOW_S = 24 * 3600  # 24 h — see the probe above
MAX_TRACK_AGE_S = 30 * 86400               # tracks beyond 30 days unavailable

#: OpenSky "live" is within this window.
LIVE_WINDOW_S = 3 * 3600


class OpenSkyError(RuntimeError):
    """Upstream or configuration failure talking to OpenSky."""

    def __init__(self, message: str, status: int | None = None, pool: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.pool = pool


class OpenSkyNotConfigured(OpenSkyError):
    """Credentials are absent. Feature degrades, the app keeps working."""


# ─── Credit estimation (spec §49) ───────────────────────────────────────────

def estimate_track_credits(begin_s: int, end_s: int) -> int:
    """Credits a ``/tracks`` or ``/flights`` query will cost.

    Mirrors OpenSky's published table for calendar-day partitions
    crossed by the time range.
    """
    if end_s <= begin_s:
        return 4
    if end_s - begin_s <= 86400:
        return 4                       # live / under 24 h
    partitions = _day_partitions(begin_s, end_s)
    if partitions <= 2:
        return 30
    if partitions <= 10:
        return 60 * partitions
    if partitions <= 15:
        return 120 * partitions
    if partitions <= 20:
        return 240 * partitions
    if partitions <= 25:
        return 480 * partitions
    return 960 * partitions


def _day_partitions(begin_s: int, end_s: int) -> int:
    """Number of distinct UTC calendar days touched by ``[begin, end]``."""
    d0 = datetime.fromtimestamp(begin_s, tz=timezone.utc).date()
    d1 = datetime.fromtimestamp(end_s, tz=timezone.utc).date()
    return (d1 - d0).days + 1


def estimate_states_credits(
    lat_min: float | None = None,
    lon_min: float | None = None,
    lat_max: float | None = None,
    lon_max: float | None = None,
) -> int:
    """Credits a ``/states/all`` query will cost, by bounding-box area.

    OpenSky bills square degrees of the requested box. A query filtered
    only by ``icao24`` (a serial query) always costs 1 credit regardless
    of how many aircraft it returns, which is why the watchlist is capped
    at five and fetched in one call.
    """
    if None in (lat_min, lon_min, lat_max, lon_max):
        return 1  # serial-only query
    area = abs(lat_max - lat_min) * abs(lon_max - lon_min)
    if area <= 25:
        return 1
    if area <= 100:
        return 2
    if area <= 400:
        return 3
    return 4


# ─── Parsing ─────────────────────────────────────────────────────────────────

def parse_state_vector(row: Sequence[Any], now_ts: Optional[int] = None) -> dict | None:
    """Turn one OpenSky state-vector row into a typed dict.

    Returns ``None`` only for structurally malformed rows. Fields OpenSky
    did not publish stay ``None`` — they are never back-filled with a
    guess (spec §56).

    Accepts both payload widths: 17 fields by default, 18 with
    ``extended=1``.
    """
    if not isinstance(row, (list, tuple)) or len(row) < SV_MIN_FIELDS:
        return None

    icao24 = (row[SV_ICAO24] or "").strip().lower()
    if not icao24:
        return None

    callsign = (row[SV_CALLSIGN] or "").strip() or None
    lat = row[SV_LATITUDE]
    lon = row[SV_LONGITUDE]

    # Prefer geometric altitude (true MSL) and fall back to barometric,
    # labelling which one was used. Both are reported because the
    # difference matters for a 118 MHz investigation.
    geo_alt = row[SV_GEO_ALTITUDE]
    baro_alt = row[SV_BARO_ALTITUDE]
    if geo_alt is not None:
        altitude, altitude_type = geo_alt, "geometric"
    elif baro_alt is not None:
        altitude, altitude_type = baro_alt, "barometric"
    else:
        altitude, altitude_type = None, None

    pos_source = row[SV_POSITION_SOURCE]
    # `category` is index 17 and is only present with extended=1.
    category = row[SV_CATEGORY] if len(row) >= SV_MIN_FIELDS_EXTENDED else None

    time_position = row[SV_TIME_POSITION]
    # How stale the *position* is. A live capture on 2026-09-25 showed
    # positions up to 1.5 h old on aircraft still transmitting other
    # messages, so the UI can flag them rather than present them as live.
    position_age_s = (
        (now_ts - int(time_position))
        if (now_ts is not None and time_position is not None)
        else None
    )

    return {
        "icao24": icao24,
        "callsign": callsign,
        "origin_country": row[SV_ORIGIN_COUNTRY],
        # time_position is when the *position* was measured; last_contact
        # is when any message arrived. Keeping them apart avoids the bug
        # present in the previous implementation, which used last_contact
        # as if it were a position timestamp.
        "time_position": row[SV_TIME_POSITION],
        "last_contact": row[SV_LAST_CONTACT],
        "position_age_s": position_age_s,
        "latitude": _f(lat),
        "longitude": _f(lon),
        "altitude": _f(altitude),
        "altitude_type": altitude_type,
        "baro_altitude": _f(baro_alt),
        "geo_altitude": _f(geo_alt),
        "on_ground": bool(row[SV_ON_GROUND]) if row[SV_ON_GROUND] is not None else None,
        "velocity": _f(row[SV_VELOCITY]),
        "heading": _f(row[SV_TRUE_TRACK]),
        "vertical_rate": _f(row[SV_VERTICAL_RATE]),
        "squawk": row[SV_SQUAWK],
        "spi": row[SV_SPI],
        "position_source": (
            POSITION_SOURCES.get(pos_source) if pos_source is not None else None
        ),
        "category": (
            AIRCRAFT_CATEGORIES.get(category) if category is not None else None
        ),
        "category_id": category,
        "has_position": lat is not None and lon is not None,
    }


def parse_waypoint(point: Sequence[Any]) -> dict | None:
    """Parse one track waypoint ``[time, lat, lon, baro_alt, track, on_ground]``."""
    if not isinstance(point, (list, tuple)) or len(point) < 6:
        return None
    ts, lat, lon, alt, track, on_ground = point[:6]
    if lat is None or lon is None:
        # OpenSky can emit waypoints without a position; skip rather than
        # place a point at (0, 0).
        return None
    return {
        "timestamp": int(ts) if ts is not None else None,
        "latitude": _f(lat),
        "longitude": _f(lon),
        "altitude": _f(alt),
        "heading": _f(track),
        "on_ground": bool(on_ground) if on_ground is not None else None,
    }


def parse_track(payload: dict) -> dict:
    """Parse a ``/tracks/all`` response.

    Deliberately reports the *observed* temporal distribution so the UI can
    state it rather than assuming 1 Hz.

    Why the distribution and not the mean
    ------------------------------------
    Measured on three real tracks on 2026-09-25, the gap between
    consecutive waypoints ranged from 2 s to 890 s, with a median near
    28 s but a mean around 80 s. A mean on its own is badly misleading:
    it is dragged upward by the long straight-line gaps and hides the
    fact that an aircraft in a turn produces waypoints every few seconds.
    AeroRF reports the range and the median because that is what an
    operator needs in order to judge a track's fidelity.
    """
    if not isinstance(payload, dict):
        return {"icao24": None, "points": [], "point_count": 0}

    icao24 = (payload.get("icao24") or "").strip().lower() or None
    raw_path = payload.get("path") or []
    points = [p for p in (parse_waypoint(w) for w in raw_path) if p]
    # OpenSky labels this "calllsign" (sic) in some responses and
    # "callsign" in others; accept both.
    callsign = payload.get("callsign") or payload.get("calllsign")

    times = [p["timestamp"] for p in points if p.get("timestamp") is not None]
    times_sorted = sorted(times)
    span_s = (times_sorted[-1] - times_sorted[0]) if len(times_sorted) >= 2 else 0
    steps = sorted(
        b - a for a, b in zip(times_sorted, times_sorted[1:]) if b >= a
    )

    return {
        "icao24": icao24,
        "callsign": (callsign or "").strip() or None,
        "start_time": payload.get("startTime") or (times_sorted[0] if times_sorted else None),
        "end_time": payload.get("endTime") or (times_sorted[-1] if times_sorted else None),
        "points": points,
        "point_count": len(points),
        "span_s": span_s,
        "step_min_s": steps[0] if steps else None,
        "step_median_s": statistics.median(steps) if steps else None,
        "step_max_s": steps[-1] if steps else None,
        "mean_step_s": (sum(steps) / len(steps)) if steps else None,
        "altitude_range": _altitude_range(points),
        "suspect_altitudes": _suspect_altitudes(points),
        "resolution_note": _resolution_note(
            len(points), span_s,
            steps[0] if steps else None,
            statistics.median(steps) if steps else None,
            steps[-1] if steps else None,
        ),
        "source": "opensky",
    }


def _altitude_range(points: list[dict]) -> dict | None:
    alts = [p["altitude"] for p in points if p.get("altitude") is not None]
    if not alts:
        return None
    return {"min_m": min(alts), "max_m": max(alts)}


def _suspect_altitudes(points: list[dict]) -> list[dict]:
    """Waypoints whose barometric altitude is not physically plausible.

    Measured on a real track (2026-09-25): one aircraft published
    ``-304 m``, which is a pressure artefact rather than a descent below
    sea level, and another published exactly ``0``. In an aeronautical
    investigation a bogus altitude on a profile is worse than a missing
    one, so these are flagged instead of being plotted as fact.
    """
    suspect: list[dict] = []
    for index, point in enumerate(points):
        altitude = point.get("altitude")
        if altitude is None:
            continue
        if altitude < 0 or altitude == 0:
            suspect.append({"index": index, "altitude_m": altitude})
    return suspect


def _resolution_note(count, span_s, step_min, step_median, step_max) -> str:
    if count < 2:
        return (
            "Un solo waypoint: no hay trayectoria que evaluar. Los tracks de "
            "OpenSky son experimentales y sus waypoints no son un punto por "
            "segundo."
        )
    if step_median is None:
        return "Waypoints de OpenSky, sin paso temporal calculable."

    return (
        f"{count} waypoints en {_hms(span_s)} · paso mediano {_hms(step_median)}, "
        f"mínimo {step_min:.0f} s, máximo {step_max:.0f} s. OpenSky agrega un "
        f"waypoint al cambiar el rumbo más de 2,5°, la altitud más de 100 m o "
        f"el estado en tierra, y al menos uno cada 15 min: la resolución NO es "
        f"uniforme y no es de un punto por segundo."
    )


def _hms(seconds) -> str:
    seconds = int(round(seconds or 0))
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {(seconds % 3600) // 60} min"


def _f(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


# ─── Service ─────────────────────────────────────────────────────────────────

class OpenSkyService:
    """Async client for the OpenSky REST API with caching and credit control."""

    def __init__(
        self,
        token_manager: Optional[OpenSkyTokenManager] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.settings = get_settings()
        self.tokens = token_manager or get_token_manager()
        self.base_url = (base_url or self.settings.opensky_base_url).rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=self.settings.opensky_timeout_s,
            headers={"User-Agent": "AeroRF/1.0 (ENACOM RF investigation tool)"},
        )

        # One backoff controller shared by all pools: a 429 means the
        # account is over budget, and hammering a different endpoint
        # would only make it worse.
        self.backoff = BackoffController(
            base_s=self.settings.opensky_backoff_base_s,
            max_s=self.settings.opensky_backoff_max_s,
        )
        self.states = CreditAwareClient(
            POOL_STATES, self.settings.cache_ttl_states_s, self.backoff
        )
        self.tracks = CreditAwareClient(
            POOL_TRACKS, self.settings.cache_ttl_tracks_s, self.backoff
        )
        self.flights = CreditAwareClient(
            POOL_FLIGHTS, self.settings.cache_ttl_flights_s, self.backoff
        )

    # ─── Internals ────────────────────────────────────────────────────────
    @property
    def configured(self) -> bool:
        """True when OAuth2 client credentials are present."""
        return self.tokens.configured

    @property
    def can_query_states(self) -> bool:
        """True when live state vectors can be fetched.

        OpenSky serves ``/states/all`` to anonymous callers from a
        400-credit daily pool, so AeroRF is usable for live traffic
        without an account. Everything else needs credentials.
        """
        return self.configured or self.settings.opensky_allow_anonymous

    @property
    def requires_credentials(self) -> bool:
        """True when the request will carry a Bearer token."""
        return self.configured

    def _can_reach(self, path: str) -> bool:
        """Whether this endpoint is reachable in the current auth mode.

        Verified live on 2026-09-25: ``/states/all`` answers 200
        anonymously, ``/tracks/all`` answers 200 but empty, and
        ``/flights/*`` answers 403.
        """
        if self.configured:
            return True
        if not self.settings.opensky_allow_anonymous:
            return False
        return path.startswith("states/")

    async def _headers(self, path: str = "") -> dict[str, str]:
        """Auth headers for a request, or none when running anonymous."""
        if not self.configured:
            if not self._can_reach(path):
                raise OpenSkyNotConfigured(
                    "Este endpoint de OpenSky requiere credenciales OAuth2. "
                    "Defina OPENSKY_CLIENT_ID y OPENSKY_CLIENT_SECRET en el "
                    ".env del backend. (El tráfico en vivo de /states/all "
                    "funciona sin credenciales.)"
                )
            return {}
        try:
            return await self.tokens.auth_headers()
        except OpenSkyAuthError as exc:
            raise OpenSkyNotConfigured(str(exc)) from exc

    async def _request(
        self,
        path: str,
        params: Optional[dict] = None,
        pool: str = POOL_STATES,
    ) -> Any:
        """Perform one GET with error mapping and 401 replay.

        Sends a Bearer token when credentials exist; otherwise calls
        anonymously, which OpenSky permits for ``/states/all`` only.
        """
        url = f"{self.base_url}/api/{path.lstrip('/')}"
        anonymous = not self.configured

        for attempt in (1, 2):
            headers = await self._headers(path)
            query = {k: v for k, v in (params or {}).items() if v is not None}

            with timed(
                "opensky.request", opensky_log,
                endpoint=path, attempt=attempt, pool=pool,
                auth="anonymous" if anonymous else "oauth2",
            ):
                try:
                    response = await self._client.get(url, params=query, headers=headers)
                except httpx.TimeoutException as exc:
                    opensky_log.error(
                        "opensky.timeout", "request timed out",
                        endpoint=path, pool=pool,
                    )
                    raise OpenSkyError(
                        f"OpenSky did not respond within "
                        f"{self.settings.opensky_timeout_s:.0f}s ({path}).",
                        pool=pool,
                    ) from exc
                except httpx.HTTPError as exc:
                    opensky_log.error(
                        "opensky.network_error", "network failure",
                        endpoint=path, error=type(exc).__name__, pool=pool,
                    )
                    raise OpenSkyError(
                        f"Could not reach OpenSky ({path}): {exc}", pool=pool
                    ) from exc

            status = response.status_code

            if status == 401:
                if anonymous:
                    # Nothing to refresh: the call went out with no token.
                    raise OpenSkyNotConfigured(
                        f"OpenSky rechazó la petición anónima ({path}). "
                        f"Configure las credenciales OAuth2."
                    )
                # Token rejected/expired: invalidate, refresh, replay once.
                opensky_log.warning(
                    "opensky.unauthorized", "401 from OpenSky, refreshing token",
                    endpoint=path, pool=pool, attempt=attempt,
                )
                self.tokens.invalidate()
                if attempt == 1:
                    continue
                raise OpenSkyError(
                    "OpenSky rejected the access token twice. Check the "
                    "client credentials in the backend .env.",
                    status=401, pool=pool,
                )

            if status == 403:
                # Documented: /flights/* and /states/own need credentials.
                opensky_log.info(
                    "opensky.forbidden", "403 from OpenSky",
                    endpoint=path, pool=pool,
                    auth="anonymous" if anonymous else "oauth2",
                )
                raise OpenSkyNotConfigured(
                    f"OpenSky exige credenciales OAuth2 para {path}. "
                    f"Defina OPENSKY_CLIENT_ID y OPENSKY_CLIENT_SECRET en el .env."
                )

            if status == 429:
                retry_after = _retry_after(response)
                delay = self.backoff.trip(retry_after)
                remaining = response.headers.get("X-Rate-Limit-Remaining")
                opensky_log.warning(
                    "opensky.rate_limited", "429 from OpenSky",
                    endpoint=path, pool=pool, backoff_s=round(delay, 1),
                    credits_remaining=remaining,
                )
                raise RateLimitedError(
                    f"OpenSky credit limit reached for /{path}. "
                    f"Pausing calls for {delay:.0f}s.",
                    retry_after_s=delay, pool=pool,
                )

            if status == 404:
                # Documented behaviour: "no flights found". Not an error.
                opensky_log.info(
                    "opensky.not_found", "404 from OpenSky (no data)",
                    endpoint=path, pool=pool,
                )
                return None

            if status == 400:
                opensky_log.warning(
                    "opensky.bad_request", "400 from OpenSky", endpoint=path, pool=pool
                )
                raise OpenSkyError(
                    f"OpenSky rejected the request parameters ({path}). "
                    "Check the time window and identifiers.",
                    status=400, pool=pool,
                )

            if status >= 500:
                opensky_log.error(
                    "opensky.server_error", "5xx from OpenSky",
                    endpoint=path, status=status, pool=pool,
                )
                raise OpenSkyError(
                    f"OpenSky server error ({status}) on {path}. Try again shortly.",
                    status=status, pool=pool,
                )

            if status >= 400:
                opensky_log.warning(
                    "opensky.client_error", "unexpected status",
                    endpoint=path, status=status, pool=pool,
                )
                raise OpenSkyError(
                    f"OpenSky returned HTTP {status} for {path}.",
                    status=status, pool=pool,
                )

            self.backoff.clear()
            return _decode(response)

        raise OpenSkyError("OpenSky request failed after retry.", pool=pool)  # pragma: no cover

    async def _cached(
        self, client: CreditAwareClient, key: str, path: str,
        params: Optional[dict] = None, ttl: Optional[float] = None,
    ) -> tuple[Any, bool]:
        async def call() -> Any:
            return await self._request(path, params, pool=client.pool)

        return await client.fetch(key, call, ttl)

    # ─── /states/all (spec §23, §25) ──────────────────────────────────────
    async def get_states(
        self,
        icao24: Optional[Sequence[str]] = None,
        bbox: Optional[tuple[float, float, float, float]] = None,
        time_: Optional[int] = None,
        extended: bool = False,
    ) -> dict:
        """Current state vectors.

        ``icao24`` accepts a list, which is what makes the five-aircraft
        watchlist affordable: one serial query, one credit, instead of
        five.

        ``bbox`` is ``(lat_min, lon_min, lat_max, lon_max)``. Bounding-box
        queries cost 2–4 credits depending on area, so prefer ``icao24``
        when the aircraft are already known.
        """
        params: dict[str, Any] = {}
        codes = [str(c).strip().lower() for c in (icao24 or []) if c]
        if codes:
            # httpx repeats the key when given a list.
            params["icao24"] = codes
        if bbox is not None:
            lat_min, lon_min, lat_max, lon_max = bbox
            params.update(
                lamin=lat_min, lomin=lon_min, lamax=lat_max, lomax=lon_max
            )
        if time_ is not None:
            params["time"] = int(time_)
        if extended:
            params["extended"] = 1

        key = "states:" + "&".join(
            f"{k}={','.join(map(str, v)) if isinstance(v, list) else v}"
            for k, v in sorted(params.items())
        )
        data, from_cache = await self._cached(self.states, key, "states/all", params)
        return self._states_result(data, from_cache)

    async def get_states_for(self, icao24: Sequence[str]) -> dict:
        """State vectors for a specific set of aircraft (≤5 in practice)."""
        return await self.get_states(icao24=icao24)

    async def get_states_in_box(
        self, lat_min: float, lon_min: float, lat_max: float, lon_max: float
    ) -> dict:
        """State vectors inside a WGS84 bounding box."""
        return await self.get_states(bbox=(lat_min, lon_min, lat_max, lon_max))

    def _states_result(self, data: Any, from_cache: bool) -> dict:
        raw = (data or {}).get("states") or []
        # The response's own `time` is the reference for position age —
        # using the local clock would drift against OpenSky's window.
        now_ts = (data or {}).get("time")
        vectors = [v for v in (parse_state_vector(r, now_ts) for r in raw) if v]
        out = {
            "time": now_ts,
            "time_utc": from_unix(now_ts),
            "count": len(vectors),
            "states": vectors,
            "from_cache": from_cache,
            "source": "opensky",
            "provenance": "live",
            "auth": "oauth2" if self.configured else "anonymous",
        }
        if not self.configured:
            out["notice"] = (
                "Acceso anónimo a OpenSky: 400 créditos diarios por IP, "
                "resolución temporal de 10 s y solo los vectores más "
                "recientes. Configure credenciales OAuth2 para historial."
            )
        return out

    # ─── /tracks/all (spec §22) ───────────────────────────────────────────
    async def get_track(self, icao24: str, time_: Optional[int] = None) -> dict:
        """Trajectory for one aircraft.

        ``time_=0`` asks for the live track (spec §23). OpenSky caps
        history at 30 days.
        """
        code = str(icao24).strip().lower()
        params = {"icao24": code}
        if time_ is not None:
            params["time"] = int(time_)

        key = f"tracks:{code}:{params.get('time', 'live')}"
        data, from_cache = await self._cached(
            self.tracks, key, "tracks/all", params
        )

        if data is None:
            return {
                "icao24": code, "points": [], "point_count": 0,
                "from_cache": from_cache, "source": "opensky",
                "provenance": "historical", "available": False,
                "note": "OpenSky no tiene track para este vuelo en esa ventana.",
            }

        parsed = parse_track(data)
        parsed["from_cache"] = from_cache
        parsed["available"] = parsed["point_count"] > 0
        parsed["provenance"] = "historical" if params.get("time") else "live"
        return parsed

    async def get_live_track(self, icao24: str) -> dict:
        """The ongoing flight's track, if any (spec §23)."""
        return await self.get_track(icao24, time_=0)

    # ─── /flights/* (spec §20) ────────────────────────────────────────────
    async def get_flights(
        self,
        begin: int,
        end: int,
        airport: Optional[str] = None,
        icao24: Optional[str] = None,
    ) -> list[dict]:
        """Flights in a window, via the most specific endpoint available.

        Chooses ``/flights/aircraft`` when an ICAO24 is known, otherwise
        ``/flights/arrival`` or ``/flights/departure`` for an airport, and
        falls back to ``/flights/all``. This avoids the broad, expensive
        query when a narrow one answers the question (spec §19: "no
        consultar OpenSky innecesariamente").
        """
        begin, end = int(begin), int(end)

        if icao24:
            # Endpoint cap: 2 days.
            begin, end = _clamp(begin, end, MAX_FLIGHTS_AIRCRAFT_WINDOW_S)
            key = f"flights:aircraft:{str(icao24).lower()}:{begin}:{end}"
            data, _ = await self._cached(
                self.flights, key, "flights/aircraft",
                {"icao24": str(icao24).lower(), "begin": begin, "end": end},
            )
        elif airport:
            begin, end = _clamp(begin, end, MAX_FLIGHTS_AIRCRAFT_WINDOW_S)
            kind = "arrival" if airport[0].lower() == "arrival" else "departure"
            ap = airport[3:].upper() if len(airport) > 3 else airport.upper()
            key = f"flights:{kind}:{ap}:{begin}:{end}"
            data, _ = await self._cached(
                self.flights, key, f"flights/{kind}",
                {"airport": ap, "begin": begin, "end": end},
            )
        else:
            begin, end = _clamp(begin, end, MAX_FLIGHTS_ALL_WINDOW_S)
            key = f"flights:all:{begin}:{end}"
            data, _ = await self._cached(
                self.flights, key, "flights/all", {"begin": begin, "end": end}
            )

        return data if isinstance(data, list) else []

    async def get_flights_all(self, begin: int, end: int) -> list[dict]:
        return await self.get_flights(begin, end)

    async def get_flights_by_aircraft(
        self, icao24: str, begin: int, end: int
    ) -> list[dict]:
        return await self.get_flights(begin, end, icao24=icao24)

    async def get_arrivals(self, airport: str, begin: int, end: int) -> list[dict]:
        return await self.get_flights(begin, end, airport=f"arrival:{airport}")

    async def get_departures(self, airport: str, begin: int, end: int) -> list[dict]:
        return await self.get_flights(begin, end, airport=f"departure:{airport}")

    # ─── Diagnostics ──────────────────────────────────────────────────────
    def status(self) -> dict:
        """Service health for /api/system/status. Contains no secrets."""
        out = {
            "configured": self.configured,
            "auth_mode": "oauth2" if self.configured else "anonymous",
            "can_query_states": self.can_query_states,
            "base_url": self.base_url,
            "token": self.tokens.status(),
            "pools": {
                "states": self.states.stats(),
                "tracks": self.tracks.stats(),
                "flights": self.flights.stats(),
            },
        }
        if not self.configured and self.settings.opensky_allow_anonymous:
            out["anonymous_note"] = (
                "Sin credenciales: /states/all funciona anónimamente "
                "(400 créditos/día por IP, resolución 10 s). "
                "/flights/* y /tracks/* requieren OAuth2."
            )
        return out

    def invalidate(self, pool: str | None = None) -> None:
        """Clear cached data. ``pool`` may be states/tracks/flights."""
        if pool in (None, "all"):
            self.states.invalidate()
            self.tracks.invalidate()
            self.flights.invalidate()
        elif pool == "states":
            self.states.invalidate()
        elif pool == "tracks":
            self.tracks.invalidate()
        elif pool == "flights":
            self.flights.invalidate()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _clamp(begin: int, end: int, max_span_s: int) -> tuple[int, int]:
    """Keep a window inside OpenSky's endpoint limit without reordering it."""
    if end - begin > max_span_s:
        end = begin + max_span_s
    return begin, end


def _retry_after(response: httpx.Response) -> Optional[float]:
    raw = response.headers.get("X-Rate-Limit-Retry-After-Seconds")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return None


def _decode(response: httpx.Response) -> Any:
    import json

    try:
        return response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise OpenSkyError("OpenSky returned a non-JSON response.") from exc


# ─── Process-wide singleton ──────────────────────────────────────────────────
_service: Optional[OpenSkyService] = None


def get_opensky_service() -> OpenSkyService:
    global _service
    if _service is None:
        _service = OpenSkyService()
    return _service


def reset_opensky_service() -> None:
    """Drop the singleton. Test helper."""
    global _service
    _service = None
