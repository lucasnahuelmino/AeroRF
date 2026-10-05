"""
api/routes/map.py
────────────────
The GIS object API (spec §47).

    GET    /api/v1/map/objects          list / filter
    POST   /api/v1/map/objects          create
    GET    /api/v1/map/objects/{id}     read
    PUT    /api/v1/map/objects/{id}     update (historised)
    DELETE /api/v1/map/objects/{id}     delete
    PATCH  /api/v1/map/objects/{id}/status
    PATCH  /api/v1/map/objects/{id}/move
    POST   /api/v1/map/objects/{id}/duplicate
    GET    /api/v1/map/objects/{id}/history
    GET    /api/v1/map/objects/{id}/notes
    POST   /api/v1/map/objects/{id}/notes
    POST   /api/v1/map/objects/{id}/annotations
    GET    /api/v1/map/objects/stats
    GET    /api/v1/map/objects/near
    GET    /api/v1/map/objects/distances
    POST   /api/v1/map/objects/from-geojson

One create/read/update path for every object type — a circle, a source and
an antenna differ only by their payload, not by their endpoint.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
# `func` is imported at module level, not inside a route. It used to be
# imported inside `list_layers`, which made it a *local* name there: every
# other handler that counted objects raised NameError and returned 500.
# `PUT /map/layers/{id}` — the toggle behind the layer panel — was one of them,
# so no layer could be shown, hidden or reordered from the interface.
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.layer import Layer
from app.models.map_object import MapObject
from app.models.schemas_gis import (
    AnnotationCreate,
    DuplicateRequest,
    HistoryResponse,
    MapObjectCreate,
    MapObjectUpdate,
    MoveRequest,
    NoteCreate,
    NoteResponse,
    StatusChange,
)
from app.services import geojson_service as gjs
from app.services import map_service as svc
from app.core.geo import format_latlon
from app.core.units import UNIT_NM, to_metres

router = APIRouter(tags=["Map Objects"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _bad_request(exc: svc.MapServiceError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _not_found(object_id: int) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No existe el objeto {object_id}.")


def _to_leaflet(obj: MapObject) -> dict:
    payload = gjs.object_to_leaflet(obj)
    if payload is None:
        # Persisted but geometry is not derivable; surface it honestly
        # rather than dropping it silently from the map.
        return {
            "id": obj.id,
            "type": obj.type,
            "name": obj.name,
            "geometry": None,
            "geometry_type": None,
            "latlng": None,
            "latlngs": [],
            "properties": {"id": obj.id, "type": obj.type},
            "warning": "Objeto sin geometría derivable",
        }
    return payload


# ─── Object list / create ────────────────────────────────────────────────────

@router.get("/map/objects")
def list_map_objects(
    type: Optional[str] = Query(
        None, description="Comma-separated object types"
    ),
    layer_id: Optional[int] = None,
    layer_key: Optional[str] = None,
    expediente_id: Optional[int] = None,
    status: Optional[str] = None,
    visible: Optional[bool] = None,
    bbox: Optional[str] = Query(
        None, description="lat_min,lon_min,lat_max,lon_max"
    ),
    search: Optional[str] = None,
    limit: int = Query(2000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    format: str = Query("leaflet", pattern="^(leaflet|geojson|raw)$"),
    db: Session = Depends(get_db),
):
    """List map objects, optionally filtered by layer, expediente, state or box."""
    types = [t.strip() for t in type.split(",") if t.strip()] if type else None
    box = _parse_bbox(bbox)

    try:
        objects = svc.list_objects(
            db,
            types=types,
            layer_id=layer_id,
            layer_key=layer_key,
            expediente_id=expediente_id,
            status=status,
            visible=visible,
            bbox=box,
            search=search,
            limit=limit,
            offset=offset,
        )
    except svc.MapServiceError as exc:
        raise _bad_request(exc)

    if format == "geojson":
        return gjs.objects_to_feature_collection(objects)
    if format == "raw":
        return [_to_leaflet(o) for o in objects]
    return {"count": len(objects), "objects": [_to_leaflet(o) for o in objects]}


@router.post("/map/objects", status_code=status.HTTP_201_CREATED)
def create_map_object(
    payload: MapObjectCreate,
    db: Session = Depends(get_db),
):
    """Create any GIS object: point, circle, radial, source, antenna, event…"""
    data = payload.model_dump()
    try:
        obj = svc.create_object(
            db,
            data["type"],
            name=data["name"],
            description=data["description"],
            category=data["category"],
            status=data["status"],
            latitude=data["latitude"],
            longitude=data["longitude"],
            radius=data["radius"],
            radius_unit=data["radius_unit"],
            azimuth=data["azimuth"],
            length_value=data["length_value"],
            length_unit=data["length_unit"],
            geometry=data["geometry"],
            geometry_type=data["geometry_type"],
            color=data["color"],
            icon=data["icon"],
            label=data["label"],
            opacity=data["opacity"],
            weight=data["weight"],
            fill_opacity=data["fill_opacity"],
            layer_id=data["layer_id"],
            layer_key=data["layer_key"],
            visible=data["visible"],
            locked=data["locked"],
            z_index=data["z_index"],
            expediente_id=data["expediente_id"],
            observed_at=data["observed_at"],
            valid_from=data["valid_from"],
            valid_to=data["valid_to"],
            source=data["source"],
            created_by=data["created_by"],
            properties=data["properties"],
            user=data["user"],
            comment=data["comment"],
            notes=data["notes"],
            # model_dump() has already turned nested payloads into dicts.
            rf=data["rf"] or None,
            antenna=data["antenna"] or None,
            reference=data["reference"] or None,
            measurement=data["measurement"] or None,
            event=data["event"] or None,
        )
    except svc.MapServiceError as exc:
        raise _bad_request(exc)

    obj.show_label = payload.show_label
    db.commit()
    db.refresh(obj)
    return _to_leaflet(obj)


# ─── Object read / update / delete ───────────────────────────────────────────

@router.get("/map/objects/stats")
def get_object_stats(db: Session = Depends(get_db)):
    return svc.object_stats(db)


@router.get("/map/objects/near")
def get_objects_near(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_nm: float = Query(5, gt=0, le=500),
    type: Optional[str] = None,
    expediente_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Objects within a radius, nearest first (spec §35)."""
    types = [t.strip() for t in type.split(",") if t.strip()] if type else None
    rows = svc.objects_near(
        db, latitude, longitude, radius_nm,
        types=types, expediente_id=expediente_id,
    )
    return {
        "center": {"latitude": latitude, "longitude": longitude},
        "radius_nm": radius_nm,
        "count": len(rows),
        "results": [
            {
                **_to_leaflet(row["object"]),
                "distance_m": row["distance_m"],
                "distance_km": row["distance_m"] / 1000.0,
                "distance_nm": row["distance_m"] / 1852.0,
            }
            for row in rows
        ],
    }


@router.get("/map/objects/distances")
def get_distances(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    object_ids: Optional[str] = Query(
        None, description="Comma-separated object ids"
    ),
    type: Optional[str] = None,
    expediente_id: Optional[int] = None,
    radius_nm: Optional[float] = Query(None, gt=0, le=500),
    db: Session = Depends(get_db),
):
    """Distance from a point to references, in KM and NM (spec §30).

    This is what answers "select an aircraft, how far is it from each
    source, event, antenna and circle?".
    """
    ids = None
    if object_ids:
        try:
            ids = [int(i) for i in object_ids.split(",") if i.strip()]
        except ValueError:
            raise HTTPException(400, "object_ids must be comma-separated integers")
    types = [t.strip() for t in type.split(",") if t.strip()] if type else None

    rows = svc.distances_from(
        db, latitude, longitude,
        object_ids=ids, types=types,
        expediente_id=expediente_id, radius_nm=radius_nm,
    )
    return {
        "origin": {"latitude": latitude, "longitude": longitude},
        "count": len(rows),
        "results": rows,
    }


@router.post("/map/objects/from-geojson")
def import_geojson(
    body: dict = Body(..., description="GeoJSON Feature or FeatureCollection"),
    layer_key: Optional[str] = None,
    user: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Import GeoJSON features as map objects (spec §17, §46)."""
    from app.models.constants import PROVENANCE_IMPORTED

    features: list[dict]
    if body.get("type") == "FeatureCollection":
        features = body.get("features") or []
    elif body.get("type") == "Feature":
        features = [body]
    else:
        raise HTTPException(400, "Expected a GeoJSON Feature or FeatureCollection")

    created, errors = [], []
    for index, feature in enumerate(features):
        params = gjs.geojson_feature_to_object_params(feature)
        # Guess the type from the geometry when the import omits it.
        gtype = params.get("geometry_type")
        if params.get("radius") is not None:
            otype = "circle"
        elif params.get("azimuth") is not None:
            otype = "radial"
        elif gtype == "Polygon":
            otype = "polygon"
        elif gtype == "LineString":
            otype = "trace"
        else:
            otype = params.get("type") or "point"

        try:
            obj = svc.create_object(
                db,
                otype,
                name=params.get("name"),
                description=params.get("description"),
                category=params.get("category"),
                status=params.get("status"),
                latitude=params.get("latitude"),
                longitude=params.get("longitude"),
                radius=params.get("radius"),
                radius_unit=params.get("radius_unit"),
                azimuth=params.get("azimuth"),
                length_value=params.get("length_value"),
                length_unit=params.get("length_unit"),
                geometry=params.get("geometry"),
                geometry_type=params.get("geometry_type"),
                color=params.get("color"),
                icon=params.get("icon"),
                label=params.get("label"),
                layer_key=layer_key,
                properties=params.get("properties"),
                # Un archivo importado no lo tecleó nadie: la procedencia
                # tiene que decirlo (F2-08).
                source=PROVENANCE_IMPORTED,
                user=user,
                comment="Importado desde GeoJSON",
            )
            created.append({"id": obj.id, "type": obj.type, "name": obj.name})
        except svc.MapServiceError as exc:
            errors.append({"index": index, "error": str(exc)})

    return {"created": created, "errors": errors, "count": len(created)}


@router.get("/map/objects/{object_id}")
def get_map_object(object_id: int, db: Session = Depends(get_db)):
    """One object with its payload, notes and derived metrics."""
    obj = svc.get_object(db, object_id)
    if obj is None:
        raise _not_found(object_id)

    payload = _to_leaflet(obj)
    payload["notes"] = [
        {
            "id": n.id,
            "text": n.text,
            "user": n.user,
            "timestamp": n.timestamp,
        }
        for n in obj.notes
    ]
    payload["history_count"] = len(obj.history)
    if obj.expediente:
        payload["expediente"] = {
            "id": obj.expediente.id,
            "numero_expediente": obj.expediente.numero_expediente,
            "estado": obj.expediente.estado,
            "freq_mhz": obj.expediente.freq_mhz,
            "aeropuerto": obj.expediente.aeropuerto,
        }
    return payload


@router.put("/map/objects/{object_id}")
def update_map_object(
    object_id: int,
    payload: MapObjectUpdate,
    db: Session = Depends(get_db),
):
    """Partial update. Each changed field is written to the history log."""
    if svc.get_object(db, object_id) is None:
        raise _not_found(object_id)

    patch = payload.model_dump(exclude_unset=True, exclude_none=False)
    patch = {k: v for k, v in patch.items() if k not in {"user", "comment"}}
    if not patch:
        raise HTTPException(400, "No fields to update")

    try:
        obj = svc.update_object(
            db, object_id, patch,
            user=payload.user, comment=payload.comment,
        )
    except svc.MapServiceError as exc:
        raise _bad_request(exc)
    return _to_leaflet(obj)


@router.delete("/map/objects/{object_id}")
def delete_map_object(
    object_id: int,
    cascade: bool = Query(False, description="Force delete linked objects"),
    user: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Delete an object. Refused when it belongs to an expediente."""
    if svc.get_object(db, object_id) is None:
        raise _not_found(object_id)
    try:
        svc.delete_object(db, object_id, cascade=cascade, user=user)
    except svc.MapServiceError as exc:
        raise _bad_request(exc)
    return {"deleted": object_id}


@router.patch("/map/objects/{object_id}/status")
def change_status(
    object_id: int,
    payload: StatusChange,
    db: Session = Depends(get_db),
):
    """Change an object's state (spec §15). Always historised."""
    if svc.get_object(db, object_id) is None:
        raise _not_found(object_id)
    try:
        obj = svc.set_status(
            db, object_id, payload.status,
            user=payload.user, comment=payload.comment,
        )
    except svc.MapServiceError as exc:
        raise _bad_request(exc)
    return _to_leaflet(obj)


@router.patch("/map/objects/{object_id}/move")
def move_map_object(
    object_id: int,
    payload: MoveRequest,
    db: Session = Depends(get_db),
):
    """Reposition an object by dragging it on the map (spec §8)."""
    if svc.get_object(db, object_id) is None:
        raise _not_found(object_id)
    try:
        obj = svc.move_object(
            db, object_id, payload.latitude, payload.longitude, user=payload.user
        )
    except svc.MapServiceError as exc:
        raise _bad_request(exc)
    return _to_leaflet(obj)


@router.post("/map/objects/{object_id}/duplicate")
def duplicate_map_object(
    object_id: int,
    payload: DuplicateRequest = DuplicateRequest(),
    db: Session = Depends(get_db),
):
    """Copy an object (spec §8)."""
    try:
        obj = svc.duplicate_object(
            db, object_id,
            name_suffix=payload.name_suffix,
            offset_lat=payload.offset_lat,
            offset_lon=payload.offset_lon,
            user=payload.user,
        )
    except svc.MapServiceError as exc:
        if "no existe" in str(exc):
            raise _not_found(object_id)
        raise _bad_request(exc)
    return _to_leaflet(obj)


# ─── Notes, history, annotations ─────────────────────────────────────────────

@router.get("/map/objects/{object_id}/notes", response_model=list[NoteResponse])
def get_notes(object_id: int, db: Session = Depends(get_db)):
    """Append-only note log (spec §14, §42)."""
    if svc.get_object(db, object_id) is None:
        raise _not_found(object_id)
    return svc.list_notes(db, object_id)


@router.post("/map/objects/{object_id}/notes", status_code=status.HTTP_201_CREATED)
def add_note(
    object_id: int,
    payload: NoteCreate,
    db: Session = Depends(get_db),
):
    """Append a note. Notes are never overwritten (spec §14)."""
    try:
        return svc.add_note(db, object_id, payload.text, user=payload.user)
    except svc.MapServiceError as exc:
        if "no existe" in str(exc):
            raise _not_found(object_id)
        raise _bad_request(exc)


@router.get("/map/objects/{object_id}/history", response_model=list[HistoryResponse])
def get_history(
    object_id: int,
    field: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """Field-level change history (spec §41). Nothing is ever removed."""
    if svc.get_object(db, object_id) is None:
        raise _not_found(object_id)
    return svc.list_history(db, object_id, field=field, limit=limit)


@router.post("/map/objects/{object_id}/annotations", status_code=status.HTTP_201_CREATED)
def add_annotation(
    object_id: int,
    payload: AnnotationCreate,
    db: Session = Depends(get_db),
):
    """Attach an annotation to an object."""
    try:
        return svc.add_annotation(
            db, object_id, payload.text,
            author=payload.author, category=payload.category,
        )
    except svc.MapServiceError as exc:
        if "no existe" in str(exc):
            raise _not_found(object_id)
        raise _bad_request(exc)


# ─── Layers (spec §38) ───────────────────────────────────────────────────────

@router.get("/map/layers")
def list_layers(db: Session = Depends(get_db)):
    """All layers with their live object counts."""
    rows = (
        db.query(Layer, func.count(MapObject.id))
        .outerjoin(MapObject, MapObject.layer_id == Layer.id)
        .group_by(Layer.id)
        .order_by(Layer.order_index, Layer.id)
        .all()
    )
    return {
        "count": len(rows),
        "layers": [
            {
                "id": layer.id,
                "key": layer.key,
                "name": layer.name,
                "description": layer.description,
                "object_types": layer.object_types,
                "visible": layer.visible,
                "opacity": layer.opacity,
                "order_index": layer.order_index,
                "locked": layer.locked,
                "min_zoom": layer.min_zoom,
                "max_zoom": layer.max_zoom,
                "color": layer.color,
                "is_system": layer.is_system,
                "object_count": count,
            }
            for layer, count in rows
        ],
    }


@router.post("/map/layers", status_code=status.HTTP_201_CREATED)
def create_layer(payload: dict = Body(...), db: Session = Depends(get_db)):
    """Create a custom layer."""
    key = (payload.get("key") or "").strip()
    if not key or not key.replace("_", "").isalnum():
        raise HTTPException(400, "key must be alphanumeric with underscores")
    if db.query(Layer).filter(Layer.key == key).first():
        raise HTTPException(400, f"Layer key {key!r} already exists")

    # El cuerpo llega crudo (`body: dict`): sin este corte, un `opacity`
    # no numérico era ValueError → 500 (F2-05).
    try:
        opacity = float(payload.get("opacity", 1.0))
    except (TypeError, ValueError):
        raise HTTPException(400, "opacity debe ser un número.") from None
    try:
        order_index = int(payload.get("order_index", 500))
    except (TypeError, ValueError):
        raise HTTPException(400, "order_index debe ser un número entero.") from None

    layer = Layer(
        key=key,
        name=payload.get("name") or key,
        description=payload.get("description"),
        visible=bool(payload.get("visible", True)),
        opacity=opacity,
        order_index=order_index,
        is_system=False,
    )
    db.add(layer)
    db.commit()
    db.refresh(layer)
    return {
        "id": layer.id, "key": layer.key, "name": layer.name,
        "visible": layer.visible, "opacity": layer.opacity,
        "order_index": layer.order_index, "locked": layer.locked,
        "object_count": 0, "is_system": layer.is_system,
    }


@router.put("/map/layers/{layer_id}")
def update_layer(
    layer_id: int, payload: dict = Body(...), db: Session = Depends(get_db)
):
    """Change visibility, opacity, order, lock or zoom limits (spec §38)."""
    layer = db.query(Layer).filter(Layer.id == layer_id).first()
    if layer is None:
        raise HTTPException(404, f"Layer {layer_id} not found")

    allowed = {
        "name", "description", "visible", "opacity",
        "order_index", "locked", "min_zoom", "max_zoom", "color",
    }
    for field, value in payload.items():
        if field in allowed:
            setattr(layer, field, value)
    db.commit()
    db.refresh(layer)
    return {
        "id": layer.id, "key": layer.key, "name": layer.name,
        "visible": layer.visible, "opacity": layer.opacity,
        "order_index": layer.order_index, "locked": layer.locked,
        "min_zoom": layer.min_zoom, "max_zoom": layer.max_zoom,
        "object_count": db.query(func.count(MapObject.id))
        .filter(MapObject.layer_id == layer_id).scalar() or 0,
    }


@router.delete("/map/layers/{layer_id}")
def delete_layer(
    layer_id: int,
    clear: bool = Query(False, description="También borra los objetos de la capa"),
    db: Session = Depends(get_db),
):
    """Borra una capa propia. Las de sistema están protegidas.

    F2-04: si después de limpiar queda algún objeto protegido (bloqueado,
    vinculado a un expediente o parte de un grupo), la capa **no** se borra
    y se contesta 409 con el detalle. `Layer.objects` no tiene cascade, así
    que SQLAlchemy pondría `layer_id = NULL` en los supervivientes y los
    dejaría huérfanos: protegerlos dentro de `clear_layer` no serviría de
    nada si la capa se borrara igual.
    """
    layer = db.query(Layer).filter(Layer.id == layer_id).first()
    if layer is None:
        raise HTTPException(404, f"No existe la capa {layer_id}")
    if layer.is_system:
        raise HTTPException(
            400, "Las capas de sistema no se pueden borrar; ocultalas en su lugar."
        )

    limpiados = 0
    if clear:
        limpiados = svc.clear_layer(db, layer_id, cascade=True)

    restantes = (
        db.query(func.count(MapObject.id))
        .filter(MapObject.layer_id == layer_id)
        .scalar()
        or 0
    )
    if restantes:
        if clear:
            detalle = (
                f"Quedan {restantes} objeto(s) protegido(s) (bloqueados, "
                f"vinculados a un expediente o parte de un grupo): se borraron "
                f"{limpiados} libres y la capa no se borra hasta que no queden. "
                "Desbloquéalos o desvincúlos e inténtalo de nuevo."
            )
        else:
            detalle = (
                f"La capa todavía tiene {restantes} objeto(s); usa clear=true "
                "para borrarlos junto con la capa."
            )
        raise HTTPException(409, detalle)

    db.delete(layer)
    db.commit()
    return {"deleted": layer_id}


# ─── Utilities ───────────────────────────────────────────────────────────────

@router.get("/map/coordinate")
def describe_coordinate(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    format: str = Query("dd", pattern="^(dd|dms|dmm)$"),
):
    """Format a coordinate pair (spec §5).

    Lets the frontend verify its own formatting against the backend, so
    the cursor bar and the print output cannot disagree.
    """
    return {
        "latitude": latitude,
        "longitude": longitude,
        "text": format_latlon(latitude, longitude, format),
        "format": format,
    }


@router.get("/map/vocabulary")
def get_vocabulary():
    """Closed vocabularies so the UI cannot offer an invalid value."""
    from app.models.constants import (
        ANTENNA_KINDS,
        OBJECT_STATES,
        OBJECT_TYPES,
        POINT_CATEGORIES,
        POLARIZATIONS,
        PROVENANCE_LABELS_ES,
        PROVENANCE_VALUES,
        REFERENCE_RADII_NM,
        RF_EVENT_CLASSIFICATIONS,
        RF_SOURCE_KINDS,
        CORRELATION_RADII_NM,
    )
    from app.core.units import SUPPORTED_UNITS

    return {
        "object_types": list(OBJECT_TYPES),
        "states": list(OBJECT_STATES),
        "point_categories": list(POINT_CATEGORIES),
        "rf_source_kinds": list(RF_SOURCE_KINDS),
        "rf_event_classifications": list(RF_EVENT_CLASSIFICATIONS),
        "antenna_kinds": list(ANTENNA_KINDS),
        "polarizations": list(POLARIZATIONS),
        "units": list(SUPPORTED_UNITS),
        "reference_radii_nm": list(REFERENCE_RADII_NM),
        "correlation_radii_nm": list(CORRELATION_RADII_NM),
        "provenance": list(PROVENANCE_VALUES),
        "provenance_labels": PROVENANCE_LABELS_ES,
    }


def _parse_bbox(raw: Optional[str]):
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise HTTPException(
            400, "bbox must be 'lat_min,lon_min,lat_max,lon_max'"
        )
    try:
        lat_min, lon_min, lat_max, lon_max = (float(p) for p in parts)
    except ValueError:
        raise HTTPException(400, "bbox values must be numbers")
    if lat_min > lat_max:
        lat_min, lat_max = lat_max, lat_min
    if lon_min > lon_max:
        lon_min, lon_max = lon_max, lon_min
    return lat_min, lon_min, lat_max, lon_max
