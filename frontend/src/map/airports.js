/**
 * map/airports.js
 * ───────────────
 * Capa de referencia: dibuja lo publicado (archivo `data/airports.js`) y los
 * sitios de la lista del operador (composable `useAirport`), y responde
 * consultas de distancia contra lo publicado.
 *
 * Reglas que dan forma a este módulo:
 *
 * 1. Nada de esto se persiste. Las posiciones son datos de referencia —
 *    publicados o cargados por el operador — y la capa se reconstruye desde
 *    los archivos cada vez: nunca se vuelve una fila en `map_objects`, así
 *    un punto de referencia no puede confundirse con algo medido.
 *
 * 2. Cada marcador dice que es referencia: el tooltip dice «referencia» y
 *    la leyenda lo lista bajo datos de referencia.
 *
 * 3. Un sitio de la lista que cae a ≤ 2 km de un aeropuerto publicado se
 *    dibuja UNA sola vez, junto a ese aeropuerto: el popup lista todos los
 *    sitios que caen ahí, de modo que ninguna entrada de la lista se pierde.
 *    El resto de la lista se dibuja como sitio suelto con círculo: un EAVA
 *    o un CCTE lejos de todo aeropuerto no es un aerodromo y no lleva avión.
 *
 * 4. El símbolo de aeropuerto es una imagen: `public/iconos/aeropuerto.svg`.
 *    El marcador sólo nombra la ruta, así que cambiar el dibujo es
 *    reemplazar el archivo — sin tocar código.
 */

import L from 'leaflet'
import { AIRPORTS, AIRPORT_COUNTRIES, findAirport, airportCode, isMajor } from '@/data/airports'
import { haversine, haversineKm, bearing, normaliseAzimuth } from './geo'
import { useAirport } from '@/composables/useAirport'

export const AIRPORT_LAYER_KEY = 'airports'

/** Ruta del icono de aeropuerto. Cambiar la imagen = reemplazar el archivo. */
export const ICONO_AEROPUERTO = '/iconos/aeropuerto.svg'

/** Tolerancia de la coincidencia sitio-lista ↔ aeropuerto publicado, en metros. */
const COINCIDENCIA_M = 2000

/** La lista del operador, aplanada y con su grupo, una sola vez. */
const SITIOS_LISTA = useAirport().airport.flatMap((g) =>
  g.options.map((o) => ({ ...o, grupo: g.group })),
)

/** El aeropuerto publicado más cercano a un sitio de la lista, o null. */
function aeropuertoCercano(sitio) {
  let mejor = null
  let mejorD = Infinity
  for (const a of AIRPORTS) {
    const d = haversine(a.lat, a.lon, sitio.latitude, sitio.longitude)
    if (d <= COINCIDENCIA_M && d < mejorD) {
      mejor = a
      mejorD = d
    }
  }
  return mejor
}

/**
 * Todos los sitios de la lista que caen junto a un aeropuerto publicado, el
 * más cercano primero. Son varios a veces — SAAV tiene «SANTA FE» a 101 m y
 * «EAVA SAUCE VIEJO» a 593 m — y todos deben aparecer en el popup: perder el
 * segundo sería dejar de visualizar una entrada de la lista del operador.
 */
function sitiosDe(aeropuerto) {
  return SITIOS_LISTA.map((s) => ({
    s,
    d: haversine(aeropuerto.lat, aeropuerto.lon, s.latitude, s.longitude),
  }))
    .filter((x) => x.d <= COINCIDENCIA_M)
    .sort((a, b) => a.d - b.d)
    .map((x) => x.s)
}

/**
 * Todo lo que la capa dibuja, calculado una vez.
 *
 * Lo publicado primero (cada aeropuerto con los sitios de la lista que caen
 * a ≤ 2 km, y el más cercano como nombre principal), y después los sitios de
 * la lista que no son aeropuerto publicado. El resultado no tiene repetidos:
 * un sitio ya emparejado no vuelve a sumarse por su cuenta.
 */
function sitiosParaDibujar() {
  const dibujados = AIRPORTS.map((a) => {
    const cerca = sitiosDe(a)
    if (!cerca.length) return a
    return {
      ...a,
      sitios: cerca.map((s) => s.label),
      sitio: cerca[0].label,
      grupo: cerca[0].grupo,
    }
  })
  for (const s of SITIOS_LISTA) {
    if (aeropuertoCercano(s)) continue
    dibujados.push({
      key: s.value,
      name: s.label,
      sitio: s.label,
      grupo: s.grupo,
      lat: s.latitude,
      lon: s.longitude,
      // Todas las coordenadas de la lista caen en territorio argentino: el
      // país existe sólo para el filtro y se toma de esa coordenada.
      country: 'AR',
      kind: 'sitio',
      icao: null,
      iata: null,
      gps: null,
      local: null,
      scheduled: false,
      elevFt: null,
    })
  }
  return dibujados
}

const DIBUJAR = sitiosParaDibujar()

/**
 * Símbolos de los círculos. Los aerodromes publicados ya no usan círculo:
 * se dibujan con el icono de avión (ver `_marker`) y el tamaño distingue a
 * los mayores de los menores. El círculo queda para lo que no es aeródromo
 * de porte: el helipuerto (pizarra) y los sitios de la lista del operador
 * sin aeropuerto publicado (ámbar, hueco — la familia menor de siempre).
 */
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
  return SYMBOL_MINOR
}

const KIND_LABEL = {
  large_airport: 'Aeropuerto grande',
  medium_airport: 'Aeropuerto mediano',
  small_airport: 'Aeropuerto pequeño',
  heliport: 'Helipuerto',
  sitio: 'Sitio de la lista del operador',
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
    for (const airport of DIBUJAR) {
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
    let marker
    if (airport.kind !== 'sitio' && airport.kind !== 'heliport') {
      // Aeródromo: el icono de avión sobre un disco claro, para que cualquier
      // imagen que ponga el operador en `public/iconos/` se lea sobre el mapa
      // oscuro. Los mayores van más grandes: la información de antes (dos
      // familias distinguibles), ahora en el tamaño y no en el color.
      const lado = isMajor(airport) ? 26 : 18
      marker = L.marker([airport.lat, airport.lon], {
        icon: L.divIcon({
          className: 'aerorf-airport-icon',
          html:
            `<img src="${ICONO_AEROPUERTO}" alt="" draggable="false"` +
            ` width="${lado - 8}" height="${lado - 8}">`,
          iconSize: [lado, lado],
        }),
        bubblingMouseEvents: false,
      })
    } else {
      const symbol = symbolFor(airport)
      marker = L.circleMarker([airport.lat, airport.lon], {
        radius: symbol.radius,
        color: symbol.color,
        weight: symbol.weight,
        opacity: 0.95,
        fillColor: symbol.fillColor,
        fillOpacity: symbol.fillOpacity,
        bubblingMouseEvents: false,
      })
    }

    marker.bindTooltip(this._tooltip(airport), {
      sticky: true,
      direction: 'top',
      className: 'aerorf-airport-tip',
    })
    marker.bindPopup(this._popup(airport), { className: 'aerorf-popup-wrap', maxWidth: 260 })
    marker.airport = airport
    marker.major =
      airport.kind !== 'heliport' && airport.kind !== 'sitio' && isMajor(airport)
    return marker
  }

  _tooltip(airport) {
    // El código en negrita. Para un sitio de la lista no hay IATA ni ICAO,
    // y ahí manda el nombre tal cual lo cargó el operador: el recorte a 14
    // caracteres de `airportCode` partiría «EAVA SAUCE VIEJO» por la mitad.
    const codigo = airport.kind === 'sitio' ? airport.name : airportCode(airport)
    const bits = [`<strong>${escapeHtml(codigo)}</strong>`]
    if (codigo !== airport.name) bits.push(escapeHtml(airport.name))
    // Los nombres del operador cuando el marcador lleva un aeropuerto
    // publicado encima: es como él los llama en su lista. Todos, porque la
    // lista puede tener dos entradas sobre el mismo aeropuerto y ninguna
    // debe perderse.
    if (airport.sitios?.length) {
      bits.push(`Sitio: ${escapeHtml(airport.sitios.join(' · '))}`)
    }
    if (airport.grupo && airport.grupo !== airport.sitio && airport.grupo !== airport.name) {
      bits.push(escapeHtml(airport.grupo))
    }
    bits.push('<i>referencia</i>')
    // Every code it publishes, so the operator can see which one to type.
    const codes = [airport.icao, airport.iata, airport.gps, airport.local]
      .filter((c) => typeof c === 'string' && c.length > 0)
      .filter((c, i, all) => all.indexOf(c) === i)
    if (codes.length > 1) bits.push(codes.join(' · '))
    return bits.join('<br/>')
  }

  _popup(airport) {
    const esSitio = airport.kind === 'sitio'
    const row = (k, v) =>
      v === null || v === undefined || v === ''
        ? ''
        : `<div class="aerorf-popup-row"><span>${escapeHtml(k)}</span><b>${escapeHtml(
            String(v),
          )}</b></div>`

    const filas = []
    // Cómo lo llama el operador en su lista, antes que los códigos
    // publicados. Un aeropuerto puede llevar varios sitios encima (el campo
    // y una instalación vecina): se listan todos.
    if (!esSitio && airport.sitios?.length) {
      filas.push(
        row(airport.sitios.length > 1 ? 'Sitios' : 'Sitio', airport.sitios.join(' · ')),
      )
    }
    if (airport.grupo && airport.grupo !== airport.sitio && airport.grupo !== airport.name) {
      filas.push(row('Grupo', airport.grupo))
    }
    filas.push(
      row('ICAO', airport.icao),
      row('IATA', airport.iata),
      row('Código local', airport.local),
      row('Nombre', airport.name),
      row('Tipo', KIND_LABEL[airport.kind] || airport.kind),
      // Un sitio de la lista no es un aeropuerto con tráfico: la fila diría
      // «Sin vuelo regular» sobre un CCTE, que es ruido.
      row('Tráfico', esSitio ? null : airport.scheduled ? 'Vuelo regular' : 'Sin vuelo regular'),
      row('ARP', `${airport.lat.toFixed(5)}, ${airport.lon.toFixed(5)}`),
      row('Elevación', airport.elevFt != null ? `${airport.elevFt} ft` : null),
      row('País', airport.country),
    )

    const codigo = esSitio ? airport.name : airportCode(airport)
    const bajada = esSitio ? airport.grupo || airport.name : airport.name

    return (
      `<div class="aerorf-popup">` +
      `<div class="aerorf-popup-title">${escapeHtml(codigo)}</div>` +
      `<div class="aerorf-popup-desc">${escapeHtml(bajada)}</div>` +
      filas.join('') +
      `<div class="aerorf-popup-hint">${
        esSitio
          ? 'Sitio de la lista del operador, no medido por AeroRF.'
          : 'Punto de referencia publicado, no medido por AeroRF.'
      }</div>` +
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
        //
        // Los sitios de la lista no llevan etiqueta permanente: no tienen
        // código corto y el nombre completo (a veces de 40 caracteres) en
        // cada panear convertiría la capa en un muro de texto. Su nombre se
        // lee igual en el tooltip al pasar el mouse.
        if (airport.kind !== 'sitio') {
          marker.bindTooltip(airportCode(airport), {
            permanent: true,
            direction: 'right',
            className: marker.major ? 'aerorf-airport-label' : 'aerorf-airport-label aerorf-airport-label-minor',
            opacity: 0.8,
          })
        }
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

  /** Fit the map to what the layer draws, optionally filtered. */
  fitTo({ country = null } = {}) {
    const points = []
    for (const airport of DIBUJAR) {
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
