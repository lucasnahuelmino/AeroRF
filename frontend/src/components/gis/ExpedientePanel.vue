<template>
  <div class="p-2 space-y-3">
    <div class="flex items-center justify-between">
      <h3 class="text-xs font-semibold uppercase tracking-widest text-slate-300">Expedientes</h3>
      <button class="gis-mini-btn" title="Actualizar" @click="expedientesStore.fetchExpedientes()">↺</button>
    </div>

    <!-- Create -->
    <details class="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5">
      <summary class="cursor-pointer text-[10px] uppercase tracking-widest text-slate-500">
        Nuevo expediente
      </summary>
      <div class="mt-2 space-y-1.5">
        <input
          v-model="draft.numero_expediente"
          placeholder="Nº de expediente"
          class="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-[11px] text-slate-100"
        />
        <div class="grid grid-cols-2 gap-1.5">
          <input
            v-model.number="draft.freq_mhz"
            type="number"
            step="0.001"
            placeholder="Frecuencia MHz"
            class="rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-100"
          />
          <input
            v-model="draft.aeropuerto"
            placeholder="Aeropuerto (ICAO)"
            class="rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-100"
          />
        </div>
        <div class="grid grid-cols-2 gap-1.5">
          <input
            v-model.number="draft.lat"
            type="number"
            step="0.000001"
            placeholder="Latitud"
            class="rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-100"
          />
          <input
            v-model.number="draft.lon"
            type="number"
            step="0.000001"
            placeholder="Longitud"
            class="rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-100"
          />
        </div>
        <button
          class="gis-mini-btn w-full"
          :disabled="!draft.numero_expediente"
          @click="create"
        >
          Crear expediente
        </button>
      </div>
    </details>

    <!-- List -->
    <p v-if="!expedientesStore.expedientes.length" class="text-center text-[11px] text-slate-500">
      Sin expedientes.
    </p>

    <ul class="space-y-1.5">
      <li
        v-for="exp in expedientesStore.expedientes"
        :key="exp.id"
        class="rounded-lg border p-2 transition"
        :class="exp.id === linkedId ? 'border-blue-500 bg-blue-950/30' : 'border-slate-800 bg-slate-900/60'"
      >
        <button class="w-full text-left" @click="link(exp)">
          <div class="flex items-center justify-between">
            <span class="font-mono text-[12px] font-semibold text-slate-200">
              {{ exp.numero_expediente }}
            </span>
            <span class="rounded bg-slate-800 px-1.5 text-[9px] text-slate-400">
              {{ exp.estado }}
            </span>
          </div>
          <div class="mt-0.5 flex items-center gap-2 text-[10px] text-slate-500">
            <span class="font-mono">{{ exp.freq_mhz }} MHz</span>
            <span>{{ exp.aeropuerto }}</span>
          </div>
        </button>

        <!-- Objects linked to this expediente (spec §43) -->
        <div v-if="exp.id === linkedId" class="mt-1.5 space-y-1 border-t border-slate-800 pt-1.5">
          <p class="text-[9px] uppercase tracking-widest text-slate-500">
            Objetos asociados ({{ linkedObjects.length }})
          </p>
          <ul v-if="linkedObjects.length" class="max-h-40 space-y-0.5 overflow-y-auto">
            <li
              v-for="obj in linkedObjects"
              :key="obj.id"
              class="flex items-center justify-between gap-1.5 rounded bg-slate-950/60 px-1.5 py-0.5 text-[10px]"
            >
              <button
                class="min-w-0 flex-1 truncate text-left text-slate-300 hover:text-blue-300"
                @click="mapStore.select(obj.id)"
              >
                {{ obj.name || typeName(obj.type) }}
              </button>
              <span class="flex-none text-slate-500">{{ obj.status }}</span>
            </li>
          </ul>
          <p v-else class="text-[10px] italic text-slate-500">
            Sin objetos. Seleccione un objeto en el mapa y use «asociar» en el Inspector.
          </p>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
/**
 * components/gis/ExpedientePanel.vue
 * ───────────────────────────────
 * Expediente management (spec §43) and the link between case files and
 * GIS objects. Reuses the existing SIARI expedientes store and API
 * unchanged.
 */
import { computed, ref, watch } from 'vue'

import { useExpedientesStore } from '@/stores/expedientes'
import { useMapStore, typeName } from '@/stores/map'

const expedientesStore = useExpedientesStore()
const mapStore = useMapStore()

const linkedId = ref(null)

const draft = ref({
  numero_expediente: '',
  freq_mhz: 118.3,
  aeropuerto: 'EZE',
  lat: null,
  lon: null,
})

const linkedObjects = computed(() =>
  mapStore.objects.filter((o) => o.expediente_id === linkedId.value),
)

// Keep the linked case in sync with the current selection.
watch(
  () => mapStore.selected?.expediente_id,
  (id) => {
    if (id) linkedId.value = id
  },
)

async function create() {
  const created = await expedientesStore.createExpediente({
    ...draft.value,
    lat: draft.value.lat ?? null,
    lon: draft.value.lon ?? null,
    estado: 'abierto',
  })
  if (created) {
    linkedId.value = created.id
    draft.value.numero_expediente = ''
    mapStore.notice = `Expediente ${created.numero_expediente} creado`
  }
}

function link(exp) {
  linkedId.value = linkedId.value === exp.id ? null : exp.id
}
</script>
