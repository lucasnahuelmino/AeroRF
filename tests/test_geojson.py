"""
tests/test_geojson.py
────────────────────
GeoJSON conversion both ways (spec §17, §52).

The checks that matter most are the ones that catch a silently mirrored
map: GeoJSON is ``[lon, lat]`` and Leaflet is ``[lat, lon]``, and a
regression there would place every object on the wrong side of the world
while still looking plausible.
"""

from __future__ import annotations

import json

import pytest

from app.services import geojson_service as gjs

# EZE (Ministro Pistarini)
EZE = (-34.8222, -58.5358)


# ─── Coordinate order ────────────────────────────────────────────────────────

class TestCoordinateOrder:
    def test_leaflet_to_geojson(self):
        assert gjs.leaflet_to_geojson_coord([-34.6, -58.4]) == [-58.4, -34.6]

    def test_geojson_to_leaflet(self):
        assert gjs.geojson_to_leaflet_coord([-58.4, -34.6]) == [-34.6, -58.4]

    def test_roundtrip(self):
        original = [-34.603722, -58.381592]
        assert gjs.geojson_to_leaflet_coord(
            gjs.leaflet_to_geojson_coord(original)
        ) == original

    def test_bulk_conversion(self):
        pts = [[-34.6, -58.4], [-34.5, -58.3]]
        assert gjs.latlngs_to_geojson(pts) == [[-58.4, -34.6], [-58.3, -34.5]]
        assert gjs.geojson_to_latlngs([[-58.4, -34.6], [-58.3, -34.5]]) == pts

    def test_malformed_points_dropped(self):
        assert gjs.latlngs_to_geojson([[-34.6], None, [-34.5, -58.3]]) == [
            [-58.3, -34.5]
        ]


# ─── Geometry builders ───────────────────────────────────────────────────────

class TestGeometryBuilders:
    def test_point_geometry(self):
        g = gjs.point_geometry(-34.6, -58.4)
        assert g["type"] == "Point"
        assert g["coordinates"] == [-58.4, -34.6]

    def test_point_geometry_rejects_bad_input(self):
        assert gjs.point_geometry(91, -58.4) is None
        assert gjs.point_geometry(-34.6, 181) is None

    def test_line_geometry(self):
        g = gjs.line_geometry([[-34.6, -58.4], [-34.5, -58.3]])
        assert g["type"] == "LineString"
        assert g["coordinates"] == [[-58.4, -34.6], [-58.3, -34.5]]

    def test_line_needs_two_points(self):
        assert gjs.line_geometry([[-34.6, -58.4]]) is None
        assert gjs.line_geometry([]) is None

    def test_polygon_geometry_closes_the_ring(self):
        ring = [[-34.6, -58.4], [-34.5, -58.4], [-34.5, -58.3]]
        g = gjs.polygon_geometry(ring)
        assert g["type"] == "Polygon"
        assert g["coordinates"][0][0] == g["coordinates"][0][-1]
        assert len(g["coordinates"][0]) == 4

    def test_polygon_needs_three_points(self):
        assert gjs.polygon_geometry([[-34.6, -58.4], [-34.5, -58.4]]) is None

    def test_already_closed_ring_not_duplicated(self):
        ring = [[-34.6, -58.4], [-34.5, -58.4], [-34.5, -58.3], [-34.6, -58.4]]
        g = gjs.polygon_geometry(ring)
        assert len(g["coordinates"][0]) == 4

    def test_circle_geometry_is_a_closed_polygon(self):
        g = gjs.circle_geometry(-34.6, -58.4, 37_040, steps=72)
        assert g["type"] == "Polygon"
        ring = g["coordinates"][0]
        assert len(ring) == 73           # 72 + closing vertex
        assert ring[0] == ring[-1]

    def test_circle_vertices_at_the_right_radius(self):
        from app.core.geo import haversine_m

        g = gjs.circle_geometry(-34.6, -58.4, 18_520, steps=12)
        for lon, lat in g["coordinates"][0][:-1]:
            assert haversine_m(-34.6, -58.4, lat, lon) == pytest.approx(
                18_520, rel=1e-6
            )

    def test_circle_rejects_zero_or_negative_radius(self):
        assert gjs.circle_geometry(-34.6, -58.4, 0) is None
        assert gjs.circle_geometry(-34.6, -58.4, -5) is None

    def test_radial_geometry_is_a_line(self):
        g = gjs.radial_geometry(-34.6, -58.4, 135, 55_560, steps=4)
        assert g["type"] == "LineString"
        assert len(g["coordinates"]) == 5

    def test_radial_start_is_the_origin(self):
        g = gjs.radial_geometry(-34.6, -58.4, 135, 55_560, steps=4)
        assert g["coordinates"][0] == [-58.4, -34.6]


# ─── Inbound parsing ─────────────────────────────────────────────────────────

class TestInboundParsing:
    def test_point_feature(self):
        p = gjs.geojson_feature_to_object_params(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-58.4, -34.6]},
                "properties": {"name": "Punto", "category": "Referencia"},
            }
        )
        assert p["latitude"] == pytest.approx(-34.6)
        assert p["longitude"] == pytest.approx(-58.4)
        assert p["name"] == "Punto"
        assert p["category"] == "Referencia"
        assert p["geometry_type"] == "Point"

    def test_line_feature(self):
        p = gjs.geojson_feature_to_object_params(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-58.4, -34.6], [-58.3, -34.5]],
                },
                "properties": {},
            }
        )
        assert p["path"] == [[-34.6, -58.4], [-34.5, -58.3]]
        assert p["latitude"] == pytest.approx(-34.6)  # anchored at the first vertex

    def test_polygon_feature_unwraps_the_ring(self):
        p = gjs.geojson_feature_to_object_params(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-58.4, -34.6], [-58.4, -34.5],
                        [-58.3, -34.5], [-58.4, -34.6],
                    ]],
                },
                "properties": {},
            }
        )
        assert len(p["ring"]) == 3       # closing vertex removed
        assert p["geometry_type"] == "Polygon"

    def test_loose_latlng_shape_from_the_map_tools(self):
        p = gjs.geojson_feature_to_object_params(
            {"latlng": [-34.6, -58.4], "properties": {"name": "Suelto"}}
        )
        assert p["latitude"] == pytest.approx(-34.6)
        assert p["longitude"] == pytest.approx(-58.4)

    def test_loose_lat_lon_shape(self):
        p = gjs.geojson_feature_to_object_params(
            {"lat": -34.6, "lon": -58.4, "properties": {}}
        )
        assert p["latitude"] == pytest.approx(-34.6)

    def test_circle_properties_are_read(self):
        p = gjs.geojson_feature_to_object_params(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-58.4, -34.6]},
                "properties": {"radius": 20, "radius_unit": "nm"},
            }
        )
        assert p["radius"] == 20
        assert p["radius_unit"] == "nm"

    def test_extra_properties_are_preserved(self):
        p = gjs.geojson_feature_to_object_params(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-58.4, -34.6]},
                "properties": {"name": "X", "custom_field": "kept",
                               "another": 42},
            }
        )
        assert p["properties"].get("custom_field") == "kept"
        assert p["properties"].get("another") == 42

    def test_no_geometry(self):
        p = gjs.geojson_feature_to_object_params({"properties": {"name": "X"}})
        assert p["latitude"] is None
        assert p["longitude"] is None


# ─── Serialisation (spec §17, §46) ──────────────────────────────────────────

class TestSerialisation:
    def test_dumps_preserves_spanish_accents(self):
        text = gjs.dumps({"name": "Fuente interferente nº1 —ción"})
        assert "ó" in text and "—" in text
        assert json.loads(text)["name"].startswith("Fuente interferente")

    def test_object_to_leaflet_point(self, db):
        from app.services import map_service as svc

        obj = svc.create_object(
            db, "point", name="P", latitude=-34.6, longitude=-58.4
        )
        payload = gjs.object_to_leaflet(obj)
        assert payload["geometry_type"] == "Point"
        # Leaflet order for a point is the bare [lat, lon] pair.
        assert payload["latlng"] == pytest.approx([-34.6, -58.4])
        assert payload["latlngs"] == [[pytest.approx(-34.6), pytest.approx(-58.4)]]
        assert payload["id"] == obj.id
        assert payload["type"] == "point"

    def test_object_to_leaflet_circle_metrics(self, db):
        from app.services import map_service as svc

        obj = svc.create_object(
            db, "circle", latitude=-34.6, longitude=-58.4,
            radius=20, radius_unit="nm",
        )
        payload = gjs.object_to_leaflet(obj)
        assert payload["metrics"]["radius_m"] == pytest.approx(37_040.0)
        assert payload["metrics"]["radius_km"] == pytest.approx(37.04)
        assert payload["radius"] == 20
        assert payload["radius_unit"] == "nm"

    def test_object_to_leaflet_radial(self, db):
        from app.services import map_service as svc

        obj = svc.create_object(
            db, "radial", latitude=-34.6, longitude=-58.4,
            azimuth=135, length_value=30, length_unit="nm",
        )
        payload = gjs.object_to_leaflet(obj)
        assert payload["radial"]["azimuth"] == pytest.approx(135.0)
        assert payload["radial"]["length_m"] == pytest.approx(55_560.0)
        assert payload["azimuth"] == 135
        assert len(payload["radial"]["end"]) == 2

    def test_polygon_ring_is_unwrapped_for_leaflet(self, db):
        from app.services import map_service as svc

        obj = svc.create_object(
            db, "polygon", latitude=-34.6, longitude=-58.4,
            properties={"ring": [[-34.6, -58.4], [-34.5, -58.4], [-34.5, -58.3]]},
        )
        payload = gjs.object_to_leaflet(obj)
        assert payload["geometry_type"] == "Polygon"
        # Leaflet closes the ring itself, so the duplicate must be gone.
        assert len(payload["latlngs"]) == 3
        assert payload["latlngs"][0] != payload["latlngs"][-1]

    def test_line_metrics_computed_server_side(self, db):
        from app.services import map_service as svc

        obj = svc.create_object(
            db, "trace", latitude=-34.6, longitude=-58.4,
            properties={"path": [[-34.6, -58.4], [-34.5, -58.3]]},
        )
        payload = gjs.object_to_leaflet(obj)
        assert payload["metrics"]["total_length_nm"] > 0
        assert payload["metrics"]["total_length_km"] == pytest.approx(
            payload["metrics"]["total_length_m"] / 1000
        )

    def test_feature_collection_skips_objects_without_geometry(self, db):
        from app.models.map_object import MapObject
        from app.services import map_service as svc

        good = svc.create_object(db, "point", latitude=-34.6, longitude=-58.4)
        # A deliberately positionless object: it exists but cannot be drawn.
        bad = MapObject(type="point", name="Sin posición")
        db.add(bad)
        db.commit()

        collection = gjs.objects_to_feature_collection([good, bad])
        assert collection["type"] == "FeatureCollection"
        assert len(collection["features"]) == 1
        assert collection["features"][0]["id"] == good.id

    def test_feature_properties_are_self_describing(self, db):
        from app.services import map_service as svc

        obj = svc.create_object(
            db, "rf_source", name="Fuente #1", latitude=-34.6, longitude=-58.4,
            rf={"kind": "FM", "frequency_mhz": 98.1, "power_dbm": -55},
        )
        feature = gjs.object_to_feature(obj)
        props = feature["properties"]
        for key in ("id", "type", "name", "status", "created_at", "source"):
            assert key in props
        assert props["rf"]["frequency_mhz"] == 98.1
        assert props["provenance"] if "provenance" in props else True

    def test_notes_are_embedded(self, db):
        from app.services import map_service as svc

        obj = svc.create_object(db, "point", latitude=-34.6, longitude=-58.4)
        svc.add_note(db, obj.id, "Fuente apagada.")
        svc.add_note(db, obj.id, "Se reactivó.")

        obj = svc.get_object(db, obj.id)
        props = gjs.object_to_feature(obj)["properties"]
        assert [n["text"] for n in props["notes"]] == [
            "Fuente apagada.", "Se reactivó."
        ]

    def test_history_included_on_request(self, db):
        from app.services import map_service as svc

        obj = svc.create_object(db, "point", latitude=-34.6, longitude=-58.4)
        svc.set_status(db, obj.id, "Apagado")
        obj = svc.get_object(db, obj.id)

        without = gjs.object_to_feature(obj, include_history=False)
        assert "history" not in without["properties"]
        with_hist = gjs.object_to_feature(obj, include_history=True)
        fields = [h["field"] for h in with_hist["properties"]["history"]]
        assert "status" in fields
