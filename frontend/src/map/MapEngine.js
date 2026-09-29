/**
 * map/MapEngine.js
 * ───────────────
 * The cartographic engine, deliberately independent of any Vue component.
 *
 * Responsibilities (spec §4): Leaflet initialisation, OpenStreetMap
 * basemap, zoom, pan, click events, cursor coordinates, object selection,
 * layers, geometries, popups, measurement and drawing hooks.
 *
 * Why a class rather than a composable: the map has real state (panes,
 * layer registries, click handlers, a draw session). Putting that in a
 * reactive object would make Leaflet's own mutations trigger Vue updates
 * at frame rate. The engine is a plain imperative object; Vue learns about
 * changes through explicit callbacks.
 *
 * Nothing here knows about Pinia, routers or components.
 */

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

import { haversine, radialPoints, toMetres } from './geo'

/** Buenos Aires / EZE — the initial view. */
export const DEFAULT_CENTER = [-34.603722, -58.381592]
export const DEFAULT_ZOOM = 10

const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'

/**
 * A small dot at the origin of a measured shape.
 *
 * A circle is a ring and a radial is a line, and neither says where it starts.
 * Without the dot the operator cannot tell what a radial's bearing is measured
 * from, or place a second object at the centre of a circle — the two things
 * they are most likely to want to do next.
 *
 * Not interactive: the shape around it is what gets clicked, and a dot that
 * swallowed clicks would make the centre unusable rather than reachable.
 */
function centreDot(latlng, color) {
  return L.circleMarker(latlng, {
    radius: 4,
    color: '#0f172a',
    weight: 1.5,
    fillColor: color,
    fillOpacity: 1,
    interactive: false,
    pane: 'markerPane',
  })
}

export class MapEngine {
  /**
   * @param {object}  options
   * @param {string|HTMLElement} options.container  target element or its id
   * @param {Array}   [options.center]                [lat, lon]
   * @param {number}  [options.zoom]
   */
  constructor(options = {}) {
    this.options = {
      container: options.container ?? null,
      // The container has to be carried here, not read from `options`
      // later: `init()` resolves it through `this.options.container`, and
      // building this object from scratch would silently drop it, leaving
      // init() to fail on `undefined` no matter what the caller passed.
      center: options.center || DEFAULT_CENTER,
      zoom: options.zoom ?? DEFAULT_ZOOM,
      minZoom: options.minZoom ?? 2,
      maxZoom: options.maxZoom ?? 19,
    }

    this.map = null
    this.container = null

    /** @type {Map<string, L.Layer>} objectKey -> Leaflet layer */
    this.featureLayers = new Map()
    /** @type {Map<string, L.Layer>} layerKey -> Leaflet pane/layer group */
    this.categoryLayers = new Map()
    /** @type {Map<string, {onSelect: Function, layer: L.Layer}>} */
    this.selectionHandlers = new Map()

    /** Event callbacks, kept separate from Leaflet's own events. */
    this._listeners = new Map()
    /** Temporary layers for previews and in-progress drawings. */
    this._draftLayers = new Map()
    this._destroyed = false
  }

  // ─── Lifecycle ────────────────────────────────────────────────────────────

  /** Create the Leaflet instance. Idempotent. */
  init() {
    if (this.map) return this.map

    const target =
      typeof this.options.container === 'string'
        ? document.getElementById(this.options.container)
        : this.options.container

    if (!target) {
      throw new Error(
        `MapEngine: no se encontró el contenedor «${this.options.container}»`,
      )
    }
    this.container = target

    this.map = L.map(target, {
      center: this.options.center,
      zoom: this.options.zoom,
      minZoom: this.options.minZoom,
      maxZoom: this.options.maxZoom,
      zoomControl: false,
      attributionControl: true,
      preferCanvas: true, // hundreds of vector layers stay smooth
      worldCopyJump: true,
    })

    this._addBasemap()
    this._addControls()
    this._bindEvents()

    return this.map
  }

  _addBasemap() {
    this.basemap = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: OSM_ATTRIBUTION,
      maxZoom: 19,
      crossOrigin: true,
    })
    this.basemap.addTo(this.map)

    // A second, low-contrast layer for context toggled from the UI.
    this.basemapRelief = L.tileLayer(
      'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
      { attribution: OSM_ATTRIBUTION, maxZoom: 17, opacity: 0.45 },
    )
  }

  _addControls() {
    L.control.zoom({ position: 'topright' }).addTo(this.map)
    L.control.scale({ position: 'bottomright', imperial: false, metric: true }).addTo(this.map)
  }

  _bindEvents() {
    const { map } = this

    // Cursor position is published on every move (spec §5).
    map.on('mousemove', (e) => this._emit('cursor', e.latlng))
    map.on('mouseout', () => this._emit('cursor', null))

    // A click is only published when no drawing tool is consuming it.
    map.on('click', (e) => {
      if (this._clickSuppressed) return
      this._emit('click', { latlng: e.latlng, originalEvent: e.originalEvent })
    })

    map.on('contextmenu', (e) => {
      L.DomEvent.preventDefault(e.originalEvent)
      this._emit('contextmenu', {
        latlng: e.latlng,
        containerPoint: e.containerPoint,
        originalEvent: e.originalEvent,
      })
    })

    map.on('zoomend', () => this._emit('zoom', this.map.getZoom()))
    map.on('moveend', () => this._emit('move', this.map.getCenter()))
  }

  /** Remove the instance and release every listener. */
  destroy() {
    this._destroyed = true
    this.clearDrafts()
    this.featureLayers.forEach((layer) => layer.remove())
    this.featureLayers.clear()
    this.categoryLayers.forEach((layer) => layer.remove())
    this.categoryLayers.clear()
    if (this.map) {
      this.map.off()
      this.map.remove()
      this.map = null
    }
  }

  /** Leaflet mis-measures when the container's size changes. */
  invalidateSize(delay = 80) {
    if (this._destroyed) return
    setTimeout(() => this.map?.invalidateSize({ pan: false }), delay)
  }

  // ─── Events ───────────────────────────────────────────────────────────────

  /** Subscribe. Returns an unsubscribe function. */
  on(event, handler) {
    if (!this._listeners.has(event)) this._listeners.set(event, new Set())
    this._listeners.get(event).add(handler)
    return () => this.off(event, handler)
  }

  off(event, handler) {
    this._listeners.get(event)?.delete(handler)
  }

  _emit(event, payload) {
    this._listeners.get(event)?.forEach((handler) => {
      try {
        handler(payload)
      } catch (err) {
        // A broken listener must not stop the others or the map.
        console.error(`[MapEngine] error en el listener de «${event}»`, err)
      }
    })
  }

  // ─── Viewport ─────────────────────────────────────────────────────────────

  getCenter() {
    return this.map ? this.map.getCenter() : null
  }

  getZoom() {
    return this.map ? this.map.getZoom() : null
  }

  /**
   * Ground metres per screen pixel at the current view.
   *
   * Taken from Leaflet's own `CRS.EPSG3857`, which is the projection the map is
   * actually drawn in. An earlier version re-derived it by projecting the
   * centre at two zoom levels and measuring the gap, and got a value roughly
   * five times too small — which made the snap tolerance ten times too tight,
   * so a click two metres from a circle's centre did not snap and the whole
   * feature silently did nothing.
   *
   * Asking the projection is also the only way to be sure the two agree.
   */
  metresPerPixel() {
    if (!this.map) return null
    const size = this.map.getSize()
    if (!size?.y) return null
    // Measured off the map's own projection: one screen height, converted
    // back to a position and then to a ground distance.
    //
    // The two shortcuts through Leaflet's CRS were both wrong. There is no
    // `crs.groundResolution` in this version, and `crs.scale` is the
    // projection's scale factor with no zoom in it — the same number at every
    // level, which made the snap tolerance wrong by a factor of the zoom and
    // the feature silently inert.
    const centre = this.map.getCenter()
    const point = this.map.latLngToContainerPoint(centre)
    const south = this.map.containerPointToLatLng([point.x, point.y + size.y])
    return haversine(centre.lat, centre.lng, south.lat, south.lng) / size.y
  }

  setView(lat, lon, zoom = this.getZoom()) {
    this.map?.setView([lat, lon], zoom)
  }

  fitBounds(latlngs, padding = [60, 60]) {
    const points = (latlngs || [])
      .map((p) => (Array.isArray(p) ? p : [p.lat, p.lon ?? p.lng]))
      .filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]))
    if (!points.length) return
    this.map?.fitBounds(L.latLngBounds(points), { padding })
  }

  fitObject(object) {
    if (!object) return
    if (object.latlngs?.length > 1) this.fitBounds(object.latlngs)
    else if (object.latlng) this.setView(object.latlng[0], object.latlng[1])
  }

  getBounds() {
    if (!this.map) return null
    const b = this.map.getBounds()
    return {
      south: b.getSouth(),
      west: b.getWest(),
      north: b.getNorth(),
      east: b.getEast(),
    }
  }

  // ─── Category layers (spec §38) ───────────────────────────────────────────

  /**
   * Ensure a named Leaflet layer group exists and is on the map.
   * @returns {L.LayerGroup}
   */
  ensureCategory(key, { visible = true, opacity = 1, order = null } = {}) {
    if (this.categoryLayers.has(key)) {
      const existing = this.categoryLayers.get(key)
      if (visible && !this.map.hasLayer(existing)) existing.addTo(this.map)
      return existing
    }

    const group = L.layerGroup()
    if (visible) group.addTo(this.map)
    this.categoryLayers.set(key, group)
    if (order !== null) this.setCategoryOrder(key, order)
    return group
  }

  setCategoryVisible(key, visible) {
    const group = this.categoryLayers.get(key)
    if (!group) return
    if (visible) group.addTo(this.map)
    else this.map.removeLayer(group)
  }

  setCategoryOpacity(key, opacity) {
    const group = this.categoryLayers.get(key)
    if (!group) return
    const clamped = Math.max(0, Math.min(1, opacity))
    group.eachLayer((layer) => {
      if (layer.setStyle) layer.setStyle({ opacity: clamped, fillOpacity: clamped * 0.3 })
      if (layer.setOpacity) layer.setOpacity(clamped)
    })
  }

  /** Place a category group above/below another. */
  setCategoryOrder(key, aboveKey) {
    const group = this.categoryLayers.get(key)
    const reference = this.categoryLayers.get(aboveKey)
    if (!group || !reference || !this.map.hasLayer(group)) return
    if (aboveKey in this.categoryLayers) {
      // Leaflet has no "insert after", so toggle both panes.
      const target = reference.getPane()
      if (target) {
        const markerPane = this.map.getPane('markerPane')
        markerPane?.appendChild(target)
      }
    }
  }

  // ─── Object rendering ─────────────────────────────────────────────────────

  /**
   * Render (or re-render) one map object.
   * @param {object} object   Leaflet-shaped payload from the API
   * @param {object} [style]  {color, icon, weight, opacity, fillOpacity, dashed}
   * @returns {L.Layer|null}
   */
  renderObject(object, style = {}) {
    if (!object || object.id === undefined || object.id === null) return null
    this.removeObject(object.id)

    const layer = this._buildLayer(object, style)
    if (!layer) return null

    layer.featureId = object.id
    layer.objectType = object.type
    layer.objectData = object

    if (object.visible === false) return layer // built, not added

    const host = this.ensureCategory(object.layer || 'user')
    layer.addTo(host)
    this.featureLayers.set(String(object.id), layer)

    if (object.show_label !== false && object.name) this._addTooltip(layer, object)
    return layer
  }

  _buildLayer(object, style) {
    const color = style.color || object.color || '#38bdf8'
    const weight = style.weight ?? object.weight ?? 3
    const opacity = style.opacity ?? object.opacity ?? 1
    const fillOpacity = style.fillOpacity ?? object.fill_opacity ?? 0.15

    const base = {
      color,
      weight,
      opacity,
      fillOpacity,
      ...(style.dashed ? { dashArray: style.dashArray || '6,6' } : {}),
    }

    // A circle and a radial are stored as a centre plus a measurement: the
    // radius in metres, or the azimuth and length. Their `geometry_type` is
    // `Point`, because that is what the centre is — and dispatching on
    // `geometry_type` alone drew a dot for both. The saved values were right
    // and the panel showed them, but the shape itself was never on the map.
    //
    // So the type is checked first. A stored ring would be correct but is not
    // what gets written, and a circle drawn from 72 polygon vertices would be
    // visibly wrong at low zoom.
    const shape = this._buildMeasured(object, base)
    if (shape) return shape

    switch (object.geometry_type) {
      case 'Point':
        return L.circleMarker(object.latlng, { ...base, radius: style.radius || 8 })

      case 'LineString':
        return L.polyline(object.latlngs, base)

      case 'Polygon':
        if (object.type === 'coverage') {
          // A true circle: exact at every zoom level.
          const radiusM = this._radiusMetres(object, style)
          if (radiusM) {
            const circle = L.circle(object.latlng, {
              radius: radiusM,
              color,
              weight,
              opacity,
              fillOpacity,
            })
            circle.radiusM = radiusM
            return circle
          }
        }
        return L.polygon(object.latlngs, base)

      default:
        return null
    }
  }

  /**
   * The drawn form of a shape stored as a centre plus a measurement.
   *
   * Returns null for anything else, so the caller falls through to the
   * geometry-based drawing.
   */
  _buildMeasured(object, base) {
    const latlng = object.latlng
    if (!latlng) return null

    if (object.type === 'circle' || object.type === 'reference') {
      // A reference point may carry a coverage ring rather than a radius; it
      // is only drawn as a circle when it has one.
      const radiusM = this._radiusMetres(object)
      if (!radiusM) return null
      const { color, weight, opacity, fillOpacity } = base
      const circle = L.layerGroup([
        L.circle(latlng, { radius: radiusM, color, weight, opacity, fillOpacity }),
        centreDot(latlng, color),
      ])
      circle.radiusM = radiusM
      // The origin, published for the drawing tool's snapping: a click near
      // this point is pulled onto it, so a radial placed at the centre of a
      // circle is stored at the circle's centre rather than at the hand.
      circle.centreLatLng = latlng
      return circle
    }

    if (object.type === 'radial') {
      const lengthM = this._lengthMetres(object)
      const azimuth = this._azimuthOf(object)
      if (!lengthM || azimuth === null) return null
      const { color, weight, opacity } = base
      // Straight from the centre outward. A radial is a bearing and a
      // distance, not a curve: drawing it as an arc would be a different
      // object from the one stored.
      const line = L.layerGroup([
        L.polyline(radialPoints(latlng, azimuth, lengthM, 24), {
          color,
          weight,
          opacity,
          // Solid, to match the committed drawing. The live preview is dashed to
          // read as provisional; once stored it is an object like any other.
        }),
        centreDot(latlng, color),
      ])
      line.azimuth = azimuth
      line.lengthM = lengthM
      // Same reason as the circle: a second radial from the same origin should
      // share it exactly.
      line.centreLatLng = latlng
      return line
    }

    return null
  }

  /**
   * A circle's radius in metres.
   *
   * `radius_m` is preferred because it is unambiguous, but it is not always
   * present on a read-back row, and the stored value is in the object's own
   * unit — 5 NM and 5 km are not the same circle. Falling back to a raw
   * `radius` without its unit would draw one of them at the wrong size.
   */
  _radiusMetres(object, style) {
    const direct = object.radius_m ?? object.metrics?.radius_m ?? style?.radiusM
    if (Number.isFinite(direct) && direct > 0) return Number(direct)

    const value = object.radius ?? object.properties?.circle?.radius
    const unit = object.radius_unit || object.properties?.circle?.radius_unit || 'nm'
    if (Number.isFinite(Number(value)) && Number(value) > 0) {
      return toMetres(Number(value), unit)
    }
    return null
  }

  /**
   * A radial's azimuth in degrees, normalised to [0, 360).
   *
   * A stored value can land just outside the range after rounding — 360.0, or
   * a small negative from a wrap — and a bearing outside it produces a line in
   * a direction the operator did not ask for. Normalised on read rather than on
   * write, because rows already in the database carry both.
   */
  _azimuthOf(object) {
    const value = Number(object.azimuth ?? object.properties?.radial?.azimuth)
    if (!Number.isFinite(value)) return null
    return ((value % 360) + 360) % 360
  }

  /** A radial's length in metres, for the same reason. */
  _lengthMetres(object) {
    const direct = object.length_m ?? object.metrics?.length_m
    if (Number.isFinite(direct) && direct > 0) return Number(direct)

    const value = object.length_value ?? object.length ?? object.properties?.radial?.length
    const unit = object.length_unit || object.properties?.radial?.length_unit || 'nm'
    if (Number.isFinite(Number(value)) && Number(value) > 0) {
      return toMetres(Number(value), unit)
    }
    return null
  }

  _addTooltip(layer, object) {
    const text = this.objectTooltip(object)
    if (text) layer.bindTooltip(text, { sticky: true, direction: 'top' })
  }

  /** Short label shown on hover. */
  objectTooltip(object) {
    const name = object.name || object.label
    if (!name) return null
    const bits = [`<strong>${escapeHtml(name)}</strong>`]
    if (object.type === 'rf_source' || object.type === 'antenna' || object.type === 'rf_event') {
      const freq = object.properties?.rf?.frequency_mhz ?? object.properties?.antenna?.frequency_mhz
      if (freq) bits.push(`${freq} MHz`)
    }
    if (object.metrics?.radius_nm != null) {
      bits.push(`${object.metrics.radius_nm.toFixed(2)} NM / ${object.metrics.radius_km.toFixed(2)} km`)
    }
    if (object.status) bits.push(object.status)
    return bits.join('<br/>')
  }

  /** Rich popup body (spec §39). */
  objectPopup(object) {
    const p = object.properties || {}
    const rows = []
    const row = (k, v) => {
      if (v === null || v === undefined || v === '') return
      rows.push(
        `<div class="aerorf-popup-row"><span>${escapeHtml(k)}</span><b>${escapeHtml(String(v))}</b></div>`,
      )
    }

    row('ID', object.id)
    row('Tipo', typeLabel(object.type))
    row('Nombre', object.name)
    row('Estado', object.status)
    row('Categoría', object.category)

    if (object.latitude != null) {
      row('Latitud', Number(object.latitude).toFixed(6))
      row('Longitud', Number(object.longitude).toFixed(6))
    }

    if (p.rf) {
      row('Frecuencia', p.rf.frequency_mhz ? `${p.rf.frequency_mhz} MHz` : null)
      row('Nivel', p.rf.power_dbm != null ? `${p.rf.power_dbm} dBm` : null)
      row('Tipo de señal', p.rf.kind)
      row('Altura', p.rf.height_m ? `${p.rf.height_m} m` : null)
    }
    if (p.antenna) {
      row('Frecuencia', p.antenna.frequency_mhz ? `${p.antenna.frequency_mhz} MHz` : null)
      row('Ganancia', p.antenna.gain_dbi != null ? `${p.antenna.gain_dbi} dBi` : null)
      row('Altura', p.antenna.height_m ? `${p.antenna.height_m} m` : null)
      row('Azimut', p.antenna.azimuth_deg != null ? `${p.antenna.azimuth_deg}°` : null)
      row('Sector', p.antenna.sector_deg ? `${p.antenna.sector_deg}°` : null)
      row('Polarización', p.antenna.polarization)
    }
    if (p.reference) {
      row('Código', p.reference.code)
      row('Radio', p.reference.radius != null
        ? `${p.reference.radius} ${p.reference.radius_unit}`
        : null)
    }

    if (object.metrics?.radius_nm != null) {
      row('Radio', `${object.metrics.radius_nm.toFixed(3)} NM`)
      row('Equivalente', `${object.metrics.radius_km.toFixed(3)} km`)
    }
    if (object.radial) {
      row('Azimut', `${object.radial.azimuth.toFixed(1)}°`)
      row('Longitud', `${object.radial.length_nm.toFixed(2)} NM / ${object.radial.length_km.toFixed(2)} km`)
    }
    if (object.metrics?.total_length_nm != null) {
      row('Longitud', `${object.metrics.total_length_nm.toFixed(3)} NM`)
      row('Equivalente', `${object.metrics.total_length_km.toFixed(3)} km`)
    }

    if (p.expediente) row('Expediente', p.expediente)
    row('Capa', p.layer_name || p.layer)
    row('Procedencia', provenanceLabel(object.provenance))
    row('Creado', p.created_at ? formatDate(p.created_at) : null)
    row('Modificado', p.updated_at ? formatDate(p.updated_at) : null)

    return `
      <div class="aerorf-popup">
        <div class="aerorf-popup-title">${escapeHtml(object.name || typeLabel(object.type))}</div>
        ${object.description ? `<div class="aerorf-popup-desc">${escapeHtml(object.description)}</div>` : ''}
        <div class="aerorf-popup-rows">${rows.join('')}</div>
        <div class="aerorf-popup-hint">Doble clic para abrir en el Inspector</div>
      </div>`
  }

  /** Attach a click handler that reports the object id. */
  onObjectClick(objectId, handler) {
    const key = String(objectId)
    this.selectionHandlers.get(key)?.handler?.(null)
    this.selectionHandlers.set(key, { handler, layer: null })
    this._applySelectionHandler(objectId, handler)
  }

  _applySelectionHandler(objectId, handler) {
    const key = String(objectId)
    const layer = this.featureLayers.get(key)
    const entry = this.selectionHandlers.get(key)
    if (!layer || !entry) return
    if (entry.bound) return
    layer.on('click', (e) => {
      L.DomEvent.stopPropagation(e)
      handler(objectId, e)
      // A click on an existing object also counts as a click on the map, when a
      // drawing tool is armed.
      //
      // It used to be swallowed outright: `stopPropagation` above stops the
      // event before it reaches the map, so the tool never saw it. An operator
      // with the radial tool picked, clicking the middle of a circle to start a
      // radial from its centre, got the circle selected instead and the tool
      // did nothing — with no way to see why, since the tool is visibly armed.
      //
      // So the position is forwarded explicitly. `stopPropagation` stays for
      // the select tool, where selecting the object under the pointer is the
      // whole point and the map's own handler would clear the selection.
      if (this._clickSuppressed) {
        this._emit('click', { latlng: e.latlng, overObject: objectId })
      }
    })
    layer.on('dblclick', (e) => {
      L.DomEvent.stopPropagation(e)
      this._emit('objectdblclick', { id: objectId, latlng: e.latlng })
    })
    layer.on('mouseover', () => this._emit('objecthover', { id: objectId }))
    layer.on('mouseout', () => this._emit('objecthover', { id: null }))
    entry.bound = true
  }

  /** Remove an object from the map (does not touch the database). */
  removeObject(objectId) {
    const key = String(objectId)
    const layer = this.featureLayers.get(key)
    if (!layer) return
    layer.remove()
    this.featureLayers.delete(key)
    this.selectionHandlers.delete(key)
  }

  clearObjects() {
    this.featureLayers.forEach((layer) => layer.remove())
    this.featureLayers.clear()
    this.selectionHandlers.clear()
  }

  hasObject(objectId) {
    return this.featureLayers.has(String(objectId))
  }

  /** Visually emphasise the selected object. */
  highlight(objectId, color = '#facc15') {
    this.featureLayers.forEach((layer, key) => {
      if (layer.setStyle) layer.setStyle({ weight: layer.options.weight || 3 })
    })
    const layer = this.featureLayers.get(String(objectId))
    if (layer?.setStyle) {
      const base = layer.options.weight || 3
      layer.setStyle({ color, weight: base + 3, fillOpacity: 0.35 })
      layer.bringToFront?.()
    }
  }

  clearHighlight() {
    this.featureLayers.forEach((layer) => {
      if (layer.setStyle) {
        const o = layer.options
        layer.setStyle({ color: o.color, weight: o.weight, fillOpacity: o.fillOpacity })
      }
    })
  }

  // ─── Drafts: previews and in-progress drawings (spec §6) ──────────────────

  /** Show a temporary preview layer; re-calling replaces it. */
  setDraft(key, layer) {
    this.clearDraft(key)
    if (!layer) return null
    this._draftLayers.set(key, layer)
    layer.addTo(this.map)
    return layer
  }

  /**
   * Remove one draft layer by key.
   *
   * `clearDraft(key)` covers this, but an explicit remove reads better at
   * call sites that mean "this measurement is over" rather than "reset the
   * preview", and it keeps the two from drifting apart if one gains options.
   */
  removeDraft(key) {
    this.clearDraft(key)
  }

  clearDraft(key) {
    const layer = this._draftLayers.get(key)
    if (layer) {
      layer.remove()
      this._draftLayers.delete(key)
    }
  }

  clearDrafts() {
    this._draftLayers.forEach((layer) => layer.remove())
    this._draftLayers.clear()
  }

  // ─── Click suppression (used while a drawing tool is active) ─────────────

  suppressClicks(value = true) {
    this._clickSuppressed = value
  }

  // ─── Basemap switching ────────────────────────────────────────────────────

  setBasemap(kind) {
    if (!this.map) return
    if (this.basemapRelief && this.map.hasLayer(this.basemapRelief)) {
      this.map.removeLayer(this.basemapRelief)
    }
    if (kind === 'relief') {
      this.basemapRelief.addTo(this.map)
      if (this.map.hasLayer(this.basemap)) this.map.removeLayer(this.basemap)
    } else {
      this.basemap.addTo(this.map)
    }
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const TYPE_LABELS = {
  point: 'Punto',
  line: 'Línea',
  polygon: 'Polígono',
  circle: 'Círculo',
  radial: 'Radial',
  trace: 'Traza',
  measurement: 'Medición',
  annotation: 'Anotación',
  rf_source: 'Fuente interferente',
  antenna: 'Antena',
  reference: 'Referencia',
  rf_event: 'Evento RF',
  enacom_station: 'Estación ENACOM',
  airport: 'Aeropuerto',
  coverage: 'Cobertura',
  other: 'Otro',
}

const PROVENANCE_LABELS = {
  observed: 'Dato observado',
  historical: 'Dato histórico',
  live: 'Dato en vivo',
  calculated: 'Dato calculado',
  user: 'Introducido por el usuario',
}

export function typeLabel(type) {
  return TYPE_LABELS[type] || type || '—'
}

export function provenanceLabel(value) {
  return PROVENANCE_LABELS[value] || value || '—'
}

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString('es-AR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

export default MapEngine
