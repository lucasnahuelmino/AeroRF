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
  // The map is the point of the application, so the two side panels are
  // sized well under a third of the viewport between them and both can be
  // collapsed to give the map the whole width. The widths are remembered
  // because an operator who works at a particular size should not have to
  // drag the edges again on every reload.
  const _num = (key, fallback, min, max) => {
    const raw = Number(localStorage.getItem(key))
    return Number.isFinite(raw) && raw >= min ? Math.min(raw, max) : fallback
  }
  const _remember = (key, value) => localStorage.setItem(key, String(value))

  const sidebarOpen = ref(localStorage.getItem('aerorf:sidebar-open') !== '0')
  const leftPanel = ref('tools')
  const sidebarWidth = ref(_num('aerorf:sidebar-width', 268, 220, 460))

  const inspectorOpen = ref(localStorage.getItem('aerorf:inspector-open') !== '0')
  const inspectorWidth = ref(_num('aerorf:inspector-width', 300, 260, 520))

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

  function setSidebarWidth(px) {
    const w = Math.max(220, Math.min(Number(px) || 268, 460))
    sidebarWidth.value = w
    _remember('aerorf:sidebar-width', w)
  }

  function setInspectorWidth(px) {
    const w = Math.max(260, Math.min(Number(px) || 300, 520))
    inspectorWidth.value = w
    _remember('aerorf:inspector-width', w)
  }

  function toggleInspector() {
    inspectorOpen.value = !inspectorOpen.value
    localStorage.setItem('aerorf:inspector-open', inspectorOpen.value ? '1' : '0')
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

  function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
    localStorage.setItem('aerorf:sidebar-open', sidebarOpen.value ? '1' : '0')
  }

  function setPanel(panel) {
    if (leftPanel.value === panel && sidebarOpen.value) {
      toggleSidebar()
      return
    }
    leftPanel.value = panel
    sidebarOpen.value = true
    localStorage.setItem('aerorf:sidebar-open', '1')
  }

  return {
    backendStatus, openskyStatus, dbStatus, config, lastCheck,
    connected, dbConnected, checkBackend, loadConfig,
    cursor, coordinateFormat, setCursor, setCoordinateFormat,
    sidebarOpen, leftPanel, sidebarWidth, setSidebarWidth, setPanel, toggleSidebar,
    inspectorOpen, inspectorWidth, setInspectorWidth, toggleInspector,
    showTimeline,
    airportCountries, airportLabels, setAirportCountries, toggleAirportCountry,
    setAirportLabels,
  }
})
