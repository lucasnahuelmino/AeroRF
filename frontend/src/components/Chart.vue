<template>
  <div class="rounded-lg border border-slate-800 bg-[#070d1a] p-4">
    <h3 v-if="title" class="mb-3 text-sm font-semibold text-slate-200">
      {{ title }}
    </h3>
    <div
      v-if="!data || data.length === 0"
      class="grid place-items-center text-xs text-slate-500"
      :style="{ height: `${height}px` }"
    >
      Sin datos para graficar.
    </div>
    <div
      v-else
      :id="hostId"
      class="w-full"
      :style="{ height: `${height}px` }"
    />
  </div>
</template>

<script setup>
/**
 * Chart.vue
 * ─────────
 * A Plotly chart, loaded from a partial bundle.
 *
 * ── Why the partial import ──────────────────────────────────────────────────
 * `plotly.js` ships every trace type: surface, mesh3d, choropleth, ternary,
 * polar, ohlc. That is 4.4 MB. This component draws exactly three kinds —
 * scatter, bar and line — so the import is trimmed to those. Same behaviour,
 * roughly a tenth of the weight, and it stays in the lazy chunk that only
 * the spectrum and calculator views load.
 *
 * ── Why the id is generated ────────────────────────────────────────────────
 * The container used to be `id="chart"`, a hard-coded value. Two charts on
 * one page therefore shared a node, and the second silently overwrote the
 * first: whichever mounted last took the box, and the first was left blank
 * with no error anywhere. `useId` is per-component-instance, so each chart
 * gets its own node.
 */
import { computed, onMounted, onBeforeUnmount, ref, useId, watch } from 'vue'
import Plotly from 'plotly.js/dist/plotly-basic'

const props = defineProps({
  title: { type: String, default: '' },
  /** Points as {x, y, label}. Bar charts read {label, value}. */
  data: { type: Array, required: true },
  /** 'scatter' | 'bar' | 'line' */
  type: { type: String, default: 'scatter' },
  height: { type: Number, default: 300 },
})

// Vue 3.5+ generates an id per instance. Fall back to a counter for older
// versions rather than shipping a shared id again.
const uid = useId ? useId() : null
const fallbackId = ref(0)
const hostId = computed(
  () => `aerorf-chart-${uid || (fallbackId.value += 1)}`,
)

const LAYOUT = {
  paper_bgcolor: '#070d1a',
  plot_bgcolor: '#070d1a',
  font: { color: '#cbd5e1', size: 11, family: 'Inter, sans-serif' },
  margin: { l: 56, r: 16, b: 40, t: 16 },
  hovermode: 'closest',
  xaxis: {
    gridcolor: '#16233a',
    zerolinecolor: '#16233a',
    linecolor: '#24344f',
    tickfont: { size: 10 },
  },
  yaxis: {
    gridcolor: '#16233a',
    zerolinecolor: '#16233a',
    linecolor: '#24344f',
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
        marker: { color: '#3b82f6' },
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
        line: { color: '#38bdf8', width: 2 },
        marker: { size: 5, color: '#0ea5e9' },
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
      marker: { color: '#3b82f6', size: 8 },
      text: d.map((p) => p.label || ''),
      hovertemplate: '<b>%{text}</b><br>%{x} MHz<br>%{y}<extra></extra>',
    },
  ]
}

function draw() {
  const el = document.getElementById(hostId.value)
  if (!el || !props.data?.length) return
  Plotly.react(el, buildTraces(), LAYOUT, CONFIG)
}

onMounted(draw)
// Redraw when the data changes, so a view that recomputes does not keep the
// previous plot on screen.
watch(() => props.data, draw, { deep: true })

onBeforeUnmount(() => {
  // Leaving a Plotly node behind keeps its ResizeObserver and its inline
  // styles alive in the detached element.
  const el = document.getElementById(hostId.value)
  if (el) Plotly.purge(el)
})
</script>
