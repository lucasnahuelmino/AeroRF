"""
models/rf.py
────────────
Type-specific payloads for the RF domain objects (spec §32, §33, §34, §31).

Each table is a 1:1 satellite of ``MapObject``: it holds only the
attributes that make the object what it is, and inherits identity, geometry,
state, styling, history and notes from the parent row. A source is
therefore selectable, draggable, hideable and historised exactly like a
plain point, without a second CRUD path.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.time import utcnow
from app.database.database import Base
from app.models.constants import (
    PROVENANCE_USER,
    RF_EVENT_CLASSIFICATIONS,
    RF_KIND_OTHER,
    RF_SOURCE_KINDS,
    STATE_ACTIVE,
)


#: Shared UTC clock; see app/core/time.py
_utcnow = utcnow


class RFSource(Base):
    """An interfering emitter (spec §32).

    ``power_dbm`` and ``power_w`` are both nullable because a field
    measurement usually yields one or the other, and guessing the missing
    one would be inventing data (spec §56).
    """

    __tablename__ = "rf_sources"

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(
        Integer, ForeignKey("map_objects.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )

    kind = Column(String(32), nullable=False, default=RF_KIND_OTHER, index=True)
    frequency_mhz = Column(Float, nullable=True, index=True)
    power_dbm = Column(Float, nullable=True)
    power_w = Column(Float, nullable=True)
    #: EIRP in dBm, when the operator computed it.
    eirp_dbm = Column(Float, nullable=True)
    bandwidth_khz = Column(Float, nullable=True)

    #: Height above ground in metres (spec §32: "altura").
    height_m = Column(Float, nullable=True)

    observations = Column(Text, nullable=True)
    measured_at = Column(DateTime, nullable=True)
    provenance = Column(String(24), nullable=False, default=PROVENANCE_USER)

    object = relationship("MapObject", back_populates="rf_source")

    def __repr__(self) -> str:
        return (
            f"<RFSource {self.id} obj={self.object_id} "
            f"{self.kind} {self.frequency_mhz} MHz>"
        )


class Antenna(Base):
    """A receiving or transmitting antenna (spec §33).

    ``azimuth_deg``/``sector_deg`` drive the directional sector rendering
    (spec §33 "preparar sector direccional").
    """

    __tablename__ = "antennas"

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(
        Integer, ForeignKey("map_objects.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )

    kind = Column(String(48), nullable=True, index=True)
    frequency_mhz = Column(Float, nullable=True, index=True)
    height_m = Column(Float, nullable=True)
    gain_dbi = Column(Float, nullable=True)
    power_w = Column(Float, nullable=True)

    #: Pointing direction, degrees clockwise from true north.
    azimuth_deg = Column(Float, nullable=True)
    #: Horizontal beamwidth in degrees; drives the visual sector.
    sector_deg = Column(Float, nullable=True)
    tilt_deg = Column(Float, nullable=True)
    polarization = Column(String(24), nullable=True)
    pattern = Column(String(64), nullable=True)

    object = relationship("MapObject", back_populates="antenna")

    def __repr__(self) -> str:
        return f"<Antenna {self.id} obj={self.object_id} {self.kind}>"


class ReferencePoint(Base):
    """A named geographic reference (spec §31).

    May carry a protection radius, which is rendered as a circle around
    the reference ("Referencia: Fuente interferente #01, Radio: 10 NM").
    """

    __tablename__ = "reference_points"

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(
        Integer, ForeignKey("map_objects.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )

    kind = Column(String(64), nullable=True, index=True)
    #: Optional cross-reference to the operator's own numbering.
    code = Column(String(64), nullable=True)

    # Radius in the operator's unit; converted at render time.
    radius = Column(Float, nullable=True)
    radius_unit = Column(String(8), nullable=True, default="nm")

    observations = Column(Text, nullable=True)

    object = relationship("MapObject", back_populates="reference")

    def __repr__(self) -> str:
        return f"<ReferencePoint {self.id} obj={self.object_id} {self.code}>"


class RFEvent(Base):
    """A measured or reported RF event (spec §34).

    Distinct from the legacy ``EventoRF`` model, which stores the *output*
    of the intermodulation calculator (formula, error, score). That model
    is kept untouched for the RF engine; this one is the geographic,
    operator-facing event with a frequency, level, time and position.
    """

    __tablename__ = "rf_events"

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(
        Integer, ForeignKey("map_objects.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )

    frequency_mhz = Column(Float, nullable=True, index=True)
    level_dbm = Column(Float, nullable=True)
    bandwidth_khz = Column(Float, nullable=True)

    #: When the event happened. `observed_at` on the parent holds the
    #: same value; it is duplicated here so RF-only queries stay simple.
    event_at = Column(DateTime, nullable=True, index=True)

    classification = Column(String(64), nullable=True, index=True)
    source_kind = Column(String(32), nullable=True)
    description = Column(Text, nullable=True)
    observations = Column(Text, nullable=True)

    #: What kind of event: measured on site, reported, calculated.
    event_kind = Column(String(32), nullable=True, default="medido")
    provenance = Column(String(24), nullable=False, default=PROVENANCE_USER)

    #: Optional link to a legacy calculated ``evento_rf`` row.
    calculated_evento_id = Column(
        Integer, ForeignKey("eventos_rf.id", ondelete="SET NULL"), nullable=True
    )

    object = relationship("MapObject", back_populates="rf_event")

    def __repr__(self) -> str:
        return f"<RFEvent {self.id} obj={self.object_id} {self.frequency_mhz} MHz>"


__all__ = [
    "RFSource",
    "Antenna",
    "ReferencePoint",
    "RFEvent",
    "RF_SOURCE_KINDS",
    "RF_EVENT_CLASSIFICATIONS",
]
