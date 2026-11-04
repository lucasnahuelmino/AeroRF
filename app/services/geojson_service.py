"""
services/geojson_service.py
───────────────────────────
Bidirectional geometry conversion (spec §17).

    DB  →  GeoJSON  →  Leaflet
    Leaflet  →  GeoJSON  →  DB

Two hard rules:

* **WGS84 / EPSG:4326** everywhere, and GeoJSON is always
  ``[longitude, latitude]`` — the reverse of Leaflet's
  ``[latitude, longitude]``. This is the single most common source of
  silently mirrored maps, so the conversion is centralised here and
  nowhere else.
* **Never invent geometry.** A circle with no radius, or a track with a
  single point, produces ``None`` rather than a degenerate shape that
  would render as a dot at (0, 0).
"""

from __future__ import annotations

import json

from app.core.logging import log
from typing import Any, Iterable, Sequence

from app.core.geo import (
    EARTH_RADIUS_M,
    circle_points,
    destination_point,
    haversine_m,
    path_summary,
    valid_latlon,
)
from app.core.units import UNIT_NM, from_metres, normalise_unit, to_metres
from app.models.constants import (
    PROVENANCE_CALCULATED,
    TYPE_CIRCLE,
    TYPE_COVERAGE,
    TYPE_LINE,
    TYPE_MEASUREMENT,
    TYPE_POINT,
    TYPE_POLYGON,
    TYPE_RADIAL,
    TYPE_REFERENCE,
    TYPE_TRACE,
)

#: Number of segments used to approximate a circle as a polygon.
CIRCLE_STEPS = 72

#: Segments used to follow Earth's curvature along a radial.
RADIAL_STEPS = 4


# ─── Leaflet ⇄ GeoJSON coordinate order ──────────────────────────────────────

def leaflet_to_geojson_coord(ll: Sequence[float]) -> list[float]:
    """``[lat, lon]`` (Leaflet) → ``[lon, lat]`` (GeoJSON)."""
    return [float(ll[1]), float(ll[0])]


def geojson_to_leaflet_coord(ll: Sequence[float]) -> list[float]:
    """``[lon, lat]`` (GeoJSON) → ``[lat, lon]`` (Leaflet)."""
    return [float(ll[1]), float(ll[0])]


def latlngs_to_geojson(latlngs: Iterable[Sequence[float]]) -> list[list[float]]:
    return [leaflet_to_geojson_coord(p) for p in latlngs if p and len(p) >= 2]


def geojson_to_latlngs(positions: Iterable[Sequence[float]]) -> list[list[float]]:
    return [geojson_to_leaflet_coord(p) for p in positions if p and len(p) >= 2]


# ─── Geometry validation ────────────────────────────────────────────────────
#
# Validate a geometry on the way IN, not only on the way out.
#
# Reading assumed the stored geometry was well formed: `object_to_leaflet`
# indexes `coord[1]`, so a ring that was saved with flat numbers raised
# TypeError and the whole listing endpoint returned 500. One malformed object
# therefore took down every map object in the database, not just itself.
#
# A bad payload is a client mistake, and it has to be answered as one: 422
# with a message naming the problem, on the request that caused it. Storing it
# and failing later is the worst of both.
#
# GeoJSON coordinate order is [lon, lat]. Getting it backwards is the single
# most common mistake at this boundary and it is accepted silently by
# GeoJSON itself, so the ranges are what catch it.

GEOMETRY_MIN_VERTICES = {"Point": 1, "LineString": 2, "Polygon": 4}


class GeometryError(ValueError):
    """Raised when a submitted geometry cannot be stored or drawn."""


def _check_position(coord, where: str) -> None:
    if not isinstance(coord, (list, tuple)) or len(coord) < 2:
        raise GeometryError(
            f"{where}: cada posición debe ser [lonitud, latitud], "
            f"recibido {coord!r}."
        )
    try:
        lon, lat = float(coord[0]), float(coord[1])
    except (TypeError, ValueError) as exc:
        raise GeometryError(
            f"{where}: las coordenadas deben ser numéricas, recibido {coord!r}."
        ) from exc
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise GeometryError(
            f"{where}: [{lon}, {lat}] está fuera de rango. GeoJSON es "
            "[longitud, latitud]: longitud -180..180, latitud -90..90."
        )


def validate_geometry(geometry) -> dict:
    """Return the geometry unchanged, or raise :class:`GeometryError`.

    Checks nesting depth, vertex count, numeric coordinates and range, and
    that a polygon's ring is closed. Called from the create and update paths.
    """
    if geometry is None:
        return geometry
    if not isinstance(geometry, dict):
        raise GeometryError(f"La geometría debe ser un objeto, recibido {type(geometry).__name__}.")

    gtype = geometry.get("type")
    if gtype not in GEOMETRY_MIN_VERTICES:
        raise GeometryError(
            f"Tipo de geometría no soportado: {gtype!r}. "
            f"Use Point, LineString o Polygon."
        )
    coords = geometry.get("coordinates")
    if coords is None:
        raise GeometryError(f"La geometría {gtype} no trae 'coordinates'.")

    if gtype == "Point":
        _check_position(coords, f"Geometría {gtype}")
        return geometry

    if gtype == "LineString":
        if not isinstance(coords, (list, tuple)):
            raise GeometryError("LineString: 'coordinates' debe ser una lista de posiciones.")
        for i, c in enumerate(coords):
            _check_position(c, f"LineString, vértice {i}")
        if len(coords) < GEOMETRY_MIN_VERTICES["LineString"]:
            raise GeometryError(
                f"LineString necesita al menos 2 vértices, recibió {len(coords)}."
            )
        return geometry

    # Polygon: a list of rings, each a list of positions.
    if not isinstance(coords, (list, tuple)) or not coords:
        raise GeometryError("Polygon: 'coordinates' debe ser una lista de anillos.")
    ring = coords[0]
    if not isinstance(ring, (list, tuple)):
        raise GeometryError("Polygon: el primer anillo debe ser una lista de posiciones.")
    for i, c in enumerate(ring):
        _check_position(c, f"Polygon, vértice {i}")
    if len(ring) < 3:
        raise GeometryError(
            f"Un polígono necesita al menos 3 vértices distintos, recibió {len(ring)}."
        )
    # The closure check comes before the count check, so a three-vertex open
    # ring is reported as the mistake it is: the caller forgot to repeat the
    # first vertex, not that the polygon is too small.
    if ring[0] != ring[-1]:
        raise GeometryError(
            "El anillo del polígono no está cerrado: la primera posición "
            f"{list(ring[0])} debe repetirse al final, que es {list(ring[-1])}."
        )
    if len(ring) < GEOMETRY_MIN_VERTICES["Polygon"]:
        raise GeometryError(
            f"Un polígono necesita al menos 4 posiciones con la primera repetida "
            f"al final, recibió {len(ring)}."
        )
    return geometry


# ─── Geometry construction ───────────────────────────────────────────────────

def point_geometry(lat: float, lon: float) -> dict | None:
    if not valid_latlon(lat, lon):
        return None
    return {"type": "Point", "coordinates": [float(lon), float(lat)]}


def line_geometry(coordinates: Sequence[Sequence[float]]) -> dict | None:
    """LineString from a ``[[lat, lon], ...]`` sequence."""
    pts = [p for p in (latlngs_to_geojson(coordinates) if coordinates else []) if p]
    if len(pts) < 2:
        return None
    return {"type": "LineString", "coordinates": pts}


def polygon_geometry(coordinates: Sequence[Sequence[float]]) -> dict | None:
    """Polygon from an open ``[[lat, lon], ...]`` ring; the ring is closed."""
    pts = [p for p in (latlngs_to_geojson(coordinates) if coordinates else []) if p]
    if len(pts) < 3:
        return None
    if pts[0] != pts[-1]:
        pts.append(list(pts[0]))
    return {"type": "Polygon", "coordinates": [pts]}


def circle_geometry(
    lat: float,
    lon: float,
    radius_m: float,
    steps: int = CIRCLE_STEPS,
) -> dict | None:
    """Approximate a circle as a GeoJSON polygon ring.

    Leaflet draws ``L.circle`` natively, but export and PostGIS need a
    ring, so the circle is always derivable as a polygon too.
    """
    if not valid_latlon(lat, lon) or radius_m is None or radius_m <= 0:
        return None
    ring = latlngs_to_geojson(circle_points(lat, lon, radius_m, steps=steps))
    if len(ring) < 4:
        return None
    if ring[0] != ring[-1]:
        ring.append(list(ring[0]))
    return {"type": "Polygon", "coordinates": [ring]}


def radial_geometry(
    lat: float,
    lon: float,
    azimuth: float,
    length_m: float,
    steps: int = RADIAL_STEPS,
) -> dict | None:
    """A radial as a LineString, curved to follow the Earth."""
    if not valid_latlon(lat, lon) or length_m is None or length_m <= 0:
        return None
    pts: list[list[float]] = []
    for i in range(steps + 1):
        p = destination_point(lat, lon, azimuth, length_m * (i / steps))
        pts.append([p[1], p[0]])
    return {"type": "LineString", "coordinates": pts}


def geometry_for_object(obj) -> dict | None:
    """Derive the GeoJSON geometry for a ``MapObject`` row.

    Priority order:
      1. an explicit stored ``geometry`` (arbitrary shapes, imported data)
      2. type-specific derivation (circle / radial from their parameters)
      3. a plain point at ``latitude``/``longitude``
    """
    stored = getattr(obj, "geometry", None)
    if isinstance(stored, dict) and stored.get("type") and stored.get("coordinates"):
        return stored

    lat, lon = getattr(obj, "latitude", None), getattr(obj, "longitude", None)
    otype = getattr(obj, "type", None)

    if otype in (TYPE_CIRCLE, TYPE_COVERAGE) and lat is not None:
        radius_m = _radius_metres(obj)
        if radius_m:
            return circle_geometry(lat, lon, radius_m)

    if otype in (TYPE_RADIAL,) and lat is not None:
        length_m = _length_metres(obj)
        if length_m and obj.azimuth is not None:
            return radial_geometry(lat, lon, obj.azimuth, length_m)

    if otype in (TYPE_POLYGON,):
        ring = (getattr(obj, "properties", None) or {}).get("ring")
        if ring:
            return polygon_geometry(ring)

    if otype in (TYPE_TRACE, TYPE_LINE, TYPE_MEASUREMENT):
        path = (getattr(obj, "properties", None) or {}).get("path")
        if path:
            return line_geometry(path)

    if lat is not None and lon is not None:
        return point_geometry(lat, lon)

    return None


def _radius_metres(obj) -> float | None:
    radius = getattr(obj, "radius", None)
    if radius is None:
        return None
    return to_metres(radius, getattr(obj, "radius_unit", None) or UNIT_NM)


def _length_metres(obj) -> float | None:
    length = getattr(obj, "length_value", None)
    if length is None:
        return None
    return to_metres(length, getattr(obj, "length_unit", None) or UNIT_NM)


# ─── Feature / FeatureCollection ─────────────────────────────────────────────

def object_to_feature(obj, include_history: bool = False) -> dict | None:
    """Serialise one ``MapObject`` as a GeoJSON Feature.

    Properties are deliberately verbose: the exported file has to be
    self-describing, because it leaves AeroRF and may be handed to
    somebody else as evidence.
    """
    geometry = geometry_for_object(obj)
    if geometry is None:
        return None

    props: dict[str, Any] = {
        "id": obj.id,
        "type": obj.type,
        "name": obj.name,
        "description": obj.description,
        "category": obj.category,
        "status": obj.status,
        "layer": obj.layer.key if obj.layer else None,
        "layer_name": obj.layer.name if obj.layer else None,
        "visible": obj.visible,
        "locked": obj.locked,
        "color": obj.color,
        "icon": obj.icon,
        "label": obj.label,
        "expediente_id": obj.expediente_id,
        "expediente": (
            obj.expediente.numero_expediente if obj.expediente else None
        ),
        "source": obj.source,
        "created_at": _iso(obj.fecha_creacion),
        "updated_at": _iso(obj.fecha_actualizacion),
        "observed_at": _iso(obj.observed_at),
        "valid_from": _iso(obj.valid_from),
        "valid_to": _iso(obj.valid_to),
    }

    # Circle / radial parameters travel with the feature, both in the
    # operator's unit and normalised, so the file is unambiguous.
    if obj.radius is not None:
        props["radius"] = obj.radius
        props["radius_unit"] = normalise_unit(obj.radius_unit)
        radius_m = _radius_metres(obj)
        if radius_m:
            props["radius_km"] = round(radius_m / 1000.0, 6)
            props["radius_nm"] = round(radius_m / 1852.0, 6)
    if obj.azimuth is not None:
        props["azimuth"] = obj.azimuth
    if obj.length_value is not None:
        props["length"] = obj.length_value
        props["length_unit"] = normalise_unit(obj.length_unit)
        length_m = _length_metres(obj)
        if length_m:
            props["length_km"] = round(length_m / 1000.0, 6)
            props["length_nm"] = round(length_m / 1852.0, 6)

    # Type-specific payloads.
    if getattr(obj, "rf_source", None):
        s = obj.rf_source
        props["rf"] = {
            "kind": s.kind,
            "frequency_mhz": s.frequency_mhz,
            "power_dbm": s.power_dbm,
            "power_w": s.power_w,
            "eirp_dbm": s.eirp_dbm,
            "bandwidth_khz": s.bandwidth_khz,
            "height_m": s.height_m,
            "provenance": s.provenance,
            "measured_at": _iso(s.measured_at),
        }
    if getattr(obj, "antenna", None):
        a = obj.antenna
        props["antenna"] = {
            "kind": a.kind,
            "frequency_mhz": a.frequency_mhz,
            "height_m": a.height_m,
            "gain_dbi": a.gain_dbi,
            "power_w": a.power_w,
            "azimuth_deg": a.azimuth_deg,
            "sector_deg": a.sector_deg,
            "tilt_deg": a.tilt_deg,
            "polarization": a.polarization,
        }
    if getattr(obj, "reference", None):
        r = obj.reference
        props["reference"] = {
            "kind": r.kind,
            "code": r.code,
            "radius": r.radius,
            "radius_unit": normalise_unit(r.radius_unit),
        }
    if getattr(obj, "measurement", None):
        m = obj.measurement
        props["measurement"] = {
            "mode": m.mode,
            "total_m": m.total_m,
            "total_km": m.total_km,
            "total_nm": m.total_nm,
            "segments": m.segments,
        }
    # El evento RF era la única sin serializar (F2-03): `export_service.to_csv`
    # ya leía `props["event"]` y salía con las columnas vacías, y el Inspector
    # no tenía nada que mostrar. Se emite el mismo bloque que declara
    # `RFEventPayload`, incluido `calculated_evento_id` —hoy siempre nulo—
    # para que la exportación diga exactamente lo que hay en la fila.
    if getattr(obj, "rf_event", None):
        e = obj.rf_event
        props["event"] = {
            "frequency_mhz": e.frequency_mhz,
            "level_dbm": e.level_dbm,
            "bandwidth_khz": e.bandwidth_khz,
            "event_at": _iso(e.event_at),
            "classification": e.classification,
            "source_kind": e.source_kind,
            "description": e.description,
            "observations": e.observations,
            "event_kind": e.event_kind,
            "provenance": e.provenance,
            "calculated_evento_id": e.calculated_evento_id,
        }

    if obj.properties:
        props["properties"] = obj.properties

    # Notes and history make the export a real record of the investigation.
    if getattr(obj, "notes", None) is not None:
        props["notes"] = [
            {
                "timestamp": _iso(n.timestamp),
                "user": n.user,
                "text": n.text,
            }
            for n in obj.notes
        ]
    if include_history and getattr(obj, "history", None) is not None:
        props["history"] = [
            {
                "changed_at": _iso(h.changed_at),
                "field": h.field,
                "old_value": h.old_value,
                "new_value": h.new_value,
                "comment": h.comment,
                "user": h.user,
            }
            for h in obj.history
        ]

    return {
        "type": "Feature",
        "id": obj.id,
        "geometry": geometry,
        "properties": props,
    }


def objects_to_feature_collection(
    objects: Iterable, include_history: bool = False
) -> dict:
    """Serialise a collection, skipping objects with no derivable geometry."""
    features = []
    for obj in objects:
        feature = object_to_feature(obj, include_history=include_history)
        if feature:
            features.append(feature)
    return {
        "type": "FeatureCollection",
        "features": features,
    }


def _iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


# ─── Leaflet-facing output ───────────────────────────────────────────────────

def object_to_leaflet(obj) -> dict | None:
    try:
        return _object_to_leaflet(obj)
    except (TypeError, KeyError, IndexError, ValueError) as exc:
        # One un-drawable object must not fail the listing. Report it in the
        # response instead of hiding it, so the operator can see that it
        # exists and fix it.
        log.warning(
            "geojson.object_not_drawable",
            f"object {getattr(obj, 'id', '?')} could not be drawn: {exc}",
            object_id=getattr(obj, "id", None),
            object_type=getattr(obj, "type", None),
        )
        return None


def _object_to_leaflet(obj) -> dict | None:
    """Produce the dict the frontend's MapEngine consumes directly.

    Includes everything Leaflet needs (``latlngs`` in Leaflet order) plus
    the derived measurements the inspector shows, so the frontend does not
    recompute geometry the backend already knows.
    """
    feature = object_to_feature(obj)
    if feature is None:
        return None

    geometry = feature["geometry"]
    gtype = geometry["type"]

    if gtype == "Point":
        # A point is a single [lat, lon] pair.
        position = geojson_to_leaflet_coord(geometry["coordinates"])
        latlngs: list[list[float]] = [position]
    elif gtype == "LineString":
        latlngs = [geojson_to_leaflet_coord(c) for c in geometry["coordinates"]]
        position = latlngs[0] if latlngs else None
    else:  # Polygon
        ring = [geojson_to_leaflet_coord(c) for c in geometry["coordinates"][0]]
        if ring and ring[0] == ring[-1]:
            ring = ring[:-1]  # Leaflet closes the ring itself
        latlngs = ring
        position = ring[0] if ring else None

    # Reading is defensive even though writing is now validated. Rows created
    # before validation existed, or written by a direct database edit, must
    # not be able to fail the whole request: an object the map cannot draw is
    # skipped with a note, and every other object still comes back.

    out: dict[str, Any] = {
        "id": obj.id,
        "type": obj.type,
        "geometry": geometry,
        "geometry_type": gtype,
        "latlngs": latlngs,
        "latlng": position,
        "name": obj.name,
        "properties": feature["properties"],
        "color": obj.color,
        "icon": obj.icon,
        "visible": obj.visible,
        "locked": obj.locked,
        "opacity": obj.opacity,
        "weight": obj.weight,
        "fill_opacity": obj.fill_opacity,
        "label": obj.label,
        "show_label": obj.show_label,
        "layer": obj.layer.key if obj.layer else None,
        "expediente_id": obj.expediente_id,
        "status": obj.status,
        # The raw geometric parameters, in the operator's own units, so the
        # inspector can pre-fill the edit form without reverse-engineering
        # them from the derived geometry.
        "radius": obj.radius,
        "radius_unit": normalise_unit(obj.radius_unit) if obj.radius is not None else None,
        "azimuth": obj.azimuth,
        "length_value": obj.length_value,
        "length_unit": normalise_unit(obj.length_unit) if obj.length_value is not None else None,
        "created_at": _iso(obj.fecha_creacion),
        "updated_at": _iso(obj.fecha_actualizacion),
        "provenance": obj.source,
    }

    # Derived measurements, computed server-side so the numbers on screen
    # and the numbers in the export cannot diverge.
    if obj.latitude is not None and obj.longitude is not None:
        out["center"] = [obj.latitude, obj.longitude]
    if gtype == "LineString" and len(latlngs) >= 2:
        out["metrics"] = _line_metrics(latlngs)
    if obj.radius is not None and obj.latitude is not None:
        radius_m = _radius_metres(obj)
        if radius_m:
            out["radius_m"] = radius_m
            out["metrics"] = {
                "radius_m": radius_m,
                "radius_km": radius_m / 1000.0,
                "radius_nm": radius_m / 1852.0,
            }
    if obj.azimuth is not None and obj.latitude is not None:
        length_m = _length_metres(obj)
        if length_m:
            end = destination_point(obj.latitude, obj.longitude, obj.azimuth, length_m)
            out["radial"] = {
                "azimuth": obj.azimuth % 360.0,
                "length_m": length_m,
                "length_km": length_m / 1000.0,
                "length_nm": length_m / 1852.0,
                "end": [end[0], end[1]],
            }

    return out


def _line_metrics(latlng: Sequence[Sequence[float]]) -> dict:
    s = path_summary(latlng)
    return {
        "total_length_m": s["total_length_m"],
        "total_length_km": s["total_length_km"],
        "total_length_nm": s["total_length_nm"],
        "segment_count": s["segment_count"],
        "point_count": s["point_count"],
    }


# ─── Inbound: GeoJSON / Leaflet → typed parameters ──────────────────────────

def geojson_feature_to_object_params(feature: dict) -> dict:
    """Turn a Feature into keyword arguments for object creation.

    Accepts both a proper GeoJSON Feature and the looser
    ``{lat, lon}`` / ``{latlngs}`` shapes the drawing tools emit, so the
    map tools and a file import share one validation path.
    """
    geometry = feature.get("geometry") or {}
    gtype = geometry.get("type")
    coords = geometry.get("coordinates") or []
    props = feature.get("properties") or {}

    out: dict[str, Any] = {
        "name": props.get("name") or props.get("title"),
        "description": props.get("description"),
        "category": props.get("category"),
        "status": props.get("status"),
        "color": props.get("color"),
        "icon": props.get("icon"),
        "label": props.get("label"),
        "radius": props.get("radius"),
        "radius_unit": props.get("radius_unit"),
        "azimuth": props.get("azimuth"),
        "length_value": props.get("length"),
        "length_unit": props.get("length_unit"),
        "expediente_id": props.get("expediente_id"),
        "geometry": None,
        "geometry_type": None,
        "latitude": None,
        "longitude": None,
        "ring": None,
        "path": None,
        "properties": {},
    }

    # Loose shape straight from the map tools.
    if "latlng" in feature and feature["latlng"]:
        ll = feature["latlng"]
        out["latitude"], out["longitude"] = float(ll[0]), float(ll[1])
    elif "lat" in feature and "lon" in feature and feature["lat"] is not None:
        out["latitude"], out["longitude"] = float(feature["lat"]), float(feature["lon"])

    if gtype == "Point" and coords:
        out["longitude"], out["latitude"] = float(coords[0]), float(coords[1])
        out["geometry_type"] = "Point"
    elif gtype == "LineString" and len(coords) >= 2:
        latlngs = geojson_to_latlngs(coords)
        out["path"] = latlngs
        out["geometry_type"] = "LineString"
        out["latitude"], out["longitude"] = latlngs[0]
    elif gtype == "Polygon" and coords:
        ring = geojson_to_latlngs(coords[0])
        if ring and ring[0] == ring[-1]:
            ring = ring[:-1]
        out["ring"] = ring
        out["geometry_type"] = "Polygon"
        if ring:
            out["latitude"], out["longitude"] = ring[0]

    # Carry through any extra properties verbatim.
    extra = {
        k: v
        for k, v in props.items()
        if k not in out and k not in {"rf", "antenna", "reference", "measurement",
                                      "notes", "history", "radius_km", "radius_nm",
                                      "length_km", "length_nm", "id", "created_at",
                                      "updated_at", "observed_at", "valid_from",
                                      "valid_to", "source", "layer", "layer_name",
                                      "visible", "locked", "title"}
    }
    out["properties"] = extra
    return out


def ring_or_path_params(obj) -> tuple[list | None, list | None]:
    """Return ``(ring, path)`` for a stored object, whichever applies."""
    props = getattr(obj, "properties", None) or {}
    return props.get("ring"), props.get("path")


# ─── Export serialisation ────────────────────────────────────────────────────

def dumps(feature_collection: dict, indent: int | None = None) -> str:
    """JSON serialisation with non-ASCII preserved (Spanish accents)."""
    return json.dumps(feature_collection, ensure_ascii=False, indent=indent, default=str)
