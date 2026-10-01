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
  arcPoints,
  bearing as bearingBetween,
  destination,
  formatDistance,
  formatRadius,
  fromMetres,
  haversine,
  radialPoints,
  round,
  snapToleranceM,
  toMetres,
} from './geo'

/** The 16-point compass label for an azimuth, for the label on the map. */
function compassPoint(azimuth) {
  const NAMES = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
    'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
  const index = Math.floor(((((azimuth % 360) + 360) % 360) + 11.25) % 360 / 22.5) % 16
  return NAMES[index]
}

/**
 * How close, in screen pixels, a click must be to a shape's centre to snap
 * onto it.
 *
 * Ten pixels is enough to be deliberate and small enough not to fight the
 * operator. Large enough to be reachable on a trackpad, small enough that
 * placing a point in open ground well away from any shape is unaffected.
 */
const SNAP_PIXELS = 10

/** Used only before the map exists; a mid-zoom Web Mercator pixel. */
const SNAP_METRES_PER_PIXEL_FALLBACK = 100

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
    // `useTyped` picks how a circle or a radial gets its size. False is the
    // original interaction — click the centre, then click where you want the
    // edge — and it is the default, so nothing that worked before changes.
    // True makes the panel's number the size: one click, and the number you
    // typed is the number stored.
    this.options = { unit: 'nm', radius: 5, length: 10, azimuth: 0, useTyped: false }
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
    // A new shape starts without a pointer position: the sizing line is drawn
    // from the centre to here, and until the pointer moves there is no
    // "here".
    this._pointer = null

    if (name === TOOLS.SELECT) {
      this._restoreCursor()
      // Show the shape at its configured size straight away, so choosing a radius
    // is a decision made against the map rather than against a number.
    this._renderGhost()
    this._emitChange()
      return
    }

    // Consume map clicks and reflect the tool's cursor.
    this.engine.suppressClicks(false)
    this._setCursor(TOOL_META[name].cursor)

    // One stable handler, subscribed once. It stays subscribed for as long as
    // the tool is armed, including between one committed shape and the next,
    // so that finishing a circle does not have to touch the subscription.
    this._onEngineClick = (payload) => this._onClick(payload)
    this._unsubscribe = this.engine.on('click', this._onEngineClick)

    const onKey = (event) => this._onKey(event)
    window.addEventListener('keydown', onKey)
    this._keyHandler = onKey

    // Show the shape at its configured size straight away, so choosing a radius
    // is a decision made against the map rather than against a number.
    this._renderGhost()
    this._emitChange()
  }

  /**
   * Report the current shape to the panel.
   *
   * Separate from `_emitChange`, which carries the draft to the store. The
   * panel needs the measured values as the pointer moves — the degrees of a
   * radial, the radius of a circle — and the store's draft is not what the
   * operator reads.
   */
  _emitPreview(payload) {
    this.handlers.onPreview?.(payload)
  }

  /**
   * Re-read the options without changing the active tool.
   *
   * The options were snapshotted in `activate`, so a radius typed *after* the
   * tool was picked was ignored: the operator set 20 NM, clicked, and got a
   * circle of whatever the previous default happened to be. The tool options
   * panel is meant to be usable while drawing, so the panel pushes its changes
   * here rather than requiring the operator to re-pick the tool.
   *
   * An in-progress shape is not resized. Its centre has already been placed
   * and the operator may be mid-drag, so changing the radius under their
   * pointer would move the ring they are sizing. It applies to the next shape.
   */
  setOptions(options = {}) {
    this.options = { ...this.options, ...options }
    // Re-paint the ghost preview. It is the operator's answer to "what does
    // 5 NM actually look like here?", and it is the only thing on screen when
    // the tool is picked but nothing has been clicked yet.
    if (!this.draft) {
      this._renderGhost()
      this._emitChange()
    }
  }

  /**
   * The shape at its configured size, drawn before the operator clicks.
   *
   * Selecting the circle tool with a radius of 5 NM used to show nothing at
   * all: the ring only appeared once the centre was placed, so the number in
   * the panel could not be judged against the map. Choosing a radius without
   * seeing what it covers is choosing it blind, which defeats the point of
   * setting one.
   *
   * Drawn faintly and without any fill, so it reads as a guide rather than as
   * the object. The real shape, once the centre is placed, is drawn solid.
   */
  _renderGhost() {
    const center = this._ghostCenter()
    if (!center) {
      this.engine.removeDraft('ghost')
      return
    }
    if (this.active === TOOLS.CIRCLE) {
      const unit = this.options.unit
      const radius = this.options.radius ?? 5
      this.engine.setDraft(
        'ghost',
        L.circle(center, {
          radius: toMetres(radius, unit),
          color: '#3b82f6',
          weight: 1.5,
          fillOpacity: 0,
          opacity: 0.55,
          dashArray: '2,6',
          interactive: false,
        }),
      )
      this._emitPreview({
        type: 'circle',
        ghost: true,
        latitude: center[0],
        longitude: center[1],
        radius,
        radius_m: toMetres(radius, unit),
        unit,
      })
      return
    }
    if (this.active === TOOLS.RADIAL) {
      const unit = this.options.unit
      const length = this.options.length ?? 10
      const azimuth = this.options.azimuth ?? 0
      this.engine.setDraft(
        'ghost',
        L.polyline(radialPoints(center, azimuth, toMetres(length, unit), 24), {
          color: '#a855f7',
          weight: 1.5,
          opacity: 0.55,
          dashArray: '2,6',
          interactive: false,
        }),
      )
      this._emitPreview({
        type: 'radial',
        ghost: true,
        latitude: center[0],
        longitude: center[1],
        azimuth,
        length,
        length_m: toMetres(length, unit),
        unit,
      })
    }
  }

  /**
   * Where the ghost is drawn: where the pointer last was, else the view centre.
   *
   * The view centre is the better default of the two, because it is where the
   * operator is looking, and it is known before any click happens.
   */
  _ghostCenter() {
    if (this._pointer) return this._pointer
    const c = this.engine.getCenter?.()
    return c ? [c.lat, c.lng] : null
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

  /**
   * Clear what a finished shape leaves behind, without touching the
   * subscription.
   *
   * Split out of `cleanup()` for one specific reason. The engine emits by
   * walking a `Set` with `forEach`, and `forEach` visits entries **added during
   * the iteration**. So a click handler that unsubscribes and re-subscribes
   * while it is being called hands the event straight back to its replacement,
   * which commits, re-subscribes again, and the walk never ends: the tab locks
   * up on the first click.
   *
   * That is what leaving the tool armed looked like when it was first written.
   * The fix is not to defer the subscription — it is not to change it at all.
   * One handler, subscribed once when the tool is armed, left in place for as
   * long as the tool is armed. What changes between one shape and the next is
   * the draft, and the draft is not the subscription.
   */
  _clearDrawing() {
    this.engine.clearDrafts()
    if (this._keyHandler) {
      window.removeEventListener('keydown', this._keyHandler)
      this._keyHandler = null
    }
    this._restoreCursor()
  }

  cleanup() {
    this._clearDrawing()
    if (this._unsubscribe) {
      this._unsubscribe()
      this._unsubscribe = null
    }
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

  _onClick({ latlng, overObject = null } = {}) {
    if (!latlng) return undefined
    const raw = [latlng.lat, latlng.lng]
    // The centres of the measured shapes on the map, read before the snap: a
    // click that lands on one of them is asking to use its centre.
    this._objectCentres = this._collectCentres()
    const point = this._snapToCentre(raw)
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
        // Two ways to size a circle, and the operator chooses.
        //
        // `cursorSizing` (the default) is the original interaction: the first
        // click places the centre, the second one is the decision to keep the
        // circle, and its radius is the distance from the centre to where they
        // clicked. Point at what you want covered.
        //
        // `typed` is the other one: the radius in the options panel is the
        // radius, and one click places the whole circle. Write 5 NM, press the
        // map, get 5 NM.
        //
        // They were conflated before this, which is the bug the operator
        // reported: they typed 5 NM, clicked, and the stored radius was the
        // distance between the two clicks — 2.987 NM in the reproduction — with
        // the typed number discarded. Worse, the *second* click also snapped to
        // the centre of a nearby shape, so the radius came out of a position
        // the operator never aimed at.
        if (this.options.useTyped) {
          this._startCircle(point)
          return this.commitCircle({ keepTool: true })
        }
        // The first click places the centre; the second one is the decision
        // to keep the circle, sized to where the operator clicked. Sizing is
        // measured from that click before committing, so the stored radius is
        // the one the pointer was showing, not a stale value from the last
        // mousemove.
        if (this.draft?.center) {
          // Deliberately *not* snapped: the centre was already placed, and
          // snapping the sizing click moved it onto another shape and changed
          // the radius behind the operator's back.
          this._updateCircle(raw)
          return this.commitCircle()
        }
        return this._startCircle(point)

      case TOOLS.RADIAL:
        if (this.options.useTyped) {
          this._startRadial(point)
          return this.commitRadial({ keepTool: true })
        }
        if (this.draft?.origin) {
          // Same reasoning as the circle: this click is azimuth and length, so
          // it is taken where it landed.
          this._updateRadial(raw)
          return this.commitRadial()
        }
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
      // A dashed path, per-vertex handles, and a live readout.
      this.engine.setDraft(
        'measure',
        L.polyline(points, { color: '#facc15', weight: 2, dashArray: '5,5' }),
      )
      this._renderVertices(points, '#facc15')
      this._renderLiveDistance(points)
      this._emitPreview({ type: 'measure', points: [...points] })
      return
    }

    this.engine.setDraft(
      'line',
      L.polyline(points, { color: '#22d3ee', weight: 3, dashArray: '6,4' }),
    )
    this._renderVertices(points)
  }

  /**
   * The live distance for the MEASURE tool, as a small box on the map.
   *
   * The tool already drew the dashed path and the vertex handles, and already
   * created the measurement object when finished — but it never showed a number
   * while the operator was still moving. Measured in the browser: arming MEDIR,
   * clicking two points and reading the screen gave **no labels at all**, only
   * the "Creado: Medición" notice afterwards. The number only ever existed after
   * the fact, which is the one moment it is not wanted.
   *
   * `MeasureEngine` has its own midpoint labels, but this tool is drawn by
   * `ToolManager`/`draw.js`, not by `MeasureEngine` — which is why those labels
   * never ran. So the readout lives here, next to the path it describes.
   *
   * The last point of `points` is the pointer, not a committed vertex, so the
   * segment being reported is the one the pointer is currently extending. It is
   * placed at that segment's midpoint rather than under the pointer, so the box
   * does not sit on top of the crosshair the operator is aiming with.
   */
_renderLiveDistance(points) {
    const key = 'measure-live'
    this.engine.clearDraft(key)
    if (points.length < 2) return

    const [aLat, aLon] = points[points.length - 2]
    const [bLat, bLon] = points[points.length - 1]
    const distanceM = haversine(aLat, aLon, bLat, bLon)
    if (!Number.isFinite(distanceM)) return

    const total = points.length > 2 ? this._pathLength(points.slice(0, -1)) : 0
    const text =
      total > 0
        ? `${formatDistance(distanceM)} · total ${formatDistance(total + distanceM)}`
        : formatDistance(distanceM)

    this.engine.setDraft(
      key,
      L.marker([(aLat + bLat) / 2, (aLon + bLon) / 2], {
        interactive: false,
        keyboard: false,
        icon: L.divIcon({
          className: 'aerorf-measure-live',
          html: `<span>${text}</span>`,
          iconSize: [0, 0],
        }),
      }),
    )
  }

  /** Great-circle length of a path already in `[lat, lon]` pairs. */
  _pathLength(points) {
    let total = 0
    for (let i = 1; i < points.length; i++) {
      total += haversine(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1])
    }
    return total
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
    // Remember where the pointer is: the sizing line is drawn from the centre
    // to here, so without it the live readout has nothing to point at.
    this._pointer = point
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
    this._renderEdge(this.draft.radius, this.draft.unit, '#3b82f6')
    this._emitPreview({ type: 'circle', ...this.draft })
  }

  /**
   * A line from the centre to the pointer, labelled with the live distance.
   *
   * Without this the operator extends the pointer and gets no number: the
   * tooltip on the ring only appears on hover, and a ring cannot be hovered
   * while you are still dragging it. Sizing a circle is exactly the case
   * where a live readout is not a nicety.
   */
  _renderEdge(radius, unit, color) {
    const { center } = this.draft
    const metres = typeof radius === 'number' && unit ? toMetres(radius, unit) : radius
    if (!metres || !this._pointer) {
      this.engine.removeDraft('edge')
      return
    }
    // Leaflet has no `L.line`: a two-point segment is a polyline.
    const line = L.polyline([center, this._pointer], {
      color,
      weight: 1.5,
      dashArray: '4,4',
      interactive: false,
    })
    line.bindTooltip(formatRadius(radius, unit), {
      permanent: true,
      direction: 'top',
      className: 'aerorf-draft-label',
    })
    this.engine.setDraft('edge', L.layerGroup([line]))
  }

  /**
   * Centres of the measured shapes on the map, keyed by object id, as
   * `[lat, lng]` pairs.
   *
   * Read from the engine's own layers, which already know where every centre
   * is, rather than from a second copy of the data. A duplicate list would be
   * one more thing to keep in step.
   *
   * The pair is built here rather than read straight off the layer because
   * `centreLatLng` is whatever the API sent in `latlng`, and that is a
   * `{lat, lng}` object, not an array. The snapping code read it as
   * `centre[0]` and `centre[1]`, which on an object is `undefined`: the
   * distance came out `NaN`, `NaN <= tolerance` is false, and **no placement
   * ever snapped to anything**. The feature had been inert since it was added
   * in 0.27.0. It looked fine because the tests that cover it build their
   * fixture with an array `latlng`, and an array does have indices.
   *
   * Both shapes are accepted, so a caller that hands over a real `L.LatLng`
   * works too.
   */
  _collectCentres() {
    const out = new Map()
    this.engine.featureLayers?.forEach?.((layer, id) => {
      const c = layer?.centreLatLng
      if (!c) return
      const lat = Array.isArray(c) ? c[0] : c.lat
      const lng = Array.isArray(c) ? c[1] : c.lng
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return
      out.set(String(id), [lat, lng])
    })
    return out
  }

  /**
   * Pull a click onto the centre of a measured shape.
   *
   * Putting a radial at the centre of a circle expresses a relationship
   * between the two objects, and a few pixels of hand tremor is not part of
   * that relationship. The stored radial would be centred on the operator's
   * hand rather than on the object it is measured from, and the two would
   * disagree by an amount nobody can see.
   *
   * The tolerance is in screen pixels, converted to metres at the current
   * latitude. A fixed number of metres would be out of reach when zoomed out
   * and unavoidable when zoomed in.
   */
  _snapToCentre(point) {
    if (!this._objectCentres?.size) return point
    const toleranceM = this._snapTolerance()
    if (!Number.isFinite(toleranceM) || toleranceM <= 0) return point

    let best = null
    let bestD = toleranceM
    this._objectCentres.forEach((centre) => {
      const d = haversine(point[0], point[1], centre[0], centre[1])
      if (d <= bestD) {
        bestD = d
        best = centre
      }
    })
    if (best) this._snappedTo = best
    else this._snappedTo = null
    return best || point
  }

  /** The snap tolerance in metres, from the engine's own projection. */
  _snapTolerance() {
    const mpp = this.engine.metresPerPixel?.()
    if (Number.isFinite(mpp) && mpp > 0) return mpp * SNAP_PIXELS
    // No engine yet: fall back to the formula, at the equator, which is the
    // conservative case since the tolerance is smallest there.
    return snapToleranceM(0, SNAP_METRES_PER_PIXEL_FALLBACK)
  }

  /** Confirm the current circle. */
  commitCircle({ keepTool = false } = {}) {
    if (this.active !== TOOLS.CIRCLE || !this.draft?.center) return null
    const { center, radiusM } = this.draft
    const result = this._emitComplete(
      {
        type: 'circle',
        latitude: center[0],
        longitude: center[1],
        radius: round(this.draft.radius, 3),
        radius_unit: this.draft.unit,
        radius_m: radiusM,
      },
      { keepTool },
    )
    // The object is stored; drop the sizing aids so the map is left clean.
    this.engine.removeDraft('edge')
    this._pointer = null
    return result
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

  /**
   * The reference line the degrees are measured from: due north.
   *
   * An azimuth means nothing on its own. 045° is a number until the operator
   * can see what it is measured from, so the radial is drawn over its
   * reference: a dashed line from the origin towards north, with the true
   * bearing between the two shown at the origin. Sweeping the pointer and
   * watching the gap close is what makes the reading legible.
   */
  _renderRadialReference() {
    const { origin, lengthM } = this.draft
    // The reference is as long as the radial itself, so the angle it makes is
    // the angle on screen. A fixed-length reference would distort the reading
    // when the radial is short.
    const reach = Math.max(lengthM, 1000)
    const north = radialPoints(origin, 0, reach, 2)

    const reference = L.polyline(north, {
      color: '#64748b',
      weight: 1,
      opacity: 0.7,
      dashArray: '1,5',
      interactive: false,
    })
    reference.bindTooltip('Referencia 000° (norte)', {
      permanent: true,
      direction: 'right',
      className: 'aerorf-draft-label aerorf-draft-label--muted',
    })

    // The arc between the reference and the radial, at the origin.
    const arc = L.polyline(
      arcPoints(origin, reach * 0.35, 0, this.draft.azimuth, 24),
      {
        color: '#a855f7',
        weight: 1.5,
        opacity: 0.8,
        interactive: false,
      },
    )
    arc.bindTooltip(`${this.draft.azimuth.toFixed(1)}°`, {
      permanent: true,
      direction: 'top',
      className: 'aerorf-draft-label',
    })

    this.engine.setDraft('radial-ref', L.layerGroup([reference, arc]))
  }

  /** Paint the current draft. Pure rendering: no measurement, no state change. */
  _renderRadial() {
    const { origin, azimuth, lengthM, length, unit } = this.draft
    this._renderRadialReference()
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
    // The degrees at the far end, permanently. The tooltip on the line needs a
    // hover; this one is always there, which is what lets the operator read the
    // value while sweeping without moving the pointer off the shape.
    this.engine.setDraft(
      'radial-end',
      L.circleMarker(radialPoints(origin, azimuth, lengthM, 1)[1], {
        radius: 3,
        color: '#a855f7',
        fillOpacity: 1,
        weight: 1,
        interactive: false,
      }).bindTooltip(
        `${azimuth.toFixed(1)}\xb0 ${compassPoint(azimuth)} \xb7 ${formatRadius(length, unit)}`,
        { permanent: true, direction: 'right', className: 'aerorf-draft-label' },
      ),
    )
    this._emitPreview({ type: 'radial', ...this.draft })
  }

  commitRadial({ keepTool = false } = {}) {
    if (this.active !== TOOLS.RADIAL || !this.draft?.origin) return null
    const { origin, azimuth, lengthM } = this.draft
    return this._emitComplete(
      {
        type: 'radial',
        latitude: origin[0],
        longitude: origin[1],
        azimuth: round(azimuth, 2),
        length_value: round(this.draft.length, 3),
        length_unit: this.draft.unit,
        length_m: lengthM,
      },
      { keepTool },
    )
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

  /**
   * Hand the finished shape to the shell.
   *
   * `keepTool` leaves the tool armed. It is what the typed-radius mode needs:
   * an operator placing a 5 NM circle around four sites wants four circles of
   * 5 NM, and having to re-pick the tool and retype the number after each one
   * is what made the panel look like it had vanished — the fields disappear
   * with the tool.
   *
   * The click subscription is deliberately left alone here. See
   * `_clearDrawing()`: re-subscribing from inside the handler deadlocks the
   * engine's own event walk.
   */
  _emitComplete(payload, { keepTool = false } = {}) {
    this._clearDrawing()
    this.draft = null
    if (keepTool) {
      this._pointer = null
      this._renderGhost()
    } else {
      this._unsubscribe?.()
      this._unsubscribe = null
      this.active = null
    }
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
