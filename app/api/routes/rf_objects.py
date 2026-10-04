"""
api/routes/rf_objects.py
────────────────────────
Type-specific endpoints for RF sources, antennas and events (spec §32–§34).

These are **views** over `MapObject`, not a second store. A source created
here is a normal map object: it appears in the layer list, can be dragged,
hidden, edited, historised and exported like any other. The endpoints
here simply accept the type-specific fields and then return the standard
object representation, so the frontend has one object shape to render.

    GET/POST   /api/v1/rf/sources
    GET/PUT    /api/v1/rf/sources/{id}
    GET/POST   /api/v1/rf/events
    GET/PUT    /api/v1/rf/events/{id}
    GET/POST   /api/v1/antennas
    GET/PUT    /api/v1/antennas/{id}
    GET/POST   /api/v1/references
    GET/PUT    /api/v1/references/{id}
    GET        /api/v1/rf/summary
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.constants import (
    TYPE_ANTENNA,
    TYPE_RF_EVENT,
    TYPE_RF_SOURCE,
    TYPE_REFERENCE,
)
from app.models.map_object import MapObject
from app.models.schemas_gis import (
    AntennaPayload,
    MapObjectCreate,
    MapObjectUpdate,
    RFEventPayload,
    RFSourcePayload,
    ReferencePayload,
)
from app.services import geojson_service as gjs
from app.services import map_service as svc

router = APIRouter(tags=["RF Objects"])


def _to_leaflet(obj: MapObject) -> dict:
    return gjs.object_to_leaflet(obj) or {
        "id": obj.id, "type": obj.type, "name": obj.name,
        "geometry": None, "latlngs": [],
    }


def _not_found(oid: int) -> HTTPException:
    return HTTPException(404, f"Object {oid} not found")


def _chequear_candado(db_obj: MapObject, patch: dict) -> None:
    """El candado se chequea **antes** de escribir el satélite (F2-01).

    En las cuatro rutas los campos tipados se escribían y hacían `commit`
    antes de llegar a `svc.update_object`, único punto que verificaba el
    candado: con la fuente bloqueada, `PUT ... {"frequency_mhz": 200}`
    respondía 200, y un cuerpo mixto dejaba el campo RF guardado aunque la
    respuesta fuera 400.
    """
    try:
        svc.require_unlocked(db_obj, patch)
    except svc.MapServiceError as exc:
        raise HTTPException(400, str(exc))


# ─── RF sources (spec §32) ───────────────────────────────────────────────────

@router.get("/rf/sources")
def list_sources(
    expediente_id: Optional[int] = None,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    bbox: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List interfering sources, with their RF attributes attached."""
    from app.api.routes.map import _parse_bbox

    q = (
        db.query(MapObject)
        .filter(MapObject.type == TYPE_RF_SOURCE)
        .options(*_loaders())
    )
    if expediente_id is not None:
        q = q.filter(MapObject.expediente_id == expediente_id)
    if status:
        q = q.filter(MapObject.status == status)
    box = _parse_bbox(bbox)
    if box:
        q = q.filter(
            MapObject.latitude.between(box[0], box[2]),
            MapObject.longitude.between(box[1], box[3]),
        )
    rows = q.order_by(MapObject.id).all()

    out = []
    for obj in rows:
        payload = _to_leaflet(obj)
        if obj.rf_source and kind and obj.rf_source.kind != kind:
            continue
        out.append(payload)
    return {"count": len(out), "sources": out}


@router.post("/rf/sources", status_code=status.HTTP_201_CREATED)
def create_source(
    body: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Create an interfering source.

    Accepts either a full ``MapObjectCreate``-shaped body with a ``rf``
    block, or a flat body where the RF fields sit at the top level
    (frequency_mhz, power_dbm, …). Both are common in field use.
    """
    payload = _coerce(MapObjectCreate, {**body, "type": TYPE_RF_SOURCE}, default_rf=True)
    data = payload.model_dump()
    try:
        obj = svc.create_object(
            db, TYPE_RF_SOURCE,
            name=data["name"], description=data["description"],
            category=data["category"], status=data["status"],
            latitude=data["latitude"], longitude=data["longitude"],
            color=data["color"], icon=data["icon"], label=data["label"],
            layer_id=data["layer_id"], layer_key=data["layer_key"],
            visible=data["visible"], locked=data["locked"],
            z_index=data["z_index"], expediente_id=data["expediente_id"],
            observed_at=data["observed_at"],
            source=data["source"], created_by=data["created_by"],
            properties=data["properties"],
            user=data["user"], comment=data["comment"], notes=data["notes"],
            rf=data["rf"] or None,
        )
    except svc.MapServiceError as exc:
        raise HTTPException(400, str(exc))
    return _to_leaflet(obj)


@router.get("/rf/sources/{object_id}")
def get_source(object_id: int, db: Session = Depends(get_db)):
    obj = svc.get_object(db, object_id)
    if obj is None or obj.type != TYPE_RF_SOURCE:
        raise _not_found(object_id)
    return _to_leaflet(obj)


@router.put("/rf/sources/{object_id}")
def update_source(
    object_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Update a source. RF fields are historised like any other."""
    obj = svc.get_object(db, object_id)
    if obj is None or obj.type != TYPE_RF_SOURCE:
        raise _not_found(object_id)

    rf_patch = {k: v for k, v in body.items() if k in RFSourcePayload.model_fields}
    payload = MapObjectUpdate(**{
        k: v for k, v in body.items() if k in MapObjectUpdate.model_fields
    })

    db_obj = db.query(MapObject).filter(MapObject.id == object_id).first()

    patch = payload.model_dump(exclude_unset=True, exclude_none=False)
    patch = {k: v for k, v in patch.items() if k not in {"user", "comment"}}

    # F2-01: primero el candado, después escribir, y todo en una sola
    # transacción — un edit rechazado no puede dejar media escritura atrás.
    _chequear_candado(db_obj, patch)
    # F2-02: foto del objeto antes de que el bloque de abajo le cambie el
    # radio o el azimuth, para que ese cambio también tenga su diff.
    before_obj = svc._snapshot(db_obj)

    try:
        if rf_patch and db_obj.rf_source is None:
            from app.models.rf import RFSource

            db.add(RFSource(object_id=object_id, **rf_patch))
        elif rf_patch:
            before = {c.name: getattr(db_obj.rf_source, c.name)
                      for c in db_obj.rf_source.__table__.columns}
            for field, value in rf_patch.items():
                setattr(db_obj.rf_source, field, value)
            svc.record_typed_history(
                db, db_obj, db_obj.rf_source, "rf", before, before_obj,
                comment=payload.comment, user=payload.user,
            )
        if patch:
            # `update_object` hace el único `commit` de este camino: el
            # satélite pendiente viaja en la misma transacción.
            svc.update_object(
                db, object_id, patch, user=payload.user, comment=payload.comment
            )
        else:
            db.commit()
    except svc.MapServiceError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return _to_leaflet(svc.get_object(db, object_id))


# ─── Antennas (spec §33) ─────────────────────────────────────────────────────

@router.get("/antennas")
def list_antennas(
    expediente_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(MapObject).filter(MapObject.type == TYPE_ANTENNA)
    if expediente_id is not None:
        q = q.filter(MapObject.expediente_id == expediente_id)
    if status:
        q = q.filter(MapObject.status == status)
    rows = q.order_by(MapObject.id).all()
    return {"count": len(rows), "antennas": [_to_leaflet(o) for o in rows]}


@router.post("/antennas", status_code=status.HTTP_201_CREATED)
def create_antenna(body: dict = Body(...), db: Session = Depends(get_db)):
    payload = _coerce(MapObjectCreate, {**body, "type": TYPE_ANTENNA}, default_antenna=True)
    data = payload.model_dump()
    try:
        obj = svc.create_object(
            db, TYPE_ANTENNA,
            name=data["name"], description=data["description"],
            category=data["category"], status=data["status"],
            latitude=data["latitude"], longitude=data["longitude"],
            azimuth=data["azimuth"],
            layer_id=data["layer_id"], layer_key=data["layer_key"],
            visible=data["visible"], locked=data["locked"],
            z_index=data["z_index"], expediente_id=data["expediente_id"],
            color=data["color"], icon=data["icon"], label=data["label"],
            source=data["source"], created_by=data["created_by"],
            properties=data["properties"],
            user=data["user"], comment=data["comment"], notes=data["notes"],
            antenna=data["antenna"] or None,
        )
    except svc.MapServiceError as exc:
        raise HTTPException(400, str(exc))
    return _to_leaflet(obj)


@router.get("/antennas/{object_id}")
def get_antenna(object_id: int, db: Session = Depends(get_db)):
    obj = svc.get_object(db, object_id)
    if obj is None or obj.type != TYPE_ANTENNA:
        raise _not_found(object_id)
    return _to_leaflet(obj)


@router.put("/antennas/{object_id}")
def update_antenna(
    object_id: int, body: dict = Body(...), db: Session = Depends(get_db)
):
    obj = svc.get_object(db, object_id)
    if obj is None or obj.type != TYPE_ANTENNA:
        raise _not_found(object_id)

    antenna_patch = {k: v for k, v in body.items() if k in AntennaPayload.model_fields}
    payload = MapObjectUpdate(**{
        k: v for k, v in body.items() if k in MapObjectUpdate.model_fields
    })

    db_obj = db.query(MapObject).filter(MapObject.id == object_id).first()

    patch = payload.model_dump(exclude_unset=True, exclude_none=False)
    patch = {k: v for k, v in patch.items() if k not in {"user", "comment"}}

    # F2-01: candado primero, una sola transacción para todo el resto.
    _chequear_candado(db_obj, patch)
    # F2-02: foto del objeto antes de que le cambien el azimuth.
    before_obj = svc._snapshot(db_obj)

    try:
        if antenna_patch and db_obj.antenna is None:
            from app.models.rf import Antenna

            db.add(Antenna(object_id=object_id, **antenna_patch))
        elif antenna_patch:
            before = {c.name: getattr(db_obj.antenna, c.name)
                      for c in db_obj.antenna.__table__.columns}
            for field, value in antenna_patch.items():
                setattr(db_obj.antenna, field, value)
            # Keep the object's own azimuth in step so the radial line the map
            # draws always matches the antenna's recorded pointing direction.
            if db_obj.antenna.azimuth_deg is not None:
                db_obj.azimuth = db_obj.antenna.azimuth_deg
            svc.record_typed_history(
                db, db_obj, db_obj.antenna, "antenna", before, before_obj,
                comment=payload.comment, user=payload.user,
            )
        if patch:
            svc.update_object(
                db, object_id, patch, user=payload.user, comment=payload.comment
            )
        else:
            db.commit()
    except svc.MapServiceError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return _to_leaflet(svc.get_object(db, object_id))


# ─── RF events (spec §34) ────────────────────────────────────────────────────

@router.get("/rf/events")
def list_events(
    expediente_id: Optional[int] = None,
    status: Optional[str] = None,
    classification: Optional[str] = None,
    frequency_min: Optional[float] = None,
    frequency_max: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List RF events, filterable by frequency band and date."""
    from sqlalchemy import and_

    from app.models.rf import RFEvent

    q = db.query(MapObject).join(RFEvent, RFEvent.object_id == MapObject.id)
    if expediente_id is not None:
        q = q.filter(MapObject.expediente_id == expediente_id)
    if status:
        q = q.filter(MapObject.status == status)
    if classification:
        q = q.filter(RFEvent.classification == classification)
    if frequency_min is not None:
        q = q.filter(RFEvent.frequency_mhz >= frequency_min)
    if frequency_max is not None:
        q = q.filter(RFEvent.frequency_mhz <= frequency_max)

    conditions = []
    if date_from:
        conditions.append(
            func.coalesce(RFEvent.event_at, MapObject.observed_at) >= date_from
        )
    if date_to:
        conditions.append(
            func.coalesce(RFEvent.event_at, MapObject.observed_at) <= date_to
        )
    if conditions:
        q = q.filter(and_(*conditions))

    rows = q.order_by(MapObject.id).all()
    return {"count": len(rows), "events": [_to_leaflet(o) for o in rows]}


@router.post("/rf/events", status_code=status.HTTP_201_CREATED)
def create_event(body: dict = Body(...), db: Session = Depends(get_db)):
    payload = _coerce(MapObjectCreate, {**body, "type": TYPE_RF_EVENT}, default_event=True)
    data = payload.model_dump()
    try:
        obj = svc.create_object(
            db, TYPE_RF_EVENT,
            name=data["name"], description=data["description"],
            category=data["category"], status=data["status"],
            latitude=data["latitude"], longitude=data["longitude"],
            layer_id=data["layer_id"], layer_key=data["layer_key"],
            visible=data["visible"], locked=data["locked"],
            z_index=data["z_index"], expediente_id=data["expediente_id"],
            observed_at=data["observed_at"],
            color=data["color"], icon=data["icon"], label=data["label"],
            source=data["source"], created_by=data["created_by"],
            properties=data["properties"],
            user=data["user"], comment=data["comment"], notes=data["notes"],
            event=data["event"] or None,
        )
    except svc.MapServiceError as exc:
        raise HTTPException(400, str(exc))
    return _to_leaflet(obj)


@router.get("/rf/events/{object_id}")
def get_event(object_id: int, db: Session = Depends(get_db)):
    obj = svc.get_object(db, object_id)
    if obj is None or obj.type != TYPE_RF_EVENT:
        raise _not_found(object_id)
    return _to_leaflet(obj)


@router.put("/rf/events/{object_id}")
def update_event(
    object_id: int, body: dict = Body(...), db: Session = Depends(get_db)
):
    obj = svc.get_object(db, object_id)
    if obj is None or obj.type != TYPE_RF_EVENT:
        raise _not_found(object_id)

    payload = MapObjectUpdate(**{
        k: v for k, v in body.items() if k in MapObjectUpdate.model_fields
    })

    db_obj = db.query(MapObject).filter(MapObject.id == object_id).first()
    event_patch = {k: v for k, v in body.items() if k in RFEventPayload.model_fields}

    patch = payload.model_dump(exclude_unset=True, exclude_none=False)
    patch = {k: v for k, v in patch.items() if k not in {"user", "comment"}}

    # F2-01: candado primero, una sola transacción para todo el resto.
    _chequear_candado(db_obj, patch)
    # F2-02: foto del objeto antes de que el bloque de abajo escriba.
    before_obj = svc._snapshot(db_obj)

    try:
        if event_patch:
            from app.models.rf import RFEvent

            existing = db.query(RFEvent).filter(
                RFEvent.object_id == object_id
            ).first()
            if existing is None:
                db.add(RFEvent(object_id=object_id, **event_patch))
            else:
                before = {c.name: getattr(existing, c.name)
                          for c in existing.__table__.columns}
                for field, value in event_patch.items():
                    setattr(existing, field, value)
                svc.record_typed_history(
                    db, db_obj, existing, "event", before, before_obj,
                    comment=payload.comment, user=payload.user,
                )
        if patch:
            svc.update_object(
                db, object_id, patch, user=payload.user, comment=payload.comment
            )
        else:
            db.commit()
    except svc.MapServiceError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return _to_leaflet(svc.get_object(db, object_id))


# ─── Reference points (spec §31) ─────────────────────────────────────────────

@router.get("/references")
def list_references(
    expediente_id: Optional[int] = None, db: Session = Depends(get_db)
):
    q = db.query(MapObject).filter(MapObject.type == TYPE_REFERENCE)
    if expediente_id is not None:
        q = q.filter(MapObject.expediente_id == expediente_id)
    rows = q.order_by(MapObject.id).all()
    return {"count": len(rows), "references": [_to_leaflet(o) for o in rows]}


@router.post("/references", status_code=status.HTTP_201_CREATED)
def create_reference(body: dict = Body(...), db: Session = Depends(get_db)):
    payload = _coerce(
        MapObjectCreate, {**body, "type": TYPE_REFERENCE}, default_reference=True
    )
    data = payload.model_dump()
    try:
        obj = svc.create_object(
            db, TYPE_REFERENCE,
            name=data["name"], description=data["description"],
            category=data["category"], status=data["status"],
            latitude=data["latitude"], longitude=data["longitude"],
            radius=data["radius"], radius_unit=data["radius_unit"],
            layer_id=data["layer_id"], layer_key=data["layer_key"],
            visible=data["visible"], locked=data["locked"],
            z_index=data["z_index"], expediente_id=data["expediente_id"],
            color=data["color"], icon=data["icon"], label=data["label"],
            source=data["source"], created_by=data["created_by"],
            properties=data["properties"],
            user=data["user"], comment=data["comment"], notes=data["notes"],
            reference=data["reference"] or None,
        )
    except svc.MapServiceError as exc:
        raise HTTPException(400, str(exc))
    return _to_leaflet(obj)


@router.get("/references/{object_id}")
def get_reference(object_id: int, db: Session = Depends(get_db)):
    obj = svc.get_object(db, object_id)
    if obj is None or obj.type != TYPE_REFERENCE:
        raise _not_found(object_id)
    return _to_leaflet(obj)


@router.put("/references/{object_id}")
def update_reference(
    object_id: int, body: dict = Body(...), db: Session = Depends(get_db)
):
    obj = svc.get_object(db, object_id)
    if obj is None or obj.type != TYPE_REFERENCE:
        raise _not_found(object_id)

    ref_patch = {k: v for k, v in body.items() if k in ReferencePayload.model_fields}
    payload = MapObjectUpdate(**{
        k: v for k, v in body.items() if k in MapObjectUpdate.model_fields
    })

    db_obj = db.query(MapObject).filter(MapObject.id == object_id).first()
    from app.models.rf import ReferencePoint

    existing = db.query(ReferencePoint).filter(
        ReferencePoint.object_id == object_id
    ).first()

    patch = payload.model_dump(exclude_unset=True, exclude_none=False)
    patch = {k: v for k, v in patch.items() if k not in {"user", "comment"}}

    # F2-01: candado primero, una sola transacción para todo el resto.
    _chequear_candado(db_obj, patch)
    # F2-02: foto del objeto antes de que le copien el radio.
    before_obj = svc._snapshot(db_obj)

    try:
        if ref_patch and existing is None:
            db.add(ReferencePoint(object_id=object_id, **ref_patch))
        elif ref_patch:
            before = {c.name: getattr(existing, c.name)
                      for c in existing.__table__.columns}
            for field, value in ref_patch.items():
                setattr(existing, field, value)
            if ref_patch.get("radius") is not None and db_obj.radius is None:
                db_obj.radius = ref_patch["radius"]
            svc.record_typed_history(
                db, db_obj, existing, "reference", before, before_obj,
                comment=payload.comment, user=payload.user,
            )
        if patch:
            svc.update_object(
                db, object_id, patch, user=payload.user, comment=payload.comment
            )
        else:
            db.commit()
    except svc.MapServiceError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return _to_leaflet(svc.get_object(db, object_id))


# ─── Summary ─────────────────────────────────────────────────────────────────

@router.get("/rf/summary")
def rf_summary(expediente_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Counts and frequency summary across the RF domain."""
    from app.models.rf import Antenna, RFEvent, RFSource

    def _count(model, extra=None):
        q = db.query(func.count(func.coalesce(model.object_id, model.id)))
        if expediente_id is not None:
            q = q.join(MapObject, MapObject.id == model.object_id).filter(
                MapObject.expediente_id == expediente_id
            )
        return q.scalar() or 0

    sources = (
        db.query(RFSource.kind, func.count(RFSource.id))
        .join(MapObject, MapObject.id == RFSource.object_id)
        .filter(
            MapObject.expediente_id == expediente_id
            if expediente_id is not None
            else MapObject.id.isnot(None)
        )
        .group_by(RFSource.kind)
        .all()
    )
    events = (
        db.query(RFEvent.classification, func.count(RFEvent.id))
        .join(MapObject, MapObject.id == RFEvent.object_id)
        .filter(
            MapObject.expediente_id == expediente_id
            if expediente_id is not None
            else MapObject.id.isnot(None)
        )
        .group_by(RFEvent.classification)
        .all()
    )
    freqs = [
        f for (f,) in db.query(RFEvent.frequency_mhz).filter(
            RFEvent.frequency_mhz.isnot(None)
        ).all()
    ]

    return {
        "expediente_id": expediente_id,
        "sources_total": _count(RFSource),
        "antennas_total": _count(Antenna),
        "events_total": _count(RFEvent),
        "sources_by_kind": {k: n for k, n in sources if k},
        "events_by_classification": {k: n for k, n in events if k},
        "event_frequencies": {
            "count": len(freqs),
            "min_mhz": min(freqs) if freqs else None,
            "max_mhz": max(freqs) if freqs else None,
            "mean_mhz": (sum(freqs) / len(freqs)) if freqs else None,
        },
    }


# ─── Internal helpers ────────────────────────────────────────────────────────

def _loaders():
    """Eager-load the satellite rows for the object types served here."""
    from sqlalchemy.orm import selectinload

    return (
        selectinload(MapObject.layer),
        selectinload(MapObject.rf_source),
        selectinload(MapObject.antenna),
        selectinload(MapObject.reference),
        selectinload(MapObject.measurement),
        selectinload(MapObject.rf_event),
    )


def _coerce(model, data: dict, **defaults):
    """Build a `MapObjectCreate` from a flat or nested body.

    Field use produces flat bodies (``{"latitude": …, "frequency_mhz": …}``)
    while the API docs show nested ones. Both are accepted so the operator
    is not forced to remember which shape a particular form uses.
    """
    body = dict(data)

    # Lift flat payload fields into their nested block — but only the
    # block that matches this endpoint's object type. Lifting every block
    # would move an antenna's `kind` ("Direccional") into the RF block and
    # fail validation against the RF vocabulary.
    block_for_type = {
        TYPE_RF_SOURCE: ("rf", RFSourcePayload),
        TYPE_ANTENNA: ("antenna", AntennaPayload),
        TYPE_REFERENCE: ("reference", ReferencePayload),
        TYPE_RF_EVENT: ("event", RFEventPayload),
    }
    target = body.get("type")
    block, payload_model = block_for_type.get(target, (None, None))

    if block is not None:
        fields = payload_model.model_fields
        if body.get(block) is None:
            flat = {k: body.pop(k) for k in list(body) if k in fields}
            if flat:
                body[block] = flat
        else:
            # An explicit nested block wins; fold in any flat leftovers.
            for k in list(body):
                if k in fields and k not in body[block]:
                    body[block][k] = body.pop(k)

    # A reference's radius may legitimately arrive top-level.
    if target == TYPE_REFERENCE and body.get("radius") is not None:
        block_body = body.setdefault("reference", {})
        block_body.setdefault("radius", body["radius"])
        if body.get("radius_unit"):
            block_body.setdefault("radius_unit", body["radius_unit"])

    # An antenna's pointing direction also drives the object's radial.
    ant = body.get("antenna") or {}
    if ant.get("azimuth_deg") is not None and body.get("azimuth") is None:
        body["azimuth"] = ant["azimuth_deg"]

    return model(**body)
