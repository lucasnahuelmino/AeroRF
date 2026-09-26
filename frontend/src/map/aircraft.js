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

import L from 'leaflet'

/** Longitudes beyond this are "over the pole" and break icon rotation. */
const MAX_ICON_ROTATION = 179.9

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
  updateAircraft(state, color = '#22c55e') {
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
   * @param {object} track  the `/flights/{icao24}/track` response
   * @param {string} color
   */
  drawTrack(track, color = '#a855f7') {
    if (!track) {
      this.clearTracks()
      return null
    }
    this.clearTracks()

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

    // AeroRF's own recording: dashed, so it is never mistaken for OpenSky data.
    if (groups.aerorf.length >= 2) {
      layer.addLayer(
        L.polyline(groups.aerorf, {
          color: '#22c55e',
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
          color,
          weight: 3,
          opacity: 0.85,
        }),
      )
    }
    if (groups.live.length >= 2) {
      layer.addLayer(
        L.polyline(groups.live, {
          color: '#eab308',
          weight: 3,
          opacity: 0.9,
        }),
      )
    }
    if (groups.other.length >= 2) {
      layer.addLayer(L.polyline(groups.other, { color, weight: 2, opacity: 0.6 }))
    }

    // Single-point tracks still deserve a marker: the position is real even
    // if the path is not.
    if (points.length === 1) {
      layer.addLayer(
        L.circleMarker(points[0], {
          radius: 6, color, fillOpacity: 0.6, weight: 2,
        }),
      )
    }

    // Waypoint dots: the density on screen IS the data density.
    const step = Math.max(1, Math.floor(points.length / 120))
    points.forEach((p, i) => {
      if (i % step !== 0) return
      layer.addLayer(
        L.circleMarker([p.latitude, p.longitude], {
          radius: 1.8,
          color,
          fillOpacity: 0.5,
          weight: 0,
        }),
      )
    })

    // Start and end markers.
    const first = points[0]
    const last = points[points.length - 1]
    layer.addLayer(
      L.circleMarker([first.latitude, first.longitude], {
        radius: 5, color: '#22c55e', fillOpacity: 0.9, weight: 2,
      }).bindTooltip('Inicio', { permanent: false }),
    )
    layer.addLayer(
      L.circleMarker([last.latitude, last.longitude], {
        radius: 5, color: '#ef4444', fillOpacity: 0.9, weight: 2,
      }).bindTooltip('Fin', { permanent: false }),
    )

    layer.addTo(this.trackGroup)
    this.tracks.set(track.icao24 || 'current', layer)
    return layer
  }

  clearTracks() {
    this.tracks.forEach((layer) => layer.remove())
    this.tracks.clear()
  }

  // ─── Housekeeping ────────────────────────────────────────────────────────

  /** Remove markers for aircraft no longer tracked. */
  syncMarkers(activeIcao24s) {
    const active = new Set((activeIcao24s || []).map((c) => c))
    this.markers.forEach((entry, icao24) => {
      if (!active.has(icao24)) {
        entry.marker.remove()
        this.markers.delete(icao24)
      }
    })
  }

  highlight(icao24, color = '#facc15') {
    this.markers.forEach((entry, key) => {
      const size = key === icao24 ? [32, 32] : [26, 26]
      entry.marker.setIcon(this._aircraftIcon(key === icao24 ? color : entry.color, null, { callsign: key }))
    })
  }

  clear() {
    this.markers.forEach((entry) => entry.marker.remove())
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
