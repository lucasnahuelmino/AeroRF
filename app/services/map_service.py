"""
services/map_service.py
──────────────────────
CRUD, history and notes for `MapObject` (spec §8, §14, §15, §40, §41).

Single write path for every spatial object. Circles, radials, sources,
antennas and events all funnel through here, so the rules that protect
the investigation record are enforced in exactly one place:

* **Every field change is diffed into `object_history`.** A status going
  ACTIVA → APAGADA → REACTIVADA produces three history rows and the
  previous values are never lost.
* **Notes are append-only.** ``add_note`` refuses to update; there is no
  update method by design.
* **Destructive operations require an explicit flag.** Bulk operations
  such as "clear layer" pass ``cascade=True``, because losing a whole
  investigation because of a mis-click is the failure mode that matters.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.geo import (
    circle_points,
    destination_point,
    haversine_m,
    path_summary,
    valid_latlon,
)
from app.core.logging import object_log
from app.core.units import UNIT_NM, normalise_unit, to_metres
from app.models.constants import (
    LAYER_BY_OBJECT_TYPE,
    OBJECT_STATES,
    OBJECT_TYPES,
    PROVENANCE_USER,
    STATE_ACTIVE,
    TYPE_ANTENNA,
    TYPE_CIRCLE,
    TYPE_COVERAGE,
    TYPE_MEASUREMENT,
    TYPE_RADIAL,
    TYPE_REFERENCE,
    TYPE_RF_EVENT,
    TYPE_RF_SOURCE,
)
from app.models.layer import Layer
from app.models.map_object import MapObject
from app.models.measurement import Measurement
from app.models.rf import RFEvent, RFSource, Antenna, ReferencePoint
from app.models.tracking import Annotation, ObjectHistory, ObjectNote

from app.services import geojson_service as gjs

#: Fields excluded from history diffing: audit metadata and relationship
#: plumbing that changes on every save and would drown the real history.
_HISTORY_SKIP = {
    "fecha_creacion",
    "fecha_actualizacion",
    "id",
}

#: Same idea for a type-specific satellite: its own identity columns (`id`,
#: `object_id`) are plumbing, not values the operator edits. Handing those to
#: the generic diff is what produced rows saying the parent link had been
#: deleted (F2-02).
_SATELLITE_SKIP = _HISTORY_SKIP | {"object_id"}


class MapServiceError(ValueError):
    """Invalid object payload."""


# ─── Serialisation helpers ───────────────────────────────────────────────────

def _scalar(value: Any) -> Optional[str]:
    """Render a value as a history-safe string."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    return str(value)


def _mismo_valor(old: Any, new: Any, old_s: str, new_s: str) -> bool:
    """True when the value did not really change.

    Comparing the rendered strings alone is not enough: `25.0` and `25`
    render differently but are the same number, so re-sending an integer for
    a decimal column would write a history row claiming a change that never
    happened. `old_s`/`new_s` are the pre-rendered strings (they are what
    history stores, so rendering them twice would be waste).
    """
    if old_s == new_s:
        return True
    if (
        isinstance(old, (int, float)) and not isinstance(old, bool)
        and isinstance(new, (int, float)) and not isinstance(new, bool)
    ):
        return float(old) == float(new)
    return False


def _record_history(
    db: Session,
    obj: MapObject,
    before: dict[str, Any],
    comment: str | None = None,
    user: str | None = None,
) -> list[ObjectHistory]:
    """Diff ``before`` against the current state and append history rows."""
    rows: list[ObjectHistory] = []
    for field, old in before.items():
        if field in _HISTORY_SKIP:
            continue
        new = getattr(obj, field, None)
        old_s, new_s = _scalar(old), _scalar(new)
        if _mismo_valor(old, new, old_s, new_s):
            continue
        row = ObjectHistory(
            object_id=obj.id,
            field=field,
            old_value=old_s,
            new_value=new_s,
            comment=comment,
            user=user,
        )
        db.add(row)
        rows.append(row)
    return rows


def record_typed_history(
    db: Session,
    obj: MapObject,
    satellite,
    prefix: str,
    before_satellite: dict[str, Any],
    before_object: dict[str, Any],
    comment: str | None = None,
    user: str | None = None,
) -> list[ObjectHistory]:
    """Diff a type-specific satellite **and** its parent object (F2-02).

    Both diffs are here for one reason: both are changes the operator caused,
    and only one of them was being recorded correctly.

    The satellite one compares its **own** snapshot against itself. The
    generic `_record_history` was being handed `{"rf.power_dbm": 40}` and then
    did `getattr(obj, "rf.power_dbm")` over the *MapObject*, which carries no
    such attribute — so every field came back `None`: the history claimed the
    frequency and the kind had been deleted, while the real change (40 → 41)
    went unrecorded.

    `before_object` covers the parent's own edits made in the same breath:
    `update_antenna` copies `azimuth_deg` onto the object and
    `update_reference` may copy `radius`, and neither used to reach a diff.
    """
    rows: list[ObjectHistory] = []

    for field, old in before_satellite.items():
        if field in _SATELLITE_SKIP:
            continue
        new = getattr(satellite, field, None) if satellite is not None else None
        old_s, new_s = _scalar(old), _scalar(new)
        if _mismo_valor(old, new, old_s, new_s):
            continue
        row = ObjectHistory(
            object_id=obj.id,
            field=f"{prefix}.{field}",
            old_value=old_s,
            new_value=new_s,
            comment=comment,
            user=user,
        )
        db.add(row)
        rows.append(row)

    rows.extend(_record_history(db, obj, before_object, comment=comment, user=user))
    return rows


def _snapshot(obj: MapObject) -> dict[str, Any]:
    return {c.name: getattr(obj, c.name, None) for c in obj.__table__.columns}


# ─── Validation ──────────────────────────────────────────────────────────────

def validate_type(object_type: str) -> str:
    t = (object_type or "").strip().lower()
    if t not in OBJECT_TYPES:
        raise MapServiceError(
            f"Unknown object type {object_type!r}. Valid types: {', '.join(OBJECT_TYPES)}"
        )
    return t


def validate_status(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    s = str(status).strip()
    if s not in OBJECT_STATES:
        raise MapServiceError(
            f"Unknown status {status!r}. Valid states: {', '.join(OBJECT_STATES)}"
        )
    return s


# ─── Create ──────────────────────────────────────────────────────────────────

def create_object(
    db: Session,
    object_type: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius: Optional[float] = None,
    radius_unit: Optional[str] = None,
    azimuth: Optional[float] = None,
    length_value: Optional[float] = None,
    length_unit: Optional[str] = None,
    geometry: Optional[dict] = None,
    geometry_type: Optional[str] = None,
    color: Optional[str] = None,
    icon: Optional[str] = None,
    label: Optional[str] = None,
    opacity: Optional[float] = None,
    weight: Optional[float] = None,
    fill_opacity: Optional[float] = None,
    layer_id: Optional[int] = None,
    layer_key: Optional[str] = None,
    visible: bool = True,
    locked: bool = False,
    z_index: int = 0,
    expediente_id: Optional[int] = None,
    observed_at: Optional[datetime] = None,
    valid_from: Optional[datetime] = None,
    valid_to: Optional[datetime] = None,
    source: str = PROVENANCE_USER,
    created_by: Optional[str] = None,
    properties: Optional[dict] = None,
    user: Optional[str] = None,
    comment: Optional[str] = None,
    # type-specific payloads
    rf: Optional[dict] = None,
    antenna: Optional[dict] = None,
    reference: Optional[dict] = None,
    measurement: Optional[dict] = None,
    event: Optional[dict] = None,
    notes: Optional[Iterable[str]] = None,
) -> MapObject:
    """Create one map object with its type-specific payload and history."""
    otype = validate_type(object_type)

    if latitude is not None and longitude is not None:
        if not valid_latlon(latitude, longitude):
            raise MapServiceError(
                f"Invalid WGS84 coordinate: lat={latitude}, lon={longitude}"
            )

    # Normalise units once, at the edge, so the database only ever holds
    # canonical ids.
    radius_unit_c = normalise_unit(radius_unit) if radius_unit else UNIT_NM
    length_unit_c = normalise_unit(length_unit) if length_unit else UNIT_NM

    # Reject a malformed geometry here rather than storing it. Reading a
    # geometry assumes it is well formed, so one bad ring used to be stored
    # happily and then took down the whole listing endpoint with a 500.
    if geometry is not None:
        try:
            gjs.validate_geometry(geometry)
        except gjs.GeometryError as exc:
            raise MapServiceError(str(exc)) from exc

    obj = MapObject(
        type=otype,
        name=name,
        description=description,
        category=category,
        status=validate_status(status) or STATE_ACTIVE,
        latitude=latitude,
        longitude=longitude,
        radius=radius,
        radius_unit=radius_unit_c,
        azimuth=azimuth,
        length_value=length_value,
        length_unit=length_unit_c,
        geometry=geometry,
        geometry_type=geometry_type,
        color=color,
        icon=icon,
        label=label,
        opacity=opacity,
        weight=weight,
        fill_opacity=fill_opacity,
        layer_id=_resolve_layer_id(db, layer_id, layer_key, otype),
        visible=visible,
        locked=locked,
        z_index=z_index,
        expediente_id=expediente_id,
        observed_at=observed_at,
        valid_from=valid_from,
        valid_to=valid_to,
        source=source,
        created_by=created_by,
        properties=properties or {},
    )
    obj.apply_defaults()
    db.add(obj)
    db.flush()  # assign obj.id

    _attach_payloads(db, obj, otype, rf, antenna, reference, measurement, event)

    # Creation is itself a history event, so the object's first state is
    # reconstructable from the audit log alone.
    db.add(
        ObjectHistory(
            object_id=obj.id,
            field="__created__",
            old_value=None,
            new_value=otype,
            comment=comment or "Objeto creado",
            user=user or created_by,
        )
    )

    for text in (notes or []):
        db.add(ObjectNote(object_id=obj.id, text=text, user=user or created_by))

    db.commit()
    db.refresh(obj)

    object_log.info(
        "object.created",
        f"{otype} created",
        object_id=obj.id,
        type=otype,
        name=name,
        layer=obj.layer.key if obj.layer else None,
        expediente_id=expediente_id,
        user=user or created_by,
    )
    return obj


def _resolve_layer_id(
    db: Session,
    layer_id: Optional[int],
    layer_key: Optional[str],
    otype: str,
) -> Optional[int]:
    if layer_id is not None:
        return layer_id
    if layer_key:
        layer = db.query(Layer).filter(Layer.key == layer_key).first()
        return layer.id if layer else None
    target = LAYER_BY_OBJECT_TYPE.get(otype)
    if target:
        layer = db.query(Layer).filter(Layer.key == target).first()
        return layer.id if layer else None
    return None


def _attach_payloads(
    db: Session,
    obj: MapObject,
    otype: str,
    rf: Optional[dict],
    antenna: Optional[dict],
    reference: Optional[dict],
    measurement: Optional[dict],
    event: Optional[dict],
) -> None:
    """Attach the satellite row appropriate to this object type."""
    if otype == TYPE_RF_SOURCE and rf:
        payload = dict(rf)
        payload.pop("id", None)
        payload.pop("object_id", None)
        db.add(RFSource(object_id=obj.id, **payload))

    elif otype == TYPE_ANTENNA and antenna:
        payload = dict(antenna)
        payload.pop("id", None)
        payload.pop("object_id", None)
        # An antenna's pointing direction doubles as the object's radial.
        if payload.get("azimuth_deg") is not None and obj.azimuth is None:
            obj.azimuth = payload["azimuth_deg"]
        db.add(Antenna(object_id=obj.id, **payload))

    elif otype == TYPE_REFERENCE and reference:
        payload = dict(reference)
        payload.pop("id", None)
        payload.pop("object_id", None)
        if payload.get("radius") is not None:
            if obj.radius is None:
                obj.radius = payload["radius"]
            if payload.get("radius_unit"):
                obj.radius_unit = normalise_unit(payload["radius_unit"])
        db.add(ReferencePoint(object_id=obj.id, **payload))

    elif otype == TYPE_MEASUREMENT and measurement:
        payload = dict(measurement)
        payload.pop("id", None)
        payload.pop("object_id", None)
        db.add(Measurement(object_id=obj.id, **payload))

    if otype == TYPE_RF_EVENT and event:
        payload = dict(event)
        payload.pop("id", None)
        payload.pop("object_id", None)
        db.add(RFEvent(object_id=obj.id, **payload))


# ─── Read ────────────────────────────────────────────────────────────────────

#: SQLite stores INTEGER as at most 8 bytes. An id outside that range cannot
#: exist, and passing one straight to the driver raises OverflowError, which
#: reached the client as a 500. An id that cannot exist is a client error, not
#: a server fault: the answer is 404, the same as any other missing id.
MAX_SQLITE_INT = 2**63 - 1
MIN_SQLITE_INT = -(2**63)


def _is_storable_id(value: Any) -> bool:
    """Whether an id can exist at all.

    SQLite stores INTEGER in at most 8 bytes, so anything outside 2**63-1
    cannot be a row. `bool` is excluded on purpose: it is an `int` subclass in
    Python, and `True` as an id means the client sent a flag, not an id.
    """
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and MIN_SQLITE_INT <= value <= MAX_SQLITE_INT
    )


def _find_by_id(db: Session, object_id: int) -> Optional[MapObject]:
    """Fetch one object, tolerating an id that cannot exist.

    Every id-based lookup goes through here. Four of the five call sites that
    filtered by id directly each had the same OverflowError bug; the
    alternative to this helper is five places to remember the same guard, and
    one of them would eventually be missed.
    """
    if not _is_storable_id(object_id):
        return None
    return db.query(MapObject).filter(MapObject.id == object_id).first()


def get_object(db: Session, object_id: int) -> Optional[MapObject]:
    if not _is_storable_id(object_id):
        return None
    return (
        db.query(MapObject)
        .options(
            selectinload(MapObject.layer),
            selectinload(MapObject.notes),
            selectinload(MapObject.rf_source),
            selectinload(MapObject.antenna),
            selectinload(MapObject.reference),
            selectinload(MapObject.measurement),
        )
        .filter(MapObject.id == object_id)
        .first()
    )


def list_objects(
    db: Session,
    types: Optional[Iterable[str]] = None,
    layer_id: Optional[int] = None,
    layer_key: Optional[str] = None,
    expediente_id: Optional[int] = None,
    status: Optional[str] = None,
    visible: Optional[bool] = None,
    bbox: Optional[tuple[float, float, float, float]] = None,
    search: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
) -> list[MapObject]:
    """Filtered listing used by the map's initial load and the inspector."""
    q = db.query(MapObject).options(
        selectinload(MapObject.layer),
        selectinload(MapObject.rf_source),
        selectinload(MapObject.antenna),
        selectinload(MapObject.reference),
        selectinload(MapObject.measurement),
    )

    if types:
        wanted = [validate_type(t) for t in types]
        q = q.filter(MapObject.type.in_(wanted))
    if layer_id is not None:
        q = q.filter(MapObject.layer_id == layer_id)
    if layer_key:
        q = q.join(Layer, MapObject.layer_id == Layer.id).filter(Layer.key == layer_key)
    if expediente_id is not None:
        q = q.filter(MapObject.expediente_id == expediente_id)
    if status:
        q = q.filter(MapObject.status == validate_status(status))
    if visible is not None:
        q = q.filter(MapObject.visible == visible)

    if bbox is not None:
        lat_min, lon_min, lat_max, lon_max = bbox
        q = q.filter(
            MapObject.latitude.isnot(None),
            MapObject.longitude.isnot(None),
            MapObject.latitude >= lat_min,
            MapObject.latitude <= lat_max,
            MapObject.longitude >= lon_min,
            MapObject.longitude <= lon_max,
        )

    if search:
        pattern = f"%{search.strip()}%"
        q = q.filter(
            or_(
                MapObject.name.ilike(pattern),
                MapObject.description.ilike(pattern),
                MapObject.category.ilike(pattern),
                MapObject.label.ilike(pattern),
            )
        )

    q = q.order_by(MapObject.z_index, MapObject.id)
    return q.limit(max(1, min(limit, 5000))).offset(max(0, offset)).all()


# ─── Update (spec §8, §40) ───────────────────────────────────────────────────

#: Fields an update may touch. Anything else is ignored rather than
#: silently written, which keeps a malformed request from corrupting a row.
MUTABLE_FIELDS = {
    "name", "description", "category", "status", "latitude", "longitude",
    "radius", "radius_unit", "azimuth", "length_value", "length_unit",
    "geometry", "geometry_type", "color", "icon", "label", "opacity",
    "weight", "fill_opacity", "layer_id", "visible", "locked", "z_index",
    "expediente_id", "observed_at", "valid_from", "valid_to", "properties",
    "show_label",
}

_UNIT_FIELDS = {"radius_unit", "length_unit"}


def require_unlocked(obj: MapObject, patch: dict[str, Any]) -> None:
    """Raise unless ``patch`` may touch a locked object.

    A locked object refuses every edit *except* unlocking itself — otherwise
    it could never be reopened, which would make the lock a one-way trap.

    It lives here, outside `update_object`, because the gate has to run
    **before** anything is written: the four RF views used to write their
    satellite and commit it first, and only then reach `update_object`
    (F2-01) — a locked object's frequency could be edited by a body that
    carried nothing but RF fields.
    """
    if obj.locked and not (set(patch) == {"locked"} and patch["locked"] is False):
        raise MapServiceError(
            f"El objeto {obj.id} está bloqueado. Desbloquéalo antes de editar."
        )


def update_object(
    db: Session,
    object_id: int,
    patch: dict[str, Any],
    user: Optional[str] = None,
    comment: Optional[str] = None,
) -> MapObject:
    """Apply a partial update, recording every changed field in history."""
    obj = get_object(db, object_id)
    if obj is None:
        raise MapServiceError(f"Object {object_id} not found")

    before = _snapshot(obj)
    unknown = set(patch) - MUTABLE_FIELDS
    if unknown:
        raise MapServiceError(
            f"Unknown field(s): {', '.join(sorted(unknown))}. "
            f"Editable: {', '.join(sorted(MUTABLE_FIELDS))}"
        )

    require_unlocked(obj, patch)

    for field, value in patch.items():
        if value is None and field not in {"description", "label", "name"}:
            # A null for a scalar column would violate NOT NULL defaults.
            if field in {"radius", "azimuth", "length_value", "expediente_id"}:
                setattr(obj, field, None)
                continue
        if field == "status":
            value = validate_status(value)
        if field in _UNIT_FIELDS and value is not None:
            value = normalise_unit(value)
        if field in {"latitude", "longitude"}:
            lat = value if field == "latitude" else obj.latitude
            lon = value if field == "longitude" else obj.longitude
            if lat is not None and lon is not None and not valid_latlon(lat, lon):
                raise MapServiceError(
                    f"Invalid WGS84 coordinate: lat={lat}, lon={lon}"
                )
        setattr(obj, field, value)

    _record_history(db, obj, before, comment=comment, user=user)

    db.commit()
    db.refresh(obj)

    changed = [
        r.field for r in obj.history[-20:] if r.changed_at and r.field != "__created__"
    ]
    object_log.info(
        "object.updated",
        f"{obj.type} updated",
        object_id=obj.id,
        fields=",".join(sorted(set(changed))) or None,
        user=user,
    )
    return obj


def set_status(
    db: Session,
    object_id: int,
    status: str,
    user: Optional[str] = None,
    comment: Optional[str] = None,
) -> MapObject:
    """Change an object's state. The transition is always historised."""
    return update_object(
        db, object_id, {"status": status}, user=user,
        comment=comment or f"Estado cambiado a {status}",
    )


def move_object(
    db: Session,
    object_id: int,
    latitude: float,
    longitude: float,
    user: Optional[str] = None,
) -> MapObject:
    """Reposition an object (drag on the map)."""
    if not valid_latlon(latitude, longitude):
        raise MapServiceError(f"Invalid WGS84 coordinate: {latitude}, {longitude}")
    return update_object(
        db, object_id,
        {"latitude": latitude, "longitude": longitude},
        user=user, comment="Objeto movido",
    )


def duplicate_object(
    db: Session,
    object_id: int,
    name_suffix: str = "(copia)",
    offset_lat: float = 0.0,
    offset_lon: float = 0.0,
    user: Optional[str] = None,
) -> MapObject:
    """Copy an object, optionally offset so both are visible (spec §8)."""
    src = get_object(db, object_id)
    if src is None:
        raise MapServiceError(f"Object {object_id} not found")

    new_props = dict(src.properties or {})
    # Copy vertex-level shapes so the duplicate is independent.
    for key in ("path", "ring"):
        if key in new_props and new_props[key]:
            new_props[key] = list(new_props[key])

    new_obj = create_object(
        db,
        src.type,
        name=f"{src.name} {name_suffix}" if src.name else name_suffix,
        description=src.description,
        category=src.category,
        status=src.status,
        latitude=(src.latitude + offset_lat) if src.latitude is not None else None,
        longitude=(src.longitude + offset_lon) if src.longitude is not None else None,
        radius=src.radius,
        radius_unit=src.radius_unit,
        azimuth=src.azimuth,
        length_value=src.length_value,
        length_unit=src.length_unit,
        geometry=src.geometry,
        geometry_type=src.geometry_type,
        color=src.color,
        icon=src.icon,
        label=src.label,
        opacity=src.opacity,
        weight=src.weight,
        fill_opacity=src.fill_opacity,
        layer_id=src.layer_id,
        visible=src.visible,
        z_index=src.z_index,
        expediente_id=src.expediente_id,
        observed_at=src.observed_at,
        valid_from=src.valid_from,
        valid_to=src.valid_to,
        properties=new_props,
        user=user,
        comment=f"Duplicado del objeto {object_id}",
        rf=_payload_dict(src.rf_source),
        antenna=_payload_dict(src.antenna),
        reference=_payload_dict(src.reference),
        measurement=_payload_dict(src.measurement),
    )
    return new_obj


def _payload_dict(satellite) -> Optional[dict]:
    if satellite is None:
        return None
    return {
        c.name: getattr(satellite, c.name)
        for c in satellite.__table__.columns
        if c.name not in {"id", "object_id"}
    }


# ─── Delete ──────────────────────────────────────────────────────────────────

def delete_object(
    db: Session, object_id: int, cascade: bool = False, user: Optional[str] = None
) -> None:
    """Delete one object, refusing when it still has dependants.

    Notes and history cascade with the object (they cannot exist without
    it). An object referenced by an expediente, or carrying a linked
    flight/track relation, is refused unless ``cascade=True``, so an
    operator cannot quietly destroy part of a case file.
    """
    obj = _find_by_id(db, object_id)
    if obj is None:
        return

    blockers: list[str] = []
    if obj.expediente_id and not cascade:
        blockers.append(f"belongs to expediente {obj.expediente_id}")
    if obj.parent_id and not cascade:
        blockers.append(f"is a child of object {obj.parent_id}")
    if blockers:
        raise MapServiceError(
            f"Object {object_id} cannot be deleted: {'; '.join(blockers)}. "
            "Pass cascade=true to remove it anyway."
        )

    otype = obj.type
    db.delete(obj)
    db.commit()
    object_log.info(
        "object.deleted", f"{otype} deleted",
        object_id=object_id, cascade=cascade, user=user,
    )


def clear_layer(db: Session, layer_id: int, cascade: bool = False) -> int:
    """Remove every object in a layer. Requires ``cascade=True``."""
    if not cascade:
        raise MapServiceError(
            "clear_layer requires cascade=true; it deletes every object in the layer."
        )
    count = db.query(MapObject).filter(MapObject.layer_id == layer_id).delete(
        synchronize_session=False
    )
    db.commit()
    object_log.warning("layer.cleared", "layer cleared", layer_id=layer_id, removed=count)
    return count


# ─── Notes (spec §14) — append only ──────────────────────────────────────────

def add_note(
    db: Session,
    object_id: int,
    text: str,
    user: Optional[str] = None,
) -> ObjectNote:
    """Append a note. There is no update path, by design."""
    if not (text or "").strip():
        raise MapServiceError("A note cannot be empty.")
    if _find_by_id(db, object_id) is None:
        raise MapServiceError(f"Object {object_id} not found")

    note = ObjectNote(object_id=object_id, text=text.strip(), user=user)
    db.add(note)
    db.commit()
    db.refresh(note)
    object_log.info(
        "object.note_added", "note appended",
        object_id=object_id, user=user,
    )
    return note


def list_notes(db: Session, object_id: int) -> list[ObjectNote]:
    return (
        db.query(ObjectNote)
        .filter(ObjectNote.object_id == object_id)
        .order_by(ObjectNote.timestamp)
        .all()
    )


# ─── History (spec §41) ──────────────────────────────────────────────────────

def list_history(
    db: Session,
    object_id: int,
    field: Optional[str] = None,
    limit: int = 500,
) -> list[ObjectHistory]:
    q = db.query(ObjectHistory).filter(ObjectHistory.object_id == object_id)
    if field:
        q = q.filter(ObjectHistory.field == field)
    return q.order_by(ObjectHistory.changed_at, ObjectHistory.id).limit(limit).all()


def get_history(db: Session, object_id: int) -> list[dict]:
    return [
        {
            "id": h.id,
            "object_id": h.object_id,
            "changed_at": h.changed_at,
            "field": h.field,
            "old_value": h.old_value,
            "new_value": h.new_value,
            "comment": h.comment,
            "user": h.user,
        }
        for h in list_history(db, object_id)
    ]


# ─── Annotations ─────────────────────────────────────────────────────────────

def add_annotation(
    db: Session,
    object_id: int,
    text: str,
    author: Optional[str] = None,
    category: Optional[str] = None,
) -> Annotation:
    obj = _find_by_id(db, object_id)
    if obj is None:
        raise MapServiceError(f"Object {object_id} not found")
    ann = Annotation(
        object_id=object_id,
        text=(text or "").strip(),
        author=author,
        category=category,
        latitude=obj.latitude,
        longitude=obj.longitude,
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    return ann


# ─── Spatial queries ─────────────────────────────────────────────────────────

def objects_near(
    db: Session,
    latitude: float,
    longitude: float,
    radius_nm: float,
    types: Optional[Iterable[str]] = None,
    expediente_id: Optional[int] = None,
) -> list[dict]:
    """Objects within ``radius_nm``, sorted by distance.

    A bounding-box pre-filter narrows the SQL set, then exact haversine
    distances are computed in Python. This keeps the query portable
    between SQLite and PostgreSQL without PostGIS, and is accurate to
    well under a metre at these ranges.
    """
    radius_m = to_metres(radius_nm, UNIT_NM)
    # Conservative box: pad the latitude by the angular radius, and scale
    # the longitude by 1/cos(lat) so the box contains the true circle.
    import math

    lat_pad = math.degrees(radius_m / 6_371_008.8)
    cos_lat = math.cos(math.radians(latitude))
    lon_pad = math.degrees(radius_m / (6_371_008.8 * cos_lat)) if abs(cos_lat) > 1e-9 else 180.0

    candidates = list_objects(
        db,
        types=types,
        expediente_id=expediente_id,
        bbox=(
            max(-90.0, latitude - lat_pad),
            longitude - lon_pad,
            min(90.0, latitude + lat_pad),
            longitude + lon_pad,
        ),
        limit=5000,
    )

    out: list[dict] = []
    for obj in candidates:
        if obj.latitude is None or obj.longitude is None:
            continue
        distance_m = haversine_m(latitude, longitude, obj.latitude, obj.longitude)
        if distance_m <= radius_m:
            out.append({"object": obj, "distance_m": distance_m})
    out.sort(key=lambda r: r["distance_m"])
    return out


def distances_from(
    db: Session,
    latitude: float,
    longitude: float,
    object_ids: Optional[Iterable[int]] = None,
    types: Optional[Iterable[str]] = None,
    expediente_id: Optional[int] = None,
    radius_nm: Optional[float] = None,
    limit: int = 200,
) -> list[dict]:
    """Distance from a point to every nearby reference (spec §30, §25).

    This is the "select an aircraft, see how far it is from every source,
    event, antenna and circle" query. Returns KM *and* NM, and ``None``
    for objects without a position rather than a misleading 0.
    """
    if radius_nm is not None:
        rows = objects_near(
            db, latitude, longitude, radius_nm,
            types=types, expediente_id=expediente_id,
        )
        pairs = [(r["object"], r["distance_m"]) for r in rows]
    else:
        q = db.query(MapObject)
        if object_ids:
            q = q.filter(MapObject.id.in_(list(object_ids)))
        if types:
            q = q.filter(MapObject.type.in_([validate_type(t) for t in types]))
        if expediente_id is not None:
            q = q.filter(MapObject.expediente_id == expediente_id)
        pairs = []
        for obj in q.limit(limit).all():
            if obj.latitude is None or obj.longitude is None:
                pairs.append((obj, None))
            else:
                pairs.append(
                    (obj, haversine_m(latitude, longitude, obj.latitude, obj.longitude))
                )

    result = []
    for obj, distance_m in pairs:
        entry = {
            "object_id": obj.id,
            "type": obj.type,
            "name": obj.name,
            "status": obj.status,
            "expediente_id": obj.expediente_id,
            "latitude": obj.latitude,
            "longitude": obj.longitude,
        }
        if distance_m is None:
            entry.update({"distance_m": None, "distance_km": None, "distance_nm": None})
        else:
            entry.update(
                {
                    "distance_m": distance_m,
                    "distance_km": distance_m / 1000.0,
                    "distance_nm": distance_m / 1852.0,
                }
            )
        result.append(entry)

    known = [r for r in result if r["distance_m"] is not None]
    unknown = [r for r in result if r["distance_m"] is None]
    known.sort(key=lambda r: r["distance_m"])
    return known + unknown


# ─── Statistics ──────────────────────────────────────────────────────────────

def object_stats(db: Session) -> dict:
    """Counts per type, per state and per layer, for the map header."""
    count = func.count(MapObject.id)

    by_type: dict[str, int] = {
        t: n for t, n in db.query(MapObject.type, count).group_by(MapObject.type)
    }

    by_status: dict[str, int] = {
        (s or "sin estado"): n
        for s, n in db.query(MapObject.status, count).group_by(MapObject.status)
    }

    per_layer: dict[str, int] = {
        key: n
        for key, n in (
            db.query(Layer.key, count)
            .join(MapObject, MapObject.layer_id == Layer.id)
            .group_by(Layer.key)
        )
    }

    return {
        "total": db.query(count).scalar() or 0,
        "visible": db.query(count).filter(MapObject.visible.is_(True)).scalar() or 0,
        "hidden": db.query(count).filter(MapObject.visible.is_(False)).scalar() or 0,
        "locked": db.query(count).filter(MapObject.locked.is_(True)).scalar() or 0,
        "by_type": by_type,
        "by_status": by_status,
        "by_layer": per_layer,
    }
