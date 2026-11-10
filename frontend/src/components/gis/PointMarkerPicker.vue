<template>
  <!--
    Compact dropdown instead of the old grid of buttons: the grid took a whole
    block of the panel for nine options that are chosen once per point. The
    preview keeps the current icon visible, and the ids are the historical
    ones (`marker`, `fm`, `tprs`, …), so stored points keep their meaning.

    This is *visual* classification of a point, unrelated to the technical
    `antenna` / `rf_source` object categories.
  -->
  <div class="flex items-center gap-2" role="group" aria-label="Tipo de marcador">
    <img
      class="h-7 w-7 shrink-0"
      :src="selected.icon"
      :alt="selected.label"
      :title="selected.description"
    />
    <select
      class="min-w-0 flex-1 rounded border border-borde-fuerte bg-panel-hondo px-2 py-1.5 text-[11px] text-texto disabled:cursor-not-allowed disabled:opacity-50"
      :value="selectedId"
      :disabled="disabled"
      :title="selected.description"
      aria-label="Tipo de marcador"
      @change="$emit('update:modelValue', $event.target.value)"
    >
      <option v-for="marker in POINT_MARKERS" :key="marker.id" :value="marker.id">
        {{ marker.label }}
      </option>
    </select>
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
const selected = computed(() => getPointMarker(props.modelValue))
</script>
