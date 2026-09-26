/**
 * tests/geo.spec.js
 * ─────────────────
 * Frontend geodesy, verified against the same vectors the Python suite
 * uses (see tests/test_geo.py and tests/geo_parity.mjs).
 *
 * This module is the only place these numbers are computed, so the map,
 * the inspector, the status bar and the exports cannot disagree.
 */

import { describe, it, expect } from 'vitest'
import {
  toMetres, fromMetres, convert, nmToKm, kmToNm,
  haversine, haversineKm, bearing, destination, radialPoints, circlePoints,
  normaliseAzimuth, compassPoint, formatAzimuth,
  pathLengthM, pathSummary, boundsOf,
  formatDms, formatCoordinate, formatLatLon, toPlainString,
  formatRadius, formatDistance, round,
  NM_TO_M, EARTH_RADIUS_M,
} from '@/map/geo'

describe('units', () => {
  it('uses the exact international nautical mile', () => {
    expect(NM_TO_M).toBe(1852)
    expect(nmToKm(20)).toBeCloseTo(37.04, 12)
    expect(toMetres(20, 'nm')).toBeCloseTo(37040, 9)
  })

  it('converts between every supported unit', () => {
    expect(convert(20, 'nm', 'km')).toBeCloseTo(37.04, 9)
    expect(convert(37.04, 'km', 'nm')).toBeCloseTo(20, 9)
    expect(convert(37040, 'm', 'nm')).toBeCloseTo(20, 9)
  })

  it('round-trips', () => {
    for (const v of [1, 5, 20, 50, 100, 37.04]) {
      expect(kmToNm(nmToKm(v))).toBeCloseTo(v, 9)
    }
  })

  it('falls back to nm for an unknown unit', () => {
    // A typo must not silently produce a wrong distance.
    expect(fromMetres(1852, 'furlongs')).toBeCloseTo(1, 9)
    expect(fromMetres(1852, undefined)).toBeCloseTo(1, 9)
  })

  it('shows both units in a radius label', () => {
    expect(formatRadius(20, 'nm')).toBe('20.00 NM (37.04 km)')
    expect(formatRadius(5, 'km')).toBe('5.00 km')
  })

  it('shows metres, km and NM in a distance', () => {
    expect(formatDistance(37_040)).toContain('37.040 km')
    expect(formatDistance(37_040)).toContain('20.000 NM')
    expect(formatDistance(null)).toBe('—')
  })
})

describe('distance', () => {
  it('is zero for identical points', () => {
    expect(haversine(-34.6, -58.4, -34.6, -58.4)).toBeCloseTo(0, 6)
  })

  it('matches a known great-circle length', () => {
    // One degree of latitude is about 111.195 km.
    expect(haversineKm(0, 0, 1, 0)).toBeCloseTo(111.195, 2)
  })

  it('matches EZE to Cordoba within 0.5%', () => {
    const m = haversine(-34.8222, -58.5358, -31.3208, -64.1888)
    expect(m / 1000).toBeCloseTo(653, -1)
  })

  it('is symmetric', () => {
    const a = haversine(-34.6, -58.4, -34.5, -58.3)
    const b = haversine(-34.5, -58.3, -34.6, -58.4)
    expect(a).toBeCloseTo(b, 9)
  })

  it('survives antipodal points without NaN', () => {
    const d = haversine(0, 0, 0, 180)
    expect(Number.isFinite(d)).toBe(true)
    expect(d).toBeCloseTo(Math.PI * EARTH_RADIUS_M, 0)
  })
})

describe('bearing and destination', () => {
  it('gives cardinal bearings', () => {
    expect(bearing(0, 0, 0, 1)).toBeCloseTo(90, 6)
    expect(bearing(0, 0, 1, 0)).toBeCloseTo(0, 6)
    expect(bearing(1, 0, 0, 0)).toBeCloseTo(180, 6)
  })

  it('matches the spec example: 20 NM at azimuth 90', () => {
    const [lat, lon] = destination(-34.603722, -58.381592, 90, 37_040)
    // A great circle with an initial bearing of 90° still drifts toward
    // the equator as it goes, so the latitude moves by ~0.0007°. The
    // Python test allows 0.001 for exactly this reason.
    expect(Math.abs(lat - -34.603722)).toBeLessThan(0.001)
    expect(lon).toBeCloseTo(-58.381592 + 0.4055, 2)
    expect(haversine(-34.603722, -58.381592, lat, lon)).toBeCloseTo(37_040, -2)
  })

  it('returns the origin for zero distance', () => {
    expect(destination(-34.6, -58.4, 45, 0)).toEqual([-34.6, -58.4])
  })

  it('round-trips every bearing', () => {
    for (let az = 0; az < 360; az += 15) {
      const [lat, lon] = destination(-34.6, -58.4, az, 50_000)
      expect(bearing(-34.6, -58.4, lat, lon)).toBeCloseTo(az, 0)
    }
  })

  it('keeps longitude inside [-180, 180]', () => {
    const [, lon] = destination(0, 179.9, 90, 200_000)
    expect(lon).toBeGreaterThanOrEqual(-180)
    expect(lon).toBeLessThanOrEqual(180)
  })
})

describe('azimuth', () => {
  it('normalises into [0, 360)', () => {
    expect(normaliseAzimuth(450)).toBeCloseTo(90, 9)
    expect(normaliseAzimuth(-90)).toBeCloseTo(270, 9)
    expect(normaliseAzimuth(360)).toBeCloseTo(0, 9)
  })

  it('maps compass points', () => {
    expect(compassPoint(0)).toBe('N')
    expect(compassPoint(90)).toBe('E')
    expect(compassPoint(135)).toBe('SE')
    expect(compassPoint(270)).toBe('W')
  })

  it('formats', () => {
    expect(formatAzimuth(135)).toBe('135°')
    expect(formatAzimuth(405)).toBe('45°')
  })
})

describe('circle', () => {
  it('produces the requested number of vertices', () => {
    expect(circlePoints(-34.6, -58.4, 10_000, 72).length).toBe(72)
  })

  it('enforces a minimum of 8', () => {
    expect(circlePoints(-34.6, -58.4, 100, 1).length).toBeGreaterThanOrEqual(8)
  })

  it('puts every vertex on the radius', () => {
    for (const [lat, lon] of circlePoints(-34.6, -58.4, 18_520, 24)) {
      expect(haversine(-34.6, -58.4, lat, lon)).toBeCloseTo(18_520, -3)
    }
  })

  it('collapses to the centre for zero radius', () => {
    expect(circlePoints(-34.6, -58.4, 0)).toEqual([[-34.6, -58.4]])
  })
})

describe('radial', () => {
  it('follows the curvature of the Earth', () => {
    const pts = radialPoints([0, 0], 90, 1_000_000, 8)
    const lats = pts.map((p) => p[0])
    // Heading east from the equator along a great circle curves north.
    expect(lats[lats.length - 1]).toBeGreaterThan(lats[0])
  })

  it('ends at the requested distance', () => {
    const pts = radialPoints([-34.6, -58.4], 270, 37_040, 8)
    const end = pts[pts.length - 1]
    expect(haversine(-34.6, -58.4, end[0], end[1])).toBeCloseTo(37_040, -3)
  })

  it('normalises the azimuth', () => {
    const pts = radialPoints([-34.6, -58.4], 405, 10_000, 2)
    const pts45 = radialPoints([-34.6, -58.4], 45, 10_000, 2)
    expect(pts[1]).toEqual(pts45[1])
  })
})

describe('paths', () => {
  const PATH = [[-34.603722, -58.381592], [-34.5, -58.3], [-34.4, -58.2]]

  it('sums the segments', () => {
    const summary = pathSummary(PATH)
    const manual = pathLengthM(PATH)
    expect(summary.total_length_m).toBeCloseTo(manual, 6)
    expect(summary.segment_count).toBe(2)
    expect(summary.point_count).toBe(3)
  })

  it('agrees between km and nm', () => {
    const s = pathSummary(PATH)
    expect(s.total_length_km * 1000).toBeCloseTo(s.total_length_m, 6)
    expect(s.total_length_nm * 1852).toBeCloseTo(s.total_length_m, 6)
  })

  it('handles an empty path', () => {
    const s = pathSummary([])
    expect(s.point_count).toBe(0)
    expect(s.total_length_m).toBe(0)
  })

  it('computes bounds', () => {
    expect(boundsOf(PATH)).toEqual([
      [-34.603722, -58.381592],
      [-34.4, -58.2],
    ])
    expect(boundsOf([])).toBeNull()
  })
})

describe('coordinate formatting', () => {
  it('matches the backend byte for byte', () => {
    // Mirrors app/core/geo.py::format_latlon. The Python suite compares
    // the same string, so a divergence here fails both suites.
    expect(formatLatLon(-34.603722, -58.381592)).toBe(
      'LAT -34.603722  LON -58.381592',
    )
  })

  it('shows a placeholder when there is no position', () => {
    expect(formatLatLon(null, null)).toBe('LAT —   LON —')
    expect(formatLatLon(-34.6, undefined)).toContain('—')
  })

  it('formats DMS with the right hemisphere', () => {
    expect(formatDms(-34.603722, true)).toBe('34°36\'13.40"S')
    expect(formatDms(34.603722, false)).toContain('E')
  })

  it('formats DMM and DD', () => {
    expect(formatCoordinate(34.5, true, 'dmm')).toBe('34°30.000\'N')
    expect(formatCoordinate(-34.6, true, 'dd')).toBe('-34.600000')
  })

  it('produces a clipboard string', () => {
    expect(toPlainString(-34.603722, -58.381592)).toBe('-34.603722, -58.381592')
  })
})

describe('rounding', () => {
  it('rounds to a number of decimals', () => {
    expect(round(1.23456, 2)).toBe(1.23)
    expect(round(1.23556, 2)).toBe(1.24)
    expect(round(0)).toBe(0)
  })
})
