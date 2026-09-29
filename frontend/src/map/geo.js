/**
 * map/geo.js
 * ──────────
 * Pure geodesy and formatting for the frontend. **No Leaflet import.**
 *
 * This module is deliberately dependency-free so it can be unit-tested in
 * Node without a DOM, and so the numbers shown on screen come from exactly
 * one implementation. The backend has the authoritative version in
 * `app/core/geo.py` and `app/core/units.py`; the two are cross-checked
 * against the same vectors (see tests/geo_parity.py).
 *
 * Reference frame: WGS84 / EPSG:4326, spherical with the WGS84 mean
 * radius. At the ranges of aeronautical RF investigation the difference
 * against a full ellipsoidal solution is well under a metre.
 */

export const EARTH_RADIUS_M = 6371008.8

// ─── Units (spec §10, §13) ───────────────────────────────────────────────────

export const NM_TO_M = 1852
export const KM_TO_M = 1000
export const NM_TO_KM = 1.852

export function toMetres(value, unit = 'nm') {
  const v = Number(value) || 0
  if (unit === 'km') return v * KM_TO_M
  if (unit === 'm') return v
  return v * NM_TO_M
}

export function fromMetres(metres, unit = 'nm') {
  const value = Number(metres) || 0
  if (unit === 'km') return value / KM_TO_M
  if (unit === 'm') return value
  return value / NM_TO_M
}

export function convert(value, fromUnit, toUnit) {
  return fromMetres(toMetres(value, fromUnit), toUnit)
}

export function nmToKm(nm) {
  return Number(nm) * NM_TO_KM
}

export function kmToNm(km) {
  return Number(km) / NM_TO_KM
}

/** ``20 NM`` → ``20.00 NM (37.04 km)``. */
export function formatRadius(value, unit = 'nm') {
  const v = Number(value) || 0
  if (unit === 'km') return `${v.toFixed(2)} km`
  if (unit === 'm') return `${v.toFixed(0)} m`
  return `${v.toFixed(2)} NM (${nmToKm(v).toFixed(2)} km)`
}

/** Metres, kilometres and nautical miles, all three (spec §13). */
export function formatDistance(metres) {
  if (metres === null || metres === undefined) return '—'
  const value = Number(metres)
  const km = value / KM_TO_M
  const nm = value / NM_TO_M
  if (value < 1000) return `${value.toFixed(1)} m · ${nm.toFixed(3)} NM · ${km.toFixed(3)} km`
  if (value < 100_000) return `${km.toFixed(3)} km · ${nm.toFixed(3)} NM`
  return `${km.toFixed(2)} km · ${nm.toFixed(2)} NM`
}

// ─── Distance and bearing ────────────────────────────────────────────────────

const toRad = (deg) => (Number(deg) * Math.PI) / 180
const toDeg = (rad) => (Number(rad) * 180) / Math.PI

export function haversine(lat1, lon1, lat2, lon2) {
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.max(0, Math.sqrt(a))))
}

export function haversineKm(lat1, lon1, lat2, lon2) {
  return haversine(lat1, lon1, lat2, lon2) / KM_TO_M
}

/** Initial great-circle bearing, degrees clockwise from true north. */
export function bearing(lat1, lon1, lat2, lon2) {
  const φ1 = toRad(lat1)
  const φ2 = toRad(lat2)
  const Δλ = toRad(lon2 - lon1)
  const y = Math.sin(Δλ) * Math.cos(φ2)
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ)
  return (toDeg(Math.atan2(y, x)) + 360) % 360
}

/** Point reached along a bearing for a distance. */
export function destination(lat, lon, azimuthDeg, distanceM) {
  if (!distanceM) return [Number(lat), Number(lon)]
  const δ = Number(distanceM) / EARTH_RADIUS_M
  const θ = toRad(azimuthDeg)
  const φ1 = toRad(lat)
  const λ1 = toRad(lon)
  const sinφ2 = Math.sin(φ1) * Math.cos(δ) + Math.cos(φ1) * Math.sin(δ) * Math.cos(θ)
  const φ2 = Math.asin(Math.max(-1, Math.min(1, sinφ2)))
  const λ2 =
    λ1 +
    Math.atan2(
      Math.sin(θ) * Math.sin(δ) * Math.cos(φ1),
      Math.cos(δ) - Math.sin(φ1) * sinφ2,
    )
  return [toDeg(φ2), (((toDeg(λ2) + 540) % 360) - 180)]
}

/** Vertices that follow the Earth's curvature, so a radial is not a chord. */
export function radialPoints(origin, azimuth, distanceM, steps = 24) {
  return Array.from({ length: steps + 1 }, (_, i) =>
    destination(origin[0], origin[1], azimuth, (Number(distanceM) * i) / steps),
  )
}

/** Circle approximated as a polygon ring (for export and hit-testing). */
/**
 * An arc between two bearings, centred on a point.
 *
 * Used to draw the angle a radial makes with north. It is the arc and not the
 * straight chord: a chord reads as a different angle from the one the operator
 * is being shown, which is the only reason to draw it at all.
 */
/**
 * How far, in metres, a click may sit from a snap target and still be pulled
 * onto it — expressed in screen pixels and converted at the current latitude.
 *
 * Leaflet already computes this for its own snapping, and duplicating the
 * formula here would be a second place for the Web Mercator constants to drift.
 * So the engine is asked; this is the fallback for a caller that has none.
 */
export function snapToleranceM(latitude, metresPerPixel) {
  const R = 6371008.8
  const lat = Math.abs(Number(latitude) || 0)
  const cos = Math.max(0.01, Math.cos((lat * Math.PI) / 180))
  return Number(metresPerPixel) * 2 * Math.PI * R * cos
}

export function arcPoints(origin, radiusM, fromAzimuth, toAzimuth, steps = 24) {
  if (!radiusM) return [origin]
  // The short way round, so a sweep past 360 does not draw a 350-degree arc
  // backwards through every bearing.
  let span = (((toAzimuth - fromAzimuth) % 360) + 360) % 360
  if (span > 180) span -= 360
  return Array.from({ length: steps + 1 }, (_, i) =>
    destination(origin[0], origin[1], fromAzimuth + (span * i) / steps, radiusM),
  )
}

export function circlePoints(lat, lon, radiusM, steps = 72) {
  const count = Math.max(8, steps)
  if (!radiusM) return [[Number(lat), Number(lon)]]
  return Array.from({ length: count }, (_, i) =>
    destination(lat, lon, (360 * i) / count, radiusM),
  )
}

// ─── Azimuth ─────────────────────────────────────────────────────────────────

/**
 * Wrap an azimuth into [0, 360).
 *
 * The double modulo is not redundant: JavaScript's `%` keeps the sign of
 * the dividend, so `-90 % 360` is `-90`, while Python's is `270`. Without
 * this, the same azimuth normalises differently on the two sides of the
 * wire and a radial would be drawn at a different bearing depending on
 * where the maths ran.
 */
export function normaliseAzimuth(azimuth) {
  return (((Number(azimuth) % 360) + 360) % 360)
}

const COMPASS = [
  'N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW',
]

export function compassPoint(azimuth) {
  const index = Math.floor((normaliseAzimuth(azimuth) + 11.25) / 22.5) % 16
  return COMPASS[index]
}

export function formatAzimuth(azimuth) {
  return `${normaliseAzimuth(azimuth).toFixed(0)}°`
}

// ─── Paths ───────────────────────────────────────────────────────────────────

export function pathLengthM(coordinates) {
  let total = 0
  for (let i = 0; i < coordinates.length - 1; i += 1) {
    total += haversine(...coordinates[i], ...coordinates[i + 1])
  }
  return total
}

export function pathSummary(coordinates) {
  const segments = []
  for (let i = 0; i < coordinates.length - 1; i += 1) {
    const a = coordinates[i]
    const b = coordinates[i + 1]
    const length = haversine(...a, ...b)
    segments.push({
      index: i,
      from: a,
      to: b,
      length_m: length,
      distance_km: length / KM_TO_M,
      distance_nm: length / NM_TO_M,
      bearing: bearing(...a, ...b),
    })
  }
  const total = segments.reduce((sum, s) => sum + s.length_m, 0)
  return {
    point_count: coordinates.length,
    segment_count: segments.length,
    total_length_m: total,
    total_length_km: total / KM_TO_M,
    total_length_nm: total / NM_TO_M,
    segments,
  }
}

export function boundsOf(coordinates) {
  const pts = (coordinates || []).filter((c) => c && c.length >= 2)
  if (!pts.length) return null
  const lats = pts.map((p) => Number(p[0]))
  const lons = pts.map((p) => Number(p[1]))
  return [[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]]
}

// ─── Coordinate formatting (spec §5) ─────────────────────────────────────────

export function formatDms(value, isLatitude) {
  const hemisphere = isLatitude
    ? value >= 0 ? 'N' : 'S'
    : value >= 0 ? 'E' : 'W'
  const abs = Math.abs(Number(value))
  const degrees = Math.floor(abs)
  const minutesFull = (abs - degrees) * 60
  const minutes = Math.floor(minutesFull)
  const seconds = (minutesFull - minutes) * 60
  return `${degrees}°${String(minutes).padStart(2, '0')}'${seconds
    .toFixed(2)
    .padStart(5, '0')}"${hemisphere}`
}

export function formatCoordinate(value, isLatitude, fmt = 'dd') {
  if (fmt === 'dms') return formatDms(value, isLatitude)
  if (fmt === 'dmm') {
    const hemisphere = isLatitude
      ? value >= 0 ? 'N' : 'S'
      : value >= 0 ? 'E' : 'W'
    const abs = Math.abs(Number(value))
    const degrees = Math.floor(abs)
    const minutes = (abs - degrees) * 60
    return `${degrees}°${minutes.toFixed(3).padStart(6, '0')}'${hemisphere}`
  }
  return Number(value).toFixed(6)
}

/**
 * The cursor readout (spec §5). Must match
 * `app/core/geo.py::format_latlon` byte for byte.
 */
export function formatLatLon(lat, lon, fmt = 'dd') {
  if (lat === null || lat === undefined || lon === null || lon === undefined) {
    return 'LAT —   LON —'
  }
  if (fmt === 'dd') {
    const latText = Number(lat).toFixed(6).padStart(9, ' ')
    const lonText = Number(lon).toFixed(6).padStart(10, ' ')
    return `LAT ${latText}  LON ${lonText}`
  }
  return `LAT ${formatCoordinate(lat, true, fmt)}  LON ${formatCoordinate(lon, false, fmt)}`
}

/** Plain ``lat, lon`` string for the clipboard. */
export function toPlainString(lat, lon) {
  return `${Number(lat).toFixed(6)}, ${Number(lon).toFixed(6)}`
}

export function round(value, digits = 3) {
  const f = 10 ** digits
  return Math.round(Number(value) * f) / f
}
