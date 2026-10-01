/**
 * tests/objects.spec.js
 * ────────────────────
 * Object creation: the translation between the drawing tools and the API.
 *
 * The bug this file exists for
 * ────────────────────────────
 * The tools emit `latlngs` in Leaflet's order, `[[lat, lon], ...]`, because
 * that is what they draw with. The API declares a `geometry` field in
 * GeoJSON's order, `[lon, lat]`. Nothing translated between them, and
 * `latlngs` is not a field the schema declares, so Pydantic dropped it
 * silently.
 *
 * The result was the worst kind of failure: the request **succeeded**. An id
 * came back, a "Creado" notice appeared, and an object with zero points landed
 * in the database. Lines and polygons simply could not be drawn.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// ─── Capture what reaches the API ───────────────────────────────────────────
const sent = []

vi.mock('@/api/client', () => {
  const RESP = (payload) => Promise.resolve(payload)
  const record = (payload) => {
    sent.push(payload)
    // Echo back what the API would return: Leaflet order, plus an id.
    return RESP({
      id: 99,
      type: payload.type,
      name: payload.name || 'sin nombre',
      geometry: payload.geometry || null,
      geometry_type: payload.geometry_type || null,
      latlngs: payload.latlngs || [],
      latlng: null,
      latitude: payload.latitude ?? null,
      longitude: payload.longitude ?? null,
      properties: { layer_name: 'Objetos del usuario' },
      provenance: 'user',
      visible: true,
      locked: false,
      layer: 'user',
      created_at: '2026-09-26T10:00:00',
      updated_at: '2026-09-26T10:00:00',
    })
  }
  return {
    API_PREFIX: '/api/v1',
    default: { get: RESP, post: RESP, put: RESP, delete: RESP },
    describeError: (e) => String(e?.message || e),
    system: { status: RESP({}), config: RESP({}), vocabulary: RESP({}) },
    mapObjects: {
      list: RESP({ count: 0, objects: [] }),
      all: RESP({ count: 0, objects: [] }),
      create: (payload) => record(payload),
      update: (id, payload) => record(payload),
      remove: RESP({ deleted: 1 }),
      setStatus: RESP({}),
      move: RESP({}),
      duplicate: RESP({}),
      near: RESP({ count: 0, results: [] }),
      distances: RESP({ count: 0, results: [] }),
      stats: RESP({ total: 0, by_type: {} }),
      history: RESP([]),
      notes: RESP([]),
      addNote: RESP({}),
      importGeoJson: RESP({ created: [], errors: [] }),
    },
    layers: { list: RESP({ count: 0, layers: [] }), create: RESP({}), update: RESP({}), remove: RESP({}) },
    flights: { tracked: RESP({ count: 0, slots: [] }) },
    correlation: { rfAircraft: RESP({ bands: [] }) },
    exporter: { geojsonUrl: () => '/api/v1/export/geojson', kmlUrl: () => '', csvUrl: () => '' },
  }
})

const { useMapStore } = await import('@/stores/map')

// A line as ToolManager emits it: Leaflet order.
const LINE = {
  type: 'line',
  name: 'Linea',
  latlngs: [[-34.6, -58.4], [-34.5, -58.3], [-34.4, -58.2]],
}

// A polygon as ToolManager emits it: Leaflet order, ring NOT closed.
const POLYGON = {
  type: 'polygon',
  name: 'Poligono',
  latlngs: [[-34.9, -58.9], [-34.8, -58.9], [-34.8, -58.8], [-34.9, -58.8]],
}

describe('object creation reaches the API with real geometry', () => {
  beforeEach(() => {
    sent.length = 0
    setActivePinia(createPinia())
  })

  it('sends a line as a GeoJSON LineString, not as latlngs', async () => {
    await useMapStore().createObject({ ...LINE })
    expect(sent.length).toBe(1)
    const body = sent[0]
    // The field the schema actually declares.
    expect(body.geometry).toBeTruthy()
    expect(body.geometry.type).toBe('LineString')
    expect(body.geometry_type).toBe('LineString')
    // And not the field it silently dropped.
    expect(body.latlngs).toBeUndefined()
  })

  it('swaps the coordinate order, because GeoJSON is [lon, lat]', async () => {
    await useMapStore().createObject({ ...LINE })
    // Input was [[-34.6, -58.4], ...]: latitude first.
    // The API wants [[-58.4, -34.6], ...]: longitude first.
    expect(sent[0].geometry.coordinates[0]).toEqual([-58.4, -34.6])
    expect(sent[0].geometry.coordinates[1]).toEqual([-58.3, -34.5])
    expect(sent[0].geometry.coordinates[2]).toEqual([-58.2, -34.4])
  })

  it('keeps every vertex', async () => {
    await useMapStore().createObject({ ...LINE })
    expect(sent[0].geometry.coordinates).toHaveLength(3)
  })

  it('closes a polygon ring, because GeoJSON requires it', async () => {
    await useMapStore().createObject({ ...POLYGON })
    const body = sent[0]
    expect(body.geometry.type).toBe('Polygon')
    const ring = body.geometry.coordinates[0]
    // A 4-vertex ring becomes 5 positions with the first repeated.
    expect(ring).toHaveLength(5)
    expect(ring[0]).toEqual(ring[ring.length - 1])
    expect(ring[0]).toEqual([-58.9, -34.9])
  })

  it('does not double-close an already closed ring', async () => {
    await useMapStore().createObject({
      type: 'polygon',
      name: 'Ya cerrado',
      latlngs: [[-34.9, -58.9], [-34.8, -58.9], [-34.8, -58.8], [-34.9, -58.9]],
    })
    const ring = sent[0].geometry.coordinates[0]
    expect(ring).toHaveLength(4)
    expect(ring[0]).toEqual(ring[ring.length - 1])
  })

  it('treats a trace the same way as a line', async () => {
    await useMapStore().createObject({ type: 'trace', name: 'Traza', latlngs: [[-34.6, -58.4], [-34.5, -58.3]] })
    expect(sent[0].geometry.type).toBe('LineString')
  })

  it('sends a point as a GeoJSON Point', async () => {
    await useMapStore().createObject({ type: 'point', name: 'Punto', latitude: -34.6, longitude: -58.4 })
    expect(sent[0].geometry).toEqual({ type: 'Point', coordinates: [-58.4, -34.6] })
    expect(sent[0].geometry_type).toBe('Point')
  })

  it('leaves a circle alone: the backend builds the ring from centre and radius', async () => {
    await useMapStore().createObject({
      type: 'circle', name: 'Circulo', latitude: -34.6, longitude: -58.4,
      radius: 20, radius_unit: 'nm', radius_m: 37040,
    })
    // No geometry is invented for a circle; the radius is the truth.
    expect(sent[0].radius_m).toBe(37040)
    expect(sent[0].latlngs).toBeUndefined()
  })

  it('does not mutate the caller payload', async () => {
    // handleToolComplete spreads the same payload into the store afterwards,
    // so mutating it here would corrupt the object's own record.
    const payload = { ...LINE }
    const before = JSON.stringify(payload)
    await useMapStore().createObject(payload)
    expect(JSON.stringify(payload)).toBe(before)
  })

  it('accumulates: creating a second line leaves the first alone', async () => {
    const store = useMapStore()
    await store.createObject({ ...LINE, name: 'Primera' })
    await store.createObject({ ...LINE, name: 'Segunda', latlngs: [[-34.1, -58.1], [-34.0, -58.0]] })
    expect(sent.length).toBe(2)
    expect(sent[0].geometry.coordinates[0]).toEqual([-58.4, -34.6])
    expect(sent[1].geometry.coordinates[0]).toEqual([-58.1, -34.1])
    // Both reached the API as real geometry, each with its own vertices.
    expect(sent[0].geometry.coordinates).toHaveLength(3)
    expect(sent[1].geometry.coordinates).toHaveLength(2)
    expect(sent.every((b) => (b.geometry?.coordinates?.length || 0) > 0)).toBe(true)
  })

  it('translates an update too, not only a create', async () => {
    await useMapStore().updateObject(1, { type: 'line', latlngs: [[-34.6, -58.4], [-34.5, -58.3]] })
    expect(sent[0].geometry.type).toBe('LineString')
    expect(sent[0].latlngs).toBeUndefined()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// The shape the tools actually emit
// ─────────────────────────────────────────────────────────────────────────────
//
// Every test above builds its payload with `latlngs`. That is a real field and
// the translation handles it — and it is the shape **nothing in the application
// produces**.
//
// `draw.js`'s `finish()` emits the vertices as `properties.path` (line, trace,
// measurement) or `properties.ring` (polygon, coverage). The translation read
// only `latlngs`, so for every one of those five tools it took the early return:
// a line, polygon, coverage or trace was saved as a **Point** on its first
// vertex, and a measurement was saved with no geometry at all.
//
// Measured against the running API before the fix: all four came back
// `geometry_type=Point` with one vertex. Circles and radials were fine, because
// they carry a centre and a measurement and the backend builds the ring — which
// is also the only reason they were ever on the map.
//
// So this file was fully green over a feature that did not work. The fixture was
// the problem: it used a plausible-looking key that the real caller never sends,
// which is the same trap as the centre-snap fixture that hid the broken snapping
// until it was measured in the browser.
//
// These tests use the real payloads. If the tools ever rename `path` or `ring`,
// these fail and the tools fail with them, which is the point.
describe('the payload the drawing tools actually emit', () => {
  beforeEach(() => {
    sent.length = 0
    setActivePinia(createPinia())
  })

  it('reads the vertices out of properties.path, as line, trace and measure send them', async () => {
    await useMapStore().createObject({
      type: 'line',
      name: 'Linea',
      latitude: -34.6,
      longitude: -58.4,
      properties: { path: [[-34.6, -58.4], [-34.5, -58.3], [-34.4, -58.2]] },
    })
    expect(sent.length).toBe(1)
    expect(sent[0].geometry.type).toBe('LineString')
    expect(sent[0].geometry.coordinates).toHaveLength(3)
    // Still [lon, lat], the same swap the `latlngs` path does.
    expect(sent[0].geometry.coordinates[0]).toEqual([-58.4, -34.6])
  })

  it('reads the ring out of properties.ring, as polygon and coverage send them', async () => {
    await useMapStore().createObject({
      type: 'polygon',
      name: 'Poligono',
      latitude: -34.9,
      longitude: -58.9,
      properties: { ring: [[-34.9, -58.9], [-34.8, -58.9], [-34.8, -58.8]] },
    })
    expect(sent[0].geometry.type).toBe('Polygon')
    const ring = sent[0].geometry.coordinates[0]
    // The tool sends an open ring; GeoJSON needs it closed.
    expect(ring).toHaveLength(4)
    expect(ring[0]).toEqual(ring[ring.length - 1])
    expect(ring[0]).toEqual([-58.9, -34.9])
  })

  it.each([
    ['line', 'path', 'LineString'],
    ['trace', 'path', 'LineString'],
    ['measurement', 'path', 'LineString'],
    ['polygon', 'ring', 'Polygon'],
    ['coverage', 'ring', 'Polygon'],
  ])('does not downgrade a %s to a point on its first vertex', async (type, key, esperado) => {
    // The failure this guards against is silent: the request succeeded, an id
    // came back and a "Creado" notice appeared, while the stored shape was a
    // single vertex. Asserting the geometry type is what catches it.
    const vertices = [[-34.6, -58.4], [-34.5, -58.3], [-34.4, -58.2]]
    await useMapStore().createObject({
      type,
      latitude: -34.6,
      longitude: -58.4,
      properties: { [key]: vertices },
    })
    expect(sent[0].geometry, `${type} debe llegar con geometria`).toBeTruthy()
    expect(sent[0].geometry.type, `${type} no debe guardarse como Point`).not.toBe('Point')
    expect(sent[0].geometry_type).toBe(esperado)

    // The vertex count, which is where the two GeoJSON shapes differ: a
    // LineString's `coordinates` is the list of positions, while a Polygon's is
    // a list of rings and the positions are one level in. A three-vertex ring
    // becomes four positions because GeoJSON requires it closed.
    const positions =
      esperado === 'Polygon' ? sent[0].geometry.coordinates[0] : sent[0].geometry.coordinates
    expect(positions, `${type}: ${vertices.length} vertices`).toHaveLength(
      esperado === 'Polygon' ? vertices.length + 1 : vertices.length,
    )
    expect(positions[0], `${type}: la primera posicion`).toEqual([-58.4, -34.6])
  })

  it('prefers latlngs when both keys are present', async () => {
    // The two orders can disagree, and `latlngs` is the store's own spelling, so
    // it wins. Asserted so the fallback never quietly takes precedence.
    await useMapStore().createObject({
      type: 'line',
      latlngs: [[-1, -1], [-2, -2]],
      properties: { path: [[-9, -9], [-9, -9], [-9, -9]] },
    })
    expect(sent[0].geometry.coordinates).toHaveLength(2)
    expect(sent[0].geometry.coordinates[0]).toEqual([-1, -1])
  })

  it('still sends a circle as centre plus radius, not as a vertex list', async () => {
    // The fallback must not reach circles: a circle has no `path` and no
    // `ring`, and its truth is the centre and the radius. A Point geometry on
    // the centre is what this write path has always sent and what the engine
    // dispatches on; what must not happen is a LineString or a Polygon.
    await useMapStore().createObject({
      type: 'circle', name: 'Circulo', latitude: -34.6, longitude: -58.4,
      radius: 20, radius_unit: 'nm', radius_m: 37040,
    })
    expect(sent[0].geometry.type).toBe('Point')
    expect(sent[0].radius_m).toBe(37040)
    expect(sent[0].latlngs).toBeUndefined()
  })
})
