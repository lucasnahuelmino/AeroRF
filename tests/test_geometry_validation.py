"""
tests/test_geometry_validation.py
──────────────────────────────────
Geometry is validated on the way in, not only on the way out.

Two real defects motivated this file, and both are the kind that hide:

1. Nothing validated a submitted geometry. Reading one assumed it was well
   formed, so a ring stored with flat numbers raised ``TypeError`` and the
   whole ``GET /map/objects`` returned 500. One bad object removed every
   object from the map.
2. The frontend tools speak Leaflet's ``[lat, lon]`` and the API speaks
   GeoJSON's ``[lon, lat]``. Nothing translated between them, so a line drawn
   on the map was created with **zero points**: the request succeeded, an id
   came back, and an empty object appeared. ``latlngs`` is not a field the
   schema declares, so Pydantic dropped it without a word.

These are unit tests against the service. The HTTP round trip is covered in
``tests/smoke_e2e.py``, which needs the backend running, because this repo
deliberately keeps the default suite free of a live server.
"""
import pytest

from app.services import geojson_service as gjs
from app.services.geojson_service import GeometryError, validate_geometry


# ─── The validator: what it accepts ─────────────────────────────────────────

def test_none_passes_through():
    # A circle carries no submitted geometry; the backend builds its ring.
    assert validate_geometry(None) is None


def test_accepts_a_well_formed_point():
    g = {"type": "Point", "coordinates": [-58.4, -34.6]}
    assert validate_geometry(g) is g


def test_accepts_a_well_formed_linestring():
    g = {"type": "LineString", "coordinates": [[-58.4, -34.6], [-58.3, -34.5]]}
    assert validate_geometry(g) is g


def test_accepts_a_closed_polygon_ring():
    g = {
        "type": "Polygon",
        "coordinates": [[[-58.9, -34.9], [-58.9, -34.8], [-58.8, -34.8], [-58.9, -34.9]]],
    }
    assert validate_geometry(g) is g


# ─── The validator: what it rejects ─────────────────────────────────────────

def test_rejects_a_linestring_with_one_vertex():
    with pytest.raises(GeometryError, match="al menos 2"):
        validate_geometry({"type": "LineString", "coordinates": [[-58.4, -34.6]]})


def test_rejects_an_unclosed_polygon_ring():
    with pytest.raises(GeometryError, match="cerrado"):
        validate_geometry({
            "type": "Polygon",
            "coordinates": [[[-58.9, -34.9], [-58.9, -34.8], [-58.8, -34.8]]],
        })


def test_rejects_a_polygon_with_too_few_positions():
    with pytest.raises(GeometryError, match="al menos 3"):
        validate_geometry({
            "type": "Polygon",
            "coordinates": [[[-58.9, -34.9], [-58.9, -34.9]]],
        })


def test_rejects_an_empty_polygon():
    with pytest.raises(GeometryError, match="anillos"):
        validate_geometry({"type": "Polygon", "coordinates": []})


@pytest.mark.parametrize(
    "coordinates",
    [
        [[181.0, 0.0], [0.0, 0.0]],   # longitude out of range
        [[0.0, 91.0], [1.0, 1.0]],    # latitude out of range
    ],
)
def test_rejects_out_of_range_coordinates(coordinates):
    with pytest.raises(GeometryError, match="fuera de rango"):
        validate_geometry({"type": "LineString", "coordinates": coordinates})


def test_the_range_message_states_the_coordinate_order():
    # [lat, lon] submitted where [lon, lat] is expected is the most common
    # mistake at this boundary, and GeoJSON accepts it silently. The message
    # is the only place the operator finds out.
    with pytest.raises(GeometryError) as exc:
        validate_geometry({"type": "LineString", "coordinates": [[200.0, -34.6], [-58.3, -34.5]]})
    assert "longitud" in str(exc.value)
    assert "latitud" in str(exc.value)


def test_rejects_a_position_that_is_not_a_pair():
    with pytest.raises(GeometryError, match="posici"):
        validate_geometry({"type": "LineString", "coordinates": [[0.0], [1.0, 1.0]]})


def test_rejects_non_numeric_coordinates():
    with pytest.raises(GeometryError, match="num"):
        validate_geometry({"type": "LineString", "coordinates": [["a", "b"], [1.0, 1.0]]})


def test_rejects_an_unknown_geometry_type():
    with pytest.raises(GeometryError, match="no soportado"):
        validate_geometry({"type": "Nonsense", "coordinates": []})


def test_rejects_a_geometry_that_is_not_an_object():
    with pytest.raises(GeometryError, match="debe ser un objeto"):
        validate_geometry("not a dict")


def test_rejects_a_geometry_without_coordinates():
    with pytest.raises(GeometryError, match="coordinates"):
        validate_geometry({"type": "Point", "coordinates": None})


# ─── Reading is defensive even though writing is validated ─────────────────

class _FakeObj:
    """Minimal stand-in for MapObject, carrying what the reader touches."""

    def __init__(self, object_id, geometry, object_type="line", name="x"):
        self.id = object_id
        self.type = object_type
        self.name = name
        self.description = None
        self.category = None
        self.status = "Activo"
        self.color = "#3b82f6"
        self.icon = None
        self.label = None
        self.opacity = 1.0
        self.weight = 2
        self.fill_opacity = 0.15
        self.show_label = True
        self.visible = True
        self.locked = False
        self.z_index = 0
        self.layer_id = None
        self.layer = None
        self.expediente = None
        self.expediente_id = None
        self.latitude = None
        self.longitude = None
        self.radius = None
        self.radius_unit = None
        self.azimuth = None
        self.length_value = None
        self.length_unit = None
        self.source = "user"
        # The model names these in Spanish; the serializer reads them by those
        # names, so the double has to match or the test fails on the double
        # rather than on the behaviour under test.
        self.fecha_creacion = None
        self.fecha_actualizacion = None
        self.observed_at = None
        self.valid_from = None
        self.valid_to = None
        self.properties = None
        self.geometry = geometry
        self.geometry_type = (geometry or {}).get("type")


def test_a_broken_stored_object_does_not_raise():
    # This is the exact shape that used to produce a 500 on the whole listing.
    broken = _FakeObj(7, {"type": "Polygon", "coordinates": [[-58.9, -34.9, 0.0]]}, "polygon")
    assert gjs.object_to_leaflet(broken) is None


def test_a_broken_object_is_skipped_and_the_good_one_still_renders():
    good = _FakeObj(1, {"type": "LineString", "coordinates": [[-58.4, -34.6], [-58.3, -34.5]]})
    bad = _FakeObj(2, {"type": "LineString", "coordinates": "nonsense"}, "line")
    rendered = [gjs.object_to_leaflet(o) for o in (good, bad)]
    assert rendered[0] is not None, "el objeto valido debe seguir saliendo"
    assert rendered[1] is None, "el invalido se omite en vez de tumbar la respuesta"


# ─── Coordinate order, the other half of the bug ────────────────────────────

def test_geojson_in_leaflet_out():
    """The direction that was broken: tools send [lat, lon], the API stores
    [lon, lat], and the response must come back in Leaflet's order."""
    ll = gjs.line_geometry([[-34.6, -58.4], [-34.5, -58.3]])
    assert ll["type"] == "LineString"
    # Stored as [lon, lat].
    assert ll["coordinates"][0] == [-58.4, -34.6]
    back = gjs.geojson_to_latlngs(ll["coordinates"])
    # Read back as [lat, lon].
    assert back[0] == [-34.6, -58.4]


def test_polygon_ring_is_closed_on_write():
    poly = gjs.polygon_geometry([[-34.9, -58.9], [-34.8, -58.9], [-34.8, -58.8]])
    ring = poly["coordinates"][0]
    assert len(ring) == 4
    assert ring[0] == ring[-1], "GeoJSON exige el anillo cerrado"


# ─── The layer panel, which could not toggle anything ───────────────────────

def test_func_is_imported_at_module_level():
    """A regression with a long reach.

    ``from sqlalchemy import func`` used to sit *inside* ``list_layers``,
    which made it a local name. Every other handler that counted objects then
    raised NameError, so ``PUT /map/layers/{id}`` returned 500: no layer could
    be shown, hidden, reordered or made transparent from the interface.

    The import has to be visible to every handler in the module, so this
    asserts it is a module attribute and not merely that the route works: a
    working route could also be explained by a function-local import that
    happens to be correct for that one path.
    """
    from app.api.routes import map as map_routes

    assert hasattr(map_routes, "func"), (
        "func debe importarse a nivel de modulo en app/api/routes/map.py; "
        "importado dentro de una funcion es un nombre local y las demas rutas "
        "devuelven 500."
    )
