/**
 * tests/airports.spec.js
 * ─────────────────────
 * The aerodrome reference layer, and the distance measurement from one.
 *
 * Two things are being protected here.
 *
 * The data must be real. An earlier hand-written version of this file had four
 * duplicated ICAO codes, four duplicated IATA codes, two identical coordinate
 * pairs under different names, and a set of coordinates belonging to no
 * aerodrome at all. Every one of them looked plausible. An operator computing
 * interference protection around a wrong ARP produces a confidently wrong
 * report, so the uniqueness and range checks below are not decoration.
 *
 * The layer must be presentation, not data. The aerodromes are not stored as
 * map objects, so nothing the operator can select, edit or delete refers to
 * them, and no reference point can be mistaken for something they measured.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { AirportLayer, AIRPORT_LAYER_KEY, cardinal } from '@/map/airports'
import {
  AIRPORTS,
  AIRPORTS_BY_ICAO,
  findAirport,
  airportCode,
  isMajor,
} from '@/data/airports'
import { haversine } from '@/map/geo'
import { MapEngine } from '@/map/MapEngine'
import { useAirport } from '@/composables/useAirport'

// ─── The data ───────────────────────────────────────────────────────────────

describe('the aerodrome reference data', () => {
  it('is not empty', () => {
    expect(AIRPORTS.length).toBeGreaterThan(40)
  })

  it('has no duplicated identifier', () => {
    // `key`, not `icao`: some aerodromes in service publish no ICAO code at
    // all, and indexing on it would put more than one of them under the same
    // value. San Fernando is the one in this list.
    const seen = new Map()
    for (const a of AIRPORTS) {
      expect(a.key, 'un aerodromo sin identificador').toBeTruthy()
      expect(seen.has(a.key), `identificador duplicado: ${a.key}`).toBe(false)
      seen.set(a.key, a)
    }
  })

  it('has no duplicated ICAO code', () => {
    const seen = new Set()
    for (const a of AIRPORTS) {
      if (!a.icao) continue
      expect(seen.has(a.icao), `ICAO duplicado: ${a.icao}`).toBe(false)
      seen.add(a.icao)
    }
  })

  it('has no duplicated IATA code', () => {
    const seen = new Set()
    for (const a of AIRPORTS) {
      if (!a.iata) continue
      expect(seen.has(a.iata), `IATA duplicado: ${a.iata}`).toBe(false)
      seen.add(a.iata)
    }
  })

  it('has no two aerodromes at the same coordinates', () => {
    // Two names on one point means one of them is wrong.
    const seen = new Map()
    for (const a of AIRPORTS) {
      const key = `${a.lat},${a.lon}`
      expect(seen.has(key), `${a.icao} comparte coordenadas con ${seen.get(key)}`).toBe(false)
      seen.set(key, a.icao)
    }
  })

  it('has every coordinate in range', () => {
    for (const a of AIRPORTS) {
      expect(a.lat, `${a.icao} lat`).toBeGreaterThanOrEqual(-90)
      expect(a.lat, `${a.icao} lat`).toBeLessThanOrEqual(90)
      expect(a.lon, `${a.icao} lon`).toBeGreaterThanOrEqual(-180)
      expect(a.lon, `${a.icao} lon`).toBeLessThanOrEqual(180)
    }
  })

  it('uses a four-letter code and a three-letter IATA code', () => {
    for (const a of AIRPORTS) {
      // An aerodrome with no ICAO still has to carry a four-letter identifier
      // of some kind, or there is nothing to look it up or label it with. The
      // two in this list that have no ICAO both publish a gps_code.
      const four = a.icao || a.gps
      expect(four, `${a.key} sin codigo de cuatro letras`).toMatch(/^[A-Z0-9]{4}$/)
      if (a.icao) expect(a.icao).toMatch(/^[A-Z0-9]{4}$/)
      if (a.iata) expect(a.iata).toMatch(/^[A-Z0-9]{3}$/)
    }
  })

  it('keeps the accents in the published names', () => {
    // The generator used to run every name through
    // `name.encode("ascii", "ignore")`, on the theory that the names were for a
    // console. They are not: they are read in the browser, and every accented
    // aerodrome in the country came out with a hole where the vowel belonged —
    // "Martn Miguel de Gemes", "Presidente Pern".
    const salta = AIRPORTS.find((a) => a.icao === 'SASA')
    expect(salta?.name, 'el nombre de SASA debe conservar los acentos')
      .toBe('Martín Miguel de Güemes International Airport')
    const perón = AIRPORTS.find((a) => a.icao === 'SAZN')
    expect(perón?.name).toContain('Perón')
  })

  it('carries the two Buenos Aires fields the operator asked for', () => {
    // El Palomar and San Fernando. The first publishes its code as SADP with
    // IATA EPA; the second publishes neither an ICAO nor an IATA code, only a
    // gps_code and a local one. Both are looked up by either.
    const palomar = findAirport('SADP')
    expect(palomar?.name).toBe('El Palomar Airport')
    expect(palomar?.iata).toBe('EPA')

    const fernando = findAirport('SADF')
    expect(fernando?.name).toBe('San Fernando Airport')
    expect(fernando?.icao, 'la fuente no publica ICAO para San Fernando').toBeNull()
    expect(fernando?.local).toBe('FDO')
    // Reachable by the local code too, which is how it is published in the
    // Argentine AIP.
    expect(findAirport('FDO')?.key).toBe('SADF')
  })

  it('carries every Argentine aerodrome the source calls a hub or a scheduled field', () => {
    // The rule the selection follows, asserted so it cannot quietly shrink:
    // every Argentine airport the source types medium_airport, or
    // small_airport with scheduled service, is present. Jujuy was missing
    // before this, and it is a large airport with a scheduled service.
    const required = ['SASJ', 'SADP', 'SADL', 'SANE', 'SAVH', 'SAVN', 'SAWR', 'SAWT']
    for (const code of required) {
      expect(findAirport(code), `falta el aeropuerto ${code}`).toBeTruthy()
    }
  })

  it('labels with the IATA, which is the code an operator types', () => {
    expect(airportCode(AIRPORTS_BY_ICAO.get('saez'))).toBe('EZE')
    expect(airportCode(AIRPORTS_BY_ICAO.get('sabe'))).toBe('AEP')
    // No IATA published: falls through to the ICAO rather than to nothing.
    const sinIata = AIRPORTS.find((a) => !a.iata)
    expect(airportCode(sinIata), 'un aerodromo sin IATA igual debe tener etiqueta')
      .toBeTruthy()
  })

  it('tells the major fields from the minor ones, for the two symbol colours', () => {
    const eze = AIRPORTS_BY_ICAO.get('saez')
    expect(isMajor(eze)).toBe(true)
    // A small aerodrome with no scheduled service is the minor family.
    const menor = AIRPORTS.find(
      (a) => a.kind === 'small_airport' && !a.scheduled,
    )
    expect(menor, 'debe haber al menos un aerodromo menor en la lista').toBeTruthy()
    expect(isMajor(menor)).toBe(false)
  })

  it('carries a name and a country for every aerodrome', () => {
    for (const a of AIRPORTS) {
      expect(a.name, `${a.icao} sin nombre`).toBeTruthy()
      expect(a.country, `${a.icao} sin pais`).toMatch(/^[A-Z]{2}$/)
    }
  })

  it('covers the countries that matter for Argentine airspace', () => {
    // ENACOM work spans the FIR, so a layer with only Argentina on it would
    // be missing exactly the cases that cross a border.
    const countries = new Set(AIRPORTS.map((a) => a.country))
    for (const cc of ['AR', 'UY', 'PY', 'CL', 'BR']) {
      expect(countries.has(cc), `falta ${cc}`).toBe(true)
    }
  })

  it('places the two Buenos Aires fields at different points', () => {
    // SAEZ and SABE are two kilometres apart. Equal coordinates would mean
    // one of them was copied from the other, which is a real bug that was
    // present in the first draft of this file.
    const eze = AIRPORTS_BY_ICAO.get('saez')
    const aeroparque = AIRPORTS_BY_ICAO.get('sabe')
    expect(eze).toBeTruthy()
    expect(aeroparque).toBeTruthy()
    expect(haversine(eze.lat, eze.lon, aeroparque.lat, aeroparque.lon)).toBeGreaterThan(1000)
  })

  it('resolves by ICAO and by IATA, case-insensitively', () => {
    expect(findAirport('SAEZ')?.icao).toBe('SAEZ')
    expect(findAirport('saez')?.icao).toBe('SAEZ')
    expect(findAirport('EZE')?.icao).toBe('SAEZ')
    expect(findAirport('eze')?.icao).toBe('SAEZ')
  })

  it('returns null for something that is not an airport', () => {
    expect(findAirport('XXXX')).toBeNull()
    expect(findAirport('')).toBeNull()
    expect(findAirport(null)).toBeNull()
    // Too short to be either code: rejected rather than matched loosely.
    expect(findAirport('SA')).toBeNull()
  })
})

// ─── The layer on the map ───────────────────────────────────────────────────

describe('AirportLayer on the map', () => {
  let container
  let engine
  let layer

  beforeEach(() => {
    container = document.createElement('div')
    container.id = 'map-airports-test'
    document.body.appendChild(container)
    engine = new MapEngine({ container: 'map-airports-test' })
    engine.init()
    layer = new AirportLayer(engine).init()
  })

  afterEach(() => {
    layer?.destroy()
    engine?.destroy()
    container?.remove()
  })

  it('draws every aerodrome into the airports category', () => {
    // Lo que la capa dibuja es la unión: lo publicado, más los sitios de la
    // lista del operador que no caen junto a un aeropuerto publicado (≤ 2 km,
    // la misma regla que usa map/airports.js). Un EAVA o un CCTE no existe en
    // el archivo publicado, y sin sumarlo la mitad de su lista no aparece.
    const sitios = useAirport().airport.flatMap((g) => g.options)
    const sueltos = sitios.filter(
      (s) => !AIRPORTS.some((a) => haversine(a.lat, a.lon, s.latitude, s.longitude) <= 2000),
    )
    expect(layer.markers.size).toBe(AIRPORTS.length + sueltos.length)
    expect(engine.categoryLayers.has(AIRPORT_LAYER_KEY)).toBe(true)
  })

  it('starts hidden, so it never appears without the operator asking', () => {
    expect(layer.visible).toBe(false)
  })

  it('can be switched on and off, which is the point of a layer', () => {
    layer.setVisible(true)
    expect(layer.visible).toBe(true)
    layer.setVisible(false)
    expect(layer.visible).toBe(false)
  })

  it('filters by country, and an empty filter means all of them', () => {
    // Antes la cuenta se comparaba contra el archivo publicado; ahora la capa
    // dibuja también los sitios del operador (todos argentinos), así que lo
    // que se protege es lo mismo: el filtro AR deja todo lo argentino y
    // quita lo extranjero, y el filtro vacío devuelve lo que había.
    const total = layer.count
    layer.setCountries(['AR'])
    const arOnly = new Set([...layer.markers.values()].map((m) => m.airport.country))
    expect(arOnly).toEqual(new Set(['AR']))
    expect(layer.count).toBeLessThan(total)

    layer.setCountries([])
    expect(layer.count).toBe(total)
  })

  it('reports how many it drew, for the panel counter', () => {
    const sitios = useAirport().airport.flatMap((g) => g.options)
    const sueltos = sitios.filter(
      (s) => !AIRPORTS.some((a) => haversine(a.lat, a.lon, s.latitude, s.longitude) <= 2000),
    )
    expect(layer.count).toBe(AIRPORTS.length + sueltos.length)
    // Los sitios sueltos son todos argentinos, por eso sólo cambian el total
    // cuando el filtro incluye AR.
    layer.setCountries(['AR', 'CL'])
    const esperado =
      AIRPORTS.filter((a) => ['AR', 'CL'].includes(a.country)).length + sueltos.length
    expect(layer.count).toBe(esperado)
  })

  it('labels the symbols as reference data, not as observations', () => {
    // The whole point of separating this layer from the operator's objects.
    const tip = layer.markers.get('SAEZ').getTooltip()
    expect(tip).toBeTruthy()
    expect(tip.getContent()).toContain('referencia')
  })

  it('shows the short code when labels are on, and hides them again', () => {
    layer.setLabels(true)
    const eze = layer.markers.get('SAEZ')
    expect(eze.getTooltip()).toBeTruthy()
    // The permanent label is the IATA, not the ICAO: the operator says EZE.
    expect(eze.getTooltip().getContent()).toContain('EZE')
    layer.setLabels(false)
    expect(layer.labelsVisible).toBe(false)
  })

  it('draws the minor aerodromes differently from the major ones', () => {
    // Two symbol families, so a regional strip does not disappear under a hub
    // and the operator can tell at a glance which is which. La familia ahora
    // es el tamaño del icono de avión, no el color del círculo: el círculo
    // quedó para lo que no es aeródromo.
    const major = layer.markers.get('SAEZ')
    const minor = AIRPORTS.find((a) => !isMajor(a) && a.kind !== 'heliport')
    const minorMarker = layer.markers.get(minor.key)
    expect(minorMarker, 'el aeropuerto menor debe estar dibujado').toBeTruthy()
    expect(major.options.icon, 'ambos son marcadores de imagen').toBeTruthy()
    expect(minorMarker.options.icon, 'el menor también lleva icono').toBeTruthy()
    expect(
      major.options.icon.options.iconSize[0],
      'el tamaño distingue las dos familias',
    ).toBeGreaterThan(minorMarker.options.icon.options.iconSize[0])
  })

  it('labels an aerodrome that has no ICAO code at all', () => {
    // San Fernando. Keyed on `key`, so it is reachable and not filed under
    // `null` together with anything else.
    const fernando = layer.markers.get('SADF')
    expect(fernando, 'San Fernando debe estar en el mapa').toBeTruthy()
    expect(fernando.airport.name).toBe('San Fernando Airport')
    layer.setLabels(true)
    expect(fernando.getTooltip().getContent()).toBeTruthy()
  })

  it('fits the map to the aerodromes', () => {
    expect(() => layer.fitTo()).not.toThrow()
    expect(() => layer.fitTo({ country: 'AR' })).not.toThrow()
  })
})

// ─── La lista del operador en el mapa ───────────────────────────────────────

/**
 * El composable `useAirport` es la lista que el operador cargó para ver en el
 * mapa (aeropuertos, sitios EAVA/ACC, CCTE, aeroclubs). La capa la dibuja
 * **además** de lo publicado: nada de lo que ya estaba se pierde, y un sitio
 * que coincide con un aeropuerto publicado se dibuja una sola vez.
 *
 * El icono vive en `public/iconos/aeropuerto.svg`: el marcador sólo nombra la
 * ruta, así que cambiar la imagen es reemplazar el archivo.
 */
describe('la lista del operador en el mapa', () => {
  let container
  let engine
  let layer

  beforeEach(() => {
    container = document.createElement('div')
    container.id = 'map-airports-sitios'
    document.body.appendChild(container)
    engine = new MapEngine({ container: 'map-airports-sitios' })
    engine.init()
    layer = new AirportLayer(engine).init()
  })

  afterEach(() => {
    layer?.destroy()
    engine?.destroy()
    container?.remove()
  })

  it('dibuja los sitios de la lista que no son aeropuertos publicados', () => {
    // El CCTE CABA está a más de 6 km de cualquier aeropuerto publicado: es
    // un sitio de la lista, no un aeródromo. Sin esto la capa dibuja sólo lo
    // del archivo publicado y esos sitios no aparecen nunca.
    expect(
      layer.markers.has('OTRO - CCTE CABA'),
      'el sitio de la lista debe estar en el mapa',
    ).toBe(true)
    // Y un sitio que sí coincide con un aeropuerto publicado se dibuja con
    // ese aeropuerto (una sola vez), y el popup lleva todos los que caen
    // ahí: SAAV tiene «SANTA FE» y «EAVA SAUCE VIEJO» a la vez.
    expect(layer.markers.has('EZEIZA - EAVA SAUCE VIEJO')).toBe(false)
    expect(layer.markers.get('SAAV')?.airport.sitios).toEqual([
      'SANTA FE',
      'EAVA SAUCE VIEJO',
    ])
  })

  it('dibuja cada aeropuerto con el icono de avión, por la ruta reemplazable', () => {
    const eze = layer.markers.get('SAEZ')
    expect(eze, 'EZEIZA debe seguir dibujado').toBeTruthy()
    const html = eze.options.icon?.options?.html
    expect(html, 'el aeropuerto debe ser un marcador de imagen, no un círculo').toBeTruthy()
    expect(html).toContain('/iconos/aeropuerto.svg')
  })

  it('tiene el archivo del icono en public/iconos para poder reemplazarlo', async () => {
    // Ruta relativa al cwd: vitest corre desde `frontend/`, que es de donde
    // el navegador serviría el archivo.
    const fs = await import('node:fs')
    const { resolve } = await import('node:path')
    const archivo = resolve('public/iconos/aeropuerto.svg')
    expect(fs.existsSync(archivo), 'falta public/iconos/aeropuerto.svg').toBe(true)
  })

  it('la lista del operador no tiene valores duplicados ni coordenadas fuera de rango', () => {
    // La advertencia del encabezado de este archivo vale también para la
    // lista cargada a mano: un identificador repetido o una coordenada mal
    // copiada se ve exactamente igual que un dato válido.
    const sitios = useAirport().airport.flatMap((g) => g.options)
    expect(sitios.length).toBeGreaterThan(50)
    const vistos = new Set()
    for (const s of sitios) {
      expect(s.value, 'sitio sin identificador').toBeTruthy()
      expect(vistos.has(s.value), `identificador duplicado: ${s.value}`).toBe(false)
      vistos.add(s.value)
      expect(s.latitude, `${s.value} lat`).toBeGreaterThanOrEqual(-90)
      expect(s.latitude, `${s.value} lat`).toBeLessThanOrEqual(90)
      expect(s.longitude, `${s.value} lon`).toBeGreaterThanOrEqual(-180)
      expect(s.longitude, `${s.value} lon`).toBeLessThanOrEqual(180)
    }
  })
})

// ─── Measuring from an aerodrome ────────────────────────────────────────────

describe('measuring from an aerodrome', () => {
  let container
  let engine
  let layer

  beforeEach(() => {
    container = document.createElement('div')
    container.id = 'map-airport-measure'
    document.body.appendChild(container)
    engine = new MapEngine({ container: 'map-airport-measure' })
    engine.init()
    layer = new AirportLayer(engine).init()
  })

  afterEach(() => {
    layer?.destroy()
    engine?.destroy()
    container?.remove()
  })

  it('measures in metres, kilometres and nautical miles, consistently', () => {
    // EZE to Aeroparque: about 31 km, north-north-east. Computed
    // independently, not copied from the code under test.
    const r = layer.measureFrom('SAEZ', -34.559419, -58.415536)
    expect(r).toBeTruthy()
    expect(r.airport.icao).toBe('SAEZ')
    expect(r.km).toBeCloseTo(31.2, 0)
    // The three units must describe the same distance.
    expect(r.km * 1000).toBeCloseTo(r.metres, 3)
    expect(r.nm * 1852).toBeCloseTo(r.metres, 3)
  })

  it('agrees with the shared geodesy, because it uses it', () => {
    const eze = AIRPORTS_BY_ICAO.get('saez')
    const r = layer.measureFrom('SAEZ', -34.2, -58.0)
    expect(r.metres).toBeCloseTo(haversine(eze.lat, eze.lon, -34.2, -58.0), 6)
  })

  it('reports the bearing from the aerodrome to the point', () => {
    // From EZE to Aeroparque the great circle runs north-north-east, about
    // 21 degrees. Checking the value, not just its range, catches a swapped
    // argument that a range check would pass.
    const r = layer.measureFrom('SAEZ', -34.559419, -58.415536)
    expect(r.bearing).toBeCloseTo(20.7, 0)
    expect(r.bearing_cardinal).toBe('NNE')
  })

  it('is zero at the aerodrome itself, without pretending otherwise', () => {
    const eze = AIRPORTS_BY_ICAO.get('saez')
    const r = layer.measureFrom('SAEZ', eze.lat, eze.lon)
    expect(r.metres).toBeCloseTo(0, 3)
  })

  it('accepts an IATA code as well as an ICAO one', () => {
    expect(layer.measureFrom('EZE', -34.2, -58.0).airport.icao).toBe('SAEZ')
  })

  it('returns null for an unknown code instead of guessing', () => {
    expect(layer.measureFrom('ZZZZ', -34.2, -58.0)).toBeNull()
    expect(layer.measureFrom('', -34.2, -58.0)).toBeNull()
  })

  it('returns null when the destination is missing', () => {
    expect(layer.measureFrom('SAEZ', null, null)).toBeNull()
  })

  it('lists the aerodromes within a radius, nearest first', () => {
    const near = layer.within(-34.8222, -58.5358, 50)
    expect(near.length).toBeGreaterThan(0)
    // Sorted by distance, so the first is the closest.
    for (let i = 1; i < near.length; i += 1) {
      expect(near[i].metres).toBeGreaterThanOrEqual(near[i - 1].metres)
    }
    for (const hit of near) {
      expect(hit.nm).toBeLessThanOrEqual(50)
    }
  })

  it('draws the distance line and can take it away again', () => {
    const result = layer.measureFrom('SAEZ', -34.5, -58.4)
    const line = layer.drawMeasure('airport-distance', result, [-34.5, -58.4])
    expect(line).toBeTruthy()
    expect(engine.map.hasLayer(line)).toBe(true)
    layer.removeMeasure('airport-distance')
    expect(engine.map.hasLayer(line)).toBe(false)
  })

  it('refuses to draw a line to a coordinate that is not a number', () => {
    const result = layer.measureFrom('SAEZ', -34.5, -58.4)
    expect(layer.drawMeasure('k', result, ['nope', null])).toBeNull()
  })
})

// ─── Compass names ──────────────────────────────────────────────────────────

describe('compass names', () => {
  it('names the cardinal points', () => {
    expect(cardinal(0)).toBe('N')
    expect(cardinal(90)).toBe('E')
    expect(cardinal(180)).toBe('S')
    expect(cardinal(270)).toBe('W')
  })

  it('normalises a negative azimuth instead of failing', () => {
    // The same divergence that made the two languages disagree: -90 wraps to
    // 270, which is west. If the normalisation were dropped, -90 would index
    // out of the table and every negative bearing would come back undefined.
    expect(cardinal(-90)).toBe('W')
    expect(cardinal(450)).toBe('E')
    expect(cardinal(-180)).toBe('S')
  })
})
