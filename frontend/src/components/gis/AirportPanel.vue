<template>
  <!--
    Aerodrome reference controls.

    The airports themselves are drawn by map/airports.js from data/airports.js
    and are never stored as objects. This panel only turns the layer on and
    off, filters it by country, zooms to it, and measures from one.

    The panel owns no map state. It emits what the operator asked for and the
    shell, which owns the layer, does it. That keeps the same rule as the rest
    of the app: the map engine holds Leaflet, the components hold the DOM.
  -->
  <div class="flex flex-col gap-3 p-2">
    <label class="flex items-center gap-2 text-[11px] text-slate-300">
      <input
        type="checkbox"
        :checked="visible"
        class="accent-blue-600"
        @change="emit('update:visible', $event.target.checked)"
      />
      Mostrar capa
    </label>

    <label class="flex items-center gap-2 text-[11px] text-slate-300">
      <input
        type="checkbox"
        :checked="labels"
        class="accent-blue-600"
        @change="emit('update:labels', $event.target.checked)"
      />
      Mostrar códigos (IATA)
    </label>

    <!-- What the two symbol families mean. The layer now carries every
         aerodrome in the country, so a blue dot and an amber dot have to be
         told apart, and the difference is the source's own classification. -->
    <ul class="space-y-1 border-t border-slate-800 pt-2 text-[10px] text-slate-500">
      <li class="flex items-center gap-1.5">
        <span class="inline-block h-2 w-2 rounded-full border border-sky-400 bg-sky-500/50" />
        Con tráfico: EZE, AEP y regionales con vuelo regular
      </li>
      <li class="flex items-center gap-1.5">
        <span class="inline-block h-2 w-2 rounded-full border border-amber-500 bg-amber-900/30" />
        Aeródromos menores activos: El Palomar, San Fernando y strippings
      </li>
      <li>Referencia publicada, no medida por AeroRF.</li>
    </ul>

    <div class="border-t border-slate-800 pt-2">
      <div class="mb-1 flex items-center justify-between">
        <span class="text-[10px] uppercase tracking-widest text-slate-500">
          Países
        </span>
        <span class="text-[10px] text-slate-500">{{ drawn }}/{{ total }}</span>
      </div>
      <div class="flex flex-wrap gap-1">
        <button
          v-for="c in countries"
          :key="c.code"
          class="rounded border px-1.5 py-0.5 text-[10px] transition-colors"
          :class="
            active.has(c.code)
              ? 'border-blue-500 bg-blue-600/25 text-blue-200'
              : 'border-slate-700 text-slate-500 hover:text-slate-300'
          "
          :title="`${c.label}: ${c.count} aeródromos`"
          @click="emit('toggle-country', c.code)"
        >
          {{ c.code }}
        </button>
      </div>
      <p v-if="active.size" class="mt-1.5 text-[10px] text-slate-500">
        Filtro activo. Desmarcando todos se muestran todos.
      </p>
    </div>

    <div class="border-t border-slate-800 pt-2">
      <span class="text-[10px] uppercase tracking-widest text-slate-500">
        Distancia desde aeropuerto
      </span>
      <p class="mb-1.5 mt-1 text-[10px] text-slate-500">
        Código ICAO o IATA, después un clic en el punto de destino.
      </p>
      <div class="flex gap-1">
        <input
          v-model="code"
          class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-1.5 py-1 font-mono text-[11px] uppercase text-slate-200 outline-none focus:border-blue-500"
          placeholder="SAEZ"
          maxlength="4"
          @keyup.enter="arm"
        />
        <button
          class="gis-mini-btn"
          :disabled="!valid"
          :title="armed ? 'Haga clic en el mapa' : 'Preparar la medición'"
          @click="arm"
        >
          {{ armed ? 'Clic…' : 'Medir' }}
        </button>
      </div>
      <p v-if="invalid" class="mt-1 text-[10px] text-rose-300">
        Código no reconocido.
      </p>
      <p v-else-if="armed" class="mt-1 text-[10px] text-amber-300">
        Haga clic en el punto de destino.
      </p>

      <div
        v-if="result"
        class="mt-1.5 rounded bg-slate-950/60 p-1.5 text-[10px]"
      >
        <div class="font-mono text-slate-200">
          {{ result.airport.icao }} → {{ result.km.toFixed(2) }} km
        </div>
        <div class="text-slate-500">
          {{ result.nm.toFixed(2) }} NM · rumbo {{ result.bearing.toFixed(0) }}°
          {{ result.bearing_cardinal }}
        </div>
      </div>
    </div>

    <p class="text-[10px] leading-snug text-slate-600">
      Puntos de referencia publicados, no mediciones de AeroRF.
    </p>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useSystemStore } from '@/stores/system'
import { findAirport, AIRPORT_COUNTRIES } from '@/data/airports'

const props = defineProps({
  /** Whether the layer is currently drawn. */
  visible: { type: Boolean, default: true },
  /** Show the ICAO code beside each symbol. */
  labels: { type: Boolean, default: false },
  /** The last measurement, so the panel can show it. */
  result: { type: Object, default: null },
  /** Set by the shell while waiting for a click. */
  armed: { type: Boolean, default: false },
})

const emit = defineEmits([
  'update:visible',
  'update:labels',
  'toggle-country',
  'zoom',
  'measure',
  'cancel-measure',
])

const systemStore = useSystemStore()

const code = ref('')
const countries = AIRPORT_COUNTRIES
const total = computed(() => countries.reduce((n, c) => n + c.count, 0))
const active = computed(() => new Set(systemStore.airportCountries))
const drawn = computed(() => {
  const filter = systemStore.airportCountries
  if (!filter.length) return total.value
  return countries
    .filter((c) => filter.includes(c.code))
    .reduce((n, c) => n + c.count, 0)
})

const resolved = computed(() => findAirport(code.value))
const valid = computed(() => code.value.trim().length === 4 && Boolean(resolved.value))
const invalid = computed(
  () => code.value.trim().length === 4 && !resolved.value,
)

function arm() {
  if (valid.value) emit('measure', { code: code.value.trim().toUpperCase() })
}
</script>
