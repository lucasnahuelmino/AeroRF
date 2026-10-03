/**
 * map/MapEngine.js
 * ───────────────
 * The cartographic engine, deliberately independent of any Vue component.
 *
 * Responsibilities (spec §4): Leaflet initialisation, OpenStreetMap
 * basemap, zoom, pan, click events, cursor coordinates, object selection,
 * layers, geometries, labels on hover, measurement and drawing hooks.
 *
 * No popups here: the objects' details live in the Inspector panel, and the
 * airport and aircraft popups belong to their own modules.
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
import { token } from '../assets/tokens'

/** Buenos Aires / EZE — the initial view. */
export const DEFAULT_CENTER = [-34.603722, -58.381592]
export const DEFAULT_ZOOM = 10

const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'

/**
 * Where a category sits in the canvas draw order, when the order the layers
 * arrived in is not the one that should be used.
 *
 * A circle's hit area is its whole disc and a radial's is its line, so the two
 * are not comparable targets: the disc is a 16 km area, the line is 3 pixels
 * wide. Drawing the circle above the radial means that wherever the two cross,
 * the click belongs to the circle and the radial cannot be picked up there —
 * the operator clicks the line they can see and get the area they did not aim
 * at. The rule every drawing tool applies is the opposite one: the broad target
 * goes underneath the precise one.
 *
 * Only the conflict is listed. The sort is stable, so every category that is
 * not named here keeps the order the API gave it, which already puts the
 * discrete objects — points, events, sources, antennas — above both measured
 * shapes.
 */
/**
 * Draw rank: lower is further from the viewer.
 *
 * **What the operator asked for, in order.** An aircraft has to be visible over
 * anything: it is the thing that moves, and it is what they are watching. Then
 * their own objects, in the order they created them, except that a measured
 * shape's broad target goes under its precise parts. Then the reference marks
 * nobody flies the map by.
 *
 * Measured in the browser, this is not a preference. The canvas is one draw list
 * ordered by `_leaflet_id`, and `aircraft_tracks` was created before any object
 * existed — the renderer is built when the shell mounts, long before the operator
 * draws. That put every trajectory *underneath* every filled shape:
 *
 *     aircraft_tracks (35) → radials (357) → circles (358) → traces (364) → ...
 *
 * So a coverage circle or a polygon was painted over the flight path. The fills
 * are 15% opaque by default, which is why the path was dimmed rather than
 * vanished, and a raised category opacity hid it completely.
 *
 * The numbers are spacing, not indices. `Array.prototype.sort` on rank is stable,
 * so anything not named here keeps its arrival order inside its own rank, which
 * is the behaviour the comment above this block already claimed and did not have.
 */
const CATEGORY_DRAW_RANK = {
  // Reference marks: aerodromes, and anything else nobody is flying by.
  airports: -2,
  base_map: -3,
  // A circle's disc is a hit area the size of its radius, so it goes under.
  circles: -1,
  // The operator's own objects, in the order they were made.
  objects: 0,
  // The flight path and the aircraft. Above every object, always.
  aircraft_tracks: 10,
  aircraft: 11,
}

/** Draw rank of a category; anything unlisted sits at 0, in arrival order. */
function drawRank(key) {
  return CATEGORY_DRAW_RANK[key] ?? 0
}

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
  // No `pane: 'markerPane'`. That was the cause of nothing on the map being
  // selectable, and it was invisible to every test.
  //
  // This map renders with `preferCanvas`, so a vector layer in a non-overlay
  // pane gets its **own full-size canvas**, and Leaflet gives every canvas
  // `pointer-events: auto` by default. The markerPane sits above the
  // overlayPane (z-index 600 against 400), so that canvas covered the whole map,
  // in front of everything, and swallowed every click — including the ones
  // meant for the objects and the ones meant for the ground.
  //
  // Measured in the browser: with the canvas present, `elementFromPoint` over a
  // circle returned the markerPane canvas; with it hidden, the overlayPane
  // canvas. Nothing was ever selectable, and no amount of fixing the click
  // handlers could change that, because no click was arriving at any of them.
  //
  // The dot therefore shares the overlayPane with the shape it marks, which is
  // where it belongs: it is part of that object, not a floating marker.
  return L.circleMarker(latlng, {
    radius: 4,
    color: '#0f172a',
    weight: 1.5,
    fillColor: color,
    fillOpacity: 1,
    interactive: false,
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
    this._addTrackPane()

    return this.map
  }

  /**
   * The pane and renderer the flight paths are drawn on.
   *
   * **Why a pane at all, when `restack()` is supposed to order the categories.**
   * It isn't, and that is not a guess. The map is `preferCanvas`, so every
   * vector layer shares one canvas and one draw list, and that list is ordered by
   * `_leaflet_id` — assigned when a layer is *created*. Measured here: the
   * category group ids were identical before and after a `restack()`, because
   * removing and re-adding a layer does not renumber it. So `CATEGORY_DRAW_RANK`
   * can decide the order groups are re-added in, but it cannot move a trajectory
   * above a shape that was created after it.
   *
   * And that is exactly what happened. `aircraft_tracks` is created when the
   * renderer is built, long before the operator draws anything, so it sat at the
   * bottom of the shared canvas:
   *
   *     aircraft_tracks (35) → radials (357) → circles (358) → traces (364) → ...
   *
   * The operator's requirement is that the aircraft is visible over anything, and
   * a filled shape drawn over the flight path is the one thing that makes a
   * trajectory unreadable. Pane stacking *does* work, because each renderer
   * container is a DOM element and the browser stacks those by z-index. So the
   * paths get their own canvas, in a pane above `overlayPane`.
   *
   * **And it must not take clicks.** A vector layer outside the overlayPane gets
   * its own full-size canvas, and Leaflet gives every canvas `pointer-events:
   * auto`. That is what made nothing on the map selectable once: the extra canvas
   * covered the map in front of everything and swallowed every click, so no click
   * ever reached a handler to be fixed. The pane is therefore `pointer-events:
   * none` in `assets/styles.css`, and there is a guard test that fails if that
   * rule disappears — a canvas that is drawn on top and cannot be clicked is the
   * worst of both.
   *
   * Below `markerPane` on purpose: the aircraft icon belongs above its own path.
   */
  _addTrackPane() {
    const pane = this.map.createPane('aerorfTracksPane')
    pane.style.zIndex = 500
    pane.classList.add('aerorf-tracks-pane')
    // Kept as fields so a test can assert the pane's own z-index and name. The
    // z-index is the whole mechanism: panes stack by DOM order, not by any of
    // Leaflet's own ordering.
    this.trackPane = pane
    this.trackPaneName = 'aerorfTracksPane'
    this.trackRenderer = L.canvas({ pane: 'aerorfTracksPane' })
    return this.trackRenderer
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
    // Through `removeObject`, so the layers are detached from their category
    // groups too. Here it hardly matters — the groups are removed on the next
    // line — but going through the one removal path is what keeps a second
    // removal path from drifting away from the first.
    Array.from(this.featureLayers.keys()).forEach((key) => this.removeObject(key))
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
   *
   * There is no `order` option. The draw position of a category is decided by
   * `restack()`, from `CATEGORY_DRAW_RANK` and the order the layers arrived in.
   *
   * The option used to exist, and it took a `aboveKey` and reordered *panes* to
   * fake an insert-at-position. Nothing ever passed it, and it was the wrong
   * mechanism: this map is `preferCanvas`, so every category is painted on one
   * canvas and the pane order has nothing to say about what is drawn on top of
   * what. Worse, it moved the overlayPane element itself into the markerPane,
   * which is the same family of mistake as the centre dot's own pane — the
   * outage where an invisible full-map element swallowed every click.
   * @returns {L.LayerGroup}
   */
  ensureCategory(key, { visible = true, opacity = 1 } = {}) {
    if (this.categoryLayers.has(key)) {
      const existing = this.categoryLayers.get(key)
      if (visible && !this.map.hasLayer(existing)) existing.addTo(this.map)
      return existing
    }

    const group = L.layerGroup()
    if (visible) group.addTo(this.map)
    this.categoryLayers.set(key, group)
    return group
  }

  setCategoryVisible(key, visible) {
    const group = this.categoryLayers.get(key)
    if (!group) return
    if (visible) group.addTo(this.map)
    else this.map.removeLayer(group)
    // Re-showing a layer must not leave it stuck on top. Leaflet has no
    // "insert at position": a group that was removed and added back becomes
    // the most recently added, which is the front of the shared canvas. For a
    // circle — whose whole disc is a hit area — that is enough to lock every
    // object inside it out of reach, so the order is rebuilt here.
    if (visible) this.restack()
  }

  /**
   * Rebuild the canvas draw order from the category insertion order.
   *
   * With `preferCanvas` the draw list is global, and selection depends on it:
   * Leaflet fires a click on the topmost layer that contains the point. A
   * deterministic order is therefore not cosmetic — without it, whether an
   * object can be clicked at all depends on the order the operator happened to
   * toggle layers in.
   *
   * The order is the one the layers arrived in, with the two measured shapes
   * resolved by `CATEGORY_DRAW_RANK`: a circle's disc underneath, a radial's
   * line above it, and both underneath the discrete objects. Nothing here
   * invents a policy beyond that; it only makes the order reproducible instead
   * of dependent on which layer the operator happened to toggle last.
   */
  restack() {
    if (!this.map) return
    const onMap = []
    this.categoryLayers.forEach((group, key) => {
      if (this.map.hasLayer(group)) onMap.push({ group, key })
    })
    onMap.sort((a, b) => drawRank(a.key) - drawRank(b.key))
    onMap.forEach(({ group }) => this.map.removeLayer(group))
    onMap.forEach(({ group }) => group.addTo(this.map))
    // Drafts are previews of what the operator is drawing right now. They were
    // on top before the restack; put them back there.
    this._draftLayers.forEach((layer) => {
      if (!this.map.hasLayer(layer)) layer.addTo(this.map)
    })
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
  // Intentionally absent: `setCategoryOrder` used to reorder panes for this and
  // is gone. It never worked with `preferCanvas` — one canvas, one draw list —
  // and no caller ever passed an order. `restack()` is the mechanism now, and
  // it moves the draw list rather than the DOM.

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
    // Remembered so `removeObject` can detach from this group and not only from
    // the map. See the note there: leaving the layer in the group is what made
    // deleted objects come back the next time the category was shown.
    layer._aerorfHost = host
    this.featureLayers.set(String(object.id), layer)

    if (object.show_label !== false && object.name) this._addTooltip(layer, object)
    return layer
  }

  _buildLayer(object, style) {
    const color = style.color || object.color || token('--trazo-observado', '#38bdf8')
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
      // A FeatureGroup, not a LayerGroup: the group has to pass on the clicks
      // its children receive. A plain LayerGroup does not, so making the circle
      // a group to carry the centre dot silently made it unselectable — no
      // click reached the store, and with no selection there was no way to
      // delete it or annotate it.
      const circle = L.featureGroup([
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
      // A FeatureGroup for the same reason as the circle: the line and its
      // origin dot have to be clickable as one object.
      const line = L.featureGroup([
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
    if (!text) return
    // Bound to the children, because a group has no tooltip of its own and the
    // name would never appear.
    const targets = this._vectorLayers(layer)
    if (targets.length) {
      targets.forEach((child) =>
        child.bindTooltip(text, { sticky: true, direction: 'top' }),
      )
    } else {
      layer.bindTooltip?.(text, { sticky: true, direction: 'top' })
    }
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
      // A click on an object is also published as a click on the map, carrying
      // the id of the object it landed on.
      //
      // It used to be swallowed: `stopPropagation` above was assumed to stop
      // the event before it reached the map, and it does not — the map draws
      // with `preferCanvas`, so all objects share one canvas element and there
      // is nothing for the propagation to stop at. Two consequences, both
      // reported as "nothing selects":
      //
      //   * a drawing tool never saw the click, so placing a radial at the
      //     centre of a circle did nothing;
      //   * the map's handler did see it, and with the select tool it cleared
      //     the selection the object handler had just made.
      //
      // Forwarding the position with the id attached is what lets a caller
      // tell "clicked an object" from "clicked empty ground".
      // The position is forwarded with the object id attached, whatever the
      // state of the tools.
      //
      // It used to be forwarded only while a drawing tool was armed, on the
      // reasoning that the select tool wanted the click for itself. That was
      // wrong in the other direction: this map draws with `preferCanvas`, so
      // every object shares one canvas element and `stopPropagation` cannot
      // stop the event at the object. The map's handler therefore runs for
      // every click on an object, and with the select tool it cleared the
      // selection the object handler had just made. Nothing was selectable.
      //
      // The id is what the shell needs in order to tell the two apart: a click
      // on an object selects, a click on empty space clears.
      this._emit('click', { latlng: e.latlng, overObject: objectId })
    })
    layer.on('dblclick', (e) => {
      L.DomEvent.stopPropagation(e)
      this._emit('objectdblclick', { id: objectId, latlng: e.latlng })
    })
    layer.on('mouseover', () => this._emit('objecthover', { id: objectId }))
    layer.on('mouseout', () => this._emit('objecthover', { id: null }))
    entry.bound = true
  }

  /**
   * Remove an object from the map (does not touch the database).
   *
   * Two removals, and the second one is the one that was missing.
   *
   * `layer.remove()` only takes the layer off the map. It does **not** detach it
   * from the `LayerGroup` that holds it — objects are added to a per-category
   * group, not straight to the map, so the group keeps the reference either way.
   * And `LayerGroup.onAdd` re-adds every child it still holds, so the moment that
   * category is put back on the map — by `restack()`, which runs on every layer
   * and category change — the layer comes back drawn.
   *
   * That was the whole of "deleted objects reappear, visible but unselectable":
   * the store had dropped them, `featureLayers` was empty, and the selection
   * handler had been deleted, so nothing could be selected any more; but the
   * group still held the layer and put it back on the next restack. Measured
   * after deleting three objects: store 0, map 0, one child left in each of
   * `reference_points`, `circles` and `radials`, and one `restack()` later all
   * three were back with no selection handler between them.
   *
   * The same leak happened on every re-render, because `renderObject` starts by
   * calling this: moving an object or changing its status left the old layer
   * behind in its group as well.
   *
   * The host is remembered in `_aerorfHost` when the layer is registered, so the
   * group can be found without searching all of them.
   */
  removeObject(objectId) {
    const key = String(objectId)
    if (this._highlighted != null && String(this._highlighted) === key) {
      this._highlighted = null
    }
    const layer = this.featureLayers.get(key)
    if (layer) {
      const host = layer._aerorfHost
      if (host && typeof host.removeLayer === 'function') host.removeLayer(layer)
      layer.remove()
      this.featureLayers.delete(key)
    }
    // Unconditional: a layer can be gone from the map and still be holding a
    // click handler, and a handler for an object that no longer exists is what
    // makes a selection land on nothing.
    this.selectionHandlers.delete(key)
  }

  /**
   * Every registered object, removed through the one path that also detaches
   * from the category group. Iterating `featureLayers` and calling
   * `layer.remove()` — what this did before — left every one of them in its
   * group.
   */
  clearObjects() {
    Array.from(this.featureLayers.keys()).forEach((key) => this.removeObject(key))
    this.featureLayers.clear()
    this.selectionHandlers.clear()
  }

  hasObject(objectId) {
    return this.featureLayers.has(String(objectId))
  }

  /** Visually emphasise the selected object. */
  /**
   * Every vector layer of a stored object, however it is grouped.
   *
   * A measured shape is a group — the ring or line plus its centre dot — and a
   * group has no `setStyle` of its own. Styling has to reach the children, and
   * doing it through `eachLayer` is what makes the highlight work on a circle
   * as well as on a bare point.
   *
   * It is also what stops a selection from throwing. `select()` calls this
   * before recording the id, so a layer whose `setStyle` was missing raised
   * here and the id was never stored: the object was clicked, and nothing was
   * selected. Every object was unselectable, not only the ones that had just
   * become groups.
   */
  _vectorLayers(layer) {
    if (!layer) return []
    if (typeof layer.eachLayer === 'function') {
      const out = []
      layer.eachLayer((child) => {
        if (typeof child.setStyle === 'function') out.push(child)
      })
      return out
    }
    return typeof layer.setStyle === 'function' ? [layer] : []
  }

  /**
   * The vector layers of a stored object, for callers outside the engine.
   *
   * Public because the store binds popups and double-click handlers, and it
   * needs to reach the children of a grouped shape. Duplicating the descent
   * there would be a second place to get it wrong.
   */
  vectorLayersFor(layer) {
    return this._vectorLayers(layer)
  }

  /**
   * The style a layer should return to.
   *
   * Captured once, the first time the object is styled, and kept on the layer.
   * Reading it back from `options` does not work: `setStyle` writes through to
   * `options`, so the first highlight overwrites the original weight and every
   * later restore puts back the *highlighted* weight. The selection then
   * compounded on each click, thickening the object a little more every time.
   */
  _baseStyle(layer) {
    if (layer.__aerorfBaseStyle) return layer.__aerorfBaseStyle
    const o = layer.options || {}
    const style = {
      color: o.color,
      weight: o.weight ?? 3,
      opacity: o.opacity ?? 1,
      fillOpacity: o.fillOpacity ?? 0.15,
    }
    Object.defineProperty(layer, '__aerorfBaseStyle', {
      value: style,
      writable: true,
      configurable: true,
      enumerable: false,
    })
    return style
  }

  highlight(objectId, color = token('--medicion', '#facc15')) {
    // Only the previously highlighted one is restored. Rewriting every object's
    // weight on every selection meant one extra write per object per click, and
    // the weight it wrote came from `options`, which the last highlight had
    // already changed.
    if (this._highlighted != null && this._highlighted !== objectId) {
      this._vectorLayers(this.featureLayers.get(String(this._highlighted))).forEach(
        (child) => child.setStyle(this._baseStyle(child)),
      )
    }
    const target = this.featureLayers.get(String(objectId))
    this._vectorLayers(target).forEach((child) => {
      const base = this._baseStyle(child)
      child.setStyle({ color, weight: base.weight + 3, fillOpacity: 0.35 })
    })
    // No `bringToFront()` here. The map renders with `preferCanvas`, so every
    // vector layer shares one canvas and one draw list: "bring to front" is a
    // *global* reorder, not a per-object one, and it sticks.
    //
    // A circle's hit area is its whole disc, not its ring — Leaflet's
    // `CircleMarker._containsPoint` is `distance <= radius` — and Leaflet's
    // canvas only fires the click on the topmost layer whose disc contains the
    // point. So selecting a 16 km circle once promoted it to the top of the
    // list for the rest of the session, and from then on every click inside it
    // was answered by that circle. The points, radials and events inside it
    // became unselectable until the page was reloaded.
    //
    // The highlight is made visible with weight and colour instead, which
    // cannot change who receives a click.
    this._highlighted = objectId
  }

  clearHighlight() {
    if (this._highlighted == null) return
    const layer = this.featureLayers.get(String(this._highlighted))
    this._vectorLayers(layer).forEach((child) => {
      child.setStyle(this._baseStyle(child))
    })
    this._highlighted = null
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

// The type labels live in `stores/map.js` as `typeName`, and that is the one the
// whole interface uses — the Inspector included. There was a second, identical
// table here as `typeLabel`, used only by `objectPopup`, which meant two places
// to keep in step and one that nothing read. It went when the popup did.

const PROVENANCE_LABELS = {
  observed: 'Dato observado',
  historical: 'Dato histórico',
  live: 'Dato en vivo',
  calculated: 'Dato calculado',
  user: 'Introducido por el usuario',
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

export default MapEngine
