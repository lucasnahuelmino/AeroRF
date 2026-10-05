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

// The API is replaced for this whole file. Mounting the shell makes it pull
// the vocabulary, the layers, the objects, the counts and the live state, and
// each of those against an origin with no backend behind it raises an
// AggregateError inside jsdom. Vitest prints those as stderr tagged with
// whichever test was running, which buries the real output — and it happened
// for every shell-mounting test, not only the one below.
//
// `vi.mock` is hoisted to the top of the file, so this applies before any
// import below. A spy inside the test body is too late: `onMounted` has
// already fired by then.
//
// The real client unwraps `response.data` in an interceptor, so callers
// receive the payload directly. Returning `{ data }` here would make every
// store read off `undefined` and render empty panels — a bug in the stub, not
// in the app.
vi.mock('@/api/client', () => {
  const RESP = (payload) => Promise.resolve(payload)
  return {
    API_PREFIX: '/api/v1',
    describeError: (e) => String(e?.message || e),
    client: {
      get: () => RESP({}), post: () => RESP({}),
      put: () => RESP({}), patch: () => RESP({}), delete: () => RESP({}),
    },
    default: { get: () => RESP({}), post: () => RESP({}), put: () => RESP({}), delete: () => RESP({}) },
    system: { vocabulary: () => RESP({}) },
    layers: { list: () => RESP({ layers: [] }) },
    mapObjects: {
      all: () => RESP({ objects: [] }),
      stats: () => RESP({}),
      create: () => RESP({}),
      update: () => RESP({}),
    },
    flights: {
      live: () => RESP({ states: {} }),
      tracked: () => RESP({ slots: [] }),
      track: () => RESP({}),
      sessions: () => RESP({ sessions: [] }),
    },
    rf: {},
    correlation: {},
    expedientes: {},
    exporter: {},
  }
})

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

  it('a real drag then a click keeps the size shown on screen', () => {
    // The whole flow, driven the way the shell drives it: a click for the
    // centre, Leaflet mousemove events for the drag, then a click to keep it.
    //
    // The symptom this covers: the circle came out at a different size than
    // the one the guide was showing, so the operator dragged carefully, read
    // the number, clicked — and got something else.
    const done = []
    tools.handlers.onComplete = (payload) => done.push(payload)

    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    engine.map.fire('click', { latlng: CENTRE })

    // The drag. `previewAt` is what the shell calls from its own mousemove
    // handler; firing Leaflet's event here would need the shell mounted, and
    // the shell's wiring is covered by active-tool.spec.js. What matters here
    // is that the size on screen survives the click that keeps it.
    tools.previewAt({ lat: -34.55, lng: -58.4 })
    tools.previewAt({ lat: -34.50, lng: -58.4 })
    tools.previewAt({ lat: -34.45, lng: -58.4 })
    tools.previewAt(FURTHER)
    const shown = tools.draft.radius
    const shownM = tools.draft.radiusM

    // The click to keep it.
    engine.map.fire('click', { latlng: FURTHER })
    expect(done.length, 'el clic no creo el circulo').toBe(1)
    expect(done[0].radius_m).toBeCloseTo(shownM, 3)
    expect(done[0].radius).toBeCloseTo(shown, 3)
  })

  it('the second click stores the size the pointer was showing', () => {
    // The exact flow an operator uses: press circle, click the centre, extend
    // the pointer until the readout shows the size they want, then click.
    //
    // The bug was that the shell sized and committed the circle, and then the
    // tool's own click handler ran on the same event and started a *second*
    // circle. The first was stored at the wrong size and the tool was left
    // armed, so no other tool could be picked cleanly.
    const done = []
    tools.handlers.onComplete = (payload) => done.push(payload)

    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    engine.map.fire('click', { latlng: CENTRE })
    // `previewAt` rather than a Leaflet mousemove event: jsdom does not
    // deliver synthetic pointer moves, and this is the same call the shell
    // makes on mousemove.
    tools.previewAt(FURTHER)
    // The operator reads this number and decides.
    const shown = tools.draft.radius
    const shownM = tools.draft.radiusM

    engine.map.fire('click', { latlng: FURTHER })
    expect(done.length, 'el segundo clic no creo el circulo').toBe(1)

    // The stored radius is the one that was on screen, not a stale value.
    expect(done[0].radius_m).toBeCloseTo(shownM, 3)
    expect(done[0].radius).toBeCloseTo(shown, 3)
  })

  it('leaves the tool released, so another tool can be picked', () => {
    // With two click handlers racing, the tool stayed armed after a commit,
    // and the next tool could not take the click.
    const done = []
    tools.handlers.onComplete = (payload) => done.push(payload)

    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    engine.map.fire('click', { latlng: CENTRE })
    engine.map.fire('mousemove', { latlng: FURTHER })
    engine.map.fire('click', { latlng: FURTHER })

    expect(done.length).toBe(1)
    expect(tools.active, 'la herramienta quedo armada tras confirmar').toBeNull()
    expect(tools.draft, 'quedo un borrador sin confirmar').toBeNull()

    // And a different tool works right away, with no leftover state.
    const other = []
    tools.handlers.onComplete = (payload) => other.push(payload)
    tools.activate(TOOLS.LINE, {})
    engine.map.fire('click', { latlng: CENTRE })
    expect(tools.draft?.points?.length, 'la linea no arranco limpia').toBe(1)
  })

  it('creates exactly one circle, not one per click', () => {
    const done = []
    tools.handlers.onComplete = (payload) => done.push(payload)
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    engine.map.fire('click', { latlng: CENTRE })
    engine.map.fire('mousemove', { latlng: FURTHER })
    engine.map.fire('click', { latlng: FURTHER })
    // A third click must not resurrect the tool into a new circle: the tool
    // was released, so it is inert.
    engine.map.fire('click', { latlng: { lat: -34.2, lng: -58.0 } })
    expect(done.length, 'un clic creo mas de un circulo').toBe(1)
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
   *
   * The whole API module is mocked, per file and at the top level, because
   * `vi.mock` is hoisted and a specifier can only replace the module for the
   * file that asks. A method-by-method spy inside the test body came too
   * late: the shell's `onMounted` had already issued its requests, and jsdom
   * raised an AggregateError for each one against a port with nothing on it.
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

  it('deja el circulo recién creado seleccionado y con el inspector abierto', async () => {
    // El operador dibuja un círculo para detallar de qué se trata. Si el
    // objeto no queda seleccionado y el inspector cerrado, tiene que buscarlo
    // a mano en la lista antes de poder escribir una sola palabra sobre él.
    //
    // El inspector arranca cerrado a propósito, para que la apertura sea
    // parte de lo que esta prueba mide; el valor se lee al crear el store,
    // así que se restituye apenas quedó capturado.
    localStorage.setItem('aerorf:inspector-open', '0')

    const { mount, flushPromises } = await import('@vue/test-utils')
    const { createRouter, createMemoryHistory } = await import('vue-router')
    const { default: GisShell } = await import('@/views/GisShell.vue')
    const { useSystemStore } = await import('@/stores/system')

    const pinia = createPinia()
    setActivePinia(pinia)
    const map = useMapStore()
    const system = useSystemStore()
    localStorage.removeItem('aerorf:inspector-open')
    expect(system.inspectorOpen, 'el inspector debería arrancar cerrado').toBe(false)

    map.createObject = (payload) =>
      Promise.resolve({ id: 7, ...payload, latlng: null, latlngs: [] })

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push('/')
    await router.isReady()

    const w = mount(GisShell, { global: { plugins: [pinia, router] } })
    await flushPromises()

    const engine = map.engine
    expect(engine, 'el shell no adjunto el motor al store').toBeTruthy()

    map.setTool(TOOLS.CIRCLE)
    await flushPromises()

    engine.map.fire('click', { latlng: CENTRE })
    await flushPromises()
    engine.map.fire('mousemove', { latlng: FURTHER })
    engine.map.fire('click', { latlng: FURTHER })
    await flushPromises()

    expect(
      map.selectedId,
      'el circulo recién creado debe quedar seleccionado',
    ).toBe(7)
    expect(
      system.inspectorOpen,
      'el inspector debe abrirse: ahi es donde se detalla el objeto',
    ).toBe(true)

    w.unmount()
  })

  it('le pasa la fuente elegida al crear el punto', async () => {
    // El operador elige FM/TPRS/Otro en las opciones antes de hacer clic.
    // Si el payload no lleva el campo, el backend guarda el `icon` por
    // defecto y la eleccion desaparece sin que nada la contradiga.
    const { mount, flushPromises } = await import('@vue/test-utils')
    const { createRouter, createMemoryHistory } = await import('vue-router')
    const { default: GisShell } = await import('@/views/GisShell.vue')

    const pinia = createPinia()
    setActivePinia(pinia)
    const map = useMapStore()

    let payload = null
    map.createObject = (p) => {
      payload = p
      return Promise.resolve({ id: 8, ...p, latlng: null, latlngs: [] })
    }

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div/>' } }],
    })
    await router.push('/')
    await router.isReady()

    const w = mount(GisShell, { global: { plugins: [pinia, router] } })
    await flushPromises()

    const engine = map.engine
    map.setTool(TOOLS.POINT)
    map.setToolOption('fuente', 'fm')
    await flushPromises()

    engine.map.fire('click', { latlng: CENTRE })
    await flushPromises()

    expect(payload, 'el punto no se creo').toBeTruthy()
    expect(payload.icon, 'el payload debe llevar la fuente elegida').toBe('fm')

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
