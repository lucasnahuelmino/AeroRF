"""
models/tracking.py
──────────────────
Traceability models (spec §14, §40, §41, §42).

Three distinct records, deliberately kept apart because they answer
different questions:

* ``ObjectNote``  — free-form operator log. **Append-only.** Never
  overwritten, never deleted by an edit. This is the running log of an
  investigation ("Fuente apagada", "Se volvió a medir").
* ``ObjectHistory`` — field-level before/after diffs. One row per changed
  field per save, so the full evolution of an object is reconstructable
  ("Hoy ACTIVA, mañana APAGADA, después REACTIVADA").
* ``Annotation`` — a note pinned to a place on the map, optionally
  attached to an object.

None of them are cascade-deleted by a status change. Only an explicit
object deletion removes them, and that is the operator's decision.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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

from app.core.time import utcnow
from app.database.database import Base


#: Shared UTC clock; see app/core/time.py
_utcnow = utcnow


class ObjectNote(Base):
    """Append-only operator note (spec §14).

    Never updated. A note's only lifecycle is "written" and "read".
    """

    __tablename__ = "object_notes"

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(
        Integer, ForeignKey("map_objects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user = Column(String(100), nullable=True)
    timestamp = Column(DateTime, default=_utcnow, nullable=False, index=True)
    text = Column(Text, nullable=False)

    object = relationship("MapObject", back_populates="notes")

    __table_args__ = (Index("ix_object_notes_object_ts", "object_id", "timestamp"),)

    def __repr__(self) -> str:
        return f"<ObjectNote {self.id} obj={self.object_id} @{self.timestamp}>"


class ObjectHistory(Base):
    """Field-level change log (spec §41).

    One row per changed field. ``old_value`` is ``None`` on creation.
    Status transitions therefore appear as ordinary history rows, which is
    what makes the "ACTIVA → APAGADA → REACTIVADA" case auditable.
    """

    __tablename__ = "object_history"

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(
        Integer, ForeignKey("map_objects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    changed_at = Column(DateTime, default=_utcnow, nullable=False, index=True)
    field = Column(String(64), nullable=False)
    old_value = Column(String(1000), nullable=True)
    new_value = Column(String(1000), nullable=True)
    comment = Column(Text, nullable=True)
    user = Column(String(100), nullable=True)

    object = relationship("MapObject", back_populates="history")

    __table_args__ = (
        Index("ix_object_history_object_field", "object_id", "field"),
    )

    def __repr__(self) -> str:
        return (
            f"<ObjectHistory obj={self.object_id} "
            f"{self.field}: {self.old_value!r} -> {self.new_value!r}>"
        )


class Annotation(Base):
    """A note pinned to a map location (spec §6, §38)."""

    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(
        Integer, ForeignKey("map_objects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    text = Column(Text, nullable=False)
    author = Column(String(100), nullable=True)
    timestamp = Column(DateTime, default=_utcnow, nullable=False, index=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    category = Column(String(64), nullable=True)
    color = Column(String(16), nullable=True)

    object = relationship("MapObject", back_populates="annotations")

    def __repr__(self) -> str:
        return f"<Annotation {self.id} obj={self.object_id}>"
