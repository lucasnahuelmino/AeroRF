"""
models/map_object.py
────────────────────
`MapObject` is the single root of every geographic object in AeroRF.

Architectural decision (spec §2: "TODO ES UN OBJETO")
────────────────────────────────────────────────────
Rather than giving each concept its own disconnected table with its own
CRUD, every operator-created spatial thing is a row here. `MapObject`
carries identity, geometry, state, styling, layer membership and
expediente association — the properties the inspector shows for *any*
object. Type-specific attributes live in satellite tables
(`rf_sources`, `antennas`, `reference_points`, `measurements`) linked 1:1
by `object_id`, so a `RFSource` is simultaneously a normal map object
(selectable, movable, hidden, layered, historised) *and* a source with a
frequency and a power.

That gives one CRUD, one selection model, one history table and one
GeoJSON path for circles, radials, antennas, sources and events alike.

Geometry storage
────────────────
Coordinates are stored twice, on purpose:

* ``latitude`` / ``longitude`` — plain Float columns, indexed. Every
  spatial query AeroRF actually runs (bounding box, distance ordering,
  correlation within N NM) is expressible with plain SQL on these, and
  they work identically on SQLite today and PostgreSQL tomorrow.
* ``geometry`` — a JSON column holding a GeoJSON geometry. This is the
  authoritative shape for arbitrary geometry (trace vertices, circle
  parameters, polygon rings) and the direct source for GeoJSON export.

The JSON column is deliberate rather than PostGIS-only: it keeps SQLite
as a first-class citizen. On migration to PostgreSQL, add a
``geometry(Geometry, 4326)`` column and populate it from ``geometry``
with ``ST_GeomFromGeoJSON``; nothing above the database layer changes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.time import utcnow
from app.database.database import Base
from app.models.constants import (
    LAYER_BY_OBJECT_TYPE,
    STATE_ACTIVE,
    default_color_for_type,
    default_icon_for_type,
)


#: Shared UTC clock; see app/core/time.py
_utcnow = utcnow


class MapObject(Base):
    """Any operator-created spatial object."""

    __tablename__ = "map_objects"

    id = Column(Integer, primary_key=True, index=True)

    # ─── Type and identity ────────────────────────────────────────────────
    type = Column(String(32), nullable=False, index=True)
    name = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String(64), nullable=True, index=True)
    status = Column(
        String(32), nullable=False, default=STATE_ACTIVE, index=True
    )

    # ─── Geometry ─────────────────────────────────────────────────────────
    # Primary position. Null for objects that only exist as a line/polygon
    # without an anchor (rare, but permitted).
    latitude = Column(Float, nullable=True, index=True)
    longitude = Column(Float, nullable=True, index=True)

    # GeoJSON geometry: Point | LineString | Polygon | MultiPolygon
    geometry_type = Column(String(24), nullable=True)
    geometry = Column(JSON, nullable=True)

    # ─── Circle parameters (spec §10) ────────────────────────────────────
    # Stored in the operator's unit so the exact figure entered is
    # recoverable; converted to metres only at render/export time.
    radius = Column(Float, nullable=True)
    radius_unit = Column(String(8), nullable=True, default="nm")

    # ─── Radial parameters (spec §11, §37) ────────────────────────────────
    azimuth = Column(Float, nullable=True)
    length_value = Column(Float, nullable=True)
    length_unit = Column(String(8), nullable=True, default="nm")

    # ─── Styling ──────────────────────────────────────────────────────────
    color = Column(String(16), nullable=True)
    icon = Column(String(32), nullable=True)
    opacity = Column(Float, nullable=True, default=1.0)
    weight = Column(Float, nullable=True, default=3.0)
    fill_opacity = Column(Float, nullable=True, default=0.15)
    label = Column(String(200), nullable=True)
    show_label = Column(Boolean, nullable=False, default=True)

    # ─── Visibility / locking / ordering (spec §38) ──────────────────────
    layer_id = Column(
        Integer, ForeignKey("layers.id", ondelete="SET NULL"), nullable=True,
        index=True,
    )
    visible = Column(Boolean, nullable=False, default=True, index=True)
    locked = Column(Boolean, nullable=False, default=False)
    z_index = Column(Integer, nullable=False, default=0)

    # ─── Links ────────────────────────────────────────────────────────────
    expediente_id = Column(
        Integer, ForeignKey("expedientes.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    parent_id = Column(
        Integer, ForeignKey("map_objects.id", ondelete="SET NULL"), nullable=True
    )

    # ─── Provenance (spec §58) ────────────────────────────────────────────
    # Distinguishes what the operator typed from what the system derived.
    source = Column(String(24), nullable=False, default="user")
    created_by = Column(String(100), nullable=True)

    # ─── Observation window (spec §28, temporal objects) ──────────────────
    observed_at = Column(DateTime, nullable=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)

    # ─── Free-form technical payload ─────────────────────────────────────
    # Type-specific values that do not warrant a column. Serialised to
    # GeoJSON properties on export so nothing is lost.
    properties = Column(JSON, nullable=True)

    # ─── Audit ────────────────────────────────────────────────────────────
    fecha_creacion = Column(DateTime, default=_utcnow, nullable=False)
    fecha_actualizacion = Column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # ─── Relationships ────────────────────────────────────────────────────
    layer = relationship("Layer", back_populates="objects", lazy="selectin")
    expediente = relationship("Expediente", lazy="selectin")
    notes = relationship(
        "ObjectNote",
        back_populates="object",
        cascade="all, delete-orphan",
        order_by="ObjectNote.timestamp",
    )
    history = relationship(
        "ObjectHistory",
        back_populates="object",
        cascade="all, delete-orphan",
        order_by="ObjectHistory.changed_at",
    )
    rf_source = relationship(
        "RFSource", back_populates="object", uselist=False,
        cascade="all, delete-orphan", lazy="selectin",
    )
    antenna = relationship(
        "Antenna", back_populates="object", uselist=False,
        cascade="all, delete-orphan", lazy="selectin",
    )
    reference = relationship(
        "ReferencePoint", back_populates="object", uselist=False,
        cascade="all, delete-orphan", lazy="selectin",
    )
    measurement = relationship(
        "Measurement", back_populates="object", uselist=False,
        cascade="all, delete-orphan", lazy="selectin",
    )
    #: El evento RF (spec §34). Era la única sin relación en este lado:
    #: `RFEvent.object` era de una sola vía, así que ni el Inspector ni la
    #: exportación podían llegar al payload (F2-03).
    rf_event = relationship(
        "RFEvent", back_populates="object", uselist=False,
        cascade="all, delete-orphan", lazy="selectin",
    )
    annotations = relationship(
        "Annotation", back_populates="object",
        cascade="all, delete-orphan", order_by="Annotation.timestamp",
    )

    __table_args__ = (
        Index("ix_map_objects_type_status", "type", "status"),
        Index("ix_map_objects_expediente_type", "expediente_id", "type"),
        Index("ix_map_objects_lat_lon", "latitude", "longitude"),
    )

    # ─── Defaults ─────────────────────────────────────────────────────────
    def apply_defaults(self) -> "MapObject":
        """Fill style/layer defaults for a freshly created object."""
        if not self.color:
            self.color = default_color_for_type(self.type)
        if not self.icon:
            self.icon = default_icon_for_type(self.type)
        if self.opacity is None:
            self.opacity = 1.0
        if not self.status:
            self.status = STATE_ACTIVE
        if self.show_label is None:
            self.show_label = True
        if self.visible is None:
            self.visible = True
        if self.locked is None:
            self.locked = False
        return self

    def __repr__(self) -> str:
        return (
            f"<MapObject {self.id} {self.type} "
            f"'{self.name or ''}' @({self.latitude},{self.longitude})>"
        )
