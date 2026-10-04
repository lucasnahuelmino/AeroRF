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
import DialogHost from '@/components/DialogHost.vue'
import FlightPanel from '@/components/gis/FlightPanel.vue'
import InspectorPanel from '@/components/gis/InspectorPanel.vue'
import LayerPanel from '@/components/gis/LayerPanel.vue'
import Timeline from '@/components/gis/Timeline.vue'
import ToolOptions from '@/components/gis/ToolOptions.vue'
import ExpedientePanel from '@/components/gis/ExpedientePanel.vue'
import GisShell from '@/views/GisShell.vue'

import { useMapStore } from '@/stores/map'
import { useSystemStore } from '@/stores/system'
import { readFileSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { useFlightsStore } from '@/stores/flights'
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

  it('muestra el payload del evento leído de properties.event (F2-03)', async () => {
    // El backend serializa el evento como `properties.event`, igual que
    // `rf`, `antenna` y `reference` (geojson_service.object_to_feature).
    // El panel lo leía en plano (`p.frequency_mhz`) y, como el backend no
    // emitía nada, la sección salía vacía: F2-03.
    const pinia = makePinia()
    const map = useMapStore()
    const w = mountComponent(InspectorPanel, { pinia })
    map.upsert({
      id: 41, type: 'rf_event', name: 'Evento RF 118.300', status: 'Activo',
      geometry_type: 'Point', latlng: [-34.55, -58.44], latlngs: [[-34.55, -58.44]],
      latitude: -34.55, longitude: -58.44,
      visible: true, locked: false, layer: 'rf_events',
      provenance: 'user',
      properties: {
        layer_name: 'Eventos RF',
        event: {
          frequency_mhz: 118.3,
          level_dbm: -62.5,
          classification: 'Interferencia aeronaútica',
        },
      },
      created_at: '2026-10-01T10:00:00', updated_at: '2026-10-01T10:00:00',
    })
    map.select(41)
    await flushPromises()

    const texto = w.text()
    expect(texto).toContain('Atributos del evento')
    expect(texto).toContain('118.3 MHz')
    expect(texto).toContain('-62.5 dBm')
    expect(texto).toContain('Interferencia aeronaútica')
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

  // The bug this protects against made the map look frozen, which is what the
  // operator reported as "press, drag, and the map does not move".
  //
  // There was a full-screen shield behind the menu: `fixed inset-0`,
  // `pointer-events: auto`, `z-index: 1240`, closing on `@click`. It covered the
  // viewport, so the map never got the `mousedown` that starts a pan — and since
  // a drag produces no `click`, the shield survived the whole gesture. Measured
  // in the browser: menu closed, a drag moved the map 16,906 m; menu open, the
  // same drag moved it 0 m and the menu was still open.
  it('has no full-screen shield swallowing the press that should drag the map', async () => {
    const pinia = makePinia()
    const map = useMapStore()
    const w = mountComponent(ContextMenu, { pinia })
    map.openContextMenu({ latlng: { lat: -34.6, lng: -58.4 }, containerPoint: { x: 100, y: 100 } })
    await flushPromises()

    // Asserted on the rendered structure, not on geometry. The first version of
    // this test filtered by `getBoundingClientRect()` and it passed *with the
    // shield restored*: jsdom computes no layout, every rect is zero, and a
    // filter for "covers the viewport" can never match anything — including the
    // bug. A guard that cannot fail is not a guard.
    //
    // What is actually asserted is the thing the shield was: a `fixed` element
    // pinned to all four edges, sitting over the map. `inset-0` is what makes an
    // element cover the viewport, and it is in the class list either way,
    // because Tailwind emits no stylesheet for jsdom to measure.
    const shields = [...document.body.querySelectorAll('div')]
      .filter((el) => !el.classList.contains('aerorf-context'))
      .filter((el) => el.className.split(/\s+/).includes('inset-0'))
      .map((el) => el.className)
    expect(
      shields,
      'no debe haber una capa a pantalla completa sobre el mapa: se queda el tiempo del arrastre',
    ).toEqual([])

    w.unmount()
  })

  it('closes on the press outside the menu, and that same press still reaches the map', async () => {
    const pinia = makePinia()
    const map = useMapStore()
    const w = mountComponent(ContextMenu, { pinia })
    map.openContextMenu({ latlng: { lat: -34.6, lng: -58.4 }, containerPoint: { x: 100, y: 100 } })
    await flushPromises()
    expect(document.body.querySelector('.aerorf-context')).not.toBeNull()

    // A press on the map — anywhere outside the menu — dismisses it. `mousedown`
    // and not `click`: press and release land on different points when dragging,
    // so a `click` never arrives and the menu would outlive the gesture.
    const fuera = document.createElement('div')
    document.body.appendChild(fuera)
    fuera.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await flushPromises()
    expect(document.body.querySelector('.aerorf-context')).toBeNull()

    // And the dismissal must not consume the press: the event is not stopped, so
    // a listener further down still sees it. That is what lets one press close
    // the menu and begin the pan.
    map.openContextMenu({ latlng: { lat: -34.6, lng: -58.4 }, containerPoint: { x: 100, y: 100 } })
    await flushPromises()
    let llegoAlMapa = false
    const alMapa = () => {
      llegoAlMapa = true
    }
    document.addEventListener('mousedown', alMapa)
    document.body.appendChild(fuera).dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await flushPromises()
    document.removeEventListener('mousedown', alMapa)
    expect(document.body.querySelector('.aerorf-context')).toBeNull()
    expect(llegoAlMapa, 'la pulsacion no debe consumirse al cerrar el menu').toBe(true)

    fuera.remove()
    w.unmount()
  })

  it('does not close when the press is on the menu itself', async () => {
    const pinia = makePinia()
    const map = useMapStore()
    const w = mountComponent(ContextMenu, { pinia })
    map.openContextMenu({ latlng: { lat: -34.6, lng: -58.4 }, containerPoint: { x: 100, y: 100 } })
    await flushPromises()

    const menu = document.body.querySelector('.aerorf-context')
    expect(menu).not.toBeNull()
    menu.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await flushPromises()
    // Still open: otherwise the first press on any row would dismiss the menu
    // before the click that activates the row could land.
    expect(document.body.querySelector('.aerorf-context')).not.toBeNull()

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
    //
    // The full names live in each tab's `title` and `aria-label`, because the
    // visible label is abbreviated: the five full names need 312px and the
    // sidebar has 215, and `flex: 1 1 0` shrank them until Expediente fell off
    // the strip entirely. Asserted on the accessible name so a rename of the
    // abbreviation cannot quietly take a section with it.
    for (const label of ['Herramientas', 'Capas', 'Vuelos', 'Aeropuertos', 'Expediente']) {
      const tab = w.findAll('.gis-tab').find((b) => b.attributes('title') === `Panel ${label}`)
      expect(tab, `falta la pestana ${label}`).toBeTruthy()
      expect(tab.attributes('aria-label'), `${label} sin nombre accesible`).toBe(`Panel ${label}`)
      // An icon and a short label, so the strip is a diagram and not a row of
      // words that may or may not fit.
      expect(tab.find('.gis-tab-icon').exists(), `${label} sin icono`).toBe(true)
      expect(tab.find('.gis-tab-label').exists(), `${label} sin rotulo`).toBe(true)
    }
    expect(w.findAll('.gis-tab')).toHaveLength(5)
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
    // Matched on the full name, which the tab carries as its accessible name;
    // the visible label is the abbreviation.
    const tab = w.findAll('.gis-tab').find((b) => b.attributes('title') === 'Panel Capas')
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

// The operator: the confirmation boxes said "localhost:5199 dice…" — the browser
// draws them, with the page's origin as the title, in the operating system's
// style, in the middle of an institutional tool. Seven of them: four confirms
// and three prompts used as a clipboard fallback.
// The operator: the "Limpiar" button next to the search box does not clear
// anything.
describe('Limpiar clears the search box, which is what it says it does', () => {
  it('empties every field of the query and the result', async () => {
    const pinia = makePinia()
    const flights = useFlightsStore()

    flights.query.callsign = 'ARG1763'
    flights.query.icao24 = 'e02659'
    flights.query.date = '2026-09-29'
    flights.query.time_hint = 'mañana'
    flights.selectedIcao24 = 'e02659'
    flights.error = 'algo'

    flights.clearSearch()

    // The fields are what the operator sees. `clearSearch` used to leave them
    // exactly as they were — it reset everything *derived* from the search and
    // nothing the operator had typed, which is why the button looked broken.
    expect(flights.query, 'la caja de busqueda debe quedar vacia').toEqual({
      callsign: '',
      icao24: '',
      date: '',
      time_hint: '',
    })
    expect(flights.selectedIcao24).toBeNull()
    expect(flights.searchResult).toBeNull()
    expect(flights.error).toBeNull()
  })

  it('does not throw on a query that was never filled in', async () => {
    // `query` is an object of four fields, not a string. `query.value = ''` would
    // have left the store holding something that is not that shape, and the next
    // render would have thrown on `query.callsign`.
    const pinia = makePinia()
    const flights = useFlightsStore()
    expect(() => flights.clearSearch()).not.toThrow()
    expect(flights.query.callsign).toBe('')
    expect(flights.query.icao24).toBe('')
  })

  it('keeps the cached trajectories, which is what "Quitar todas" is for', async () => {
    // Documented boundary: "Limpiar" sits next to the search box, not next to
    // the watchlist, and the map is drawing those routes. Clearing them here
    // would make the button do something the operator did not ask for.
    const pinia = makePinia()
    const flights = useFlightsStore()
    flights.tracks = { abc123: { points: [] } }
    flights.clearSearch()
    expect(flights.tracks.abc123, 'las trayectorias no son de este boton').toBeTruthy()
  })
})

describe('the application draws its own confirmations', () => {
  it('leaves no native dialog anywhere in the source', () => {
    // A source-level check, deliberately. The alternative would be to assert
    // that each of the seven call sites renders something, which would pass even
    // if the eighth `window.confirm` appeared tomorrow. This one fails the moment
    // anyone reaches for the browser's box again.
    const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'src')
    const offenders = []
    const walk = (dir) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name)
        if (entry.isDirectory()) {
          walk(full)
          continue
        }
        if (!/\.(js|vue)$/.test(entry.name)) continue
        readFileSync(full, 'utf8')
          .split('\n')
          .forEach((line, i) => {
            // The dialog host is the one place allowed to reason about them.
            if (full.endsWith('DialogHost.vue')) return
            if (/window\.(confirm|alert|prompt)\s*\(/.test(line)) {
              offenders.push(`${entry.name}:${i + 1}  ${line.trim()}`)
            }
          })
      }
    }
    walk(root)
    expect(
      offenders,
      'los diálogos nativos los dibuja el navegador: dicen "localhost:5199 dice..." y no se pueden ~\n' +
        'estilizar. Usar systemStore.ask() o systemStore.notify().',
    ).toEqual([])
  })

  it('ask resolves to what the operator answered', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const system = useSystemStore()

    const pendiente = system.ask({ title: 'Eliminar', message: '¿Eliminar «X»?' })
    expect(system.dialog, 'debe haber un dialogo abierto').toBeTruthy()
    expect(system.dialog.title).toBe('Eliminar')

    system.answerDialog(true)
    expect(await pendiente, 'Aceptar resuelve con true').toBe(true)
    expect(system.dialog, 'el dialogo se cierra').toBeNull()

    const otra = system.ask({ title: 'Seguir', message: '¿Seguir?' })
    system.answerDialog(false)
    expect(await otra, 'Cancelar resuelve con false').toBe(false)
  })

  it('keeps its labels and its danger flag, which the caller chose', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const system = useSystemStore()

    system.ask({ title: 'T', message: 'M' })
    expect(system.dialog.confirmLabel).toBe('Aceptar')
    expect(system.dialog.cancelLabel).toBe('Cancelar')
    expect(system.dialog.danger, 'por defecto no es destructivo').toBe(false)

    system.ask({ title: 'T', message: 'M', confirmLabel: 'Eliminar', danger: true })
    expect(system.dialog.confirmLabel).toBe('Eliminar')
    expect(system.dialog.danger).toBe(true)

    system.answerDialog(false)
  })

  it('answers the previous question with "no" when a second one arrives', async () => {
    // Otherwise the first `await` is stranded forever, and the caller proceeds
    // only if someone eventually clicks — a dialog that can be answered by a
    // question that is no longer on screen.
    const pinia = createPinia()
    setActivePinia(pinia)
    const system = useSystemStore()

    const primera = system.ask({ title: 'Una', message: '¿?' })
    const segunda = system.ask({ title: 'Dos', message: '¿?' })
    system.answerDialog(true)

    expect(await primera, 'la primera se responde sola con no').toBe(false)
    expect(await segunda).toBe(true)
  })

  it('notify shows a message and clears itself', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const system = useSystemStore()
    vi.useFakeTimers()

    system.notify('Coordenadas copiadas')
    expect(system.notice.text).toBe('Coordenadas copiadas')
    expect(system.notice.kind).toBe('info')

    vi.advanceTimersByTime(2600)
    expect(system.notice, 'el aviso se va solo').toBeNull()

    system.notify('No se pudo copiar', { kind: 'warn', ms: 6000 })
    expect(system.notice.kind).toBe('warn')
    vi.advanceTimersByTime(5999)
    expect(system.notice, 'un aviso largo sigue en pantalla').not.toBeNull()
    system.dismissNotice()
    expect(system.notice, 'y se puede cerrar a mano').toBeNull()
    vi.useRealTimers()
  })

  it('renders the question, both answers, and nothing when closed', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const system = useSystemStore()
    const w = mountComponent(DialogHost, { pinia })
    await flushPromises()

    expect(document.body.querySelector('.aerorf-dialog')).toBeNull()

    system.ask({
      title: 'Eliminar objeto',
      message: '¿Eliminar «Círculo»?',
      confirmLabel: 'Eliminar',
      danger: true,
    })
    await flushPromises()

    const dlg = document.body.querySelector('.aerorf-dialog')
    expect(dlg, 'el dialogo debe estar en el body: esta teletransportado').toBeTruthy()
    expect(dlg.textContent).toContain('Eliminar objeto')
    expect(dlg.textContent).toContain('¿Eliminar «Círculo»?')
    const botones = [...dlg.querySelectorAll('button')].map((b) => b.textContent.trim())
    expect(botones).toEqual(['Cancelar', 'Eliminar'])
    expect(dlg.getAttribute('role')).toBe('alertdialog')
    expect(dlg.getAttribute('aria-modal')).toBe('true')

    w.unmount()
  })

  it('Cancelar answers no and closes; a press on the backdrop too', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const system = useSystemStore()
    const w = mountComponent(DialogHost, { pinia })
    await flushPromises()

    const primera = system.ask({ title: 'T', message: 'M' })
    await flushPromises()
    document.body.querySelector('.aerorf-dialog button').click()
    await flushPromises()
    expect(await primera).toBe(false)
    expect(document.body.querySelector('.aerorf-dialog')).toBeNull()

    const segunda = system.ask({ title: 'T', message: 'M' })
    await flushPromises()
    // `mousedown`, not `click`: a press that becomes a drag must not leave the
    // dialog standing, which is the trap the context menu's shield walked into.
    document.body
      .querySelector('.aerorf-dialog')
      .parentElement.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await flushPromises()
    expect(await segunda).toBe(false)
    expect(document.body.querySelector('.aerorf-dialog')).toBeNull()

    w.unmount()
  })
})

describe('the drawing palette', () => {
  it('offers eight tools, without polígono and traza', async () => {
    // The operator: polígono does what cobertura does and traza does what línea
    // does, so two of the ten buttons were a duplicate. Four ways to draw two
    // shapes is one too many on a strip the width of a hand.
    //
    // The *types* stay: an object saved as `polygon` or `trace` earlier has to
    // keep rendering, labelling and exporting. Dropping the type would orphan
    // whatever is already in the database. `TOOL_META` still carries both; only
    // `HIDDEN_TOOLS` in `GisShell.vue` keeps them off the palette.
    const pinia = makePinia()
    const router = makeRouter()
    await router.push('/')
    await router.isReady()
    const w = mount(GisShell, { global: { plugins: [pinia, router] } })
    await flushPromises()

    const titles = w.findAll('.gis-tool').map((b) => b.attributes('title') || '')
    expect(titles.length, 'la paleta tiene que tener botones').toBe(8)
    expect(titles.join(' ')).not.toMatch(/Polígono/)
    expect(titles.join(' ')).not.toMatch(/Traza/)
    // And the ones that stay are all there.
    for (const label of ['Punto', 'Línea', 'Círculo', 'Radial', 'Medir', 'Cobertura']) {
      expect(titles.join(' '), `falta ${label}`).toContain(label)
    }
    w.unmount()
  })
})

describe('clicking an aircraft fills the inspector', () => {
  it('shows the live position, its provenance and the basics', async () => {
    // The click used to set `selectedIcao24` and nothing displayed it: the panel
    // went on saying "select an object" while the operator had just picked a
    // flight. The information was fetched and then nowhere.
    const pinia = makePinia()
    const flights = useFlightsStore()
    flights.selectedIcao24 = 'e02659'
    flights.liveStates = {
      e02659: {
        icao24: 'e02659', callsign: 'ARG1763', latitude: -34.6, longitude: -58.4,
        altitude: 34000, heading: 95, velocity: 242, on_ground: false,
        time_position: 1_758_000_000, position_source: 'ADS-B',
        origin_country: 'Argentina', position_age_s: 4,
      },
    }
    const w = mountComponent(InspectorPanel, { pinia })
    await flushPromises()

    const texto = w.text()
    expect(texto).toContain('ARG1763')
    expect(texto).toContain('e02659')
    expect(texto).toContain('34000')
    expect(texto).toContain('242')
    expect(texto).toContain('95')
    // Provenance is stated, not implied.
    expect(texto).toContain('posición en vivo')
    expect(texto).toContain('ADS-B')
    expect(texto).toContain('hace 4 s')
    w.unmount()
  })

  it('says so when the position is old, rather than implying it is live', async () => {
    const pinia = makePinia()
    const flights = useFlightsStore()
    flights.selectedIcao24 = 'e02659'
    flights.liveStates = {
      e02659: { icao24: 'e02659', latitude: -34.6, longitude: -58.4, position_age_s: 600 },
    }
    const w = mountComponent(InspectorPanel, { pinia })
    await flushPromises()
    expect(w.text()).toContain('última posición conocida')
    expect(w.text()).not.toContain('posición en vivo')
    w.unmount()
  })

  it('renders the object panel and nothing of the aircraft when an object is selected', async () => {
    // The bug this file's other tests were hiding: `v-else` pairs with the
    // immediately preceding conditional sibling. A second `v-if` between them
    // steals it, both blocks render, and the object panel reads `object.color` off
    // a null object — which took the whole map shell down with it.
    const pinia = makePinia()
    const map = useMapStore()
    const flights = useFlightsStore()
    flights.selectedIcao24 = 'e02659'
    flights.liveStates = { e02659: { icao24: 'e02659', latitude: -34.6, longitude: -58.4 } }
    map.upsert({
      id: 11, type: 'circle', name: 'Radio 20 NM', status: 'Activo',
      geometry_type: 'Polygon', latlng: [-34.6, -58.4], latlngs: [[-34.6, -58.4]],
      latitude: -34.6, longitude: -58.4, radius: 20, radius_unit: 'nm',
      metrics: { radius_km: 37.04, radius_nm: 20 }, visible: true, locked: false,
      layer: 'circles', provenance: 'user', properties: { layer_name: 'Círculos' },
      created_at: '2026-09-25T10:00:00', updated_at: '2026-09-25T10:00:00',
    })
    map.select(11)
    const w = mountComponent(InspectorPanel, { pinia })
    await flushPromises()
    expect(w.text(), 'el panel del objeto manda cuando hay objeto').toContain('Inspector')
    expect(w.text()).not.toContain('Procedencia:')
    w.unmount()
  })

  it('never implies that an aircraft caused an RF event', async () => {
    const pinia = makePinia()
    const flights = useFlightsStore()
    flights.selectedIcao24 = 'e02659'
    flights.liveStates = { e02659: { icao24: 'e02659', latitude: -34.6, longitude: -58.4 } }
    flights.aircraftDistances = [
      { id: 3, name: 'Fuente A', latitude: -34.61, longitude: -58.41, distance_km: 1.2, radius_nm: 5 },
    ]
    const w = mountComponent(InspectorPanel, { pinia })
    await flushPromises()
    const texto = w.text()
    expect(texto).toContain('Objetos RF cercanos')
    expect(texto).toContain('No implica causalidad')
    w.unmount()
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

  // The operator reported trajectories piling up on themselves: two flights of
  // the same aircraft, and the earlier one's route stayed on the map. "Quitar
  // todas" left the lot behind.
  //
  // Same cause as the deleted-objects bug fixed in 0.29.3, in a different class:
  // `drawTrack` adds with `layer.addTo(this.trackGroup)`, `removeTrack` called
  // only `layer.remove()`, and a layer off the map is still a child of the group —
  // so `LayerGroup.onAdd` put it back. Measured in the browser with two flights
  // of `e02659`: 2 children after the first, **3** after the second, and one
  // `restack()` brought all three back.
  describe('a trajectory must also be detached from its group', () => {
    const TRACK_A = {
      icao24: 'e02659',
      points: [
        { latitude: -34.6, longitude: -58.4, provenance: 'historical' },
        { latitude: -34.7, longitude: -58.5, provenance: 'historical' },
        { latitude: -34.8, longitude: -58.6, provenance: 'historical' },
      ],
    }
    const TRACK_B = {
      ...TRACK_A,
      points: [
        { latitude: -35.1, longitude: -59.1, provenance: 'historical' },
        { latitude: -35.2, longitude: -59.2, provenance: 'historical' },
      ],
    }

    const hijos = () => {
      const g = engine.categoryLayers.get('aircraft_tracks')
      return g && g._layers ? Object.keys(g._layers).length : 0
    }

    it('replaces the route instead of stacking a second one', () => {
      renderer.drawTrack(TRACK_A, '#a855f7')
      expect(hijos(), 'la primera ruta debe estar en su grupo').toBe(1)

      renderer.drawTrack(TRACK_B, '#a855f7')

      // One aircraft, one route. The second flight of the same aircraft replaces
      // the first; before the fix the group held both.
      expect(hijos(), 'la ruta anterior debe quedar suelta del grupo').toBe(1)
      expect(renderer.tracks.size).toBe(1)
    })

    it('removeTrack empties the group, not just the map', () => {
      renderer.drawTrack(TRACK_A, '#a855f7')
      renderer.drawTrack(TRACK_B, '#a855f7')
      renderer.removeTrack('e02659')
      expect(hijos(), 'no debe quedar ninguna ruta en el grupo').toBe(0)
      expect(renderer.tracks.size).toBe(0)
    })

    it('clearTracks empties the group too, which is what "Quitar todas" relies on', () => {
      renderer.drawTrack(TRACK_A, '#a855f7')
      renderer.drawTrack({ ...TRACK_A, icao24: 'e06491' }, '#a855f7')
      renderer.drawTrack({ ...TRACK_B, icao24: 'def456' }, '#a855f7')
      expect(hijos()).toBe(3)

      renderer.clearTracks()

      expect(hijos(), 'todas las rutas deben quedar sueltas del grupo').toBe(0)
      expect(renderer.tracks.size).toBe(0)
      // And a restack must not bring them back, which is how they reappeared.
      engine.restack()
      expect(hijos(), 'un restack no debe resucitar ninguna ruta').toBe(0)
    })
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

  // The operator: "I deleted every flight and the aeroplane is still there."
  //
  // `syncMarkers` and `clear` called `marker.remove()`, which takes the marker off
  // the map and leaves it in the `aircraft` `LayerGroup`. `LayerGroup.onAdd`
  // re-adds every child it still holds, so any restack brought the aircraft back.
  describe('an aircraft marker must also leave its group', () => {
    const hijos = () => {
      const g = engine.categoryLayers.get('aircraft')
      return g && g._layers ? Object.keys(g._layers).length : 0
    }

    it('syncMarkers empties the group for aircraft that went away', () => {
      renderer.updateAircraft(STATE, '#22c55e')
      renderer.updateAircraft({ ...STATE, icao24: 'def456' }, '#22c55e')
      expect(hijos()).toBe(2)

    renderer.syncMarkers(['abc123']) // only the first survives
      expect(hijos(), 'el que dejo de estar seguido no debe quedar en el grupo').toBe(1)

      renderer.syncMarkers([])
      expect(hijos(), 'syncMarkers([]) debe vaciar el grupo').toBe(0)
      expect(renderer.markers.size).toBe(0)
    })

    it('clear empties the group, and a restack does not bring them back', () => {
      renderer.updateAircraft(STATE, '#22c55e')
      renderer.updateAircraft({ ...STATE, icao24: 'def456' }, '#22c55e')
      expect(hijos()).toBe(2)

      renderer.clear()

      expect(hijos(), 'clear debe soltar los marcadores de su grupo').toBe(0)
      engine.restack()
      expect(hijos(), 'un restack no debe resucitar ningun avion').toBe(0)
      expect(document.querySelectorAll('.aerorf-aircraft-marker').length).toBe(0)
    })
  })

  it('removes markers for aircraft that are no longer tracked', () => {
    renderer.updateAircraft(STATE, '#fff')
    renderer.updateAircraft({ ...STATE, icao24: 'def456' }, '#fff')
    expect(renderer.markers.size).toBe(2)
    renderer.syncMarkers(['abc123'])
    expect(renderer.markers.size).toBe(1)
  })
})
