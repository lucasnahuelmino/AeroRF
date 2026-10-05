<template>
  <div class="card-small border p-6">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold">{{ title }}</h3>
      <div class="text-sm text-texto-tenue">&nbsp;</div>
    </div>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="bg-panel rounded-md p-4 text-center">
        <div class="text-3xl font-bold text-sky-600">{{ value }}</div>
        <div class="text-sm text-texto-tenue mt-1">{{ label }}</div>
      </div>
      <div v-if="secondary" class="bg-panel rounded-md p-4 text-center">
        <div class="text-2xl font-semibold text-warning">{{ secondary }}</div>
        <div class="text-xs text-texto-tenue mt-1">{{ secondaryLabel }}</div>
      </div>
      <div v-if="tertiary" class="bg-panel rounded-md p-4 text-center">
        <div class="text-2xl font-semibold text-success">{{ tertiary }}</div>
        <div class="text-xs text-texto-tenue mt-1">{{ tertiaryLabel }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: String,
  value: [String, Number],
  label: String,
  secondary: [String, Number],
  secondaryLabel: String,
  tertiary: [String, Number],
  tertiaryLabel: String,
})
</script>
