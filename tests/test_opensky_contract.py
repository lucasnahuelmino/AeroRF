"""
tests/test_opensky_contract.py
─────────────────────────────
Contract tests against a **real** OpenSky response.

Why this file exists
────────────────────
The unit tests in ``test_opensky.py`` use a hand-written fixture. When
that fixture was built from the OpenSky documentation's state-vector
table it had 18 fields — and the parser accepted 18. The documentation
lists all 18 in one table, but that describes the ``extended=1`` shape.

The first live call on 2026-09-25 returned **13 369 aircraft with 17
fields each**. The parser rejected every one of them: ``get_states()``
would have returned ``count: 0`` forever, with no error and an empty map,
and every mock-based test would still have passed.

So the contract is now pinned to a real capture, kept in
``tests/fixtures/opensky_states_contract.json``. Mocks can disagree with
reality; a real capture cannot be argued with.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.opensky_service import (
    AIRCRAFT_CATEGORIES,
    POSITION_SOURCES,
    SV_MIN_FIELDS,
    SV_MIN_FIELDS_EXTENDED,
    parse_state_vector,
)

FIXTURE = Path(__file__).parent / "fixtures" / "opensky_states_contract.json"


@pytest.fixture(scope="module")
def capture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rows(capture):
    return [item["row"] for item in capture["sample"]]


# ─── The shape of a real payload ─────────────────────────────────────────────

class TestRealPayloadShape:
    def test_default_payload_has_seventeen_fields(self, capture):
        """The regression that broke the live feed.

        OpenSky's documentation lists 18 fields in one table, but that is
        the ``extended=1`` shape. The default ``/states/all`` payload has
        17. Requiring 18 silently rejects every published aircraft.
        """
        assert capture["stats"]["field_count"] == SV_MIN_FIELDS
        assert SV_MIN_FIELDS == 17

    def test_every_captured_row_parses(self, rows):
        parsed = [parse_state_vector(r) for r in rows]
        assert all(p is not None for p in parsed), "some real rows were rejected"
        assert len(parsed) == len(rows)

    def test_every_shape_is_covered(self, capture):
        shapes = set(capture["stats"]["shapes"])
        covered = {item["_shape"] for item in capture["sample"]}
        assert shapes == covered, (
            f"shapes present in the capture but not sampled: {shapes - covered}"
        )

    def test_a_short_row_is_still_rejected(self):
        """Structural validation must survive the fix."""
        assert parse_state_vector([1, 2, 3]) is None
        assert parse_state_vector([]) is None
        assert parse_state_vector("not a list") is None
        assert parse_state_vector([None] * 16) is None


# ─── Field indices, checked against real data ───────────────────────────────

class TestFieldIndices:
    def test_identity_fields(self, rows):
        for row in rows:
            sv = parse_state_vector(row)
            # 0: hex transponder address, lowercase
            assert sv["icao24"] == row[0].lower()
            assert len(sv["icao24"]) == 6
            int(sv["icao24"], 16)          # must be valid hex
            # 2: country
            assert sv["origin_country"] == row[2]
            # 16: position source
            assert sv["position_source"] == POSITION_SOURCES.get(row[16])

    def test_position_fields(self, rows):
        for row in rows:
            sv = parse_state_vector(row)
            if row[6] is not None:
                assert -90 <= float(row[6]) <= 90
                assert sv["latitude"] == pytest.approx(float(row[6]))
            if row[5] is not None:
                assert -180 <= float(row[5]) <= 180
                assert sv["longitude"] == pytest.approx(float(row[5]))
            assert sv["has_position"] == (row[5] is not None and row[6] is not None)

    def test_time_fields_are_distinct(self, rows):
        """The historical bug: last_contact used as a position timestamp.

        In a real capture these differ on almost every row — the position
        can be minutes older than the last message received.
        """
        diffs = [
            r[4] - r[3] for r in rows if r[3] is not None and r[4] is not None
        ]
        assert diffs, "no rows with both timestamps"
        assert any(d != 0 for d in diffs), (
            "time_position and last_contact never differ — "
            "the fixture may be synthetic"
        )
        for row in rows:
            sv = parse_state_vector(row)
            assert sv["time_position"] == row[3]
            assert sv["last_contact"] == row[4]

    def test_altitude_preference(self, rows):
        for row in rows:
            sv = parse_state_vector(row)
            if row[13] is not None:
                assert sv["altitude_type"] == "geometric"
                assert sv["altitude"] == pytest.approx(float(row[13]))
            elif row[7] is not None:
                assert sv["altitude_type"] == "barometric"
                assert sv["altitude"] == pytest.approx(float(row[7]))
            else:
                assert sv["altitude"] is None
                assert sv["altitude_type"] is None

    def test_motion_fields(self, rows):
        for row in rows:
            sv = parse_state_vector(row)
            if row[9] is not None:
                assert sv["velocity"] == pytest.approx(float(row[9]))
            if row[10] is not None:
                assert 0 <= float(row[10]) <= 360 or float(row[10]) < 0
                assert sv["heading"] == pytest.approx(float(row[10]))
            assert sv["on_ground"] == bool(row[8])

    def test_category_absent_without_extended(self, rows):
        for row in rows:
            assert len(row) == SV_MIN_FIELDS
            sv = parse_state_vector(row)
            assert sv["category"] is None
            assert sv["category_id"] is None

    def test_category_present_with_extended(self, rows):
        """Same row plus index 17, as `extended=1` returns."""
        for row in rows[:4]:
            extended = list(row) + [3]
            sv = parse_state_vector(extended)
            assert sv is not None
            assert sv["category_id"] == 3
            assert sv["category"] == AIRCRAFT_CATEGORIES[3]
            # Everything else must be unchanged.
            assert sv["icao24"] == parse_state_vector(row)["icao24"]
            assert sv["latitude"] == parse_state_vector(row)["latitude"]

    def test_extended_boundary(self, rows):
        assert len(rows[0]) == SV_MIN_FIELDS_EXTENDED - 1
        assert len(rows[0]) + 1 == SV_MIN_FIELDS_EXTENDED


# ─── Real-world edge cases ───────────────────────────────────────────────────

class TestRealEdgeCases:
    def test_blank_callsign_becomes_none(self, capture):
        blanks = [i for i in capture["sample"] if i["_shape"] == "blank_callsign"]
        assert blanks, "fixture lost the blank-callsign shape"
        for item in blanks:
            assert parse_state_vector(item["row"])["callsign"] is None

    def test_callsigns_are_trimmed(self, rows):
        for row in rows:
            if row[1] and row[1].strip():
                assert parse_state_vector(row)["callsign"] == row[1].strip()

    def test_missing_position_is_none_not_zero(self, capture):
        cases = [i for i in capture["sample"] if i["_shape"] == "no_position"]
        assert cases, "fixture lost the no-position shape"
        for item in cases:
            sv = parse_state_vector(item["row"])
            assert sv["latitude"] is None or sv["longitude"] is None
            assert sv["has_position"] is False

    def test_missing_altitude_is_none(self, capture):
        cases = [i for i in capture["sample"] if i["_shape"] == "no_altitude"]
        assert cases, "fixture lost the no-altitude shape"
        for item in cases:
            sv = parse_state_vector(item["row"])
            assert sv["altitude"] is None
            assert sv["altitude_type"] is None

    def test_barometric_only_is_labelled(self, capture):
        cases = [i for i in capture["sample"] if i["_shape"] == "barometric_only"]
        assert cases, "fixture lost the barometric-only shape"
        for item in cases:
            sv = parse_state_vector(item["row"])
            assert sv["altitude_type"] == "barometric"
            assert sv["geo_altitude"] is None
            assert sv["baro_altitude"] is not None

    def test_integers_are_coerced(self, capture):
        """OpenSky emits `0` where the docs say `0.0`."""
        cases = [i for i in capture["sample"] if i["_shape"] == "int_valued"]
        assert cases, "fixture lost the int-valued shape"
        for item in cases:
            sv = parse_state_vector(item["row"])
            for value in (sv["latitude"], sv["longitude"],
                          sv["velocity"], sv["altitude"]):
                if value is not None:
                    assert isinstance(value, float)

    def test_sensors_is_null_anonymously(self, rows):
        """Documented: null unless a sensor filter was used.

        AeroRF never requests one, so it is always null — recorded here
        so a future change that starts reading index 12 is deliberate.
        """
        assert all(row[12] is None for row in rows)

    def test_squawk_may_be_null(self, rows, capture):
        """Roughly half of real aircraft publish no squawk."""
        assert capture["stats"]["captured_rows"] > 0
        assert any(row[14] is None for row in rows)


# ─── Position staleness ──────────────────────────────────────────────────────

class TestPositionStaleness:
    def test_age_is_computed_from_the_response_time(self, rows, capture):
        now = capture["time"]
        for row in rows:
            if row[3] is None:
                assert parse_state_vector(row, now)["position_age_s"] is None
                continue
            sv = parse_state_vector(row, now)
            assert sv["position_age_s"] == now - row[3]
            assert sv["position_age_s"] >= 0

    def test_real_capture_contains_very_stale_positions(self, capture):
        """Positions up to ~1.5 h old on aircraft still transmitting.

        This is why AeroRF shows an age rather than presenting every
        marker as live: during an investigation, a position that is 90
        minutes old must not look current.
        """
        max_age = capture["stats"]["position_age_max_s"]
        assert max_age > 3600, (
            "expected real captures to include positions over an hour old; "
            "if this changes, re-check the staleness handling in the UI"
        )

    def test_age_is_none_without_a_reference_time(self, rows):
        for row in rows[:3]:
            assert parse_state_vector(row)["position_age_s"] is None


# ─── Capture statistics, as documentation ────────────────────────────────────

class TestCaptureStatistics:
    def test_representative_sample(self, capture):
        stats = capture["stats"]
        assert stats["captured_rows"] > 10000
        assert stats["with_position"] > stats["captured_rows"] * 0.9
        assert 0 < stats["on_ground"] < stats["captured_rows"] * 0.2

    def test_missing_altitude_is_common(self, capture):
        """~10% of aircraft publish no altitude at all."""
        rate = capture["stats"]["no_altitude"] / capture["stats"]["captured_rows"]
        assert 0.01 < rate < 0.25, (
            f"no-altitude rate changed to {rate:.1%}; the UI shows "
            f"'dato no disponible' for these"
        )
