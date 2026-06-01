"""
Pydantic models for the SIARI RF engine.
Covers all I/O contracts for the RF calculation API.
"""

from __future__ import annotations
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
    score: int        = Field(..., ge=0, le=99, description="Probability score 0–99")
    score_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="Score component breakdown for transparency",
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
