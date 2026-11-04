<template>
  <div class="rounded-lg border border-borde bg-[var(--fondo)] p-4">
    <h3 v-if="title" class="mb-3 text-sm font-semibold text-texto">
      {{ title }}
    </h3>

    <!--
      The placeholder exists because the library is fetched after this
      component mounts. Without it the box is simply blank for a second and a
      half, which reads as a broken section rather than a slow one.
    -->
    <div
      v-if="loading"
      class="grid place-items-center gap-2"
      :style="{ height: `${height}px` }"
    >
      <div class="h-1 w-40 overflow-hidden rounded-full bg-panel-alto">
        <div class="h-full w-1/3 animate-pulse rounded-full bg-sky-600" />
      </div>
      <span class="text-[10px] text-texto-invisible">Cargando el motor de gráficos…</span>
    </div>

    <div
      v-else-if="error"
      class="grid place-items-center text-center"
      :style="{ height: `${height}px` }"
    >
      <div>
        <p class="text-xs text-amber-300">No se pudo cargar el motor de gráficos.</p>
        <p class="mt-1 text-[10px] text-texto-invisible">{{ error }}</p>
        <button
          class="mt-2 rounded border border-borde-fuerte px-2 py-1 text-[10px] text-texto-medio hover:bg-panel-alto"
          @click="draw"
        >
          Reintentar
        </button>
      </div>
    </div>

    <div
      v-else-if="!data || data.length === 0"
      class="grid place-items-center text-xs text-texto-tenue"
      :style="{ height: `${height}px` }"
    >
      Sin datos para graficar.
    </div>

    <div v-else :id="hostId" class="w-full" :style="{ height: `${height}px` }" />
  </div>
</template>

<script setup>
/**
 * Chart.vue
 * ─────────
 * A Plotly chart, loaded on demand.
 *
 * ── Why the import is dynamic ──────────────────────────────────────────────
 * The library was imported statically, which put it in the module graph of
 * every view that shows a chart. Opening the RF calculator meant downloading
 * and parsing a megabyte before the page could paint anything, so the section
 * appeared to hang.
 *
 * The component now renders first and fetches the library in the background.
 * The calculator is usable while it arrives, and the chart fills in behind a
 * placeholder that says what is happening. On a second visit the module is
 * already in the browser cache and there is no wait at all.
 *
 * ── Why the partial bundle ────────────────────────────────────────────────
 * `plotly.js` ships every trace type: surface, mesh3d, choropleth, ternary,
 * polar, ohlc. That is 4.4 MB. This component draws three kinds, so the import
 * is trimmed to `plotly-basic`: about a quarter of the weight, same behaviour.
 *
 * ── Why the id is generated ────────────────────────────────────────────────
 * The container used to be `id="chart"`. Two charts on one page therefore
 * shared a node, and the second silently overwrote the first: whichever
 * mounted last took the box, and the first was left blank with no error
 * anywhere. `useId` is per component instance.
 */
import { computed, onMounted, onBeforeUnmount, ref, useId, watch } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  /** Points as {x, y, label}. Bar charts read {label, value}. */
  data: { type: Array, required: true },
  /** 'scatter' | 'bar' | 'line' */
  type: { type: String, default: 'scatter' },
  height: { type: Number, default: 300 },
})

const uid = useId ? useId() : null
const fallbackId = ref(0)
const hostId = computed(
  () => `aerorf-chart-${uid || (fallbackId.value += 1)}`,
)

const loading = ref(true)
const error = ref('')
/** Resolves to the module, so the fetch happens once per page however many
 *  charts there are, rather than once per chart. */
let library = null

const LAYOUT = {
  paper_bgcolor: 'var(--fondo)',
  plot_bgcolor: 'var(--fondo)',
  font: { color: 'var(--texto-medio)', size: 11, family: 'Inter, sans-serif' },
  margin: { l: 56, r: 16, b: 40, t: 16 },
  hovermode: 'closest',
  xaxis: {
    gridcolor: 'var(--panel-alto)',
    zerolinecolor: 'var(--panel-alto)',
    linecolor: 'var(--borde-fuerte)',
    tickfont: { size: 10 },
  },
  yaxis: {
    gridcolor: 'var(--panel-alto)',
    zerolinecolor: 'var(--panel-alto)',
    linecolor: 'var(--borde-fuerte)',
    tickfont: { size: 10 },
  },
}

const CONFIG = { responsive: true, displayModeBar: false, displaylogo: false }

function buildTraces() {
  const d = props.data || []
  if (props.type === 'bar') {
    return [
      {
        x: d.map((p) => p.label),
        y: d.map((p) => p.value),
        type: 'bar',
        marker: { color: 'var(--signal-on-ink)' },
        hovertemplate: '<b>%{x}</b><br>%{y}<extra></extra>',
      },
    ]
  }
  if (props.type === 'line') {
    return [
      {
        x: d.map((p) => p.x),
        y: d.map((p) => p.y),
        mode: 'lines+markers',
        line: { color: 'var(--trazo-observado)', width: 2 },
        marker: { size: 5, color: 'var(--trazo-observado)' },
        text: d.map((p) => p.label || ''),
        hovertemplate: '<b>%{text}</b><br>%{x} MHz<br>%{y}<extra></extra>',
      },
    ]
  }
  return [
    {
      x: d.map((p) => p.x),
      y: d.map((p) => p.y),
      mode: 'markers',
      marker: { color: 'var(--signal-on-ink)', size: 8 },
      text: d.map((p) => p.label || ''),
      hovertemplate: '<b>%{text}</b><br>%{x} MHz<br>%{y}<extra></extra>',
    },
  ]
}

async function draw() {
  if (!props.data?.length) return
  loading.value = true
  error.value = ''
  try {
    // Awaited once and cached in module scope: several charts on one page
    // share a single fetch.
    if (!library) {
      library = await import('plotly.js/dist/plotly-basic')
    }
    const Plotly = library.default || library
    const el = document.getElementById(hostId.value)
    if (!el) return
    Plotly.react(el, buildTraces(), LAYOUT, CONFIG)
  } catch (e) {
    error.value = e?.message || 'No se pudo cargar.'
  } finally {
    loading.value = false
  }
}

onMounted(draw)
// Redraw when the data changes, so a view that recomputes does not keep the
// previous plot on screen.
watch(() => props.data, draw, { deep: true })

onBeforeUnmount(() => {
  // Leaving a Plotly node behind keeps its ResizeObserver and its inline
  // styles alive in the detached element.
  const el = document.getElementById(hostId.value)
  if (el && library) {
    const Plotly = library.default || library
    Plotly.purge(el)
  }
})
</script>
