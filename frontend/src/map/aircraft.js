/**
 * map/aircraft.js
 * ───────────────
 * Renders aircraft and their trajectories on the map.
 *
 * Provenance drives the styling, because the distinction matters to an
 * investigation (spec §56, §58):
 *
 *   live       — a current state vector, drawn as a solid aircraft marker
 *   historical — an OpenSky track waypoint path, drawn as a thin solid line
 *   aerorf     — a position AeroRF recorded itself, drawn dashed
 *   merged     — both together, drawn as a two-tone polyline
 *
 * A track is never interpolated to look denser than it is. If OpenSky
 * returned 12 waypoints, 12 vertices are drawn.
 */

import { token } from '../assets/tokens'
import L from 'leaflet'

/** Longitudes beyond this are "over the pole" and break icon rotation. */
const MAX_ICON_ROTATION = 179.9

/**
 * The dot that marks where a trajectory starts and where it ends.
 *
 * A `divIcon` marker instead of a `circleMarker` — a circleMarker is a path and
 * would have to ride the elevated, non-interactive track canvas, which would
 * cost the "Inicio"/"Fin" hover labels. See the note in `drawTrack`.
 *
 * Leaflet assigns `className` by *replacement* (`_setIconStyles`: `'leaflet-marker-icon '
 * + className`), so `leaflet-div-icon` and its white square are never applied.
 * The round shape is ours and lives in `assets/styles.css` as a **global** rule:
 * divIcon content is built as an HTML string and never receives the `data-v-…`
 * attribute a scoped style would need.
 *
 * @param {string} clase `aerorf-trazo-inicio` or `aerorf-trazo-fin`
 * @returns {L.DivIcon}
 */
function puntoTraza(clase) {
  return L.divIcon({
    className: `aerorf-trazo-punto ${clase}`,
    iconSize: [10, 10],
    iconAnchor: [5, 5],
  })
}

export class AircraftRenderer {
  /**
   * @param {import('./MapEngine').MapEngine} engine
   * @param {object} handlers {onSelect, onContext}
   */
  constructor(engine, handlers = {}) {
    this.engine = engine
    this.handlers = handlers

    /** @type {Map<string, {marker: L.Marker, color: string}>} */
    this.markers = new Map()
    /** @type {Map<string, L.Layer>} */
    this.tracks = new Map()

    this._ensureGroups()
  }

  _ensureGroups() {
    this.markerGroup = this.engine.ensureCategory('aircraft')
    this.trackGroup = this.engine.ensureCategory('aircraft_tracks')
  }

  // ─── Live markers (spec §23) ─────────────────────────────────────────────

  /**
   * Draw (or move) one aircraft marker.
   * @param {object} state  a parsed state vector
   * @param {string} color  watchlist slot colour
   */
  updateAircraft(state, color = token('--trazo-medido', '#22c55e')) {
    if (!state || state.latitude == null || state.longitude == null) return null

    const key = state.icao24
    let entry = this.markers.get(key)

    if (!entry) {
      const icon = this._aircraftIcon(color, state.heading, state)
      const marker = L.marker([state.latitude, state.longitude], {
        icon,
        zIndexOffset: 1000,
        keyboard: false,
      })
      marker.on('click', (e) => {
        L.DomEvent.stopPropagation(e)
        this.handlers.onSelect?.(state.icao24)
      })
      marker.on('contextmenu', (e) => {
        L.DomEvent.stopPropagation(e)
        this.handlers.onContext?.(state.icao24, e.latlng)
      })
      marker.addTo(this.markerGroup)
      // Remembered so `_detach` can let go of the group as well as of the map.
      // Without it an aircraft that left the watchlist came back the next time
      // the category was shown — the operator's "I deleted every flight and the
      // aeroplane is still there".
      marker._aerorfHost = this.markerGroup
      entry = { marker, color }
      this.markers.set(key, entry)
    } else if (entry.color !== color) {
      entry.marker.setIcon(this._aircraftIcon(color, state.heading, state))
      entry.color = color
    } else {
      entry.marker.setLatLng([state.latitude, state.longitude])
      entry.marker.setIcon(this._aircraftIcon(color, state.heading, state))
    }

    entry.marker.bindPopup(this._aircraftPopup(state, color))
    return entry.marker
  }

  _aircraftIcon(color, heading, state) {
    // Unknown heading: show the marker upright rather than guessing a
    // direction. Spec §56 — no invented data.
    const rotation =
      heading === null || heading === undefined
        ? 0
        : Math.max(-MAX_ICON_ROTATION, Math.min(MAX_ICON_ROTATION, heading))

    const label = state.callsign ? state.callsign.trim() : state.icao24

    return L.divIcon({
      className: 'aerorf-aircraft',
      html: `
        <div class="aerorf-aircraft-marker" style="color:${color}">
          <svg viewBox="0 0 24 24" width="26" height="26"
               style="transform: rotate(${rotation}deg)">
            <path fill="currentColor" stroke="#020617" stroke-width="0.7"
              d="M12 2 L14 9 L22 13 L22 15 L14 13.2 L14 20 L17 22 L17 23
                 L12 21.6 L7 23 L7 22 L10 20 L10 13.2 L2 15 L2 13 L10 9 Z"/>
          </svg>
          <span class="aerorf-aircraft-label" style="border-color:${color}">${escapeHtml(label)}</span>
        </div>`,
      iconSize: [26, 26],
      iconAnchor: [13, 13],
    })
  }

  _aircraftPopup(state, color) {
    const row = (k, v) =>
      v === null || v === undefined || v === ''
        ? ''
        : `<div class="aerorf-popup-row"><span>${k}</span><b>${escapeHtml(String(v))}</b></div>`

    const rows = [
      row('Callsign', state.callsign || 'dato no disponible'),
      row('ICAO24', state.icao24),
      row('Estado', state.on_ground ? 'en tierra' : 'en vuelo'),
      row('Altitud', state.altitude != null ? `${Math.round(state.altitude)} m` : 'dato no disponible'),
      row('Velocidad', state.velocity != null ? `${state.velocity.toFixed(1)} m/s` : 'dato no disponible'),
      row('Rumbo', state.heading != null ? `${state.heading.toFixed(1)}°` : 'dato no disponible'),
      row('Vertical', state.vertical_rate != null ? `${state.vertical_rate.toFixed(2)} m/s` : null),
      row('Posición', `${state.latitude.toFixed(5)}, ${state.longitude.toFixed(5)}`),
      row('Fuente posición', state.position_source),
      row('Origen', state.origin_country),
      row('Actualizado', state.time_position ? formatUnix(state.time_position) : 'dato no disponible'),
    ].join('')

    return `
      <div class="aerorf-popup">
        <div class="aerorf-popup-title" style="color:${color}">
          ✈ ${escapeHtml(state.callsign || state.icao24)}
        </div>
        <div class="aerorf-popup-rows">${rows}</div>
        <div class="aerorf-popup-hint">Doble clic para ver la trayectoria</div>
      </div>`
  }

  // ─── Tracks (spec §21, §22) ─────────────────────────────────────────────

  /**
   * Draw a track, colour-coded by provenance.
   *
   * Each aircraft keeps its own track, so several trajectories can be on the
   * map at once. That is the point of drawing them: comparing one route
   * against another. It used to call `clearTracks()` first, which meant the
   * previous aircraft's path vanished the moment a second one arrived, and
   * there was no way to see two flights together.
   *
   * @param {object} track  the `/flights/{icao24}/track` response
   * @param {string} color
   */
  drawTrack(track, color = token('--trazo-vuelo', '#a855f7')) {
    if (!track) {
      this.clearTracks()
      return null
    }
    // Only this aircraft's own previous track goes; the others stay.
    this.removeTrack(track.icao24 || 'current')

    const points = (track.points || []).filter(
      (p) => p.latitude != null && p.longitude != null,
    )
    if (!points.length) return null

    // Split by provenance so each source is visually distinct.
    const groups = { historical: [], aerorf: [], live: [], other: [] }
    points.forEach((p) => {
      const key = p.provenance || 'other'
      ;(groups[key] || groups.other).push([p.latitude, p.longitude])
    })

    const layer = L.layerGroup()

    // The engine's own renderer, in a pane above everything the operator drew.
    // Without it the trajectory shares the object's canvas and lands *under* it:
    // the paths are created when the shell mounts, before any object exists, and
    // a shared canvas draws in creation order. `restack()` cannot fix that —
    // re-adding a layer does not renumber it — but a pane can, because panes are
    // stacked by z-index. See `MapEngine._addTrackPane`.
    const render = this.engine.trackRenderer

    // AeroRF's own recording: dashed, so it is never mistaken for OpenSky data.
    if (groups.aerorf.length >= 2) {
      layer.addLayer(
        L.polyline(groups.aerorf, {
          renderer: render,
          color: token('--trazo-medido', '#22c55e'),
          weight: 2.5,
          opacity: 0.9,
          dashArray: '7,5',
        }),
      )
    }
    // OpenSky historical track: solid.
    if (groups.historical.length >= 2) {
      layer.addLayer(
        L.polyline(groups.historical, {
          renderer: render,
          color,
          weight: 3,
          opacity: 0.85,
        }),
      )
    }
    if (groups.live.length >= 2) {
      layer.addLayer(
        L.polyline(groups.live, {
          renderer: render,
          color: '#eab308',
          weight: 3,
          opacity: 0.9,
        }),
      )
    }
    if (groups.other.length >= 2) {
      layer.addLayer(
        L.polyline(groups.other, { renderer: render, color, weight: 2, opacity: 0.6 }),
      )
    }

    // Single-point tracks still deserve a marker: the position is real even
    // if the path is not.
    if (points.length === 1) {
      layer.addLayer(
        L.circleMarker(points[0], {
          renderer: render,
          radius: 6, color, fillOpacity: 0.6, weight: 2,
        }),
      )
    }

    // Waypoint dots: the density on screen IS the data density.
    //
    // They take the track renderer too, and that is not cosmetic. Measured:
    // `drawTrack` produced five children for a two-point track and only the
    // polyline was in the elevated pane — the four dots stayed on the shared
    // canvas, under every filled object. The line looked right and the dots
    // under a coverage circle simply were not there.
    const step = Math.max(1, Math.floor(points.length / 120))
    points.forEach((p, i) => {
      if (i % step !== 0) return
      layer.addLayer(
        L.circleMarker([p.latitude, p.longitude], {
          renderer: render,
          radius: 1.8,
          color,
          fillOpacity: 0.5,
          weight: 0,
        }),
      )
    })

    // Start and end markers — markers, not paths, on purpose.
    //
    // A `circleMarker` is a path, so it would have to ride the elevated track
    // canvas. That canvas is `pointer-events: none`, because a vector layer
    // outside the overlay pane gets its own full-size canvas and Leaflet gives
    // every canvas `pointer-events: auto` — that is the outage where nothing on
    // the map was clickable. And a layer that receives no pointer events
    // receives no hover either, so the "Inicio"/"Fin" labels would have opened
    // on nothing: a feature quietly gone, which is the thing this project keeps
    // refusing to do.
    //
    // A marker is a DOM element, not a canvas, so it keeps its own hit area and
    // its tooltip, and it sits in the marker pane (z 600) — above the track
    // pane (500), so the endpoints are visible over any filled shape. DivIcon
    // replaces the class rather than appending it, so the white
    // `leaflet-div-icon` square is not applied; the circle is ours in
    // `assets/styles.css`.
    const first = points[0]
    const last = points[points.length - 1]
    layer.addLayer(
      L.marker([first.latitude, first.longitude], {
        icon: puntoTraza('aerorf-trazo-inicio'),
        keyboard: false,
      }).bindTooltip('Inicio', { permanent: false }),
    )
    layer.addLayer(
      L.marker([last.latitude, last.longitude], {
        icon: puntoTraza('aerorf-trazo-fin'),
        keyboard: false,
      }).bindTooltip('Fin', { permanent: false }),
    )

    layer.addTo(this.trackGroup)
    // Remembered so `_detach` can let go of the group as well as of the map.
    // Without it the trajectory stayed in `trackGroup` and came back on the next
    // restack — and the group has no way to find its members otherwise.
    layer._aerorfHost = this.trackGroup
    this.tracks.set(track.icao24 || 'current', layer)
    return layer
  }

  /**
   * Remove one aircraft's track, leaving every other one on the map.
   *
   * Detaching from `trackGroup` is not optional. `drawTrack` adds each
   * trajectory with `layer.addTo(this.trackGroup)`, and `layer.remove()` only
   * takes it off the map — the group keeps the reference, and `LayerGroup.onAdd`
   * re-adds every child it still holds.
   *
   * The store caches one trajectory per aircraft, so selecting a second flight
   * of the same aircraft replaces the cached data and calls `drawTrack` again,
   * which calls this first. Measured in the browser with two flights of
   * `e02659`: the group held 2 children after the first and **3** after the
   * second, and a single `restack()` put all three back on the map. That is the
   * trajectories piling up on themselves and never going away.
   *
   * The same leak applied to `clearTracks`, which is what "Quitar todas" calls:
   * it emptied its own `Map` and left every layer in the group, so the next
   * restack brought the lot back.
   */
  removeTrack(icao24) {
    const key = icao24 || 'current'
    const layer = this.tracks.get(key)
    if (layer) {
      this._detach(layer)
      this.tracks.delete(key)
    }
    return Boolean(layer)
  }

  clearTracks() {
    this.tracks.forEach((layer) => this._detach(layer))
    this.tracks.clear()
  }

  // ─── Housekeeping ────────────────────────────────────────────────────────

  /**
   * Take a layer off the map *and* let go of it.
   *
   * `layer.remove()` only does the first. Both the markers and the trajectories
   * live in a per-category `LayerGroup`, so the group keeps the reference and
   * `LayerGroup.onAdd` re-adds every child it still holds the next time that
   * category is shown. That is what put aircraft back on the map after "Quitar
   * todas", and what stacked trajectories of the same aircraft in 0.29.4.
   *
   * Four call sites needed this and each got it wrong on its own once already,
   * so it is one method now: a layer is detached here or nowhere.
   */
  _detach(layer) {
    const group = layer?._aerorfHost
    if (group && typeof group.removeLayer === 'function') group.removeLayer(layer)
    layer?.remove()
  }

  /** Remove markers for aircraft no longer tracked. */
  syncMarkers(activeIcao24s) {
    const active = new Set((activeIcao24s || []).map((c) => c))
    this.markers.forEach((entry, icao24) => {
      if (!active.has(icao24)) {
        this._detach(entry.marker)
        this.markers.delete(icao24)
      }
    })
  }

  highlight(icao24, color = token('--medicion', '#facc15')) {
    this.markers.forEach((entry, key) => {
      const size = key === icao24 ? [32, 32] : [26, 26]
      entry.marker.setIcon(this._aircraftIcon(key === icao24 ? color : entry.color, null, { callsign: key }))
    })
  }

  clear() {
    this.markers.forEach((entry) => this._detach(entry.marker))
    this.markers.clear()
    this.clearTracks()
  }
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function formatUnix(ts) {
  const d = new Date(ts * 1000)
  if (Number.isNaN(d.getTime())) return String(ts)
  return d.toISOString().replace('T', ' ').slice(0, 19) + 'Z'
}

export default AircraftRenderer
