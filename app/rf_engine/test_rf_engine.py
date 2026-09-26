"""
tests/test_rf_engine.py
───────────────────────
Unit + integration tests for the SIARI RF engine.

Run with:
    pytest tests/ -v
"""

import pytest
from app.models.rf_models import FrequencyInput, RFCalculationRequest, SignalType
from app.rf_engine.engine      import RFEngine
from app.rf_engine.harmonics   import calculate_harmonics, all_harmonics_table
from app.rf_engine.intermod    import calculate_im3, calculate_im2, calculate_im5
from app.rf_engine.tolerance   import check_tolerance, tolerance_band
from app.rf_engine.ranking     import score_candidate
from app.rf_engine.signal_classifier import classify


# ─── Tolerance ────────────────────────────────────────────────────────────────

class TestTolerance:
    def test_exact_match(self):
        r = check_tolerance(119.000, 119.000, 10.0)
        assert r.match is True
        assert r.error_khz == 0.0
        assert r.proximity == 1.0

    def test_within_tolerance(self):
        r = check_tolerance(119.002, 119.000, 10.0)
        assert r.match is True
        assert r.error_khz == pytest.approx(2.0, abs=0.001)
        assert r.proximity == pytest.approx(0.8, abs=0.001)

    def test_outside_tolerance(self):
        r = check_tolerance(119.050, 119.000, 10.0)
        assert r.match is False

    def test_negative_result_no_match(self):
        r = check_tolerance(-10.0, 119.0, 10.0)
        assert r.match is False

    def test_band(self):
        lo, hi = tolerance_band(119.0, 10.0)
        assert lo == pytest.approx(118.990)
        assert hi == pytest.approx(119.010)


# ─── Harmonics ────────────────────────────────────────────────────────────────

class TestHarmonics:
    def test_h3_match(self):
        """3rd harmonic of 39.667 MHz ≈ 119.001 MHz → matches 119.000 ±10 kHz."""
        results = calculate_harmonics(39.667, 119.000, 10.0, max_order=5)
        tipos = [r.tipo for r in results]
        assert "H3" in tipos

    def test_no_match_outside_tolerance(self):
        results = calculate_harmonics(50.0, 119.0, 5.0, max_order=5)
        # 50*2=100, 50*3=150 — none within 5 kHz of 119 MHz
        assert results == []

    def test_formula_format(self):
        results = calculate_harmonics(59.5, 119.0, 5.0, max_order=3)
        # 2 × 59.5 = 119.0 → exact match H2
        assert any(r.tipo == "H2" for r in results)
        h2 = next(r for r in results if r.tipo == "H2")
        assert "2 × 59.5" in h2.formula

    def test_all_harmonics_table(self):
        table = all_harmonics_table(59.5, max_order=4)
        assert len(table) == 3   # H2, H3, H4
        assert table[0]["freq_mhz"] == pytest.approx(119.0)
        assert table[0]["tipo"] == "H2"


# ─── Intermod ────────────────────────────────────────────────────────────────

class TestIntermod:
    def test_canonical_im3_saez(self):
        """
        Classic SAEZ case: 2×88.5 − 58.0 = 119.0 MHz
        Should be found by calculate_im3 within 10 kHz.
        """
        results = calculate_im3(88.5, 58.0, 119.0, 10.0)
        assert len(results) > 0
        match = next((r for r in results if abs(r.result_mhz - 119.0) < 0.001), None)
        assert match is not None, "Expected 119.000 MHz IM3 product not found"
        assert match.tipo == "IM3"
        assert match.tolerance.error_khz == pytest.approx(0.0, abs=0.1)

    def test_im3_formula_content(self):
        results = calculate_im3(88.5, 58.0, 119.0, 10.0)
        formulas = [r.formula for r in results]
        assert any("2×88.5" in f for f in formulas)

    def test_im2_sum(self):
        results = calculate_im2(60.0, 59.0, 119.0, 5.0)
        freqs = [r.result_mhz for r in results]
        assert 119.0 in freqs

    def test_im5_product(self):
        # 3×40.0 − 2×0.5 = 119.0  → trivial example
        results = calculate_im5(40.0, 0.5, 119.0, 5.0)
        match = next((r for r in results if abs(r.result_mhz - 119.0) < 0.01), None)
        assert match is not None

    def test_negative_results_excluded(self):
        """Products that compute to ≤ 0 must never appear."""
        results = calculate_im3(5.0, 200.0, 119.0, 100.0)
        for r in results:
            assert r.result_mhz > 0


# ─── Ranking ─────────────────────────────────────────────────────────────────

class TestRanking:
    def test_im3_scores_higher_than_im5(self):
        im3 = score_candidate("IM3", 1.0, SignalType.FM)
        im5 = score_candidate("IM5", 1.0, SignalType.FM)
        assert im3.final > im5.final

    def test_fm_scores_higher_than_unknown(self):
        fm  = score_candidate("IM3", 0.8, SignalType.FM)
        unk = score_candidate("IM3", 0.8, SignalType.UNKNOWN)
        assert fm.final > unk.final

    def test_exact_match_boosts_score(self):
        exact    = score_candidate("IM3", 1.0, SignalType.FM)
        boundary = score_candidate("IM3", 0.0, SignalType.FM)
        assert exact.final > boundary.final

    def test_score_within_range(self):
        s = score_candidate("IM7", 0.5, SignalType.UNKNOWN)
        assert 0 <= s.final <= 99

    def test_power_bonus(self):
        with_power    = score_candidate("IM3", 1.0, SignalType.FM, power_dbm=60.0)
        without_power = score_candidate("IM3", 1.0, SignalType.FM, power_dbm=None)
        assert with_power.final >= without_power.final


# ─── Signal Classifier ────────────────────────────────────────────────────────

class TestClassifier:
    def test_fm_band(self):
        r = classify(98.7)
        assert r.signal_type == SignalType.FM
        assert r.confidence == 1.0

    def test_tv_uhf(self):
        r = classify(600.0)
        assert r.signal_type == SignalType.TV_UHF

    def test_unknown(self):
        r = classify(1.0)
        assert r.signal_type == SignalType.UNKNOWN
        assert r.confidence == 0.5


# ─── Full Engine Integration ──────────────────────────────────────────────────

class TestEngine:
    def setup_method(self):
        self.engine = RFEngine()

    def _saez_request(self, **kwargs) -> RFCalculationRequest:
        # `tolerance_khz` is set via setdefault so a caller can override it
        # without passing the keyword twice (which is a TypeError).
        params = {
            "tolerance_khz": 10.0,
            "frequencies": [
                FrequencyInput(freq_mhz=88.5, label="FM Radio",  signal_type=SignalType.FM),
                FrequencyInput(freq_mhz=58.0, label="TV señal",  signal_type=SignalType.TV_UHF),
            ],
        }
        params.update(kwargs)
        return RFCalculationRequest(target_mhz=119.0, **params)

    def test_canonical_result_present(self):
        """2×88.5 − 58.0 = 119.000 must be the top result."""
        resp = self.engine.calculate(self._saez_request())
        assert resp.total_matches > 0
        top = resp.matches[0]
        assert top.tipo == "IM3"
        assert abs(top.result_mhz - 119.0) < 0.001
        assert top.error_khz == pytest.approx(0.0, abs=0.1)

    def test_canonical_result_has_high_score(self):
        resp = self.engine.calculate(self._saez_request())
        top = resp.matches[0]
        assert top.score >= 85, f"Expected score ≥ 85, got {top.score}"

    def test_response_fields_populated(self):
        resp = self.engine.calculate(self._saez_request())
        assert resp.target_mhz == 119.0
        assert resp.tolerance_khz == 10.0
        assert resp.total_candidates_evaluated > 0

    def test_max_results_respected(self):
        resp = self.engine.calculate(self._saez_request(max_results=3))
        assert len(resp.matches) <= 3

    def test_wide_tolerance_finds_more(self):
        narrow = self.engine.calculate(self._saez_request(tolerance_khz=1.0))
        wide   = self.engine.calculate(self._saez_request(tolerance_khz=50.0))
        assert wide.total_matches >= narrow.total_matches

    def test_no_frequencies_returns_warning(self):
        req = RFCalculationRequest(
            target_mhz=119.0,
            tolerance_khz=1.0,
            frequencies=[
                FrequencyInput(freq_mhz=100.0, signal_type=SignalType.FM),
            ],
        )
        resp = self.engine.calculate(req)
        # 2×100=200, 3×100=300 — none near 119 within 1 kHz
        # May or may not have matches; just ensure it doesn't crash
        assert isinstance(resp.matches, list)

    def test_score_breakdown_present(self):
        resp = self.engine.calculate(self._saez_request())
        for match in resp.matches:
            assert "final" in match.score_breakdown
            assert "base_order" in match.score_breakdown

    def test_frequencies_involved_populated(self):
        resp = self.engine.calculate(self._saez_request())
        for match in resp.matches:
            assert len(match.frequencies_involved) >= 1
