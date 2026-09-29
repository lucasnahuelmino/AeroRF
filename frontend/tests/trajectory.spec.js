import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

/**
 * The operator's flow, and the failure it hit.
 *
 * They record a flight, and the panel keeps saying "Trayectoria: no cargada"
 * even though the backend has the route. Asking for the trajectory turned out
 * to be the wrong HTTP call entirely.
 */
const TRACK_ICAO = 'e06491'
const OTHER_ICAO = 'e80618'

function trackResponse(icao24, count) {
  return {
    icao24,
    callsign: 'ARG1775',
    point_count: count,
    source: 'merged',
    provenance_counts: { historical: count - 2, aerorf: 2, live: 0 },
    start_time: 1790687775,
    end_time: 1790692821,
    length_km: 1057.4,
    points: Array.from({ length: count }, (_, i) => ({
      timestamp: 1790687775 + i * 60,
      latitude: -26 + i * 0.01,
      longitude: -54.6 + i * 0.01,
      altitude: 3900,
      provenance: i < 2 ? 'aerorf' : 'historical',
    })),
    warnings: [],
  }
}

/**
 * A store with every network call stubbed, including the WebSocket.
 *
 * The socket matters: `trackAircraft` opens one, jsdom has nothing to connect
 * to, and the failure arrives later as an AggregateError that vitest reports
 * against whichever test happens to be running. Stubbing it keeps these
 * assertions about the trajectory rather than about the transport.
 */
async function makeStore(trackImpl, slotOverrides = {}) {
  setActivePinia(createPinia())
  const api = await import('@/api/client')

  vi.spyOn(api.flights, 'track').mockImplementation(trackImpl)
  vi.spyOn(api.flights, 'tracked').mockResolvedValue({ slots: [] })
  vi.spyOn(api.flights, 'addToWatchlist').mockImplementation(async (icao24, callsign) => ({
    icao24: String(icao24).toLowerCase(),
    callsign,
    slot: 0,
    show_track: true,
    show_marker: true,
    ...slotOverrides,
  }))
  vi.spyOn(api.flights, 'untrack').mockResolvedValue(true)
  vi.spyOn(api.flights, 'sessions').mockResolvedValue({ sessions: [] })
  vi.spyOn(api.flights, 'createSession').mockResolvedValue({ id: 1 })
  vi.spyOn(api.flights, 'stopSession').mockResolvedValue({ id: 1, sample_count: 10 })

  const store = await import('@/stores/flights')
  const instance = store.useFlightsStore()
  // Replacing the socket opener keeps jsdom from reaching for a real one.
  if (typeof instance.subscribeSocket === 'function') {
    instance.subscribeSocket = () => {}
  }
  return instance
}

describe('the trajectory of a recorded flight', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.restoreAllMocks()
  })

  it('does not define the same key twice in the api object', async () => {
    // The cause, and the only place it can be caught.
    //
    // `flights` defined `track` twice in one object literal: the GET for a
    // trajectory, and the POST that adds an aircraft to the watchlist. In a
    // JavaScript literal the second silently replaces the first, so
    // `loadTrack` never asked the backend for a route. It added the aircraft
    // to the list and stored a watchlist row, which has no points, and the
    // panel said "no cargada" while the backend had 88 points ready.
    //
    // A spy cannot catch this: it would be installed on whichever `track`
    // happens to be there and would pass either way. The shadow has to be
    // found in the source, so this reads the file and looks for any name
    // defined more than once in the `flights` object.
    const fs = await import('node:fs')
    const path = await import('node:path')
    const file = path.resolve(__dirname, '../src/api/client.js')
    const src = fs.readFileSync(file, 'utf8')

    const start = src.indexOf('export const flights = {')
    expect(start, 'no se encontro el objeto flights en client.js').toBeGreaterThan(-1)
    const end = src.indexOf('\n}', start)
    const body = src.slice(start, end)

    const defined = [...body.matchAll(/^\s{2}(\w+):/gm)].map((m) => m[1])
    const dupes = defined.filter((name, i) => defined.indexOf(name) !== i)

    expect(dupes, `claves duplicadas en el objeto flights: ${dupes.join(', ')}`).toEqual([])
    expect(defined, 'la trayectoria debe seguir llamandose track').toContain('track')
    expect(defined, 'el alta en la lista debe llamarse addToWatchlist').toContain('addToWatchlist')
  })

  it('reaches the trajectory endpoint, and keeps what it returns', async () => {
    const store = await makeStore(async () => trackResponse(TRACK_ICAO, 88))
    const api = await import('@/api/client')

    await store.loadTrack(TRACK_ICAO)

    expect(api.flights.track, 'no se llamo a flights.track').toHaveBeenCalledTimes(1)
    expect(api.flights.track.mock.calls[0][0]).toBe(TRACK_ICAO)
    expect(api.flights.addToWatchlist, 'no debe tocar el alta en la lista').not.toHaveBeenCalled()

    const held = store.trackFor(TRACK_ICAO)
    expect(held, 'la trayectoria no quedo guardada').not.toBeNull()
    expect(held.point_count).toBe(88)
  })

  it('is available once the recording stops, without asking for it', async () => {
    // The recording is the thing the operator asked for. Finishing it used to
    // leave the panel reading "no cargada", as if the samples had gone
    // nowhere, when the route was in the database the whole time.
    const store = await makeStore(async () => trackResponse(TRACK_ICAO, 88))

    await store.trackAircraft(TRACK_ICAO, 'ARG1775')
    await store.startRecording(TRACK_ICAO, 'ARG1775')
    await store.stopRecording(TRACK_ICAO)

    const held = store.trackFor(TRACK_ICAO)
    expect(held, 'la trayectoria no se cargo al terminar de grabar').not.toBeNull()
    expect(held.point_count).toBe(88)
    expect(held.provenance_counts.aerorf, 'faltan las muestras propias').toBe(2)
  })

  it('reports per aircraft, so the panel can show two at once', async () => {
    const store = await makeStore(async (icao) =>
      trackResponse(String(icao).toLowerCase(), icao === TRACK_ICAO ? 88 : 40))

    await store.loadTrack(TRACK_ICAO)
    await store.loadTrack(OTHER_ICAO)

    expect(store.trackFor(TRACK_ICAO).point_count).toBe(88)
    expect(store.trackFor(OTHER_ICAO).point_count).toBe(40)
    expect(store.allTracks(), 'solo cabe una trayectoria a la vez').toHaveLength(2)
  })

  it('finds a cached trajectory whatever case the code was asked in', async () => {
    // The backend lower-cases the ICAO24 it returns. A cache keyed on the raw
    // request string missed whenever the caller used a different case, and
    // the panel fell back to "no cargada" with the data already loaded.
    const store = await makeStore(async () => trackResponse(TRACK_ICAO, 88))
    await store.loadTrack(TRACK_ICAO.toUpperCase())
    expect(store.trackFor(TRACK_ICAO.toLowerCase()), 'no se encontro por clave normalizada').not.toBeNull()
    expect(store.trackFor(TRACK_ICAO.toUpperCase())).not.toBeNull()
  })

  it('asks OpenSky for the flight in progress when time is zero', async () => {
    // `time = 0` means "the flight happening now". A truthiness check dropped
    // it, so the request went out with no time at all and came back with the
    // latest track instead, labelled historical rather than live.
    const store = await makeStore(async () => trackResponse(TRACK_ICAO, 88))
    const api = await import('@/api/client')
    await store.loadTrack(TRACK_ICAO, { time: 0 })
    expect(api.flights.track).toHaveBeenCalledWith(TRACK_ICAO, { time: 0, include_local: true })
  })

  it('drops the trajectory when the aircraft leaves the watchlist', async () => {
    const store = await makeStore(async () => trackResponse(TRACK_ICAO, 88))

    await store.loadTrack(TRACK_ICAO)
    expect(store.trackFor(TRACK_ICAO)).not.toBeNull()

    await store.untrackAircraft(TRACK_ICAO)
    expect(store.trackFor(TRACK_ICAO), 'la trayectoria quedo tras salir de la lista').toBeNull()
  })
})
