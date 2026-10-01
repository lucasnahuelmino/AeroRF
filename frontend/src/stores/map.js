/**
 * stores/map.js
 * ─────────────
 * State for the map: objects, layers, selection, tools and the cursor.
 *
 * The store owns persistence; `MapEngine` owns pixels. Vue components
 * never talk to Leaflet directly, and Leaflet never triggers a Vue render
 * on its own — the store pushes changes one way.
 */

import { defineStore } from 'pinia'
import { computed, ref, shallowRef, markRaw } from 'vue'

import { describeError, layers as layersApi, mapObjects, system as systemApi } from '@/api/client'
import { TOOLS } from '@/map/draw'
import { formatLatLon } from '@/map/geo'

/**
 * Convert a drawer's payload into the shape the API expects.
 *
 * The tools speak Leaflet's order, `[[lat, lon], ...]`, because that is what
 * they draw and measure with. The API speaks GeoJSON, `[lon, lat]`, because
 * that is the interchange format the database stores and what the spec
 * requires on export.
 *
 * Nothing in between used to translate them. The result was that a line or a
 * polygon was created with **zero points**: the request was accepted, an id
 * came back, and an empty object appeared on the map. `latlngs` was not a
 * field the schema declared, so Pydantic dropped it silently.
 *
 * Doing it here, at the single write path, means no caller has to remember,
 * and there is exactly one place where the two orders can disagree.
 *
 * The returned object is a copy: the caller's payload is not mutated, because
 * `handleToolComplete` spreads the same payload into the store afterwards.
 */
function toApiPayload(payload) {
  if (!payload || typeof payload !== 'object') return payload
  const out = { ...payload }

  // Where the vertices actually are.
  //
  // The two shapes that carry a vertex list arrive under `properties`: the
  // drawing tools call them `path` (line, trace, measurement) and `ring`
  // (polygon, coverage). `latlngs` is what the rest of the store and the engine
  // speak, and it is what the translation below has always read.
  //
  // It read only `latlngs`, so for every tool that names its vertices `path` or
  // `ring` the list was invisible here. The early-return branch ran instead: a
  // line, polygon, coverage or trace was saved as a **Point** on its first
  // vertex, and a measurement was saved with no geometry at all. Measured
  // against the API: all four came back `geometry_type=Point` with one vertex.
  // The request succeeded and the object appeared, which is why it read as
  // "does not save" rather than as an error — there was no error to see.
  //
  // Circles and radials were unaffected: they carry a centre and a measurement
  // and the backend builds the ring itself. Which is also why only they were
  // ever on the map.
  const props = out.properties
  const points =
    Array.isArray(out.latlngs) && out.latlngs.length
      ? out.latlngs
      : Array.isArray(props?.path) && props.path.length
        ? props.path
        : Array.isArray(props?.ring) && props.ring.length
          ? props.ring
          : out.latlngs
  if (!Array.isArray(points) || points.length === 0) {
    // No vertex list: nothing to translate. A circle carries its centre and
    // radius and the backend builds the ring itself.
    if (!out.geometry && out.latitude != null && out.longitude != null) {
      out.geometry = { type: 'Point', coordinates: [out.longitude, out.latitude] }
      out.geometry_type = out.geometry_type || 'Point'
    }
    delete out.latlngs
    return out
  }

  // GeoJSON is [lon, lat]; the tools are [lat, lon].
  const ring = points.map(([lat, lon]) => [Number(lon), Number(lat)])

  if (out.type === 'polygon' || out.type === 'coverage' || out.geometry_type === 'Polygon') {
    // GeoJSON requires a closed ring: first vertex repeated at the end.
    const first = ring[0]
    const last = ring[ring.length - 1]
    const closed =
      ring.length >= 4 &&
      first[0] === last[0] &&
      first[1] === last[1]
    const finalRing = closed ? ring : [...ring, first]
    out.geometry = { type: 'Polygon', coordinates: [finalRing] }
    out.geometry_type = 'Polygon'
  } else {
    out.geometry = { type: 'LineString', coordinates: ring }
    out.geometry_type = 'LineString'
  }

  delete out.latlngs
  return out
}

export const useMapStore = defineStore('map', () => {
  // ─── Engine (non-reactive: Leaflet must not be proxied by Vue) ───────────
  const engine = shallowRef(null)
  const toolManager = shallowRef(null)
  const measureEngine = shallowRef(null)

  // ─── Cursor (spec §5) ────────────────────────────────────────────────────
  const cursor = ref({ lat: null, lon: null })
  const coordinateFormat = ref(localStorage.getItem('aerorf:coord-format') || 'dd')
  const lastClick = ref(null)

  // ─── Objects ─────────────────────────────────────────────────────────────
  const objects = ref([])
  const byId = computed(() => {
    const map = new Map()
    objects.value.forEach((o) => map.set(o.id, o))
    return map
  })

  // ─── Layers (spec §38) ───────────────────────────────────────────────────
  const layers = ref([])

  // ─── Selection & tools ───────────────────────────────────────────────────
  const selectedId = ref(null)
  const selected = computed(() => (selectedId.value ? byId.value.get(selectedId.value) : null))
  const hoveredId = ref(null)
  const activeTool = ref(TOOLS.SELECT)
  const toolHint = ref('')
  const draft = ref(null)

  // Tool defaults the operator tweaks between uses (spec §10, §36, §37).
  // `useTyped: false` keeps the original two-click sizing: click the centre,
  // then click the edge. The panel can switch it to one-click sizing, where the
  // radius or length typed here is what gets stored.
  const toolOptions = ref({
    unit: 'nm',
    radius: 20,
    length: 20,
    azimuth: 135,
    useTyped: false,
  })

  // ─── Context menu (spec §45) ─────────────────────────────────────────────
  const contextMenu = ref({ open: false, lat: null, lon: null, x: 0, y: 0 })

  // ─── Loading / errors ────────────────────────────────────────────────────
  const loading = ref(false)
  const saving = ref(false)
  const error = ref(null)
  const notice = ref(null)
  const stats = ref(null)

  // ─── Vocabulary (closed lists from the backend) ──────────────────────────
  const vocabulary = ref({
    object_types: [], states: [], point_categories: [], rf_source_kinds: [],
    rf_event_classifications: [], antenna_kinds: [], polarizations: [],
    units: ['nm', 'km', 'm'], reference_radii_nm: [], correlation_radii_nm: [],
    provenance: [], provenance_labels: {},
  })

  // ─── Layer helpers ───────────────────────────────────────────────────────
  const visibleLayers = computed(() => layers.value.filter((l) => l.visible))

  function layerByKey(key) {
    return layers.value.find((l) => l.key === key) || null
  }

  function isLayerVisible(key) {
    return layerByKey(key)?.visible !== false
  }

  /** Objects belonging to a layer. */
  function objectsInLayer(key) {
    return objects.value.filter((o) => o.layer === key)
  }

  // ─── Bootstrapping ───────────────────────────────────────────────────────

  async function loadVocabulary() {
    try {
      vocabulary.value = await systemApi.vocabulary()
    } catch (e) {
      error.value = describeError(e)
    }
  }

  async function loadLayers() {
    try {
      const data = await layersApi.list()
      layers.value = data.layers || []
      layers.value.forEach((layer) => {
        engine.value?.ensureCategory(layer.key, {
          visible: layer.visible,
          opacity: layer.opacity,
        })
      })
    } catch (e) {
      error.value = describeError(e)
    }
  }

  async function loadObjects() {
    loading.value = true
    error.value = null
    try {
      const data = await mapObjects.all()
      objects.value = data.objects || []
      renderAll()
    } catch (e) {
      error.value = describeError(e)
      objects.value = []
    } finally {
      loading.value = false
    }
  }

  async function loadStats() {
    try {
      stats.value = await mapObjects.stats()
    } catch (e) {
      /* stats are decorative; a failure must not block the map */
    }
  }

  async function bootstrap() {
    await Promise.all([loadVocabulary(), loadLayers()])
    await loadObjects()
    await loadStats()
  }

  // ─── Engine wiring ───────────────────────────────────────────────────────

  function attachEngine(instance) {
    engine.value = markRaw(instance)
    loadLayers()
  }

  function renderAll() {
    const e = engine.value
    if (!e) return
    e.clearObjects()
    objects.value.forEach((obj) => {
      const layer = e.renderObject(obj)
      if (layer) {
        e.onObjectClick(obj.id, (id) => select(id))
        bindInspect(obj, layer)
      }
    })
    // The draw order is what decides who receives a click, so it is set here
    // rather than left to whichever category happened to be created first. A
    // circle added before a radial would otherwise cover the radial's whole
    // length, and the operator could only select the circle.
    e.restack()
  }

  /**
   * Bind the double click that opens the object in the Inspector.
   *
   * There is no popup on the map objects any more. The balloon was the second
   * place the same information appeared, it opened right on top of the panel
   * the operator had just clicked into, and it covered the toolbar and the
   * coordinates bar. Nothing is lost: `InspectorPanel` shows every field the
   * popup did, plus the per-type payload and the edit form, and it does it in
   * the panel that the operator was already reading.
   *
   * Airport and aircraft markers keep their popups. Neither has a side panel —
   * `AirportPanel` is a search box and a live aircraft only shows up in
   * `selectedAircraft` when the flight panel picks it — so for those the popup
   * is the only place the information is readable.
   *
   * The double click is bound to the *children* of a group, not to the group. A
   * measured shape is a group — the ring or line plus its centre dot — and
   * `on('dblclick')` on a group never fires, because no event is ever raised on
   * the group from a child. Bound on the group it looked like it worked and did
   * nothing.
   */
  function bindInspect(obj, layer = null) {
    const e = engine.value
    if (!e) return
    const target = layer || e.featureLayers.get(String(obj.id))
    if (!target) return
    const fresh = byId.value.get(obj.id) || obj
    const targets = e.vectorLayersFor(target)
    if (!targets.length) {
      target.on?.('dblclick', () => select(fresh.id))
      return
    }
    targets.forEach((child) => {
      child.on?.('dblclick', () => select(fresh.id))
    })
  }

  // ─── CRUD ────────────────────────────────────────────────────────────────

  async function createObject(payload) {
    saving.value = true
    error.value = null
    try {
      const created = await mapObjects.create(toApiPayload(payload))
      upsert(created)
      notice.value = `Creado: ${created.name || typeName(created.type)}`
      return created
    } catch (e) {
      error.value = describeError(e)
      return null
    } finally {
      saving.value = false
    }
  }

  async function updateObject(id, patch, { silent = false } = {}) {
    saving.value = true
    error.value = null
    try {
      const updated = await mapObjects.update(id, toApiPayload(patch))
      upsert(updated)
      if (!silent) notice.value = `Actualizado: ${updated.name || typeName(updated.type)}`
      return updated
    } catch (e) {
      error.value = describeError(e)
      return null
    } finally {
      saving.value = false
    }
  }

  async function setStatus(id, status, comment = null) {
    saving.value = true
    error.value = null
    try {
      const updated = await mapObjects.setStatus(id, status, comment)
      upsert(updated)
      notice.value = `Estado: ${status}`
      return updated
    } catch (e) {
      error.value = describeError(e)
      return null
    } finally {
      saving.value = false
    }
  }

  async function moveObject(id, lat, lon) {
    try {
      const moved = await mapObjects.move(id, lat, lon)
      upsert(moved)
      return moved
    } catch (e) {
      error.value = describeError(e)
      return null
    }
  }

  async function deleteObject(id, cascade = false) {
    error.value = null
    try {
      await mapObjects.remove(id, cascade)
      objects.value = objects.value.filter((o) => o.id !== id)
      if (selectedId.value === id) selectedId.value = null
      engine.value?.removeObject(id)
      notice.value = 'Objeto eliminado'
      await loadStats()
      return true
    } catch (e) {
      error.value = describeError(e)
      return false
    }
  }

  async function duplicateObject(id) {
    try {
      const copy = await mapObjects.duplicate(id)
      upsert(copy)
      select(copy.id)
      notice.value = 'Objeto duplicado'
      return copy
    } catch (e) {
      error.value = describeError(e)
      return null
    }
  }

  /** Insert or replace an object in the local cache and on the map. */
  function upsert(object) {
    if (!object?.id) return
    const index = objects.value.findIndex((o) => o.id === object.id)
    if (index >= 0) {
      // Preserve richer local data (e.g. notes) that the update omits.
      const merged = { ...objects.value[index], ...object }
      objects.value.splice(index, 1, merged)
    } else {
      objects.value.push(object)
    }
    renderObject(object)
  }

  function renderObject(object) {
    const e = engine.value
    if (!e || !object) return
    const layer = e.renderObject(object)
    if (layer) {
      e.onObjectClick(object.id, (id) => select(id))
      bindInspect(object, layer)
    }
  }

  // ─── Notes and history (spec §14, §41) ───────────────────────────────────

  async function addNote(id, text) {
    error.value = null
    try {
      await mapObjects.addNote(id, text)
      // Re-read the object so the inspector shows the new note.
      const fresh = await mapObjects.get(id)
      upsert(fresh)
      notice.value = 'Nota agregada'
      return true
    } catch (e) {
      error.value = describeError(e)
      return false
    }
  }

  async function loadHistory(id) {
    try {
      return await mapObjects.history(id)
    } catch (e) {
      error.value = describeError(e)
      return []
    }
  }

  async function loadNotes(id) {
    try {
      return await mapObjects.notes(id)
    } catch (e) {
      error.value = describeError(e)
      return []
    }
  }

  // ─── Selection ───────────────────────────────────────────────────────────

  function select(id) {
    selectedId.value = id ?? null
    engine.value?.clearHighlight()
    if (id) engine.value?.highlight(id)
  }

  function clearSelection() {
    select(null)
  }

  // ─── Cursor (spec §5) ────────────────────────────────────────────────────

  function setCursor(latlng) {
    if (!latlng) {
      cursor.value = { lat: null, lon: null }
      return
    }
    cursor.value = { lat: latlng.lat, lon: latlng.lng }
  }

  function setCoordinateFormat(format) {
    coordinateFormat.value = format
    localStorage.setItem('aerorf:coord-format', format)
  }

  /** Formatted cursor text, e.g. ``LAT -34.603722  LON -58.381592``. */
  const cursorText = computed(() => formatLatLon(cursor.value.lat, cursor.value.lon, coordinateFormat.value))

  function captureClick(latlng) {
    lastClick.value = { lat: latlng.lat, lon: latlng.lng }
    return lastClick.value
  }

  // ─── Tools (spec §6) ─────────────────────────────────────────────────────

  function setTool(name, options = {}) {
    toolManager.value?.activate(name, { ...toolOptions.value, ...options })
  }

  function cancelTool() {
    toolManager.value?.cancel()
  }

  function finishTool() {
    return toolManager.value?.finish()
  }

  function setToolOption(key, value) {
    toolOptions.value = { ...toolOptions.value, [key]: value }
  }

  // ─── Layer controls (spec §38) ───────────────────────────────────────────

  async function toggleLayer(key, visible) {
    const layer = layerByKey(key)
    if (!layer) return
    const next = visible ?? !layer.visible
    layer.visible = next
    engine.value?.setCategoryVisible(key, next)
    try {
      await layersApi.update(layer.id, { visible: next })
    } catch (e) {
      layer.visible = !next
      error.value = describeError(e)
    }
  }

  async function setLayerOpacity(key, opacity) {
    const layer = layerByKey(key)
    if (!layer) return
    layer.opacity = opacity
    engine.value?.setCategoryOpacity(key, opacity)
    try {
      await layersApi.update(layer.id, { opacity })
    } catch (e) {
      error.value = describeError(e)
    }
  }

  async function toggleLayerLock(key, locked) {
    const layer = layerByKey(key)
    if (!layer) return
    const next = locked ?? !layer.locked
    layer.locked = next
    try {
      await layersApi.update(layer.id, { locked: next })
    } catch (e) {
      error.value = describeError(e)
    }
  }

  // ─── Context menu ────────────────────────────────────────────────────────

  function openContextMenu(payload) {
    contextMenu.value = {
      open: true,
      lat: payload.latlng.lat,
      lon: payload.latlng.lng,
      x: payload.containerPoint?.x ?? 0,
      y: payload.containerPoint?.y ?? 0,
    }
  }

  function closeContextMenu() {
    contextMenu.value = { ...contextMenu.value, open: false }
  }

  // ─── Distances (spec §30) ────────────────────────────────────────────────

  const distances = ref([])
  const distancesLoading = ref(false)

  /** Distances from a point to every reference, in KM and NM. */
  async function loadDistances(lat, lon, params = {}) {
    distancesLoading.value = true
    try {
      const data = await mapObjects.distances(lat, lon, params)
      distances.value = data.results || []
      return data
    } catch (e) {
      error.value = describeError(e)
      return null
    } finally {
      distancesLoading.value = false
    }
  }

  function clearDistances() {
    distances.value = []
  }

  // ─── Message helpers ─────────────────────────────────────────────────────

  function dismiss() {
    error.value = null
    notice.value = null
  }

  return {
    // engine
    engine, toolManager, measureEngine, attachEngine,
    // cursor
    cursor, cursorText, coordinateFormat, setCursor, setCoordinateFormat,
    lastClick, captureClick,
    // objects
    objects, byId, loading, saving, error, notice, stats,
    loadObjects, loadStats, bootstrap,
    createObject, updateObject, setStatus, moveObject, deleteObject,
    duplicateObject, upsert, renderObject, renderAll,
    addNote, loadHistory, loadNotes,
    // selection
    selectedId, selected, hoveredId, select, clearSelection,
    // layers
    layers, loadLayers, layerByKey, visibleLayers, isLayerVisible, objectsInLayer,
    toggleLayer, setLayerOpacity, toggleLayerLock,
    // tools
    activeTool, toolHint, draft, toolOptions, setTool, cancelTool, finishTool,
    setToolOption,
    // context menu
    contextMenu, openContextMenu, closeContextMenu,
    // distances
    distances, distancesLoading, loadDistances, clearDistances,
    // vocabulary
    vocabulary, loadVocabulary,
    // misc
    dismiss,
  }
})

// ─── Helpers ────────────────────────────────────────────────────────────────

const TYPE_LABELS = {
  point: 'Punto', line: 'Línea', polygon: 'Polígono', circle: 'Círculo',
  radial: 'Radial', trace: 'Traza', measurement: 'Medición', annotation: 'Anotación',
  rf_source: 'Fuente interferente', antenna: 'Antena', reference: 'Referencia',
  rf_event: 'Evento RF', enacom_station: 'Estación ENACOM', airport: 'Aeropuerto',
  coverage: 'Cobertura', other: 'Otro',
}

export function typeName(type) {
  return TYPE_LABELS[type] || type || 'objeto'
}

export { formatLatLon }
