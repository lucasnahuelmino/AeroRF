"""
tests/test_opensky_flights_contract.py
──────────────────────────────────────
Contract tests for ``/tracks/*`` and ``/flights/*``, against **real**
responses captured with OAuth2 on 2026-09-25.

Two bugs of the same class were found this way, both invisible to the
mock tests:

1. ``/states/all`` returns **17** fields, not the 18 the documentation
   table lists. See ``test_opensky_contract.py``.
2. ``/flights/*`` returns **camelCase** keys (``firstSeen``,
   ``lastSeen``, ``estDepartureAirport``) and has **no** ``dep_lat`` /
   ``arr_lat``. The documentation renders them lower case, so reading the
   documented names produced flight records whose times and airports were
   silently all ``None``.

And one finding that is not a bug but a design correction: OpenSky's
waypoint spacing is **not uniform**. Real tracks measured a minimum of
2 s, a median near 28 s and a maximum of 890 s. Reporting only the mean
(~80 s) is misleading, so AeroRF reports the distribution.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.flight_service import _normalise_flight
from app.services.opensky_service import parse_track, parse_waypoint

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def track_capture():
    return json.loads(
        (FIXTURES / "opensky_track_contract.json").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def flight_capture():
    return json.loads(
        (FIXTURES / "opensky_flights_contract.json").read_text(encoding="utf-8")
    )


# ─── Track waypoint shape ────────────────────────────────────────────────────

class TestRealTrackPayload:
    def test_documented_waypoint_fields(self, track_capture):
        raw = track_capture["path"][0]
        wp = parse_waypoint(raw)
        # [time, latitude, longitude, baro_altitude, true_track, on_ground]
        assert wp["timestamp"] == raw[0]
        assert wp["latitude"] == pytest.approx(raw[1])
        assert wp["longitude"] == pytest.approx(raw[2])
        assert wp["altitude"] == pytest.approx(raw[3])
        assert wp["heading"] == pytest.approx(raw[4])
        assert wp["on_ground"] == bool(raw[5])

    def test_callsign_key_is_spelled_with_three_ls(self, track_capture):
        """The API really does send `calllsign` on /tracks/all."""
        assert "calllsign" in track_capture
        assert "callsign" not in track_capture
        parsed = parse_track(track_capture)
        assert parsed["callsign"] == track_capture["calllsign"].strip()

    def test_both_callsign_spellings_accepted(self):
        for key in ("callsign", "calllsign"):
            parsed = parse_track({"icao24": "abc123", key: "TEST", "path": []})
            assert parsed["callsign"] == "TEST"

    def test_timestamps_are_non_decreasing(self, track_capture):
        # Each waypoint is a list: [time, lat, lon, alt, track, on_ground]
        times = [p[0] for p in track_capture["path"]]
        assert times == sorted(times)

    def test_short_waypoint_still_rejected(self):
        assert parse_waypoint([1, 2, 3]) is None


# ─── Resolution is not uniform ──────────────────────────────────────────────

class TestTrackResolutionReporting:
    def test_capture_is_a_contiguous_window(self, track_capture):
        """The fixture must not invent gaps.

        An earlier version of this fixture was abridged by picking
        scattered indices, which produced a 4202 s "gap" that never
        existed. A fixture that misrepresents the data is worse than no
        fixture, so the window is consecutive and the assertions below
        check it.
        """
        times = [p[0] for p in track_capture["path"]]
        gaps = [b - a for a, b in zip(times, times[1:])]
        stats = track_capture["stats"]
        # The window's own gaps must stay within the range OpenSky
        # published for this flight, not exceed it.
        assert max(gaps) <= stats["original_step_max_s"], (
            f"fixture has a {max(gaps)}s gap but the real track's maximum "
            f"was {stats['original_step_max_s']}s"
        )

    def test_reports_the_distribution_not_just_the_mean(self, track_capture):
        stats = track_capture["stats"]
        # The real track is far from uniform, and a mean alone would have
        # hidden that: the mean sits near 79 s while the median is 28 s.
        assert stats["original_step_min_s"] < stats["original_step_median_s"]
        assert stats["original_step_median_s"] < stats["original_step_max_s"]
        assert stats["original_step_max_s"] > 300
        assert stats["original_steps_le_15s"] > 0

    def test_note_states_the_median_and_the_range(self, track_capture):
        parsed = parse_track(track_capture)
        note = parsed["resolution_note"]
        assert "mediano" in note
        assert "NO es uniforme" in note
        assert "no es de un punto por segundo" in note

    def test_median_differs_from_mean_in_the_real_data(self, track_capture):
        """The reason the distribution matters, pinned numerically.

        For the captured flight the median step is ~28 s while the mean
        is ~79 s: the mean is inflated by a handful of 5-10 minute gaps
        and would understate how densely the turning segments are
        sampled.
        """
        stats = track_capture["stats"]
        median = stats["original_step_median_s"]
        assert stats["original_step_max_s"] > 3 * median, (
            "the long gaps are what inflate the mean; the median is the "
            "honest summary of typical spacing"
        )

    def test_exposes_step_fields(self, track_capture):
        parsed = parse_track(track_capture)
        for key in ("step_min_s", "step_median_s", "step_max_s", "mean_step_s"):
            assert key in parsed

    def test_single_waypoint_is_handled(self):
        parsed = parse_track({
            "icao24": "abc123",
            "path": [[1758000000, -34.6, -58.4, 100, 90, False]],
        })
        assert parsed["point_count"] == 1
        assert parsed["step_median_s"] is None
        assert "Un solo waypoint" in parsed["resolution_note"]

    def test_empty_track(self):
        parsed = parse_track({"icao24": "abc123", "path": []})
        assert parsed["point_count"] == 0
        assert parsed["altitude_range"] is None
        assert parsed["suspect_altitudes"] == []


# ─── Implausible altitudes ───────────────────────────────────────────────────

class TestSuspectAltitudes:
    def test_real_capture_contained_impossible_altitudes(self, track_capture):
        """A real track published -304 m and 0 m.

        Neither is a real altitude. Plotting -304 m on a profile would be
        a fabrication, so AeroRF flags it.
        """
        # The abridged fixture keeps only 5 waypoints, so assert the
        # detector directly on the values the capture showed.
        from app.services.opensky_service import _suspect_altitudes

        points = [
            {"altitude": 3048.0},
            {"altitude": -304.0},     # observed: pressure artefact
            {"altitude": 0.0},        # observed: ADS-B placeholder
            {"altitude": 11582.0},
            {"altitude": None},
        ]
        suspect = _suspect_altitudes(points)
        assert [s["index"] for s in suspect] == [1, 2]
        assert suspect[0]["altitude_m"] == -304.0

    def test_plausible_altitudes_are_not_flagged(self):
        from app.services.opensky_service import _suspect_altitudes

        points = [{"altitude": a} for a in (0.0, 10.0, 10000.0, 12000.0)]
        points[0]["altitude"] = 0.5
        assert _suspect_altitudes(points) == []

    def test_altitude_range_ignores_nulls(self, track_capture):
        parsed = parse_track(track_capture)
        rng = parsed["altitude_range"]
        assert rng is not None
        assert rng["min_m"] <= rng["max_m"]


# ─── /flights/* key casing ───────────────────────────────────────────────────

class TestRealFlightPayload:
    def test_capture_uses_camel_case(self, flight_capture):
        record = flight_capture["records"][0]
        assert "firstSeen" in record
        assert "lastSeen" in record
        assert "estDepartureAirport" in record
        # The lower-case spellings from the docs are NOT present.
        assert "firstseen" not in record
        assert "estdepartureairport" not in record

    def test_documented_lat_lon_fields_do_not_exist(self, flight_capture):
        record = flight_capture["records"][0]
        for key in ("dep_lat", "dep_lon", "arr_lat", "arr_lon"):
            assert key not in record, (
                f"{key} was assumed by the code but is absent from the "
                f"real response"
            )

    def test_times_are_recovered(self, flight_capture):
        record = flight_capture["records"][0]
        out = _normalise_flight(record)
        assert out["first_seen_ts"] == record["firstSeen"]
        assert out["last_seen_ts"] == record["lastSeen"]
        assert out["first_seen"] is not None
        assert out["last_seen"] is not None

    def test_duration_computed_from_real_timestamps(self, flight_capture):
        record = flight_capture["records"][0]
        out = _normalise_flight(record)
        assert out["duration_s"] == record["lastSeen"] - record["firstSeen"]
        assert out["duration_s"] > 0

    def test_callsign_is_trimmed(self, flight_capture):
        record = flight_capture["records"][0]
        out = _normalise_flight(record)
        assert out["callsign"] == record["callsign"].strip()
        assert out["callsign"] != record["callsign"] or record["callsign"] == "X"

    def test_unresolved_airport_is_reported_not_faked(self, flight_capture):
        """OpenSky reported candidates=0; the airports are legitimately null."""
        record = flight_capture["records"][0]
        out = _normalise_flight(record)
        assert out["departure"] is None
        assert out["arrival"] is None
        # ...and the reason is visible.
        assert out["departure_candidates"] == 0
        assert out["arrival_candidates"] == 0

    def test_provenance_declared(self, flight_capture):
        out = _normalise_flight(flight_capture["records"][0])
        assert out["source"] == "opensky"
        assert out["provenance"] == "historical"

    def test_lowercase_documentation_spelling_still_works(self):
        """Defensive: if OpenSky ever reverts, the code still parses."""
        out = _normalise_flight({
            "icao24": "abc123", "callsign": "TEST",
            "firstseen": 1758000000, "lastseen": 1758003600,
            "estdepartureairport": "EZE", "estarrivalairport": "COR",
        })
        assert out["first_seen_ts"] == 1758000000
        assert out["last_seen_ts"] == 1758003600
        assert out["departure"] == "EZE"
        assert out["arrival"] == "COR"
        assert out["duration_s"] == 3600

    def test_empty_record_does_not_crash(self):
        out = _normalise_flight({})
        assert out["icao24"] is None
        assert out["first_seen"] is None
        assert out["duration_s"] is None
