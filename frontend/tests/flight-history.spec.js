import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

/**
 * Choosing which flight's trajectory to draw.
 *
 * An interference report names a flight that has already landed. Asking for
 * "the track" without an instant returns whichever flight that aircraft flew
 * most recently — often a different one. Verified against the live API: the
 * same aircraft answered with 129 points covering 09-29 13:14-15:48 when the
 * report was about a flight on 09-28 10:10 that had 308 points and 812 km.
 *
 * The points are real in both answers and the provenance is right, so nothing
 * downstream can tell them apart. These tests pin the fix: the operator picks
 * the flight, and a mismatched answer is declared.
 */
const ICAO = 'a101c3'
const OTHER = 'e06491'

function candidate(start, end, callsign, dep, arr) {
  return {
    icao24: ICAO,
    callsign,
    start_time: start,
    end_time: end,
    duration_s: end - start,
    track_time: start,
    departure_airport: dep,
    arrival_airport: arr,
    departure_candidates: 2,
    arrival_candidates: 2,
  }
}

const FLIGHTS = [
  candidate(1790687691, 1790696912, 'AAL1107', 'KBOI', null),
  candidate(1790631783, 1790639283, 'AAL3209', 'KCLT', 'KDFW'),
  candidate(1790615933, 1790624273, 'AAL1804', 'KSAT', 'KCLT'),
  candidate(1790600870, 1790609510, 'AAL2889', 'KCLT', 'KSAT'),
  candidate(1790590220, 1790594220, 'AAL3139', 'KPHL', 'KCLT'),
]

function trackOf(start, end, extra = {}) {
  return {
    icao24: ICAO,
    callsign: 'AAL3139',
    point_count: 308,
    source: 'opensky',
    provenance_counts: { historical: 308, aerorf: 0, live: 0 },
    start_time: start,
    end_time: end,
    length_km: 811.6,
    points: [],
    covered_window: { start, end, duration_s: end - start },
    matches_request: true,
    warnings: [],
    ...extra,
  }
}

async function makeStore(overrides = {}) {
  setActivePinia(createPinia())
  const api = await import('@/api/client')
  vi.spyOn(api.flights, 'flightsOf').mockImplementation(
    async (icao24, params) =>
      ({
        icao24,
        count: FLIGHTS.length,
        flights: FLIGHTS,
        estimated_credits: (params?.days || 2) * 4,
        history_limit_days: 30,
        search_truncated: false,
        windows_queried: [],
        ...overrides.list,
      }),
  )
  vi.spyOn(api.flights, 'track').mockImplementation(
    async (icao24, params) =>
      overrides.track
        ? overrides.track(icao24, params)
        : trackOf(FLIGHTS[4].start_time, FLIGHTS[4].end_time),
  )
  vi.spyOn(api.flights, 'tracked').mockResolvedValue({ slots: [] })
  vi.spyOn(api.flights, 'untrack').mockResolvedValue(true)
  const store = await import('@/stores/flights')
  const instance = store.useFlightsStore()
  if (typeof instance.subscribeSocket === 'function') instance.subscribeSocket = () => {}
  return instance
}

describe('choosing the flight behind a trajectory', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.restoreAllMocks()
  })

  it('lists the flights an aircraft flew, newest first', async () => {
    const store = await makeStore()
    const rows = await store.loadFlightsOf(ICAO, { days: 2 })

    expect(rows).toHaveLength(FLIGHTS.length)
    const starts = rows.map((f) => f.start_time)
    expect(starts).toEqual([...starts].sort((a, b) => b - a))
    expect(store.flightsFor(ICAO)).toHaveLength(FLIGHTS.length)
    // The list is per aircraft, so a second one does not overwrite it.
    expect(store.flightsFor(OTHER)).toEqual([])
  })

  it('asks for the trajectory of the flight that was chosen, not the newest', async () => {
    // The whole point. Without `time`, the backend returns the most recent
    // flight; with it, the one in the report.
    const store = await makeStore()
    const api = await import('@/api/client')
    await store.loadFlightsOf(ICAO, { days: 2 })

    const chosen = store.flightsFor(ICAO).find((f) => f.callsign === 'AAL3139')
    expect(chosen, 'el vuelo del reporte debe estar en la lista').toBeTruthy()

    await store.loadTrack(ICAO, { time: chosen.track_time })

    expect(api.flights.track).toHaveBeenCalledWith(ICAO, {
      time: chosen.track_time,
      include_local: true,
    })
    const used = api.flights.track.mock.calls[0][1].time
    expect(used, 'no debe pedir el vuelo mas reciente').not.toBe(FLIGHTS[0].track_time)
  })

  it('says when the answer belongs to a different flight', async () => {
    // OpenSky answered with the newest flight even though an older one was
    // asked for. The points are real; they are the wrong route.
    const store = await makeStore({
      track: async () =>
        trackOf(FLIGHTS[0].start_time, FLIGHTS[0].end_time, {
          matches_request: false,
          warnings: [
            'OpenSky devolvió el vuelo de 1790687691–1790696912, no el del '
              + 'instante solicitado (1790590220). Es el vuelo más reciente de '
              + 'esta aeronave, no el del reporte. Elija el vuelo en la lista.',
          ],
        }),
    })
    await store.loadFlightsOf(ICAO, { days: 2 })
    await store.loadTrack(ICAO, { time: FLIGHTS[4].track_time })

    expect(store.trackMismatch(ICAO), 'un vuelo ajeno no puede pasar por correcto').toBe(true)

    // And the aircraft whose answer is right is not flagged.
    const ok = await makeStore()
    await ok.loadTrack(ICAO, { time: FLIGHTS[4].track_time })
    expect(ok.trackMismatch(ICAO)).toBe(false)
  })

  it('does not flag an aircraft with no trajectory at all', async () => {
    // "Nothing" is not a mismatch. Only a wrong answer is.
    const store = await makeStore({
      track: async () => ({
        icao24: ICAO, point_count: 0, points: [], source: 'opensky',
        covered_window: null, matches_request: null, warnings: [],
      }),
    })
    await store.loadTrack(ICAO, { time: FLIGHTS[4].track_time })
    expect(store.trackMismatch(ICAO)).toBe(false)
  })

  it('reports what a search cost, and whether it was cut short', async () => {
    // Each day back is a metered request. A short list must not read as
    // "this aircraft did not fly then".
    const store = await makeStore({
      list: {
        flights: FLIGHTS.slice(0, 1),
        count: 1,
        search_truncated: true,
        estimated_credits: 120,
        windows_queried: Array.from({ length: 30 }, (_, i) => ({ begin: i, end: i + 1, count: 0 })),
      },
    })
    await store.loadFlightsOf(ICAO, { days: 30 })

    expect(store.flightListNote).toMatch(/cort/i)
    expect(store.flightListNote).toMatch(/120/)
    expect(store.flightListMessage).toMatch(/1 vuelo/)
  })

  it('a failed search says so instead of leaving an empty list looking like "no flights"', async () => {
    const store = await makeStore()
    const api = await import('@/api/client')
    vi.spyOn(api.flights, 'flightsOf').mockRejectedValue(new Error('429 rate limited'))

    const rows = await store.loadFlightsOf(ICAO)

    expect(rows).toEqual([])
    expect(store.error).toBeTruthy()
    expect(store.flightListMessage).toMatch(/No se pudo consultar/i)
    expect(store.flightListNote).toBeTruthy()
  })

  it('forgets the flight list when the aircraft leaves the watchlist', async () => {
    const store = await makeStore()
    await store.loadFlightsOf(ICAO)
    expect(store.flightsFor(ICAO)).toHaveLength(FLIGHTS.length)

    await store.untrackAircraft(ICAO)
    expect(store.flightsFor(ICAO), 'la lista quedo tras salir de la lista').toEqual([])
    expect(store.flightListFor, 'el panel quedo abierto').toBeNull()
  })

  it('keeps the search window inside what was asked for', async () => {
    // A regression guard on the parameter: `days` is a search back from now,
    // and the response says what it covered.
    const store = await makeStore()
    const api = await import('@/api/client')

    await store.loadFlightsOf(ICAO, { days: 7 })
    expect(api.flights.flightsOf).toHaveBeenCalledWith(ICAO, { days: 7 })

    await store.loadFlightsOf(ICAO, { days: 3, begin: 1000, end: 2000 })
    expect(api.flights.flightsOf).toHaveBeenLastCalledWith(ICAO, {
      days: 3, begin: 1000, end: 2000,
    })
  })
})
