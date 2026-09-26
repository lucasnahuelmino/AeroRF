"""
models/constants.py
───────────────────
Closed vocabularies shared by the database, the API schemas and the
frontend. Keeping them in one module prevents the classic drift where the
API accepts a state the map cannot colour, or the frontend offers a
category the backend rejects.
"""

from __future__ import annotations

# ─── Map object types (spec §2, §7) ──────────────────────────────────────────
TYPE_POINT = "point"
TYPE_LINE = "line"
TYPE_POLYGON = "polygon"
TYPE_CIRCLE = "circle"
TYPE_RADIAL = "radial"
TYPE_TRACE = "trace"
TYPE_MEASUREMENT = "measurement"
TYPE_ANNOTATION = "annotation"
TYPE_RF_SOURCE = "rf_source"
TYPE_ANTENNA = "antenna"
TYPE_REFERENCE = "reference"
TYPE_RF_EVENT = "rf_event"
TYPE_ENACOM_STATION = "enacom_station"
TYPE_AIRPORT = "airport"
TYPE_COVERAGE = "coverage"
TYPE_OTHER = "other"

OBJECT_TYPES = (
    TYPE_POINT,
    TYPE_LINE,
    TYPE_POLYGON,
    TYPE_CIRCLE,
    TYPE_RADIAL,
    TYPE_TRACE,
    TYPE_MEASUREMENT,
    TYPE_ANNOTATION,
    TYPE_RF_SOURCE,
    TYPE_ANTENNA,
    TYPE_REFERENCE,
    TYPE_RF_EVENT,
    TYPE_ENACOM_STATION,
    TYPE_AIRPORT,
    TYPE_COVERAGE,
    TYPE_OTHER,
)

# Types that enclose an area, i.e. rendered as a filled polygon.
POLYGONAL_TYPES = (TYPE_CIRCLE, TYPE_POLYGON, TYPE_COVERAGE)

# Types that carry a circle radius (spec §10, §36).
RADIUS_TYPES = (TYPE_CIRCLE, TYPE_REFERENCE, TYPE_COVERAGE)

# Types that carry an azimuth + length (spec §11, §37).
RADIAL_TYPES = (TYPE_RADIAL, TYPE_ANTENNA)

# ─── Point categories (spec §7) ──────────────────────────────────────────────
CATEGORY_REFERENCE = "Referencia"
CATEGORY_ANTENNA = "Antena"
CATEGORY_RF_SOURCE = "Fuente interferente"
CATEGORY_ENACOM = "Estación ENACOM"
CATEGORY_RF_EVENT = "Evento RF"
CATEGORY_AIRPORT = "Aeropuerto"
CATEGORY_OTHER = "Otro"

POINT_CATEGORIES = (
    CATEGORY_REFERENCE,
    CATEGORY_ANTENNA,
    CATEGORY_RF_SOURCE,
    CATEGORY_ENACOM,
    CATEGORY_RF_EVENT,
    CATEGORY_AIRPORT,
    CATEGORY_OTHER,
)

# ─── Object states (spec §15) ────────────────────────────────────────────────
STATE_ACTIVE = "Activo"
STATE_INACTIVE = "Inactivo"
STATE_OFF = "Apagado"
STATE_CLOSED = "Cerrado"
STATE_INVESTIGATING = "En investigación"
STATE_CONFIRMED = "Confirmado"
STATE_UNKNOWN = "Desconocido"

OBJECT_STATES = (
    STATE_ACTIVE,
    STATE_INACTIVE,
    STATE_OFF,
    STATE_CLOSED,
    STATE_INVESTIGATING,
    STATE_CONFIRMED,
    STATE_UNKNOWN,
)

# ─── RF source kinds (spec §32) ──────────────────────────────────────────────
RF_KIND_FM = "FM"
RF_KIND_AM = "AM"
RF_KIND_TV = "TV"
RF_KIND_LTE = "LTE"
RF_KIND_5G = "5G"
RF_KIND_WIFI = "WiFi"
RF_KIND_RADAR = "Radar"
RF_KIND_MICROWAVE = "Microondas"
RF_KIND_SATELLITE = "Satélite"
RF_KIND_OTHER = "Otro"

RF_SOURCE_KINDS = (
    RF_KIND_FM,
    RF_KIND_AM,
    RF_KIND_TV,
    RF_KIND_LTE,
    RF_KIND_5G,
    RF_KIND_WIFI,
    RF_KIND_RADAR,
    RF_KIND_MICROWAVE,
    RF_KIND_SATELLITE,
    RF_KIND_OTHER,
)

# ─── Antennas (spec §33) ─────────────────────────────────────────────────────
ANTENNA_KINDS = (
    "Omnidireccional",
    "Direccional",
    "Yagi",
    "Panel",
    "Dipolo",
    "Parabólica",
    "Log-periódica",
    "Another",
    "Otro",
)

POLARIZATIONS = ("Vertical", "Horizontal", "Circular", "Elíptica")

# ─── RF events (spec §34) ────────────────────────────────────────────────────
RF_EVENT_CLASSIFICATIONS = (
    "Interferencia aeronaútica",
    "Armónico",
    "Intermodulación",
    "Emisión no identificada",
    "Ruido de banda",
    "Espurious",
    "Otro",
)

# ─── Data provenance (spec §58) ──────────────────────────────────────────────
# The system must always distinguish where a value came from. This is not
# cosmetic: an ENACOM expediente has to be able to tell the operator which
# facts OpenSky provided and which AeroRF recorded itself.
PROVENANCE_OBSERVED = "observed"      # directly measured on site
PROVENANCE_HISTORICAL = "historical"  # historical OpenSky data
PROVENANCE_LIVE = "live"              # current OpenSky state vectors
PROVENANCE_CALCULATED = "calculated"  # derived by AeroRF
PROVENANCE_USER = "user"              # typed in by the operator

PROVENANCE_VALUES = (
    PROVENANCE_OBSERVED,
    PROVENANCE_HISTORICAL,
    PROVENANCE_LIVE,
    PROVENANCE_CALCULATED,
    PROVENANCE_USER,
)

PROVENANCE_LABELS_ES = {
    PROVENANCE_OBSERVED: "Dato observado",
    PROVENANCE_HISTORICAL: "Dato histórico",
    PROVENANCE_LIVE: "Dato en vivo",
    PROVENANCE_CALCULATED: "Dato calculado",
    PROVENANCE_USER: "Dato introducido por el usuario",
}

# ─── Aircraft track sources (spec §24, §56) ─────────────────────────────────
TRACK_SOURCE_OPENSKY = "opensky"
TRACK_SOURCE_AERORF = "aerorf"
TRACK_SOURCE_MERGED = "merged"

TRACK_SOURCES = (TRACK_SOURCE_OPENSKY, TRACK_SOURCE_AERORF, TRACK_SOURCE_MERGED)

# ─── Flight session status ───────────────────────────────────────────────────
SESSION_RECORDING = "recording"
SESSION_STOPPED = "stopped"
SESSION_ERROR = "error"

SESSION_STATUSES = (SESSION_RECORDING, SESSION_STOPPED, SESSION_ERROR)

# ─── Layer keys (spec §38) ───────────────────────────────────────────────────
LAYER_BASE = "base_map"
LAYER_AIRCRAFT = "aircraft"
LAYER_AIRCRAFT_TRACKS = "aircraft_tracks"
LAYER_AIRPORTS = "airports"
LAYER_RF_EVENTS = "rf_events"
LAYER_RF_SOURCES = "rf_sources"
LAYER_ANTENNAS = "antennas"
LAYER_REFERENCE_POINTS = "reference_points"
LAYER_CIRCLES = "circles"
LAYER_RADIALS = "radials"
LAYER_MEASUREMENTS = "measurements"
LAYER_EXPEDIENTES = "expedientes"
LAYER_ANNOTATIONS = "annotations"
LAYER_TRACES = "traces"
LAYER_LINES = "lines"
LAYER_POLYGONS = "polygons"
LAYER_USER = "user"

# key, display name, default visible, default opacity, default order
DEFAULT_LAYERS = (
    (LAYER_BASE,            "Mapa base",                True,  1.0,  0),
    (LAYER_AIRPORTS,        "Aeropuertos",              True,  1.0,  10),
    (LAYER_AIRCRAFT_TRACKS, "Trayectorias de aeronaves", True,  1.0,  20),
    (LAYER_AIRCRAFT,        "Aeronaves",                True,  1.0,  30),
    (LAYER_RADIALS,         "Radiales",                 True,  1.0,  40),
    (LAYER_CIRCLES,         "Círculos",                 True,  0.8,  50),
    (LAYER_ANTENNAS,        "Antenas",                  True,  1.0,  60),
    (LAYER_RF_SOURCES,      "Fuentes interferentes",    True,  1.0,  70),
    (LAYER_RF_EVENTS,       "Eventos RF",               True,  1.0,  80),
    (LAYER_REFERENCE_POINTS, "Puntos de referencia",    True,  1.0,  90),
    (LAYER_MEASUREMENTS,    "Mediciones",               True,  0.9,  100),
    (LAYER_TRACES,          "Trazas",                   True,  1.0,  110),
    (LAYER_LINES,           "Líneas",                   True,  1.0,  112),
    (LAYER_POLYGONS,        "Polígonos",                 True,  1.0,  114),
    (LAYER_ANNOTATIONS,     "Anotaciones",              True,  1.0,  120),
    (LAYER_EXPEDIENTES,     "Expedientes",              True,  1.0,  130),
    (LAYER_USER,            "Objetos del usuario",      True,  1.0,  140),
)

#: Which layer a newly created object of a given type lands in.
LAYER_BY_OBJECT_TYPE = {
    TYPE_POINT: LAYER_REFERENCE_POINTS,
    TYPE_TRACE: LAYER_TRACES,
    TYPE_CIRCLE: LAYER_CIRCLES,
    TYPE_COVERAGE: LAYER_CIRCLES,
    TYPE_RADIAL: LAYER_RADIALS,
    TYPE_MEASUREMENT: LAYER_MEASUREMENTS,
    TYPE_ANNOTATION: LAYER_ANNOTATIONS,
    TYPE_RF_SOURCE: LAYER_RF_SOURCES,
    TYPE_ANTENNA: LAYER_ANTENNAS,
    TYPE_REFERENCE: LAYER_REFERENCE_POINTS,
    TYPE_RF_EVENT: LAYER_RF_EVENTS,
    TYPE_ENACOM_STATION: LAYER_REFERENCE_POINTS,
    TYPE_AIRPORT: LAYER_AIRPORTS,
    TYPE_LINE: LAYER_LINES,
    TYPE_POLYGON: LAYER_POLYGONS,
    TYPE_OTHER: LAYER_USER,
}

# ─── Reference circle presets (spec §36) ─────────────────────────────────────
REFERENCE_RADII_NM = (1, 2, 5, 10, 20, 50, 100)

# ─── Correlation radius presets (spec §35) ───────────────────────────────────
CORRELATION_RADII_NM = (5, 10, 20, 50)


def default_color_for_type(object_type: str) -> str:
    """Default hex colour per object type, so the map is readable by default."""
    return {
        TYPE_POINT: "#38bdf8",
        TYPE_CIRCLE: "#3b82f6",
        TYPE_COVERAGE: "#6366f1",
        TYPE_RADIAL: "#a855f7",
        TYPE_TRACE: "#22d3ee",
        TYPE_LINE: "#22d3ee",
        TYPE_POLYGON: "#14b8a6",
        TYPE_MEASUREMENT: "#facc15",
        TYPE_ANNOTATION: "#fbbf24",
        TYPE_RF_SOURCE: "#f97316",
        TYPE_ANTENNA: "#10b981",
        TYPE_REFERENCE: "#f43f5e",
        TYPE_RF_EVENT: "#ef4444",
        TYPE_ENACOM_STATION: "#8b5cf6",
        TYPE_AIRPORT: "#60a5fa",
        TYPE_OTHER: "#94a3b8",
    }.get(object_type, "#94a3b8")


def default_icon_for_type(object_type: str) -> str:
    return {
        TYPE_POINT: "point",
        TYPE_CIRCLE: "circle",
        TYPE_RADIAL: "bearing",
        TYPE_TRACE: "polyline",
        TYPE_LINE: "polyline",
        TYPE_POLYGON: "polygon",
        TYPE_MEASUREMENT: "ruler",
        TYPE_ANNOTATION: "note",
        TYPE_RF_SOURCE: "emitter",
        TYPE_ANTENNA: "antenna",
        TYPE_REFERENCE: "target",
        TYPE_RF_EVENT: "signal",
        TYPE_ENACOM_STATION: "tower",
        TYPE_AIRPORT: "airport",
        TYPE_OTHER: "marker",
    }.get(object_type, "marker")
