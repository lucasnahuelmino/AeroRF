<template>
  <div class="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Tipo de marcador">
    <button
      v-for="marker in POINT_MARKERS"
      :key="marker.id"
      type="button"
      role="radio"
      :aria-checked="selectedId === marker.id"
      :disabled="disabled"
      class="flex min-w-0 items-center gap-2 rounded border border-borde-fuerte bg-panel-hondo p-1.5 text-left hover:border-cyan-500/60 disabled:cursor-not-allowed disabled:opacity-50"
      :class="{ 'border-cyan-500 bg-cyan-950/30': selectedId === marker.id }"
      :title="marker.description"
      @click="$emit('update:modelValue', marker.id)"
    >
      <img class="h-7 w-7 shrink-0 rounded-full bg-elevado p-1" :src="marker.icon" alt="" />
      <span class="min-w-0">
        <strong class="block truncate text-[10px] font-semibold text-texto">{{ marker.label }}</strong>
        <small class="block truncate text-[9px] leading-tight text-texto-tenue">
          {{ marker.description }}
        </small>
      </span>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { getPointMarker, POINT_MARKERS } from '@/map/pointMarkers'

const props = defineProps({
  modelValue: { type: String, default: 'marker' },
  disabled: { type: Boolean, default: false },
})

defineEmits(['update:modelValue'])
const selectedId = computed(() => getPointMarker(props.modelValue).id)
</script>
