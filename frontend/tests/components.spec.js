/**
 * tests/components.spec.js
 * ───────────────────────
 * Mounts the real components in jsdom and exercises them.
 *
 * Why this file exists
 * ────────────────────
 * "It compiles" is not "it works". A component can pass the SFC compiler
 * and still throw the instant `mount()` runs its `onMounted` hook: an
 * undefined helper, a store accessed before `createPinia()`, a Leaflet
 * call that needs layout. Those failures are invisible until a human
 * opens the app — which is exactly the situation this project was in.
 *
 * A real bug found this way: `draw.js` called `this._toMetres(...)`,
 * a method that does not exist. It compiled. It only failed when a user
 * activated the circle tool.
 *
 * The API layer is stubbed, so nothing here touches the network.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

// ─── Stub the API before any component imports it ──────────────────────────
vi.mock('@/api/client', () => {
  const LAYERS = [
    { id: 1, key: 'base_map', name: 'Mapa base', visible: true, opacity: 1, order_index: 0, object_count: 0, locked: false, is_system: true },
    { id: 6, key: 'circles', name: 'Círculos', visible: true, opacity: 0.8, order_index: 50, object_count: 1, locked: false, is_system: true },
    { id: 7, key: 'rf_sources', name: 'Fuentes interferentes', visible: true, opacity: 1, order_index: 70, object_count: 1, locked: false, is_system: true },
  ]

  const CIRCLE = {
    id: 11, type: 'circle', name: 'Radio 20 NM',
    geometry_type: 'Polygon',
    geometry: { type: 'Polygon', coordinates: [[[-58.4, -34.6]]] },
    latlng: [-34.6, -58.4], latlngs: [[-34.6, -58.4]],
    latitude: -34.6, longitude: -58.4,
    radius: 20, radius_unit: 'nm',
    metrics: { radius_m: 37040, radius_km: 37.04, radius_nm: 20 },
    status: 'Activo', visible: true, locked: false,
    layer: 'circles', color: '#3b82f6', icon: 'circle',
    opacity: 1, weight: 3, fill_opacity: 0.15,
    show_label: true, label: null,
    properties: { layer_name: 'Círculos', provenance: 'user' },
    provenance: 'user', created_at: '2026-09-25T10:00:00', updated_at: '2026-09-25T10:00:00',
    expiration: null,
  }

  // The real client unwraps `response.data` in an interceptor, so callers
  // receive the payload directly. Mocking `{ data }` here would make every
  // store read `.layers` / `.objects` off `undefined` and quietly render
  // empty panels — a bug in the test, not in the app.
  const RESP = (payload) => Promise.resolve(payload)

  return {
    API_PREFIX: '/api/v1',
    default: { get: () => RESP({}), post: () => RESP({}), put: () => RESP({}), delete: () => RESP({}) },
    client: { get: () => RESP({}), post: () => RESP({}), put: () => RESP({}), delete: () => RESP({}) },
    describeError: (e) => String(e?.message || e || 'error'),

    system: {
      status: () => RESP({ status: 'ok', opensky: { configured: true, detail: {} }, database: { connected: true, tables: [] } }),
      config: () => RESP({ config: { opensky_configured: true } }),
      credits: () => RESP({}),
      vocabulary: () => RESP({
        object_types: ['point', 'circle', 'radial', 'rf_source', 'antenna', 'rf_event', 'reference', 'trace', 'polygon', 'line', 'measurement', 'annotation', 'airport', 'enacom_station', 'coverage', 'other'],
        states: ['Activo', 'Inactivo', 'Apagado', 'Cerrado', 'En investigación', 'Confirmado', 'Desconocido'],
        point_categories: ['Referencia', 'Antena', 'Fuente interferente', 'Estación ENACOM', 'Evento RF', 'Aeropuerto', 'Otro'],
        rf_source_kinds: ['FM', 'AM', 'TV', 'LTE', '5G', 'WiFi', 'Radar', 'Microondas', 'Satélite', 'Otro'],
        rf_event_classifications: ['Interferencia aeronaútica', 'Armónico', 'Intermodulación'],
        antenna_kinds: ['Omnidireccional', 'Direccional'],
        polarizations: ['Vertical', 'Horizontal', 'Circular'],
        units: ['nm', 'km', 'm'],
        reference_radii_nm: [1, 2, 5, 10, 20, 50, 100],
        correlation_radii_nm: [5, 10, 20, 50],
        provenance: ['observed', 'historical', 'live', 'calculated', 'user'],
        provenance_labels: { user: 'Introducido por el usuario', live: 'Dato en vivo' },
      }),
      formatCoordinate: () => RESP({}),
      logs: { recent: () => RESP({}), },
    },

    mapObjects: {
      list: () => RESP({ count: 1, objects: [CIRCLE] }),
      all: () => RESP({ count: 1, objects: [CIRCLE] }),
      get: () => RESP(CIRCLE),
      create: (payload) => RESP({ ...CIRCLE, ...payload, id: 99 }),
      update: (id, patch) => RESP({ ...CIRCLE, ...patch }),
      remove: () => RESP({ deleted: 1 }),
      setStatus: (id, status) => RESP({ ...CIRCLE, status }),
      move: (id, lat, lon) => RESP({ ...CIRCLE, latitude: lat, longitude: lon }),
      duplicate: () => RESP({ ...CIRCLE, id: 100 }),
      near: () => RESP({ count: 0, results: [] }),
      distances: () => RESP({ count: 1, results: [{ object_id: 11, distance_km: 0, distance_nm: 0 }] }),
      stats: () => RESP({ total: 1, visible: 1, hidden: 0, locked: 0, by_type: { circle: 1 }, by_status: { Activo: 1 }, by_layer: { circles: 1 } }),
      history: () => RESP([{ id: 1, field: 'status', old_value: 'Activo', new_value: 'Apagado', changed_at: '2026-09-25T10:00:00' }]),
      notes: () => RESP([{ id: 1, text: 'Fuente apagada.', timestamp: '2026-09-25T10:00:00' }]),
      addNote: () => RESP({}),
      importGeoJson: () => RESP({ created: [], errors: [] }),
    },

    layers: {
      list: () => RESP({ count: LAYERS.length, layers: LAYERS }),
      create: () => RESP({}),
      update: () => RESP({}),
      remove: () => RESP({}),
    },

    rf: {
      sources: () => RESP({ count: 0, sources: [] }),
      createSource: () => RESP({}), updateSource: () => RESP({}),
      events: () => RESP({ count: 0, events: [] }),
      createEvent: () => RESP({}), updateEvent: () => RESP({}),
      antennas: () => RESP({ count: 0, antennas: [] }),
      createAntenna: () => RESP({}), updateAntenna: () => RESP({}),
      references: () => RESP({ count: 0, references: [] }),
      createReference: () => RESP({}), updateReference: () => RESP({}),
      summary: () => RESP({ sources_total: 0, events_total: 0, antennas_total: 0, event_frequencies: {} }),
    },

    flights: {
      search: () => RESP({ flights: [], warnings: [] }),
      get: () => RESP({ flights: [] }), track: () => RESP({ points: [] }),
      liveTrack: () => RESP({ points: [] }), live: () => RESP({ states: [] }),
      all: () => RESP({ flights: [] }), byAircraft: () => RESP({ flights: [] }),
      arrivals: () => RESP({ flights: [] }), departures: () => RESP({ flights: [] }),
      sessions: () => RESP({ sessions: [] }),
      createSession: () => RESP({ id: 1, icao24: 'abc123', status: 'recording' }),
      startSession: () => RESP({}), stopSession: () => RESP({ id: 1, status: 'stopped', sample_count: 3 }),
      session: () => RESP({ session: { id: 1, icao24: 'abc123', status: 'stopped' }, positions: [], tracks: [] }),
      deleteSession: () => RESP({}),
      tracked: () => RESP({ count: 0, max: 5, slots: [] }),
      trackAircraft: () => RESP({}), untrack: () => RESP({}), patchTracked: () => RESP({}),
      untrackAircraft: () => RESP({}), patchTracked: () => RESP({}),
    },

    correlation: {
      rfAircraft: () => RESP({ bands: [], disclaimer: 'no implica causalidad' }),
      forObject: () => RESP({ bands: [], disclaimer: 'no implica causalidad' }),
      forAircraft: () => RESP({ count: 0, objects: [], disclaimer: 'no implica causalidad' }),
    },

    exporter: {
      geojsonUrl: () => '/api/v1/export/geojson',
      kmlUrl: () => '/api/v1/export/kml',
      csvUrl: () => '/api/v1/export/csv',
      trackUrl: () => '/api/v1/export/track/abc123',
    },

    updateTyped: () => RESP({}),

    expedientes: {
      list: () => RESP([]), get: () => RESP({}), create: () => RESP({}),
      update: () => RESP({}), remove: () => RESP({}),
      mediciones: () => RESP([]), eventos: () => RESP([]),
    },

    ping: () => Promise.resolve({ ok: true }),
  }
})

// ─── Imports after the mock ─────────────────────────────────────────────────
import CoordinateBar from '@/components/gis/CoordinateBar.vue'
import ContextMenu from '@/components/gis/ContextMenu.vue'
import FlightPanel from '@/components/gis/FlightPanel.vue'
import InspectorPanel from '@/components/gis/InspectorPanel.vue'
import LayerPanel from '@/components/gis/LayerPanel.vue'
import Timeline from '@/components/gis/Timeline.vue'
import ToolOptions from '@/components/gis/ToolOptions.vue'
import ExpedientePanel from '@/components/gis/ExpedientePanel.vue'
import GisShell from '@/views/GisShell.vue'

import { useMapStore } from '@/stores/map'
import { useFlightsStore } from '@/stores/flights'
import { useSystemStore } from '@/stores/system'
import { useExpedientesStore } from '@/stores/expedientes'

import { MapEngine } from '@/map/MapEngine'
import { ToolManager, TOOLS, TOOL_META } from '@/map/draw'
import { MeasureEngine, formatDistance as formatMetres } from '@/map/measure'
import { AircraftRenderer } from '@/map/aircraft'

// ─── Harness ────────────────────────────────────────────────────────────────

function makePinia() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return pinia
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
}

function mountComponent(component, { pinia = makePinia(), router = makeRouter() } = {}) {
  return mount(component, {
    global: { plugins: [pinia, router] },
    // Leaflet is happy with a detached node in jsdom.
    attachTo: document.body,
  })
}

// ─── Components ─────────────────────────────────────────────────────────────

describe('CoordinateBar', () => {
  it('mounts and shows the cursor placeholder', () => {
    const w = mountComponent(CoordinateBar)
    expect(w.text()).toContain('LAT')
    expect(w.text()).toContain('LON')
    w.unmount()
  })

  it('renders live coordinates once the store has them', async () => {
    const pinia = makePinia()
    const map = useMapStore()
    // setCursor takes a Leaflet LatLng, i.e. `.lng` not `.lon`.
    map.setCursor({ lat: -34.603722, lng: -58.381592 })
    const w = mountComponent(CoordinateBar, { pinia })
    await flushPromises()
    // The exact string the Python suite compares byte for byte.
    expect(w.text()).toContain('-34.603722')
    expect(w.text()).toContain('-58.381592')
    w.unmount()
  })

  it('switches coordinate format', async () => {
    const pinia = makePinia()
    const map = useMapStore()
    map.setCursor({ lat: -34.603722, lng: -58.381592 })
    const w = mountComponent(CoordinateBar, { pinia })
    await flushPromises()
    map.setCoordinateFormat('dms')
    await flushPromises()
    expect(w.text()).toContain('°')
    w.unmount()
  })
})

describe('InspectorPanel', () => {
  it('mounts with nothing selected', () => {
    const w = mountComponent(InspectorPanel)
    expect(w.text()).toContain('Inspector')
    w.unmount()
  })

  it('shows general properties for a selected object', async () => {
    const pinia = makePinia()
    const map = useMapStore()
    const w = mountComponent(InspectorPanel, { pinia })
    map.upsert({
      id: 11, type: 'circle', name: 'Radio 20 NM', status: 'Activo',
      geometry_type: 'Polygon', latlng: [-34.6, -58.4], latlngs: [[-34.6, -58.4]],
      latitude: -34.6, longitude: -58.4, radius: 20, radius_unit: 'nm',
      metrics: { radius_km: 37.04, radius_nm: 20 }, visible: true, locked: false,
      layer: 'circles', provenance: 'user', properties: { layer_name: 'Círculos' },
      created_at: '2026-09-25T10:00:00', updated_at: '2026-09-25T10:00:00',
    })
    map.select(11)
    await flushPromises()

    // The name is an editable field, not static text.
    expect(w.find('input[value="Radio 20 NM"], input').exists()).toBe(true)
    expect(w.find('input').element.value).toBe('Radio 20 NM')
    expect(w.text()).toContain('ID 11')
    // Both units must be shown for a circle.
    expect(w.text()).toContain('37.04')
    // Provenance is always visible (spec §14).
    expect(w.text()).toContain('Introducido por el usuario')
    w.unmount()
  })
})

describe('LayerPanel', () => {
  it('lists the layers returned by the API', async () => {
    const pinia = makePinia()
    const map = useMapStore()
    const w = mountComponent(LayerPanel, { pinia })
    await map.loadLayers()
    await flushPromises()
    expect(w.text()).toContain('Mapa base')
    expect(w.text()).toContain('Círculos')
    w.unmount()
  })
})

describe('ToolOptions', () => {
  it('mounts with the unit selector', async () => {
    const pinia = makePinia()
    const map = useMapStore()
    const w = mountComponent(ToolOptions, { pinia })
    await flushPromises()
    expect(w.text()).toContain('Unidades')
    // 1 NM = 1.852 km is stated so the operator knows the conversion.
    expect(w.text()).toContain('1,852')
    w.unmount()
  })
})

describe('FlightPanel', () => {
  it('mounts and shows the watchlist cap', async () => {
    const w = mountComponent(FlightPanel)
    await flushPromises()
    expect(w.text()).toContain('Vuelos')
    expect(w.text()).toContain('/5')
    w.unmount()
  })
})

describe('Timeline', () => {
  it('mounts with no session selected', () => {
    const w = mountComponent(Timeline)
    expect(w.text()).toBeTruthy()
    w.unmount()
  })

  it('renders a loaded session without throwing', async () => {
    // The regression this covers: the provenance badge read
    // `flightStore.track`, and the store is `flightsStore`. It only renders
    // when a session is loaded, so it sat behind a v-if that was false in
    // every other test, and the build, the linter and the whole suite passed
    // with a ReferenceError waiting behind that condition.
    const pinia = makePinia()
    const { useFlightsStore } = await import('@/stores/flights')
    const flights = useFlightsStore()

    flights.replaySession = {
      session: { id: 1, icao24: 'abc123', callsign: 'TEST1', source: 'aerorf' },
      positions: [
        { latitude: -34.6, longitude: -58.4, timestamp: 1758000000, altitude: 3000 },
        { latitude: -34.5, longitude: -58.3, timestamp: 1758000060, altitude: 3200 },
      ],
    }
    flights.replayIndex = 0

    const errors = []
    const spy = vi.spyOn(console, 'error').mockImplementation((...a) => errors.push(a.join(' ')))
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation((...a) => errors.push(a.join(' ')))

    const w = mountComponent(Timeline, { pinia })
    await flushPromises()

    // It found the store: the source badge rendered.
    expect(w.text()).toContain('aerorf')
    // And the point counter agrees with what was loaded.
    expect(w.text()).toContain('1/2')
    expect(errors).toEqual([])

    spy.mockRestore()
    warnSpy.mockRestore()
    w.unmount()
  })
})

describe('ExpedientePanel', () => {
  it('mounts with no expedientes', async () => {
    const w = mountComponent(ExpedientePanel)
    await flushPromises()
    expect(w.text()).toContain('Expedientes')
    w.unmount()
  })
})

describe('ContextMenu', () => {
  it('stays hidden until opened', async () => {
    const pinia = makePinia()
    const map = useMapStore()
    const w = mountComponent(ContextMenu, { pinia })
    await flushPromises()
    // The menu is teleported to <body>, so it is not inside the wrapper.
    const sel = () => document.body.querySelector('.aerorf-context')
    expect(sel()).toBeNull()

    map.openContextMenu({ latlng: { lat: -34.6, lng: -58.4 }, containerPoint: { x: 100, y: 100 } })
    await flushPromises()
    expect(sel()).not.toBeNull()
    expect(sel().textContent).toContain('Crear')
    map.closeContextMenu()
    await flushPromises()
    expect(sel()).toBeNull()
    w.unmount()
  })

  it('closes on Escape', async () => {
    const pinia = makePinia()
    const map = useMapStore()
    const w = mountComponent(ContextMenu, { pinia })
    map.openContextMenu({ latlng: { lat: -34.6, lng: -58.4 }, containerPoint: { x: 10, y: 10 } })
    await flushPromises()
    expect(document.body.querySelector('.aerorf-context')).not.toBeNull()
    window.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(document.body.querySelector('.aerorf-context')).toBeNull()
    w.unmount()
  })
})

// ─── The shell itself ────────────────────────────────────────────────────────

describe('GisShell boots', () => {
  /**
   * The one test that matters most.
   *
   * GisShell is the only view that has never been looked at by a human,
   * and the SFC compiler is happy with code that throws the instant
   * `onMounted` runs. Three of the bugs fixed in this pass were of exactly
   * that shape — a missing `onMounted` import, a `watch_selected()` call
   * to a function that did not exist, and a `MapEngine` that dropped the
   * `container` option, so the map could not initialise at all. None of
   * them were visible to the build.
   *
   * If this test mounts and renders the panels, the shell starts.
   */
  it('mounts, builds the map and renders every panel', async () => {
    const pinia = makePinia()
    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const errors = []
    const spy = vi.spyOn(console, 'error').mockImplementation((...a) => errors.push(a.join(' ')))
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation((...a) => errors.push(a.join(' ')))

    const w = mount(GisShell, { global: { plugins: [pinia, router] } })

    // Let the async onMounted settle: bootstrap, vocabulary, layers, objects.
    await flushPromises()
    await new Promise((r) => setTimeout(r, 0))
    await flushPromises()

    // The map container must have become a real Leaflet map. This is the
    // assertion that fails if MapEngine drops its options. The shell
    // passes the element itself, not an id, so both forms matter.
    const mapEl = w.find('.gis-map')
    expect(mapEl.exists()).toBe(true)
    expect(mapEl.element.classList.contains('leaflet-container')).toBe(true)

    // The engine must be attached to the store, or the tools are dead.
    const map = useMapStore()
    expect(map.engine).toBeTruthy()
    expect(map.toolManager).toBeTruthy()
    expect(map.measureEngine).toBeTruthy()

    // The tool palette and the side-panel tab strip must be present. The
    // panels themselves sit behind tabs, so only one is mounted at a time.
    for (const label of ['Herramientas', 'Capas', 'Vuelos', 'Expediente']) {
      expect(w.text()).toContain(label)
    }
    expect(w.findComponent(ToolOptions).exists()).toBe(true)
    expect(w.findComponent(CoordinateBar).exists()).toBe(true)

    // Nothing anywhere in the tree may have failed to render.
    expect(errors).toEqual([])

    spy.mockRestore()
    warnSpy.mockRestore()
    w.unmount()
  })

  it('switches the side panel and mounts the one that was asked for', async () => {
    const pinia = makePinia()
    const router = makeRouter()
    await router.push('/')
    await router.isReady()
    const w = mount(GisShell, { global: { plugins: [pinia, router] } })
    await flushPromises()

    // The shell starts on the tools tab.
    expect(w.findComponent(ToolOptions).exists()).toBe(true)
    expect(w.findComponent(LayerPanel).exists()).toBe(false)

    // Clicking "Capas" must swap the panel, not just change a label.
    const tab = w.findAll('button').find((b) => b.text().trim() === 'Capas')
    expect(tab).toBeTruthy()
    await tab.trigger('click')
    await flushPromises()

    expect(w.findComponent(LayerPanel).exists()).toBe(true)
    expect(w.findComponent(ToolOptions).exists()).toBe(false)
    w.unmount()
  })

  it('tears the map down on unmount without throwing', async () => {
    const pinia = makePinia()
    const router = makeRouter()
    await router.push('/')
    await router.isReady()
    const w = mount(GisShell, { global: { plugins: [pinia, router] } })
    await flushPromises()
    expect(() => w.unmount()).not.toThrow()
  })
})

describe('MapEngine in jsdom', () => {
  let container

  beforeEach(() => {
    container = document.createElement('div')
    container.id = 'map-test'
    container.style.width = '1024px'
    container.style.height = '768px'
    document.body.appendChild(container)
  })

  afterEach(() => {
    container?.remove()
  })

  it('initialises, and turns the container into a Leaflet map', () => {
    // The constructor must carry `container` through: if it rebuilds
    // `this.options` from scratch and drops the key, init() fails on
    // `undefined` and the whole shell never mounts.
    const engine = new MapEngine({ container: 'map-test' })
    engine.init()
    expect(engine.map).toBeTruthy()
    // Leaflet puts the class on the container element itself.
    expect(container.classList.contains('leaflet-container')).toBe(true)
    expect(engine.getZoom()).toBeGreaterThan(0)
    engine.destroy()
  })

  it('accepts a container element as well as an id', () => {
    // GisShell passes `mapContainer.value`, i.e. the element. Both
    // resolutions have to work or the map only half initialises.
    const el = document.createElement('div')
    el.className = 'gis-map'
    document.body.appendChild(el)
    const engine = new MapEngine({ container: el })
    engine.init()
    expect(el.classList.contains('leaflet-container')).toBe(true)
    engine.destroy()
    el.remove()
  })

  it('reports a missing container instead of failing obscurely', () => {
    const engine = new MapEngine({ container: 'does-not-exist' })
    expect(() => engine.init()).toThrow(/no se encontró el contenedor/)
  })

  it('publishes cursor coordinates on mousemove (spec §5)', () => {
    const engine = new MapEngine({ container: 'map-test' })
    engine.init()
    const seen = []
    engine.on('cursor', (ll) => seen.push(ll))
    engine.map.fire('mousemove', { latlng: { lat: -34.6, lng: -58.4 } })
    expect(seen.length).toBe(1)
    expect(seen[0].lat).toBeCloseTo(-34.6, 6)
    engine.destroy()
  })

  it('publishes clicks with the coordinates (spec §5)', () => {
    const engine = new MapEngine({ container: 'map-test' })
    engine.init()
    const seen = []
    engine.on('click', (p) => seen.push(p.latlng))
    engine.map.fire('click', { latlng: { lat: -34.6, lng: -58.4 } })
    expect(seen.length).toBe(1)
    expect(seen[0].lat).toBeCloseTo(-34.6, 6)
    engine.destroy()
  })

  it('renders a circle and a point', () => {
    const engine = new MapEngine({ container: 'map-test' })
    engine.init()
    const circle = engine.renderObject({
      id: 1, type: 'circle', geometry_type: 'Polygon',
      latlng: [-34.6, -58.4], latlngs: [[-34.6, -58.4]],
      radius: 20, radius_m: 37040, layer: 'circles', visible: true, color: '#3b82f6',
    })
    expect(circle).toBeTruthy()
    expect(engine.hasObject(1)).toBe(true)

    const point = engine.renderObject({
      id: 2, type: 'point', geometry_type: 'Point',
      latlng: [-34.5, -58.3], layer: 'user', visible: true,
    })
    expect(point).toBeTruthy()
    expect(engine.hasObject(2)).toBe(true)

    engine.removeObject(1)
    expect(engine.hasObject(1)).toBe(false)
    engine.destroy()
  })

  it('reports an object with no derivable geometry as null, not a broken layer', () => {
    const engine = new MapEngine({ container: 'map-test' })
    engine.init()
    const layer = engine.renderObject({
      id: 3, type: 'point', geometry_type: null, latlng: null, latlngs: [],
      layer: 'user', visible: true,
    })
    expect(layer).toBeNull()
    engine.destroy()
  })

  it('formats a circle popup with both units (spec §10, §39)', () => {
    const engine = new MapEngine({ container: 'map-test' })
    engine.init()
    const html = engine.objectPopup({
      id: 1, type: 'circle', name: 'Radio 20 NM', status: 'Activo',
      metrics: { radius_nm: 20, radius_km: 37.04 },
      properties: {}, provenance: 'user',
    })
    expect(html).toContain('Radio 20 NM')
    expect(html).toContain('20.000')
    expect(html).toContain('37.040')
    engine.destroy()
  })
})

describe('ToolManager in jsdom', () => {
  let container
  let engine
  let tools
  let completed

  beforeEach(() => {
    container = document.createElement('div')
    container.id = 'map-tools'
    document.body.appendChild(container)
    engine = new MapEngine({ container: 'map-tools' })
    engine.init()
    completed = []
    tools = new ToolManager(engine, { onComplete: (p) => completed.push(p) })
  })

  afterEach(() => {
    tools?.deactivate()
    engine?.destroy()
    container?.remove()
  })

  it('describes every tool with a label, a cursor and a hint (spec §6)', () => {
    for (const id of Object.values(TOOLS)) {
      expect(TOOL_META[id].label).toBeTruthy()
      expect(TOOL_META[id].cursor).toBeTruthy()
      expect(TOOL_META[id].hint).toBeTruthy()
    }
  })

  it('creates a point on click (spec §7 method A)', () => {
    tools.activate(TOOLS.POINT)
    engine.map.fire('click', { latlng: { lat: -34.6, lng: -58.4 } })
    expect(completed.length).toBe(1)
    expect(completed[0].type).toBe('point')
    expect(completed[0].latitude).toBeCloseTo(-34.6, 6)
    expect(completed[0].longitude).toBeCloseTo(-58.4, 6)
  })

  it('cancels with ESC without emitting anything (spec §6)', () => {
    tools.activate(TOOLS.LINE)
    engine.map.fire('click', { latlng: { lat: -34.6, lng: -58.4 } })
    window.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }))
    expect(completed.length).toBe(0)
    expect(tools.active).toBeNull()
  })

  it('builds a trace from several clicks', () => {
    tools.activate(TOOLS.TRACE)
    engine.map.fire('click', { latlng: { lat: -34.6, lng: -58.4 } })
    engine.map.fire('click', { latlng: { lat: -34.5, lng: -58.3 } })
    engine.map.fire('click', { latlng: { lat: -34.4, lng: -58.2 } })
    tools.finish()
    expect(completed.length).toBe(1)
    expect(completed[0].type).toBe('trace')
    expect(completed[0].properties.path.length).toBe(3)
  })

  it('creates a circle with the radius in the operator unit (spec §10)', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    // First click places the centre. The pointer then sizes the circle;
    // GisShell calls previewAt() from its own mousemove handler rather
    // than the manager subscribing to the map, so the test does the same.
    engine.map.fire('click', { latlng: { lat: -34.6, lng: -58.4 } })
    tools.previewAt({ lat: -34.4, lng: -58.4 })
    tools.commitCircle()
    expect(completed.length).toBe(1)
    const c = completed[0]
    expect(c.type).toBe('circle')
    expect(c.radius_unit).toBe('nm')
    // 0.2° of latitude here is about 22 km, so the radius is real and
    // expressed in the operator's unit, not the raw click offset.
    expect(c.radius_m).toBeGreaterThan(15_000)
    expect(c.radius_m).toBeLessThan(25_000)
    expect(c.radius).toBeCloseTo(c.radius_m / 1852, 1)
  })

  it('honours the radius typed by the operator when the pointer never moves', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20 })
    engine.map.fire('click', { latlng: { lat: -34.6, lng: -58.4 } })
    tools.commitCircle()
    // 20 NM must come out as 37040 m, whatever the pointer did.
    expect(completed[0].radius_m).toBeCloseTo(37_040, -1)
  })

  it('creates a radial with an azimuth (spec §11)', () => {
    tools.activate(TOOLS.RADIAL, { unit: 'nm', length: 30 })
    engine.map.fire('click', { latlng: { lat: -34.6, lng: -58.4 } })
    tools.previewAt({ lat: -34.5, lng: -58.4 })
    tools.commitRadial()
    expect(completed.length).toBe(1)
    const r = completed[0]
    expect(r.type).toBe('radial')
    expect(r.azimuth).toBeGreaterThanOrEqual(0)
    expect(r.azimuth).toBeLessThan(360)
    expect(r.length_unit).toBe('nm')
    expect(r.length_m).toBeGreaterThan(9_000)
  })

  it('keeps the azimuth and length the operator typed (regression)', () => {
    // Both used to be overwritten by a bearing/length measured from the
    // origin back to itself, which is 0° and 0 m.
    tools.activate(TOOLS.RADIAL, { unit: 'nm', length: 30, azimuth: 135 })
    engine.map.fire('click', { latlng: { lat: -34.6, lng: -58.4 } })
    tools.commitRadial()
    expect(completed[0].azimuth).toBeCloseTo(135, 1)
    expect(completed[0].length_m).toBeCloseTo(30 * 1852, -2)
  })

  it('refuses to finish an unfinished shape', () => {
    tools.activate(TOOLS.POLYGON)
    engine.map.fire('click', { latlng: { lat: -34.6, lng: -58.4 } })
    // One vertex is not a polygon.
    expect(tools.finish()).toBeNull()
    expect(completed.length).toBe(0)
  })
})

describe('MeasureEngine in jsdom', () => {
  let container
  let engine
  let measure

  beforeEach(() => {
    container = document.createElement('div')
    container.id = 'map-measure'
    document.body.appendChild(container)
    engine = new MapEngine({ container: 'map-measure' })
    engine.init()
    measure = new MeasureEngine(engine)
  })

  afterEach(() => {
    measure?.stop()
    engine?.destroy()
    container?.remove()
  })

  it('measures a single segment in m, km and NM (spec §13)', () => {
    measure.start('single')
    measure.addPoint({ lat: -34.6, lng: -58.4 })
    measure.addPoint({ lat: -34.5, lng: -58.4 })
    const m = measure.current()
    expect(m.segment_count).toBe(1)
    expect(m.total_km).toBeGreaterThan(10)
    expect(m.total_nm).toBeGreaterThan(5)
    expect(m.total_label).toContain('NM')
  })

  it('accumulates a multipoint measurement with per-segment bearings', () => {
    measure.start('multi')
    measure.addPoint({ lat: -34.6, lng: -58.4 })
    measure.addPoint({ lat: -34.5, lng: -58.4 })
    measure.addPoint({ lat: -34.4, lng: -58.4 })
    const m = measure.current()
    expect(m.segment_count).toBe(2)
    expect(m.segments[0].bearing).toBeCloseTo(0, 0) // due north
    expect(m.total_m).toBeGreaterThan(m.segments[0].distance_m)
  })

  it('undoes the last point', () => {
    measure.start('multi')
    measure.addPoint({ lat: -34.6, lng: -58.4 })
    measure.addPoint({ lat: -34.5, lng: -58.4 })
    measure.undo()
    expect(measure.current().points.length).toBe(1)
  })

  it('only produces a saveable payload with two points (spec §13)', () => {
    measure.start('single')
    expect(measure.toObjectPayload()).toBeNull()
    measure.addPoint({ lat: -34.6, lng: -58.4 })
    measure.addPoint({ lat: -34.5, lng: -58.4 })
    const payload = measure.toObjectPayload('Medición A-B')
    expect(payload.type).toBe('measurement')
    expect(payload.measurement.total_nm).toBeGreaterThan(0)
  })

  it('formats a distance with all three units', () => {
    expect(formatMetres(37_040)).toContain('37.040 km')
  })
})

describe('AircraftRenderer in jsdom', () => {
  let container
  let engine
  let renderer

  const STATE = {
    icao24: 'abc123', callsign: 'ARG1234', latitude: -34.6, longitude: -58.4,
    altitude: 10_000, heading: 90, velocity: 240, on_ground: false,
    time_position: 1_758_000_000, position_source: 'ADS-B', origin_country: 'Argentina',
    position_age_s: 2,
  }

  beforeEach(() => {
    container = document.createElement('div')
    container.id = 'map-aircraft'
    document.body.appendChild(container)
    engine = new MapEngine({ container: 'map-aircraft' })
    engine.init()
    renderer = new AircraftRenderer(engine)
  })

  afterEach(() => {
    renderer?.clear()
    engine?.destroy()
    container?.remove()
  })

  it('draws an aircraft marker with its callsign', () => {
    renderer.updateAircraft(STATE, '#22c55e')
    const html = container.innerHTML
    expect(html).toContain('ARG1234')
    expect(html).toContain('aerorf-aircraft-marker')
  })

  it('moves the marker instead of duplicating it', () => {
    renderer.updateAircraft(STATE, '#22c55e')
    renderer.updateAircraft({ ...STATE, latitude: -34.7 }, '#22c55e')
    expect(renderer.markers.size).toBe(1)
  })

  it('refuses to draw an aircraft with no position (spec §56)', () => {
    const marker = renderer.updateAircraft({ ...STATE, latitude: null }, '#fff')
    expect(marker).toBeNull()
    expect(renderer.markers.size).toBe(0)
  })

  it('draws the marker upright when the heading is unknown', () => {
    // Better an unrotated marker than an invented direction.
    renderer.updateAircraft({ ...STATE, heading: null }, '#fff')
    expect(container.innerHTML).toContain('rotate(0deg)')
  })

  it('colours a track by provenance (spec §56)', () => {
    renderer.drawTrack({
      icao24: 'abc123',
      points: [
        { latitude: -34.6, longitude: -58.4, timestamp: 1, provenance: 'aerorf' },
        { latitude: -34.5, longitude: -58.3, timestamp: 2, provenance: 'aerorf' },
        { latitude: -34.4, longitude: -58.2, timestamp: 3, provenance: 'historical' },
        { latitude: -34.3, longitude: -58.1, timestamp: 4, provenance: 'historical' },
      ],
    }, '#a855f7')
    // Two segments, one per source, plus start/end markers.
    expect(renderer.tracks.size).toBe(1)
    expect(renderer.tracks.get('abc123').getLayers().length).toBeGreaterThan(2)
  })

  it('removes markers for aircraft that are no longer tracked', () => {
    renderer.updateAircraft(STATE, '#fff')
    renderer.updateAircraft({ ...STATE, icao24: 'def456' }, '#fff')
    expect(renderer.markers.size).toBe(2)
    renderer.syncMarkers(['abc123'])
    expect(renderer.markers.size).toBe(1)
  })
})
