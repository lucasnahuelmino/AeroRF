"""
rf_engine/ranking.py
────────────────────
Probability scoring and ranking of RF interference candidates.

Scoring model
─────────────
The final score (0–99) is the product of four independent factors:

    score = base_order × proximity × signal_type × power

1. base_order  — lower IM order is more likely to cause interference.
                 H2/IM2 = 1.00, IM3 = 0.90, H3 = 0.85, IM5 = 0.70 …

2. proximity   — how close the calculated product is to the target.
                 Exact match = 1.0; at tolerance boundary = 0.0 (linear).
                 Applied as a weighted bonus (not a pure multiplier) so that
                 a very close IM5 can outscore a borderline IM3.

3. signal_type — FM transmitters and TV stations are strong, well-known
                 sources; unknown signals are down-weighted.

4. power       — if dBm is provided, higher-power emitters score higher.
                 Optional: omitted when power is not available.

All factors are normalised so the output is always in [0, 99].
"""

from __future__ import annotations
from dataclasses import dataclass

from app.models.rf_models import IMOrder, SignalType


# ─── Weight tables ────────────────────────────────────────────────────────────

_ORDER_BASE: dict[str, float] = {
    "H2":  0.82,
    "IM2": 0.88,
    "H3":  0.75,
    "IM3": 0.92,  # IM3 is the most operationally relevant
    "H4":  0.65,
    "H5":  0.58,
    "H6":  0.50,
    "IM5": 0.70,
    "IM7": 0.55,
}

_SIGNAL_TYPE_WEIGHT: dict[str, float] = {
    SignalType.FM:        1.00,   # High-power, well-characterised
    SignalType.TV_VHF:    0.92,
    SignalType.TV_UHF:    0.85,
    SignalType.VHF:       0.80,
    SignalType.UHF:       0.75,
    SignalType.CELLULAR:  0.70,
    SignalType.LINK:      0.65,
    SignalType.UNKNOWN:   0.55,
}

_POWER_REFERENCE_DBM = 60.0   # reference "high power" level (e.g. 1 kW FM tx)
_POWER_FLOOR_DBM     = 0.0    # below this → no power bonus


# ─── Public API ───────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    base_order:   float
    proximity:    float
    signal_type:  float
    power:        float
    final:        int

    def as_dict(self) -> dict[str, float]:
        return {
            "base_order":  round(self.base_order,  3),
            "proximity":   round(self.proximity,   3),
            "signal_type": round(self.signal_type, 3),
            "power":       round(self.power,       3),
            "final":       float(self.final),
        }


def score_candidate(
    tipo: str,
    proximity: float,
    signal_type: SignalType,
    power_dbm: float | None = None,
) -> ScoreBreakdown:
    """
    Compute a probability score for a single RF interference candidate.

    Args:
        tipo:        Product type string ("H2", "IM3", "IM5", …).
        proximity:   Normalised proximity from tolerance check (0.0–1.0).
        signal_type: Emitter signal type.
        power_dbm:   Estimated emitter power in dBm (optional).

    Returns:
        ScoreBreakdown with component weights and final integer score.

    Example:
        >>> s = score_candidate("IM3", 1.0, SignalType.FM, None)
        >>> s.final   # 99  (perfect IM3 match from FM transmitter, exact freq)
    """
    base = _ORDER_BASE.get(tipo, 0.50)

    # Proximity bonus: proximity goes 0→1, scaled to add up to 15 points
    prox_bonus = proximity * 0.15

    # Signal type multiplier
    sig_w = _SIGNAL_TYPE_WEIGHT.get(signal_type, 0.55)

    # Power factor: optional, adds up to 0.10 multiplicative bonus
    if power_dbm is not None:
        clamped = max(_POWER_FLOOR_DBM, min(_POWER_REFERENCE_DBM, power_dbm))
        power_factor = 1.0 + 0.10 * (clamped / _POWER_REFERENCE_DBM)
    else:
        power_factor = 1.0

    raw = (base + prox_bonus) * sig_w * power_factor
    final = min(99, max(1, round(raw * 100)))

    return ScoreBreakdown(
        base_order=base,
        proximity=prox_bonus,
        signal_type=sig_w,
        power=power_factor,
        final=final,
    )


def rank_candidates(candidates: list[dict]) -> list[dict]:
    """
    Sort candidates by score descending, then by error_khz ascending.

    Each dict in the list must have 'score' and 'error_khz' keys.
    Returns a new sorted list (original is not mutated).
    """
    return sorted(
        candidates,
        key=lambda c: (-c["score"], c["error_khz"]),
    )


def deduplicate(candidates: list[dict], key: str = "formula") -> list[dict]:
    """Remove duplicate candidates by the given key (keeps highest-score copy)."""
    seen: dict[str, dict] = {}
    for c in candidates:
        k = c[key]
        if k not in seen or c["score"] > seen[k]["score"]:
            seen[k] = c
    return list(seen.values())
