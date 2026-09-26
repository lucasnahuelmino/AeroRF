"""
core/geo.py
───────────
Spherical geometry for AeroRF.

Reference frame
───────────────
WGS84 / EPSG:4326. Latitude and longitude in decimal degrees, altitude in
metres above the ellipsoid. Geodesy uses a spherical model with the WGS84
mean Earth radius (6371.0088 km). For the ranges involved in aeronautical RF
investigation (tens of kilometres) the difference against the full
Vincenty/Karney ellipsoidal solution is well under a metre, which is
irrelevant next to ADS-B position noise of several hundred metres.

Every function here is pure and side-effect free, so it is directly
testable without a database or a map.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

# WGS84 mean Earth radius (IUGG), in metres.
EARTH_RADIUS_M = 6_371_008.8

LatLon = tuple[float, float]  # (lat, lon) in decimal degrees
LatLonDict = dict[str, float]


# ─── Validation ──────────────────────────────────────────────────────────────

def valid_latlon(lat: float, lon: float) -> bool:
    """True when the pair is inside the EPSG:4326 domain."""
    try:
        return (
            -90.0 <= float(lat) <= 90.0
            and -180.0 <= float(lon) <= 180.0
            and math.isfinite(float(lat))
            and math.isfinite(float(lon))
        )
    except (TypeError, ValueError):
        return False


def require_latlon(lat: float, lon: float) -> LatLon:
    """Return the pair as floats, raising ``ValueError`` if out of range."""
    if not valid_latlon(lat, lon):
        raise ValueError(f"Invalid WGS84 coordinate: lat={lat!r}, lon={lon!r}")
    return float(lat), float(lon)


# ─── Distance ────────────────────────────────────────────────────────────────

def haversine_m(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Great-circle distance in metres between two WGS84 points."""
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = φ2 - φ1
    Δλ = math.radians(lon2 - lon1)

    a = (
        math.sin(Δφ / 2) ** 2
        + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    )
    # Clamp guards against float drift pushing `a` marginally above 1.
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_M * c


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_m(lat1, lon1, lat2, lon2) / 1000.0


def distance_to_object_m(
    lat: float, lon: float, obj_lat: float | None, obj_lon: float | None
) -> float | None:
    """Distance in metres, or ``None`` when the reference has no position.

    Returning ``None`` rather than 0.0 matters: spec §56 forbids inventing
    data, and "0 km" would read as "coincident" instead of "unknown".
    """
    if obj_lat is None or obj_lon is None:
        return None
    if not valid_latlon(obj_lat, obj_lon) or not valid_latlon(lat, lon):
        return None
    return haversine_m(lat, lon, obj_lat, obj_lon)


# ─── Bearing and destination ─────────────────────────────────────────────────

def initial_bearing(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Initial great-circle bearing in degrees clockwise from true north."""
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δλ = math.radians(lon2 - lon1)

    y = math.sin(Δλ) * math.cos(φ2)
    x = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)
    return math.degrees(math.atan2(y, x)) % 360.0


def destination_point(
    lat: float, lon: float, bearing_deg: float, distance_m: float
) -> LatLon:
    """Point reached from ``(lat, lon)`` along ``bearing_deg`` for ``distance_m``."""
    if distance_m == 0:
        return float(lat), float(lon)

    δ = float(distance_m) / EARTH_RADIUS_M
    θ = math.radians(float(bearing_deg))
    φ1, λ1 = math.radians(lat), math.radians(lon)

    sin_φ2 = math.sin(φ1) * math.cos(δ) + math.cos(φ1) * math.sin(δ) * math.cos(θ)
    # asin domain guard for antipodal/near-antipodal cases.
    sin_φ2 = min(1.0, max(-1.0, sin_φ2))
    φ2 = math.asin(sin_φ2)

    λ2 = λ1 + math.atan2(
        math.sin(θ) * math.sin(δ) * math.cos(φ1),
        math.cos(δ) - math.sin(φ1) * sin_φ2,
    )

    # Normalise longitude into [-180, 180].
    return (
        math.degrees(φ2),
        (math.degrees(λ2) + 540.0) % 360.0 - 180.0,
    )


def midpoint(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> LatLon:
    """Great-circle midpoint between two points.

    Implemented as "walk half the distance along the initial bearing"
    rather than with the closed-form spherical-law-of-cosines variant:
    that form degenerates to ``atan2(0, 0)`` for equatorial paths, and
    this reuses :func:`destination_point`, which is already verified.
    """
    distance_m = haversine_m(lat1, lon1, lat2, lon2)
    if distance_m == 0:
        return float(lat1), float(lon1)
    return destination_point(
        lat1, lon1, initial_bearing(lat1, lon1, lat2, lon2), distance_m / 2.0
    )


# ─── Circles ─────────────────────────────────────────────────────────────────

def circle_points(
    lat: float,
    lon: float,
    radius_m: float,
    steps: int = 72,
    start_bearing: float = 0.0,
) -> list[LatLon]:
    """Approximate a circle as a closed polyline of ``steps`` vertices.

    Leaflet renders ``L.circle`` natively, but GeoJSON export and
    PostgreSQL/PostGIS migration need a real ring, so circles are always
    derivable as a polygon. The first vertex is not repeated at the end;
    GeoJSON linear rings are closed by the serializer.
    """
    if radius_m < 0:
        raise ValueError("radius_m must be non-negative")
    steps = max(8, int(steps))
    if radius_m == 0:
        return [(float(lat), float(lon))]

    return [
        destination_point(lat, lon, start_bearing + (360.0 * i / steps), radius_m)
        for i in range(steps)
    ]


def circle_bounds(lat: float, lon: float, radius_m: float) -> list[list[float]]:
    """Bounding box ``[[south, west], [north, east]]`` of a circle."""
    lat_delta = math.degrees(radius_m / EARTH_RADIUS_M)
    # Longitude degrees shrink with latitude; guard the poles.
    cos_lat = math.cos(math.radians(lat))
    lon_delta = math.degrees(radius_m / (EARTH_RADIUS_M * cos_lat)) if abs(cos_lat) > 1e-12 else 180.0
    return [
        [max(-90.0, lat - lat_delta), lon - lon_delta],
        [min(90.0, lat + lat_delta), lon + lon_delta],
    ]


# ─── Radials ─────────────────────────────────────────────────────────────────

def radial_geometry(
    lat: float, lon: float, azimuth_deg: float, length_m: float, steps: int = 2
) -> dict:
    """Build the geometry of a radial (spec §11, §37).

    Returns the origin, the end point and the intermediate vertices needed
    to follow the curvature of the Earth rather than a straight Cartesian
    line. At 20 NM the straight-line shortcut is visually wrong on a
    Mercator/Web-Mercator basemap.
    """
    steps = max(1, int(steps))
    coordinates: list[LatLon] = []
    for i in range(steps + 1):
        frac = i / steps
        coordinates.append(
            destination_point(lat, lon, azimuth_deg, length_m * frac)
        )

    start = coordinates[0]
    end = coordinates[-1]
    return {
        "origin": {"latitude": start[0], "longitude": start[1]},
        "end": {"latitude": end[0], "longitude": end[1]},
        "azimuth": float(azimuth_deg) % 360.0,
        "length_m": float(length_m),
        "coordinates": [list(c) for c in coordinates],
    }


# ─── Paths, traces and tracks ───────────────────────────────────────────────

def path_length_m(coordinates: Sequence[Sequence[float]]) -> float:
    """Total length in metres of a polyline given as ``[[lat, lon], ...]``."""
    total = 0.0
    for i in range(len(coordinates) - 1):
        a, b = coordinates[i], coordinates[i + 1]
        total += haversine_m(float(a[0]), float(a[1]), float(b[0]), float(b[1]))
    return total


def segment_bearings(
    coordinates: Sequence[Sequence[float]],
) -> list[dict]:
    """Per-segment length and initial bearing for a polyline.

    Backs the trace editor (spec §12), which shows total length in km/NM
    plus the azimuth of each tramo.
    """
    out: list[dict] = []
    for i in range(len(coordinates) - 1):
        a, b = coordinates[i], coordinates[i + 1]
        length = haversine_m(float(a[0]), float(a[1]), float(b[0]), float(b[1]))
        out.append(
            {
                "index": i,
                "from": [float(a[0]), float(a[1])],
                "to": [float(b[0]), float(b[1])],
                "length_m": length,
                "bearing": initial_bearing(
                    float(a[0]), float(a[1]), float(b[0]), float(b[1])
                ),
            }
        )
    return out


def path_summary(coordinates: Sequence[Sequence[float]]) -> dict:
    """Aggregate measurements for a polyline."""
    segments = segment_bearings(coordinates)
    total = sum(s["length_m"] for s in segments)
    return {
        "point_count": len(coordinates),
        "segment_count": len(segments),
        "total_length_m": total,
        "total_length_km": total / 1000.0,
        "total_length_nm": total / 1852.0,
        "segments": segments,
        "start": list(coordinates[0]) if coordinates else None,
        "end": list(coordinates[-1]) if coordinates else None,
    }


def bounds_of(coordinates: Iterable[Sequence[float]]) -> list[list[float]] | None:
    """Bounding box of a point set, or ``None`` when empty."""
    lats: list[float] = []
    lons: list[float] = []
    for c in coordinates:
        if c is None or len(c) < 2:
            continue
        lats.append(float(c[0]))
        lons.append(float(c[1]))
    if not lats:
        return None
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def interpolate_along(
    lat1: float, lon1: float, lat2: float, lon2: float, fraction: float
) -> LatLon:
    """Point at ``fraction`` of the way between two coordinates.

    Used only to *render* dense OpenSky waypoints smoothly. Spec §56
    forbids presenting interpolated positions as observed data, so callers
    must mark the result accordingly.
    """
    f = min(1.0, max(0.0, float(fraction)))
    lat = float(lat1) + (float(lat2) - float(lat1)) * f
    lon = float(lon1) + (float(lon2) - float(lon1)) * f
    return lat, lon


# ─── Coordinate formatting (spec §5) ─────────────────────────────────────────

def format_dms(value: float, is_latitude: bool) -> str:
    """Format a coordinate as degrees/minutes/seconds with hemisphere."""
    hemisphere = ""
    if is_latitude:
        hemisphere = "N" if value >= 0 else "S"
    else:
        hemisphere = "E" if value >= 0 else "W"
    v = abs(float(value))
    degrees = int(v)
    minutes_full = (v - degrees) * 60
    minutes = int(minutes_full)
    seconds = (minutes_full - minutes) * 60
    return f"{degrees}°{minutes:02d}'{seconds:05.2f}\"{hemisphere}"


def format_coordinate(value: float, is_latitude: bool, fmt: str = "dd") -> str:
    """Format one coordinate.

    ``fmt``:
      * ``dd``  — decimal degrees (default), 6 decimals ≈ 0.11 m
      * ``dms`` — degrees / minutes / seconds
      * ``dmm`` — degrees / decimal minutes
    """
    fmt = (fmt or "dd").lower()
    if fmt == "dms":
        return format_dms(value, is_latitude)
    if fmt == "dmm":
        hemisphere = (
            ("N" if value >= 0 else "S")
            if is_latitude
            else ("E" if value >= 0 else "W")
        )
        v = abs(float(value))
        degrees = int(v)
        minutes = (v - degrees) * 60
        return f"{degrees}°{minutes:06.3f}'{hemisphere}"
    return f"{float(value):.6f}"


def format_latlon(
    lat: float | None,
    lon: float | None,
    fmt: str = "dd",
    prefix: bool = True,
) -> str:
    """Format a full pair for the cursor bar (spec §5).

    ``dd`` renders as ``LAT -34.603722  LON -58.381592``;
    ``dms`` as ``LAT 34°36'13.40"S  LON 58°22'53.73"W``.
    """
    if lat is None or lon is None:
        return "LAT —   LON —"
    if (fmt or "dd").lower() == "dd":
        body = f"LAT {float(lat):9.6f}  LON {float(lon):10.6f}"
    else:
        body = f"LAT {format_coordinate(lat, True, fmt)}  LON {format_coordinate(lon, False, fmt)}"
    return body if prefix else body


def parse_coordinate(text: str) -> float | None:
    """Parse ``-34.603722`` or ``34°36'13.40"S`` into decimal degrees."""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass

    cleaned = s.replace("°", " ").replace("'", " ").replace('"', " ").replace("S", " -").replace("N", " ")
    cleaned = cleaned.replace("W", " -").replace("E", " ").replace(",", " ")
    parts = cleaned.split()
    if not parts:
        return None
    try:
        numbers = [float(p) for p in parts if p not in {"-", ""}]
    except ValueError:
        return None
    if not numbers:
        return None
    sign = -1.0 if "-" in parts else 1.0
    degrees = numbers[0]
    minutes = numbers[1] if len(numbers) > 1 else 0.0
    seconds = numbers[2] if len(numbers) > 2 else 0.0
    return sign * (abs(degrees) + minutes / 60.0 + seconds / 3600.0)
