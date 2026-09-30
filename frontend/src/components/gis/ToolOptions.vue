<template>
  <div class="p-3 space-y-4">
    <!-- Active tool + hint -->
    <section class="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <div class="mb-1 flex items-center gap-2">
        <span class="text-sm">{{ TOOL_META[mapStore.activeTool]?.icon }}</span>
        <h3 class="text-xs font-semibold uppercase tracking-widest text-slate-300">
          {{ TOOL_META[mapStore.activeTool]?.label || 'Seleccionar' }}
        </h3>
      </div>
      <p class="text-[11px] leading-relaxed text-slate-400">
        {{ mapStore.toolHint || 'Seleccione una herramienta de la barra superior.' }}
      </p>
      <button
        v-if="mapStore.activeTool !== 'select'"
        class="gis-mini-btn mt-2 w-full"
        @click="mapStore.cancelTool()"
      >
        Cancelar (ESC)
      </button>
    </section>

    <!-- Unit choice (spec §10, §13, §36) -->
    <section class="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <h3 class="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-300">
        Unidades
      </h3>
      <div class="grid grid-cols-3 gap-1">
        <button
          v-for="unit in units"
          :key="unit.id"
          class="gis-mini-btn !py-1.5"
          :class="{ '!bg-blue-600 !text-white !border-blue-500': mapStore.toolOptions.unit === unit.id }"
          :title="unit.title"
          @click="setUnit(unit.id)"
        >
          {{ unit.id.toUpperCase() }}
        </button>
      </div>
      <p class="mt-2 text-[10px] text-slate-500">
        1 NM = 1,852 km = 1852 m
      </p>
    </section>

    <!-- Circle radius (spec §10, §36) -->
    <section class="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <h3 class="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-300">
        Radio del círculo
      </h3>
      <!--
        The circle is drawn on the map at this radius as soon as the tool is
        picked, so the number can be judged against the ground it will cover.
        The live figure is what the pointer is measuring, which is a different
        value from the configured one as soon as the shape is sized.
      -->
      <p
        v-if="liveCircle"
        class="mb-2 rounded bg-blue-950/50 px-2 py-1 font-mono text-[11px] leading-snug text-blue-200"
      >
        {{ liveCircle.ghost ? 'En el mapa' : 'Midiendo' }}:
        {{ liveCircle.value }}<span v-if="!liveCircle.ghost" class="text-blue-300/70"> · soltar para commitear</span>
      </p>
      <div class="mb-2 flex items-center gap-2">
        <input
          v-model.number="radius"
          type="number"
          min="0.01"
          step="0.5"
          class="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-100"
          @change="applyRadius"
        />
        <span class="text-xs font-semibold text-blue-300 uppercase">
          {{ mapStore.toolOptions.unit }}
        </span>
      </div>
      <!-- Preset radii (spec §36) -->
      <div class="flex flex-wrap gap-1">
        <button
          v-for="preset in radiusPresets"
          :key="preset"
          class="gis-mini-btn"
          :title="`${preset} ${mapStore.toolOptions.unit.toUpperCase()} = ${equivalent(preset)} km`"
          @click="applyRadius(preset)"
        >
          {{ preset }}
        </button>
      </div>
      <p class="mt-2 rounded bg-slate-950/60 px-2 py-1 font-mono text-[11px] text-emerald-300">
        {{ radiusValue }} {{ mapStore.toolOptions.unit.toUpperCase() }}
        = {{ equivalent(mapStore.toolOptions.radius) }} km
      </p>
    </section>

    <!--
      How the circle and the radial get their size. This is the control the
      operator asked for: before it, the number in this panel was drawn on the
      map as a preview and then thrown away by the second click, so typing 5 NM
      and pressing the map stored whatever distance the two clicks happened to
      be apart. Two distinct jobs, two explicit choices.
    -->
    <section
      v-if="mapStore.activeTool === 'circle' || mapStore.activeTool === 'radial'"
      class="rounded-lg border border-slate-800 bg-slate-900/60 p-3"
    >
      <h3 class="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-300">
        Tamaño
      </h3>
      <label class="flex items-start gap-2 text-[11px] text-slate-300">
        <input
          type="checkbox"
          :checked="mapStore.toolOptions.useTyped"
          class="mt-0.5 accent-blue-600"
          @change="applyUseTyped($event.target.checked)"
        />
        <span>
          Usar el valor del panel
          <span class="mt-0.5 block text-[10px] leading-snug text-slate-500">
            {{
              mapStore.toolOptions.useTyped
                ? 'Un clic y listo. La herramienta sigue armada para el siguiente.'
                : 'Dos clics: primero el centro, después el borde. El radio sale de esa distancia.'
            }}
          </span>
        </span>
      </label>
    </section>

    <!-- Radial (spec §11, §37) -->
    <section class="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <h3 class="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-300">
        Radial
      </h3>
      <!--
        The live azimuth, in degrees and in compass points, measured against
        the north reference drawn on the map. An azimuth is a bare number
        until the operator can see what it is measured from.
      -->
      <p
        v-if="liveRadial"
        class="mb-2 rounded bg-purple-950/50 px-2 py-1 font-mono text-[11px] leading-snug text-purple-200"
      >
        {{ liveRadial.ghost ? 'En el mapa' : 'Midiendo' }}:
        {{ liveRadial.azimuth.toFixed(1) }}° {{ liveRadial.compass }} ·
        {{ liveRadial.value }}
      </p>
      <label class="mb-1 block text-[10px] text-slate-500">Azimut (° desde el norte)</label>
      <div class="mb-2 flex items-center gap-2">
        <input
          v-model.number="azimuth"
          type="number"
          min="0"
          max="360"
          step="1"
          class="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-100"
          @change="applyAzimuth"
        />
        <span class="w-9 text-right font-mono text-[11px] text-purple-300">
          {{ compass }}
        </span>
      </div>
      <input
        v-model.number="azimuthSlider"
        type="range"
        min="0"
        max="360"
        step="1"
        class="mb-2 w-full accent-purple-500"
        @input="applyAzimuth(Number($event.target.value))"
      />
      <label class="mb-1 block text-[10px] text-slate-500">
        Longitud ({{ mapStore.toolOptions.unit.toUpperCase() }})
      </label>
      <div class="flex items-center gap-2">
        <input
          v-model.number="length"
          type="number"
          min="0.01"
          step="0.5"
          class="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-100"
          @change="applyLength"
        />
        <span class="text-xs font-semibold text-purple-300 uppercase">
          {{ mapStore.toolOptions.unit }}
        </span>
      </div>
    </section>

    <!-- Quick create from the last click (spec §7 method B) -->
    <section class="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <h3 class="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-300">
        Crear en posición manual
      </h3>
      <p class="mb-2 text-[10px] text-slate-500">
        Método B: introducir latitud y longitud a mano en vez de hacer clic.
      </p>
      <div class="mb-2 grid grid-cols-2 gap-1.5">
        <input
          v-model.number="manualLat"
          type="number"
          step="0.000001"
          placeholder="Latitud"
          class="rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-100"
        />
        <input
          v-model.number="manualLon"
          type="number"
          step="0.000001"
          placeholder="Longitud"
          class="rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-100"
        />
      </div>
      <div class="grid grid-cols-2 gap-1">
        <button
          v-for="preset in manualPresets"
          :key="preset.type"
          class="gis-mini-btn !py-1.5"
          :disabled="!coordsValid"
          :class="{ 'opacity-40': !coordsValid }"
          @click="createManually(preset)"
        >
          {{ preset.icon }} {{ preset.label }}
        </button>
      </div>
    </section>

    <!-- Object census -->
    <section v-if="mapStore.stats" class="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <h3 class="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-300">
        Objetos por tipo
      </h3>
      <ul class="space-y-1">
        <li
          v-for="(count, type) in mapStore.stats.by_type"
          :key="type"
          class="flex items-center justify-between text-[11px]"
        >
          <span class="flex items-center gap-1.5 text-slate-400">
            <i class="h-2 w-2 rounded-full" :style="{ background: colorOf(type) }" />
            {{ typeName(type) }}
          </span>
          <span class="font-mono text-slate-200">{{ count }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup>
/**
 * components/gis/ToolOptions.vue
 * ────────────────────────────────
 * Tool parameters (spec §10, §11, §36, §37) and manual coordinate entry
 * (spec §7, method B).
 */
import { computed, ref, watch } from 'vue'

import { TOOL_META } from '@/map/draw'
import { useMapStore, typeName } from '@/stores/map'

const mapStore = useMapStore()

const units = [
  { id: 'nm', title: 'Millas náuticas' },
  { id: 'km', title: 'Kilómetros' },
  { id: 'm', title: 'Metros' },
]

/** Preset radii from the spec (§36), in the current unit. */
const radiusPresets = computed(() => {
  const nm = [1, 2, 5, 10, 20, 50, 100]
  if (mapStore.toolOptions.unit === 'nm') return nm
  if (mapStore.toolOptions.unit === 'km') return [1, 2, 5, 10, 20, 50, 100]
  return [500, 1000, 2000, 5000, 10000, 20000, 50000]
})

const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']

// Local mirrors of the tool defaults so the inputs feel responsive.
const radius = ref(mapStore.toolOptions.radius)
const azimuth = ref(mapStore.toolOptions.azimuth)
const azimuthSlider = ref(mapStore.toolOptions.azimuth)
const length = ref(mapStore.toolOptions.length)

watch(
  () => mapStore.toolOptions,
  (opts) => {
    radius.value = opts.radius
    azimuth.value = opts.azimuth
    azimuthSlider.value = opts.azimuth
    length.value = opts.length
  },
  { deep: true },
)

const compass = computed(() => {
  const index = Math.floor(((azimuth.value % 360) + 360 + 11.25) % 360 / 22.5) % 16
  return COMPASS[index]
})

/** The entered radius expressed in km, for the equivalence readout. */
const equivalent = (value) => {
  const v = Number(value) || 0
  if (mapStore.toolOptions.unit === 'km') return v.toFixed(2)
  if (mapStore.toolOptions.unit === 'm') return (v / 1000).toFixed(2)
  return (v * 1.852).toFixed(2)
}

const radiusValue = computed(() => (Number(radius.value) || 0).toFixed(2))

/**
 * The live circle reading: the radius on the map right now.
 *
 * Two things share this field and the operator has to be able to tell them
 * apart, because they are different numbers. The configured radius is what
 * they typed; the live one is what the pointer is measuring, which only
 * becomes different once the centre is placed and the shape is sized. Labelled
 * rather than left to be inferred from the position of a number.
 */
const liveCircle = computed(() => {
  const d = mapStore.draft
  if (d?.type !== 'circle') return null
  const unit = String(d.unit || mapStore.toolOptions.unit).toUpperCase()
  const value = `${Number(d.radius ?? 0).toFixed(2)} ${unit}`
  return { value, ghost: false }
})

/** The live radial reading: degrees and compass point, plus the length. */
const liveRadial = computed(() => {
  const d = mapStore.draft
  if (d?.type !== 'radial') return null
  const azimuth = Number(d.azimuth ?? 0)
  const unit = String(d.unit || mapStore.toolOptions.unit).toUpperCase()
  return {
    azimuth,
    compass: compassFor(azimuth),
    value: `${Number(d.length ?? 0).toFixed(2)} ${unit}`,
    ghost: false,
  }
})

function compassFor(azimuth) {
  const index = Math.floor(((((azimuth % 360) + 360) % 360) + 11.25) % 360 / 22.5) % 16
  return COMPASS[index]
}

function setUnit(unit) {
  // Keep the physical size sensible when switching units: convert the
  // stored value rather than leaving a 20 NM circle as a 20 km one.
  const factor = { nm: 1.852, km: 1, m: 0.001 }[unit] / { nm: 1.852, km: 1, m: 0.001 }[mapStore.toolOptions.unit]
  const converted = (mapStore.toolOptions.radius || 0) * factor
  mapStore.setToolOption('unit', unit)
  mapStore.setToolOption('radius', round(converted, 3))
  mapStore.setToolOption('length', round(converted, 3))
}

function applyRadius(value = radius.value) {
  const v = Math.max(0.001, Number(value) || 0)
  radius.value = v
  mapStore.setToolOption('radius', v)
  // Push it to the live tool. Without this the value only sits in the store:
  // the tool snapshotted its options when it was activated, so a radius typed
  // after picking the tool was silently ignored.
  mapStore.toolManager?.setOptions({ radius: v })
}

function applyAzimuth(value = azimuth.value) {
  const v = ((Number(value) || 0) % 360 + 360) % 360
  azimuth.value = v
  azimuthSlider.value = v
  mapStore.setToolOption('azimuth', v)
  mapStore.toolManager?.setOptions({ azimuth: v })
}

function applyLength(value = length.value) {
  const v = Math.max(0.001, Number(value) || 0)
  length.value = v
  mapStore.setToolOption('length', v)
  mapStore.toolManager?.setOptions({ length: v })
}

function applyUseTyped(checked) {
  mapStore.setToolOption('useTyped', Boolean(checked))
  mapStore.toolManager?.setOptions({ useTyped: Boolean(checked) })
}

// ─── Manual entry (spec §7 method B) ────────────────────────────────────────
const manualLat = ref(mapStore.lastClick?.lat ?? -34.603722)
const manualLon = ref(mapStore.lastClick?.lon ?? -58.381592)

const coordsValid = computed(
  () =>
    Number.isFinite(manualLat.value) &&
    Number.isFinite(manualLon.value) &&
    Math.abs(manualLat.value) <= 90 &&
    Math.abs(manualLon.value) <= 180,
)

const manualPresets = [
  { type: 'point', icon: '📍', label: 'Punto' },
  { type: 'circle', icon: '◯', label: 'Círculo' },
  { type: 'rf_source', icon: '📡', label: 'Fuente' },
  { type: 'antenna', icon: '📶', label: 'Antena' },
  { type: 'rf_event', icon: '⚡', label: 'Evento' },
  { type: 'reference', icon: '🎯', label: 'Referencia' },
  { type: 'radial', icon: '➤', label: 'Radial' },
  { type: 'annotation', icon: '✎', label: 'Anotación' },
]

async function createManually(preset) {
  if (!coordsValid.value) return
  const base = {
    latitude: manualLat.value,
    longitude: manualLon.value,
    name: `${preset.label} ${new Date().toLocaleTimeString('es-AR')}`,
    category: 'Referencia',
  }

  const payloads = {
    circle: { ...base, type: 'circle', radius: mapStore.toolOptions.radius, radius_unit: mapStore.toolOptions.unit },
    radial: { ...base, type: 'radial', azimuth: mapStore.toolOptions.azimuth, length_value: mapStore.toolOptions.length, length_unit: mapStore.toolOptions.unit },
    reference: { ...base, type: 'reference', reference: { radius: mapStore.toolOptions.radius, radius_unit: mapStore.toolOptions.unit } },
    rf_source: { ...base, type: 'rf_source', rf: { kind: 'Otro' } },
    antenna: { ...base, type: 'antenna', antenna: { kind: 'Omnidireccional' } },
    rf_event: { ...base, type: 'rf_event', event: { classification: 'Emisión no identificada' } },
    annotation: { ...base, type: 'annotation' },
    point: { ...base, type: 'point' },
  }

  const created = await mapStore.createObject(payloads[preset.type])
  if (created) {
    mapStore.select(created.id)
    mapStore.engine?.setView(created.latlng?.[0], created.latlng?.[1])
  }
}

function colorOf(type) {
  return mapStore.objects.find((o) => o.type === type)?.color || '#64748b'
}

function round(value, digits) {
  const f = 10 ** digits
  return Math.round(value * f) / f
}
</script>
