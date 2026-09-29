import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useFlightsStore } from '@/stores/flights'

/**
 * The panel's flight chooser, mounted.
 *
 * The store can hold a list of flights and the store can request a trajectory
 * for a chosen instant. Neither proves the panel passes the chosen instant:
 * the decision lives in the template, and a template is not exercised by a
 * store test. So this mounts the component and reads what it asked for.
 */
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
    mapObjects: { all: () => RESP({ objects: [] }), stats: () => RESP({}) },
    flights: {
      live: () => RESP({ states: {} }),
      tracked: () => RESP({ slots: [] }),
      track: () => RESP({}),
      flightsOf: () => RESP({ flights: [] }),
      patchTracked: () => RESP({}),
      untrack: () => RESP({}),
      sessions: () => RESP({ sessions: [] }),
    },
    rf: {}, correlation: {}, expedientes: {}, exporter: {},
  }
})

const ICAO = 'a101c3'

const FLIGHTS = [
  {
    icao24: ICAO, callsign: 'AAL1107',
    start_time: 1790687691, end_time: 1790696912, duration_s: 9221,
    track_time: 1790687691, departure_airport: 'KBOI', arrival_airport: null,
  },
  {
    icao24: ICAO, callsign: 'AAL3139',
    start_time: 1790590220, end_time: 1790594220, duration_s: 4000,
    track_time: 1790590220, departure_airport: 'KPHL', arrival_airport: 'KCLT',
  },
]

async function mountPanel(flightsOf) {
  setActivePinia(createPinia())
  const api = await import('@/api/client')
  const requested = []
  vi.spyOn(api.flights, 'flightsOf').mockImplementation(async (icao24, params) => {
    requested.push({ icao24, params })
    return flightsOf(icao24, params)
  })
  vi.spyOn(api.flights, 'track').mockImplementation(async () => ({
    icao24: ICAO, point_count: 308, source: 'opensky', points: [],
    provenance_counts: { historical: 308, aerorf: 0, live: 0 },
    start_time: 1790590220, end_time: 1790594220,
    covered_window: { start: 1790590220, end: 1790594220, duration_s: 4000 },
    matches_request: true, warnings: [],
  }))
  vi.spyOn(api.flights, 'untrack').mockResolvedValue(true)

  const FlightPanel = (await import('@/components/gis/FlightPanel.vue')).default
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  router.push('/')
  await router.isReady()

  const w = mount(FlightPanel, { global: { plugins: [router] } })
  await flushPromises()

  // The panel only renders a watchlist entry once the store holds one, and it
  // deliberately does not fetch one on mount: `onMounted` only refreshes an
  // existing list. So the slot is placed directly, and then the panel is told
  // to re-render.
  const store = useFlightsStore()
  store.watchlist = [
    {
      icao24: ICAO, callsign: 'AAL3139', slot: 0,
      show_track: true, show_marker: true, color: '#3b82f6',
    },
  ]
  await flushPromises()

  return { w, api, store, requested }
}

describe('the panel asks for the flight that was chosen', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.restoreAllMocks()
  })

  it('requests the trajectory of the flight whose row was clicked', async () => {
    const { w, api, requested } = await mountPanel(async () => ({
      icao24: ICAO, count: FLIGHTS.length, flights: FLIGHTS,
      estimated_credits: 8, history_limit_days: 30, search_truncated: false,
    }))

    // Open the chooser. Matched on the whole label, because the panel's
    // section heading is also called "Vuelos": a substring match finds the
    // heading instead of the button and the test passes while clicking
    // nothing.
    const openButton = w
      .findAll('button')
      .find((b) => b.text().trim() === '☰ Vuelos')
    expect(openButton, `no hay boton de vuelos. Botones: ${w.findAll('button').map((b) => JSON.stringify(b.text().trim())).join(', ')}`)
      .toBeTruthy()
    await openButton.trigger('click')
    await flushPromises()

    expect(requested, 'no se consultedo la lista de vuelos').toHaveLength(1)

    // Both flights are offered, newest first, with what identifies them.
    const listText = w.find('.gis-mini-btn.w-full').element.parentElement
      ?.parentElement?.textContent || ''
    expect(listText, `la lista no muestra los vuelos. Texto: ${w.text()}`)
      .toContain('KPHL')
    expect(listText).toContain('KCLT')
    expect(listText, 'falta la duracion del vuelo').toMatch(/\d+h\d\d/)

    // Newest first. The store test already pins the ordering of the rows it is
    // given; what can go wrong here is that the template renders them in a
    // different order, so this reads the rendered rows.
    const rows = w.findAll('button.w-full').map((b) => b.text())
    expect(rows.length, `se esperaban 2 filas de vuelos, hay ${rows.length}`).toBe(2)
    expect(rows[0], 'la fila mas reciente deberia ir primera').toContain('KBOI')
    expect(rows[1], 'la fila mas antigua deberia ir segunda').toContain('KPHL')

    // Click the older one — the one a report from yesterday would name.
    // Matched on the route, which is unique per row, rather than on the
    // callsign: the watchlist entry above carries AAL3139 too.
    const row = w.findAll('button').find((b) => b.text().includes('KPHL'))
    expect(row, 'no se ofrecio el vuelo del reporte').toBeTruthy()
    await row.trigger('click')
    await flushPromises()

    expect(api.flights.track).toHaveBeenCalledTimes(1)
    const [code, params] = api.flights.track.mock.calls[0]
    expect(code).toBe(ICAO)
    // The instant of the chosen flight, and nothing else. Without it the
    // backend returns the most recent flight, which is the wrong route.
    expect(params.time).toBe(FLIGHTS[1].track_time)
    expect(params.time).not.toBe(FLIGHTS[0].track_time)
  })

  it('shows a warning when the answer is a different flight', async () => {
    const { w } = await mountPanel(async () => ({
      icao24: ICAO, count: FLIGHTS.length, flights: FLIGHTS,
      estimated_credits: 8, history_limit_days: 30, search_truncated: false,
    }))

    const openButton = w.findAll('button').find((b) => b.text().includes('Vuelos'))
    await openButton.trigger('click')
    await flushPromises()

    const api = await import('@/api/client')
    vi.spyOn(api.flights, 'track').mockImplementation(async () => ({
      icao24: ICAO, point_count: 129, source: 'opensky', points: [],
      provenance_counts: { historical: 129, aerorf: 0, live: 0 },
      start_time: FLIGHTS[0].start_time, end_time: FLIGHTS[0].end_time,
      covered_window: {
        start: FLIGHTS[0].start_time, end: FLIGHTS[0].end_time, duration_s: 9221,
      },
      matches_request: false, warnings: ['vuelo mas reciente'],
    }))

    const row = w.findAll('button').find((b) => b.text().includes('KPHL'))
    await row.trigger('click')
    await flushPromises()

    const text = w.text()
    expect(text).toMatch(/corresponde a otro vuelo/i)
  })

  it('says the search was cut short, so a short list is not read as "no flights"', async () => {
    const { w } = await mountPanel(async () => ({
      icao24: ICAO, count: 1, flights: [FLIGHTS[0]],
      estimated_credits: 120, history_limit_days: 30,
      search_truncated: true,
      windows_queried: Array.from({ length: 30 }, (_, i) => ({ begin: i, end: i + 1, count: 0 })),
    }))

    const openButton = w.findAll('button').find((b) => b.text().includes('Vuelos'))
    await openButton.trigger('click')
    await flushPromises()

    const text = w.text()
    expect(text).toMatch(/cort/i)
    expect(text).toMatch(/120/)
  })

  it('does not open a second chooser when one is already showing', async () => {
    const { w, api } = await mountPanel(async () => ({
      icao24: ICAO, count: FLIGHTS.length, flights: FLIGHTS,
      estimated_credits: 8, history_limit_days: 30, search_truncated: false,
    }))

    const button = () => w.findAll('button').find((b) => b.text().includes('Vuelos'))
    await button().trigger('click')
    await flushPromises()
    expect(api.flights.flightsOf).toHaveBeenCalledTimes(1)

    // Clicking again closes it, and does not re-query: every day back is a
    // metered request.
    await button().trigger('click')
    await flushPromises()
    expect(api.flights.flightsOf).toHaveBeenCalledTimes(1)
    expect(w.text()).not.toContain('KPHL')
  })
})
