"""
models/schemas_gis.py
────────────────────
Pydantic request/response contracts for the AeroRF GIS API (spec §47).

Validation happens at the edge so the services can assume well-formed
input. Closed vocabularies (``OBJECT_TYPES``, ``OBJECT_STATES``) are
enforced here, which is what stops the API from accepting a state the
map has no colour for.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.units import SUPPORTED_UNITS
from app.models.constants import (
    ANTENNA_KINDS,
    OBJECT_STATES,
    OBJECT_TYPES,
    POINT_CATEGORIES,
    POLARIZATIONS,
    PROVENANCE_VALUES,
    RF_EVENT_CLASSIFICATIONS,
    RF_SOURCE_KINDS,
    SESSION_STATUSES,
    TRACK_SOURCES,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Layers ──────────────────────────────────────────────────────────────────

class LayerResponse(ORMModel):
    id: int
    key: str
    name: str
    description: Optional[str] = None
    object_types: Optional[str] = None
    visible: bool
    opacity: float
    order_index: int
    locked: bool
    min_zoom: Optional[int] = None
    max_zoom: Optional[int] = None
    color: Optional[str] = None
    is_system: bool
    object_count: int = 0


class LayerCreate(BaseModel):
    key: str = Field(..., min_length=2, max_length=48, pattern=r"^[a-z0-9_]+$")
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    visible: bool = True
    opacity: float = Field(1.0, ge=0.0, le=1.0)
    order_index: int = 0


class LayerUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    visible: Optional[bool] = None
    opacity: Optional[float] = Field(None, ge=0.0, le=1.0)
    order_index: Optional[int] = None
    locked: Optional[bool] = None
    min_zoom: Optional[int] = None
    max_zoom: Optional[int] = None
    color: Optional[str] = None


# ─── Type-specific payloads ──────────────────────────────────────────────────

class RFSourcePayload(BaseModel):
    kind: str = "Otro"
    frequency_mhz: Optional[float] = Field(None, gt=0, lt=6000)
    power_dbm: Optional[float] = Field(None, ge=-200, le=100)
    power_w: Optional[float] = Field(None, ge=0)
    eirp_dbm: Optional[float] = Field(None, ge=-200, le=200)
    bandwidth_khz: Optional[float] = Field(None, ge=0)
    height_m: Optional[float] = Field(None, ge=0)
    observations: Optional[str] = None
    measured_at: Optional[datetime] = None
    provenance: str = "user"

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in RF_SOURCE_KINDS:
            raise ValueError(
                f"kind debe ser uno de: {', '.join(RF_SOURCE_KINDS)}"
            )
        return v


class AntennaPayload(BaseModel):
    kind: Optional[str] = None
    frequency_mhz: Optional[float] = Field(None, gt=0, lt=6000)
    height_m: Optional[float] = Field(None, ge=0)
    gain_dbi: Optional[float] = Field(None, ge=-50, le=100)
    power_w: Optional[float] = Field(None, ge=0)
    azimuth_deg: Optional[float] = Field(None, ge=0, lt=360)
    sector_deg: Optional[float] = Field(None, gt=0, le=360)
    tilt_deg: Optional[float] = Field(None, ge=-90, le=90)
    polarization: Optional[str] = None
    pattern: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ANTENNA_KINDS:
            raise ValueError(f"kind debe ser uno de: {', '.join(ANTENNA_KINDS)}")
        return v

    @field_validator("polarization")
    @classmethod
    def _pol(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in POLARIZATIONS:
            raise ValueError(
                f"polarization debe ser uno de: {', '.join(POLARIZATIONS)}"
            )
        return v


class ReferencePayload(BaseModel):
    kind: Optional[str] = None
    code: Optional[str] = Field(None, max_length=64)
    radius: Optional[float] = Field(None, gt=0)
    radius_unit: Optional[str] = None
    observations: Optional[str] = None

    @field_validator("radius_unit")
    @classmethod
    def _unit(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.lower() not in SUPPORTED_UNITS:
            raise ValueError(f"radius_unit debe ser uno de: {', '.join(SUPPORTED_UNITS)}")
        return v.lower() if v else None


class MeasurementPayload(BaseModel):
    mode: str = "single"
    total_m: Optional[float] = Field(None, ge=0)
    total_km: Optional[float] = Field(None, ge=0)
    total_nm: Optional[float] = Field(None, ge=0)
    segments: Optional[list[dict]] = None
    surface: Optional[str] = None

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in ("single", "multi"):
            raise ValueError("mode debe ser 'single' o 'multi'")
        return v


class RFEventPayload(BaseModel):
    frequency_mhz: Optional[float] = Field(None, gt=0, lt=6000)
    level_dbm: Optional[float] = Field(None, ge=-200, le=100)
    bandwidth_khz: Optional[float] = Field(None, ge=0)
    event_at: Optional[datetime] = None
    classification: Optional[str] = None
    source_kind: Optional[str] = None
    description: Optional[str] = None
    observations: Optional[str] = None
    event_kind: Optional[str] = "medido"
    provenance: str = "user"
    calculated_evento_id: Optional[int] = None

    @field_validator("classification")
    @classmethod
    def _class(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in RF_EVENT_CLASSIFICATIONS:
            raise ValueError(
                f"classification debe ser uno de: "
                f"{', '.join(RF_EVENT_CLASSIFICATIONS)}"
            )
        return v


# ─── Map objects (spec §7, §8) ───────────────────────────────────────────────

class MapObjectCreate(BaseModel):
    """Create any GIS object.

    One endpoint for every type (spec §8, "no duplicar endpoints"): the
    type-specific attributes travel in the matching ``*_payload`` field,
    which keeps a circle, a source and an antenna on one create path.
    """

    type: str = Field(..., description=f"One of: {', '.join(OBJECT_TYPES)}")
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=64)
    status: Optional[str] = None

    # Position — click on the map (method A) or typed in (method B).
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)

    # Circle / coverage
    radius: Optional[float] = Field(None, gt=0)
    radius_unit: Optional[str] = Field(None, max_length=8)

    # Radial
    azimuth: Optional[float] = Field(None, ge=-360, le=360)
    length_value: Optional[float] = Field(None, gt=0)
    length_unit: Optional[str] = Field(None, max_length=8)

    # Arbitrary geometry (traces, polygons, imported shapes)
    geometry: Optional[dict] = None
    geometry_type: Optional[str] = None
    properties: Optional[dict] = None

    # Appearance
    color: Optional[str] = Field(None, max_length=16)
    icon: Optional[str] = Field(None, max_length=32)
    label: Optional[str] = Field(None, max_length=200)
    opacity: Optional[float] = Field(None, ge=0, le=1)
    weight: Optional[float] = Field(None, gt=0, le=20)
    fill_opacity: Optional[float] = Field(None, ge=0, le=1)
    show_label: bool = True

    # Placement
    layer_id: Optional[int] = None
    layer_key: Optional[str] = None
    visible: bool = True
    locked: bool = False
    z_index: int = 0

    # Links
    expediente_id: Optional[int] = None
    observed_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

    source: str = "user"
    created_by: Optional[str] = None
    user: Optional[str] = None
    comment: Optional[str] = None
    notes: Optional[list[str]] = None

    rf: Optional[RFSourcePayload] = None
    antenna: Optional[AntennaPayload] = None
    reference: Optional[ReferencePayload] = None
    measurement: Optional[MeasurementPayload] = None
    event: Optional[RFEventPayload] = None

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        t = (v or "").strip().lower()
        if t not in OBJECT_TYPES:
            raise ValueError(f"type debe ser uno de: {', '.join(OBJECT_TYPES)}")
        return t

    @field_validator("status")
    @classmethod
    def _status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in OBJECT_STATES:
            raise ValueError(f"status debe ser uno de: {', '.join(OBJECT_STATES)}")
        return v

    @field_validator("category")
    @classmethod
    def _category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in POINT_CATEGORIES:
            raise ValueError(
                f"category debe ser uno de: {', '.join(POINT_CATEGORIES)}"
            )
        return v

    @field_validator("radius_unit", "length_unit")
    @classmethod
    def _unit(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v.lower() not in SUPPORTED_UNITS:
            raise ValueError(f"unit debe ser uno de: {', '.join(SUPPORTED_UNITS)}")
        return v.lower()

    @field_validator("source")
    @classmethod
    def _source(cls, v: str) -> str:
        if v not in PROVENANCE_VALUES:
            raise ValueError(
                f"source debe ser uno de: {', '.join(PROVENANCE_VALUES)}"
            )
        return v


class MapObjectUpdate(BaseModel):
    """Partial update. Every changed field is historised server-side."""

    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=64)
    status: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius: Optional[float] = Field(None, gt=0)
    radius_unit: Optional[str] = Field(None, max_length=8)
    azimuth: Optional[float] = Field(None, ge=-360, le=360)
    length_value: Optional[float] = Field(None, gt=0)
    length_unit: Optional[str] = Field(None, max_length=8)
    geometry: Optional[dict] = None
    geometry_type: Optional[str] = None
    properties: Optional[dict] = None
    color: Optional[str] = Field(None, max_length=16)
    icon: Optional[str] = Field(None, max_length=32)
    label: Optional[str] = Field(None, max_length=200)
    opacity: Optional[float] = Field(None, ge=0, le=1)
    weight: Optional[float] = Field(None, gt=0, le=20)
    fill_opacity: Optional[float] = Field(None, ge=0, le=1)
    show_label: Optional[bool] = None
    layer_id: Optional[int] = None
    visible: Optional[bool] = None
    locked: Optional[bool] = None
    z_index: Optional[int] = None
    expediente_id: Optional[int] = None
    observed_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    user: Optional[str] = None
    comment: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in OBJECT_STATES:
            raise ValueError(f"status debe ser uno de: {', '.join(OBJECT_STATES)}")
        return v


class StatusChange(BaseModel):
    status: str
    user: Optional[str] = None
    comment: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in OBJECT_STATES:
            raise ValueError(f"status debe ser uno de: {', '.join(OBJECT_STATES)}")
        return v


class MoveRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    user: Optional[str] = None


class DuplicateRequest(BaseModel):
    name_suffix: str = "(copia)"
    offset_lat: float = 0.0
    offset_lon: float = 0.0
    user: Optional[str] = None


# ─── Notes, history, annotations (spec §14, §41, §42) ───────────────────────

class NoteCreate(BaseModel):
    text: str = Field(..., min_length=1)
    user: Optional[str] = None


class NoteResponse(ORMModel):
    id: int
    object_id: int
    user: Optional[str] = None
    timestamp: datetime
    text: str


class HistoryResponse(ORMModel):
    id: int
    object_id: int
    changed_at: datetime
    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    comment: Optional[str] = None
    user: Optional[str] = None


class AnnotationCreate(BaseModel):
    text: str = Field(..., min_length=1)
    author: Optional[str] = None
    category: Optional[str] = None


# ─── Flights (spec §20–§26) ──────────────────────────────────────────────────

class FlightSearchRequest(BaseModel):
    """Search a flight (spec §20).

    ``callsign`` is a convenience lookup: OpenSky has no callsign search
    endpoint, so a callsign is resolved by scanning live state vectors for
    a match and then querying ``/flights/aircraft`` for the ICAO24.
    """

    callsign: Optional[str] = Field(None, max_length=16)
    icao24: Optional[str] = Field(None, max_length=8)
    date: Optional[str] = Field(None, description="YYYY-MM-DD (UTC)")
    time_hint: Optional[str] = Field(None, description="HH:MM (UTC)")
    window_hours: int = Field(6, ge=1, le=48)


class FlightSessionCreate(BaseModel):
    icao24: str = Field(..., min_length=6, max_length=8)
    callsign: Optional[str] = Field(None, max_length=16)
    interval_s: Optional[float] = Field(10.0, gt=1, le=300)
    description: Optional[str] = None
    user: Optional[str] = None


class FlightSessionResponse(ORMModel):
    id: int
    icao24: str
    callsign: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: str
    source: str
    interval_s: Optional[float] = None
    sample_count: int
    description: Optional[str] = None
    user: Optional[str] = None
    notes: Optional[str] = None
    error: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in SESSION_STATUSES:
            raise ValueError(f"status debe ser uno de: {', '.join(SESSION_STATUSES)}")
        return v


class TrackSelectionRequest(BaseModel):
    icao24: str = Field(..., min_length=6, max_length=8)
    callsign: Optional[str] = Field(None, max_length=16)


class SelectionResponse(ORMModel):
    icao24: str
    callsign: Optional[str] = None
    slot: int
    color: Optional[str] = None
    show_track: bool
    show_marker: bool
    selected: bool
    last_seen: Optional[datetime] = None
    last_position: Optional[dict] = None
    added_at: datetime


__all__ = [
    "ORMModel",
    "LayerResponse", "LayerCreate", "LayerUpdate",
    "RFSourcePayload", "AntennaPayload", "ReferencePayload",
    "MeasurementPayload", "RFEventPayload",
    "MapObjectCreate", "MapObjectUpdate", "StatusChange",
    "MoveRequest", "DuplicateRequest",
    "NoteCreate", "NoteResponse", "HistoryResponse", "AnnotationCreate",
    "FlightSearchRequest", "FlightSessionCreate", "FlightSessionResponse",
    "TrackSelectionRequest", "SelectionResponse",
]
