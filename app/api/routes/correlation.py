"""
api/routes/correlation.py
────────────────────────
Correlación espacial entre objetos RF y aeronaves (spec §35).

    POST /api/v1/correlation/rf-aircraft   aeronaves cerca de un objeto RF
    GET  /api/v1/correlation/aircraft/{icao24}  objetos RF cerca de una aeronave
    GET  /api/v1/correlation/object/{id}        informe completo

Una nota gobierna cada respuesta de acá: cuando el evento tiene fecha
de observación (``observed_at``), la comparación es espacial **y
temporal contra esa fecha** — cada coincidencia declara su
``delta_t_s`` y sólo cuenta dentro de la ventana —; sin fecha, es
espacial y la respuesta lo declara. ADS-B no lleva datos de emisión, y
la distancia geográfica entre una aeronave y un evento RF registrado no
dice nada sobre cuál causó el otro. Cada respuesta lleva ese disclaimer
en su payload para que viaje con los datos hacia cualquier export.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.correlacion import (
    CORRELACION_VENTANA_TEMPORAL_S,
    DISCLAIMER,
    DISCLAIMER_AERONAVE,
    caja_alrededor,
    delta_t_s,
)
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
        raise HTTPException(400, "object_id es obligatorio.")
    # El cuerpo llega crudo (`body: dict`): un id no numérico era
    # ValueError → 500 (F2-05).
    try:
        oid = int(object_id)
    except (TypeError, ValueError):
        raise HTTPException(
            400, "object_id debe ser un número entero."
        ) from None

    obj = svc.get_object(db, oid)
    if obj is None:
        raise HTTPException(404, f"No existe el objeto {object_id}.")
    if obj.latitude is None or obj.longitude is None:
        raise HTTPException(
            400, f"El objeto {object_id} no tiene posición, no se puede correlizar."
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
            # La caja del radio máximo alrededor del objeto, no el estado
            # global: se pide sólo lo que puede correlizar (y la caja de
            # 50 nm sigue en el tramo de 1 crédito).
            caja = caja_alrededor(
                obj.latitude, obj.longitude, to_metres(radii[-1], "nm")
            )
            states = (await service.get_states_in_box(*caja)).get("states") or []
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
        raise HTTPException(404, f"No existe el objeto {object_id}.")
    if obj.latitude is None or obj.longitude is None:
        raise HTTPException(
            400, f"El objeto {object_id} no tiene posición."
        )

    radios = _radii(radii_nm)
    service = get_opensky_service()
    if not service.configured:
        raise HTTPException(
            503, "OpenSky no está configurado; no hay datos de aeronaves."
        )
    try:
        # La caja del radio máximo alrededor del objeto, no el estado global.
        caja = caja_alrededor(
            obj.latitude, obj.longitude, to_metres(radios[-1], "nm")
        )
        states = (await service.get_states_in_box(*caja)).get("states") or []
    except (OpenSkyNotConfigured, OpenSkyError) as exc:
        raise HTTPException(502, str(exc))

    return _correlate(obj, states, radios)


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
        "disclaimer": DISCLAIMER_AERONAVE,
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
        raise HTTPException(400, "radii_nm debe ser una lista de números.")
    return values or list(CORRELATION_RADII_NM)


def _correlate(obj: MapObject, states: list[dict], radii: list[float]) -> dict:
    """Bandas de distancia + comparación temporal contra ``observed_at``.

    Si el objeto tiene fecha de observación, sólo se cuentan los estados
    dentro de la ventana ``CORRELACION_VENTANA_TEMPORAL_S`` de ella; los
    que caen dentro del radio pero fuera de la ventana se reportan en
    ``fuera_de_ventana`` y no se cuentan. Sin fecha no hay nada que
    comparar: se corrige lo espacial y la respuesta se declara
    ``espacial``.
    """
    ventana = (
        CORRELACION_VENTANA_TEMPORAL_S if obj.observed_at is not None else None
    )
    radio_max_m = to_metres(max(radii), "nm")

    # Pase único: posición dentro de todo el radio pedido + delta contra
    # observed_at. (estado, delta, distancia) — la banda sólo compara.
    parejas: list[tuple[dict, Optional[int], float]] = []
    fuera_de_ventana: Optional[int] = 0 if ventana is not None else None
    for state in states:
        lat, lon = state.get("latitude"), state.get("longitude")
        if lat is None or lon is None:
            continue
        distance = haversine_m(obj.latitude, obj.longitude, lat, lon)
        if distance > radio_max_m:
            continue
        delta = delta_t_s(obj.observed_at, state)
        if ventana is None or (delta is not None and abs(delta) <= ventana):
            parejas.append((state, delta, distance))
        elif fuera_de_ventana is not None:
            fuera_de_ventana += 1

    bands: list[dict] = []
    for radius_nm in radii:
        radius_m = to_metres(radius_nm, "nm")
        matches: list[dict] = []
        for state, delta, distance in parejas:
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
                                obj.latitude,
                                obj.longitude,
                                state.get("latitude"),
                                state.get("longitude"),
                            ),
                            1,
                        ),
                        "altitude": state.get("altitude"),
                        "velocity": state.get("velocity"),
                        "heading": state.get("heading"),
                        "on_ground": state.get("on_ground"),
                        "timestamp": state.get("time_position"),
                        "aircraft_updated_at": state.get("last_contact"),
                        "delta_t_s": delta,
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
        "comparacion": (
            "espacial_y_temporal" if ventana is not None else "espacial"
        ),
        "observado_en": (
            obj.observed_at.isoformat() if obj.observed_at is not None else None
        ),
        "ventana_temporal_s": ventana,
        "fuera_de_ventana": fuera_de_ventana,
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
