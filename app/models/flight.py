"""
models/flight.py
───────────────
Flight persistence (spec §20–§26, §56).

The governing principle is **provenance**. AeroRF must always be able to
say, for any point on a track, whether it came from OpenSky's historical
store, from a current state vector, or from AeroRF's own recorder. An
ENACOM expediente that cannot distinguish them is worthless, because it
cannot be reproduced or defended.

Four tables, each with a single responsibility:

* ``Flight``        — identity and metadata of an aircraft's flight
                      (callsign, ICAO24, window, airports). OpenSky's
                      ``/flights`` answers this.
* ``AircraftTrack`` — a stored polyline with its source. One per
                      OpenSky track import or per local recording.
* ``FlightSession`` — an operator-initiated recording run (spec §24, §26).
* ``AircraftPosition`` — the individual samples inside a session or a
                      track. This is AeroRF's own record of what was
                      observed, and it is what survives when OpenSky's
                      retention window has passed.
* ``FlightSelection`` — the operator's watchlist, capped at 5 (spec §25).
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

from app.core.time import utcnow
from app.database.database import Base
from app.models.constants import (
    SESSION_RECORDING,
    TRACK_SOURCE_OPENSKY,
    TRACK_SOURCES,
)


#: Shared UTC clock; see app/core/time.py
_utcnow = utcnow


class Flight(Base):
    """A flight as reported by OpenSky ``/flights/*``."""

    __tablename__ = "flights"

    id = Column(Integer, primary_key=True, index=True)

    icao24 = Column(String(8), nullable=False, index=True)
    callsign = Column(String(16), nullable=True, index=True)

    first_seen = Column(DateTime, nullable=True, index=True)
    last_seen = Column(DateTime, nullable=True, index=True)

    #: ICAO codes when OpenSky resolves them. ``None`` means unavailable,
    #: which is normal for general aviation — never fabricate an airport.
    departure_icao = Column(String(8), nullable=True, index=True)
    arrival_icao = Column(String(8), nullable=True, index=True)

    departure_airport = Column(String(200), nullable=True)
    arrival_airport = Column(String(200), nullable=True)
    departure_latitude = Column(Float, nullable=True)
    departure_longitude = Column(Float, nullable=True)
    arrival_latitude = Column(Float, nullable=True)
    arrival_longitude = Column(Float, nullable=True)

    #: True while the aircraft is airborne per the last state vector.
    is_active = Column(Boolean, nullable=False, default=False, index=True)
    callsign_icao = Column(String(64), nullable=True)
    duration_s = Column(Float, nullable=True)

    #: Raw OpenSky response, so nothing is lost between polls.
    raw = Column(JSON, nullable=True)

    fetched_at = Column(DateTime, default=_utcnow, nullable=False)
    fecha_creacion = Column(DateTime, default=_utcnow, nullable=False)
    fecha_actualizacion = Column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    tracks = relationship("AircraftTrack", back_populates="flight", lazy="selectin")

    __table_args__ = (
        Index("ix_flights_icao_window", "icao24", "first_seen", "last_seen"),
    )

    def __repr__(self) -> str:
        return f"<Flight {self.icao24} {self.callsign}>"


class AircraftTrack(Base):
    """A stored trajectory polyline with an explicit source (spec §56).

    ``geometry`` is a GeoJSON LineString in WGS84. ``point_count`` and
    ``observed_seconds`` make the temporal density of the track visible,
    which matters because OpenSky waypoints are *not* one per second.
    """

    __tablename__ = "aircraft_tracks"

    id = Column(Integer, primary_key=True, index=True)

    icao24 = Column(String(8), nullable=False, index=True)
    callsign = Column(String(16), nullable=True, index=True)

    flight_id = Column(
        Integer, ForeignKey("flights.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    session_id = Column(
        Integer, ForeignKey("flight_sessions.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )

    #: One of ``opensky`` | ``aerorf`` | ``merged``. Never inferred.
    source = Column(
        String(16), nullable=False, default=TRACK_SOURCE_OPENSKY, index=True
    )

    started_at = Column(DateTime, nullable=True, index=True)
    ended_at = Column(DateTime, nullable=True, index=True)
    point_count = Column(Integer, nullable=False, default=0)

    #: Wall-clock span actually covered by samples.
    observed_seconds = Column(Float, nullable=True)

    geometry = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)

    fecha_creacion = Column(DateTime, default=_utcnow, nullable=False)

    flight = relationship("Flight", back_populates="tracks")
    session = relationship("FlightSession", back_populates="tracks")

    __table_args__ = (Index("ix_tracks_icao_start", "icao24", "started_at"),)

    def __repr__(self) -> str:
        return (
            f"<AircraftTrack {self.id} {self.icao24} "
            f"src={self.source} pts={self.point_count}>"
        )


class FlightSession(Base):
    """An operator-initiated recording run (spec §24, §26).

    Created when the operator presses "Grabar vuelo". Positions are then
    sampled on a fixed interval and stored in ``aircraft_positions``.
    Stopping the session sets ``ended_at`` and ``status``.
    """

    __tablename__ = "flight_sessions"

    id = Column(Integer, primary_key=True, index=True)

    icao24 = Column(String(8), nullable=False, index=True)
    callsign = Column(String(16), nullable=True, index=True)

    started_at = Column(
        DateTime, default=_utcnow, nullable=False, index=True
    )
    ended_at = Column(DateTime, nullable=True)

    status = Column(
        String(16), nullable=False, default=SESSION_RECORDING, index=True
    )

    #: Where the samples came from: ``opensky`` while live, or mixed when
    #: the aircraft went out of receiver coverage and AeroRF only knows
    #: what it saw.
    source = Column(String(16), nullable=False, default=TRACK_SOURCE_OPENSKY)

    #: Sampling interval actually achieved, seconds.
    interval_s = Column(Float, nullable=True)
    sample_count = Column(Integer, nullable=False, default=0)

    description = Column(Text, nullable=True)
    user = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    positions = relationship(
        "AircraftPosition",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AircraftPosition.timestamp",
    )
    tracks = relationship(
        "AircraftTrack", back_populates="session", lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<FlightSession {self.id} {self.icao24} "
            f"{self.status} n={self.sample_count}>"
        )


class AircraftPosition(Base):
    """One observed position of one aircraft (spec §24).

    This is AeroRF's own evidence. Every nullable field is nullable on
    purpose: a state vector that reports no velocity is recorded with
    ``velocity = None`` rather than a placeholder, and the UI shows
    "dato no disponible" (spec §56).
    """

    __tablename__ = "aircraft_positions"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(
        Integer, ForeignKey("flight_sessions.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    track_id = Column(
        Integer, ForeignKey("aircraft_tracks.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )

    #: OpenSky's own observation time, seconds since epoch. Null when the
    #: value was not published — AeroRF never substitutes its own clock.
    timestamp = Column(Integer, nullable=True, index=True)
    #: AeroRF's receive time, always present.
    received_at = Column(
        DateTime, default=_utcnow, nullable=False, index=True
    )

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)      # metres
    heading = Column(Float, nullable=True)       # degrees true
    velocity = Column(Float, nullable=True)      # m/s
    vertical_rate = Column(Float, nullable=True) # m/s
    on_ground = Column(Boolean, nullable=True)

    callsign = Column(String(16), nullable=True)
    icao24 = Column(String(8), nullable=True, index=True)

    #: How this sample was obtained.
    source = Column(String(16), nullable=False, default=TRACK_SOURCE_OPENSKY)

    session = relationship("FlightSession", back_populates="positions")
    track = relationship("AircraftTrack")

    __table_args__ = (
        Index("ix_positions_session_ts", "session_id", "timestamp"),
        Index("ix_positions_icao_ts", "icao24", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<AircraftPosition {self.id} {self.icao24} "
            f"@({self.latitude},{self.longitude})>"
        )


class FlightSelection(Base):
    """The operator's watchlist of tracked aircraft (spec §25, §26).

    Persisted so that reopening AeroRF restores the same set of up to five
    aircraft. ``slot`` (0–4) fixes the display colour; ``selected`` marks
    the one shown in the inspector.
    """

    __tablename__ = "flight_selections"

    id = Column(Integer, primary_key=True, index=True)

    icao24 = Column(String(8), nullable=False, unique=True, index=True)
    callsign = Column(String(16), nullable=True, index=True)

    #: 0–4. Assigned on add and reused while the row lives.
    slot = Column(Integer, nullable=False, default=0)

    color = Column(String(16), nullable=True)
    show_track = Column(Boolean, nullable=False, default=True)
    show_marker = Column(Boolean, nullable=False, default=True)
    selected = Column(Boolean, nullable=False, default=False)

    last_seen = Column(DateTime, nullable=True)
    last_position = Column(JSON, nullable=True)
    user = Column(String(100), nullable=True)
    added_at = Column(DateTime, default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<FlightSelection {self.icao24} slot={self.slot}>"


__all__ = [
    "Flight",
    "AircraftTrack",
    "FlightSession",
    "AircraftPosition",
    "FlightSelection",
    "TRACK_SOURCES",
]
