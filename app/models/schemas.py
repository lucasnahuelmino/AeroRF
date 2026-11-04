"""
models/schemas.py
─────────────────
Pydantic schemas for API request/response validation.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


# ─── Expediente Schemas ────────────────────────────────────────────────────────

class ExpedienteBase(BaseModel):
    numero_expediente: str = Field(..., max_length=50)
    freq_mhz: float = Field(..., gt=0, lt=6000)
    aeropuerto: str = Field(..., max_length=100)
    lat: Optional[float] = None
    lon: Optional[float] = None
    estado: str = Field(default="abierto")
    severidad: str = Field(default="media")
    inspector_responsable: Optional[str] = None
    observaciones: Optional[str] = None
    descripcion: Optional[str] = None


class ExpedienteCreate(ExpedienteBase):
    @field_validator("numero_expediente")
    @classmethod
    def numero_no_vacio(cls, v: str) -> str:
        # P0-01: el número es el identificador del caso — un vacío es la
        # misma falta que un null, con la base ya obligada a no admitirlo.
        if not v.strip():
            raise ValueError("el número de expediente no puede quedar vacío")
        return v


class ExpedienteUpdate(BaseModel):
    numero_expediente: Optional[str] = None
    freq_mhz: Optional[float] = None
    aeropuerto: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    estado: Optional[str] = None
    severidad: Optional[str] = None
    inspector_responsable: Optional[str] = None
    observaciones: Optional[str] = None
    descripcion: Optional[str] = None

    @field_validator("numero_expediente")
    @classmethod
    def numero_no_nulo_ni_vacio(cls, v: Optional[str]) -> str:
        # P0-01: `exclude_unset` distingue "no vino" de "vino en null" —
        # el null explicitado pasaba, se guardaba y la fila quedaba sin
        # número. Aquí se frena antes de tocar la base.
        if v is None:
            raise ValueError("el número de expediente no admite null")
        if not v.strip():
            raise ValueError("el número de expediente no puede quedar vacío")
        return v


class ExpedienteResponse(ExpedienteBase):
    id: int
    fecha_creacion: datetime
    fecha_actualizacion: datetime

    class Config:
        from_attributes = True


# ─── Medicion Schemas ──────────────────────────────────────────────────────────

class MedicionBase(BaseModel):
    expediente_id: int
    freq_mhz: float
    nivel_dbm: Optional[float] = None
    ancho_banda_khz: Optional[float] = None
    lat: float
    lon: float
    fecha_medicion: str
    descripcion: Optional[str] = None
    notas_tecnicas: Optional[str] = None
    ubicacion_nombre: Optional[str] = None


class MedicionCreate(MedicionBase):
    pass


class MedicionResponse(MedicionBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


# ─── EventoRF Schemas ──────────────────────────────────────────────────────────

class EventoRFBase(BaseModel):
    expediente_id: int
    frecuencia_resultado_mhz: float
    tipo_producto: str
    formula: str
    error_khz: float
    score_probabilidad: float
    proximidad: Optional[float] = None
    freq_1_mhz: Optional[float] = None
    freq_2_mhz: Optional[float] = None
    senal_type: Optional[str] = None
    potencia_estimada_dbm: Optional[float] = None
    observaciones: Optional[str] = None


class EventoRFCreate(EventoRFBase):
    pass


class EventoRFResponse(EventoRFBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


# ─── Flight Search Schemas ─────────────────────────────────────────────────────

class FlightRouteBase(BaseModel):
    callsign: str
    origin: str
    destination: str
    origin_name: str
    destination_name: str
    status: str
    departure_time: str
    arrival_time: str
    path: List[List[float]]


class FlightRouteResponse(FlightRouteBase):
    class Config:
        from_attributes = True


# ─── RegistroEspectral Schemas ─────────────────────────────────────────────────

class RegistroEspectralBase(BaseModel):
    expediente_id: int
    archivo_path: str
    tipo_archivo: str
    nombre_archivo: str
    frecuencia_centro_mhz: Optional[float] = None
    ancho_vista_khz: Optional[float] = None
    anotaciones: Optional[str] = None
    descripcion: Optional[str] = None


class RegistroEspectralCreate(RegistroEspectralBase):
    pass


class RegistroEspectralResponse(RegistroEspectralBase):
    id: int
    timestamp: datetime
    procesado: str

    class Config:
        from_attributes = True
