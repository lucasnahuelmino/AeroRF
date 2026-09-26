"""
api/routes/export.py
────────────────────
Export endpoints (spec §46).

    GET /api/v1/export/geojson   map objects as a FeatureCollection
    GET /api/v1/export/kml       map objects as KML 2.2
    GET /api/v1/export/csv       map objects as CSV
    GET /api/v1/export/track/{icao24}.{fmt}   a trajectory

Every export honours the same filters as ``GET /api/v1/map/objects`` and
embeds provenance metadata, so a file handed to somebody outside AeroRF
still says where each value came from.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.services import export_service as exporter
from app.services import flight_service as fsvc
from app.services import map_service as svc

router = APIRouter(prefix="/export", tags=["Export"])

STAMP = "2026-09-25T00:00:00Z"


def _filter(db: Session, args: dict):
    return svc.list_objects(db, **args)


def _disposition(kind: str, filename: Optional[str]) -> dict:
    name = filename or f"aerorf.{kind}"
    return {"Content-Disposition": f'attachment; filename="{name}"'}


@router.get("/geojson")
def export_geojson(
    type: Optional[str] = None,
    layer_id: Optional[int] = None,
    expediente_id: Optional[int] = None,
    status: Optional[str] = None,
    include_history: bool = Query(
        False, description="Embed the full change history in properties"
    ),
    pretty: bool = True,
    filename: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Export map objects as GeoJSON (spec §17, §46)."""
    from app.api.routes.map import _parse_bbox

    types = [t.strip() for t in type.split(",") if t.strip()] if type else None
    objects = svc.list_objects(
        db, types=types, layer_id=layer_id,
        expediente_id=expediente_id, status=status, limit=5000,
    )
    collection = exporter.to_geojson(objects, include_history=include_history)
    collection["name"] = filename or "AeroRF"
    return Response(
        content=__import__("json").dumps(
            collection, ensure_ascii=False,
            indent=2 if pretty else None, default=str,
        ),
        media_type="application/geo+json",
        headers=_disposition("geojson", filename),
    )


@router.get("/kml", response_class=PlainTextResponse)
def export_kml(
    type: Optional[str] = None,
    layer_id: Optional[int] = None,
    expediente_id: Optional[int] = None,
    status: Optional[str] = None,
    filename: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Export map objects as KML 2.2 (spec §46)."""
    types = [t.strip() for t in type.split(",") if t.strip()] if type else None
    objects = svc.list_objects(
        db, types=types, layer_id=layer_id,
        expediente_id=expediente_id, status=status, limit=5000,
    )
    name = filename or "AeroRF"
    return Response(
        content=exporter.to_kml(objects, name=name),
        media_type="application/vnd.google-earth.kml+xml",
        headers=_disposition("kml", filename),
    )


@router.get("/csv", response_class=PlainTextResponse)
def export_csv(
    type: Optional[str] = None,
    layer_id: Optional[int] = None,
    expediente_id: Optional[int] = None,
    status: Optional[str] = None,
    include_notes: bool = Query(True, description="Append the note log"),
    filename: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Export map objects as CSV (spec §46).

    Semicolon-delimited so the file opens directly in a Spanish-locale
    Excel.
    """
    types = [t.strip() for t in type.split(",") if t.strip()] if type else None
    objects = svc.list_objects(
        db, types=types, layer_id=layer_id,
        expediente_id=expediente_id, status=status, limit=5000,
    )
    # Notes live in a relationship; force them to load for the CSV.
    for obj in objects:
        _ = obj.notes
    return Response(
        content=exporter.to_csv(objects, include_notes=include_notes),
        media_type="text/csv; charset=utf-8",
        headers=_disposition("csv", filename),
    )


@router.get("/track/{icao24}")
def export_track(
    icao24: str,
    fmt: str = Query("geojson", pattern="^(geojson|csv)$"),
    db: Session = Depends(get_db),
):
    """Export a stored trajectory.

    Serves what AeroRF actually holds — the OpenSky track merged with any
    local recording — and labels each point's provenance. It does not
    re-query OpenSky, so exporting never costs a credit.
    """
    from app.models.flight import AircraftTrack

    code = str(icao24).strip().lower()
    tracks = (
        db.query(AircraftTrack)
        .filter(AircraftTrack.icao24 == code)
        .order_by(AircraftTrack.started_at.desc().nullslast())
        .all()
    )
    if not tracks:
        raise HTTPException(
            404,
            f"No stored track for {code}. Fetch it via "
            f"/api/v1/flights/{code}/track first.",
        )

    track = tracks[0]
    points = _points_from_geometry(track)

    if fmt == "csv":
        return Response(
            content=exporter.track_to_csv(points),
            media_type="text/csv; charset=utf-8",
            headers=_disposition("csv", f"track_{code}.csv"),
        )

    import json

    return Response(
        content=json.dumps(
            exporter.track_to_geojson(points, code, track.callsign),
            ensure_ascii=False, indent=2, default=str,
        ),
        media_type="application/geo+json",
        headers=_disposition("geojson", f"track_{code}.geojson"),
    )


def _points_from_geometry(track) -> list[dict]:
    """Rebuild point dicts from a stored track, without inventing times."""
    geometry = track.geometry or {}
    coords = geometry.get("coordinates") or []
    meta = track.meta or {}
    counts = meta.get("provenance_counts") or {}
    only_source = next(iter(counts), None) if len(counts) == 1 else None

    points: list[dict] = []
    # The stored geometry keeps positions but not per-point altitude, so
    # this export is explicitly a position-only track.
    for lon, lat in coords:
        points.append(
            {
                "timestamp": None,
                "latitude": lat,
                "longitude": lon,
                "altitude": None,
                "heading": None,
                "on_ground": None,
                "icao24": track.icao24,
                "callsign": track.callsign,
                "provenance": only_source or "mixed",
            }
        )
    return points
