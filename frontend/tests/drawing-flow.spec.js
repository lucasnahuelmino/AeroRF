/**
 * tests/drawing-flow.spec.js
 * ──────────────────────────
 * The circle and measurement flows, end to end through the engines.
 *
 * Three defects, all reported from the same session:
 *
 * 1. A radius typed in the options panel was ignored, because the tool
 *    snapshotted its options at activation and the panel's later change never
 *    reached it.
 * 2. While sizing a circle nothing showed the radius. The tooltip lived on
 *    the ring, and a ring cannot be hovered mid-drag, so the operator extended
 *    the pointer with no number at all.
 * 3. A circle could not be committed by clicking. Every click was routed to
 *    the preview, so the only way to finish was Enter, and an operator who
 *    clicked twice to adjust the size ended up with nothing on the map.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { MapEngine } from '@/map/MapEngine'
import { ToolManager, TOOLS } from '@/map/draw'
import { MeasureEngine } from '@/map/measure'
import { useMapStore } from '@/stores/map'
import { createPinia, setActivePinia } from 'pinia'

let container
let engine
let tools

beforeEach(() => {
  container = document.createElement('div')
  container.id = 'map-draw-flow'
  document.body.appendChild(container)
  engine = new MapEngine({ container: 'map-draw-flow' })
  engine.init()
  tools = new ToolManager(engine, {})
  // The shell suppresses Leaflet's double-click zoom while drawing.
  engine.suppressClicks(false)
})

afterEach(() => {
  tools?.deactivate()
  engine?.destroy()
  container?.remove()
})

const CENTRE = { lat: -34.6, lng: -58.4 }
const FURTHER = { lat: -34.4, lng: -58.4 }

describe('a typed radius reaches the tool', () => {
  it('uses the radius given when the tool was activated', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    engine.map.fire('click', { latlng: CENTRE })
    const done = tools.finish()
    expect(done.type).toBe('circle')
    // 20 NM is 37040 m exactly.
    expect(done.radius_m).toBeCloseTo(37_040, -2)
    expect(done.radius_unit).toBe('nm')
  })

  it('picks up a radius changed after the tool was activated', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5 })
    engine.map.fire('click', { latlng: CENTRE })

    // The operator then types 50 into the options panel.
    tools.setOptions({ radius: 50 })
    // The in-progress shape is not resized under their pointer.
    expect(tools.draft.radius).toBe(5)

    // The next shape uses the new value.
    const done = tools.finish()
    expect(done.radius_m).toBeCloseTo(5 * 1852, -2)

    tools.activate(TOOLS.CIRCLE, tools.options)
    engine.map.fire('click', { latlng: CENTRE })
    const next = tools.finish()
    expect(next.radius_m).toBeCloseTo(50 * 1852, -2)
  })

  it('honours a unit change too', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'km', radius: 37.04 })
    engine.map.fire('click', { latlng: CENTRE })
    const done = tools.finish()
    expect(done.radius_m).toBeCloseTo(37_040, -1)
    expect(done.radius_unit).toBe('km')
  })

  it('reaches the tool through the store, as the panel uses it', () => {
    // The panel calls `mapStore.toolManager.setOptions(...)`, so the store has
    // to hand back the live manager. If it returned a copy the operator's
    // radius would go nowhere.
    setActivePinia(createPinia())
    const map = useMapStore()
    map.toolManager = tools
    map.setToolOption('radius', 42)
    map.toolManager.setOptions({ radius: map.toolOptions.radius })

    tools.activate(TOOLS.CIRCLE, tools.options)
    engine.map.fire('click', { latlng: CENTRE })
    const done = tools.finish()
    expect(done.radius_m).toBeCloseTo(42 * 1852, -2)
  })
})

describe('sizing a circle shows the radius', () => {
  it('draws a guide from the centre to the pointer, labelled', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    engine.map.fire('click', { latlng: CENTRE })
    tools.previewAt(FURTHER)

    // The ring is on the map.
    const ring = engine._draftLayers.get('circle')
    expect(ring, 'no se dibujo el circulo').toBeTruthy()
    // And so is the guide that reports the radius.
    const edge = engine._draftLayers.get('edge')
    expect(edge, 'no se dibujo la guia del radio').toBeTruthy()
  })

  it('the label carries the radius in the operator unit', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    engine.map.fire('click', { latlng: CENTRE })
    tools.previewAt(FURTHER)

    const edge = engine._draftLayers.get('edge')
    const parts = edge.getLayers ? edge.getLayers() : []
    expect(parts.length).toBeGreaterThan(0)
    // 0.2 degrees of latitude is about 22 km, so about 12 NM.
    expect(tools.draft.radius).toBeGreaterThan(8)
    expect(tools.draft.radius).toBeLessThan(16)
    expect(tools.draft.unit).toBe('nm')
  })

  it('drops the guide once the circle is committed', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    engine.map.fire('click', { latlng: CENTRE })
    tools.previewAt(FURTHER)
    expect(engine._draftLayers.get('edge')).toBeTruthy()

    tools.finish()
    // A committed circle is an object on the map, not a shape being sized.
    expect(engine._draftLayers.get('edge')).toBeFalsy()
  })

  it('has no guide before the pointer has moved', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    engine.map.fire('click', { latlng: CENTRE })
    // There is no "here" yet, so nothing to draw a line to.
    expect(engine._draftLayers.get('edge')).toBeFalsy()
  })
})

describe('committing a circle by clicking', () => {
  it('the first click places the centre, the second commits', () => {
    const done = []
    tools.handlers.onComplete = (payload) => done.push(payload)

    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    // First click: the centre.
    engine.map.fire('click', { latlng: CENTRE })
    expect(done.length, 'el primer clic no debe crear el objeto').toBe(0)
    expect(tools.draft).toBeTruthy()

    // Sizing moves the pointer.
    tools.previewAt(FURTHER)
    // Second click: the decision to keep it.
    tools.previewAt(FURTHER)
    // Read the radius before finishing, because finishing clears the draft.
    const radiusM = tools.draft.radiusM
    tools.finish()

    expect(done.length, 'el segundo clic debio crear el objeto').toBe(1)
    expect(done[0].type).toBe('circle')
    expect(done[0].latitude).toBeCloseTo(-34.6, 5)
    // The stored radius is the one the pointer was at.
    expect(done[0].radius_m).toBeCloseTo(radiusM, 5)
  })

  it('leaves the map clean, ready for the next circle', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    engine.map.fire('click', { latlng: CENTRE })
    tools.previewAt(FURTHER)
    tools.finish()
    // No draft left over: the object is in the store, not in a draft layer.
    expect(tools.draft).toBeNull()
    expect(engine._draftLayers.get('circle')).toBeFalsy()
  })

  it('the same holds for a radial', () => {
    const done = []
    tools.handlers.onComplete = (payload) => done.push(payload)
    tools.activate(TOOLS.RADIAL, { unit: 'nm', length: 30, azimuth: 135 })
    engine.map.fire('click', { latlng: CENTRE })
    expect(done.length).toBe(0)
    tools.previewAt({ lat: -34.5, lng: -58.3 })
    tools.finish()
    expect(done.length).toBe(1)
    expect(done[0].type).toBe('radial')
  })

  it('Escape still abandons a circle without creating anything', () => {
    const done = []
    tools.handlers.onComplete = (payload) => done.push(payload)
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    engine.map.fire('click', { latlng: CENTRE })
    tools.previewAt(FURTHER)
    tools.cancel()
    expect(done.length, 'ESC no debe crear el objeto').toBe(0)
  })
})

describe('the shell wires the clicks the way the flow needs', () => {
  /**
   * The control that failed.
   *
   * The bug was in GisShell, not in ToolManager: every click was routed to
   * `previewAt`, so the second click sized the shape again instead of
   * committing it, and nothing was ever stored. A test driving ToolManager
   * directly passed cleanly against the broken shell, because the shell is
   * what decides what a click means.
   *
   * So this one mounts the shell and clicks on the real map.
   */
  it('commits a circle on the second click, through the shell', async () => {
    const { mount, flushPromises } = await import('@vue/test-utils')
    const { createRouter, createMemoryHistory } = await import('vue-router')
    const { default: GisShell } = await import('@/views/GisShell.vue')

    const pinia = createPinia()
    setActivePinia(pinia)
    const map = useMapStore()

    // Record what the shell would persist.
    const created = []
    const realCreate = map.createObject
    map.createObject = (payload) => {
      created.push(payload)
      return Promise.resolve({ id: 1, ...payload, latlng: null, latlngs: [] })
    }

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push('/')
    await router.isReady()

    const w = mount(GisShell, { global: { plugins: [pinia, router] } })
    await flushPromises()

    const mapEl = w.find('.gis-map')
    const shellMap = mapEl.element._leaflet_id
      ? null
      : null
    // The engine is reachable through the store the shell attached it to.
    const engine = map.engine
    expect(engine, 'el shell no adjunto el motor al store').toBeTruthy()

    map.setTool(TOOLS.CIRCLE)
    await flushPromises()

    // First click: the centre. Nothing stored yet.
    engine.map.fire('click', { latlng: CENTRE })
    await flushPromises()
    expect(created.length, 'el primer clic no debe crear nada').toBe(0)

    // Size it, then click again: the decision to keep it.
    engine.map.fire('mousemove', { latlng: FURTHER })
    engine.map.fire('click', { latlng: FURTHER })
    await flushPromises()

    expect(
      created.length,
      'el segundo clic debe crear el circulo: el operador se queda sin nada en el mapa',
    ).toBe(1)
    expect(created[0].type).toBe('circle')

    map.createObject = realCreate
    w.unmount()
  })
})

describe('measuring from a point to the cursor', () => {
  let measure

  beforeEach(() => {
    measure = new MeasureEngine(engine, {})
  })

  afterEach(() => {
    measure?.stop()
  })

  it('anchors on the object and previews the distance to the pointer', () => {
    measure.fromOrigin({ lat: -34.6, lng: -58.4 }, 'Fuente A')
    expect(measure.points).toEqual([[-34.6, -58.4]])

    measure.previewToPoint({ lat: -34.4, lng: -58.4 })
    // The cursor line is drawn, but nothing was committed.
    expect(engine._draftLayers.get('measure-cursor')).toBeTruthy()
    expect(measure.points.length, 'el puntero no debe agregar puntos').toBe(1)
  })

  it('commits the distance on click', () => {
    measure.fromOrigin({ lat: -34.6, lng: -58.4 }, 'Fuente A')
    measure.previewToPoint({ lat: -34.4, lng: -58.4 })
    measure.addPoint({ lat: -34.4, lng: -58.4 })

    expect(measure.points.length).toBe(2)
    // 0.2 degrees of latitude is about 22 km.
    const m = measure.current()
    expect(m.total_km).toBeGreaterThan(20)
    expect(m.total_km).toBeLessThan(24)
    expect(m.total_nm).toBeGreaterThan(10)
  })

  it('clears the preview when the measurement stops', () => {
    measure.fromOrigin({ lat: -34.6, lng: -58.4 })
    measure.previewToPoint({ lat: -34.4, lng: -58.4 })
    expect(engine._draftLayers.get('measure-cursor')).toBeTruthy()

    measure.stop()
    // A stale dashed line following the pointer after a discard is a bug the
    // operator would read as a second measurement.
    expect(engine._draftLayers.get('measure-cursor')).toBeFalsy()
    expect(measure.previewTo).toBeNull()
  })

  it('can be saved as an object, like a point', () => {
    measure.fromOrigin({ lat: -34.6, lng: -58.4 })
    measure.addPoint({ lat: -34.4, lng: -58.4 })
    const payload = measure.toObjectPayload('Medición fuente a pista')
    expect(payload).toBeTruthy()
    expect(payload.type).toBe('measurement')
    expect(payload.measurement.total_km).toBeGreaterThan(20)
  })

  it('will not save a measurement with only one point', () => {
    measure.fromOrigin({ lat: -34.6, lng: -58.4 })
    // A single point is a position, not a distance.
    expect(measure.toObjectPayload()).toBeNull()
  })
})
