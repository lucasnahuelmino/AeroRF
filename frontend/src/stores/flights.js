/**
 * stores/flights.js
 * ────────────────
 * Flight search, watchlist (max 5), recording sessions and the live feed.
 *
 * Design notes
 * ────────────
 * * The store never invents data. If OpenSky has nothing, the UI says so.
 * * Provenance is carried through: a track response reports how many
 *   points came from OpenSky versus AeroRF's own recorder, and the store
 *   keeps that visible rather than flattening it.
 * * The live feed arrives over the WebSocket, which the backend only
 *   pushes on genuine change. No client-side polling loop competes with it.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { correlation, describeError, flights as flightsApi, system as systemApi } from '@/api/client'

export const MAX_TRACKED = 5

/** Distinct colour per watchlist slot (spec §25). */
export const SLOT_COLORS = ['#22c55e', '#3b82f6', '#f97316', '#a855f7', '#eab308']

export const useFlightsStore = defineStore('flights', () => {
  // ─── Backend capability ──────────────────────────────────────────────────
  const openskyConfigured = ref(false)
  const openskyDetail = ref(null)
  const loading = ref(false)
  const error = ref(null)
  const notice = ref(null)

  // ─── Search (spec §20) ───────────────────────────────────────────────────
  const query = ref({ callsign: '', icao24: '', date: '', time_hint: '' })
  const searchResult = ref(null)
  const selectedIcao24 = ref(null)

  // ─── Trajectories (spec §21, §22) ────────────────────────────────────────
  // `tracks` holds one trajectory per aircraft, keyed by ICAO24. `track` is
  // the one the operator last asked for, kept for the panel that reports
  // "Trayectoria: ... puntos".
  //
  // A single value was not enough: comparing one route against another is
  // the whole reason for drawing a trajectory, and with one slot the previous
  // aircraft's path was overwritten as soon as another was requested.
  const tracks = ref({})
  const track = ref(null)
  const trackLoading = ref(false)
  const liveTrack = ref(null)

  // ─── Watchlist (spec §25, §26) ───────────────────────────────────────────
  const watchlist = ref([])

  // ─── Live state (spec §23) ───────────────────────────────────────────────
  const liveStates = ref({})
  const lastUpdate = ref(null)
  const throttled = ref(null)
  const socketState = ref('disconnected')

  // ─── Recording (spec §24) ────────────────────────────────────────────────
  const sessions = ref([])
  const activeSessions = ref({})
  const replaySession = ref(null)
  const replayIndex = ref(0)
  const replayPlaying = ref(false)
  let replayTimer = null

  // ─── Computed ────────────────────────────────────────────────────────────
  const trackedCount = computed(() => watchlist.value.length)
  const canTrackMore = computed(() => watchlist.value.length < MAX_TRACKED)
  const freeSlots = computed(() => MAX_TRACKED - watchlist.value.length)

  const selectedAircraft = computed(() =>
    liveStates.value[selectedIcao24.value] || null,
  )

  const replayPoints = computed(() => replaySession.value?.positions || [])
  const replayCurrent = computed(
    () => replayPoints.value[replayIndex.value] || null,
  )

  const replayTimeRange = computed(() => {
    const points = replayPoints.value.filter((p) => p.latitude != null)
    if (!points.length) return null
    return { start: points[0], end: points[points.length - 1] }
  })

  // ─── Capability probe ────────────────────────────────────────────────────

  async function probeBackend() {
    try {
      const status = await systemApi.status()
      openskyConfigured.value = Boolean(status?.opensky?.configured)
      openskyDetail.value = status?.opensky?.detail || null
    } catch (e) {
      openskyConfigured.value = false
      error.value = describeError(e)
    }
  }

  // ─── Search (spec §20) ───────────────────────────────────────────────────

  async function search(params = null) {
    const q = params || query.value
    if (!q.icao24 && !q.callsign) {
      error.value = 'Indique un callsign o un ICAO24 para buscar.'
      return null
    }
    loading.value = true
    error.value = null
    searchResult.value = null
    try {
      const clean = {}
      Object.entries(q).forEach(([k, v]) => {
        if (v) clean[k] = v
      })
      const data = await flightsApi.search(clean)
      searchResult.value = data

      if (data.icao24) {
        selectedIcao24.value = data.icao24
        if (data.warnings?.length) {
          notice.value = data.warnings.join(' ')
        }
      }
      return data
    } catch (e) {
      error.value = describeError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  function clearSearch() {
    searchResult.value = null
    selectedIcao24.value = null
    track.value = null
    error.value = null
  }

  // ─── Trajectory (spec §21) ───────────────────────────────────────────────

  async function loadTrack(icao24, { time = null, includeLocal = true } = {}) {
    if (!icao24) return null
    const key = String(icao24).trim().toLowerCase()
    trackLoading.value = true
    error.value = null
    try {
      const params = {}
      // `!== null` and not a truthiness test: `time = 0` is a real value. It
      // asks OpenSky for the flight in progress, and the backend reads it to
      // label the points as live rather than historical. A truthiness check
      // dropped it silently and asked for the latest track instead.
      if (time !== null && time !== undefined) params.time = time
      params.include_local = includeLocal
      const data = await flightsApi.track(key, params)
      // Cached per aircraft so several trajectories can be held at once. The
      // key is normalised because the backend lower-cases the ICAO24, and a
      // cache keyed on the raw string would miss whenever the caller used a
      // different case than the watchlist.
      if (data) tracks.value = { ...tracks.value, [key]: data }
      track.value = data
      selectedIcao24.value = key
      return data
    } catch (e) {
      error.value = describeError(e)
      return null
    } finally {
      trackLoading.value = false
    }
  }

  /**
   * The cached trajectory for one aircraft, or null.
   *
   * The panel and the map use this instead of `track`, which only holds the
   * most recent one.
   */
  function trackFor(icao24) {
    if (!icao24) return null
    return tracks.value[String(icao24).trim().toLowerCase()] || null
  }

  /** Every trajectory currently held, for drawing them all at once. */
  function allTracks() {
    return Object.entries(tracks.value).map(([icao24, data]) => ({ icao24, data }))
  }

  /** Drop one aircraft's trajectory, e.g. when it leaves the watchlist. */
  function forgetTrack(icao24) {
    const key = String(icao24 || '').trim().toLowerCase()
    if (!key || !(key in tracks.value)) return false
    const next = { ...tracks.value }
    delete next[key]
    tracks.value = next
    if (track.value?.icao24 === key) track.value = null
    return true
  }

  async function loadLiveTrack(icao24) {
    if (!icao24) return null
    try {
      liveTrack.value = await flightsApi.liveTrack(icao24)
      return liveTrack.value
    } catch (e) {
      error.value = describeError(e)
      liveTrack.value = null
      return null
    }
  }

  /**
   * Leaflet polyline coordinates for the current track, plus its metadata.
   * Returns coordinates in `[lat, lon]` order.
   */
  const trackLatLngs = computed(() => toLatLngs(track.value))

  /** The same coordinates for one specific aircraft's cached trajectory. */
  function trackLatLngsFor(icao24) {
    return toLatLngs(trackFor(icao24))
  }

  function toLatLngs(data) {
    if (!data?.points?.length) return []
    return data.points
      .filter((p) => p.latitude != null && p.longitude != null)
      .map((p) => [p.latitude, p.longitude])
  }

  /** How many points came from each source (spec §56). */
  const trackProvenance = computed(() => track.value?.provenance_counts || {})

  const trackNote = computed(() => track.value?.resolution_note || '')

  // ─── Watchlist (spec §25) ────────────────────────────────────────────────

  async function loadWatchlist() {
    try {
      const data = await flightsApi.tracked()
      watchlist.value = data.slots || []
      return watchlist.value
    } catch (e) {
      error.value = describeError(e)
      return []
    }
  }

  async function trackAircraft(icao24, callsign = null) {
    error.value = null
    try {
      const row = await flightsApi.addToWatchlist(icao24, callsign)
      watchlist.value = [...watchlist.value, row].sort((a, b) => a.slot - b.slot)
      selectedIcao24.value = icao24
      notice.value = `Siguiendo ${callsign || icao24}`
      subscribeSocket()
      return row
    } catch (e) {
      error.value = describeError(e)
      return null
    }
  }

  async function untrackAircraft(icao24) {
    try {
      await flightsApi.untrack(icao24)
      // Compared case-insensitively: the API lower-cases the code, so an
      // upper-case argument would leave the entry behind and the list would
      // still show an aircraft that is no longer followed.
      const key = String(icao24).trim().toLowerCase()
      watchlist.value = watchlist.value.filter((s) => String(s.icao24).toLowerCase() !== key)
      delete liveStates.value[key]
      liveStates.value = { ...liveStates.value }
      // Its trajectory goes too: the map watcher drops any track whose
      // aircraft is no longer on the watchlist.
      forgetTrack(key)
      if (selectedIcao24.value === key) selectedIcao24.value = null
      subscribeSocket()
      notice.value = 'Aeronave quitada del seguimiento'
      return true
    } catch (e) {
      error.value = describeError(e)
      return false
    }
  }

  async function patchTracked(icao24, patch) {
    try {
      const row = await flightsApi.patchTracked(icao24, patch)
      watchlist.value = watchlist.value.map((s) => (s.icao24 === icao24 ? { ...s, ...row } : s))
      return row
    } catch (e) {
      error.value = describeError(e)
      return null
    }
  }

  const colorForSlot = (slot) => SLOT_COLORS[slot % SLOT_COLORS.length]

  // ─── Live feed via WebSocket (spec §48) ──────────────────────────────────

  let socket = null
  let reconnectTimer = null

  function connectSocket() {
    if (socket && socket.readyState <= 1) return
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${window.location.host}/ws/flights`

    socketState.value = 'connecting'
    socket = new WebSocket(url)

    socket.onopen = () => {
      socketState.value = 'connected'
      subscribeSocket()
    }

    socket.onmessage = (event) => {
      let payload
      try {
        payload = JSON.parse(event.data)
      } catch {
        return
      }
      handleSocketMessage(payload)
    }

    socket.onclose = () => {
      socketState.value = 'disconnected'
      socket = null
      // Reconnect with a backoff; the server pushes on change, so a
      // dropped socket means the map goes stale until it returns.
      clearTimeout(reconnectTimer)
      reconnectTimer = setTimeout(connectSocket, 5000)
    }

    socket.onerror = () => {
      socketState.value = 'error'
    }
  }

  /** Narrow the feed to the aircraft actually being followed. */
  function subscribeSocket() {
    if (!socket || socket.readyState !== 1) return
    const codes = watchlist.value.map((s) => s.icao24)
    socket.send(
      JSON.stringify({
        action: codes.length ? 'track' : 'untrack',
        icao24: codes,
      }),
    )
  }

  function handleSocketMessage(payload) {
    switch (payload.type) {
      case 'states': {
        const next = { ...liveStates.value }
        payload.states.forEach((state) => {
          next[state.icao24] = { ...next[state.icao24], ...state }
        })
        liveStates.value = next
        lastUpdate.value = new Date()
        throttled.value = null
        break
      }
      case 'throttled':
        throttled.value = payload
        break
      case 'status':
        if (payload.opensky === 'not_configured') openskyConfigured.value = false
        break
      case 'error':
        error.value = payload.message
        break
      default:
        break
    }
  }

  function disconnectSocket() {
    clearTimeout(reconnectTimer)
    if (socket) {
      socket.onclose = null
      socket.close()
      socket = null
    }
    socketState.value = 'disconnected'
  }

  /** A snapshot of the tracked aircraft, for the FlightPanel (spec §26). */
  const watchlistWithState = computed(() =>
    watchlist.value.map((slot) => ({
      ...slot,
      color: slot.color || colorForSlot(slot.slot),
      state: liveStates.value[slot.icao24] || null,
      isRecording: Boolean(activeSessions.value[slot.icao24]),
    })),
  )

  // ─── Recording sessions (spec §24) ───────────────────────────────────────

  async function loadSessions() {
    try {
      const data = await flightsApi.sessions()
      sessions.value = data.sessions || []
      return sessions.value
    } catch (e) {
      error.value = describeError(e)
      return []
    }
  }

  async function startRecording(icao24, callsign = null) {
    error.value = null
    try {
      const session = await flightsApi.createSession({
        icao24,
        callsign,
        interval_s: 10,
      })
      activeSessions.value = { ...activeSessions.value, [icao24]: session.id }
      await loadSessions()
      notice.value = `Grabando ${callsign || icao24}`
      return session
    } catch (e) {
      error.value = describeError(e)
      return null
    }
  }

  async function stopRecording(icao24) {
    const sessionId = activeSessions.value[icao24]
    if (!sessionId) return null
    error.value = null
    try {
      const stopped = await flightsApi.stopSession(sessionId)
      const next = { ...activeSessions.value }
      delete next[icao24]
      activeSessions.value = next
      await loadSessions()
      notice.value = `Grabación detenida: ${stopped.sample_count} muestras`
      // The recording is only useful once it can be seen. Fetch the
      // trajectory now: the route just flown is the thing being recorded, and
      // having to ask for it separately made a finished recording look like
      // it had produced nothing.
      await loadTrack(icao24, { time: 0 })
      return stopped
    } catch (e) {
      error.value = describeError(e)
      return null
    }
  }

  // ─── Replay (spec §27, §28) ──────────────────────────────────────────────

  async function loadSessionForReplay(sessionId) {
    try {
      const data = await flightsApi.session(sessionId)
      replaySession.value = data
      replayIndex.value = 0
      return data
    } catch (e) {
      error.value = describeError(e)
      return null
    }
  }

  function playReplay(intervalMs = 800) {
    if (!replayPoints.value.length) return
    replayPlaying.value = true
    stopReplayTimer()
    replayTimer = setInterval(() => {
      if (replayIndex.value >= replayPoints.value.length - 1) {
        stopReplay()
        return
      }
      replayIndex.value += 1
    }, intervalMs)
  }

  function pauseReplay() {
    replayPlaying.value = false
    stopReplayTimer()
  }

  function stopReplay() {
    replayPlaying.value = false
    stopReplayTimer()
  }

  function stepReplay(delta) {
    const next = replayIndex.value + delta
    replayIndex.value = Math.max(0, Math.min(replayPoints.value.length - 1, next))
  }

  function seekReplay(index) {
    replayIndex.value = Math.max(0, Math.min(replayPoints.value.length - 1, index))
  }

  function stopReplayTimer() {
    if (replayTimer) {
      clearInterval(replayTimer)
      replayTimer = null
    }
  }

  // ─── Distances from an aircraft to references (spec §30) ────────────────

  const aircraftDistances = ref([])
  const correlationDisclaimer = ref(null)

  async function loadAircraftDistances(icao24) {
    if (!icao24) return null
    try {
      const data = await correlation.forAircraft(icao24, { radii_nm: [5, 10, 20, 50] })
      aircraftDistances.value = data.objects || []
      correlationDisclaimer.value = data.disclaimer
      return data
    } catch (e) {
      error.value = describeError(e)
      return null
    }
  }

  // ─── Misc ────────────────────────────────────────────────────────────────

  function dismiss() {
    error.value = null
    notice.value = null
  }

  function reset() {
    clearSearch()
    track.value = null
    // The per-aircraft cache goes too. Leaving it behind would keep drawing
    // trajectories for aircraft that are no longer on the watchlist, and the
    // next operator would see paths nobody asked for.
    tracks.value = {}
    liveTrack.value = null
    aircraftDistances.value = []
    correlationDisclaimer.value = null
    stopReplay()
    replaySession.value = null
  }

  return {
    // capability
    openskyConfigured, openskyDetail, probeBackend,
    loading, error, notice, dismiss,
    // search
    query, searchResult, selectedIcao24, search, clearSearch,
    // tracks
    tracks, track, trackLoading, trackLatLngs, trackProvenance, trackNote,
    loadTrack, loadLiveTrack, trackFor, allTracks, forgetTrack, trackLatLngsFor,
    // watchlist
    watchlist, watchlistWithState, trackedCount, canTrackMore, freeSlots,
    loadWatchlist, trackAircraft, untrackAircraft, patchTracked, colorForSlot,
    // live
    liveStates, lastUpdate, throttled, socketState, selectedAircraft,
    connectSocket, disconnectSocket, subscribeSocket,
    // sessions
    sessions, activeSessions, startRecording, stopRecording, loadSessions,
    // replay
    replaySession, replayPoints, replayCurrent, replayIndex, replayPlaying,
    replayTimeRange, loadSessionForReplay, playReplay, pauseReplay,
    stopReplay, stepReplay, seekReplay,
    // correlation
    aircraftDistances, correlationDisclaimer, loadAircraftDistances,
    // misc
    reset,
  }
})
