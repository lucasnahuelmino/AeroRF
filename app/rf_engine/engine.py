"""
rf_engine/engine.py
───────────────────
Main RF engine orchestrator — assembles harmonics, intermod, ranking
into a single callable that powers the /rf/calculate API endpoint.

Usage
-----
    from app.rf_engine.engine import RFEngine
    from app.models.rf_models import RFCalculationRequest, FrequencyInput, SignalType

    req = RFCalculationRequest(
        target_mhz=119.0,
        tolerance_khz=10.0,
        frequencies=[
            FrequencyInput(freq_mhz=88.5,  label="FM Radio",  signal_type=SignalType.FM),
            FrequencyInput(freq_mhz=58.0,  label="TV señal",  signal_type=SignalType.TV_UHF),
        ],
    )
    result = RFEngine().calculate(req)
    # result.matches[0].formula  → "2×88.5 − 58.0"
    # result.matches[0].tipo     → "IM3"
    # result.matches[0].score    → 91
"""

from __future__ import annotations
from itertools import combinations

from app.models.rf_models import (
    FrequencyInput,
    RFCalculationRequest,
    RFCalculationResponse,
    RFMatch,
    IMOrder,
    SignalType,
)
from .harmonics        import calculate_harmonics
from .intermod         import calculate_all_im
from .ranking          import score_candidate, rank_candidates, deduplicate
from .signal_classifier import auto_classify


class RFEngine:
    """
    Stateless RF interference analysis engine.
    Instantiate once and call .calculate() for each request.
    """

    # ── Public method ──────────────────────────────────────────────────────────

    def calculate(self, req: RFCalculationRequest) -> RFCalculationResponse:
        """
        Run the full interference analysis pipeline:

        1. Auto-classify signal types if not provided.
        2. Calculate harmonics for every input frequency.
        3. Calculate IM2/IM3/IM5 (and optionally IM7) for every pair.
        4. Score and rank all matches.
        5. Deduplicate and return top N results.
        """
        warnings: list[str] = []
        raw_candidates: list[dict] = []
        total_evaluated = 0

        # ── 1. Enrich frequencies with auto-classified signal type ─────────────
        enriched: list[tuple[FrequencyInput, SignalType]] = []
        for f in req.frequencies:
            stype = auto_classify(f.freq_mhz, f.signal_type)
            enriched.append((f, stype))

        # ── 2. Harmonics ───────────────────────────────────────────────────────
        for freq_input, stype in enriched:
            products = calculate_harmonics(
                freq_mhz=freq_input.freq_mhz,
                target_mhz=req.target_mhz,
                tolerance_khz=req.tolerance_khz,
                max_order=req.max_harmonic_order,
            )
            total_evaluated += req.max_harmonic_order - 1  # orders 2..max

            for p in products:
                breakdown = score_candidate(
                    tipo=p.tipo,
                    proximity=p.tolerance.proximity,
                    signal_type=stype,
                    power_dbm=freq_input.power_dbm,
                )
                raw_candidates.append(self._to_dict(p, breakdown, [freq_input.freq_mhz]))

        # ── 3. Intermod products (all pairs) ───────────────────────────────────
        freq_pairs = list(combinations(range(len(enriched)), 2))
        for i, j in freq_pairs:
            fa_input, sa = enriched[i]
            fb_input, sb = enriched[j]

            products = calculate_all_im(
                fa=fa_input.freq_mhz,
                fb=fb_input.freq_mhz,
                target_mhz=req.target_mhz,
                tolerance_khz=req.tolerance_khz,
                include_im7=req.include_im7,
            )

            # Approximate evaluation count: IM2(2) + IM3(4) + IM5(4) [+ IM7(2)]
            total_evaluated += 10 + (2 if req.include_im7 else 0)

            # Use the stronger/more-characterised source for signal type scoring
            stype = sa if _signal_priority(sa) >= _signal_priority(sb) else sb
            power = _combine_powers(fa_input.power_dbm, fb_input.power_dbm)

            for p in products:
                breakdown = score_candidate(
                    tipo=p.tipo,
                    proximity=p.tolerance.proximity,
                    signal_type=stype,
                    power_dbm=power,
                )
                raw_candidates.append(
                    self._to_dict(p, breakdown, [fa_input.freq_mhz, fb_input.freq_mhz])
                )

        if not raw_candidates:
            warnings.append(
                f"No products found within ±{req.tolerance_khz} kHz of "
                f"{req.target_mhz} MHz. Consider widening the tolerance."
            )

        # ── 4. Deduplicate → sort → cap ────────────────────────────────────────
        unique    = deduplicate(raw_candidates, key="formula")
        ranked    = rank_candidates(unique)
        top       = ranked[:req.max_results]

        # ── 5. Build response ──────────────────────────────────────────────────
        matches = [
            RFMatch(
                result_mhz=c["result_mhz"],
                formula=c["formula"],
                tipo=c["tipo"],
                order=c["order"],
                error_khz=c["error_khz"],
                score=c["score"],
                score_breakdown=c["score_breakdown"],
                frequencies_involved=c["frequencies_involved"],
            )
            for c in top
        ]

        return RFCalculationResponse(
            target_mhz=req.target_mhz,
            tolerance_khz=req.tolerance_khz,
            total_candidates_evaluated=total_evaluated,
            total_matches=len(unique),
            matches=matches,
            warnings=warnings,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _to_dict(product, breakdown, freqs_involved: list[float]) -> dict:
        """Flatten a product + breakdown into a plain dict for ranking."""
        return {
            "result_mhz":          round(product.result_mhz, 6),
            "formula":             product.formula,
            "tipo":                product.tipo,
            "order":               product.order,
            "error_khz":           product.tolerance.error_khz,
            "score":               breakdown.final,
            "score_breakdown":     breakdown.as_dict(),
            "frequencies_involved": freqs_involved,
        }


# ─── Module-level helpers ─────────────────────────────────────────────────────

_SIGNAL_PRIORITY: dict[SignalType, int] = {
    SignalType.FM:       5,
    SignalType.TV_VHF:   4,
    SignalType.TV_UHF:   4,
    SignalType.VHF:      3,
    SignalType.UHF:      3,
    SignalType.CELLULAR: 2,
    SignalType.LINK:     2,
    SignalType.UNKNOWN:  1,
}

def _signal_priority(st: SignalType) -> int:
    return _SIGNAL_PRIORITY.get(st, 0)


def _combine_powers(pa: float | None, pb: float | None) -> float | None:
    """Return the maximum power of two optional dBm values."""
    if pa is None and pb is None:
        return None
    if pa is None:
        return pb
    if pb is None:
        return pa
    return max(pa, pb)
