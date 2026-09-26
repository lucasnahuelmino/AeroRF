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
