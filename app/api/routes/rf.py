"""
api/routes/rf.py
────────────────
FastAPI router for all RF engine endpoints.

Endpoints
─────────
POST /rf/calculate        — Full IM + harmonic analysis
GET  /rf/harmonics/{freq} — Harmonic table for a single frequency
POST /rf/validate         — Quick tolerance check (no ranking)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.models.rf_models import (
    FrequencyInput,
    HarmonicsResponse,
    RFCalculationRequest,
    RFCalculationResponse,
    SignalType,
)
from app.rf_engine.engine    import RFEngine
from app.rf_engine.harmonics import all_harmonics_table

router  = APIRouter(prefix="/rf", tags=["RF Engine"])
_engine = RFEngine()          # single shared instance (stateless)


# ─── POST /rf/calculate ───────────────────────────────────────────────────────

@router.post(
    "/calculate",
    response_model=RFCalculationResponse,
    summary="Full RF interference analysis",
    description=(
        "Calculate harmonics (H2–H_n), IM2, IM3, IM5 and optionally IM7 "
        "products for all provided frequency candidates. Results are scored "
        "and ranked by probability of causing the reported aeronautical "
        "interference."
    ),
)
async def calculate(req: RFCalculationRequest) -> RFCalculationResponse:
    """
    **Example request body:**

    ```json
    {
      "target_mhz": 119.0,
      "tolerance_khz": 10.0,
      "frequencies": [
        {"freq_mhz": 88.5, "label": "FM Radio", "signal_type": "FM"},
        {"freq_mhz": 58.0, "label": "TV señal", "signal_type": "TV_UHF"}
      ]
    }
    ```

    **Top expected result:**
    `2×88.5 − 58.0 = 119.000 MHz` → IM3, score 91, error 0.0 kHz
    """
    try:
        return _engine.calculate(req)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ─── GET /rf/harmonics/{freq} ────────────────────────────────────────────────

@router.get(
    "/harmonics/{freq_mhz}",
    response_model=HarmonicsResponse,
    summary="Harmonic table for a single frequency",
)
async def harmonics(
    freq_mhz: float,
    max_order: int = Query(default=6, ge=2, le=12, description="Highest harmonic order"),
) -> HarmonicsResponse:
    """
    Return a table of harmonics H2 through H_n for the given frequency.
    No tolerance filtering — all products are returned.

    Example: `/rf/harmonics/88.5?max_order=5`
    → H2=177.0, H3=265.5, H4=354.0, H5=442.5
    """
    if freq_mhz <= 0 or freq_mhz >= 6000:
        raise HTTPException(status_code=422, detail="freq_mhz must be between 0 and 6000")

    return HarmonicsResponse(
        base_freq_mhz=freq_mhz,
        harmonics=all_harmonics_table(freq_mhz, max_order),
    )


# ─── POST /rf/validate ───────────────────────────────────────────────────────

@router.post(
    "/validate",
    summary="Quick tolerance check",
    description="Check a list of raw frequencies against a target without full ranking.",
)
async def validate(
    target_mhz: float,
    frequencies: list[float],
    tolerance_khz: float = 10.0,
) -> JSONResponse:
    """
    Lightweight endpoint: returns which frequencies fall within tolerance
    of the target, along with their error in kHz.
    """
    from app.rf_engine.tolerance import check_tolerance

    results = []
    for f in frequencies:
        t = check_tolerance(f, target_mhz, tolerance_khz)
        if t.match:
            results.append({
                "freq_mhz":  f,
                "error_khz": t.error_khz,
                "proximity": t.proximity,
            })

    return JSONResponse(content={
        "target_mhz":     target_mhz,
        "tolerance_khz":  tolerance_khz,
        "direct_matches": results,
    })
