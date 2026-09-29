"""
services/flight_service.py
──────────────────────────
Flight search, trajectory assembly, local recording and the watchlist
(spec §20–§27, §56).

The governing rule: **never invent a position.** Three distinct
provenance values flow through this module and are preserved all the way
to the API response:

* ``historical`` — a waypoint from OpenSky's track store,
* ``live``       — a current OpenSky state vector,
* ``aerorf``     — a sample AeroRF recorded itself during a session.

When a track is assembled the module reports which sources contributed how
many points, and never back-fills gaps. If OpenSky gives 12 waypoints over
a two-hour flight, the response says 12 points and explains the mean step;
it does not interpolate a 1 Hz line and present it as observed data.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.geo import haversine_m, path_summary
from app.core.logging import flight_log, opensky_log
from app.core.time import utcnow
from app.core.units import to_metres
from app.models.constants import (
    SESSION_ERROR,
    SESSION_RECORDING,
    SESSION_STOPPED,
    TRACK_SOURCE_AERORF,
    TRACK_SOURCE_MERGED,
    TRACK_SOURCE_OPENSKY,
    PROVENANCE_HISTORICAL,
    PROVENANCE_LIVE,
)
from app.models.flight import (
    AircraftPosition,
    AircraftTrack,
    Flight,
    FlightSelection,
    FlightSession,
)
from app.models.map_object import MapObject

#: Distinct colours for the five watchlist slots (spec §25).
SLOT_COLORS = ("#22c55e", "#3b82f6", "#f97316", "#a855f7", "#eab308")

#: Hard cap from the spec.
MAX_TRACKED = 5


class FlightServiceError(RuntimeError):
    """Invalid flight operation."""


def _utc(ts: Optional[int | float]) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).replace(tzinfo=None)
    except (ValueError, OSError, OverflowError):
        return None


# ─── Search (spec §20) ───────────────────────────────────────────────────────

async def search_flight(
    service,
    callsign: Optional[str] = None,
    icao24: Optional[str] = None,
    date: Optional[str] = None,
    time_hint: Optional[str] = None,
    window_hours: int = 6,
) -> dict:
    """Find a flight by callsign or ICAO24.

    OpenSky has no callsign search endpoint, so a callsign lookup is
    resolved in two steps: match the callsign against current state
    vectors to learn the ICAO24, then query ``/flights/aircraft`` for the
    history. Each step is documented in the response under ``resolved_via``
    so the operator can see how the aircraft was identified.
    """
    result: dict[str, Any] = {
        "query": {
            "callsign": callsign, "icao24": icao24,
            "date": date, "time_hint": time_hint, "window_hours": window_hours,
        },
        "resolved_via": None,
        "icao24": None,
        "callsign": None,
        "flights": [],
        "states": [],
        "warnings": [],
    }

    # ── Resolve ICAO24 from a callsign via live state vectors ──────────
    if icao24 and not callsign:
        code = str(icao24).strip().lower()
        if not _valid_icao24(code):
            raise FlightServiceError(
                f"Invalid ICAO24 {icao24!r}: expected 6 hex characters."
            )
        result["icao24"] = code
        result["resolved_via"] = "icao24_direct"
    elif callsign:
        wanted = callsign.strip().upper()
        if not wanted:
            raise FlightServiceError("Empty callsign.")
        live = await service.get_states()
        match = _match_callsign(live.get("states") or [], wanted)
        if match:
            result["icao24"] = match["icao24"]
            result["callsign"] = match.get("callsign")
            result["states"].append(match)
            result["resolved_via"] = "callsign_live_state"
        else:
            result["warnings"].append(
                f"No se encontró ninguna aeronave en vuelo con callsign "
                f"{wanted!r} en este momento. OpenSky no ofrece búsqueda por "
                f"callsign sobre vuelos históricos: sólo se pueden consultar "
                f"vuelos por ICAO24. Busque la aeronave en /states/all o "
                f"proporcione el ICAO24."
            )
            return result

    if not result["icao24"]:
        return result

    code = result["icao24"]

    # ── Historical flights for that aircraft ────────────────────────────
    begin, end = _window(date, time_hint, window_hours)
    try:
        flights = await service.get_flights_by_aircraft(code, begin, end)
    except Exception as exc:  # upstream failures must not kill the search
        result["warnings"].append(
            f"No se pudieron obtener los vuelos históricos: {exc}"
        )
        flights = []

    result["flights"] = [_normalise_flight(f) for f in flights] if flights else []
    if not result["flights"]:
        result["warnings"].append(
            "OpenSky no tiene registro de vuelos para este avión en la ventana "
            "consultada. Los endpoints /flights/* se procesan por lote durante la "
            "noche, por lo que el vuelo del día anterior puede no estar aún."
        )

    return result


def _match_callsign(states: Iterable[dict], wanted: str) -> Optional[dict]:
    """Exact match first, then prefix — never a fuzzy substring guess."""
    exact, prefix = None, None
    for state in states:
        cs = (state.get("callsign") or "").strip().upper()
        if not cs:
            continue
        if cs == wanted:
            exact = state
            break
        if prefix is None and cs.startswith(wanted):
            prefix = state
    return exact or prefix


def _valid_icao24(code: str) -> bool:
    return (
        len(code) == 6
        and all(c in "0123456789abcdef" for c in code)
    )


#: Public alias. The flight-list endpoint validates the same way, and a route
#: that has to reach through a private name is a sign the check belongs here.
valid_icao24 = _valid_icao24


def _window(
    date: Optional[str], time_hint: Optional[str], window_hours: int
) -> tuple[int, int]:
    """Build the ``[begin, end]`` search window.

    Defaults to the last ``window_hours`` hours, which keeps the query
    inside the 2-day / 2-hour endpoint limits and minimises the number of
    day partitions — and therefore credits — that the request spans.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=window_hours)

    if date:
        try:
            base = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise FlightServiceError(
                f"Invalid date {date!r}; expected YYYY-MM-DD."
            )
        if time_hint:
            try:
                hh, mm = (int(x) for x in time_hint.split(":")[:2])
                base = base.replace(hour=hh, minute=mm)
            except (ValueError, TypeError):
                raise FlightServiceError(
                    f"Invalid time {time_hint!r}; expected HH:MM."
                )
        start = base
        end = start + timedelta(hours=window_hours)
    else:
        end = now

    # Never query the future.
    if end > now:
        end = now
    # OpenSky rejects windows in the future or beyond its retention.
    begin_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    if end_ts <= begin_ts:
        end_ts = begin_ts + 3600
    return begin_ts, end_ts


def _normalise_flight(flight: dict) -> dict:
    """Normalise an OpenSky flight record, preserving nulls as nulls.

    Key casing
    ----------
    OpenSky's REST documentation renders the ``/flights/*`` fields in
    lower case, but the wire format is **camelCase**. Verified against a
    real response on 2026-09-25, which contained::

        firstSeen  lastSeen  estDepartureAirport  estArrivalAirport
        departureAirportCandidatesCount

    with **no** ``firstseen``, ``estdepartureairport`` or ``dep_lat``.
    Reading the documented lower-case names silently produced a flight
    record whose times and airports were all ``None``, so both spellings
    are accepted here.

    Also, ``dep_lat``/``arr_lat`` were never present in the observed
    payload; when OpenSky cannot resolve an airport it reports null and a
    candidates count of 0, which is surfaced rather than faked.
    """
    # Accept either casing for every field.
    first = _pick(flight, "firstSeen", "firstseen")
    last = _pick(flight, "lastSeen", "lastseen")
    departure = _pick(flight, "estDepartureAirport", "estdepartureairport")
    arrival = _pick(flight, "estArrivalAirport", "estarrivalairport")
    callsign_icao = _pick(flight, "callsign_icao", "callsignIcao")
    dep_lat = _pick(flight, "dep_lat", "depLat", "departure_lat")
    dep_lon = _pick(flight, "dep_lon", "depLon", "departure_lon")
    arr_lat = _pick(flight, "arr_lat", "arrLat", "arrival_lat")
    arr_lon = _pick(flight, "arr_lon", "arrLon", "arrival_lon")

    # How many candidate airports OpenSky considered. 0 means it could
    # not resolve one — normal, and worth reporting instead of hiding.
    dep_candidates = _pick(
        flight, "departureAirportCandidatesCount", "departure_airport_candidates_count"
    )
    arr_candidates = _pick(
        flight, "arrivalAirportCandidatesCount", "arrival_airport_candidates_count"
    )

    return {
        "icao24": (flight.get("icao24") or "").lower() or None,
        "callsign": (flight.get("callsign") or "").strip() or None,
        "first_seen": _utc(first),
        "last_seen": _utc(last),
        "first_seen_ts": first,
        "last_seen_ts": last,
        "departure": departure,
        "arrival": arrival,
        "departure_lat": dep_lat,
        "departure_lon": dep_lon,
        "arrival_lat": arr_lat,
        "arrival_lon": arr_lon,
        "callsign_icao": callsign_icao,
        "departure_candidates": dep_candidates,
        "arrival_candidates": arr_candidates,
        "duration_s": (
            last - first
            if isinstance(first, int) and isinstance(last, int) and last >= first
            else None
        ),
        "source": "opensky",
        "provenance": PROVENANCE_HISTORICAL,
    }


def _pick(source: dict, *names):
    """First present, non-null value among ``names``."""
    for name in names:
        if name in source and source[name] is not None:
            return source[name]
    return None


# ─── Trajectories (spec §21, §22, §56) ──────────────────────────────────────

async def build_track(
    service,
    db: Session,
    icao24: str,
    time_: Optional[int] = None,
    include_local: bool = True,
) -> dict:
    """Assemble the full available trajectory for one aircraft.

    Combines, without inventing anything:
      * the OpenSky historical track for the flight at ``time_``,
      * AeroRF's own recorded positions, when a local session exists.

    The response states how many points came from each source and the mean
    temporal step, so the operator can judge the track's fidelity instead
    of assuming 1 Hz data.
    """
    code = str(icao24).strip().lower()
    if not _valid_icao24(code):
        raise FlightServiceError(
            f"Invalid ICAO24 {icao24!r}: expected 6 hex characters."
        )

    provenance: dict[str, int] = {PROVENANCE_HISTORICAL: 0, "aerorf": 0, "live": 0}
    points: list[dict] = []
    warnings: list[str] = []

    # ── OpenSky track ───────────────────────────────────────────────────
    track: dict[str, Any] = {}
    try:
        track = await service.get_track(code, time_=time_)
    except Exception as exc:
        warnings.append(f"Track de OpenSky no disponible: {exc}")
        track = {}

    for p in (track.get("points") or []):
        if p.get("latitude") is None or p.get("longitude") is None:
            continue
        points.append(
            {
                "timestamp": p.get("timestamp"),
                "latitude": p["latitude"],
                "longitude": p["longitude"],
                "altitude": p.get("altitude"),
                "heading": p.get("heading"),
                "on_ground": p.get("on_ground"),
                "provenance": (
                    PROVENANCE_LIVE if time_ == 0 else PROVENANCE_HISTORICAL
                ),
            }
        )
        provenance[
            PROVENANCE_LIVE if time_ == 0 else PROVENANCE_HISTORICAL
        ] += 1

    # ── AeroRF's own recordings ─────────────────────────────────────────
    local_points: list[dict] = []
    if include_local:
        local_points = _local_positions(db, code)
        for p in local_points:
            points.append({**p, "provenance": TRACK_SOURCE_AERORF})
            provenance[TRACK_SOURCE_AERORF] += 1

    # Merge by timestamp, dropping exact duplicates that a live sample and
    # a track waypoint may share. No interpolation, ever.
    points = _merge_points(points)

    payload: dict[str, Any] = {
        "icao24": code,
        "callsign": track.get("callsign"),
        "points": points,
        "point_count": len(points),
        "provenance_counts": provenance,
        "start_time": points[0]["timestamp"] if points else None,
        "end_time": points[-1]["timestamp"] if points else None,
        "source": _merge_source(provenance),
        "warnings": warnings,
        "requested_time": time_,
    }

    # Which flight did the returned points actually belong to?
    #
    # OpenSky's `/tracks/all` answers "the flight near this instant" when given
    # one, and the *most recent* flight when not. For an aircraft that flew
    # several times that week, a request with no instant therefore returns a
    # different flight from the one asked about, and the caller has no way to
    # tell: the points are real, the provenance is right, and the route is
    # simply the wrong one.
    #
    # So the response states the window it covers and whether the requested
    # instant falls inside it. A caller comparing routes can then refuse to
    # treat a mismatched route as the one in the report.
    if points:
        first_ts, last_ts = points[0]["timestamp"], points[-1]["timestamp"]
        payload["covered_window"] = {
            "start": first_ts,
            "end": last_ts,
            "duration_s": (last_ts - first_ts) if None not in (first_ts, last_ts) else None,
        }
        if time_ is not None and time_ != 0:
            if first_ts is not None and not (first_ts - 300 <= time_ <= last_ts + 300):
                warnings.append(
                    f"OpenSky devolvió el vuelo de "
                    f"{first_ts}–{last_ts}, no el del instante solicitado "
                    f"({time_}). Es el vuelo más reciente de esta aeronave, "
                    f"no el del reporte. Elija el vuelo en la lista."
                )
                payload["matches_request"] = False
            else:
                payload["matches_request"] = True
    else:
        payload["covered_window"] = None
        if time_ is not None and time_ != 0:
            payload["matches_request"] = None

    if points:
        summary = path_summary([[p["latitude"], p["longitude"]] for p in points])
        payload["length_m"] = summary["total_length_m"]
        payload["length_km"] = summary["total_length_km"]
        payload["length_nm"] = summary["total_length_nm"]

        times = [p["timestamp"] for p in points if p.get("timestamp") is not None]
        if len(times) >= 2:
            span = max(times) - min(times)
            steps = [b - a for a, b in zip(sorted(times), sorted(times)[1:])]
            mean = sum(steps) / len(steps)
            payload["span_s"] = span
            payload["mean_step_s"] = mean
            payload["resolution_note"] = (
                f"{len(points)} puntos en {_hms(span)} "
                f"(paso medio {_hms(mean)}). "
                "Los waypoints históricos de OpenSky no son un punto por segundo."
            )
    else:
        payload["resolution_note"] = (
            "Sin posiciones disponibles. Si el vuelo fue visto en directo por "
            "AeroRF, active «Grabar vuelo» para conservar la trayectoria propia."
        )

    # Persist for later replay and export.
    if points:
        try:
            _store_track(db, code, track.get("callsign"), points, payload)
        except Exception as exc:  # persistence failure must not break the read
            warnings.append(f"No se pudo guardar el track localmente: {exc}")

    return payload


def _merge_points(points: list[dict]) -> list[dict]:
    """Order by time and drop duplicates on (timestamp, lat, lon)."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for p in points:
        key = (p.get("timestamp"), p.get("latitude"), p.get("longitude"))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    # Points without a timestamp sort last, preserving input order.
    out.sort(key=lambda p: (p.get("timestamp") is None, p.get("timestamp") or 0))
    return out


def _merge_source(provenance: dict[str, int]) -> str:
    used = [k for k, v in provenance.items() if v > 0]
    if len(used) > 1:
        return TRACK_SOURCE_MERGED
    if used:
        return TRACK_SOURCE_OPENSKY if provenance[PROVENANCE_HISTORICAL] else used[0]
    return TRACK_SOURCE_OPENSKY


def _local_positions(db: Session, icao24: str, limit: int = 5000) -> list[dict]:
    rows = (
        db.query(AircraftPosition)
        .filter(AircraftPosition.icao24 == icao24)
        .order_by(AircraftPosition.received_at)
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        if r.latitude is None or r.longitude is None:
            continue
        out.append(
            {
                "timestamp": r.timestamp
                or int(r.received_at.replace(tzinfo=timezone.utc).timestamp()),
                "latitude": r.latitude,
                "longitude": r.longitude,
                "altitude": r.altitude,
                "heading": r.heading,
                "velocity": r.velocity,
                "on_ground": r.on_ground,
                "session_id": r.session_id,
            }
        )
    return out


def _store_track(
    db: Session,
    icao24: str,
    callsign: Optional[str],
    points: list[dict],
    payload: dict,
    session_id: Optional[int] = None,
    flight_id: Optional[int] = None,
) -> AircraftTrack:
    """Persist a trajectory as an ``aircraft_tracks`` row.

    ``session_id`` links a track produced by a recording session back to
    that session, which is what lets the replay view find it.
    """
    from app.services.geojson_service import line_geometry

    track = AircraftTrack(
        icao24=icao24,
        callsign=callsign,
        session_id=session_id,
        flight_id=flight_id,
        source=payload.get("source", TRACK_SOURCE_OPENSKY),
        started_at=_utc(payload.get("start_time")),
        ended_at=_utc(payload.get("end_time")),
        point_count=len(points),
        observed_seconds=payload.get("span_s"),
        geometry=line_geometry([[p["latitude"], p["longitude"]] for p in points]),
        meta={
            "provenance_counts": payload.get("provenance_counts"),
            "mean_step_s": payload.get("mean_step_s"),
            "resolution_note": payload.get("resolution_note"),
        },
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    return track


def _hms(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {(seconds % 3600) // 60} min"


# ─── Live state (spec §23) ───────────────────────────────────────────────────

async def get_live(
    service,
    icao24: Optional[list[str]] = None,
) -> dict:
    """Current state vectors for the tracked aircraft, or for a box."""
    data = await service.get_states(icao24=icao24 or None)
    states = data.get("states") or []
    return {
        "time": data.get("time"),
        "time_utc": _utc(data.get("time")),
        "count": len(states),
        "states": states,
        "from_cache": data.get("from_cache"),
        "provenance": PROVENANCE_LIVE,
        "source": "opensky",
    }


# ─── Recording sessions (spec §24, §26) ─────────────────────────────────────

def create_session(
    db: Session,
    icao24: str,
    callsign: Optional[str] = None,
    interval_s: float = 10.0,
    description: Optional[str] = None,
    user: Optional[str] = None,
) -> FlightSession:
    """Open a recording session (spec §24)."""
    code = str(icao24).strip().lower()
    if not _valid_icao24(code):
        raise FlightServiceError(
            f"Invalid ICAO24 {icao24!r}: expected 6 hex characters."
        )

    existing = (
        db.query(FlightSession)
        .filter(FlightSession.icao24 == code, FlightSession.status == SESSION_RECORDING)
        .first()
    )
    if existing:
        raise FlightServiceError(
            f"A recording session for {code} is already running (id={existing.id})."
        )

    session = FlightSession(
        icao24=code,
        callsign=callsign,
        status=SESSION_RECORDING,
        source=TRACK_SOURCE_OPENSKY,
        interval_s=interval_s,
        description=description,
        user=user,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    flight_log.info(
        "session.started", "recording session started",
        session_id=session.id, icao24=code, callsign=callsign, user=user,
    )
    return session


def record_sample(
    db: Session,
    session_id: int,
    state: dict,
) -> Optional[AircraftPosition]:
    """Append one observed position to a session.

    A state vector with no position is still recorded (it proves the
    aircraft was tracked) but carries ``latitude = None``, which the UI
    shows as "dato no disponible" rather than skipping silently.
    """
    session = db.query(FlightSession).filter(FlightSession.id == session_id).first()
    if session is None:
        raise FlightServiceError(f"Session {session_id} not found")
    if session.status != SESSION_RECORDING:
        return None

    position = AircraftPosition(
        session_id=session.id,
        timestamp=state.get("time_position"),
        latitude=state.get("latitude"),
        longitude=state.get("longitude"),
        altitude=state.get("altitude"),
        heading=state.get("heading"),
        velocity=state.get("velocity"),
        vertical_rate=state.get("vertical_rate"),
        on_ground=state.get("on_ground"),
        callsign=state.get("callsign") or session.callsign,
        icao24=state.get("icao24") or session.icao24,
        source=TRACK_SOURCE_OPENSKY,
    )
    db.add(position)
    session.sample_count = (session.sample_count or 0) + 1
    if state.get("callsign"):
        session.callsign = state["callsign"]
    db.commit()
    db.refresh(position)
    return position


def stop_session(db: Session, session_id: int, notes: Optional[str] = None) -> FlightSession:
    """Close a session and materialise its track."""
    session = db.query(FlightSession).filter(FlightSession.id == session_id).first()
    if session is None:
        raise FlightServiceError(f"Session {session_id} not found")
    if session.status != SESSION_RECORDING:
        raise FlightServiceError(
            f"Session {session_id} is already {session.status}."
        )

    session.status = SESSION_STOPPED
    session.ended_at = utcnow()
    if notes:
        session.notes = notes
    db.commit()

    positions = (
        db.query(AircraftPosition)
        .filter(AircraftPosition.session_id == session_id)
        .order_by(AircraftPosition.received_at)
        .all()
    )
    usable = [p for p in positions if p.latitude is not None]
    if usable:
        points = [
            {
                "timestamp": p.timestamp
                or int(p.received_at.replace(tzinfo=timezone.utc).timestamp()),
                "latitude": p.latitude,
                "longitude": p.longitude,
                "altitude": p.altitude,
                "heading": p.heading,
                "on_ground": p.on_ground,
            }
            for p in usable
        ]
        times = [p["timestamp"] for p in points]
        try:
            _store_track(
                db, session.icao24, session.callsign, points,
                {
                    "source": TRACK_SOURCE_AERORF,
                    "start_time": min(times), "end_time": max(times),
                    "span_s": max(times) - min(times),
                    "provenance_counts": {"aerorf": len(points)},
                },
                session_id=session.id,
            )
        except Exception as exc:
            # Track materialisation must not lose the session itself.
            flight_log.error(
                "session.track_failed", "could not build session track",
                session_id=session_id, error=str(exc),
            )

    db.refresh(session)
    flight_log.info(
        "session.stopped", "recording session stopped",
        session_id=session_id, icao24=session.icao24,
        samples=session.sample_count, with_positions=len(usable),
    )
    return session


def get_session_detail(db: Session, session_id: int) -> dict:
    """A session with its positions, ready for the replay timeline."""
    session = db.query(FlightSession).filter(FlightSession.id == session_id).first()
    if session is None:
        raise FlightServiceError(f"Session {session_id} not found")

    positions = (
        db.query(AircraftPosition)
        .filter(AircraftPosition.session_id == session_id)
        .order_by(AircraftPosition.received_at)
        .all()
    )
    # Tracks materialised when the session was stopped.
    from app.models.flight import AircraftTrack

    tracks = (
        db.query(AircraftTrack)
        .filter(AircraftTrack.session_id == session_id)
        .order_by(AircraftTrack.id)
        .all()
    )

    return {
        "session": {
            "id": session.id,
            "icao24": session.icao24,
            "callsign": session.callsign,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "status": session.status,
            "source": session.source,
            "interval_s": session.interval_s,
            "sample_count": session.sample_count,
            "description": session.description,
            "user": session.user,
            "notes": session.notes,
            "error": session.error,
        },
        "tracks": [
            {
                "id": t.id,
                "source": t.source,
                "point_count": t.point_count,
                "started_at": t.started_at,
                "ended_at": t.ended_at,
                "observed_seconds": t.observed_seconds,
                "geometry": t.geometry,
                "meta": t.meta,
            }
            for t in tracks
        ],
        "positions": [
            {
                "id": p.id,
                "timestamp": p.timestamp,
                "received_at": p.received_at,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "altitude": p.altitude,
                "heading": p.heading,
                "velocity": p.velocity,
                "on_ground": p.on_ground,
                "callsign": p.callsign,
                "icao24": p.icao24,
                "provenance": TRACK_SOURCE_AERORF,
            }
            for p in positions
        ],
    }


# ─── Watchlist (spec §25, §26) ───────────────────────────────────────────────

def list_selections(db: Session) -> list[dict]:
    rows = (
        db.query(FlightSelection).order_by(FlightSelection.slot).all()
    )
    return [
        {
            "icao24": r.icao24,
            "callsign": r.callsign,
            "slot": r.slot,
            "color": r.color or SLOT_COLORS[r.slot % len(SLOT_COLORS)],
            "show_track": r.show_track,
            "show_marker": r.show_marker,
            "selected": r.selected,
            "last_seen": r.last_seen,
            "last_position": r.last_position,
            "added_at": r.added_at,
        }
        for r in rows
    ]


def add_selection(
    db: Session,
    icao24: str,
    callsign: Optional[str] = None,
    user: Optional[str] = None,
) -> FlightSelection:
    """Add an aircraft to the watchlist, enforcing the 5-aircraft cap."""
    code = str(icao24).strip().lower()
    if not _valid_icao24(code):
        raise FlightServiceError(
            f"Invalid ICAO24 {icao24!r}: expected 6 hex characters."
        )

    if db.query(FlightSelection).filter(FlightSelection.icao24 == code).first():
        raise FlightServiceError(f"Aircraft {code} is already being tracked.")

    taken = {r.slot for r in db.query(FlightSelection).all()}
    free = [s for s in range(MAX_TRACKED) if s not in taken]
    if not free:
        raise FlightServiceError(
            f"El límite es {MAX_TRACKED} aeronaves simultáneas. "
            f"Quitar una del seguimiento para agregar otra."
        )

    slot = free[0]
    row = FlightSelection(
        icao24=code,
        callsign=callsign,
        slot=slot,
        color=SLOT_COLORS[slot],
        user=user,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    flight_log.info(
        "selection.added", "aircraft tracked",
        icao24=code, callsign=callsign, slot=slot, user=user,
    )
    return row


def remove_selection(db: Session, icao24: str) -> None:
    code = str(icao24).strip().lower()
    row = db.query(FlightSelection).filter(FlightSelection.icao24 == code).first()
    if row is None:
        return
    db.delete(row)
    db.commit()
    flight_log.info("selection.removed", "aircraft untracked", icao24=code)


def update_selection(db: Session, icao24: str, patch: dict) -> FlightSelection:
    code = str(icao24).strip().lower()
    row = db.query(FlightSelection).filter(FlightSelection.icao24 == code).first()
    if row is None:
        raise FlightServiceError(f"Aircraft {code} is not being tracked.")
    allowed = {"callsign", "show_track", "show_marker", "selected", "color",
               "last_seen", "last_position"}
    for field, value in patch.items():
        if field in allowed:
            setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


def tracked_icao24s(db: Session) -> list[str]:
    return [r.icao24 for r in db.query(FlightSelection).order_by(FlightSelection.slot).all()]


# ─── Correlation (spec §35) ──────────────────────────────────────────────────

def correlate_event(
    db: Session,
    event_object_id: int,
    radii_nm: Iterable[float] = (5, 10, 20, 50),
    live_states: Optional[list[dict]] = None,
) -> dict:
    """Aircraft near an RF event, by distance band.

    This reports **spatial and temporal proximity only**. It never
    asserts that an aircraft caused an event: causation cannot be
    established from ADS-B position data plus an RF measurement, and the
    response says so explicitly.
    """
    obj = db.query(MapObject).filter(MapObject.id == event_object_id).first()
    if obj is None or obj.latitude is None or obj.longitude is None:
        raise FlightServiceError(
            f"Object {event_object_id} has no position, so it cannot be correlated."
        )

    bands: list[dict] = []
    for radius_nm in sorted(radii_nm):
        radius_m = to_metres(radius_nm, "nm")
        matches = []
        for state in live_states or []:
            lat, lon = state.get("latitude"), state.get("longitude")
            if lat is None or lon is None:
                continue
            distance = haversine_m(obj.latitude, obj.longitude, lat, lon)
            if distance <= radius_m:
                matches.append(
                    {
                        "icao24": state.get("icao24"),
                        "callsign": state.get("callsign"),
                        "distance_m": distance,
                        "distance_km": distance / 1000.0,
                        "distance_nm": distance / 1852.0,
                        "altitude": state.get("altitude"),
                        "velocity": state.get("velocity"),
                        "heading": state.get("heading"),
                        "timestamp": state.get("time_position"),
                        "timestamp_utc": _utc(state.get("time_position")),
                    }
                )
        matches.sort(key=lambda m: m["distance_m"])
        bands.append({"radius_nm": radius_nm, "count": len(matches), "aircraft": matches})

    nearest = None
    for band in bands:
        if band["count"]:
            nearest = band["aircraft"][0]
            break

    return {
        "object_id": event_object_id,
        "object_type": obj.type,
        "center": {"latitude": obj.latitude, "longitude": obj.longitude},
        "bands": bands,
        "nearest": nearest,
        "disclaimer": (
            "Correlación espacial y temporal únicamente. La cercanía entre una "
            "aeronave y un evento RF NO implica causalidad: ADS-B no registra "
            "emisiones y la posición del avión no identifica la fuente de un evento."
        ),
        "provenance": "calculated",
    }
