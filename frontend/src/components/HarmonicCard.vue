<template>
  <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
    <h3 class="text-lg font-semibold mb-4">{{ title }}</h3>
    <div class="space-y-3">
      <div
        v-for="(harmonic, idx) in harmonics"
        :key="idx"
        class="p-3 bg-gray-700 rounded border-l-4"
        :class="harmonic.match ? 'border-success' : 'border-gray-600'"
      >
        <div class="flex justify-between items-start">
          <div>
            <div class="font-mono text-primary font-semibold">{{ harmonic.formula }}</div>
            <div class="text-sm text-gray-400">{{ harmonic.label }}</div>
          </div>
          <div class="text-right">
            <div class="font-semibold text-lg">{{ harmonic.resultado.toFixed(3) }} MHz</div>
            <div v-if="harmonic.match" class="text-xs text-success">✓ Coincide</div>
            <div v-else class="text-xs text-gray-400">Error: {{ harmonic.error.toFixed(2) }} kHz</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: String,
  harmonics: {
    type: Array,
    required: true,
  },
})
</script>
