"""
core/units.py
─────────────
Distance and angle unit conversion for AeroRF.

The nautical mile is the working unit of aeronautical RF investigation
(protection volumes, radials, sectors), so it is treated as first class
alongside kilometres and metres.

    1 NM = 1852 m  (exact, by international definition)
    1 NM = 1.852 km
"""

from __future__ import annotations

# ─── Exact constants (international definition) ──────────────────────────────
METRES_PER_NAUTICAL_MILE = 1852.0
KILOMETRES_PER_NAUTICAL_MILE = 1.852
METRES_PER_KILOMETRE = 1000.0
METRES_PER_MILE = 1609.344
FEET_PER_METRE = 3.280839895

# Canonical unit identifiers used across the API and the database.
UNIT_NM = "nm"
UNIT_KM = "km"
UNIT_M = "m"

SUPPORTED_UNITS = (UNIT_NM, UNIT_KM, UNIT_M)

# Multipliers relative to metres.
_TO_METRES = {
    UNIT_M: 1.0,
    UNIT_KM: METRES_PER_KILOMETRE,
    UNIT_NM: METRES_PER_NAUTICAL_MILE,
}

_ALIASES = {
    "nmi": UNIT_NM,
    "nauticalmile": UNIT_NM,
    "nautical_mile": UNIT_NM,
    "milla_nautica": UNIT_NM,
    "millas_nauticas": UNIT_NM,
    "milla náutica": UNIT_NM,
    "millas náuticas": UNIT_NM,
    "kilometro": UNIT_KM,
    "kilometros": UNIT_KM,
    "kilómetro": UNIT_KM,
    "kilómetros": UNIT_KM,
    "metro": UNIT_M,
    "metros": UNIT_M,
}


class UnknownUnitError(ValueError):
    """Raised when a unit string cannot be resolved."""


def normalise_unit(unit: str | None, default: str = UNIT_NM) -> str:
    """Resolve a user-supplied unit string to a canonical identifier.

    Accepts the canonical ids (``nm``/``km``/``m``) plus common Spanish and
    English spellings and symbols. Unknown values fall back to ``default``
    rather than raising, because this sits on request-parsing paths.
    """
    if unit is None:
        return default
    key = str(unit).strip().lower()
    if not key:
        return default
    if key in _TO_METRES:
        return key
    if key in _ALIASES:
        return _ALIASES[key]
    if key in {"kilometers", "kilometer", "kms", "km."}:
        return UNIT_KM
    if key in {"meters", "meter", "mts", "m."}:
        return UNIT_M
    return default


def to_metres(value: float, unit: str | None = UNIT_NM) -> float:
    """Convert ``value`` expressed in ``unit`` to metres."""
    canonical = normalise_unit(unit)
    if canonical not in _TO_METRES:  # pragma: no cover - normalise guarantees this
        raise UnknownUnitError(f"Unsupported unit: {unit!r}")
    return float(value) * _TO_METRES[canonical]


def from_metres(metres: float, unit: str | None = UNIT_NM) -> float:
    """Convert ``metres`` to ``unit``."""
    canonical = normalise_unit(unit)
    if canonical not in _TO_METRES:  # pragma: no cover
        raise UnknownUnitError(f"Unsupported unit: {unit!r}")
    return float(metres) / _TO_METRES[canonical]


def convert(value: float, from_unit: str | None, to_unit: str | None) -> float:
    """Convert ``value`` between any two supported units."""
    return from_metres(to_metres(value, from_unit), to_unit)


def nm_to_km(nm: float) -> float:
    return float(nm) * KILOMETRES_PER_NAUTICAL_MILE


def km_to_nm(km: float) -> float:
    return float(km) / KILOMETRES_PER_NAUTICAL_MILE


def nm_to_m(nm: float) -> float:
    return float(nm) * METRES_PER_NAUTICAL_MILE


def m_to_nm(metres: float) -> float:
    return float(metres) / METRES_PER_NAUTICAL_MILE


def km_to_m(km: float) -> float:
    return float(km) * METRES_PER_KILOMETRE


def m_to_km(metres: float) -> float:
    return float(metres) / METRES_PER_KILOMETRE


def nm_to_feet(nm: float) -> float:
    return nm_to_m(nm) * FEET_PER_METRE


# ─── Angle helpers ───────────────────────────────────────────────────────────

def normalise_azimuth(azimuth: float) -> float:
    """Wrap an azimuth into [0, 360).

    Azimuths are measured clockwise from true north, per spec §11/§37.
    """
    return float(azimuth) % 360.0


def is_clockwise_from(azimuth: float, reference: float, span: float) -> bool:
    """True when ``azimuth`` lies within ``span`` degrees clockwise of ``reference``.

    Used for directional antenna sectors.
    """
    span = abs(float(span))
    if span >= 360.0:
        return True
    delta = (float(azimuth) - float(reference)) % 360.0
    return delta <= span


def format_azimuth(azimuth: float) -> str:
    """Format an azimuth as a compact bearing string, e.g. ``135°``."""
    return f"{normalise_azimuth(azimuth):.0f}°"


def compass_point(azimuth: float) -> str:
    """Return the 16-point compass label for an azimuth."""
    points = (
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    )
    index = int((normalise_azimuth(azimuth) + 11.25) // 22.5) % 16
    return points[index]


def format_distance(
    metres: float, unit: str = UNIT_NM, decimals: int = 2
) -> str:
    """Human-readable distance string, e.g. ``20 NM (37.04 km)``."""
    value = from_metres(metres, unit)
    canonical = normalise_unit(unit)
    if canonical == UNIT_NM:
        return f"{value:.{decimals}f} NM ({nm_to_km(value):.2f} km)"
    if canonical == UNIT_KM:
        return f"{value:.{decimals}f} km ({km_to_nm(value):.2f} NM)"
    return f"{value:,.{decimals}f} m"
