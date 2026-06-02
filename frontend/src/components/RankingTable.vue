<template>
  <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
    <h3 class="text-lg font-semibold mb-4">{{ title }}</h3>
    <div class="space-y-3">
      <div
        v-for="(result, idx) in results"
        :key="idx"
        class="p-4 bg-gray-700 rounded border-l-4"
        :class="getScoreClass(result.score)"
      >
        <div class="flex justify-between items-start mb-2">
          <div>
            <div class="font-mono text-lg font-semibold" :class="getFormulaClass(result.score)">
              {{ result.formula }}
            </div>
            <div class="text-sm text-gray-400 mt-1">{{ result.tipo }}</div>
          </div>
          <div class="text-right">
            <div class="text-2xl font-bold text-success">{{ result.score }}%</div>
          </div>
        </div>

        <div class="grid grid-cols-3 gap-3 text-sm mb-2">
          <div>
            <span class="text-gray-400">Resultado:</span>
            <div class="font-semibold text-primary">{{ (result.result_mhz ?? result.resultado)?.toFixed(3) }} MHz</div>
          </div>
          <div>
            <span class="text-gray-400">Error:</span>
            <div :class="(result.error_khz ?? 0) < 5 ? 'text-success' : 'text-warning'">
              {{ (result.error_khz ?? 0)?.toFixed(2) }} kHz
            </div>
          </div>
          <div>
            <span class="text-gray-400">Proximidad:</span>
            <div class="text-gray-200">{{ Math.round(((result.proximity ?? result.score_breakdown?.proximity ?? 0) * 100)) }}%</div>
          </div>
        </div>

        <button
          @click="$emit('select', result)"
          class="w-full mt-2 px-3 py-1 bg-blue-900 hover:bg-blue-800 rounded text-sm transition-colors"
        >
          📌 Usar
        </button>
      </div>

      <div v-if="results.length === 0" class="text-center py-8 text-gray-400">
        No hay resultados. Ingresa parámetros y calcula.
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: String,
  results: {
    type: Array,
    required: true,
  },
})

defineEmits(['select'])

const getScoreClass = (score) => {
  if (score >= 85) return 'border-success bg-green-900/20'
  if (score >= 70) return 'border-warning bg-yellow-900/20'
  return 'border-gray-600'
}

const getFormulaClass = (score) => {
  if (score >= 85) return 'text-success'
  if (score >= 70) return 'text-warning'
  return 'text-primary'
}
</script>
