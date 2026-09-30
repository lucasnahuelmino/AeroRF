/**
 * map/airports.js
 * ───────────────
 * Draws the aerodrome reference layer and answers distance queries against
 * it.
 *
 * Two rules shape this module:
 *
 * 1. Nothing here is persisted. The ARP positions are published facts (see
 *    `data/airports.js`), so the layer is rebuilt from that file every time
 *    and never becomes a row in `map_objects`. That keeps a reference point
 *    from being mistaken for something the operator drew or measured.
 *
 * 2. A reference point is labelled as one. The tooltip says "referencia" and
 *    the legend lists the layer under reference data, because an ARP is a
 *    published coordinate and not an observation.
 */

import L from 'leaflet'
import { AIRPORTS, AIRPORT_COUNTRIES, findAirport, airportCode, isMajor } from '@/data/airports'
import { haversine, haversineKm, bearing, normaliseAzimuth } from './geo'

export const AIRPORT_LAYER_KEY = 'airports'

/**
 * Two symbol families, because the layer now carries every aerodrome in the
 * country and not only the hub.
 *
 * The operator asked for the smaller ones, and El Palomar and San Fernando
 * among them, which is the right request: they share the Buenos Aires FIR with
 * EZE and AEP, so a second source of metro-area interference is exactly what
 * they need an ARP for. But a 4 nm regional strip drawn the same way as a hub
 * disappears under it, so the two are told apart by colour, by size and by
 * whether the disc is filled.
 *
 * Major: sky blue, filled, and a permanent label. Minor: amber, hollow, a
 * smaller radius, and a dimmer label. The legend in the panel says which is
 * which, so the difference is information and not decoration.
 */
const SYMBOL_MAJOR = {
  radius: 7,
  color: '#38bdf8',
  weight: 2,
  fillColor: '#0ea5e9',
  fillOpacity: 0.5,
}

const SYMBOL_MINOR = {
  radius: 4.5,
  color: '#f59e0b',
  weight: 1.5,
  fillColor: '#78350f',
  fillOpacity: 0.15,
}

/** Circle radius per aerodrome class, in metres. Only for the heliports. */
const SYMBOL_HELIPORT = { radius: 3, color: '#64748b', weight: 1.5, fillColor: '#334155', fillOpacity: 0.35 }

function symbolFor(airport) {
  if (airport.kind === 'heliport') return SYMBOL_HELIPORT
  return isMajor(airport) ? SYMBOL_MAJOR : SYMBOL_MINOR
}

const KIND_LABEL = {
  large_airport: 'Aeropuerto grande',
  medium_airport: 'Aeropuerto mediano',
  small_airport: 'Aeropuerto pequeño',
  heliport: 'Helipuerto',
}

/**
 * Renders and controls the aerodrome layer.
 *
 * Kept as a class for the same reason as MapEngine: it owns Leaflet objects
 * and must not re-render through Vue. The shell and the layer panel talk to
 * it through the four methods below.
 */
export class AirportLayer {
  /**
   * @param {import('./MapEngine').MapEngine} engine
   */
  constructor(engine) {
    this.engine = engine
    /** @type {Map<string, L.Layer>} ICAO -> marker */
    this.markers = new Map()
    this.group = null
    /**
     * Country codes currently drawn. Empty means "all".
     *
     * Underscore-prefixed because `countries` is a getter over the reference
     * data: a plain `this.countries` field and a `get countries()` cannot
     * coexist, and the setter would have thrown on every call.
     */
    this._countries = new Set()
    this.labelsVisible = true
  }

  /** Build the layer without adding it to the map. */
  init() {
    this.group = this.engine.ensureCategory(AIRPORT_LAYER_KEY, { visible: false })
    this.rebuild()
    return this
  }

  /**
   * Rebuild every marker for the current country filter.
   *
   * Called on init and whenever the filter changes. Rebuilding the markers is
   * cheaper than tracking which ones a filter removed, and it cannot leave a
   * stale marker behind.
   */
  rebuild() {
    if (!this.group) return 0
    this.group.clearLayers()
    this.markers.clear()

    let drawn = 0
    for (const airport of AIRPORTS) {
      if (this._countries.size && !this._countries.has(airport.country)) continue
      const marker = this._marker(airport)
      // Keyed by `key`, not by `icao`: San Fernando publishes no ICAO code, so
      // keying on it would put that aerodrome under `null` and lose it.
      this.markers.set(airport.key, marker)
      this.group.addLayer(marker)
      drawn += 1
    }
    return drawn
  }

  _marker(airport) {
    const symbol = symbolFor(airport)
    // A square-with-a-notch reads as "aerodrome" at a glance, which a plain
    // dot does not, and stays legible next to the aircraft markers.
    const marker = L.circleMarker([airport.lat, airport.lon], {
      radius: symbol.radius,
      color: symbol.color,
      weight: symbol.weight,
      opacity: 0.95,
      fillColor: symbol.fillColor,
      fillOpacity: symbol.fillOpacity,
      bubblingMouseEvents: false,
    })

    marker.bindTooltip(this._tooltip(airport), {
      sticky: true,
      direction: 'top',
      className: 'aerorf-airport-tip',
    })
    marker.bindPopup(this._popup(airport), { className: 'aerorf-popup-wrap', maxWidth: 260 })
    marker.airport = airport
    marker.major = airport.kind !== 'heliport' && isMajor(airport)
    return marker
  }

  _tooltip(airport) {
    const bits = [
      `<strong>${escapeHtml(airportCode(airport))}</strong>`,
      escapeHtml(airport.name),
      '<i>referencia</i>',
    ]
    // Every code it publishes, so the operator can see which one to type.
    const codes = [airport.icao, airport.iata, airport.gps, airport.local]
      .filter((c) => typeof c === 'string' && c.length > 0)
      .filter((c, i, all) => all.indexOf(c) === i)
    if (codes.length > 1) bits.push(codes.join(' · '))
    return bits.join('<br/>')
  }

  _popup(airport) {
    const row = (k, v) =>
      v === null || v === undefined || v === ''
        ? ''
        : `<div class="aerorf-popup-row"><span>${escapeHtml(k)}</span><b>${escapeHtml(
            String(v),
          )}</b></div>`

    const rows = [
      row('ICAO', airport.icao),
      row('IATA', airport.iata),
      row('Código local', airport.local),
      row('Nombre', airport.name),
      row('Tipo', KIND_LABEL[airport.kind] || airport.kind),
      row('Tráfico', airport.scheduled ? 'Vuelo regular' : 'Sin vuelo regular'),
      row('ARP', `${airport.lat.toFixed(5)}, ${airport.lon.toFixed(5)}`),
      row('Elevación', airport.elevFt != null ? `${airport.elevFt} ft` : null),
      row('País', airport.country),
    ].join('')

    return (
      `<div class="aerorf-popup">` +
      `<div class="aerorf-popup-title">${escapeHtml(airportCode(airport))}</div>` +
      `<div class="aerorf-popup-desc">${escapeHtml(airport.name)}</div>` +
      rows +
      `<div class="aerorf-popup-hint">Punto de referencia publicado, no medido por AeroRF.</div>` +
      `</div>`
    )
  }

  // ── Visibility and filtering ─────────────────────────────────────────────

  /** @param {boolean} visible */
  setVisible(visible) {
    if (!this.group) return
    if (visible) this.group.addTo(this.engine.map)
    else this.engine.map.removeLayer(this.group)
  }

  get visible() {
    return Boolean(this.group && this.engine.map.hasLayer(this.group))
  }

  /**
   * Restrict the layer to some countries. An empty set means all of them.
   * @param {Iterable<string>} codes
   */
  setCountries(codes) {
    this._countries = new Set(codes)
    this.rebuild()
    if (this.visible) this.group.addTo(this.engine.map)
  }

  /** Show or hide the short code beside each symbol. */
  setLabels(visible) {
    this.labelsVisible = Boolean(visible)
    for (const [, marker] of this.markers) {
      const airport = marker.airport
      if (this.labelsVisible) {
        marker.bindTooltip(this._tooltip(airport), {
          sticky: true,
          direction: 'top',
          className: 'aerorf-airport-tip',
        })
        // A permanent label, distinct from the hover tooltip, so the codes
        // stay readable while panning without a tooltip in the way.
        //
        // A permanent tooltip, not `bindLabel`: that is a Leaflet.marker
        // method, and a circleMarker has no such method. Calling it threw on
        // every aerodrome the moment the operator asked for labels.
        //
        // The code shown is the IATA — EZE, AEP — because that is what the
        // operator reads on a boarding pass and types into a slot. It falls
        // back to the ICAO, then the GPS, then the local code, for the
        // aerodromes that publish no IATA.
        marker.bindTooltip(airportCode(airport), {
          permanent: true,
          direction: 'right',
          className: marker.major ? 'aerorf-airport-label' : 'aerorf-airport-label aerorf-airport-label-minor',
          opacity: 0.8,
        })
      } else {
        marker.unbindTooltip()
        // Re-bind the hover tooltip, since unbinding removed it too.
        marker.bindTooltip(this._tooltip(airport), {
          sticky: true,
          direction: 'top',
          className: 'aerorf-airport-tip',
        })
      }
    }
    return this
  }

  get count() {
    return this.markers.size
  }

  /** Countries present, with their aerodrome counts, for the filter control. */
  get countries() {
    return AIRPORT_COUNTRIES
  }

  /** Fit the map to the airports, optionally filtered. */
  fitTo({ country = null } = {}) {
    const points = []
    for (const airport of AIRPORTS) {
      if (country && airport.country !== country) continue
      points.push([airport.lat, airport.lon])
    }
    if (!points.length) return null
    return this.engine.map.fitBounds(L.latLngBounds(points).pad(0.15))
  }

  // ── Distance ─────────────────────────────────────────────────────────────

  /**
   * Great-circle distance and bearing from an airport to a point.
   *
   * Used by "distancia desde aeropuerto" and by the distance tool, so both
   * report identical numbers for the same pair.
   *
   * @param {string} code   ICAO or IATA
   * @param {number} lat
   * @param {number} lon
   * @returns {{airport: object, metres: number, km: number, nm: number,
   *            bearing: number, bearing_cardinal: string} | null}
   */
  measureFrom(code, lat, lon) {
    const airport = findAirport(code)
    if (!airport) return null
    if (lat == null || lon == null) return null

    const metres = haversine(airport.lat, airport.lon, lat, lon)
    const az = normaliseAzimuth(bearing(airport.lat, airport.lon, lat, lon))
    return {
      airport,
      metres,
      km: metres / 1000,
      nm: metres / 1852,
      bearing: az,
      bearing_cardinal: cardinal(az),
    }
  }

  /**
   * Every airport within `radiusNm` of a point, nearest first.
   * @param {number} lat @param {number} lon @param {number} radiusNm
   */
  within(lat, lon, radiusNm) {
    const limit = radiusNm * 1852
    const hits = []
    for (const airport of AIRPORTS) {
      const d = haversine(lat, lon, airport.lat, airport.lon)
      if (d <= limit) hits.push({ airport, metres: d, km: d / 1000, nm: d / 1852 })
    }
    return hits.sort((a, b) => a.metres - b.metres)
  }

  /**
   * Draw the line from an airport to a point, with the distance in the
   * tooltip. The line is a draft-style layer: it belongs to the measurement
   * being shown, not to the airport layer.
   */
  drawMeasure(key, result, to) {
    const engine = this.engine
    const from = [result.airport.lat, result.airport.lon]
    const dest = [Number(to[0]), Number(to[1])]
    if (!Number.isFinite(dest[0]) || !Number.isFinite(dest[1])) return null
    const line = L.polyline([from, dest], {
      color: '#f59e0b',
      weight: 2,
      dashArray: '6,4',
      interactive: false,
    })
    const label = L.circleMarker(dest, {
      radius: 4,
      color: '#f59e0b',
      weight: 2,
      fillOpacity: 0.2,
      interactive: false,
    })
    line.bindTooltip(
      `<b>${escapeHtml(airportCode(result.airport))}</b> → punto<br/>` +
        `${result.km.toFixed(2)} km · ${result.nm.toFixed(2)} NM<br/>` +
        `rumbo ${result.bearing.toFixed(0)}° (${result.bearing_cardinal})`,
      { sticky: true },
    )
    engine.setDraft(key, L.layerGroup([line, label]))
    return line
  }

  removeMeasure(key) {
    this.engine.removeDraft(key)
  }

  destroy() {
    this.markers.clear()
    this.group = null
  }
}

const CARDINALS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                   'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']

/** Sixteen-point compass name for an azimuth. */
function cardinal(az) {
  return CARDINALS[Math.round(normaliseAzimuth(az) / 22.5) % 16]
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c])
}

export { cardinal }
