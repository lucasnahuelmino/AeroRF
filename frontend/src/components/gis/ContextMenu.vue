<template>
  <Teleport to="body">
    <!--
      There is deliberately no full-screen "click-away" shield behind this menu.

      There used to be one: `fixed inset-0`, `pointer-events: auto`,
      `z-index: 1240`, closing on `@click`. It covered the entire viewport, so
      while the menu was open the map could not be touched at all. Measured with
      the menu closed, a press-and-drag moved the map 16,906 m; with the menu
      open, the same drag moved it 0 m and the menu was still open afterwards.

      Two things were wrong with it and both had to go. It intercepted the
      press, so the map never saw the `mousedown` that starts a pan. And it
      listened for `click`, which a drag never produces — press and release land
      on different points — so it survived the whole gesture.

      Dismissal is now a document listener in `onDocMouseDown`, registered only
      while the menu is open and running in the capture phase. Capture means it
      runs before Leaflet's own handler and closes the menu first; it does not
      stop propagation, so the same press still reaches the map. One press now
      dismisses the menu *and* begins the pan, instead of being swallowed by a
      transparent sheet.
    -->
    <div
      v-if="menu.open"
      ref="menuEl"
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

    <!--
      The menu closes itself on the next `mousedown` anywhere outside it, via
      `onDocMouseDown` in the script below. There is no backdrop element: a
      transparent sheet over the whole viewport is what made the map unusable
      while the menu was open, and dismissing on the press that already belongs
      to the map is both more correct and one element less.
    -->
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
const menuEl = ref(null)

/**
 * Dismiss on the next press outside the menu — and let that press through.
 *
 * Capture phase, so the menu is already closed by the time Leaflet's own
 * `mousedown` handler runs and starts the pan. Propagation is deliberately not
 * stopped: the point of the change is that one press both dismisses the menu and
 * drags the map, instead of being eaten by a transparent sheet.
 *
 * Registered only while the menu is open, rather than permanently, so a closed
 * menu costs nothing and there is no listener left behind to surprise anyone.
 */
function onDocMouseDown(event) {
  if (!menu.value.open) return
  if (menuEl.value?.contains(event.target)) return
  close()
}

watch(
  () => menu.value.open,
  (open) => {
    if (open) document.addEventListener('mousedown', onDocMouseDown, true)
    else document.removeEventListener('mousedown', onDocMouseDown, true)
  },
  { immediate: true },
)

onBeforeUnmount(() => document.removeEventListener('mousedown', onDocMouseDown, true))

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
