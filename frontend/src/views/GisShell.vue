<template>
  <div class="gis-shell">
    <!--
      The section menu is BrandBar, rendered by App.vue above this. It is thin
      here too, so the map keeps its height budget, and it is present on every
      section, which is what makes the application navigable.
    -->
    <!-- ── Toolbar (spec §3, §6) ─────────────────────────────────────────── -->
    <header class="gis-toolbar">
      <!-- Brand. The section menu and the way back to the panel are in
           BrandBar, one click up, on every screen. Repeating them here
           stacked two navigation bars on top of each other. -->
      <div class="gis-brand">
        <span class="gis-mode-label hidden lg:inline">{{ modeLabel }}</span>
      </div>

      <!-- Drawing and measurement tools. `type="button"` because a bare
           button inside any form is a submit button, and clicking one that
           submits does not look like pressing a tool. -->
      <div class="gis-toolstrip" role="toolbar" aria-label="Herramientas de dibujo">
        <button
          v-for="tool in tools"
          :key="tool.id"
          type="button"
          class="gis-tool"
          :class="{ active: mapStore.activeTool === tool.id }"
          :title="`${tool.label} — ${tool.hint}`"
          :aria-pressed="mapStore.activeTool === tool.id"
          :aria-label="tool.label"
          @click="activateTool(tool.id)"
        >
          <span class="gis-tool-icon" aria-hidden="true">{{ tool.icon }}</span>
          <span class="gis-tool-label">{{ tool.label }}</span>
        </button>
      </div>

      <!-- The hint is the tool's own instruction. It sits in the middle of the
           free space so it never competes with the tools for room. -->
      <div class="gis-hint" :class="{ 'gis-hint-on': mapStore.toolHint }">
        {{ mapStore.toolHint || ' ' }}
      </div>

      <!-- Right-hand actions -->
      <div class="gis-actions">
        <div class="gis-status" title="Estado del backend">
          <span class="gis-dot" :class="systemStore.connected ? 'ok' : 'bad'" />
          <span class="gis-status-label">Backend</span>
        </div>
        <div class="gis-status" title="Credenciales de OpenSky">
          <span class="gis-dot" :class="flightsStore.openskyConfigured ? 'ok' : 'warn'" />
          <span class="gis-status-label">OpenSky</span>
        </div>
        <div class="gis-status" title="Canal de vuelo en vivo">
          <span class="gis-dot" :class="flightsStore.socketState === 'connected' ? 'ok' : 'off'" />
          <span class="gis-status-label">Vivos</span>
        </div>

        <span class="gis-divider" />

        <button
          class="gis-icon-btn"
          :class="{ active: systemStore.sidebarOpen }"
          :title="systemStore.sidebarOpen ? 'Ocultar panel izquierdo' : 'Mostrar panel izquierdo'"
          @click="systemStore.toggleSidebar()"
        >
          ▤
        </button>
        <button
          class="gis-icon-btn"
          :class="{ active: systemStore.inspectorOpen }"
          :title="systemStore.inspectorOpen ? 'Ocultar inspector' : 'Mostrar inspector'"
          @click="systemStore.toggleInspector()"
        >
          ▥
        </button>
        <button class="gis-icon-btn" title="Ayuda" @click="showHelp = !showHelp">?</button>
      </div>
    </header>

    <!-- ── Body: tools | map | inspector (spec §3) ───────────────────────── -->
    <div class="gis-body">
      <!-- Left: tools / layers / flights -->
      <aside
        v-if="systemStore.sidebarOpen"
        class="gis-sidebar"
        :style="{ width: `${systemStore.sidebarWidth}px` }"
      >
        <nav class="gis-tabs">
          <button
            v-for="tab in sideTabs"
            :key="tab.id"
            class="gis-tab"
            :class="{ active: systemStore.leftPanel === tab.id }"
            :title="`Panel ${tab.label}`"
            @click="systemStore.setPanel(tab.id)"
          >
            {{ tab.label }}
          </button>
        </nav>

        <div class="gis-sidebar-body">
          <ToolOptions v-if="systemStore.leftPanel === 'tools'" />
          <LayerPanel v-else-if="systemStore.leftPanel === 'layers'" />
          <FlightPanel v-else-if="systemStore.leftPanel === 'flights'" />
          <AirportPanel
            v-else-if="systemStore.leftPanel === 'airports'"
            :visible="airportsVisible"
            :labels="systemStore.airportLabels"
            :armed="airportMeasureArmed"
            :result="airportMeasureResult"
            @update:visible="setAirportsVisible"
            @update:labels="systemStore.setAirportLabels"
            @toggle-country="systemStore.toggleAirportCountry"
            @zoom="zoomToAirports()"
            @measure="armAirportMeasure"
          />
          <ExpedientePanel v-else-if="systemStore.leftPanel === 'expediente'" />
        </div>

        <!-- Drag handle: the map is the point, so the operator decides how
             much of the window the panel gets. -->
        <div
          class="gis-resizer gis-resizer-r"
          role="separator"
          aria-orientation="vertical"
          :aria-valuenow="systemStore.sidebarWidth"
          title="Arrastrar para ajustar el ancho"
          @pointerdown="startResize($event, 'sidebar')"
        />
      </aside>

      <!-- Map -->
      <main class="gis-map-area">
        <div ref="mapContainer" class="gis-map" />

        <!-- Map overlays -->
        <div class="pointer-events-none absolute inset-0">
          <!-- Distance readout while measuring -->
          <div
            v-if="measure.active && measure.segment_count > 0"
            class="pointer-events-auto absolute top-3 left-3 rounded-lg border border-amber-500/40 bg-slate-950/95 px-3 py-2 text-xs shadow-xl"
          >
            <div class="mb-1 text-[10px] uppercase tracking-widest text-amber-400">
              Medición
            </div>
            <div class="font-mono text-amber-200 text-sm">{{ measure.total_label }}</div>
            <div class="mt-0.5 text-[10px] text-slate-500">
              {{ measure.points.length }} puntos · {{ measure.segment_count }} tramos
            </div>
            <div v-if="measure.area_note" class="text-[10px] text-slate-500">
              Área ≈ {{ measure.area_note.toFixed(2) }} km²
            </div>
            <ul v-if="measure.segments.length" class="mt-1.5 space-y-0.5">
              <li
                v-for="seg in measure.segments"
                :key="seg.index"
                class="font-mono text-[10px] text-slate-400"
              >
                {{ String.fromCharCode(65 + seg.index) }}→{{ String.fromCharCode(66 + seg.index) }}
                {{ seg.label }} · {{ seg.bearing.toFixed(0) }}°
              </li>
            </ul>
            <div class="mt-2 flex gap-1">
              <button class="gis-mini-btn" @click="measureEngine?.undo()">↶</button>
              <button class="gis-mini-btn" @click="saveMeasurement">Guardar</button>
              <button class="gis-mini-btn" @click="measureEngine?.stop()">✕</button>
            </div>
          </div>

          <!-- Draft preview readout -->
          <div
            v-if="draftPreview"
            class="pointer-events-auto absolute top-3 left-1/2 -translate-x-1/2 rounded-lg border border-blue-500/40 bg-slate-950/95 px-3 py-2 text-xs shadow-xl"
          >
            <div class="text-[10px] uppercase tracking-widest text-blue-400 mb-1">
              {{ draftPreview.label }}
            </div>
            <div class="font-mono text-blue-200">{{ draftPreview.value }}</div>
            <div class="mt-1.5 flex gap-1">
              <button class="gis-mini-btn" @click="confirmDraft">Confirmar</button>
              <button class="gis-mini-btn" @click="mapStore.cancelTool()">Cancelar</button>
            </div>
          </div>

          <!-- Object quick actions -->
          <div
            v-if="mapStore.selected"
            class="pointer-events-auto absolute bottom-3 left-3 flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-950/95 px-2 py-1.5 shadow-xl"
          >
            <span class="text-[11px] text-slate-300 max-w-[16rem] truncate">
              {{ mapStore.selected.name || typeName(mapStore.selected.type) }}
            </span>
            <span class="w-px h-4 bg-slate-700" />
            <button
              class="gis-mini-btn"
              title="Medir desde este objeto hasta el cursor"
              @click="measureFromSelected"
            >
              ↔
            </button>
            <button class="gis-mini-btn" title="Centrar" @click="centerSelected">⊙</button>
            <button class="gis-mini-btn" title="Duplicar" @click="mapStore.duplicateObject(mapStore.selected.id)">⧉</button>
            <button class="gis-mini-btn" title="Ocultar" @click="toggleSelectedVisibility">
              {{ mapStore.selected.visible ? '👁' : '🚫' }}
            </button>
            <button class="gis-mini-btn danger" title="Eliminar" @click="confirmDelete">🗑</button>
          </div>

          <!-- Loading -->
          <div
            v-if="mapStore.loading"
            class="pointer-events-none absolute inset-0 flex items-center justify-center bg-slate-950/40"
          >
            <div class="rounded-lg bg-slate-950/95 px-4 py-2 text-sm text-slate-300 shadow-xl">
              Cargando objetos…
            </div>
          </div>
        </div>

        <!-- Right-click menu (spec §45) -->
        <ContextMenu />
      </main>

      <!-- Right: inspector (spec §9) -->
      <aside
        v-if="systemStore.inspectorOpen"
        class="gis-inspector"
        :style="{ width: `${systemStore.inspectorWidth}px` }"
      >
        <div
          class="gis-resizer gis-resizer-l"
          role="separator"
          aria-orientation="vertical"
          :aria-valuenow="systemStore.inspectorWidth"
          title="Arrastrar para ajustar el ancho"
          @pointerdown="startResize($event, 'inspector')"
        />
        <InspectorPanel />
      </aside>
    </div>

    <!-- ── Status bar: cursor, coordinates, scale, time (spec §5, §28) ────── -->
    <CoordinateBar />

    <!-- Timeline (spec §28) -->
    <Timeline v-if="systemStore.showTimeline" />

    <!-- Toasts -->
    <div class="pointer-events-none fixed bottom-14 right-4 z-[1200] flex flex-col gap-2">
      <div
        v-if="mapStore.error"
        class="pointer-events-auto rounded-lg border border-rose-700 bg-rose-950/95 px-3 py-2 text-xs text-rose-200 shadow-xl max-w-md"
      >
        <div class="flex items-start gap-2">
          <span class="flex-1">{{ mapStore.error }}</span>
          <button class="text-rose-400 hover:text-rose-200" @click="mapStore.dismiss()">✕</button>
        </div>
      </div>
      <div
        v-if="mapStore.notice"
        class="pointer-events-auto rounded-lg border border-emerald-800 bg-emerald-950/95 px-3 py-2 text-xs text-emerald-200 shadow-xl"
      >
        <div class="flex items-start gap-2">
          <span class="flex-1">{{ mapStore.notice }}</span>
          <button class="text-emerald-400 hover:text-emerald-200" @click="mapStore.dismiss()">✕</button>
        </div>
      </div>
      <div
        v-if="flightsStore.throttled"
        class="pointer-events-auto rounded-lg border border-amber-700 bg-amber-950/95 px-3 py-2 text-xs text-amber-200 shadow-xl max-w-md"
      >
        Límite de créditos de OpenSky. Reintento en
        {{ flightsStore.throttled.retry_after_s }}s.
      </div>
    </div>

    <!-- Help -->
    <div
      v-if="showHelp"
      class="fixed inset-0 z-[1300] flex items-center justify-center bg-slate-950/80 p-6"
      @click.self="showHelp = false"
    >
      <div class="max-w-2xl rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
        <h2 class="mb-3 text-lg font-semibold text-slate-100">AeroRF — ayuda rápida</h2>
        <div class="grid gap-4 text-sm text-slate-300 md:grid-cols-2">
          <div>
            <h3 class="mb-1 font-semibold text-slate-200">Atajos</h3>
            <ul class="space-y-1 text-xs">
              <li><kbd>ESC</kbd> — cancelar la herramienta activa</li>
              <li><kbd>Enter</kbd> — confirmar el dibujo en curso</li>
              <li><kbd>Retroceso</kbd> — quitar el último vértice</li>
              <li>Clic derecho — menú contextual en el mapa</li>
            </ul>
          </div>
          <div>
            <h3 class="mb-1 font-semibold text-slate-200">Capas de datos</h3>
            <ul class="space-y-1 text-xs">
              <li><b>Histórico</b> — track del vuelo en OpenSky</li>
              <li><b>En vivo</b> — vector de estado actual</li>
              <li><b>AeroRF</b> — grabado por esta herramienta</li>
              <li><b>Calculado</b> — derivado por el sistema</li>
            </ul>
          </div>
        </div>
        <p class="mt-4 rounded-lg border border-amber-800 bg-amber-950/40 p-3 text-xs text-amber-200">
          AeroRF no inventa posiciones. Cuando un dato no existe, muestra «dato no
          disponible». La correlación espacial entre aeronave y evento RF
          <b>no implica causalidad</b>.
        </p>
        <button class="gis-btn-primary mt-4" @click="showHelp = false">Cerrar</button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * views/GisShell.vue
 * ──────────────────
 * The map-centric shell (spec §3).
 *
 *   TOOLBAR
 *   ┌──────────┬──────────────────────────┬──────────┐
 *   │ HERRAMIENTAS│      MAPA (Leaflet)      │ INSPECTOR│
 *   └──────────┴──────────────────────────┴──────────┘
 *   CAPAS / COORDENADAS / TIEMPO
 *
 * All cartographic work lives in MapEngine / ToolManager / MeasureEngine;
 * this component only wires their events to the stores and renders the
 * panels. That split is what keeps the map logic reusable and testable.
 */
import { computed, markRaw, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import MapEngine from '@/map/MapEngine'
import { ToolManager, TOOLS, TOOL_META } from '@/map/draw'
import { MeasureEngine } from '@/map/measure'
import { AircraftRenderer } from '@/map/aircraft'
import { AirportLayer, AIRPORT_LAYER_KEY } from '@/map/airports'
import { useMapStore, typeName } from '@/stores/map'
import { useFlightsStore } from '@/stores/flights'
import { useSystemStore } from '@/stores/system'
import { useExpedientesStore } from '@/stores/expedientes'

import CoordinateBar from '@/components/gis/CoordinateBar.vue'
import ContextMenu from '@/components/gis/ContextMenu.vue'
import FlightPanel from '@/components/gis/FlightPanel.vue'
import InspectorPanel from '@/components/gis/InspectorPanel.vue'
import LayerPanel from '@/components/gis/LayerPanel.vue'
import Timeline from '@/components/gis/Timeline.vue'
import ToolOptions from '@/components/gis/ToolOptions.vue'
import ExpedientePanel from '@/components/gis/ExpedientePanel.vue'
import AirportPanel from '@/components/gis/AirportPanel.vue'

const router = useRouter()
const mapStore = useMapStore()
const flightsStore = useFlightsStore()
const systemStore = useSystemStore()
const expedientesStore = useExpedientesStore()

const mapContainer = ref(null)
const showHelp = ref(false)
const draftPreview = ref(null)
const measure = ref({ active: false, segment_count: 0, points: [], total_label: '—', area_note: null, segments: [] })

let engine = null
let toolManager = null
let measureEngine = null
let aircraftRenderer = null
let airportLayer = null
const unsubscribers = []

// Aerodrome layer state the shell owns and passes down as props, so the
// panel stays a plain view of it.
const airportsVisible = ref(true)
const airportMeasureArmed = ref(false)
const airportMeasureCode = ref(null)
const airportMeasureResult = ref(null)

const tools = computed(() =>
  Object.entries(TOOL_META).map(([id, meta]) => ({ id, ...meta })),
)

const sideTabs = [
  { id: 'tools', label: 'Herramientas' },
  { id: 'layers', label: 'Capas' },
  { id: 'flights', label: 'Vuelos' },
  { id: 'airports', label: 'Aeropuertos' },
  { id: 'expediente', label: 'Expediente' },
]

// ─── Panel resizing ──────────────────────────────────────────────────────────
// The map is the working surface, so how much window the side panels take is
// the operator's call, not a constant baked into the stylesheet. Pointer
// capture keeps the drag alive even when the cursor leaves the 4px handle.
function startResize(event, which) {
  if (event.button !== undefined && event.button !== 0) return
  event.preventDefault()
  const startX = event.clientX
  const startW =
    which === 'sidebar' ? systemStore.sidebarWidth : systemStore.inspectorWidth

  const move = (e) => {
    const delta = which === 'sidebar' ? e.clientX - startX : startX - e.clientX
    if (which === 'sidebar') systemStore.setSidebarWidth(startW + delta)
    else systemStore.setInspectorWidth(startW + delta)
  }
  const stop = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', stop)
    window.removeEventListener('pointercancel', stop)
    document.body.style.removeProperty('cursor')
    document.body.style.removeProperty('user-select')
  }
  document.body.style.setProperty('cursor', 'col-resize')
  document.body.style.setProperty('user-select', 'none')
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stop)
  window.addEventListener('pointercancel', stop)
}

const modeLabel = computed(() => {
  if (flightsStore.openskyConfigured) return 'GIS · Vuelos en vivo'
  return 'GIS · Modo sin conexión OpenSky'
})

// ─── Boot ────────────────────────────────────────────────────────────────────

onMounted(async () => {
  engine = markRaw(new MapEngine({ container: mapContainer.value }))
  engine.init()
  mapStore.attachEngine(engine)

  toolManager = markRaw(
    new ToolManager(engine, {
      onComplete: handleToolComplete,
      onPreview: handleToolPreview,
      onChange: (payload) => {
        mapStore.activeTool = payload.tool
        mapStore.toolHint = payload.hint
        mapStore.draft = payload.draft
        if (payload.tool === TOOLS.MEASURE) {
          // The measure tool is handled by MeasureEngine, not the drafter.
          measureEngine.start()
        } else {
          measureEngine.stop()
        }
      },
    }),
  )
  mapStore.toolManager = toolManager

  measureEngine = markRaw(
    new MeasureEngine(engine, {
      onChange: (value) => {
        measure.value = value
      },
    }),
  )
  mapStore.measureEngine = measureEngine

  // Aircraft: live markers and provenance-coloured tracks (spec §21–§23).
  aircraftRenderer = markRaw(
    new AircraftRenderer(engine, {
      onSelect: (icao24) => {
        flightsStore.selectedIcao24 = icao24
        flightsStore.loadAircraftDistances(icao24)
      },
    }),
  )
  mapStore.aircraftRenderer = aircraftRenderer

  // Aerodrome reference points (spec §38). Not persisted: the ARP positions
  // come from `data/airports.js`, so showing or hiding the layer touches
  // nothing in the database and no reference point can be mistaken for
  // something the operator drew.
  airportLayer = markRaw(new AirportLayer(engine)).init()
  // Honour the persisted layer visibility, so "Aeropuertos off" survives a
  // reload like every other layer.
  const airportsLayer = mapStore.layerByKey(AIRPORT_LAYER_KEY)
  airportsVisible.value = airportsLayer ? airportsLayer.visible !== false : true
  airportLayer.setVisible(airportsVisible.value)
  airportLayer.setCountries(systemStore.airportCountries)
  airportLayer.setLabels(systemStore.airportLabels)

  bindEngineEvents()
  bindGlobalKeys()

  await Promise.all([
    systemStore.checkBackend(),
    flightsStore.probeBackend(),
    mapStore.bootstrap(),
    expedientesStore.fetchExpedientes(),
  ])

  flightsStore.loadWatchlist()
  flightsStore.connectSocket()
})

onBeforeUnmount(() => {
  unsubscribers.forEach((fn) => fn())
  flightsStore.disconnectSocket()
  toolManager?.cancel()
  aircraftRenderer?.clear()
  engine?.destroy()
  engine = null
})

function bindEngineEvents() {
  // Cursor coordinates — this is what finally makes the header field live.
  unsubscribers.push(
    engine.on('cursor', (latlng) => {
      mapStore.setCursor(latlng)
      systemStore.setCursor(latlng?.lat ?? null, latlng?.lng ?? null)
    }),
  )

  unsubscribers.push(
    engine.on('click', ({ latlng }) => {
      mapStore.captureClick(latlng)

      // A pending airport measurement takes priority over any active tool:
      // the operator asked for a distance, not for a shape.
      if (airportMeasureArmed.value) {
        airportMeasureResult.value = measureFromAirport(airportMeasureCode.value, latlng)
        clearAirportMeasure()
        return
      }

      // ── One owner per click ────────────────────────────────────────────
      // The ToolManager subscribes to the map's click event itself, so it
      // already handles the tools. The shell used to handle them too, and
      // both ran on every click: the shell sized and committed the circle,
      // then the manager's own handler saw the tool still armed and started a
      // second one. The result was a circle that never kept the size the
      // operator chose, and a tool that could not be left.
      //
      // So the shell stops interpreting clicks for the drawing tools. It only
      // handles the two cases the manager does not own: a pending airport
      // measurement, and clearing the selection with the select tool.
      if (airportMeasureArmed.value) {
        airportMeasureResult.value = measureFromAirport(airportMeasureCode.value, latlng)
        clearAirportMeasure()
        return
      }
      if (toolManager?.active === TOOLS.SELECT) {
        mapStore.clearSelection()
      }
      // Every other tool, including measurement, is the manager's business.
      // Returning without acting is correct: it has already run.
    }),
  )

  unsubscribers.push(
    engine.on('mousemovepreview', (latlng) => {
      if (toolManager?.isDrawing) toolManager.previewAt(latlng)
    }),
  )

  unsubscribers.push(
    engine.on('contextmenu', (payload) => mapStore.openContextMenu(payload)),
  )

  unsubscribers.push(
    engine.on('objectdblclick', ({ id }) => {
      mapStore.select(id)
      systemStore.setPanel('layers')
    }),
  )

  // Leaflet's own mousemove drives the shape previews, and the live distance
  // readout for a measurement. Both are previews: nothing is stored until a
  // click.
  engine.map.on('mousemove', (e) => {
    if (toolManager?.isDrawing) {
      toolManager.previewAt(e.latlng)
      return
    }
    if (measureEngine?.active && measureEngine.points?.length) {
      measureEngine.previewToPoint(e.latlng)
    }
  })
}

function bindGlobalKeys() {
  const onKey = (event) => {
    if (event.target?.tagName === 'INPUT' || event.target?.tagName === 'TEXTAREA') return
    if (event.key === 'Escape') {
      mapStore.cancelTool()
      measureEngine?.stop()
      clearAirportMeasure()
      mapStore.closeContextMenu()
    }
    if (event.key === 'Enter' && toolManager?.draft) {
      handleDraftConfirm()
    }
  }
  window.addEventListener('keydown', onKey)
  unsubscribers.push(() => window.removeEventListener('keydown', onKey))
}

// ─── Tool interaction ────────────────────────────────────────────────────────

// Aerodrome reference layer controls (spec section 38).
//
// The layer is driven from the layer panel and from the context menu, so the
// shell is the one place that knows about both. It is not persisted as
// objects: the ARP positions come from `data/airports.js`, so showing it,
// hiding it or filtering it changes nothing in the database.

watch(
  () => systemStore.airportCountries.slice(),
  (codes) => airportLayer?.setCountries(codes),
)

watch(
  () => systemStore.airportLabels,
  (on) => airportLayer?.setLabels(on),
)

/** Show or hide the aerodrome layer. */
function setAirportsVisible(visible) {
  airportsVisible.value = Boolean(visible)
  airportLayer?.setVisible(airportsVisible.value)
  // Keep the layer record in step, so the layer panel and this panel cannot
  // disagree about whether the aerodromes are drawn.
  const layer = mapStore.layerByKey(AIRPORT_LAYER_KEY)
  if (layer && layer.visible !== airportsVisible.value) {
    mapStore.toggleLayer(AIRPORT_LAYER_KEY, airportsVisible.value)
  }
}

/** Fit the map to the aerodromes currently in view. */
function zoomToAirports(country = null) {
  airportLayer?.fitTo({ country })
}

/** Wait for the next map click to be measured from an aerodrome. */
function armAirportMeasure(code) {
  airportMeasureCode.value = code
  airportMeasureArmed.value = true
  airportMeasureResult.value = null
  airportLayer?.removeMeasure('airport-distance')
  mapStore.toolHint = `Haga clic en el destino para medir desde ${code}`
  // Move to the map so the operator is not typing at a panel while the map
  // waits for a click.
  mapStore.setTool(TOOLS.SELECT)
}

/**
 * Distance from an aerodrome to a point, drawn on the map.
 *
 * The line is a draft layer, not a stored object: it is a reading, and
 * nothing enters `map_objects` unless the operator saves it deliberately.
 */
function measureFromAirport(code, latlng) {
  if (!airportLayer || latlng == null) return null
  const result = airportLayer.measureFrom(code, latlng.lat, latlng.lng)
  if (!result) {
    mapStore.notice =
      `No se reconoce el aeropuerto "${code}". Se aceptan codigos ICAO e IATA.`
    return null
  }
  airportLayer.drawMeasure('airport-distance', result, [latlng.lat, latlng.lng])
  mapStore.notice =
    `${result.airport.icao} al punto: ${result.km.toFixed(2)} km ` +
    `(${result.nm.toFixed(2)} NM), rumbo ${result.bearing.toFixed(0)} grados ${result.bearing_cardinal}.`
  return result
}

/** Drop the airport distance line and stop waiting for a click. */
function clearAirportMeasure() {
  airportMeasureArmed.value = false
  airportMeasureCode.value = null
  airportLayer?.removeMeasure('airport-distance')
  if (mapStore.toolHint?.startsWith('Haga clic en el destino')) {
    mapStore.toolHint = ''
  }
}

function activateTool(id) {
  if (id === TOOLS.MEASURE) {
    measureEngine.start()
    toolManager.activate(TOOLS.MEASURE)
    return
  }
  measureEngine.stop()
  toolManager.activate(id, mapStore.toolOptions)
}

function handleToolPreview(payload) {
  if (payload.type === 'circle') {
    draftPreview.value = {
      label: 'Círculo',
      value: `${payload.radius?.toFixed(2)} ${payload.unit?.toUpperCase()}`,
    }
  } else if (payload.type === 'radial') {
    draftPreview.value = {
      label: 'Radial',
      value: `${payload.azimuth?.toFixed(1)}° · ${payload.length?.toFixed(2)} ${payload.unit?.toUpperCase()}`,
    }
  } else if (payload.type === 'measure') {
    draftPreview.value = null
  } else {
    draftPreview.value = null
  }
}

function handleDraftConfirm() {
  if (toolManager?.active === TOOLS.CIRCLE) toolManager.commitCircle()
  else if (toolManager?.active === TOOLS.RADIAL) toolManager.commitRadial()
  else toolManager.finish()
}

/** Persist whatever the tool just finished drawing. */
async function handleToolComplete(payload) {
  draftPreview.value = null
  const defaults = {
    point: { name: `Punto ${new Date().toLocaleTimeString('es-AR')}`, category: 'Referencia' },
    annotation: { name: 'Anotación', category: 'Referencia' },
    circle: { name: 'Círculo' },
    radial: { name: 'Radial' },
    trace: { name: 'Traza' },
    line: { name: 'Línea' },
    polygon: { name: 'Polígono' },
    coverage: { name: 'Cobertura' },
    measurement: { name: 'Medición' },
  }

  await mapStore.createObject({
    ...defaults[payload.type],
    ...payload,
  })
  systemStore.setPanel('tools')
}

function saveMeasurement() {
  const payload = measureEngine?.toObjectPayload()
  if (payload) {
    mapStore.createObject({ ...payload, name: `Medición ${new Date().toLocaleTimeString('es-AR')}` })
  }
  measureEngine.stop()
  toolManager.deactivate()
}

// ─── Object actions ─────────────────────────────────────────────────────────

function centerSelected() {
  engine?.fitObject(mapStore.selected)
}

/**
 * Measure from the selected object to wherever the pointer is.
 *
 * The object is already on the map, so its position is the origin and the
 * pointer is free to show the distance instead of placing it. This is the
 * question an operator actually asks: how far is the source from the runway.
 */
function measureFromSelected() {
  const obj = mapStore.selected
  if (!obj || obj.latitude == null || obj.longitude == null) {
    mapStore.notice = 'El objeto seleccionado no tiene posición.'
    return
  }
  measureEngine?.start()
  measureEngine.fromOrigin(
    { lat: obj.latitude, lng: obj.longitude },
    obj.name || typeName(obj.type),
  )
  toolManager?.deactivate()
  mapStore.activeTool = TOOLS.MEASURE
  mapStore.toolHint =
    'Mueva el puntero para ver la distancia. Clic para fijarla, Esc para terminar.'
}

function toggleSelectedVisibility() {
  const obj = mapStore.selected
  if (!obj) return
  mapStore.updateObject(obj.id, { visible: !obj.visible })
}

function confirmDelete() {
  const obj = mapStore.selected
  if (!obj) return
  // eslint-disable-next-line no-alert
  if (window.confirm(`¿Eliminar «${obj.name || typeName(obj.type)}»? Esta acción no se puede deshacer.`)) {
    mapStore.deleteObject(obj.id, true)
  }
}

// The measure readout needs no watcher: MeasureEngine already calls its
// `onChange` handler, which assigns `measure.value` directly.
//
// There was a watcher here that did the opposite — it observed `measure.value`
// and assigned a copy of it back. A reactive effect that mutates its own
// dependency never converges: Vue stops after a hundred updates and throws
// "Maximum recursive updates exceeded". It fired on the first click of any
// tool, because `activate` emits a change, and the failure surfaced as a
// broken toolbar rather than as a misbehaving watcher.

// ─── Live aircraft on the map (spec §23) ────────────────────────────────────

// Redraw markers whenever the WebSocket delivers new states.
watch(
  () => flightsStore.liveStates,
  (states) => {
    if (!aircraftRenderer) return
    const tracked = flightsStore.watchlist
    const colors = Object.fromEntries(
      tracked.map((slot) => [slot.icao24, slot.color || flightsStore.colorForSlot(slot.slot)]),
    )

    Object.entries(states || {}).forEach(([icao24, state]) => {
      const slot = tracked.find((s) => s.icao24 === icao24)
      if (slot && slot.show_marker === false) return
      aircraftRenderer.updateAircraft(state, colors[icao24] || '#22c55e')
    })
    aircraftRenderer.syncMarkers(Object.keys(states || {}))
  },
  { deep: true },
)

// Redraw the aircraft trajectories (spec §21).
//
// Every cached trajectory is drawn, not just the most recent one. The map
// keeps a layer per aircraft, so several routes stay on screen together,
// which is what makes them comparable. An aircraft whose `show_track` is off
// is not drawn; one that has left the watchlist is removed from the map.
watch(
  () => [flightsStore.tracks, flightsStore.watchlist],
  () => {
    if (!aircraftRenderer) return
    const slots = new Map((flightsStore.watchlist || []).map((s) => [String(s.icao24).toLowerCase(), s]))
    const drawn = new Set()

    flightsStore.allTracks().forEach(({ icao24, data }) => {
      const slot = slots.get(icao24)
      if (!slot) {
        // No longer tracked: its path has no business staying on the map.
        aircraftRenderer.removeTrack(icao24)
        return
      }
      if (slot.show_track === false) {
        aircraftRenderer.removeTrack(icao24)
        return
      }
      drawn.add(icao24)
      const color = slot.color || flightsStore.colorForSlot(slot.slot ?? 0)
      aircraftRenderer.drawTrack({ ...data, icao24 }, color)
    })

    // Anything left over belongs to an aircraft that is gone from the cache.
    aircraftRenderer.tracks.forEach((_layer, key) => {
      if (!drawn.has(String(key).toLowerCase())) aircraftRenderer.removeTrack(key)
    })
  },
  { deep: true },
)
</script>

<style scoped>
/* ─── Shell ─────────────────────────────────────────────────────────────────
 * Proportions, in order of importance:
 *   - the map takes every pixel the panels do not need
 *   - the toolbar is 46px: tall enough for a comfortable tool button with an
 *     icon and a readable label, short enough to stay out of the way
 *   - the side panels are defaults, not constants. Both collapse, and both
 *     are draggable, so the working area belongs to the operator.
 * ------------------------------------------------------------------------- */

.gis-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  background: #020617;
  color: #e2e8f0;
  overflow: hidden;
}

.gis-toolbar {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  height: 46px;
  flex: 0 0 46px;
  padding: 0 0.625rem;
  background: #0b1220;
  border-bottom: 1px solid #1e293b;
  z-index: 1100;
  /* The tool strip is allowed to scroll rather than push the status pills
     off the edge on a narrow window. min-width:0 is what makes that
     possible inside a flex row. */
  min-width: 0;
  /* Every control in the bar is a button, not selectable text. Without this,
     clicking the same tool twice selects its label, and the selection
     highlight makes a working button look broken. */
  user-select: none;
  -webkit-user-select: none;
  touch-action: manipulation;
}

/* ─── Brand ──────────────────────────────────────────────────────────────── */

.gis-brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding-right: 0.625rem;
  border-right: 1px solid #1e293b;
  flex: 0 0 auto;
}

/* The brand name. Hidden until there is room, so it never squeezes the
   tools on a laptop. */
.gis-mode-label {
  font-size: 0.5625rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #64748b;
  white-space: nowrap;
}

/* ─── Tool strip ────────────────────────────────────────────────────────── */

.gis-toolstrip {
  display: flex;
  align-items: center;
  gap: 0.125rem;
  flex: 0 1 auto;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
  padding: 3px 0;
  /* The strip is a scroll container, so the browser would otherwise turn a
     slightly-off click into a scroll gesture and the tool would not fire.
     `manipulation` removes the 300ms tap delay and keeps panning working. */
  touch-action: manipulation;
  -webkit-overflow-scrolling: touch;
  /* Selecting the label text while clicking a tool twice in a row is what
     makes a toolbar feel broken. */
  user-select: none;
  -webkit-user-select: none;
}
.gis-toolstrip::-webkit-scrollbar { display: none; }

.gis-tool {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  /* Sized by its content, not fixed.
   *
   * A fixed 52px clipped the longest labels: "Seleccionar" needs about
   * 48px at this size and "Anotacion" about 40px, and the overflow was cut
   * with an ellipsis. A clipped label means the operator cannot tell the
   * tools apart at a glance, and a button that looks truncated is a button
   * people hesitate to press.
   */
  height: 38px;
  min-width: 44px;
  padding: 2px 0.5rem;
  flex: 0 0 auto;
  border: 1px solid transparent;
  border-radius: 0.375rem;
  background: transparent;
  color: #94a3b8;
  white-space: nowrap;
  /* The label is part of the button, not a text run to be selected. */
  user-select: none;
  -webkit-user-select: none;
  touch-action: manipulation;
  cursor: pointer;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.gis-tool:hover { background: #1e293b; color: #e2e8f0; }
.gis-tool:active { background: #334155; }
.gis-tool:focus-visible {
  outline: 2px solid #3b82f6;
  outline-offset: -2px;
}

/*
 * The armed tool.
 *
 * A filled background alone was not enough to read at a glance, so the state
 * is carried by three signals that reinforce each other: a filled ground, a
 * bright border, and a lit underline bar under the label. On a toolbar of ten
 * tools that can be told apart at a glance is not a nicety — it is what tells
 * the operator whether the next click will draw a circle or drop a point.
 */
.gis-tool.active {
  background: #1d4ed8;
  border-color: #60a5fa;
  color: #fff;
  box-shadow: inset 0 -2px 0 #7dd3fc;
}
.gis-tool.active .gis-tool-icon { transform: scale(1.08); }

.gis-tool-icon {
  font-size: 0.9375rem;
  line-height: 1;
  pointer-events: none;
}
.gis-tool-label {
  font-size: 0.5rem;
  line-height: 1.1;
  letter-spacing: 0.01em;
  /* No truncation: the button is now wide enough for every label, and a
     label the operator cannot read is worse than a wider toolbar. */
  white-space: nowrap;
  pointer-events: none;
}

/* ─── Hint ─────────────────────────────────────────────────────────────────
 * The active tool's own instruction. It flexes into whatever space the
 * tools and the status pills leave, and is hidden entirely when empty so
 * it never reserves a gap.
 * ------------------------------------------------------------------------- */

.gis-hint {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 0.6875rem;
  color: #fcd34d;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  opacity: 0;
  transition: opacity 0.15s;
  pointer-events: none;
}
.gis-hint-on { opacity: 0.9; }

/* ─── Right-hand actions ─────────────────────────────────────────────────── */

.gis-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex: 0 0 auto;
  padding-left: 0.625rem;
  border-left: 1px solid #1e293b;
}

.gis-status {
  display: flex;
  align-items: center;
  gap: 0.3125rem;
  height: 24px;
  padding: 0 0.4375rem;
  border-radius: 0.375rem;
  background: #0f172a;
  border: 1px solid #1e293b;
}
.gis-status-label {
  font-size: 0.5625rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #94a3b8;
  white-space: nowrap;
}
.gis-dot {
  width: 6px;
  height: 6px;
  border-radius: 9999px;
  flex: 0 0 auto;
}
.gis-dot.ok { background: #34d399; }
.gis-dot.warn { background: #fbbf24; }
.gis-dot.bad { background: #f43f5e; }
.gis-dot.off { background: #475569; }

.gis-divider {
  width: 1px;
  height: 18px;
  background: #1e293b;
  margin: 0 0.1875rem;
  flex: 0 0 auto;
}

.gis-icon-btn {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  padding: 0;
  border-radius: 0.375rem;
  background: transparent;
  color: #94a3b8;
  font-size: 0.8125rem;
  flex: 0 0 auto;
}
.gis-icon-btn:hover { background: #1e293b; color: #e2e8f0; }
.gis-icon-btn.active { background: #1e293b; color: #60a5fa; }

/* ─── Body ──────────────────────────────────────────────────────────────── */

.gis-body {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
}

.gis-sidebar {
  position: relative;
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  background: #0b1220;
  border-right: 1px solid #1e293b;
  min-width: 0;
  overflow: hidden;
}

.gis-tabs {
  display: flex;
  flex: 0 0 auto;
  border-bottom: 1px solid #1e293b;
}

.gis-sidebar-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

/* ─── Map ──────────────────────────────────────────────────────────────────
 * flex: 1 1 auto with min-width:0 is what actually gives the map the space.
 * Without min-width:0 a flex item refuses to shrink below its content, and
 * a wide panel pushes the map off screen instead of the map growing.
 * ------------------------------------------------------------------------- */

.gis-map-area {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.gis-map {
  position: absolute;
  inset: 0;
  background: #0b1220;
}

/* ─── Inspector ──────────────────────────────────────────────────────────── */

.gis-inspector {
  position: relative;
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  background: #0b1220;
  border-left: 1px solid #1e293b;
  min-width: 0;
  overflow: hidden;
}

/* ─── Resizers ────────────────────────────────────────────────────────────
 * A 5px hit area on top of a 1px rule: wide enough to grab with a mouse,
 * invisible enough to stay out of the way.
 * ------------------------------------------------------------------------- */

.gis-resizer {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 5px;
  cursor: col-resize;
  z-index: 20;
  background: transparent;
  transition: background 0.12s;
}
.gis-resizer:hover { background: #3b82f6; }
.gis-resizer-r { right: -2px; }
.gis-resizer-l { left: -2px; }
</style>

<style>
/* Global (non-scoped) so Leaflet's own DOM can be styled. */
.gis-mini-btn {
  padding: 0.125rem 0.4375rem;
  font-size: 0.6875rem;
  border-radius: 0.25rem;
  border: 1px solid #334155;
  background: #0f172a;
  color: #cbd5e1;
}
.gis-mini-btn:hover { background: #1e293b; color: #fff; }
.gis-mini-btn.danger { border-color: #7f1d1d; color: #fca5a5; }
.gis-mini-btn.danger:hover { background: #7f1d1d; color: #fff; }

.gis-tab {
  flex: 1 1 0;
  padding: 0.5rem 0.25rem;
  font-size: 0.5625rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #64748b;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
}
.gis-tab:hover { color: #cbd5e1; }
.gis-tab.active { color: #60a5fa; border-bottom-color: #3b82f6; }

.aerorf-measure-label span {
  background: rgba(15, 23, 42, 0.9);
  color: #fde68a;
  border: 1px solid rgba(250, 204, 21, 0.4);
  border-radius: 0.25rem;
  padding: 1px 4px;
  font-size: 10px;
  font-family: ui-monospace, monospace;
  white-space: nowrap;
}

/*
 * The live radius shown while sizing a circle or a radial. Rendered as a
 * permanent Leaflet tooltip, so it needs its arrow removed: the marker it is
 * attached to is an invisible guide line, and an arrow would point at nothing.
 */
.aerorf-draft-label {
  background: #1d4ed8;
  border: 1px solid #60a5fa;
  color: #fff;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 0.25rem;
  box-shadow: 0 2px 8px rgba(2, 6, 23, 0.8);
  white-space: nowrap;
}
.aerorf-draft-label::before { display: none; }

.aerorf-popup { min-width: 210px; font-size: 12px; }
.aerorf-popup-title { font-weight: 600; color: #0f172a; margin-bottom: 2px; }
.aerorf-popup-desc { color: #475569; margin-bottom: 4px; font-style: italic; }
.aerorf-popup-row { display: flex; justify-content: space-between; gap: 12px; padding: 1px 0; }
.aerorf-popup-row span { color: #64748b; }
.aerorf-popup-hint { margin-top: 6px; font-size: 10px; color: #94a3b8; }
</style>
