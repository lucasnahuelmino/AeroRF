<template>
  <div class="gis-shell">
    <!-- The global BrandBar is the only header above the GIS workspace. -->
    <div
      class="gis-body"
      :class="[
        `gis-workspace-${systemStore.workspaceSide}`,
        { 'workspace-collapsed': systemStore.workspaceMode === 'collapsed' },
      ]"
    >
      <aside
        v-if="systemStore.workspaceMode !== 'closed'"
        class="gis-sidebar"
        :class="[
          `gis-sidebar-${systemStore.workspaceSide}`,
          { 'gis-sidebar-collapsed': systemStore.workspaceMode === 'collapsed' },
        ]"
        :style="{ width: `${systemStore.workspaceMode === 'collapsed' ? 64 : systemStore.workspaceWidth}px` }"
        aria-label="Workspace contextual"
      >
        <template v-if="systemStore.workspaceMode === 'collapsed'">
          <div class="gis-workspace-collapsed">
            <button
              class="gis-workspace-expand"
              type="button"
              title="Expandir Workspace"
              aria-label="Expandir Workspace"
              @click="systemStore.setWorkspaceMode('open')"
            >
              ›
            </button>
            <button
              v-for="category in workspaceCategories"
              :key="category.id"
              class="gis-workspace-category-icon"
              type="button"
              :title="category.label"
              :aria-label="category.label"
              @click="systemStore.openWorkspaceCategory(category.id)"
            >
              <span aria-hidden="true">{{ category.icon }}</span>
            </button>
          </div>
        </template>

        <template v-else>
          <header class="gis-workspace-header">
            <div class="gis-workspace-title-row">
              <div class="gis-workspace-title-group">
                <button
                  v-if="systemStore.workspaceLevel !== 'home'"
                  class="gis-workspace-back"
                  type="button"
                  :aria-label="`Volver a ${workspaceBackLabel}`"
                  :title="`Volver a ${workspaceBackLabel}`"
                  @click="goBackWorkspace"
                >
                  <span aria-hidden="true">‹</span>
                </button>
                <h2
                  v-if="systemStore.workspaceLevel === 'category'"
                  class="gis-workspace-title"
                >
                  {{ workspaceHeading }}
                </h2>
                <h2
                  v-else-if="systemStore.workspaceLevel === 'task'"
                  class="gis-workspace-title"
                >
                  {{ workspaceTaskLabel }}
                </h2>
              </div>
              <div class="gis-workspace-controls">
                <button
                  class="gis-icon-btn"
                  type="button"
                  :title="systemStore.workspaceSide === 'left' ? 'Mover Workspace a la derecha' : 'Mover Workspace a la izquierda'"
                  :aria-label="systemStore.workspaceSide === 'left' ? 'Mover Workspace a la derecha' : 'Mover Workspace a la izquierda'"
                  @click="systemStore.setWorkspaceSide(systemStore.workspaceSide === 'left' ? 'right' : 'left')"
                >
                  ⇆
                </button>
                <button
                  class="gis-icon-btn"
                  type="button"
                  title="Ayuda rápida"
                  aria-label="Ayuda rápida"
                  @click="showHelp = !showHelp"
                >
                  ?
                </button>
                <button
                  class="gis-icon-btn"
                  type="button"
                  title="Contraer Workspace"
                  aria-label="Contraer Workspace"
                  @click="systemStore.setWorkspaceMode('collapsed')"
                >
                  −
                </button>
                <button
                  class="gis-icon-btn"
                  type="button"
                  title="Cerrar Workspace"
                  aria-label="Cerrar Workspace"
                  @click="systemStore.setWorkspaceMode('closed')"
                >
                  ×
                </button>
              </div>
            </div>
            <nav
              v-if="systemStore.workspaceLevel === 'task'"
              class="gis-workspace-breadcrumb"
              aria-label="Ruta del Workspace"
            >
              <button
                type="button"
                @click="systemStore.openWorkspaceCategory(workspaceCategoryMeta.id)"
              >
                {{ workspaceCategoryMeta?.label }}
              </button>
              <span aria-hidden="true">›</span>
              <span aria-current="page">
                {{ workspaceTaskLabel }}
              </span>
            </nav>
          </header>

          <div v-if="systemStore.pendingWorkspaceContext" class="gis-workspace-pending" role="status">
            <span>Hay una nueva selección; el contexto actual está fijado.</span>
            <button class="gis-mini-btn" type="button" @click="systemStore.inspectPendingWorkspaceContext()">
              Inspeccionar selección
            </button>
          </div>

          <nav
            v-if="systemStore.workspaceLevel === 'home'"
            class="gis-workspace-home"
            aria-label="Categorías de trabajo"
          >
            <button
              v-for="category in workspaceCategories"
              :key="category.id"
              class="gis-workspace-category"
              type="button"
              @click="systemStore.openWorkspaceCategory(category.id)"
            >
              <span class="gis-workspace-category-icon-large" aria-hidden="true">{{ category.icon }}</span>
              <span class="min-w-0 flex-1 text-left">
                <strong>{{ category.label }}</strong>
                <small>{{ category.description }}</small>
              </span>
              <span class="gis-workspace-chevron" aria-hidden="true">›</span>
            </button>
          </nav>

          <section
            v-else-if="systemStore.workspaceLevel === 'category'"
            class="gis-workspace-submenu"
            :aria-label="`${workspaceCategoryMeta?.label || 'Categoría'}: tareas`"
          >
            <p class="gis-workspace-intro">{{ workspaceCategoryMeta?.description }}</p>
            <template v-if="systemStore.workspaceCategory === 'tools'">
              <h3 class="gis-workspace-section-title">Herramientas disponibles</h3>
              <div class="gis-workspace-tool-list">
                <button
                  v-for="tool in tools"
                  :key="tool.id"
                  class="gis-workspace-tool"
                  type="button"
                  :class="{ active: mapStore.activeTool === tool.id }"
                  :aria-pressed="mapStore.activeTool === tool.id"
                  @click="selectWorkspaceTool(tool.id)"
                >
                  <span class="gis-workspace-tool-icon" aria-hidden="true">{{ tool.icon }}</span>
                  <span class="min-w-0 flex-1 text-left">
                    <strong>{{ tool.label }}</strong>
                    <small>{{ tool.hint }}</small>
                  </span>
                  <span class="gis-workspace-chevron" aria-hidden="true">›</span>
                </button>
              </div>
            </template>
            <div v-else class="gis-workspace-task-list">
              <button
                v-for="task in workspaceTasksForCategory"
                :key="task.id"
                class="gis-workspace-task"
                type="button"
                @click="openWorkspaceTask(task)"
              >
                <span class="min-w-0 flex-1 text-left">
                  <strong>{{ task.label }}</strong>
                  <small>{{ task.description }}</small>
                </span>
                <span class="gis-workspace-chevron" aria-hidden="true">›</span>
              </button>
            </div>
          </section>

          <div v-else class="gis-workspace-task-view">
            <section
              v-if="systemStore.workspaceSection === 'inspector'"
              class="gis-workspace-context-bar"
            >
              <span class="min-w-0 flex-1">{{ workspaceContextLabel }}</span>
              <button
                v-if="systemStore.workspaceContext"
                class="gis-mini-btn"
                type="button"
                :aria-pressed="systemStore.workspacePinned"
                :title="systemStore.workspacePinned ? 'Desfijar contexto' : 'Fijar contexto'"
                @click="systemStore.toggleWorkspacePinned()"
              >
                {{ systemStore.workspacePinned ? 'Fijado' : 'Fijar' }}
              </button>
              <button
                v-if="systemStore.workspaceReturnTarget"
                class="gis-mini-btn"
                type="button"
                title="Volver a la tarea anterior"
                @click="systemStore.clearWorkspaceContext()"
              >
                Volver
              </button>
            </section>

            <section
              v-if="systemStore.workspaceSection === 'tools'"
              class="gis-workspace-active-tool"
              aria-live="polite"
            >
              <div class="gis-workspace-active-tool-heading">
                <span class="gis-workspace-tool-icon" aria-hidden="true">{{ activeToolMeta.icon }}</span>
                <div class="min-w-0 flex-1">
                  <p>{{ mapStore.activeTool === 'select' ? 'Lista para seleccionar' : 'Herramienta activa en el mapa' }}</p>
                </div>
                <button
                  v-if="mapStore.activeTool !== 'select'"
                  class="gis-mini-btn"
                  type="button"
                  @click="cancelActiveTool"
                >
                  Cancelar (Esc)
                </button>
              </div>
              <p class="gis-workspace-tool-hint">{{ mapStore.toolHint || activeToolMeta.hint }}</p>
              <button
                v-if="mapStore.activeTool === 'measure' && measure.active && measure.segment_count > 0"
                class="gis-btn-primary gis-workspace-finish"
                type="button"
                @click="saveMeasurement"
              >
                Guardar medición
              </button>
              <button
                v-else-if="mapStore.draft"
                class="gis-btn-primary gis-workspace-finish"
                type="button"
                @click="handleDraftConfirm"
              >
                Finalizar dibujo
              </button>
            </section>

            <div class="gis-workspace-panel-slot">
              <KeepAlive>
                <component
                  :is="workspacePanelComponent"
                  v-if="workspacePanelComponent"
                  :key="systemStore.workspaceSection"
                  v-bind="workspacePanelProps"
                  v-on="workspacePanelListeners"
                />
              </KeepAlive>
            </div>
          </div>
        </template>

        <div
          v-if="systemStore.workspaceMode === 'open'"
          class="gis-resizer"
          :class="systemStore.workspaceSide === 'left' ? 'gis-resizer-r' : 'gis-resizer-l'"
          role="separator"
          aria-orientation="vertical"
          :aria-valuenow="systemStore.workspaceWidth"
          :aria-valuemin="240"
          :aria-valuemax="520"
          :aria-label="`Ancho del Workspace: ${systemStore.workspaceWidth} píxeles`"
          :title="`Arrastrar para ajustar el ancho: ${systemStore.workspaceWidth}px`"
          @pointerdown="startResize"
        />
      </aside>

      <!-- Map -->
      <main class="gis-map-area">
        <div ref="mapContainer" class="gis-map" />
        <button
          class="gis-map-export"
          type="button"
          :disabled="isExportingMap"
          :aria-busy="isExportingMap"
          @click="downloadMapImage"
        >
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="none">
            <path d="M3 4.5h14v11H3zM6 12l2.5-2.5 2 2 1.5-1.5 3 3M7 7.5h.01" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M10 1.5v6m-2-2 2 2 2-2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          {{ isExportingMap ? 'Preparando PNG…' : 'Descargar imagen' }}
        </button>
        <button
          v-if="systemStore.workspaceMode === 'closed'"
          class="gis-workspace-reopen"
          :class="`gis-workspace-reopen-${systemStore.workspaceSide}`"
          type="button"
          @click="systemStore.setWorkspaceMode('open')"
        >
          <span aria-hidden="true">▤</span>
          Abrir Workspace
        </button>

        <!-- Map overlays -->
        <div class="pointer-events-none absolute inset-0">
          <!-- Distance readout while measuring -->
          <div
            v-if="measure.active && measure.segment_count > 0"
            class="pointer-events-auto absolute top-3 left-3 rounded-lg border border-amber-500/40 bg-panel-hondo px-3 py-2 text-xs shadow-xl"
          >
            <div class="mb-1 text-[10px] uppercase tracking-widest text-amber-400">
              Medición
            </div>
            <div class="font-mono text-amber-200 text-sm">{{ measure.total_label }}</div>
            <div class="mt-0.5 text-[10px] text-texto-tenue">
              {{ measure.points.length }} puntos · {{ measure.segment_count }} tramos
            </div>
            <div v-if="measure.area_note" class="text-[10px] text-texto-tenue">
              Área ≈ {{ measure.area_note.toFixed(2) }} km²
            </div>
            <ul v-if="measure.segments.length" class="mt-1.5 space-y-0.5">
              <li
                v-for="seg in measure.segments"
                :key="seg.index"
                class="font-mono text-[10px] text-texto-tenue"
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
            class="pointer-events-auto absolute top-3 left-1/2 -translate-x-1/2 rounded-lg border border-blue-500/40 bg-panel-hondo px-3 py-2 text-xs shadow-xl"
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
            class="pointer-events-auto absolute bottom-3 left-3 flex items-center gap-1.5 rounded-lg border border-borde-fuerte bg-panel-hondo px-2 py-1.5 shadow-xl"
          >
            <span class="text-[11px] text-texto-medio max-w-[16rem] truncate">
              {{ mapStore.selected.name || typeName(mapStore.selected.type) }}
            </span>
            <span class="w-px h-4 bg-borde" />
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
            class="pointer-events-none absolute inset-0 flex items-center justify-center bg-velo-suave"
          >
            <div class="rounded-lg bg-panel-hondo px-4 py-2 text-sm text-texto-medio shadow-xl">
              Cargando objetos…
            </div>
          </div>
        </div>

        <!-- Right-click menu (spec §45) -->
        <ContextMenu />
      </main>

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
      class="fixed inset-0 z-[1300] flex items-center justify-center bg-velo p-6"
      @click.self="showHelp = false"
    >
      <div class="max-w-2xl rounded-xl border border-borde-fuerte bg-panel p-6 shadow-2xl">
        <h2 class="mb-3 text-lg font-semibold text-texto">AeroRF — ayuda rápida</h2>
        <div class="grid gap-4 text-sm text-texto-medio md:grid-cols-2">
          <div>
            <h3 class="mb-1 font-semibold text-texto">Atajos</h3>
            <ul class="space-y-1 text-xs">
              <li><kbd>ESC</kbd> — cancelar la herramienta activa</li>
              <li><kbd>Enter</kbd> — confirmar el dibujo en curso</li>
              <li><kbd>Retroceso</kbd> — quitar el último vértice</li>
              <li>Clic derecho — menú contextual en el mapa</li>
            </ul>
          </div>
          <div>
            <h3 class="mb-1 font-semibold text-texto">Capas de datos</h3>
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

import MapEngine from '@/map/MapEngine'
import { ToolManager, TOOLS, TOOL_META } from '@/map/draw'
import { MeasureEngine } from '@/map/measure'
import { AircraftRenderer } from '@/map/aircraft'
import { AirportLayer, AIRPORT_LAYER_KEY } from '@/map/airports'
import { mapExportFilename, renderMapPng } from '@/map/exportMap'
import { useMapStore, typeName } from '@/stores/map'
import { useFlightsStore } from '@/stores/flights'
import { useSystemStore } from '@/stores/system'

import CoordinateBar from '@/components/gis/CoordinateBar.vue'
import ContextMenu from '@/components/gis/ContextMenu.vue'
import FlightPanel from '@/components/gis/FlightPanel.vue'
import InspectorPanel from '@/components/gis/InspectorPanel.vue'
import LayerPanel from '@/components/gis/LayerPanel.vue'
import ObjectsPanel from '@/components/gis/ObjectsPanel.vue'
import Timeline from '@/components/gis/Timeline.vue'
import ToolOptions from '@/components/gis/ToolOptions.vue'
import AirportPanel from '@/components/gis/AirportPanel.vue'

const mapStore = useMapStore()
const flightsStore = useFlightsStore()
const systemStore = useSystemStore()

const mapContainer = ref(null)
const isExportingMap = ref(false)
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

async function downloadMapImage() {
  if (isExportingMap.value) return
  isExportingMap.value = true
  try {
    const blob = await renderMapPng(mapContainer.value, { engine, scale: 2 })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = mapExportFilename()
    document.body.append(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    systemStore.notify('Imagen cartográfica PNG descargada.', { kind: 'success' })
  } catch (error) {
    const message = error instanceof Error
      ? error.message
      : 'No se pudo exportar la imagen cartográfica.'
    systemStore.notify(message, { kind: 'warn', ms: 7000 })
  } finally {
    isExportingMap.value = false
  }
}

/**
 * The drawing palette.
 *
 * `POLYGON` and `TRACE` are no longer offered. The operator's point was that they
 * do the same as `COVERAGE` and `LINE` respectively, and four ways to draw two
 * shapes is one too many on a strip that is already ten buttons wide — and every
 * extra tool is another thing to read before drawing.
 *
 * They stay in `TOOL_META` on purpose. That is the *tool* list; an object saved
 * as `polygon` or `trace` earlier has to keep rendering, labelling, exporting and
 * showing up in the inspector, and dropping the type would orphan whatever is
 * already in the database. The tool is what was redundant, not the data.
 */
const HIDDEN_TOOLS = new Set([TOOLS.POLYGON, TOOLS.TRACE])

const tools = computed(() =>
  Object.entries(TOOL_META)
    .filter(([id]) => !HIDDEN_TOOLS.has(id))
    .map(([id, meta]) => ({ id, ...meta })),
)

const workspaceCategories = [
  {
    id: 'tools',
    label: 'Herramientas',
    icon: '✎',
    description: 'Dibujo, selección, medición y análisis sobre el mapa.',
  },
  {
    id: 'layers',
    label: 'Capas',
    icon: '▤',
    description: 'Mapa base, visibilidad, opacidad, bloqueo y exportación.',
  },
  {
    id: 'objects',
    label: 'Objetos',
    icon: '◈',
    description: 'Buscar, filtrar, seleccionar y administrar objetos GIS.',
  },
  {
    id: 'flights',
    label: 'Vuelos',
    icon: '✈',
    description: 'Búsqueda, seguimiento, trayectorias e historial de vuelos.',
  },
  {
    id: 'airports',
    label: 'Aeropuertos',
    icon: '⌂',
    description: 'Referencias aeroportuarias, filtros y mediciones.',
  },
]

const workspaceTasks = {
  layers: [
    {
      id: 'manage-layers',
      section: 'layers',
      label: 'Administrar capas',
      description: 'Mapa base, visibilidad, opacidad, bloqueo, procedencia y exportación.',
    },
  ],
  objects: [
    {
      id: 'manage-objects',
      section: 'objects',
      label: 'Buscar y administrar objetos',
      description: 'Filtros, categorías, selección múltiple y acciones de objeto.',
    },
  ],
  flights: [
    {
      id: 'flight-operations',
      section: 'flights',
      label: 'Búsqueda y seguimiento',
      description: 'Vuelos, aeronaves seguidas, trayectorias e historial.',
    },
    {
      id: 'timeline',
      section: 'timeline',
      label: 'Sesiones y línea de tiempo',
      description: 'Reproducir una sesión grabada y sincronizarla con el mapa.',
    },
  ],
  airports: [
    {
      id: 'airport-reference',
      section: 'airports',
      label: 'Aeropuertos de referencia',
      description: 'Buscar, filtrar, etiquetar, centrar y medir distancias.',
    },
  ],
}

const workspaceCategoryMeta = computed(() =>
  workspaceCategories.find((category) => category.id === systemStore.workspaceCategory) || null,
)
const workspaceTasksForCategory = computed(
  () => workspaceTasks[systemStore.workspaceCategory] || [],
)
const workspaceHeading = computed(() => workspaceCategoryMeta.value?.label || '')
const workspaceTaskLabel = computed(() => {
  if (systemStore.workspaceSection === 'inspector') return 'Inspector'
  if (systemStore.workspaceSection === 'timeline') return 'Línea de tiempo'
  if (systemStore.workspaceSection === 'tools') return activeToolMeta.value.label
  return workspaceTasksForCategory.value.find((task) => task.id === systemStore.workspaceTask)?.label
    || workspaceCategoryMeta.value?.label
    || 'Tarea'
})
const workspaceBackLabel = computed(() =>
  systemStore.workspaceLevel === 'task'
    ? workspaceCategoryMeta.value?.label || 'Categorías'
    : 'Categorías',
)
const workspaceContextLabel = computed(() => {
  const context = systemStore.workspaceContext
  if (!context) return 'Sin contexto seleccionado'
  if (context.type === 'object') {
    const object = mapStore.byId.get(context.id)
    return object?.name || `${typeName(object?.type || 'point')} · ID ${context.id}`
  }
  const state = flightsStore.liveStates?.[context.icao24]
  return state?.callsign || `Aeronave ${context.icao24.toUpperCase()}`
})
const activeToolMeta = computed(
  () => TOOL_META[mapStore.activeTool] || TOOL_META[TOOLS.SELECT],
)
const workspacePanelMap = {
  tools: ToolOptions,
  layers: LayerPanel,
  objects: ObjectsPanel,
  flights: FlightPanel,
  airports: AirportPanel,
  inspector: InspectorPanel,
  timeline: Timeline,
}
const workspacePanelComponent = computed(() =>
  systemStore.workspaceLevel === 'task'
    ? workspacePanelMap[systemStore.workspaceSection] || null
    : null,
)
const workspacePanelProps = computed(() => {
  if (systemStore.workspaceSection === 'inspector') {
    return {
      context: systemStore.workspaceContext,
      canCreateAnother: Boolean(lastCreatedTool.value),
    }
  }
  if (systemStore.workspaceSection === 'timeline') return { embedded: true }
  if (systemStore.workspaceSection === 'airports') {
    return {
      visible: airportsVisible.value,
      labels: systemStore.airportLabels,
      armed: airportMeasureArmed.value,
      result: airportMeasureResult.value,
    }
  }
  return {}
})
const workspacePanelListeners = computed(() => {
  if (systemStore.workspaceSection === 'inspector') {
    return { 'create-another': createAnother }
  }
  if (systemStore.workspaceSection === 'airports') {
    return {
      'update:visible': setAirportsVisible,
      'update:labels': systemStore.setAirportLabels,
      'toggle-country': systemStore.toggleAirportCountry,
      zoom: zoomToAirports,
      measure: armAirportMeasure,
    }
  }
  return {}
})

const lastCreatedTool = ref(null)

function openWorkspaceTask(task) {
  systemStore.openWorkspaceTask(task.section, {
    category: systemStore.workspaceCategory,
    task: task.id,
  })
}

function goBackWorkspace() {
  if (systemStore.workspaceLevel === 'task') {
    systemStore.openWorkspaceCategory(systemStore.workspaceCategory)
  } else if (systemStore.workspaceLevel === 'category') {
    systemStore.openWorkspaceHome()
  }
}

function selectWorkspaceTool(id) {
  activateTool(id)
  systemStore.openWorkspaceTask('tools', { category: 'tools', task: 'tool-options' })
}

// ─── Workspace resizing ────────────────────────────────────────────────────
function startResize(event) {
  if (event.button !== undefined && event.button !== 0) return
  event.preventDefault()
  const startX = event.clientX
  const startWidth = systemStore.workspaceWidth
  const direction = systemStore.workspaceSide === 'left' ? 1 : -1

  const move = (e) => {
    systemStore.setWorkspaceWidth(startWidth + (e.clientX - startX) * direction)
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
        if (mapStore.selectedId != null) mapStore.clearSelection()
        systemStore.requestWorkspaceContext({ type: 'aircraft', icao24 })
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
    engine.on('click', ({ latlng, overObject = null }) => {
      mapStore.captureClick(latlng)

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
      // Clicking empty space with the select tool clears the selection.
      //
      // A click that landed on an object is excluded. The object's own handler
      // has already selected it, and this map draws with `preferCanvas`, so
      // every object shares one canvas element and there is no per-object DOM
      // node to stop the event at: the map's handler runs for that click too.
      // Clearing here undid the selection a moment after it was made, and
      // nothing stayed selected — no point, no circle, no radial.
      //
      // The test is "no drawing tool armed" rather than "the select tool
      // active". `ToolManager.active` is null until a tool is picked, and the
      // select tool is only ever activated from the airport measurement, so
      // comparing against TOOLS.SELECT meant this never ran at all: the
      // selection could be made and could never be taken back.
      const drawing = toolManager?.isDrawing
      if (!drawing && overObject != null) {
        systemStore.requestWorkspaceContext({ type: 'object', id: overObject })
      } else if (!drawing && overObject == null) {
        mapStore.clearSelection()
        if (!systemStore.workspacePinned && systemStore.workspaceContext?.type === 'object') {
          systemStore.clearWorkspaceContext()
        }
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
      systemStore.requestWorkspaceContext({ type: 'object', id })
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

function cancelActiveTool() {
  toolManager?.cancel()
  measureEngine?.stop()
  mapStore.activeTool = TOOLS.SELECT
  mapStore.toolHint = TOOL_META[TOOLS.SELECT].hint
  mapStore.draft = null
  draftPreview.value = null
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
  lastCreatedTool.value = payload.type === 'measurement' ? TOOLS.MEASURE : payload.type
  const keepLineActive = payload.type === 'line' && toolManager?.active === TOOLS.LINE
  const defaults = {
    point: {
      name: `Punto ${new Date().toLocaleTimeString('es-AR')}`,
      category: 'Referencia',
      icon: mapStore.toolOptions.markerType || 'marker',
    },
    annotation: { name: 'Anotación', category: 'Referencia' },
    circle: { name: 'Círculo' },
    radial: { name: 'Radial' },
    trace: { name: 'Traza' },
    line: { name: 'Línea' },
    polygon: { name: 'Polígono' },
    coverage: { name: 'Cobertura' },
    measurement: { name: 'Medición' },
  }

  const created = await mapStore.createObject({
    ...defaults[payload.type],
    ...payload,
  })
  if (!created) return

  measureEngine?.stop()
  if (!keepLineActive) {
    toolManager?.cancel()
    mapStore.activeTool = TOOLS.SELECT
    mapStore.toolHint = TOOL_META[TOOLS.SELECT].hint
    mapStore.draft = null
  }
  mapStore.select(created.id)
  systemStore.requestWorkspaceContext({ type: 'object', id: created.id })
}

async function saveMeasurement() {
  const payload = measureEngine?.toObjectPayload()
  measureEngine.stop()
  toolManager.deactivate()
  mapStore.activeTool = TOOLS.SELECT
  mapStore.toolHint = TOOL_META[TOOLS.SELECT].hint
  mapStore.draft = null
  if (!payload) return

  lastCreatedTool.value = TOOLS.MEASURE
  const created = await mapStore.createObject({
    ...payload,
    name: `Medición ${new Date().toLocaleTimeString('es-AR')}`,
  })
  if (!created) return
  mapStore.select(created.id)
  systemStore.requestWorkspaceContext({ type: 'object', id: created.id })
}

// ─── Object actions ─────────────────────────────────────────────────────────

function createAnother() {
  const tool = lastCreatedTool.value
  if (!tool) {
    systemStore.openWorkspaceCategory('tools')
    return
  }
  systemStore.openWorkspaceCategory('tools')
  activateTool(tool)
  systemStore.openWorkspaceTask('tools', { category: 'tools', task: 'tool-options' })
}

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

async function confirmDelete() {
  const obj = mapStore.selected
  if (!obj) return
  const ok = await systemStore.ask({
    title: 'Eliminar objeto',
    message: `¿Eliminar «${obj.name || typeName(obj.type)}»? Esta acción no se puede deshacer.`,
    confirmLabel: 'Eliminar',
    danger: true,
  })
  if (ok) mapStore.deleteObject(obj.id, true)
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
// Tell Leaflet when the panels change the space the map has.
//
// `MapEngine.invalidateSize()` existed and nothing called it, so the map kept
// the size it had when the page loaded. Measured with the sidebar open: the
// container was 544px wide and Leaflet still drew in 328 — the sidebar's 216px
// dead, with the map squeezed to the left. Opening or closing a panel, and
// dragging its edge, all left the operator looking at a map that was not
// filling the space it was given. That is the "the map is not the width it
// should be" complaint, and no amount of resizing the panels fixes it.
//
// `flush: 'post'` so it runs after the DOM has the new width, and the short
// delay is for the panel's own transition: invalidating mid-transition resizes
// to a width that is about to change again.
watch(
  () => [
    systemStore.workspaceMode,
    systemStore.workspaceWidth,
    systemStore.workspaceSide,
  ],
  () => engine?.invalidateSize(140),
  { flush: 'post' },
)

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
      aircraftRenderer.updateAircraft(state, colors[icao24] || 'var(--trazo-medido)')
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
 *   - the GIS starts immediately below the global navigation
 *   - category and task rows have readable labels and comfortable hit areas
 *   - the single contextual Workspace is configurable by the operator:
 *     position, width, open/collapsed/closed mode.
 * ------------------------------------------------------------------------- */

.gis-shell {
  display: flex;
  flex-direction: column;
  /* The viewport minus the fixed header, not the whole viewport. The footer is
     outside this component and the map must remain on the visible screen
     without an extra, hidden height budget. */
  height: calc(100vh - var(--brandbar-h, 48px));
  height: calc(100dvh - var(--brandbar-h, 48px));
  background: var(--fondo);
  color: var(--texto);
  overflow: hidden;
}

.gis-icon-btn {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  padding: 0;
  border-radius: 0.375rem;
  background: transparent;
  color: var(--texto-tenue);
  font-size: 0.8125rem;
  flex: 0 0 auto;
}
.gis-icon-btn:hover { background: var(--panel-alto); color: var(--texto); }
.gis-icon-btn.active { background: var(--panel-alto); color: var(--signal-on-ink); }

/* ─── Body ──────────────────────────────────────────────────────────────── */

.gis-body {
  position: relative;
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
}

.gis-workspace-right { flex-direction: row-reverse; }

.gis-sidebar {
  position: relative;
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  background: var(--panel);
  border-right: 1px solid var(--borde);
  min-width: 0;
  overflow: hidden;
  transition: width 0.16s ease;
}

.gis-sidebar-right {
  border-right: 0;
  border-left: 1px solid var(--borde);
}

.gis-sidebar-collapsed { width: 64px; }

.gis-workspace-header {
  flex: 0 0 auto;
  padding: 0.55rem 0.65rem;
  border-bottom: 1px solid var(--borde);
}

.gis-workspace-title-row,
.gis-workspace-title-group,
.gis-workspace-controls,
.gis-workspace-active-tool-heading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.gis-workspace-title-row { justify-content: space-between; }
.gis-workspace-title-group { min-width: 0; }
.gis-workspace-controls { flex: 0 0 auto; gap: 0.1rem; }
.gis-workspace-back {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  place-items: center;
  border-radius: 0.375rem;
  background: transparent;
  color: var(--texto-medio);
  font-size: 1.65rem;
  line-height: 1;
}
.gis-workspace-back:hover { background: var(--panel-alto); color: var(--texto); }
.gis-workspace-title-group:empty {
  display: none;
}
.gis-workspace-title {
  overflow: hidden;
  color: var(--texto);
  font-size: 0.9375rem;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gis-workspace-breadcrumb {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.35rem;
  color: var(--texto-tenue);
  font-size: 0.6875rem;
}
.gis-workspace-breadcrumb button {
  color: var(--texto-secundario, var(--texto-medio));
}
.gis-workspace-breadcrumb button:hover { color: var(--signal-on-ink); }
.gis-workspace-reopen {
  position: absolute;
  top: 0.75rem;
  z-index: 900;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  min-height: 36px;
  padding: 0 0.65rem;
  border: 1px solid var(--borde-fuerte);
  border-radius: 0.375rem;
  background: var(--panel);
  color: var(--texto);
  font-size: 0.75rem;
  box-shadow: 0 2px 8px rgb(0 0 0 / 20%);
}
.gis-workspace-reopen:hover { background: var(--panel-alto); border-color: var(--signal); }
.gis-workspace-reopen-left { left: 0.75rem; }
.gis-workspace-reopen-right { right: 0.75rem; }

.gis-workspace-home,
.gis-workspace-submenu,
.gis-workspace-task-view {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.gis-workspace-home,
.gis-workspace-submenu { padding: 0.7rem; }
.gis-workspace-home,
.gis-workspace-task-list,
.gis-workspace-tool-list { display: flex; flex-direction: column; gap: 0.45rem; }
.gis-workspace-category,
.gis-workspace-task,
.gis-workspace-tool {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  width: 100%;
  min-height: 56px;
  padding: 0.65rem;
  border: 1px solid var(--borde);
  border-radius: 0.5rem;
  background: var(--panel);
  color: var(--texto);
  text-align: left;
  transition: background 0.12s, border-color 0.12s;
  user-select: none;
  -webkit-user-select: none;
  touch-action: manipulation;
}
.gis-workspace-category:hover,
.gis-workspace-task:hover,
.gis-workspace-tool:hover {
  border-color: var(--signal);
  background: var(--panel-alto);
}
.gis-workspace-category:active,
.gis-workspace-task:active,
.gis-workspace-tool:active {
  border-color: var(--signal);
  background: var(--panel-alto);
}
.gis-workspace-category strong,
.gis-workspace-task strong,
.gis-workspace-tool strong {
  display: block;
  font-size: 0.8125rem;
  font-weight: 600;
}
.gis-workspace-category small,
.gis-workspace-task small,
.gis-workspace-tool small {
  display: block;
  margin-top: 0.2rem;
  color: var(--texto-tenue);
  font-size: 0.6875rem;
  line-height: 1.4;
}
.gis-workspace-category-icon-large,
.gis-workspace-tool-icon {
  display: grid;
  width: 2rem;
  height: 2rem;
  flex: 0 0 2rem;
  place-items: center;
  border-radius: 0.375rem;
  background: var(--panel-alto);
  color: var(--signal-on-ink);
  font-size: 1rem;
}
.gis-workspace-chevron { flex: 0 0 auto; color: var(--texto-tenue); font-size: 1.25rem; }
.gis-workspace-intro {
  margin-bottom: 0.85rem;
  color: var(--texto-secundario, var(--texto-medio));
  font-size: 0.75rem;
  line-height: 1.5;
}
.gis-workspace-section-title {
  margin-bottom: 0.5rem;
  color: var(--texto-tenue);
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.gis-workspace-tool { align-items: flex-start; }
.gis-workspace-tool.active {
  border-color: var(--signal);
  background: color-mix(in srgb, var(--signal) 14%, var(--panel));
}
.gis-workspace-tool.active .gis-workspace-tool-icon {
  background: var(--signal);
  color: var(--texto);
}
.gis-workspace-collapsed {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.45rem;
  padding: 0.55rem 0.25rem;
}
.gis-workspace-expand,
.gis-workspace-category-icon {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 0.5rem;
  background: transparent;
  color: var(--texto-medio);
  font-size: 1.15rem;
}
.gis-workspace-expand:hover,
.gis-workspace-category-icon:hover {
  border-color: var(--borde);
  background: var(--panel-alto);
  color: var(--texto);
}
.gis-workspace-pending {
  display: grid;
  gap: 0.45rem;
  padding: 0.65rem 0.8rem;
  border-bottom: 1px solid var(--borde);
  background: color-mix(in srgb, var(--risk-mid) 12%, var(--panel));
  color: var(--texto);
  font-size: 0.6875rem;
}
.gis-workspace-context-bar {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.5rem 0.65rem;
  border-bottom: 1px solid var(--borde);
  color: var(--texto);
  font-size: 0.6875rem;
}
.gis-workspace-active-tool {
  flex: 0 0 auto;
  padding: 0.7rem;
  border-bottom: 1px solid var(--borde);
  background: var(--panel);
}
.gis-workspace-active-tool-heading h3 { color: var(--texto); font-size: 0.8125rem; font-weight: 600; }
.gis-workspace-active-tool-heading p {
  margin-top: 0.1rem;
  color: var(--signal-on-ink);
  font-size: 0.625rem;
}
.gis-workspace-tool-hint {
  margin-top: 0.55rem;
  color: var(--texto-secundario, var(--texto-medio));
  font-size: 0.6875rem;
  line-height: 1.45;
}
.gis-workspace-finish { width: 100%; margin-top: 0.6rem; }
.gis-workspace-panel-slot { min-height: 0; }
.gis-workspace-panel-slot > * { min-height: 0; }

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
  background: var(--panel);
}

.gis-map-export {
  position: absolute;
  top: 3.25rem;
  right: 0.75rem;
  z-index: 1000;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  min-height: 2rem;
  padding: 0.35rem 0.6rem;
  border: 1px solid var(--borde-fuerte);
  border-radius: 0.4rem;
  background: var(--panel);
  color: var(--texto);
  font-size: 0.6875rem;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
  pointer-events: auto;
}
.gis-map-export svg { width: 1rem; height: 1rem; flex: 0 0 auto; }
.gis-map-export:hover:not(:disabled) { border-color: var(--signal); }
.gis-map-export:disabled { cursor: wait; opacity: 0.7; }

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
.gis-resizer:hover { background: var(--signal-on-ink); }
.gis-resizer-r { right: -2px; }
.gis-resizer-l { left: -2px; }

.gis-sidebar button:focus-visible,
.gis-shell button:focus-visible {
  outline: 2px solid var(--signal-on-ink);
  outline-offset: 2px;
}

@media (max-width: 760px) {
  .gis-sidebar {
    position: absolute;
    top: 0;
    bottom: 0;
    z-index: 1200;
    max-width: min(92vw, 520px);
    box-shadow: 0 12px 32px rgb(0 0 0 / 35%);
  }

  .gis-sidebar-left { left: 0; }
  .gis-sidebar-right { right: 0; }
  .gis-workspace-collapsed { box-shadow: none; }
}
</style>

<style>
/* Global (non-scoped) so Leaflet's own DOM can be styled. */
.gis-mini-btn {
  padding: 0.125rem 0.4375rem;
  font-size: 0.6875rem;
  border-radius: 0.25rem;
  border: 1px solid var(--borde-fuerte);
  background: var(--panel);
  color: var(--texto-medio);
}
.gis-mini-btn:hover { background: var(--panel-alto); color: #fff; }
.gis-mini-btn.danger { border-color: var(--risk-high); color: var(--risk-high); }
.gis-mini-btn.danger:hover { background: var(--risk-high); color: #fff; }

/*
 * The measurement labels moved to the global block below, and that is not a
 * style choice. Both are `divIcon` content: Leaflet builds the element at run
 * time, so it never receives the `data-v-…` attribute a scoped rule requires —
 * these labels rendered as unstyled 10px text with no ground. Anything drawn by
 * Leaflet has to be styled outside the scoped block, next to `.aerorf-popup`.
 */

/*
 * The live radius shown while sizing a circle or a radial. Rendered as a
 * permanent Leaflet tooltip, so it needs its arrow removed: the marker it is
 * attached to is an invisible guide line, and an arrow would point at nothing.
 */
.aerorf-draft-label {
  background: var(--signal);
  border: 1px solid var(--signal-on-ink);
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

/*
 * The reference markers a radial is read against: the due-north line and the
 * angle arc. Deliberately dimmer than the measured value — they are the frame
 * the number is read in, not the number itself, and matching their weight
 * would compete with the value it exists to give meaning to.
 */
.aerorf-draft-label--muted {
  background: var(--panel-alto);
  border-color: var(--texto-invisible);
  color: var(--texto-medio);
  font-weight: 500;
  font-size: 10px;
  padding: 1px 4px;
}

/* Measurement labels, live and committed.
 *
 * Global on purpose. Leaflet creates `divIcon` content at run time, so it never
 * gets the `data-v-…` attribute a scoped selector needs — inside `<style scoped>`
 * these labels rendered as unstyled 10px text with no ground and no border,
 * which is how they were found: measured at 10×19px with no background.
 */
.aerorf-measure-label span,
.aerorf-measure-live span {
  background: rgba(15, 23, 42, 0.9);
  color: var(--seleccion);
  border: 1px solid rgba(250, 204, 21, 0.4);
  border-radius: 0.25rem;
  padding: 1px 4px;
  font-size: 10px;
  font-family: ui-monospace, monospace;
  white-space: nowrap;
}

/* The live readout's icon box is zero-sized, so Leaflet positions its top-left
   corner on the point. Centring the span by hand puts it on the midpoint of the
   segment instead, and keeps it off the crosshair being aimed with. */
.aerorf-measure-live {
  background: none;
  border: none;
}
.aerorf-measure-live span {
  /* `inline-block`, not `block`: the icon box is zero-sized, so a block-level
     span takes the parent's width of 0 and collapses to its padding — measured
     at 10×19px with the text spilling out of it. An inline box sizes to its
     content, and the transform below then centres that content on the point. */
  display: inline-block;
  transform: translate(-50%, -50%);
  box-shadow: 0 2px 6px rgba(2, 6, 23, 0.6);
}

.aerorf-popup { min-width: 210px; font-size: 12px; }
.aerorf-popup-title { font-weight: 600; color: var(--panel); margin-bottom: 2px; }
.aerorf-popup-desc { color: var(--texto-invisible); margin-bottom: 4px; font-style: italic; }
.aerorf-popup-row { display: flex; justify-content: space-between; gap: 12px; padding: 1px 0; }
.aerorf-popup-row span { color: var(--texto-tenue); }
.aerorf-popup-hint { margin-top: 6px; font-size: 10px; color: var(--texto-tenue); }
</style>
