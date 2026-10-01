<template>
  <div class="p-2 space-y-3">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h3 class="text-xs font-semibold uppercase tracking-widest text-slate-300">Capas</h3>
      <div class="flex gap-1">
        <button class="gis-mini-btn" title="Mostrar todas" @click="setAll(true)">👁</button>
        <button class="gis-mini-btn" title="Ocultar todas" @click="setAll(false)">🚫</button>
      </div>
    </div>

    <!-- Basemap -->
    <section class="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5">
      <h4 class="mb-1.5 text-[10px] uppercase tracking-widest text-slate-500">Mapa base</h4>
      <div class="grid grid-cols-2 gap-1">
        <button
          v-for="base in basemaps"
          :key="base.id"
          class="gis-mini-btn !py-1.5"
          :class="{ '!bg-blue-600 !text-white !border-blue-500': basemap === base.id }"
          @click="setBasemap(base.id)"
        >
          {{ base.label }}
        </button>
      </div>
    </section>

    <!-- Layer list (spec §38) -->
    <section class="space-y-1.5">
      <div
        v-for="layer in orderedLayers"
        :key="layer.id"
        class="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5"
      >
        <div class="mb-1.5 flex items-center gap-1.5">
          <button
            class="flex-none text-xs"
            :title="layer.visible ? 'Ocultar capa' : 'Mostrar capa'"
            @click="mapStore.toggleLayer(layer.key)"
          >
            {{ layer.visible ? '👁' : '🚫' }}
          </button>
          <span
            class="min-w-0 flex-1 truncate text-[11px]"
            :class="layer.visible ? 'text-slate-200' : 'text-slate-500'"
          >
            {{ layer.name }}
          </span>
          <span class="flex-none font-mono text-[10px] text-slate-500">
            {{ layer.object_count }}
          </span>
          <button
            class="flex-none text-[11px]"
            :title="layer.locked ? 'Desbloquear' : 'Bloquear'"
            @click="mapStore.toggleLayerLock(layer.key)"
          >
            {{ layer.locked ? '🔒' : '🔓' }}
          </button>
        </div>

        <div class="flex items-center gap-1.5">
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            :value="layer.opacity"
            class="h-1 flex-1 accent-blue-500"
            @input="onOpacity(layer.key, $event)"
          />
          <span class="w-8 flex-none text-right font-mono text-[10px] text-slate-500">
            {{ Math.round(layer.opacity * 100) }}%
          </span>
        </div>
      </div>
    </section>

    <!-- Provenance legend (spec §58) -->
    <section class="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5">
      <h4 class="mb-1.5 text-[10px] uppercase tracking-widest text-slate-500">
        Procedencia de los datos
      </h4>
      <ul class="space-y-1 text-[10px]">
        <li v-for="(label, key) in provenanceLabels" :key="key" class="flex items-center gap-1.5">
          <i class="h-2 w-2 rounded-full" :style="{ background: provenanceColor(key) }" />
          <span class="text-slate-400">{{ label }}</span>
        </li>
      </ul>
      <p class="mt-1.5 text-[9px] leading-snug text-slate-600">
        AeroRF distingue siempre el origen de cada dato. Un valor sin fuente
        verificable se muestra como «dato no disponible».
      </p>
    </section>

    <!-- Export (spec §46) -->
    <section class="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5">
      <h4 class="mb-1.5 text-[10px] uppercase tracking-widest text-slate-500">Exportar</h4>
      <div class="grid grid-cols-3 gap-1">
        <a
          v-for="format in exportFormats"
          :key="format.id"
          :href="format.url"
          class="gis-mini-btn text-center !py-1.5 no-underline"
          :title="format.title"
        >
          {{ format.label }}
        </a>
      </div>
      <label class="mt-2 flex items-center gap-1.5 text-[10px] text-slate-500">
        <input
          v-model="includeHistory"
          type="checkbox"
          class="accent-blue-600"
        />
        Incluir historial en el GeoJSON
      </label>
    </section>
  </div>
</template>

<script setup>
/**
 * components/gis/LayerPanel.vue
 * ───────────────────────────
 * LayerManager (spec §38): visibility, opacity, order, lock, plus the
 * basemap switcher and the provenance legend (spec §58).
 */
import { computed, ref } from 'vue'

import { exporter } from '@/api/client'
import { useMapStore } from '@/stores/map'

const mapStore = useMapStore()

const basemap = ref('osm')
const includeHistory = ref(false)

const basemaps = [
  { id: 'osm', label: 'OSM' },
  { id: 'relief', label: 'Relieve' },
]

/** Draw order: base map first, user objects last. */
const orderedLayers = computed(() =>
  [...mapStore.layers].sort((a, b) => a.order_index - b.order_index),
)

const provenanceLabels = computed(
  () => mapStore.vocabulary.provenance_labels || {},
)

const exportFormats = computed(() => [
  { id: 'geojson', label: 'GeoJSON', title: 'Exportar GeoJSON (EPSG:4326)', url: exporter.geojsonUrl({ include_history: includeHistory.value }) },
  { id: 'kml', label: 'KML', title: 'Exportar KML 2.2', url: exporter.kmlUrl() },
  { id: 'csv', label: 'CSV', title: 'Exportar CSV', url: exporter.csvUrl() },
])

function onOpacity(key, event) {
  mapStore.setLayerOpacity(key, Number(event.target.value))
}

async function setAll(visible) {
  for (const layer of mapStore.layers) {
    if (layer.visible !== visible) await mapStore.toggleLayer(layer.key, visible)
  }
}

function setBasemap(kind) {
  basemap.value = kind
  mapStore.engine?.setBasemap(kind)
}

function provenanceColor(key) {
  return {
    observed: '#f97316',
    historical: '#8b5cf6',
    live: '#22c55e',
    calculated: '#3b82f6',
    user: '#e2e8f0',
  }[key] || '#64748b'
}
</script>
