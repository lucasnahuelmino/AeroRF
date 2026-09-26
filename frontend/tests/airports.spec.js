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
import { AIRPORTS, AIRPORTS_BY_ICAO, findAirport } from '@/data/airports'
import { haversine } from '@/map/geo'
import { MapEngine } from '@/map/MapEngine'

// ─── The data ───────────────────────────────────────────────────────────────

describe('the aerodrome reference data', () => {
  it('is not empty', () => {
    expect(AIRPORTS.length).toBeGreaterThan(40)
  })

  it('has no duplicated ICAO code', () => {
    const seen = new Map()
    for (const a of AIRPORTS) {
      expect(seen.has(a.icao), `ICAO duplicado: ${a.icao}`).toBe(false)
      seen.set(a.icao, a)
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

  it('uses a four-letter ICAO code and a three-letter IATA code', () => {
    for (const a of AIRPORTS) {
      expect(a.icao, `${a.icao} no parece un codigo ICAO`).toMatch(/^[A-Z0-9]{4}$/)
      if (a.iata) expect(a.iata).toMatch(/^[A-Z0-9]{3}$/)
    }
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
    expect(layer.markers.size).toBe(AIRPORTS.length)
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
    layer.setCountries(['AR'])
    const arOnly = new Set([...layer.markers.values()].map((m) => m.airport.country))
    expect(arOnly).toEqual(new Set(['AR']))
    expect(layer.markers.size).toBeLessThan(AIRPORTS.length)

    layer.setCountries([])
    expect(layer.markers.size).toBe(AIRPORTS.length)
  })

  it('reports how many it drew, for the panel counter', () => {
    expect(layer.count).toBe(AIRPORTS.length)
    layer.setCountries(['AR', 'CL'])
    const expected = AIRPORTS.filter((a) => ['AR', 'CL'].includes(a.country)).length
    expect(layer.count).toBe(expected)
  })

  it('labels the symbols as reference data, not as observations', () => {
    // The whole point of separating this layer from the operator's objects.
    const tip = layer.markers.get('SAEZ').getTooltip()
    expect(tip).toBeTruthy()
    expect(tip.getContent()).toContain('referencia')
  })

  it('shows the ICAO code when labels are on, and hides them again', () => {
    layer.setLabels(true)
    expect(layer.markers.get('SAEZ').getTooltip()).toBeTruthy()
    layer.setLabels(false)
    expect(layer.labelsVisible).toBe(false)
  })

  it('fits the map to the aerodromes', () => {
    expect(() => layer.fitTo()).not.toThrow()
    expect(() => layer.fitTo({ country: 'AR' })).not.toThrow()
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
