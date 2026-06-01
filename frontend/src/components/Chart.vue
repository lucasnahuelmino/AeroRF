<template>
  <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
    <h3 class="text-lg font-semibold mb-4">{{ title }}</h3>
    <div id="chart" style="width: 100%; height: 300px"></div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import Plotly from 'plotly.js/dist/plotly.js'

const props = defineProps({
  title: String,
  data: {
    type: Array,
    required: true,
  },
  type: {
    type: String,
    default: 'scatter', // scatter, bar, line
  },
})

onMounted(() => {
  if (props.data.length === 0) return

  const layout = {
    paper_bgcolor: '#1f2937',
    plot_bgcolor: '#111827',
    font: { color: '#e2e8f0' },
    margin: { l: 50, r: 50, b: 50, t: 50 },
    hovermode: 'closest',
    xaxis: { gridcolor: '#374151' },
    yaxis: { gridcolor: '#374151' },
  }

  const traces =
    props.type === 'scatter'
      ? [
          {
            x: props.data.map((d) => d.x),
            y: props.data.map((d) => d.y),
            mode: 'markers',
            marker: { color: '#1e40af', size: 8 },
            text: props.data.map((d) => d.label || ''),
            hovertemplate: '<b>%{text}</b><br>%{x} MHz<br>%{y}<extra></extra>',
          },
        ]
      : props.type === 'bar'
      ? [
          {
            x: props.data.map((d) => d.label),
            y: props.data.map((d) => d.value),
            type: 'bar',
            marker: { color: '#3b82f6' },
          },
        ]
      : [
          {
            x: props.data.map((d) => d.x),
            y: props.data.map((d) => d.y),
            mode: 'lines+markers',
            line: { color: '#3b82f6', width: 2 },
            marker: { size: 6 },
          },
        ]

  Plotly.newPlot('chart', traces, layout, {
    responsive: true,
    displayModeBar: false,
  })
})
</script>
