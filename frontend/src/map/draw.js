/**
 * map/draw.js
 * ───────────
 * The GIS tool system (spec §6).
 *
 * Every tool is a state machine with the same contract:
 *   activate() → capture clicks → emit a completed feature → deactivate
 * with `ESC` cancelling, a live preview, and post-creation editing handled
 * by the map store.
 *
 * Tools never write to the database. They emit a plain description of
 * what the operator drew, and the store decides how to persist it. That
 * keeps "what is being drawn" separate from "what is stored", which is
 * what makes undo and cancellation straightforward.
 */

import L from 'leaflet'

import {
  bearing as bearingBetween,
  destination,
  formatRadius,
  fromMetres,
  haversine,
  radialPoints,
  round,
  toMetres,
} from './geo'

export const TOOLS = {
  SELECT: 'select',
  POINT: 'point',
  LINE: 'line',
  POLYGON: 'polygon',
  CIRCLE: 'circle',
  RADIAL: 'radial',
  MEASURE: 'measure',
  TRACE: 'trace',
  COVERAGE: 'coverage',
  ANNOTATION: 'annotation',
}

/** Human labels and the cursor each tool uses (spec §6). */
export const TOOL_META = {
  [TOOLS.SELECT]: { label: 'Seleccionar', icon: '▸', cursor: 'default', hint: 'Haga clic en un objeto para inspeccionarlo.' },
  [TOOLS.POINT]: { label: 'Punto', icon: '📍', cursor: 'crosshair', hint: 'Haga clic en el mapa para crear un punto.' },
  [TOOLS.LINE]: { label: 'Línea', icon: '╱', cursor: 'crosshair', hint: 'Clic para cada vértice. Doble clic o Enter para terminar. ESC cancela.' },
  [TOOLS.POLYGON]: { label: 'Polígono', icon: '⬠', cursor: 'crosshair', hint: 'Clic para cada vértice (mínimo 3). Doble clic o Enter para cerrar. ESC cancela.' },
  [TOOLS.CIRCLE]: { label: 'Círculo', icon: '◯', cursor: 'crosshair', hint: 'Clic para fijar el centro, luego mueva para definir el radio.' },
  [TOOLS.RADIAL]: { label: 'Radial', icon: '➤', cursor: 'crosshair', hint: 'Clic para el origen, mueva para fijar azimut y longitud.' },
  [TOOLS.MEASURE]: { label: 'Medir', icon: '📏', cursor: 'crosshair', hint: 'Clic en A, clic en B. Clic sucesivos para multipunto. ESC termina.' },
  [TOOLS.TRACE]: { label: 'Traza', icon: '∿', cursor: 'crosshair', hint: 'Clic para agregar vértices. Doble clic o Enter para guardar. ESC cancela.' },
  [TOOLS.COVERAGE]: { label: 'Cobertura', icon: '▩', cursor: 'crosshair', hint: 'Dibuje el contorno del área de cobertura.' },
  [TOOLS.ANNOTATION]: { label: 'Anotación', icon: '✎', cursor: 'crosshair', hint: 'Haga clic para dejar una anotación en el mapa.' },
}

const EARTH_RADIUS_M = 6371008.8

export class ToolManager {
  /**
   * @param {import('./MapEngine').MapEngine} engine
   * @param {object} handlers  {onComplete, onPreview, onChange, onError}
   */
  constructor(engine, handlers = {}) {
    this.engine = engine
    this.handlers = handlers

    this.active = null
    this.draft = null
    this._unsubscribe = null
    this._keyHandler = null
    /** Options the store injects (radius unit, default names, …). */
    this.options = { unit: 'nm', radius: 5, length: 10, azimuth: 0 }
  }

  // ─── Activation ───────────────────────────────────────────────────────────

  /**
   * Activate a tool. Switching tools cancels any in-progress drawing.
   * @param {string} name
   * @param {object} [options] initial parameters (radius, unit, length…)
   */
  activate(name, options = {}) {
    if (!Object.values(TOOLS).includes(name)) {
      throw new Error(`Herramienta desconocida: ${name}`)
    }
    if (this.active === name) {
      this.deactivate()
      return
    }
    if (this.active) this.cancel()

    this.active = name
    this.options = { ...this.options, ...options }
    this.draft = null

    if (name === TOOLS.SELECT) {
      this._restoreCursor()
      this._emitChange()
      return
    }

    // Consume map clicks and reflect the tool's cursor.
    this.engine.suppressClicks(false)
    this._setCursor(TOOL_META[name].cursor)

    this._unsubscribe = this.engine.on('click', (payload) => this._onClick(payload))

    const onKey = (event) => this._onKey(event)
    window.addEventListener('keydown', onKey)
    this._keyHandler = onKey

    this._emitChange()
  }

  /** Finish the current drawing and clean up. */
  deactivate() {
    this.cleanup()
    this.active = null
    this.draft = null
    this._emitChange()
  }

  /** Abort without emitting anything. ESC key (spec §6). */
  cancel() {
    this.cleanup()
    this.active = null
    this.draft = null
    this._emitChange()
  }

  cleanup() {
    this.engine.clearDrafts()
    if (this._unsubscribe) {
      this._unsubscribe()
      this._unsubscribe = null
    }
    if (this._keyHandler) {
      window.removeEventListener('keydown', this._keyHandler)
      this._keyHandler = null
    }
    this._restoreCursor()
  }

  get isDrawing() {
    return this.active !== null && this.active !== TOOLS.SELECT
  }

  get cursor() {
    return this.active ? TOOL_META[this.active]?.cursor : 'default'
  }

  get hint() {
    return this.active ? TOOL_META[this.active]?.hint : ''
  }

  _setCursor(cursor) {
    if (this.engine?.container) {
      this.engine.container.style.cursor = cursor
    }
  }

  _restoreCursor() {
    if (this.engine?.container) this.engine.container.style.cursor = ''
  }

  _emitChange() {
    this.handlers.onChange?.({ tool: this.active, draft: this.draft, hint: this.hint })
  }

  _onKey(event) {
    if (event.key === 'Escape') {
      event.preventDefault()
      this.cancel()
    } else if (event.key === 'Enter') {
      event.preventDefault()
      this.finish()
    } else if (event.key === 'Backspace' && this.draft?.points?.length) {
      event.preventDefault()
      this.draft.points.pop()
      this._redraw()
    }
  }

  // ─── Click handling ───────────────────────────────────────────────────────

  _onClick({ latlng }) {
    const point = [latlng.lat, latlng.lng]
    switch (this.active) {
      case TOOLS.POINT:
        return this._emitComplete({ type: 'point', latitude: point[0], longitude: point[1] })

      case TOOLS.ANNOTATION:
        return this._emitComplete({ type: 'annotation', latitude: point[0], longitude: point[1] })

      case TOOLS.LINE:
      case TOOLS.TRACE:
        return this._pushPoint(point)

      case TOOLS.POLYGON:
      case TOOLS.COVERAGE:
        return this._pushPoint(point, true)

      case TOOLS.CIRCLE:
        return this._startCircle(point)

      case TOOLS.RADIAL:
        return this._startRadial(point)

      case TOOLS.MEASURE:
        return this._pushPoint(point, true)

      default:
        return undefined
    }
  }

  /** Mousemove preview while a shape is being sized. */
  previewAt(latlng) {
    if (!this.draft) return
    const point = [latlng.lat, latlng.lng]
    if (this.active === TOOLS.CIRCLE) this._updateCircle(point)
    else if (this.active === TOOLS.RADIAL) this._updateRadial(point)
  }

  // ─── Point accumulation ───────────────────────────────────────────────────

  _pushPoint(point, closeable = false) {
    this.draft = this.draft || { type: this.active, points: [] }
    this.draft.points.push(point)
    this._redraw()
    this._emitChange()
  }

  _redraw() {
    if (!this.draft) return
    const points = this.draft.points

    if (this.active === TOOLS.POLYGON || this.active === TOOLS.COVERAGE) {
      this.engine.setDraft(
        'polygon',
        points.length >= 3
          ? L.polygon(points, {
              color: '#22d3ee',
              weight: 2,
              fillOpacity: 0.15,
              dashArray: '4,4',
            })
          : L.polyline(points, { color: '#22d3ee', weight: 2, dashArray: '4,4' }),
      )
      this._renderVertices(points)
      return
    }

    if (this.active === TOOLS.MEASURE) {
      // A dashed path plus per-vertex handles.
      this.engine.setDraft(
        'measure',
        L.polyline(points, { color: '#facc15', weight: 2, dashArray: '5,5' }),
      )
      this._renderVertices(points, '#facc15')
      this.handlers.onPreview?.({ type: 'measure', points: [...points] })
      return
    }

    this.engine.setDraft(
      'line',
      L.polyline(points, { color: '#22d3ee', weight: 3, dashArray: '6,4' }),
    )
    this._renderVertices(points)
  }

  _renderVertices(points, color = '#22d3ee') {
    this.engine.clearDraft('vertices')
    if (!points.length) return
    const group = L.layerGroup(
      points.map((p, i) =>
        L.circleMarker(p, {
          radius: 4,
          color,
          fillColor: '#0f172a',
          fillOpacity: 1,
          weight: 2,
        }).bindTooltip(String(i + 1), { permanent: false }),
      ),
    )
    this.engine.setDraft('vertices', group)
  }

  // ─── Circle (spec §10) ────────────────────────────────────────────────────

  _startCircle(center) {
    const radius = this.options.radius ?? 5
    this.draft = {
      type: TOOLS.CIRCLE,
      center,
      radius,
      unit: this.options.unit,
      radiusM: toMetres(radius, this.options.unit),
    }
    // Draw the preview at the radius the operator typed. Measuring here
    // would compute the distance from the centre to itself — zero — and
    // throw away the value the tool options panel just set.
    this._renderCircle()
    this._emitChange()
  }

  _updateCircle(point) {
    const { center } = this.draft
    const distanceM = haversine(center[0], center[1], point[0], point[1])
    this.draft.radiusM = distanceM
    // Report the radius in the unit the operator is working in.
    this.draft.radius = fromMetres(distanceM, this.draft.unit)
    this._renderCircle()
  }

  /** Paint the current draft. Pure rendering: no measurement, no state change. */
  _renderCircle() {
    const { center, radiusM, radius, unit } = this.draft
    this.engine.setDraft(
      'circle',
      L.circle(center, {
        radius: radiusM,
        color: '#3b82f6',
        weight: 2,
        fillOpacity: 0.12,
        dashArray: '5,5',
      }).bindTooltip(formatRadius(radius, unit), { sticky: true }),
    )
    this.engine.setDraft(
      'center',
      L.circleMarker(center, { radius: 5, color: '#3b82f6', fillOpacity: 1, weight: 2 }),
    )
    this.handlers.onPreview?.({ type: 'circle', ...this.draft })
  }

  /** Confirm the current circle. */
  commitCircle() {
    if (this.active !== TOOLS.CIRCLE || !this.draft?.center) return null
    const { center, radiusM } = this.draft
    return this._emitComplete({
      type: 'circle',
      latitude: center[0],
      longitude: center[1],
      radius: round(this.draft.radius, 3),
      radius_unit: this.draft.unit,
      radius_m: radiusM,
    })
  }

  // ─── Radial (spec §11, §37) ───────────────────────────────────────────────

  _startRadial(origin) {
    const length = this.options.length ?? 10
    this.draft = {
      type: TOOLS.RADIAL,
      origin,
      azimuth: this.options.azimuth ?? 0,
      length,
      unit: this.options.unit,
      lengthM: toMetres(length, this.options.unit),
    }
    // Same reasoning as _startCircle: measuring against the origin itself
    // yields a bearing of 0 and a length of 0, discarding what the options
    // panel set. Draw the draft as typed and let the pointer adjust it.
    this._renderRadial()
    this._emitChange()
  }

  _updateRadial(point) {
    const { origin } = this.draft
    const azimuth = bearingBetween(origin[0], origin[1], point[0], point[1])
    const lengthM = haversine(origin[0], origin[1], point[0], point[1])
    this.draft.azimuth = azimuth
    this.draft.lengthM = lengthM
    this.draft.length = fromMetres(lengthM, this.draft.unit)
    this._renderRadial()
  }

  /** Paint the current draft. Pure rendering: no measurement, no state change. */
  _renderRadial() {
    const { origin, azimuth, lengthM, length, unit } = this.draft
    this.engine.setDraft(
      'radial',
      L.polyline(radialPoints(origin, azimuth, lengthM, 24), {
        color: '#a855f7',
        weight: 3,
        dashArray: '7,5',
      }).bindTooltip(`${azimuth.toFixed(1)}° · ${formatRadius(length, unit)}`, {
        sticky: true,
      }),
    )
    this.engine.setDraft(
      'origin',
      L.circleMarker(origin, { radius: 5, color: '#a855f7', fillOpacity: 1, weight: 2 }),
    )
    this.handlers.onPreview?.({ type: 'radial', ...this.draft })
  }

  commitRadial() {
    if (this.active !== TOOLS.RADIAL || !this.draft?.origin) return null
    const { origin, azimuth, lengthM } = this.draft
    return this._emitComplete({
      type: 'radial',
      latitude: origin[0],
      longitude: origin[1],
      azimuth: round(azimuth, 2),
      length_value: round(this.draft.length, 3),
      length_unit: this.draft.unit,
      length_m: lengthM,
    })
  }

  // ─── Commit ───────────────────────────────────────────────────────────────

  /** Finish the current drawing (Enter, or the tool's confirm button). */
  finish() {
    if (!this.draft) return null
    if (this.active === TOOLS.CIRCLE) return this.commitCircle()
    if (this.active === TOOLS.RADIAL) return this.commitRadial()

    const points = this.draft.points || []
    if (this.active === TOOLS.POLYGON || this.active === TOOLS.COVERAGE) {
      if (points.length < 3) return null
      return this._emitComplete({
        type: this.active,
        latitude: points[0][0],
        longitude: points[0][1],
        properties: { ring: points },
        ...(this.active === TOOLS.COVERAGE ? {} : {}),
      })
    }

    if (this.active === TOOLS.MEASURE) {
      if (points.length < 2) return null
      return this._emitComplete({ type: 'measurement', properties: { path: points } })
    }

    if (points.length < 2) return null
    return this._emitComplete({
      type: this.active === TOOLS.TRACE ? 'trace' : 'line',
      latitude: points[0][0],
      longitude: points[0][1],
      properties: { path: points },
    })
  }

  _emitComplete(payload) {
    this.cleanup()
    this.draft = null
    this.active = null
    this.handlers.onComplete?.(payload)
    this._emitChange()
    return payload
  }
}

// Geodesy helpers now live in ./geo: one source of truth, no Leaflet
// dependency, unit-testable in Node. Re-exported for call sites.
export { haversine, bearingBetween as bearing, destination, radialPoints }
export { toMetres, fromMetres, formatRadius, round }


export default ToolManager
