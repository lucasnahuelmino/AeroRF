"""
rf_engine/tolerance.py
─────────────────────
Utilities for comparing calculated RF products against a target frequency
within a configurable tolerance band.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToleranceResult:
    """Result of a single tolerance check."""
    match: bool
    error_khz: float
    proximity: float   # 0.0 → at tolerance boundary; 1.0 → exact match


def check_tolerance(
    result_mhz: float,
    target_mhz: float,
    tolerance_khz: float,
) -> ToleranceResult:
    """
    Check whether a calculated frequency falls within ±tolerance_khz of the target.

    Args:
        result_mhz:    Calculated product frequency in MHz.
        target_mhz:    Affected aeronautical frequency in MHz.
        tolerance_khz: Acceptable deviation in kHz.

    Returns:
        ToleranceResult with match flag, absolute error, and normalised proximity.

    Example:
        >>> r = check_tolerance(119.002, 119.000, 10.0)
        >>> r.match          # True
        >>> r.error_khz      # 2.0
        >>> r.proximity      # 0.8
    """
    if result_mhz <= 0:
        return ToleranceResult(match=False, error_khz=float("inf"), proximity=0.0)

    error_khz = abs(result_mhz - target_mhz) * 1_000.0

    if error_khz > tolerance_khz:
        return ToleranceResult(match=False, error_khz=round(error_khz, 3), proximity=0.0)

    proximity = 1.0 - (error_khz / tolerance_khz) if tolerance_khz > 0 else 1.0

    return ToleranceResult(
        match=True,
        error_khz=round(error_khz, 3),
        proximity=round(proximity, 6),
    )


def tolerance_band(
    target_mhz: float,
    tolerance_khz: float,
) -> tuple[float, float]:
    """Return the (lower, upper) MHz bounds for a given tolerance."""
    delta = tolerance_khz / 1_000.0
    return (target_mhz - delta, target_mhz + delta)
