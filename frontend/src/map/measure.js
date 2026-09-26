/**
 * map/measure.js
 * ──────────────
 * Distance measurement, Google-Earth style (spec §13).
 *
 * Two modes:
 *   • simple  — A → B, one segment
 *   • multi   — A → B → C → D, per-segment plus total
 *
 * The live readout shows metres, kilometres AND nautical miles, because a
 * protection volume is quoted in NM and a report needs km. A measurement
 * is transient by default; the operator can save it as a real object, at
 * which point it goes through the normal object pipeline and gains a
 * history and notes.
 */

import L from 'leaflet'
import { formatDistance as formatMetres, haversine, NM_TO_M } from './geo'

export const MEASURE_MODES = { SINGLE: 'single', MULTI: 'multi' }

export class MeasureEngine {
  /**
   * @param {import('./MapEngine').MapEngine} engine
   * @param {object} handlers {onChange}
   */
  constructor(engine, handlers = {}) {
    this.engine = engine
    this.handlers = handlers

    this.points = []
    this.mode = MEASURE_MODES.MULTI
    this.active = false
  }

  start(mode = MEASURE_MODES.MULTI) {
    this.reset()
    this.active = true
    this.mode = mode
  }

  stop() {
    this.reset()
  }

  reset() {
    this.points = []
    this.active = false
    this.engine.clearDraft('measure')
    this.engine.clearDraft('measure-vertices')
    this.engine.clearDraft('measure-labels')
    this._notify()
  }

  /** Add a point. Returns the recomputed measurement. */
  addPoint(latlng) {
    if (!this.active) this.start()
    const point = [latlng.lat, latlng.lng]
    this.points.push(point)
    this.render()
    return this.current()
  }

  /** Remove the most recent point (Backspace). */
  undo() {
    if (!this.points.length) return this.current()
    this.points.pop()
    this.render()
    return this.current()
  }

  /**
   * The current measurement.
   * @returns {{
   *   active: boolean, mode: string, points: Array,
   *   segments: Array, total_m: number, total_km: number, total_nm: number
   * }}
   */
  current() {
    const segments = []
    for (let i = 0; i < this.points.length - 1; i += 1) {
      const [aLat, aLon] = this.points[i]
      const [bLat, bLon] = this.points[i + 1]
      const distanceM = haversine(aLat, aLon, bLat, bLon)
      segments.push({
        index: i,
        from: [aLat, aLon],
        to: [bLat, bLon],
        distance_m: distanceM,
        distance_km: distanceM / 1000,
        distance_nm: distanceM / NM_TO_M,
        bearing: bearingBetween(aLat, aLon, bLat, bLon),
        label: formatMetres(distanceM),
      })
    }

    const totalM = segments.reduce((sum, s) => sum + s.distance_m, 0)
    return {
      active: this.active,
      mode: this.mode,
      points: [...this.points],
      segment_count: segments.length,
      segments,
      total_m: totalM,
      total_km: totalM / 1000,
      total_nm: totalM / NM_TO_M,
      total_label: formatMetres(totalM),
      area_note: this.points.length >= 3 ? this._area() : null,
    }
  }

  /** Planar approximation of a closed polygon, in km². */
  _area() {
    const pts = this.points
    if (pts.length < 3) return null
    const meanLat = pts.reduce((s, p) => s + p[0], 0) / pts.length
    const mPerDegLat = 111_132
    const mPerDegLon = 111_320 * Math.cos((meanLat * Math.PI) / 180)
    let sum = 0
    for (let i = 0; i < pts.length; i += 1) {
      const [y1, x1] = pts[i]
      const [y2, x2] = pts[(i + 1) % pts.length]
      sum += x1 * mPerDegLon * (y2 * mPerDegLat) - x2 * mPerDegLon * (y1 * mPerDegLat)
    }
    return Math.abs(sum / 2) / 1e6
  }

  render() {
    this.engine.clearDraft('measure')
    this.engine.clearDraft('measure-vertices')
    this.engine.clearDraft('measure-labels')
    if (this.points.length < 1) return

    if (this.points.length >= 2) {
      this.engine.setDraft(
        'measure',
        L.polyline(this.points, {
          color: '#facc15',
          weight: 3,
          opacity: 0.95,
          dashArray: '8,5',
        }),
      )
    }

    // Vertices, lettered A, B, C…
    this.engine.setDraft(
      'measure-vertices',
      L.layerGroup(
        this.points.map((p, i) =>
          L.circleMarker(p, {
            radius: 5,
            color: '#facc15',
            fillColor: '#0f172a',
            fillOpacity: 1,
            weight: 2,
          }).bindTooltip(String.fromCharCode(65 + i), { permanent: true, direction: 'top' }),
        ),
      ),
    )

    // Midpoint label for each segment.
    const m = this.current()
    this.engine.setDraft(
      'measure-labels',
      L.layerGroup(
        m.segments.map((s) => {
          const mid = [(s.from[0] + s.to[0]) / 2, (s.from[1] + s.to[1]) / 2]
          return L.marker(mid, {
            interactive: false,
            icon: L.divIcon({
              className: 'aerorf-measure-label',
              html: `<span>${s.label}</span>`,
              iconSize: null,
            }),
          })
        }),
      ),
    )
  }

  /** Payload for persisting the measurement as a real object. */
  toObjectPayload(name = null) {
    const m = this.current()
    if (m.points.length < 2) return null
    return {
      type: 'measurement',
      name,
      latitude: m.points[0][0],
      longitude: m.points[0][1],
      properties: { path: m.points },
      measurement: {
        mode: this.mode,
        total_m: m.total_m,
        total_km: m.total_km,
        total_nm: m.total_nm,
        segments: m.segments,
      },
    }
  }

  _notify() {
    this.handlers.onChange?.(this.current())
  }
}

// ─── Formatting ──────────────────────────────────────────────────────────────

function bearingBetween(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180
  const φ1 = toRad(lat1)
  const φ2 = toRad(lat2)
  const Δλ = toRad(lon2 - lon1)
  const y = Math.sin(Δλ) * Math.cos(φ2)
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ)
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
}

export { formatMetres as formatDistance, haversine }
export default MeasureEngine
