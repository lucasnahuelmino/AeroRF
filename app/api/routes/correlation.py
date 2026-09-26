"""
api/routes/correlation.py
────────────────────────
Spatial correlation between RF objects and aircraft (spec §35).

    POST /api/v1/correlation/rf-aircraft   aircraft near an RF object
    GET  /api/v1/correlation/aircraft/{icao24}  RF objects near an aircraft
    GET  /api/v1/correlation/object/{id}        full correlation report

A note that governs every response here: the system reports **spatial and
temporal proximity only**. ADS-B carries no emission data, and the
geographic distance between an aircraft and a recorded RF event says
nothing about which one caused the other. Every response carries that
disclaimer in its payload so it travels with the data into any export.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.geo import haversine_m, initial_bearing
from app.core.units import normalise_unit, to_metres
from app.database.database import get_db
from app.models.constants import (
    CORRELATION_RADII_NM,
    TYPE_ANTENNA,
    TYPE_RF_EVENT,
    TYPE_RF_SOURCE,
    TYPE_REFERENCE,
)
from app.models.map_object import MapObject
from app.services import map_service as svc
from app.services.opensky_service import (
    OpenSkyError,
    OpenSkyNotConfigured,
    get_opensky_service,
)

router = APIRouter(prefix="/correlation", tags=["Correlation"])

DISCLAIMER = (
    "Correlación espacial y temporal únicamente. La cercanía entre una "
    "aeronave y un evento RF NO implica causalidad. ADS-B no registra "
    "emisiones electromagnéticas, la posición del avión no identifica la "
    "fuente de un evento, y un evento de intermodulación puede originarse a "
    "kilómetros de la aeronave observada."
)

RF_TYPES = (TYPE_RF_EVENT, TYPE_RF_SOURCE, TYPE_ANTENNA, TYPE_REFERENCE)


@router.post("/rf-aircraft")
async def rf_aircraft(
    body: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Aircraft near an RF object, banded by distance (spec §35).

    Body::

        {"object_id": 42, "radii_nm": [5, 10, 20, 50],
         "states": [ ...optional live state vectors... ]}

    Supplying ``states`` lets the caller correlate against a snapshot it
    already holds, at no credit cost.
    """
    object_id = body.get("object_id")
    if object_id is None:
        raise HTTPException(400, "`object_id` is required")

    obj = svc.get_object(db, int(object_id))
    if obj is None:
        raise HTTPException(404, f"Object {object_id} not found")
    if obj.latitude is None or obj.longitude is None:
        raise HTTPException(
            400, f"Object {object_id} has no position, so it cannot be correlated."
        )

    radii = _radii(body.get("radii_nm"))
    states = body.get("states")

    if states is None:
        service = get_opensky_service()
        if not service.configured:
            raise HTTPException(
                503,
                "OpenSky no está configurado. Envíe `states` en el cuerpo "
                "para correlizar contra datos ya obtenidos.",
            )
        try:
            states = (await service.get_states()).get("states") or []
        except (OpenSkyNotConfigured, OpenSkyError) as exc:
            raise HTTPException(502, str(exc))

    return _correlate(obj, states, radii)


@router.get("/object/{object_id}")
async def correlate_object(
    object_id: int,
    radii_nm: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Full correlation report for one object, using live states."""
    obj = svc.get_object(db, object_id)
    if obj is None:
        raise HTTPException(404, f"Object {object_id} not found")
    if obj.latitude is None or obj.longitude is None:
        raise HTTPException(
            400, f"Object {object_id} has no position."
        )

    service = get_opensky_service()
    if not service.configured:
        raise HTTPException(
            503, "OpenSky no está configurado; no hay datos de aeronaves."
        )
    try:
        states = (await service.get_states()).get("states") or []
    except (OpenSkyNotConfigured, OpenSkyError) as exc:
        raise HTTPException(502, str(exc))

    return _correlate(obj, states, _radii(radii_nm))


@router.get("/aircraft/{icao24}")
async def correlate_aircraft(
    icao24: str,
    radii_nm: Optional[str] = None,
    type: Optional[str] = Query(
        None, description="Comma-separated object types; default RF types"
    ),
    db: Session = Depends(get_db),
):
    """RF objects near a tracked aircraft (spec §30, §35).

    Answers the workflow in the brief: select the aircraft, see how far it
    is from each source, event, antenna and reference.
    """
    radius_m = to_metres(
        _radii(radii_nm)[-1] if radii_nm else 50, "nm"
    )
    types = (
        tuple(t.strip() for t in type.split(",") if t.strip())
        if type
        else RF_TYPES
    )

    # Locate the aircraft: prefer the watchlist's last known position, then
    # a live state vector.
    position = await _aircraft_position(icao24, db)

    if position is None:
        raise HTTPException(
            404,
            f"No hay posición conocida para {icao24}. Agregue la aeronave al "
            f"seguimiento o espere una actualización en vivo.",
        )

    lat, lon, origin = position
    rows = svc.distances_from(
        db, lat, lon, types=list(types), radius_nm=radius_m / 1852.0, limit=500
    )

    return {
        "icao24": icao24.lower(),
        "position": {"latitude": lat, "longitude": lon, "source": origin},
        "radius_nm": radius_m / 1852.0,
        "count": len(rows),
        "objects": [
            {
                **row,
                "bearing": round(
                    initial_bearing(lat, lon, row["latitude"], row["longitude"]), 1
                )
                if row["latitude"] is not None
                else None,
            }
            for row in rows
        ],
        "disclaimer": DISCLAIMER,
        "provenance": "calculated",
    }


# ─── Internals ───────────────────────────────────────────────────────────────

def _radii(raw: Any) -> list[float]:
    if raw is None:
        return list(CORRELATION_RADII_NM)
    if isinstance(raw, (int, float)):
        return [float(raw)]
    if isinstance(raw, str):
        parts = [p for p in raw.split(",") if p.strip()]
    else:
        parts = list(raw)
    try:
        values = sorted({float(p) for p in parts})
    except (TypeError, ValueError):
        raise HTTPException(400, "radii_nm must be a list of numbers")
    return values or list(CORRELATION_RADII_NM)


def _correlate(obj: MapObject, states: list[dict], radii: list[float]) -> dict:
    """Shared banded-distance computation."""
    bands: list[dict] = []
    for radius_nm in radii:
        radius_m = to_metres(radius_nm, "nm")
        matches: list[dict] = []
        for state in states:
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
                        "bearing_from_object": round(
                            initial_bearing(
                                obj.latitude, obj.longitude, lat, lon
                            ),
                            1,
                        ),
                        "altitude": state.get("altitude"),
                        "velocity": state.get("velocity"),
                        "heading": state.get("heading"),
                        "on_ground": state.get("on_ground"),
                        "timestamp": state.get("time_position"),
                        "aircraft_updated_at": state.get("last_contact"),
                    }
                )
        matches.sort(key=lambda m: m["distance_m"])
        bands.append(
            {"radius_nm": radius_nm, "count": len(matches), "aircraft": matches}
        )

    nearest = next((b["aircraft"][0] for b in bands if b["count"]), None)

    return {
        "object_id": obj.id,
        "object": {
            "id": obj.id,
            "type": obj.type,
            "name": obj.name,
            "status": obj.status,
            "expediente_id": obj.expediente_id,
            "latitude": obj.latitude,
            "longitude": obj.longitude,
        },
        "bands": bands,
        "nearest": nearest,
        "aircraft_considered": len(states),
        "disclaimer": DISCLAIMER,
        "provenance": "calculated",
    }


async def _aircraft_position(
    icao24: str, db: Session
) -> Optional[tuple[float, float, str]]:
    """Best known position for an aircraft, with its origin labelled."""
    code = str(icao24).strip().lower()

    # 1. AeroRF's own most recent recording — our own evidence.
    from app.models.flight import AircraftPosition, FlightSelection

    last_local = (
        db.query(AircraftPosition)
        .filter(
            AircraftPosition.icao24 == code,
            AircraftPosition.latitude.isnot(None),
        )
        .order_by(AircraftPosition.received_at.desc())
        .first()
    )
    if last_local is not None:
        return last_local.latitude, last_local.longitude, "aerorf_recording"

    # 2. The watchlist's cached position.
    selection = (
        db.query(FlightSelection)
        .filter(FlightSelection.icao24 == code)
        .first()
    )
    if selection and isinstance(selection.last_position, dict):
        pos = selection.last_position
        if pos.get("latitude") is not None and pos.get("longitude") is not None:
            return pos["latitude"], pos["longitude"], "watchlist_cache"

    # 3. Live OpenSky state vector.
    service = get_opensky_service()
    if service.configured:
        try:
            data = await service.get_states(icao24=[code])
            for state in data.get("states") or []:
                if state.get("latitude") is not None:
                    return state["latitude"], state["longitude"], "opensky_live"
        except Exception:
            pass

    return None
