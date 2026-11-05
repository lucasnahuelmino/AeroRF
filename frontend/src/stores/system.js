/**
 * stores/system.js
 * ────────────────
 * Backend connectivity and shared UI state.
 *
 * The `cursor` ref existed before this refactor but nothing ever wrote to
 * it, so the header's "Cursor" field always read `n/a` (audit P5). It is
 * now fed by the MapEngine's mousemove subscription in the GIS shell, and
 * mirrored here so non-map components can read it.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { describeError, system as systemApi } from '@/api/client'

export const useSystemStore = defineStore('system', () => {
  // ─── Connectivity ────────────────────────────────────────────────────────
  const backendStatus = ref('desconectado')
  const openskyStatus = ref('desconocido')
  const dbStatus = ref(null)
  const config = ref(null)
  const lastCheck = ref(null)

  // ─── Cursor mirror (spec §5) ─────────────────────────────────────────────
  const cursor = ref({ lat: null, lon: null })
  const coordinateFormat = ref(localStorage.getItem('aerorf:coord-format') || 'dd')

  // ─── UI state ────────────────────────────────────────────────────────────
  // The map is the working surface, so its single contextual Workspace has a
  // remembered width and can be moved, collapsed, or closed without losing the
  // operator's preferred layout.
  const _num = (key, fallback, min, max) => {
    const raw = Number(localStorage.getItem(key))
    return Number.isFinite(raw) && raw >= min ? Math.min(raw, max) : fallback
  }
  const _remember = (key, value) => localStorage.setItem(key, String(value))
  const readStoredJson = (key, fallback) => {
    try {
      return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback
    } catch {
      return fallback
    }
  }
  function readWorkspaceContext() {
    const context = readStoredJson('aerorf:workspace-context', null)
    if (context?.type === 'object' && context.id != null) {
      return { type: 'object', id: context.id }
    }
    if (context?.type === 'aircraft' && typeof context.icao24 === 'string' && context.icao24.trim()) {
      return { type: 'aircraft', icao24: context.icao24.trim().toLowerCase() }
    }
    return null
  }
  function readWorkspaceHistory() {
    const history = readStoredJson('aerorf:workspace-history', [])
    if (!Array.isArray(history)) return []
    return history
      .filter((item) =>
        (item?.type === 'object' && item.id != null) ||
        (item?.type === 'aircraft' && typeof item.icao24 === 'string' && item.icao24.trim()),
      )
      .slice(0, 10)
      .map((item) => item.type === 'object'
        ? { type: 'object', id: item.id }
        : { type: 'aircraft', icao24: item.icao24.trim().toLowerCase() })
  }

  const WORKSPACE_CATEGORIES = new Set(['tools', 'layers', 'objects', 'flights', 'airports'])
  const WORKSPACE_SECTIONS = new Set([...WORKSPACE_CATEGORIES, 'inspector', 'timeline'])
  const SECTION_CATEGORY = {
    tools: 'tools',
    layers: 'layers',
    objects: 'objects',
    flights: 'flights',
    airports: 'airports',
    inspector: 'objects',
    timeline: 'flights',
  }
  const workspaceSectionValue = localStorage.getItem('aerorf:workspace-section')
  const workspaceCategoryValue = localStorage.getItem('aerorf:workspace-category')
  const workspaceLevelValue = localStorage.getItem('aerorf:workspace-level')
  const storedMode = localStorage.getItem('aerorf:workspace-mode')
  const workspaceMode = ref(
    ['open', 'collapsed', 'closed'].includes(storedMode)
      ? storedMode
      : localStorage.getItem('aerorf:sidebar-open') === '0' ? 'closed' : 'open',
  )
  const workspaceSection = ref(
    WORKSPACE_SECTIONS.has(workspaceSectionValue) ? workspaceSectionValue : 'tools',
  )
  const workspaceCategory = ref(
    WORKSPACE_CATEGORIES.has(workspaceCategoryValue)
      ? workspaceCategoryValue
      : SECTION_CATEGORY[workspaceSection.value] || null,
  )
  const workspaceLevel = ref(
    ['home', 'category', 'task'].includes(workspaceLevelValue)
      ? workspaceLevelValue
      : workspaceSectionValue ? 'task' : 'home',
  )
  const workspaceTask = ref(localStorage.getItem('aerorf:workspace-task') || '')
  const workspaceSide = ref(localStorage.getItem('aerorf:workspace-side') === 'right' ? 'right' : 'left')
  const workspaceWidth = ref(_num('aerorf:workspace-width', 300, 240, 520))
  const workspacePinned = ref(localStorage.getItem('aerorf:workspace-pinned') === '1')
  const workspaceContext = ref(readWorkspaceContext())
  const workspaceHistory = ref(readWorkspaceHistory())
  const pendingWorkspaceContext = ref(null)
  const workspaceReturnTarget = ref(null)

  const showTimeline = ref(false)

  // ─── Aerodrome reference layer ───────────────────────────────────────────
  // Kept out of the `layers` table on purpose: the ARP positions are
  // published facts, not operator data, so this is presentation state.
  // The country filter is a Set in the store but an array in localStorage,
  // because a Set does not survive serialisation.
  const airportCountries = ref(
    JSON.parse(localStorage.getItem('aerorf:airport-countries') || '[]'),
  )
  const airportLabels = ref(localStorage.getItem('aerorf:airport-labels') !== '0')

  function setAirportCountries(codes) {
    airportCountries.value = Array.from(new Set(codes || []))
    localStorage.setItem(
      'aerorf:airport-countries',
      JSON.stringify(airportCountries.value),
    )
  }

  function toggleAirportCountry(code) {
    const next = new Set(airportCountries.value)
    if (next.has(code)) next.delete(code)
    else next.add(code)
    setAirportCountries(Array.from(next))
  }

  function setAirportLabels(on) {
    airportLabels.value = Boolean(on)
    localStorage.setItem('aerorf:airport-labels', airportLabels.value ? '1' : '0')
  }

  function setWorkspaceWidth(px) {
    const w = Math.max(240, Math.min(Number(px) || 300, 520))
    workspaceWidth.value = w
    _remember('aerorf:workspace-width', w)
  }

  function setWorkspaceMode(mode) {
    if (!['open', 'collapsed', 'closed'].includes(mode)) return
    workspaceMode.value = mode
    _remember('aerorf:workspace-mode', mode)
  }

  function setWorkspaceSide(side) {
    if (!['left', 'right'].includes(side)) return
    workspaceSide.value = side
    _remember('aerorf:workspace-side', side)
  }

  function toggleWorkspacePinned() {
    workspacePinned.value = !workspacePinned.value
    _remember('aerorf:workspace-pinned', workspacePinned.value ? '1' : '0')
  }

  function setWorkspaceContext(context, { force = false } = {}) {
    if (!context || !['object', 'aircraft'].includes(context.type)) return false
    if (workspacePinned.value && workspaceContext.value && !force) {
      pendingWorkspaceContext.value = context
      return false
    }

    const normalized = context.type === 'object'
      ? { type: 'object', id: context.id }
      : { type: 'aircraft', icao24: String(context.icao24 || '').trim().toLowerCase() }
    if (normalized.type === 'object' && normalized.id == null) return false
    if (normalized.type === 'aircraft' && !normalized.icao24) return false

    workspaceContext.value = normalized
    pendingWorkspaceContext.value = null
    workspaceHistory.value = [
      normalized,
      ...workspaceHistory.value.filter((item) =>
        item.type !== normalized.type ||
        (item.type === 'object' ? item.id !== normalized.id : item.icao24 !== normalized.icao24),
      ),
    ].slice(0, 10)
    localStorage.setItem('aerorf:workspace-context', JSON.stringify(normalized))
    localStorage.setItem('aerorf:workspace-history', JSON.stringify(workspaceHistory.value))
    return true
  }

  function restoreWorkspaceContext(context) {
    return requestWorkspaceContext(context, { force: true })
  }

  function persistWorkspaceNavigation() {
    _remember('aerorf:workspace-category', workspaceCategory.value || '')
    _remember('aerorf:workspace-level', workspaceLevel.value)
    _remember('aerorf:workspace-section', workspaceSection.value)
    _remember('aerorf:workspace-task', workspaceTask.value)
  }

  function openWorkspaceHome() {
    workspaceLevel.value = 'home'
    workspaceCategory.value = null
    workspaceTask.value = ''
    persistWorkspaceNavigation()
    setWorkspaceMode('open')
    return true
  }

  function openWorkspaceCategory(category) {
    if (!WORKSPACE_CATEGORIES.has(category)) return false
    workspaceCategory.value = category
    workspaceLevel.value = 'category'
    workspaceTask.value = ''
    workspaceSection.value = category
    persistWorkspaceNavigation()
    setWorkspaceMode('open')
    return true
  }

  function openWorkspaceTask(section, { category = SECTION_CATEGORY[section], task = section } = {}) {
    if (!WORKSPACE_SECTIONS.has(section) || !WORKSPACE_CATEGORIES.has(category)) return false
    workspaceCategory.value = category
    workspaceSection.value = section
    workspaceTask.value = task
    workspaceLevel.value = 'task'
    persistWorkspaceNavigation()
    setWorkspaceMode('open')
    return true
  }

  function requestWorkspaceContext(context, { force = false } = {}) {
    if (!context || !['object', 'aircraft'].includes(context.type)) return false
    if (workspacePinned.value && workspaceContext.value && !force) {
      pendingWorkspaceContext.value = context
      return false
    }

    if (workspaceSection.value !== 'inspector' || workspaceLevel.value !== 'task') {
      workspaceReturnTarget.value = {
        category: workspaceCategory.value,
        level: workspaceLevel.value,
        section: workspaceSection.value,
        task: workspaceTask.value,
      }
    }
    if (!setWorkspaceContext(context, { force: true })) return false
    return openWorkspaceTask('inspector', { category: 'objects', task: 'inspector' })
  }

  function inspectPendingWorkspaceContext() {
    if (!pendingWorkspaceContext.value) return false
    return requestWorkspaceContext(pendingWorkspaceContext.value, { force: true })
  }

  function clearWorkspaceContext() {
    workspaceContext.value = null
    pendingWorkspaceContext.value = null
    localStorage.removeItem('aerorf:workspace-context')
    const previous = workspaceReturnTarget.value
    workspaceReturnTarget.value = null
    if (previous && WORKSPACE_CATEGORIES.has(previous.category)) {
      workspaceCategory.value = previous.category
      workspaceLevel.value = previous.level
      workspaceSection.value = previous.section
      workspaceTask.value = previous.task
      persistWorkspaceNavigation()
      setWorkspaceMode('open')
    } else {
      openWorkspaceHome()
    }
  }

  function toggleWorkspaceSection(section) {
    return setPanel(section)
  }

  function toggleWorkspaceMode() {
    if (workspaceMode.value === 'closed') setWorkspaceMode('open')
    else if (workspaceMode.value === 'open') setWorkspaceMode('collapsed')
    else setWorkspaceMode('open')
  }

  function setPanel(panel) {
    if (!WORKSPACE_SECTIONS.has(panel)) return false
    const category = SECTION_CATEGORY[panel]
    const task = panel === 'tools' ? 'tool-options' : panel
    return openWorkspaceTask(panel, { category, task })
  }

  const connected = computed(() => backendStatus.value === 'ok')
  const dbConnected = computed(() => dbStatus.value?.connected === true)

  async function checkBackend() {
    try {
      const status = await systemApi.status()
      backendStatus.value = status.status === 'ok' ? 'ok' : 'degradado'
      openskyStatus.value = status.opensky?.configured ? 'configurado' : 'sin configurar'
      dbStatus.value = status.database
      config.value = status
      lastCheck.value = new Date()
      return status
    } catch (e) {
      backendStatus.value = 'desconectado'
      openskyStatus.value = 'desconocido'
      lastCheck.value = new Date()
      return { error: describeError(e) }
    }
  }

  async function loadConfig() {
    try {
      const data = await systemApi.config()
      config.value = data.config
      return data.config
    } catch (e) {
      return null
    }
  }

  function setCursor(lat, lon) {
    if (lat === null || lon === null) {
      cursor.value = { lat: null, lon: null }
      return
    }
    cursor.value = { lat, lon }
  }

  function setCoordinateFormat(format) {
    coordinateFormat.value = format
    localStorage.setItem('aerorf:coord-format', format)
  }

  // ─── Dialogues and notices ──────────────────────────────────────────────────
  //
  // These replace `window.confirm` and `window.prompt`.
  //
  // The native ones are rendered by the browser, not by this application: they
  // carry the page's origin as their title, so the operator saw
  // "localhost:5199 dice..." above a system-styled box in the middle of an
  // otherwise institutional interface. It reads as a stray web page in the
  // middle of a tool, and it cannot be styled to match anything.
  //
  // `ask` returns a Promise because every call site is a question with a yes/no
  // answer, and `await` reads better than a callback at the call site:
  //
  //   if (await system.ask({ title: 'Eliminar', message: '…', danger: true })) …
  //
  // `notify` is for the outcome of something that has already happened and needs
  // no answer. It replaces the `window.prompt` that was used as a clipboard
  // fallback, where the "input" was always prefilled and never edited.
  const dialog = ref(null)
  let dialogResolve = null

  function ask({ title, message, confirmLabel = 'Aceptar', cancelLabel = 'Cancelar', danger = false } = {}) {
    // A second question while one is open answers the first: the operator did
    // something else, and leaving the first pending would strand its `await`.
    if (dialogResolve) dialogResolve(false)
    dialog.value = { title, message, confirmLabel, cancelLabel, danger }
    return new Promise((resolve) => {
      dialogResolve = resolve
    })
  }

  function answerDialog(value) {
    const resolve = dialogResolve
    dialog.value = null
    dialogResolve = null
    resolve?.(value)
  }

  const notice = ref(null)
  let noticeTimer = null

  function notify(text, { kind = 'info', ms = 2600 } = {}) {
    notice.value = { text, kind, id: Date.now() }
    if (noticeTimer) clearTimeout(noticeTimer)
    noticeTimer = setTimeout(() => {
      notice.value = null
      noticeTimer = null
    }, ms)
  }

  function dismissNotice() {
    if (noticeTimer) clearTimeout(noticeTimer)
    noticeTimer = null
    notice.value = null
  }

  return {
    backendStatus, openskyStatus, dbStatus, config, lastCheck,
    connected, dbConnected, checkBackend, loadConfig,
    cursor, coordinateFormat, setCursor, setCoordinateFormat,
    setPanel,
    workspaceMode, workspaceSection, workspaceCategory, workspaceLevel, workspaceTask,
    workspaceSide, workspaceWidth, workspacePinned,
    workspaceContext, workspaceHistory, setWorkspaceMode, setWorkspaceSide,
    setWorkspaceWidth, toggleWorkspacePinned, setWorkspaceContext,
    pendingWorkspaceContext, workspaceReturnTarget, restoreWorkspaceContext,
    requestWorkspaceContext, inspectPendingWorkspaceContext, clearWorkspaceContext,
    openWorkspaceHome, openWorkspaceCategory, openWorkspaceTask, toggleWorkspaceSection,
    toggleWorkspaceMode,
    dialog, ask, answerDialog, notice, notify, dismissNotice,
    showTimeline,
    airportCountries, airportLabels, setAirportCountries, toggleAirportCountry,
    setAirportLabels,
  }
})
