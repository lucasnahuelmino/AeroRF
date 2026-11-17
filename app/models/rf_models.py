"""
Pydantic models for the SIARI RF engine.
Covers all I/O contracts for the RF calculation API.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ─── Enums ────────────────────────────────────────────────────────────────────

class SignalType(str, Enum):
    """Known emitter signal types — influences ranking score."""
    FM        = "FM"        # FM broadcast (88–108 MHz)
    TV_VHF    = "TV_VHF"    # VHF TV (174–230 MHz)
    TV_UHF    = "TV_UHF"    # UHF TV (470–862 MHz)
    VHF       = "VHF"       # Generic VHF link / PMR
    UHF       = "UHF"       # Generic UHF link / PMR
    CELLULAR  = "CELLULAR"  # 700 / 850 / 1900 MHz cellular
    LINK      = "LINK"      # Microwave point-to-point link
    UNKNOWN   = "UNKNOWN"   # Unclassified


class IMOrder(str, Enum):
    H2   = "H2"
    H3   = "H3"
    H4   = "H4"
    H5   = "H5"
    H6   = "H6"
    IM2  = "IM2"
    IM3  = "IM3"
    IM5  = "IM5"
    IM7  = "IM7"


# ─── Input models ─────────────────────────────────────────────────────────────

class FrequencyInput(BaseModel):
    """A single candidate emitter frequency."""
    freq_mhz: float = Field(..., gt=0, lt=6000, description="Frequency in MHz")
    label: Optional[str] = Field(None, max_length=80, description="Human-readable identifier")
    signal_type: SignalType = Field(SignalType.UNKNOWN, description="Type of signal/emitter")
    power_dbm: Optional[float] = Field(None, description="Estimated power in dBm (optional, used for ranking)")

    @field_validator("freq_mhz")
    @classmethod
    def round_freq(cls, v: float) -> float:
        return round(v, 6)


class RFCalculationRequest(BaseModel):
    """Full request body for the main RF calculation endpoint."""
    target_mhz: float = Field(
        ..., gt=0, lt=6000,
        description="Affected aeronautical frequency in MHz",
        examples=[119.0],
    )
    frequencies: list[FrequencyInput] = Field(
        ..., min_length=1, max_length=50,
        description="List of candidate emitter frequencies",
    )
    tolerance_khz: float = Field(
        10.0, gt=0, le=500,
        description="Maximum allowable error in kHz for a match to be valid",
    )
    max_harmonic_order: int = Field(
        5, ge=2, le=8,
        description="Highest harmonic order to evaluate (2–8)",
    )
    include_im7: bool = Field(
        False,
        description="Whether to include IM7 products (slower, more results)",
    )
    max_results: int = Field(
        25, ge=1, le=100,
        description="Maximum number of ranked results to return",
    )


# ─── Output models ────────────────────────────────────────────────────────────

class RFMatch(BaseModel):
    """A single calculated product that falls within tolerance of the target."""
    result_mhz: float = Field(..., description="Calculated frequency result in MHz")
    formula: str      = Field(..., description="Human-readable formula, e.g. '2×88.5 − 58.0'")
    tipo: IMOrder     = Field(..., description="Product type (H2, IM3, etc.)")
    order: int        = Field(..., description="Intermod/harmonic order (2, 3, 5, 7…)")
    error_khz: float  = Field(..., description="Absolute frequency error vs target in kHz")
    score: int = Field(
        ..., ge=0, le=99,
        description=(
            "Métrica interna del motor (0–99). No es una probabilidad de "
            "interferencia: AeroRF no afirma causalidad."
        ),
    )
    score_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="Desglose de la métrica interna, para transparencia.",
    )
    frequencies_involved: list[float] = Field(
        default_factory=list,
        description="Source frequencies that produce this result",
    )


class RFCalculationResponse(BaseModel):
    """Full response from the RF calculation endpoint."""
    target_mhz: float
    tolerance_khz: float
    total_candidates_evaluated: int
    total_matches: int
    matches: list[RFMatch]
    warnings: list[str] = Field(default_factory=list)


class HarmonicsResponse(BaseModel):
    """Response for single-frequency harmonic lookup."""
    base_freq_mhz: float
    harmonics: list[dict]   # [{order, freq_mhz, formula}]


# ─── Historial propio de análisis (AeroRF 2.6, Bloque 1) ─────────────────────
#
# La calculadora ya no guarda en Expedientes: cada corrida que el operador
# decide conservar se persiste en `analisis_rf` con su request y su response
# completos. No se copian campos sueltos del cálculo (eso duplicaría el
# almacenamiento del motor); `parametros` y `resultados` son los contratos que
# ya existían para `POST /rf/calculate`, reutilizados tal cual.
#
# OJO al evolucionar estos dos modelos: se validan también al *leer* filas
# guardadas, así que un campo nuevo tiene que ser opcional o las corridas
# viejas dejarían de poder consultarse.

class ModoAnalisis(str, Enum):
    """Pestaña de la calculadora desde la que se guardó el análisis."""
    ARMONICOS = "armonicos"
    INTERMODULACION = "intermodulacion"


class AnalisisRFCreate(BaseModel):
    """Body for `POST /rf/analisis`: one saved calculator run."""

    modo: ModoAnalisis = Field(
        ..., description="Pestaña activa al guardar: 'armonicos' o 'intermodulacion'"
    )
    parametros: RFCalculationRequest = Field(
        ..., description="Request tal como se envió a POST /rf/calculate"
    )
    resultados: RFCalculationResponse = Field(
        ..., description="Response tal como lo devolvió el motor"
    )
    objeto_id: Optional[int] = Field(
        None,
        ge=1,
        description=(
            "Objeto GIS opcional al que asocia el análisis (fuente RF, "
            "evento RF o antena). Nunca exigido."
        ),
    )


class AnalisisRFResponse(BaseModel):
    """A stored analysis, readable on its own (spec 3.3, «consultables»)."""

    id: int
    created_at: datetime
    modo: ModoAnalisis
    frecuencia_referencia_mhz: Optional[float] = None
    tolerancia_khz: Optional[float] = None
    n_emisoras: int = Field(..., description="Cantidad de emisoras del request")
    n_productos: int = Field(..., description="Cantidad de productos en la respuesta")
    objeto_id: Optional[int] = None
    parametros: RFCalculationRequest
    resultados: RFCalculationResponse
