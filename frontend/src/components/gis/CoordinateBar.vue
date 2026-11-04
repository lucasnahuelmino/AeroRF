<template>
  <footer class="gis-statusbar">
    <!-- Cursor coordinates (spec §5) -->
    <div class="flex items-center gap-2">
      <span class="text-[10px] uppercase tracking-widest text-texto-tenue">Cursor</span>
      <span class="font-mono text-xs text-emerald-300 tabular-nums">
        {{ mapStore.cursorText }}
      </span>
      <button
        v-if="hasCursor"
        class="gis-mini-btn"
        title="Copiar coordenadas"
        @click="copyCoordinates"
      >
        ⧉
      </button>
    </div>

    <span class="w-px h-3.5 bg-borde" />

    <!-- Format switcher (spec §5: configurable decimal / DMS) -->
    <div class="flex items-center gap-1">
      <span class="text-[10px] uppercase tracking-widest text-texto-tenue">Formato</span>
      <button
        v-for="fmt in formats"
        :key="fmt.id"
        class="gis-mini-btn"
        :class="{ '!bg-blue-600 !text-white !border-blue-500': mapStore.coordinateFormat === fmt.id }"
        :title="fmt.label"
        @click="mapStore.setCoordinateFormat(fmt.id)"
      >
        {{ fmt.label }}
      </button>
    </div>

    <span class="w-px h-3.5 bg-borde" />

    <!-- Last click, offered to the tools (spec §5) -->
    <div class="hidden md:flex items-center gap-2">
      <span class="text-[10px] uppercase tracking-widest text-texto-tenue">Último clic</span>
      <span class="font-mono text-[11px] text-texto-tenue tabular-nums">
        {{ lastClickText }}
      </span>
    </div>

    <div class="flex-1" />

    <!-- Object counts (spec §38) -->
    <div v-if="mapStore.stats" class="hidden lg:flex items-center gap-3 text-[10px] text-texto-tenue">
      <span>
        Objetos
        <b class="text-texto-medio">{{ mapStore.stats.total }}</b>
      </span>
      <span>
        Ocultos
        <b class="text-texto-medio">{{ mapStore.stats.hidden }}</b>
      </span>
      <span v-for="(n, type) in topTypes" :key="type" class="flex items-center gap-1">
        <i class="w-1.5 h-1.5 rounded-full" :style="{ background: typeColor(type) }" />
        <b class="text-texto-medio">{{ n }}</b>
      </span>
    </div>

    <span class="w-px h-3.5 bg-borde" />

    <!-- UTC time: investigation records are timestamped in UTC -->
    <div class="flex items-center gap-2">
      <span class="text-[10px] uppercase tracking-widest text-texto-tenue">UTC</span>
      <span class="font-mono text-[11px] text-texto-medio tabular-nums">{{ utcTime }}</span>
    </div>
  </footer>
</template>

<script setup>
/**
 * components/gis/CoordinateBar.vue
 * ────────────────────────────────────
 * Permanent cursor readout (spec §5) plus the format switcher, the last
 * captured click and a compact object census.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { useMapStore } from '@/stores/map'
import { useSystemStore } from '@/stores/system'

const mapStore = useMapStore()
const systemStore = useSystemStore()

const formats = [
  { id: 'dd', label: 'DD', title: 'Grados decimales' },
  { id: 'dms', label: 'GMS', title: 'Grados / minutos / segundos' },
  { id: 'dmm', label: 'GDM', title: 'Grados / minutos decimales' },
]

const utcTime = ref('')
let timer = null

const hasCursor = computed(
  () => mapStore.cursor.lat !== null && mapStore.cursor.lon !== null,
)

const lastClickText = computed(() => {
  const c = mapStore.lastClick
  if (!c) return '—'
  return `${c.lat.toFixed(6)}, ${c.lon.toFixed(6)}`
})

const topTypes = computed(() => {
  const byType = mapStore.stats?.by_type || {}
  return Object.entries(byType)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
})

function typeColor(type) {
  const obj = mapStore.objects.find((o) => o.type === type)
  return obj?.color || 'var(--texto-tenue)'
}

async function copyCoordinates() {
  const { lat, lon } = mapStore.cursor
  if (lat === null) return
  const text = mapStore.coordinateFormat === 'dd'
    ? `${lat.toFixed(6)}, ${lon.toFixed(6)}`
    : mapStore.cursorText

  try {
    await navigator.clipboard.writeText(text)
    mapStore.notice = `Coordenadas copiadas: ${text}`
  } catch {
    // Clipboard API needs a secure context; fall back to a prompt.
    systemStore.notify('No se pudo copiar. Coordenadas: ' + text, { kind: 'warn', ms: 6000 })
  }
}

function tick() {
  utcTime.value = new Date().toISOString().slice(11, 19)
}

onMounted(() => {
  tick()
  timer = setInterval(tick, 1000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<style scoped>
.gis-statusbar {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  height: 26px;
  flex: 0 0 26px;
  padding: 0 0.6rem;
  background: var(--panel);
  border-top: 1px solid var(--panel-alto);
  font-size: 0.7rem;
  overflow-x: auto;
  overflow-y: hidden;
  white-space: nowrap;
}
</style>
