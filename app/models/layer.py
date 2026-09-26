"""
models/layer.py
───────────────
`Layer` — the visual container for map objects (spec §38).

A layer is a first-class row so visibility, opacity, ordering, locking and
zoom limits survive a restart, instead of living in a reactive object that
vanishes on reload.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.time import utcnow
from app.database.database import Base
from app.models.constants import DEFAULT_LAYERS


#: Shared UTC clock; see app/core/time.py
_utcnow = utcnow


class Layer(Base):
    """A named, ordered, toggleable group of map objects."""

    __tablename__ = "layers"

    id = Column(Integer, primary_key=True, index=True)

    #: Stable machine key, e.g. ``rf_sources``. Never reused.
    key = Column(String(48), nullable=False, unique=True, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)

    #: Which object types belong here by default.
    object_types = Column(String(300), nullable=True)

    # ─── Display state (spec §38) ────────────────────────────────────────
    visible = Column(Boolean, nullable=False, default=True, index=True)
    opacity = Column(Float, nullable=False, default=1.0)
    order_index = Column(Integer, nullable=False, default=0)
    locked = Column(Boolean, nullable=False, default=False)

    #: Zoom thresholds; ``None`` means unbounded.
    min_zoom = Column(Integer, nullable=True)
    max_zoom = Column(Integer, nullable=True)

    color = Column(String(16), nullable=True)
    is_system = Column(Boolean, nullable=False, default=True)

    fecha_creacion = Column(DateTime, default=_utcnow, nullable=False)
    fecha_actualizacion = Column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    objects = relationship(
        "MapObject",
        back_populates="layer",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Layer {self.key} visible={self.visible} order={self.order_index}>"

    # ─── Seeding ──────────────────────────────────────────────────────────
    @staticmethod
    def seed_defaults() -> list[tuple[str, str, bool, float, int]]:
        """Return the default layer tuples from the constants module."""
        return list(DEFAULT_LAYERS)
