<template>
  <div class="bg-panel-alto border border-borde-fuerte rounded-lg p-6">
    <h3 class="text-lg font-semibold mb-4">{{ title }}</h3>
    <div class="space-y-3">
      <div
        v-for="(harmonic, idx) in harmonics"
        :key="idx"
        class="p-3 bg-on-ink-wash rounded border-l-4"
        :class="harmonic.match ? 'border-success' : 'border-borde-fuerte'"
      >
        <div class="flex justify-between items-start">
          <div>
            <div class="font-mono text-sky-600 font-semibold">{{ harmonic.formula }}</div>
            <div class="text-sm text-texto-tenue">{{ harmonic.label }}</div>
          </div>
          <div class="text-right">
            <div class="font-semibold text-lg">{{ (harmonic.freq_mhz ?? harmonic.resultado)?.toFixed(3) }} MHz</div>
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
