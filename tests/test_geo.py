"""
tests/test_geo.py
─────────────────
Unit tests for units and geometry (spec §52: NM/KM conversion, distance
calculations, circle generation, radial generation).

These are the numbers an ENACOM report is built on, so they are checked
against the exact international definition and against independently
computed reference values, not against whatever the code happens to do.
"""

from __future__ import annotations

import math

import pytest

from app.core import geo, units


# ─── NM / KM / metres (spec §10, §13) ──────────────────────────────────────

class TestUnitConversion:
    def test_nm_to_km_is_exact(self):
        """20 NM must be 37.04 km, per the spec's worked example."""
        assert units.nm_to_km(20) == pytest.approx(37.04, abs=1e-9)

    def test_nm_to_metres_is_exact(self):
        assert units.nm_to_m(20) == pytest.approx(37040.0, abs=1e-9)
        assert units.nm_to_m(1) == pytest.approx(1852.0, abs=1e-9)

    def test_km_to_nm_roundtrip(self):
        for value in (1, 5, 20, 50, 100, 37.04):
            assert units.km_to_nm(units.nm_to_km(value)) == pytest.approx(value)

    def test_m_to_nm(self):
        assert units.m_to_nm(1852.0) == pytest.approx(1.0)

    def test_convert_between_any_pair(self):
        assert units.convert(20, "nm", "km") == pytest.approx(37.04)
        assert units.convert(37.04, "km", "nm") == pytest.approx(20.0)
        assert units.convert(37040, "m", "nm") == pytest.approx(20.0)

    @pytest.mark.parametrize(
        "alias,expected",
        [
            ("NM", "nm"), ("nm", "nm"), ("nmi", "nm"),
            ("milla náutica", "nm"), ("Millas Náuticas", "nm"),
            ("km", "km"), ("kilómetros", "km"), ("KMS", "km"),
            ("m", "m"), ("metros", "m"), ("mts", "m"),
            ("  Nm  ", "nm"),
        ],
    )
    def test_alias_resolution(self, alias, expected):
        assert units.normalise_unit(alias) == expected

    def test_unknown_unit_falls_back_to_nm(self):
        """A typo must not silently produce a wrong distance."""
        assert units.normalise_unit("furlongs") == "nm"
        assert units.normalise_unit(None) == "nm"
        assert units.normalise_unit("") == "nm"

    def test_format_distance_shows_both_units(self):
        text = units.format_distance(37040.0, "nm")
        assert "20.00 NM" in text
        assert "37.04 km" in text

    def test_nm_to_feet(self):
        assert units.nm_to_feet(1) == pytest.approx(6076.1155, abs=1e-3)


# ─── Azimuth ─────────────────────────────────────────────────────────────────

class TestAzimuth:
    @pytest.mark.parametrize(
        "raw,expected",
        [(0, 0.0), (90, 90.0), (359, 359.0), (360, 0.0),
         (450, 90.0), (-90, 270.0), (-1, 359.0), (720, 0.0)],
    )
    def test_normalise(self, raw, expected):
        assert units.normalise_azimuth(raw) == pytest.approx(expected)

    def test_compass_points(self):
        assert units.compass_point(0) == "N"
        assert units.compass_point(90) == "E"
        assert units.compass_point(180) == "S"
        assert units.compass_point(270) == "W"
        assert units.compass_point(135) == "SE"

    def test_sector_containment(self):
        # The function measures *clockwise* from the reference, so a 60°
        # sector at 90° covers 90°..150°, not 30°..150°.
        assert units.is_clockwise_from(90, 90, 60) is True
        assert units.is_clockwise_from(100, 90, 60) is True
        assert units.is_clockwise_from(150, 90, 60) is True
        assert units.is_clockwise_from(151, 90, 60) is False
        assert units.is_clockwise_from(30, 90, 60) is False
        # Wraps past north: 10° is 20° clockwise from 350°.
        assert units.is_clockwise_from(10, 350, 60) is True
        assert units.is_clockwise_from(100, 350, 60) is False
        assert units.is_clockwise_from(100, 90, 360) is True


# ─── Distance ────────────────────────────────────────────────────────────────

class TestDistance:
    def test_haversine_zero(self):
        assert geo.haversine_m(-34.6, -58.4, -34.6, -58.4) == pytest.approx(0.0)

    def test_known_distance_buenos_aires_to_cordoba(self):
        """EZE → COR (SAEZ–SACOD) is about 653 km great-circle."""
        d = geo.haversine_m(-34.8222, -58.5358, -31.3208, -64.1888)
        assert d == pytest.approx(653_000, rel=0.005)

    def test_one_degree_latitude_about_111_km(self):
        d = geo.haversine_m(0.0, 0.0, 1.0, 0.0)
        assert d == pytest.approx(111_195, rel=0.001)

    def test_symmetry(self):
        a = geo.haversine_m(-34.6, -58.4, -34.5, -58.3)
        b = geo.haversine_m(-34.5, -58.3, -34.6, -58.4)
        assert a == pytest.approx(b)

    def test_antipodal_does_not_crash(self):
        """asin's domain guard must hold at the antipodes."""
        d = geo.haversine_m(0.0, 0.0, 0.0, 180.0)
        assert math.pi * geo.EARTH_RADIUS_M == pytest.approx(d, rel=1e-6)

    def test_distance_to_object_without_position_is_none(self):
        """Unknown position must be None, never 0.0 (spec §56)."""
        assert geo.distance_to_object_m(-34.6, -58.4, None, None) is None
        assert geo.distance_to_object_m(-34.6, -58.4, -34.5, None) is None

    def test_distance_to_object_valid(self):
        d = geo.distance_to_object_m(-34.6, -58.4, -34.7, -58.4)
        assert d is not None and d > 0


# ─── Bearing and destination ─────────────────────────────────────────────────

class TestBearing:
    def test_due_east_is_90(self):
        assert geo.initial_bearing(0.0, 0.0, 0.0, 1.0) == pytest.approx(90.0)

    def test_due_north_is_0(self):
        assert geo.initial_bearing(0.0, 0.0, 1.0, 0.0) == pytest.approx(0.0)

    def test_due_south_is_180(self):
        assert geo.initial_bearing(1.0, 0.0, 0.0, 0.0) == pytest.approx(180.0)

    def test_destination_20nm_east_azimuth_90(self):
        """The spec's worked example: origin + 90° + 20 NM."""
        lat, lon = geo.destination_point(-34.603722, -58.381592, 90, 37040)
        # Latitude barely changes; longitude advances by ~0.4055°.
        assert lat == pytest.approx(-34.603722, abs=0.001)
        assert lon == pytest.approx(-58.381592 + 0.4055, abs=0.002)
        # And the distance is exactly 20 NM back.
        back = geo.haversine_m(-34.603722, -58.381592, lat, lon)
        assert back == pytest.approx(37040.0, rel=1e-6)

    def test_destination_zero_distance(self):
        assert geo.destination_point(-34.6, -58.4, 45, 0) == (-34.6, -58.4)

    def test_destination_roundtrip_all_bearings(self):
        for bearing in range(0, 360, 15):
            lat, lon = geo.destination_point(-34.6, -58.4, bearing, 50_000)
            assert -90 <= lat <= 90
            assert -180 <= lon <= 180
            back = geo.initial_bearing(-34.6, -58.4, lat, lon)
            assert back == pytest.approx(bearing, abs=0.5)

    def test_destination_normalises_longitude(self):
        _, lon = geo.destination_point(0.0, 179.9, 90, 200_000)
        assert -180 <= lon <= 180

    def test_midpoint(self):
        lat, lon = geo.midpoint(0.0, 0.0, 0.0, 2.0)
        assert lat == pytest.approx(0.0, abs=1e-9)
        assert lon == pytest.approx(1.0, abs=0.001)

    def test_midpoint_of_identical_points(self):
        assert geo.midpoint(-34.6, -58.4, -34.6, -58.4) == (-34.6, -58.4)


# ─── Circles (spec §10, §36) ────────────────────────────────────────────────

class TestCircleGeneration:
    def test_vertex_count(self):
        pts = geo.circle_points(-34.6, -58.4, 10_000, steps=72)
        assert len(pts) == 72

    def test_minimum_steps_enforced(self):
        assert len(geo.circle_points(-34.6, -58.4, 100, steps=1)) >= 8

    def test_every_vertex_is_on_the_radius(self):
        radius = 18_520.0  # 10 NM
        for lat, lon in geo.circle_points(-34.6, -58.4, radius, steps=24):
            assert geo.haversine_m(-34.6, -58.4, lat, lon) == pytest.approx(
                radius, rel=1e-6
            )

    def test_zero_radius(self):
        assert geo.circle_points(-34.6, -58.4, 0) == [(-34.6, -58.4)]

    def test_negative_radius_rejected(self):
        with pytest.raises(ValueError):
            geo.circle_points(-34.6, -58.4, -1)

    def test_bounds_contain_the_circle(self):
        bbox = geo.circle_bounds(-34.6, -58.4, 37_040)
        south, west = bbox[0]
        north, east = bbox[1]
        assert south < -34.6 < north
        assert west < -58.4 < east

    def test_bounds_pad_longitude_more_than_latitude(self):
        # Away from the equator a degree of longitude is shorter than a
        # degree of latitude, so the box must be wider in longitude.
        (s, w), (n, e) = geo.circle_bounds(-34.6, -58.4, 100_000)
        assert (n - s) < (e - w)

    def test_bounds_padding_equal_at_the_equator(self):
        (s, w), (n, e) = geo.circle_bounds(0.0, 0.0, 100_000)
        assert (n - s) == pytest.approx(e - w)


# ─── Radials (spec §11, §37) ────────────────────────────────────────────────

class TestRadialGeneration:
    def test_geometry_shape(self):
        r = geo.radial_geometry(-34.603722, -58.381592, 135, 55_560, steps=4)
        assert r["azimuth"] == pytest.approx(135.0)
        assert r["length_m"] == pytest.approx(55_560.0)
        assert len(r["coordinates"]) == 5
        assert r["origin"] == {
            "latitude": pytest.approx(-34.603722),
            "longitude": pytest.approx(-58.381592),
        }

    def test_end_point_is_at_the_requested_distance(self):
        r = geo.radial_geometry(-34.6, -58.4, 270, 37_040, steps=4)
        d = geo.haversine_m(-34.6, -58.4, r["end"]["latitude"], r["end"]["longitude"])
        assert d == pytest.approx(37_040.0, rel=1e-6)

    def test_intermediate_vertices_follow_the_curve(self):
        """A radial must not be a straight Cartesian line."""
        pts = geo.radial_geometry(0.0, 0.0, 90, 1_000_000, steps=8)["coordinates"]
        latitudes = [p[0] for p in pts]
        # Going east along a great circle from the equator curves north.
        assert latitudes[-1] > latitudes[0]

    def test_azimuth_wrapped(self):
        r = geo.radial_geometry(-34.6, -58.4, 405, 10_000)
        assert r["azimuth"] == pytest.approx(45.0)


# ─── Paths and traces (spec §12) ────────────────────────────────────────────

class TestPath:
    PATH = [[-34.603722, -58.381592], [-34.5, -58.3], [-34.4, -58.2]]

    def test_length_positive(self):
        assert geo.path_length_m(self.PATH) > 0

    def test_length_matches_sum_of_segments(self):
        segments = geo.segment_bearings(self.PATH)
        assert geo.path_length_m(self.PATH) == pytest.approx(
            sum(s["length_m"] for s in segments)
        )

    def test_summary_units_agree(self):
        s = geo.path_summary(self.PATH)
        assert s["total_length_km"] * 1000 == pytest.approx(s["total_length_m"])
        assert s["total_length_nm"] * 1852 == pytest.approx(s["total_length_m"])

    def test_summary_segment_count(self):
        assert geo.path_summary(self.PATH)["segment_count"] == 2
        assert geo.path_summary(self.PATH)["point_count"] == 3

    def test_summary_start_and_end(self):
        s = geo.path_summary(self.PATH)
        assert s["start"] == self.PATH[0]
        assert s["end"] == self.PATH[-1]

    def test_empty_path(self):
        s = geo.path_summary([])
        assert s["point_count"] == 0
        assert s["total_length_m"] == 0

    def test_bearing_of_eastward_segment_is_90(self):
        s = geo.segment_bearings([[0.0, 0.0], [0.0, 1.0]])
        assert s[0]["bearing"] == pytest.approx(90.0)

    def test_bounds(self):
        bbox = geo.bounds_of(self.PATH)
        assert bbox == [[-34.603722, -58.381592], [-34.4, -58.2]]

    def test_bounds_of_empty_is_none(self):
        assert geo.bounds_of([]) is None

    def test_interpolate_along(self):
        lat, lon = geo.interpolate_along(0.0, 0.0, 0.0, 2.0, 0.5)
        assert lon == pytest.approx(1.0)
        # Clamped outside [0, 1].
        assert geo.interpolate_along(0.0, 0.0, 0.0, 2.0, 5.0)[1] == pytest.approx(2.0)


# ─── Validation and formatting (spec §5) ────────────────────────────────────

class TestValidation:
    @pytest.mark.parametrize(
        "lat,lon,valid",
        [
            (0, 0, True), (-34.6, -58.4, True), (90, 180, True),
            (-90, -180, True), (91, 0, False), (0, 181, False),
            (float("nan"), 0, False), (0, float("inf"), False),
            ("a", 0, False), (None, None, False),
        ],
    )
    def test_valid_latlon(self, lat, lon, valid):
        assert geo.valid_latlon(lat, lon) is valid

    def test_require_raises(self):
        with pytest.raises(ValueError):
            geo.require_latlon(91, 0)


class TestCoordinateFormatting:
    def test_decimal_default(self):
        text = geo.format_latlon(-34.603722, -58.381592)
        assert text == "LAT -34.603722  LON -58.381592"

    def test_decimal_six_places(self):
        text = geo.format_latlon(-34.6, -58.4)
        assert "-34.600000" in text and "-58.400000" in text

    def test_dms_southern_western_hemisphere(self):
        text = geo.format_latlon(-34.603722, -58.381592, "dms")
        assert "S" in text and "W" in text
        assert "°" in text and "'" in text and '"' in text

    def test_dms_value(self):
        # -34.603722 = 34°36'13.4"S
        assert geo.format_dms(-34.603722, True) == '34°36\'13.40"S'

    def test_dmm(self):
        text = geo.format_coordinate(34.5, True, "dmm")
        assert text.startswith("34°30.000")

    def test_none_coordinates(self):
        assert "—" in geo.format_latlon(None, None)
        assert "—" in geo.format_latlon(-34.6, None)

    def test_parse_decimal(self):
        assert geo.parse_coordinate("-34.603722") == pytest.approx(-34.603722)

    def test_parse_dms(self):
        parsed = geo.parse_coordinate('34°36\'13.40"S')
        assert parsed == pytest.approx(-34.603722, abs=1e-5)

    def test_parse_invalid_returns_none(self):
        assert geo.parse_coordinate("") is None
        assert geo.parse_coordinate("not a coordinate") is None
        assert geo.parse_coordinate(None) is None
