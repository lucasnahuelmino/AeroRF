<template>
  <Teleport to="body">
    <div
      v-if="menu.open"
      class="aerorf-context fixed z-[1250] min-w-[13rem] rounded-lg border py-1 shadow-2xl"
      :style="style"
      @click.stop
    >
      <div class="border-b border-slate-800 px-3 py-1.5">
        <div class="font-mono text-[10px] text-emerald-300">
          {{ menu.lat.toFixed(6) }}, {{ menu.lon.toFixed(6) }}
        </div>
        <button class="text-[10px] text-slate-500 hover:text-slate-300" @click="copyCoords">
          ⧉ Copiar coordenadas
        </button>
      </div>

      <p class="px-3 pt-1.5 pb-0.5 text-[9px] uppercase tracking-widest text-slate-600">Crear</p>
      <button
        v-for="item in createItems"
        :key="item.type"
        class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-slate-300 hover:bg-blue-600/25 hover:text-white"
        @click="create(item)"
      >
        <span class="w-4 text-center">{{ item.icon }}</span>
        {{ item.label }}
      </button>

      <p class="border-t border-slate-800 px-3 pt-1.5 pb-0.5 text-[9px] uppercase tracking-widest text-slate-600">
        Herramientas
      </p>
      <button
        v-for="item in toolItems"
        :key="item.id"
        class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-slate-300 hover:bg-blue-600/25 hover:text-white"
        @click="activateTool(item.id)"
      >
        <span class="w-4 text-center">{{ item.icon }}</span>
        {{ item.label }}
      </button>

      <p class="border-t border-slate-800 px-3 pt-1.5 pb-0.5 text-[9px] uppercase tracking-widest text-slate-600">
        Medir
      </p>
      <button
        class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-slate-300 hover:bg-amber-500/25 hover:text-white"
        @click="measureFromHere"
      >
        <span class="w-4 text-center">📏</span> Medir desde aquí
      </button>

      <!-- Distance readout when measuring from the right-click point -->
      <div
        v-if="measuredDistance"
        class="border-t border-slate-800 px-3 py-1.5 font-mono text-[11px] text-amber-300"
      >
        {{ measuredDistance.km }} km / {{ measuredDistance.nm }} NM
      </div>
    </div>

    <!-- Click-away shield -->
    <div v-if="menu.open" class="fixed inset-0 z-[1240]" @click="close" @contextmenu.prevent="close" />
  </Teleport>
</template>

<script setup>
/**
 * components/gis/ContextMenu.vue
 * ──────────────────────────────
 * Right-click menu (spec §45).
 *
 * Positioned against the map container, and flipped when it would run
 * off the right or bottom edge.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { TOOLS } from '@/map/draw'
import { haversine } from '@/map/geo'
import { useMapStore } from '@/stores/map'
import { useSystemStore } from '@/stores/system'

const mapStore = useMapStore()
const systemStore = useSystemStore()

const menu = computed(() => mapStore.contextMenu)
const measuredDistance = ref(null)

/** Keep the menu inside the viewport. */
const style = computed(() => {
  if (!menu.value.open) return {}
  const width = 220
  const height = 420
  const flipX = window.innerWidth - menu.value.x < width
  const flipY = window.innerHeight - menu.value.y < height
  return {
    left: `${flipX ? Math.max(4, menu.value.x - width) : menu.value.x}px`,
    top: `${flipY ? Math.max(4, window.innerHeight - height) : menu.value.y}px`,
  }
})

const createItems = [
  { type: 'point', icon: '📍', label: 'Crear punto' },
  { type: 'rf_event', icon: '⚡', label: 'Crear evento RF' },
  { type: 'rf_source', icon: '📡', label: 'Crear fuente interferente' },
  { type: 'antenna', icon: '📶', label: 'Crear antena' },
  { type: 'circle', icon: '◯', label: 'Crear círculo' },
  { type: 'radial', icon: '➤', label: 'Crear radial' },
  { type: 'reference', icon: '🎯', label: 'Crear referencia' },
  { type: 'annotation', icon: '✎', label: 'Crear anotación' },
]

const toolItems = [
  { id: TOOLS.LINE, icon: '╱', label: 'Dibujar línea' },
  { id: TOOLS.POLYGON, icon: '⬠', label: 'Dibujar polígono' },
  { id: TOOLS.TRACE, icon: '∿', label: 'Dibujar traza' },
  { id: TOOLS.COVERAGE, icon: '▩', label: 'Área de cobertura' },
]

function close() {
  mapStore.closeContextMenu()
  measuredDistance.value = null
}

async function create(item) {
  const base = {
    latitude: menu.value.lat,
    longitude: menu.value.lon,
    name: `${item.label} ${new Date().toLocaleTimeString('es-AR')}`,
    category: 'Referencia',
  }
  const opts = mapStore.toolOptions

  const payloads = {
    point: { ...base, type: 'point' },
    circle: { ...base, type: 'circle', radius: opts.radius, radius_unit: opts.unit },
    radial: { ...base, type: 'radial', azimuth: opts.azimuth, length_value: opts.length, length_unit: opts.unit },
    reference: { ...base, type: 'reference', reference: { radius: opts.radius, radius_unit: opts.unit } },
    rf_source: { ...base, type: 'rf_source', rf: { kind: 'Otro' } },
    antenna: { ...base, type: 'antenna', antenna: { kind: 'Omnidireccional' } },
    rf_event: { ...base, type: 'rf_event', event: { classification: 'Emisión no identificada' } },
    annotation: { ...base, type: 'annotation' },
  }

  const created = await mapStore.createObject(payloads[item.type])
  if (created) mapStore.select(created.id)
  close()
}

function activateTool(id) {
  mapStore.setTool(id)
  close()
}

/** Start measuring with this point as A (spec §13, §45). */
function measureFromHere() {
  mapStore.setTool(TOOLS.MEASURE)
  const engine = mapStore.measureEngine
  if (engine) {
    engine.start()
    engine.addPoint({ lat: menu.value.lat, lng: menu.value.lon })
  }
  measuredDistance.value = null
  close()
}

async function copyCoords() {
  const text = `${menu.value.lat.toFixed(6)}, ${menu.value.lon.toFixed(6)}`
  try {
    await navigator.clipboard.writeText(text)
    mapStore.notice = `Coordenadas copiadas: ${text}`
  } catch {
    window.prompt('Copiar coordenadas:', text)
  }
  close()
}

// Distance from the right-clicked point to the selected object. A real
// watcher rather than a polling interval: the menu is open for seconds at
// most, and this has to react to the menu closing as well as to the
// selection changing.
watch(
  [
    () => menu.value.open,
    () => mapStore.selected?.id,
    () => menu.value.lat,
    () => menu.value.lon,
  ],
  ([open]) => {
    const obj = mapStore.selected
    if (!open || !obj || obj.latitude == null) {
      measuredDistance.value = null
      return
    }
    const metres = haversine(menu.value.lat, menu.value.lon, obj.latitude, obj.longitude)
    measuredDistance.value = {
      m: metres.toFixed(0),
      km: (metres / 1000).toFixed(3),
      nm: (metres / 1852).toFixed(3),
    }
  },
  { immediate: true },
)

function onKey(event) {
  if (event.key === 'Escape') close()
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  if (mapStore.contextMenu.open) mapStore.closeContextMenu()
})
</script>

<style scoped>
/**
 * The right-click menu's ground.
 *
 * It was written as `bg-slate-900/98` in the template. Tailwind's opacity scale
 * is 0, 5, 10 ... 95, 100 — **98 is not a step**, so the class was never
 * generated and the menu had no background at all. The operator saw a menu
 * floating over the map with only the map showing through behind its text,
 * which is what "the background is very transparent and cannot be seen" is.
 *
 * Checked against the built CSS: `.bg-slate-900\/98` is absent, and the only
 * `.bg-slate-900\/N` rule in the whole bundle is `/60`. A dead utility class is
 * invisible in the source and in a unit test; it is only visible in the output,
 * which is why the ground of anything that has to be legible is pinned here in
 * CSS rather than left to an opacity step that may not exist.
 */
.aerorf-context {
  background: #0f172a;
  border-color: #334155;
}
</style>
