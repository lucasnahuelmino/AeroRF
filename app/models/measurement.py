"""
models/measurement.py
────────────────────
`Measurement` — a saved distance measurement (spec §13).

Measurements are ephemeral by default: the tool shows live numbers while
the operator drags, and discards the result unless they ask to save it.
When saved it becomes a normal `MapObject` of type ``measurement`` with
this satellite row holding the breakdown, so the inspector can show each
tramo of a multipoint measurement and the total in m / km / NM.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import relationship

from app.database.database import Base


class Measurement(Base):
    """A saved measurement, single-point or multipoint."""

    __tablename__ = "measurements"

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(
        Integer, ForeignKey("map_objects.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )

    #: ``single`` (A→B) or ``multi`` (A→B→C→D).
    mode = Column(String(16), nullable=False, default="single")

    total_m = Column(Float, nullable=True)
    total_km = Column(Float, nullable=True)
    total_nm = Column(Float, nullable=True)

    #: Per-segment breakdown: length, bearing, endpoints.
    segments = Column(JSON, nullable=True)

    #: Surface type, when the operator is measuring a coverage boundary.
    surface = Column(String(64), nullable=True)

    object = relationship("MapObject", back_populates="measurement")

    def __repr__(self) -> str:
        return f"<Measurement {self.id} obj={self.object_id} {self.total_nm} NM>"
