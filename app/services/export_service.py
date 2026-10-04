"""
services/export_service.py
──────────────────────────
Export AeroRF objects as GeoJSON, KML and CSV (spec §46).

All three formats are generated from the same in-memory representation, so
a coordinate, a timestamp or a name can never differ between the formats.
Every export records provenance: the caller is told whether a value came
from OpenSky, from AeroRF's own recorder, from a calculation, or from the
operator.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Iterable, Optional
from xml.sax.saxutils import escape

from app.core.units import normalise_unit, to_metres
from app.services import geojson_service as gjs


# ─── GeoJSON ─────────────────────────────────────────────────────────────────

def to_geojson(objects: Iterable, include_history: bool = False) -> dict:
    """GeoJSON FeatureCollection (spec §17, §46)."""
    return gjs.objects_to_feature_collection(objects, include_history=include_history)


# ─── KML ─────────────────────────────────────────────────────────────────────

#: Per-type KML styling. Icons come from the bundled marker set; colour is
#: expressed as KML's aabbggrr (opaque alpha first, then BGR).
_TYPE_STYLE = {
    "point": ("ff38bdf8", "circle"),
    "rf_source": ("fff97316", "dot"),
    "antenna": ("ff10b981", "triangle"),
    "rf_event": ("ffef4444", "square"),
    "reference": ("fff43f5e", "cross"),
    "circle": ("ff3b82f6", "ring"),
    "radial": ("ffa855f7", "line"),
    "trace": ("ff22d3ee", "line"),
    "measurement": ("fffacc15", "line"),
    "annotation": ("fffbbf24", "dot"),
    "airport": ("ff60a5fa", "airport"),
    "enacom_station": ("ff8b5cf6", "tower"),
}


def _kml_color(hex_color: Optional[str]) -> str:
    """``#rrggbb`` → KML ``aabbggrr``."""
    if not hex_color or not hex_color.startswith("#"):
        return "ff64748b"
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "ff64748b"
    try:
        r, g, b = h[0:2], h[2:4], h[4:6]
    except ValueError:  # pragma: no cover
        return "ff64748b"
    return f"ff{b}{g}{r}"


def to_kml(objects: Iterable, name: str = "AeroRF") -> str:
    """KML 2.2 document, openable in Google Earth and QGIS."""
    objects = list(objects)
    out = io.StringIO()
    w = out.write

    w('<?xml version="1.0" encoding="UTF-8"?>\n')
    w('<kml xmlns="http://www.opengis.net/kml/2.2">\n<Document>\n')
    w(f"  <name>{escape(name)}</name>\n")
    w(f"  <description>Export AeroRF — {len(objects)} objetos</description>\n")
    w("  <Style id=\"aerorf_default\">\n")
    w('    <IconStyle><color>ff64748b</color>'
      "<scale>1.1</scale>"
      "<Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png"
      "</href></Icon></IconStyle>\n")
    w("  </Style>\n")

    for obj in objects:
        feature = gjs.object_to_feature(obj)
        if not feature:
            continue
        geometry = feature["geometry"]
        props = feature["properties"]
        color = _kml_color(obj.color)
        icon = _TYPE_STYLE.get(obj.type, ("ff64748b", "circle"))[1]

        w("<Placemark>\n")
        w(f"  <name>{escape(str(obj.name or obj.type))}</name>\n")
        if obj.description:
            w(f"  <description>{escape(str(obj.description))}</description>\n")

        # Structured metadata so the KML is self-describing outside AeroRF.
        w("  <ExtendedData>\n")
        for key in (
            "id", "type", "category", "status", "layer", "expediente",
            "radius", "radius_unit", "radius_km", "radius_nm",
            "azimuth", "length", "length_unit", "source", "created_at",
            "updated_at",
        ):
            value = props.get(key)
            if value not in (None, ""):
                w(
                    f'    <Data name="{key}"><value>'
                    f"{escape(str(value))}</value></Data>\n"
                )
        w("  </ExtendedData>\n")

        w("  <Style>\n")
        w(f'    <IconStyle><color>{color}</color><scale>1.2</scale>'
          f"<Icon><href>http://maps.google.com/mapfiles/kml/shapes/{icon}.png"
          "</href></Icon></IconStyle>\n")
        w(f'    <LineStyle><color>{color}</color><width>3</width></LineStyle>\n')
        w("  </Style>\n")

        gtype = geometry["type"]
        coords = geometry["coordinates"]
        if gtype == "Point":
            lon, lat = coords[0], coords[1]
            w(f"  <Point><coordinates>{lon},{lat},0</coordinates></Point>\n")
        elif gtype == "LineString":
            w("  <LineString>\n")
            w(f"    <tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>\n")
            w("    <coordinates>\n")
            for lon, lat in coords:
                w(f"      {lon},{lat},0\n")
            w("    </coordinates>\n  </LineString>\n")
        else:  # Polygon
            w("  <Polygon>\n")
            w(f"    <tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>\n")
            w("    <outerBoundaryIs><LinearRing><coordinates>\n")
            for lon, lat in coords[0]:
                w(f"      {lon},{lat},0\n")
            w("    </coordinates></LinearRing></outerBoundaryIs>\n  </Polygon>\n")

        w("</Placemark>\n")

    w("</Document>\n</kml>\n")
    return out.getvalue()


# ─── CSV ─────────────────────────────────────────────────────────────────────

CSV_COLUMNS = [
    "id", "type", "name", "category", "status", "description",
    "latitude", "longitude", "geojson_type",
    "radius", "radius_unit", "radius_km", "radius_nm",
    "azimuth", "length", "length_unit", "length_km", "length_nm",
    "layer", "expediente_id", "expediente", "visible", "locked",
    "color", "source", "created_at", "updated_at", "observed_at",
    "frequency_mhz", "power_dbm", "antenna_kind", "gain_dbi",
    "event_level_dbm", "classification", "length_total_km", "length_total_nm",
    "notes",
]


# ─── Blindado de CSV (P0-09) ─────────────────────────────────────────────────
_INICIOS_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _blindar(valor: Any) -> Any:
    """Prefija con `'` lo que una hoja de cálculo ejecutaría como fórmula.

    Un CSV abierto en Excel/LibreOffice interpreta como fórmula toda
    celda que arranca con ``=`` ``+`` ``-`` ``@`` (y con las dos
    invisibles: tabulador y retorno). De ahí sale desde el ``HYPERLINK``
    que lleva al sitio del atacante hasta los DDE.

    El blindado va por el valor, no por la columna:

    * sólo ``str`` — las columnas numéricas (latitud, longitud, dBm)
      traen números y no se tocan;
    * y un string legible como número (``"-34.6"``, ``"-62.5"``) tampoco:
      prefijarlo convertiría las latitudes negativas en texto, que es
      justamente la trampa que avisa el ítem P0-09.

    Una lista blanca de columnas se pudre con la próxima columna nueva;
    el carácter peligroso, no.
    """
    if not isinstance(valor, str) or not valor:
        return valor
    if valor[0] not in _INICIOS_FORMULA:
        return valor
    try:
        float(valor)
        return valor
    except ValueError:
        return "'" + valor


def to_csv(objects: Iterable, include_notes: bool = True) -> str:
    """Flat CSV, one row per object (spec §46)."""
    out = io.StringIO()
    writer = csv.DictWriter(
        out, fieldnames=CSV_COLUMNS, extrasaction="ignore", delimiter=";"
    )
    writer.writeheader()

    for obj in objects:
        feature = gjs.object_to_feature(obj)
        if not feature:
            continue
        props = feature["properties"]
        row: dict[str, Any] = {
            "id": obj.id,
            "type": obj.type,
            "name": obj.name or "",
            "category": obj.category or "",
            "status": obj.status or "",
            "description": obj.description or "",
            "latitude": obj.latitude,
            "longitude": obj.longitude,
            "geojson_type": feature["geometry"]["type"],
            "radius": obj.radius,
            "radius_unit": props.get("radius_unit"),
            "radius_km": props.get("radius_km"),
            "radius_nm": props.get("radius_nm"),
            "azimuth": obj.azimuth,
            "length": obj.length_value,
            "length_unit": props.get("length_unit"),
            "length_km": props.get("length_km"),
            "length_nm": props.get("length_nm"),
            "layer": props.get("layer"),
            "expediente_id": obj.expediente_id,
            "expediente": props.get("expediente"),
            "visible": obj.visible,
            "locked": obj.locked,
            "color": obj.color,
            "source": obj.source,
            "created_at": props.get("created_at"),
            "updated_at": props.get("updated_at"),
            "observed_at": props.get("observed_at"),
        }

        rf = props.get("rf")
        if rf:
            row["frequency_mhz"] = rf.get("frequency_mhz")
            row["power_dbm"] = rf.get("power_dbm")
        ant = props.get("antenna")
        if ant:
            row["antenna_kind"] = ant.get("kind")
            row["gain_dbi"] = ant.get("gain_dbi")
            row["frequency_mhz"] = row.get("frequency_mhz") or ant.get("frequency_mhz")
        meas = props.get("measurement")
        if meas:
            row["length_total_km"] = meas.get("total_km")
            row["length_total_nm"] = meas.get("total_nm")

        leaflet = gjs.object_to_leaflet(obj) or {}
        metrics = leaflet.get("metrics") or {}
        if metrics.get("total_length_km") is not None:
            row["length_total_km"] = metrics.get("total_length_km")
            row["length_total_nm"] = metrics.get("total_length_nm")
        if obj.type == "rf_event":
            row["event_level_dbm"] = (props.get("event") or {}).get("level_dbm")
            row["classification"] = (props.get("event") or {}).get("classification")

        if include_notes and props.get("notes"):
            row["notes"] = " | ".join(
                f"[{n['timestamp']}] {n['text']}" for n in props["notes"]
            )

        writer.writerow({k: _blindar(v) for k, v in row.items()})

    return out.getvalue()


# ─── Flight export ───────────────────────────────────────────────────────────

def track_to_geojson(points: list[dict], icao24: str, callsign: Optional[str] = None) -> dict:
    """A recorded or retrieved trajectory as GeoJSON (spec §21, §46)."""
    usable = [
        p for p in points
        if p.get("latitude") is not None and p.get("longitude") is not None
    ]
    geometry = gjs.line_geometry([[p["latitude"], p["longitude"]] for p in usable])
    if geometry is None:
        return {"type": "FeatureCollection", "features": []}

    times = [p.get("timestamp") for p in usable if p.get("timestamp") is not None]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "icao24": icao24,
                    "callsign": callsign,
                    "point_count": len(usable),
                    "start_timestamp": min(times) if times else None,
                    "end_timestamp": max(times) if times else None,
                    "provenance_counts": _count_provenance(usable),
                    "note": (
                        "Waypoints OpenSky: resolución variable, no 1 Hz. "
                        "VerAerRF para el detalle de procedencia."
                    ),
                },
            }
        ],
    }


def _count_provenance(points: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in points:
        key = p.get("provenance") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def track_to_csv(points: list[dict]) -> str:
    """Trajectory samples as CSV, one row per point."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(
        [
            "timestamp", "iso_utc", "latitude", "longitude", "altitude_m",
            "heading_deg", "velocity_ms", "on_ground", "icao24", "callsign",
            "provenance",
        ]
    )
    for p in points:
        ts = p.get("timestamp")
        writer.writerow(
            [
                _blindar(v)
                for v in (
                    ts if ts is not None else "",
                    _iso(ts),
                    p.get("latitude", ""),
                    p.get("longitude", ""),
                    p.get("altitude", ""),
                    p.get("heading", ""),
                    p.get("velocity", ""),
                    "" if p.get("on_ground") is None else p.get("on_ground"),
                    p.get("icao24", ""),
                    p.get("callsign", ""),
                    p.get("provenance", ""),
                )
            ]
        )
    return out.getvalue()


def _iso(ts: Optional[int]) -> str:
    if ts is None:
        return ""
    try:
        return datetime.utcfromtimestamp(int(ts)).isoformat()
    except (ValueError, OSError, OverflowError):
        return ""
