"""
api/routes/flights.py
─────────────────────
Flight API (spec §20–§27, §47).

    GET  /api/v1/flights/search                 search by callsign / ICAO24 (spec §20)
    GET  /api/v1/flights/{icao24}              flight detail
    GET  /api/v1/flights/{icao24}/track        full available trajectory (spec §21)
    GET  /api/v1/flights/{icao24}/live-track   ongoing flight track (spec §23)
    GET  /api/v1/flights/live                  current state vectors (spec §23)
    GET  /api/v1/flights/all                   flights in a time interval
    GET  /api/v1/flights/arrival               arrivals at an airport
    GET  /api/v1/flights/departure             departures from an airport
    GET  /api/v1/flights/aircraft              flights of one aircraft

    GET    /api/v1/flights/sessions            list recording sessions
    POST   /api/v1/flights/sessions            create (spec §24)
    POST   /api/v1/flights/sessions/{id}/start start
    POST   /api/v1/flights/sessions/{id}/stop  stop
    GET    /api/v1/flights/sessions/{id}       detail + positions
    DELETE /api/v1/flights/sessions/{id}       delete

    GET    /api/v1/flights/tracked             the ≤5 watchlist (spec §25)
    POST   /api/v1/flights/tracked             add to watchlist
    DELETE /api/v1/flights/tracked/{icao24}    remove
    PATCH  /api/v1/flights/tracked/{icao24}    show/hide, select
    GET    /api/v1/flights/correlate/{id}      RF event ↔ aircraft (spec §35)

**This module never fabricates a flight.** There is no sample/demo source.
If OpenSky has no data, the response says so.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.database import get_db
from app.models.flight import FlightSession
from app.models.schemas_gis import FlightSessionCreate
from app.services import flight_service as fsvc
from app.services.cache import RateLimitedError
from app.services.opensky_service import (
    OpenSkyError,
    OpenSkyNotConfigured,
    get_opensky_service,
)

router = APIRouter(prefix="/flights", tags=["Flights"])


# ─── Error translation ───────────────────────────────────────────────────────

def _handle(exc: Exception) -> HTTPException:
    """Map service errors onto honest HTTP codes."""
    if isinstance(exc, RateLimitedError):
        return HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(int(exc.retry_after_s))},
        )
    if isinstance(exc, OpenSkyNotConfigured):
        # 503: the app works, the upstream integration is not configured.
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, OpenSkyError):
        code = 502 if exc.status is None or exc.status >= 500 else exc.status
        return HTTPException(status_code=code, detail=str(exc))
    if isinstance(exc, fsvc.FlightServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))  # pragma: no cover


async def _service_or_503():
    """Return the service, or explain that credentials are required.

    OpenSky serves ``/states/all`` anonymously, so live traffic works
    without an account. Historical flights do not: those endpoints answer
    403 without OAuth2, and this gate saves the caller a round trip.
    """
    service = get_opensky_service()
    if service.configured:
        return service
    if service.can_query_states:
        return service
    raise HTTPException(
        status_code=503,
        detail=(
            "OpenSky no está configurado y el acceso anónimo está "
            "deshabilitado. Defina OPENSKY_CLIENT_ID y OPENSKY_CLIENT_SECRET "
            "en el .env del backend, o active OPENSKY_ALLOW_ANONYMOUS=true."
        ),
    )


def _credentials_required() -> HTTPException:
    """503 for the endpoints OpenSky refuses to anonymous callers."""
    return HTTPException(
        status_code=503,
        detail=(
            "Este endpoint requiere credenciales OAuth2 de OpenSky. "
            "El tráfico en vivo (/flights/live) funciona sin credenciales; "
            "el historial de vuelos no. Defina OPENSKY_CLIENT_ID y "
            "OPENSKY_CLIENT_SECRET en el .env del backend."
        ),
    )


# ─── Search (spec §20) ───────────────────────────────────────────────────────

@router.get("/search")
async def search(
    callsign: Optional[str] = Query(None, max_length=16),
    icao24: Optional[str] = Query(None, max_length=8),
    date: Optional[str] = Query(None, description="YYYY-MM-DD (UTC)"),
    time_hint: Optional[str] = Query(None, description="HH:MM (UTC)"),
    window_hours: int = Query(6, ge=1, le=48),
    db: Session = Depends(get_db),
):
    """Search a flight by callsign, ICAO24, date and approximate time.

    A callsign is resolved against current state vectors to obtain the
    ICAO24, then the aircraft's flight history is queried. The response
    states which route was used under ``resolved_via``.
    """
    if not callsign and not icao24:
        raise HTTPException(
            400, "Provide at least one of `callsign` or `icao24`."
        )
    service = get_opensky_service()
    if not service.configured:
        raise _credentials_required()
    try:
        return await fsvc.search_flight(
            service, callsign=callsign, icao24=icao24,
            date=date, time_hint=time_hint, window_hours=window_hours,
        )
    except Exception as exc:
        raise _handle(exc)


# ─── Live states (spec §23) ──────────────────────────────────────────────────

@router.get("/live")
async def live(
    icao24: Optional[str] = Query(
        None, description="Comma-separated ICAO24 codes (max 5)"
    ),
    bbox: Optional[str] = Query(
        None, description="lat_min,lon_min,lat_max,lon_max"
    ),
):
    """Current state vectors, for tracked aircraft or a bounding box."""
    service = await _service_or_503()
    codes = None
    if icao24:
        codes = [c.strip().lower() for c in icao24.split(",") if c.strip()]
        if len(codes) > get_settings().max_tracked_aircraft:
            raise HTTPException(
                400,
                f"At most {get_settings().max_tracked_aircraft} aircraft "
                f"per query.",
            )

    try:
        if bbox:
            parts = [float(p) for p in bbox.split(",")]
            if len(parts) != 4:
                raise HTTPException(
                    400, "bbox must be 'lat_min,lon_min,lat_max,lon_max'"
                )
            return await service.get_states_in_box(*parts)
        return await service.get_states(icao24=codes)
    except HTTPException:
        raise
    except Exception as exc:
        raise _handle(exc)


# ─── Flight lists (spec §19) ─────────────────────────────────────────────────

@router.get("/all")
async def flights_all(
    begin: Optional[int] = None,
    end: Optional[int] = None,
    hours: int = Query(2, ge=1, le=2),
):
    """Flights in a time interval. OpenSky caps this window at 2 hours."""
    service = get_opensky_service()
    if not service.configured:
        raise _credentials_required()
    begin, end = _resolve(begin, end, hours)
    try:
        return {"count": len(await service.get_flights_all(begin, end)),
                "flights": await service.get_flights_all(begin, end),
                "begin": begin, "end": end}
    except Exception as exc:
        raise _handle(exc)


@router.get("/aircraft")
async def flights_by_aircraft(
    icao24: str = Query(..., min_length=6, max_length=8),
    begin: Optional[int] = None,
    end: Optional[int] = None,
    hours: int = Query(24, ge=1, le=48),
):
    """Flights of one aircraft. OpenSky caps this window at 2 days."""
    service = get_opensky_service()
    if not service.configured:
        raise _credentials_required()
    begin, end = _resolve(begin, end, hours)
    try:
        rows = await service.get_flights_by_aircraft(icao24, begin, end)
        return {
            "count": len(rows), "flights": rows,
            "icao24": icao24.lower(), "begin": begin, "end": end,
        }
    except Exception as exc:
        raise _handle(exc)


@router.get("/arrival")
async def arrivals(
    airport: str = Query(..., min_length=3, max_length=4),
    begin: Optional[int] = None,
    end: Optional[int] = None,
    hours: int = Query(24, ge=1, le=48),
):
    """Arrivals at an airport (ICAO code)."""
    service = get_opensky_service()
    if not service.configured:
        raise _credentials_required()
    begin, end = _resolve(begin, end, hours)
    try:
        rows = await service.get_arrivals(airport.upper(), begin, end)
        return {
            "count": len(rows), "flights": rows,
            "airport": airport.upper(), "begin": begin, "end": end,
        }
    except Exception as exc:
        raise _handle(exc)


@router.get("/departure")
async def departures(
    airport: str = Query(..., min_length=3, max_length=4),
    begin: Optional[int] = None,
    end: Optional[int] = None,
    hours: int = Query(24, ge=1, le=48),
):
    """Departures from an airport (ICAO code)."""
    service = get_opensky_service()
    if not service.configured:
        raise _credentials_required()
    begin, end = _resolve(begin, end, hours)
    try:
        rows = await service.get_departures(airport.upper(), begin, end)
        return {
            "count": len(rows), "flights": rows,
            "airport": airport.upper(), "begin": begin, "end": end,
        }
    except Exception as exc:
        raise _handle(exc)


# ─── Recording sessions (spec §24, §26) ─────────────────────────────────────

@router.get("/sessions")
def list_sessions(
    icao24: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List recording sessions."""
    q = db.query(FlightSession)
    if icao24:
        q = q.filter(FlightSession.icao24 == icao24.lower())
    if status_filter:
        q = q.filter(FlightSession.status == status_filter)
    rows = q.order_by(FlightSession.started_at.desc()).limit(limit).all()
    return {
        "count": len(rows),
        "sessions": [
            {
                "id": s.id,
                "icao24": s.icao24,
                "callsign": s.callsign,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "status": s.status,
                "source": s.source,
                "interval_s": s.interval_s,
                "sample_count": s.sample_count,
                "description": s.description,
                "user": s.user,
            }
            for s in rows
        ],
    }


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(payload: FlightSessionCreate, db: Session = Depends(get_db)):
    """Create a recording session (spec §24)."""
    try:
        return fsvc.create_session(
            db, payload.icao24, payload.callsign,
            interval_s=payload.interval_s or 10.0,
            description=payload.description, user=payload.user,
        )
    except Exception as exc:
        raise _handle(exc)


@router.post("/sessions/{session_id}/start")
def start_session(session_id: int, db: Session = Depends(get_db)):
    """Start sampling into an existing session.

    A session created through ``POST /sessions`` is already recording, so
    this endpoint exists to (re)start a stopped one and is idempotent.
    """
    session = db.query(FlightSession).filter(FlightSession.id == session_id).first()
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    if session.status == fsvc.SESSION_RECORDING:
        return {"id": session.id, "status": session.status, "already_recording": True}
    session.status = fsvc.SESSION_RECORDING
    session.ended_at = None
    db.commit()
    db.refresh(session)
    return {"id": session.id, "status": session.status, "already_recording": False}


@router.post("/sessions/{session_id}/stop")
def stop_session(
    session_id: int,
    notes: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
):
    """Stop recording and build the session's track (spec §24)."""
    try:
        return fsvc.stop_session(db, session_id, notes=notes)
    except Exception as exc:
        raise _handle(exc)


@router.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    """A session with all its recorded positions, for replay (spec §27)."""
    try:
        return fsvc.get_session_detail(db, session_id)
    except Exception as exc:
        raise _handle(exc)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)):
    """Delete a session and its positions."""
    session = db.query(FlightSession).filter(FlightSession.id == session_id).first()
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    if session.status == fsvc.SESSION_RECORDING:
        raise HTTPException(
            400, "Stop the session before deleting it."
        )
    db.delete(session)
    db.commit()
    return {"deleted": session_id}


# ─── Watchlist (spec §25, §26) ───────────────────────────────────────────────

@router.get("/tracked")
def get_tracked(db: Session = Depends(get_db)):
    """The aircraft being followed, up to five."""
    rows = fsvc.list_selections(db)
    return {
        "count": len(rows),
        "max": fsvc.MAX_TRACKED,
        "slots": rows,
    }


@router.post("/tracked", status_code=status.HTTP_201_CREATED)
def track_aircraft(
    icao24: str = Query(..., min_length=6, max_length=8),
    callsign: Optional[str] = Query(None, max_length=16),
    user: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Add an aircraft to the watchlist. Max five (spec §25)."""
    try:
        row = fsvc.add_selection(db, icao24, callsign, user)
    except Exception as exc:
        raise _handle(exc)
    return {
        "icao24": row.icao24, "callsign": row.callsign, "slot": row.slot,
        "color": row.color, "show_track": row.show_track,
        "show_marker": row.show_marker, "selected": row.selected,
    }


@router.delete("/tracked/{icao24}")
def untrack_aircraft(icao24: str, db: Session = Depends(get_db)):
    """Stop following an aircraft."""
    fsvc.remove_selection(db, icao24)
    return {"removed": icao24.lower()}


@router.patch("/tracked/{icao24}")
def patch_aircraft(
    icao24: str, patch: dict = Body(...), db: Session = Depends(get_db)
):
    """Show/hide the marker or track, or mark as selected (spec §26)."""
    try:
        row = fsvc.update_selection(db, icao24, patch)
    except Exception as exc:
        raise _handle(exc)
    return {
        "icao24": row.icao24, "callsign": row.callsign, "slot": row.slot,
        "color": row.color, "show_track": row.show_track,
        "show_marker": row.show_marker, "selected": row.selected,
    }


# ─── Correlation (spec §35) ──────────────────────────────────────────────────

@router.get("/correlate/{object_id}")
async def correlate(
    object_id: int,
    radii_nm: Optional[str] = Query(None, description="e.g. 5,10,20,50"),
    db: Session = Depends(get_db),
):
    """Aircraft near an RF event, by distance band.

    Reports spatial and temporal proximity only, and says explicitly
    that proximity does not imply causation.
    """
    radii = (
        [float(r) for r in radii_nm.split(",") if r.strip()]
        if radii_nm
        else (5, 10, 20, 50)
    )

    live_states: list[dict] = []
    service = get_opensky_service()
    if service.configured:
        try:
            live_states = (await service.get_states()).get("states") or []
        except Exception:
            # Correlation still works with whatever the caller supplies;
            # an empty aircraft list is reported, not hidden.
            live_states = []

    try:
        return fsvc.correlate_event(db, object_id, radii, live_states)
    except Exception as exc:
        raise _handle(exc)


# ─── Trajectory (spec §21, §22) ─────────────────────────────────────────────
# NOTE: the three routes below are declared *after* the literal paths on
# purpose. FastAPI matches in registration order, so a `/{icao24}` route
# registered earlier would swallow `/flights/sessions` and
# `/flights/tracked` with icao24="sessions". The parameterised routes must
# stay last in this router.


@router.get("/{icao24}/track")
async def get_track(
    icao24: str,
    time: Optional[int] = Query(
        None, description="Unix time inside the flight; omit for the latest"
    ),
    include_local: bool = Query(
        True, description="Merge AeroRF's own recorded positions"
    ),
    db: Session = Depends(get_db),
):
    """The complete available trajectory for an aircraft.

    Combines OpenSky's historical track with AeroRF's own recordings and
    reports the provenance of every point. Waypoints are not
    second-by-second; the response says how many there are and the mean
    step, and it never interpolates missing history.
    """
    service = get_opensky_service()
    if not service.configured:
        raise _credentials_required()
    try:
        return await fsvc.build_track(
            service, db, icao24, time_=time, include_local=include_local
        )
    except Exception as exc:
        raise _handle(exc)


@router.get("/{icao24}/live-track")
async def get_live_track(icao24: str, db: Session = Depends(get_db)):
    """Track of the flight currently in progress, if any (spec §23).

    Goes through ``fsvc.build_track`` like ``/track`` does, with ``time_=0``
    to ask OpenSky for the flight in progress. Calling
    ``service.get_live_track`` directly returned a different shape: a
    ``provenance`` string instead of per-point provenance, and no
    ``provenance_counts``, so the map legend could never be filled and the
    two endpoints disagreed about the same aircraft.
    """
    service = get_opensky_service()
    if not service.configured:
        raise _credentials_required()
    try:
        return await fsvc.build_track(service, db, icao24, time_=0, include_local=True)
    except Exception as exc:
        raise _handle(exc)


@router.get("/{icao24}")
async def get_flight(
    icao24: str,
    begin: Optional[int] = None,
    end: Optional[int] = None,
    hours: int = Query(24, ge=1, le=48),
    db: Session = Depends(get_db),
):
    """Flight detail: historical flights plus the current state, if any."""
    service = get_opensky_service()
    if not service.configured:
        raise _credentials_required()
    begin, end = _resolve(begin, end, hours)
    try:
        historical = await service.get_flights_by_aircraft(icao24, begin, end)
        state = None
        try:
            live = await service.get_states(icao24=[icao24])
            state = (live.get("states") or [None])[0]
        except Exception:
            state = None  # live data is best-effort
        return {
            "icao24": icao24.lower(),
            "flights": [fsvc._normalise_flight(f) for f in historical],
            "flight_count": len(historical),
            "current_state": state,
            "begin": begin,
            "end": end,
        }
    except Exception as exc:
        raise _handle(exc)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _resolve(begin: Optional[int], end: Optional[int], hours: int) -> tuple[int, int]:
    """Build a time window, defaulting to the last ``hours`` hours."""
    now = int(datetime.now(timezone.utc).timestamp())
    if begin is None and end is None:
        return now - hours * 3600, now
    begin = begin if begin is not None else now - hours * 3600
    end = end if end is not None else begin + hours * 3600
    if end <= begin:
        raise HTTPException(400, "`end` must be greater than `begin`")
    if end > now + 300:
        raise HTTPException(
            400, "OpenSky does not accept future timestamps."
        )
    return int(begin), int(end)
