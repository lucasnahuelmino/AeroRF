/**
 * api/client.js
 * ─────────────
 * Single HTTP entry point for the whole application.
 *
 * Everything goes through the Vite proxy at `/api/v1` (see
 * `vite.config.js`), so there is no hard-coded backend URL in the
 * bundle — the previous `App.vue` called `http://localhost:8000`
 * directly, which broke outside dev and bypassed CORS.
 *
 * `OpenSky` credentials are never referenced here: the backend owns all
 * upstream authentication (spec §50).
 */

import axios from 'axios'

export const API_PREFIX = '/api/v1'

const client = axios.create({
  baseURL: API_PREFIX,
  timeout: 45000,
  headers: { 'Content-Type': 'application/json' },
})

/**
 * Normalise an axios failure into a message the UI can show verbatim.
 * The backend already speaks plain Spanish, so its `detail` is preferred.
 */
export function describeError(error) {
  if (!error) return 'Error desconocido'
  if (error.response) {
    const { status, data } = error.response
    const detail = data?.detail ?? data?.message
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length) {
      // FastAPI validation errors
      return detail
        .map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`)
        .join(' · ')
    }
    if (status === 429) return 'Límite de créditos de OpenSky alcanzado. Pausando consultas.'
    if (status === 503) return 'OpenSky no está configurado en el backend.'
    return `Error ${status}`
  }
  if (error.code === 'ECONNABORTED') return 'La solicitud tardó demasiado.'
  if (error.request) return 'No se pudo conectar con el backend.'
  return error.message || 'Error desconocido'
}

/** True when the backend is reachable. */
export async function ping() {
  try {
    const { data } = await client.get('/system/status', { timeout: 6000 })
    return { ok: true, data }
  } catch (e) {
    return { ok: false, error: describeError(e) }
  }
}

// ─── System ──────────────────────────────────────────────────────────────────

export const system = {
  status: () => client.get('/system/status').then((r) => r.data),
  config: () => client.get('/system/config').then((r) => r.data),
  credits: () => client.get('/system/credits').then((r) => r.data),
  vocabulary: () => client.get('/map/vocabulary').then((r) => r.data),
  formatCoordinate: (lat, lon, format = 'dd') =>
    client
      .get('/map/coordinate', { params: { latitude: lat, longitude: lon, format } })
      .then((r) => r.data),
}

// ─── Map objects (spec §7, §8) ──────────────────────────────────────────────

export const mapObjects = {
  list: (params = {}) =>
    client.get('/map/objects', { params }).then((r) => r.data),

  /** All objects in one call; used for the map's initial load. */
  all: () => mapObjects.list({ limit: 5000 }),

  get: (id) => client.get(`/map/objects/${id}`).then((r) => r.data),

  create: (payload) => client.post('/map/objects', payload).then((r) => r.data),

  update: (id, patch) =>
    client.put(`/map/objects/${id}`, patch).then((r) => r.data),

  remove: (id, cascade = false) =>
    client.delete(`/map/objects/${id}`, { params: { cascade } }).then((r) => r.data),

  setStatus: (id, status, comment = null, user = null) =>
    client
      .patch(`/map/objects/${id}/status`, { status, comment, user })
      .then((r) => r.data),

  move: (id, latitude, longitude) =>
    client.patch(`/map/objects/${id}/move`, { latitude, longitude }).then((r) => r.data),

  duplicate: (id, opts = {}) =>
    client.post(`/map/objects/${id}/duplicate`, opts).then((r) => r.data),

  near: (lat, lon, radiusNm, params = {}) =>
    client
      .get('/map/objects/near', {
        params: { latitude: lat, longitude: lon, radius_nm: radiusNm, ...params },
      })
      .then((r) => r.data),

  distances: (lat, lon, params = {}) =>
    client
      .get('/map/objects/distances', {
        params: { latitude: lat, longitude: lon, ...params },
      })
      .then((r) => r.data),

  stats: () => client.get('/map/objects/stats').then((r) => r.data),

  history: (id) => client.get(`/map/objects/${id}/history`).then((r) => r.data),

  notes: (id) => client.get(`/map/objects/${id}/notes`).then((r) => r.data),

  addNote: (id, text, user = null) =>
    client.post(`/map/objects/${id}/notes`, { text, user }).then((r) => r.data),

  importGeoJson: (feature, layerKey = null) =>
    client
      .post('/map/objects/from-geojson', feature, { params: { layer_key: layerKey } })
      .then((r) => r.data),
}

// ─── Layers (spec §38) ───────────────────────────────────────────────────────

export const layers = {
  list: () => client.get('/map/layers').then((r) => r.data),
  create: (payload) => client.post('/map/layers', payload).then((r) => r.data),
  update: (id, patch) => client.put(`/map/layers/${id}`, patch).then((r) => r.data),
  remove: (id, clear = false) =>
    client.delete(`/map/layers/${id}`, { params: { clear } }).then((r) => r.data),
}

// ─── RF domain (spec §32–§34) ────────────────────────────────────────────────

export const rf = {
  sources: (params = {}) => client.get('/rf/sources', { params }).then((r) => r.data),
  createSource: (payload) => client.post('/rf/sources', payload).then((r) => r.data),
  updateSource: (id, patch) => client.put(`/rf/sources/${id}`, patch).then((r) => r.data),

  events: (params = {}) => client.get('/rf/events', { params }).then((r) => r.data),
  createEvent: (payload) => client.post('/rf/events', payload).then((r) => r.data),
  updateEvent: (id, patch) => client.put(`/rf/events/${id}`, patch).then((r) => r.data),

  antennas: (params = {}) => client.get('/antennas', { params }).then((r) => r.data),
  createAntenna: (payload) => client.post('/antennas', payload).then((r) => r.data),
  updateAntenna: (id, patch) => client.put(`/antennas/${id}`, patch).then((r) => r.data),

  references: (params = {}) => client.get('/references', { params }).then((r) => r.data),
  createReference: (payload) => client.post('/references', payload).then((r) => r.data),
  updateReference: (id, patch) =>
    client.put(`/references/${id}`, patch).then((r) => r.data),

  summary: (expedienteId = null) =>
    client
      .get('/rf/summary', { params: { expediente_id: expedienteId } })
      .then((r) => r.data),
}

/**
 * Update the type-specific payload of a GIS object.
 *
 * The Inspector edits sources, antennas, references and events through one
 * form, so it needs one dispatcher rather than four dynamic imports. Each
 * type has its own endpoint, but the caller should not have to know which.
 */
const TYPE_ENDPOINTS = {
  rf_source: (id, body) => rf.updateSource(id, body),
  antenna: (id, body) => rf.updateAntenna(id, body),
  reference: (id, body) => rf.updateReference(id, body),
  rf_event: (id, body) => rf.updateEvent(id, body),
}

export function updateTyped(objectType, id, body) {
  const call = TYPE_ENDPOINTS[objectType]
  if (!call) {
    return Promise.reject(
      new Error(`El tipo «${objectType}» no tiene atributos propios que editar.`),
    )
  }
  return call(id, body)
}

// ─── Flights (spec §20–§27) ─────────────────────────────────────────────────

export const flights = {
  search: (params) => client.get('/flights/search', { params }).then((r) => r.data),

  get: (icao24, params = {}) =>
    client.get(`/flights/${icao24}`, { params }).then((r) => r.data),

  track: (icao24, params = {}) =>
    client.get(`/flights/${icao24}/track`, { params }).then((r) => r.data),

  liveTrack: (icao24) => client.get(`/flights/${icao24}/live-track`).then((r) => r.data),

  live: (params = {}) => client.get('/flights/live', { params }).then((r) => r.data),

  all: (params = {}) => client.get('/flights/all', { params }).then((r) => r.data),
  byAircraft: (icao24, params = {}) =>
    client.get('/flights/aircraft', { params: { icao24, ...params } }).then((r) => r.data),
  arrivals: (airport, params = {}) =>
    client.get('/flights/arrival', { params: { airport, ...params } }).then((r) => r.data),
  departures: (airport, params = {}) =>
    client.get('/flights/departure', { params: { airport, ...params } }).then((r) => r.data),

  // Sessions (spec §24)
  sessions: (params = {}) => client.get('/flights/sessions', { params }).then((r) => r.data),
  createSession: (payload) => client.post('/flights/sessions', payload).then((r) => r.data),
  startSession: (id) => client.post(`/flights/sessions/${id}/start`).then((r) => r.data),
  stopSession: (id, notes = null) =>
    client.post(`/flights/sessions/${id}/stop`, { notes }).then((r) => r.data),
  session: (id) => client.get(`/flights/sessions/${id}`).then((r) => r.data),
  deleteSession: (id) => client.delete(`/flights/sessions/${id}`).then((r) => r.data),

  // Watchlist (spec §25)
  tracked: () => client.get('/flights/tracked').then((r) => r.data),
  track: (icao24, callsign = null) =>
    client.post('/flights/tracked', null, { params: { icao24, callsign } }).then((r) => r.data),
  untrack: (icao24) => client.delete(`/flights/tracked/${icao24}`).then((r) => r.data),
  patchTracked: (icao24, patch) =>
    client.patch(`/flights/tracked/${icao24}`, patch).then((r) => r.data),
}

// ─── Correlation (spec §35) ─────────────────────────────────────────────────

export const correlation = {
  rfAircraft: (objectId, radiiNm = [5, 10, 20, 50], states = null) =>
    client
      .post('/correlation/rf-aircraft', {
        object_id: objectId,
        radii_nm: radiiNm,
        ...(states ? { states } : {}),
      })
      .then((r) => r.data),

  forObject: (objectId, radiiNm = null) =>
    client
      .get(`/correlation/object/${objectId}`, { params: { radii_nm: radiiNm } })
      .then((r) => r.data),

  forAircraft: (icao24, params = {}) =>
    client.get(`/correlation/aircraft/${icao24}`, { params }).then((r) => r.data),
}

// ─── Expedientes (legacy SIARI, preserved) ──────────────────────────────────

export const expedientes = {
  list: (params = {}) => client.get('/expedientes/', { params }).then((r) => r.data),
  get: (id) => client.get(`/expedientes/${id}`).then((r) => r.data),
  create: (payload) => client.post('/expedientes/', payload).then((r) => r.data),
  update: (id, patch) => client.put(`/expedientes/${id}`, patch).then((r) => r.data),
  remove: (id) => client.delete(`/expedientes/${id}`).then((r) => r.data),
  mediciones: (id) => client.get(`/expedientes/${id}/mediciones`).then((r) => r.data),
  eventos: (id) => client.get(`/expedientes/${id}/eventos`).then((r) => r.data),
}

// ─── Export (spec §46) ──────────────────────────────────────────────────────

export const exporter = {
  geojsonUrl: (params = {}) => toQueryUrl('/export/geojson', params),
  kmlUrl: (params = {}) => toQueryUrl('/export/kml', params),
  csvUrl: (params = {}) => toQueryUrl('/export/csv', params),
  trackUrl: (icao24, fmt = 'geojson') => toQueryUrl(`/export/track/${icao24}`, { fmt }),
}

/** Build a same-origin download URL that carries the API cookies/headers. */
function toQueryUrl(path, params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== '') query.append(k, v)
  })
  const qs = query.toString()
  return `${API_PREFIX}${path}${qs ? `?${qs}` : ''}`
}

export default client
