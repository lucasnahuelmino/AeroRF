<template>
  <div class="flex h-full flex-col">
    <header class="flex flex-0 items-center justify-between border-b border-slate-800 px-3 py-2">
      <h2 class="text-xs font-semibold uppercase tracking-widest text-slate-300">Inspector</h2>
      <button
        v-if="object || aircraft"
        class="gis-mini-btn"
        title="Cerrar inspección"
        @click="closeInspection()"
      >
        ✕
      </button>
    </header>

    <div class="flex-1 overflow-y-auto">
      <!--
        Nothing selected. An aircraft counts as something selected: clicking one on
        the map fills this panel in. Before, the click set a value in the flights
        store that nothing displayed, so the panel kept saying "select an object"
        while the operator had just clicked an aeroplane.
      -->
      <div v-if="!object && !aircraft" class="p-4 text-center text-xs text-slate-500">
        <div class="mb-2 text-2xl opacity-40">◎</div>
        Seleccione un objeto o una aeronave en el mapa.
      </div>

      <!--
        The aircraft. Everything the map knows about the one that was clicked, in
        one place, so the operator does not have to keep the flights panel open
        beside the map to read what they just picked.

        `v-else-if`, not `v-if`. `v-else` pairs with the *immediately preceding*
        conditional sibling, so a second `v-if` in between steals it: with
        nothing selected the "select an object" block and the object inspector
        both rendered, and the object inspector read `object.color` off a null
        `object`. That crashed the panel and took the whole map shell down with
        it — the map was not drawn at all, which is how it showed up.
      -->
      <template v-else-if="!object && aircraft">
        <section class="border-b border-slate-800 p-2.5">
          <div class="mb-2 flex items-start gap-2">
            <span class="mt-0.5 text-base leading-none text-sky-400">✈</span>
            <div class="min-w-0 flex-1">
              <div class="truncate text-[13px] font-semibold text-slate-100">
                {{ aircraft.callsign || aircraft.icao24 }}
              </div>
              <div class="font-mono text-[10px] uppercase tracking-wider text-slate-500">
                {{ aircraft.icao24 }} · {{ aircraft.origin_country || 'origen desconocido' }}
              </div>
            </div>
          </div>

          <!-- Provenance first: it says where every number below came from. -->
          <p class="mb-2 rounded border border-slate-800 bg-slate-950/60 px-2 py-1 text-[10px] text-slate-400">
            <span class="text-slate-500">Procedencia:</span>
            <span :class="aircraftIsLive ? 'text-emerald-300' : 'text-amber-300'">
              {{ aircraftIsLive ? 'posición en vivo' : 'última posición conocida' }}
            </span>
            <template v-if="aircraft.position_source">
              · fuente {{ aircraft.position_source }}
            </template>
            <template v-if="aircraft.position_age_s != null">
              · hace {{ fmtAge(aircraft.position_age_s) }}
            </template>
          </p>

          <dl class="grid grid-cols-2 gap-x-2 gap-y-1 text-[11px]">
            <dt class="text-slate-500">Altitud</dt>
            <dd class="text-right font-mono text-slate-200">
              {{ aircraft.altitude != null ? fmt(aircraft.altitude, ' m') : '—' }}
            </dd>
            <dt class="text-slate-500">Velocidad</dt>
            <dd class="text-right font-mono text-slate-200">
              {{ aircraft.velocity != null ? fmt(aircraft.velocity, ' m/s') : '—' }}
            </dd>
            <dt class="text-slate-500">Rumbo</dt>
            <dd class="text-right font-mono text-slate-200">
              {{ aircraft.heading != null ? fmt(aircraft.heading, '°') : '—' }}
            </dd>
            <dt class="text-slate-500">En tierra</dt>
            <dd class="text-right text-slate-200">{{ aircraft.on_ground ? 'Sí' : 'No' }}</dd>
            <dt class="text-slate-500">Posición</dt>
            <dd class="text-right font-mono text-slate-200">
              <template v-if="aircraft.latitude != null">
                {{ aircraft.latitude.toFixed(4) }}, {{ aircraft.longitude.toFixed(4) }}
              </template>
              <template v-else>—</template>
            </dd>
            <dt class="text-slate-500">Visto</dt>
            <dd class="text-right font-mono text-slate-200">
              {{ aircraft.time_position ? fmtTime(aircraft.time_position) : '—' }}
            </dd>
          </dl>
        </section>

        <!-- The trajectory, which is what the aeroplane was clicked for. -->
        <section
          v-if="trajectory"
          class="border-b border-slate-800 p-2.5"
        >
          <h3 class="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            Trayectoria
          </h3>
          <dl class="grid grid-cols-2 gap-x-2 gap-y-1 text-[11px]">
            <dt class="text-slate-500">Puntos</dt>
            <dd class="text-right font-mono text-slate-200">{{ trajectoryPoints }}</dd>
            <dt class="text-slate-500">Procedencia</dt>
            <dd class="text-right text-slate-200">{{ trajectoryProvenance }}</dd>
            <dt class="text-slate-500">Longitud</dt>
            <dd class="text-right font-mono text-slate-200">{{ trajectoryLength }}</dd>
          </dl>
          <p
            v-for="note in provenanceNotes"
            :key="note.text"
            class="mt-1 text-[10px] leading-snug text-slate-500"
          >
            {{ note.text }}
          </p>
        </section>

        <!--
          Distances to RF objects. The header says what this is and is not:
          a geometric proximity, never a cause.
        -->
        <section v-if="distances.length" class="border-b border-slate-800 p-2.5">
          <h3 class="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            Objetos RF cercanos
          </h3>
          <ul class="space-y-1">
            <li
              v-for="row in distances"
              :key="row.id"
              class="flex items-baseline justify-between gap-2 text-[11px]"
            >
              <button
                class="truncate text-left text-sky-300 hover:underline"
                :title="`Ir a ${row.name}`"
                @click="centerOn(row)"
              >
                {{ row.name }}
              </button>
              <span class="flex-none font-mono text-slate-400">{{ fmt(row.distance_km, ' km') }}</span>
            </li>
          </ul>
          <p class="mt-2 text-[10px] leading-snug text-slate-500">
            Proximidad geométrica a un radio de {{ distancesRadius }}. No implica causalidad: que un
            objeto esté cerca no dice que haya interferido con esta aeronave.
          </p>
        </section>

        <div class="p-3">
          <button class="gis-mini-btn w-full" @click="openFlights">
            Ver en el panel de vuelos
          </button>
        </div>
      </template>

      <template v-else>
        <!-- Identity -->
        <section class="border-b border-slate-800 p-2.5">
          <div class="mb-2 flex items-start gap-2">
            <span
              class="mt-1 h-3 w-3 flex-none rounded-full"
              :style="{ background: object.color }"
            />
            <div class="min-w-0 flex-1">
              <input
                v-model="nameDraft"
                class="w-full rounded border border-transparent bg-transparent px-1 py-0.5 text-sm font-semibold text-slate-100 hover:border-slate-700 focus:border-blue-600 focus:bg-slate-950 focus:outline-none"
                :disabled="locked"
                @change="saveField('name', nameDraft)"
              />
              <div class="px-1 text-[10px] uppercase tracking-wide text-slate-500">
                {{ typeName(object.type) }} · ID {{ object.id }}
              </div>
            </div>
          </div>

          <!-- Status (spec §15) -->
          <label class="mb-1 block text-[10px] uppercase tracking-widest text-slate-500">
            Estado
          </label>
          <div class="mb-2 grid grid-cols-2 gap-1">
            <select
              v-model="statusDraft"
              class="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-100"
              :disabled="locked"
              @change="saveStatus"
            >
              <option v-for="state in states" :key="state" :value="state">
                {{ state }}
              </option>
            </select>
            <button
              class="gis-mini-btn"
              :disabled="locked"
              title="Bloquear para evitar ediciones accidentales"
              @click="toggleLock"
            >
              {{ object.locked ? '🔒' : '🔓' }}
            </button>
          </div>

          <div class="flex flex-wrap gap-1">
            <button class="gis-mini-btn" @click="mapStore.engine?.fitObject(object)">⊙ Centrar</button>
            <button class="gis-mini-btn" @click="mapStore.duplicateObject(object.id)">⧉ Duplicar</button>
            <button class="gis-mini-btn" @click="toggleVisibility">
              {{ object.visible ? '👁 Ocultar' : '👁 Mostrar' }}
            </button>
            <button class="gis-mini-btn danger" @click="remove">🗑 Eliminar</button>
          </div>
        </section>

        <!-- General properties (spec §9) -->
        <section class="border-b border-slate-800 p-2.5">
          <h3 class="mb-2 text-[10px] uppercase tracking-widest text-slate-500">
            Propiedades generales
          </h3>
          <dl class="space-y-1 text-[11px]">
            <div class="flex justify-between gap-2">
              <dt class="text-slate-500">Descripción</dt>
              <dd class="min-w-0 flex-1 text-right text-slate-300">
                <input
                  v-model="descriptionDraft"
                  class="w-full rounded border border-transparent bg-transparent px-1 text-right text-[11px] text-slate-300 hover:border-slate-700 focus:border-blue-600 focus:bg-slate-950 focus:outline-none"
                  :disabled="locked"
                  @change="saveField('description', descriptionDraft)"
                />
              </dd>
            </div>
            <div class="flex justify-between gap-2">
              <dt class="text-slate-500">Capa</dt>
              <dd class="text-slate-300">{{ object.properties?.layer_name || object.layer || '—' }}</dd>
            </div>
            <div class="flex justify-between gap-2">
              <dt class="text-slate-500">Visible</dt>
              <dd class="text-slate-300">{{ object.visible ? 'Sí' : 'No' }}</dd>
            </div>
            <div class="flex justify-between gap-2">
              <dt class="text-slate-500">Procedencia</dt>
              <dd class="text-right text-slate-300">
                {{ provenanceLabel(object.provenance) }}
              </dd>
            </div>
            <div class="flex justify-between gap-2">
              <dt class="text-slate-500">Expediente</dt>
              <dd class="text-slate-300">
                {{ object.properties?.expediente || '—' }}
                <button
                  v-if="!object.expediente_id"
                  class="ml-1 underline hover:text-blue-400"
                  @click="linkExpediente"
                >
                  asociar
                </button>
              </dd>
            </div>
            <div class="flex justify-between gap-2">
              <dt class="text-slate-500">Creado</dt>
              <dd class="text-slate-300">{{ formatDate(object.created_at) }}</dd>
            </div>
            <div class="flex justify-between gap-2">
              <dt class="text-slate-500">Modificado</dt>
              <dd class="text-slate-300">{{ formatDate(object.updated_at) }}</dd>
            </div>
          </dl>
        </section>

        <!-- Geometry -->
        <section v-if="hasGeometry" class="border-b border-slate-800 p-2.5">
          <h3 class="mb-2 text-[10px] uppercase tracking-widest text-slate-500">
            Geometría
          </h3>
          <div v-if="isPoint" class="space-y-1.5">
            <div class="grid grid-cols-2 gap-1.5">
              <label class="block">
                <span class="mb-0.5 block text-[10px] text-slate-500">Latitud</span>
                <input
                  v-model.number="latDraft"
                  type="number"
                  step="0.000001"
                  class="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-100"
                  :disabled="locked"
                  @change="savePosition"
                />
              </label>
              <label class="block">
                <span class="mb-0.5 block text-[10px] text-slate-500">Longitud</span>
                <input
                  v-model.number="lonDraft"
                  type="number"
                  step="0.000001"
                  class="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-100"
                  :disabled="locked"
                  @change="savePosition"
                />
              </label>
            </div>
            <button class="gis-mini-btn w-full" :disabled="locked" @click="copyCoords">
              ⧉ Copiar coordenadas
            </button>
          </div>

          <!-- Circle radius (spec §10) -->
          <div v-if="hasRadius" class="mt-1 space-y-1.5">
            <div class="flex items-center gap-1.5">
              <input
                v-model.number="radiusDraft"
                type="number"
                min="0.01"
                step="0.5"
                class="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-100"
                :disabled="locked"
                @change="saveRadius"
              />
              <select
                v-model="radiusUnitDraft"
                class="rounded border border-slate-700 bg-slate-950 px-1 py-1 text-[11px] text-slate-100"
                :disabled="locked"
                @change="saveRadius"
              >
                <option v-for="u in units" :key="u" :value="u">{{ u.toUpperCase() }}</option>
              </select>
            </div>
            <p class="rounded bg-slate-950/60 px-2 py-1 font-mono text-[11px] text-emerald-300">
              {{ radiusValue }} {{ radiusUnitDraft.toUpperCase() }}
              = {{ radiusKm }} km
            </p>
          </div>

          <!-- Radial (spec §11) -->
          <div v-if="object.azimuth !== null && object.azimuth !== undefined" class="mt-1 space-y-1.5">
            <div class="grid grid-cols-2 gap-1.5">
              <label class="block">
                <span class="mb-0.5 block text-[10px] text-slate-500">Azimut (°)</span>
                <input
                  v-model.number="azimuthDraft"
                  type="number"
                  min="0"
                  max="360"
                  step="1"
                  class="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-100"
                  :disabled="locked"
                  @change="saveRadial"
                />
              </label>
              <label class="block">
                <span class="mb-0.5 block text-[10px] text-slate-500">
                  Longitud ({{ lengthUnitDraft.toUpperCase() }})
                </span>
                <input
                  v-model.number="lengthDraft"
                  type="number"
                  min="0.01"
                  step="0.5"
                  class="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-100"
                  :disabled="locked"
                  @change="saveRadial"
                />
              </label>
            </div>
            <p v-if="object.radial" class="rounded bg-slate-950/60 px-2 py-1 font-mono text-[11px] text-purple-300">
              {{ object.radial.azimuth.toFixed(1) }}° ·
              {{ object.radial.length_nm.toFixed(2) }} NM ·
              {{ object.radial.length_km.toFixed(2) }} km
            </p>
          </div>

          <!-- Line metrics (spec §12, §13) -->
          <dl v-if="object.metrics?.total_length_nm != null" class="mt-1.5 space-y-1 text-[11px]">
            <div class="flex justify-between">
              <dt class="text-slate-500">Longitud total</dt>
              <dd class="font-mono text-slate-300">
                {{ object.metrics.total_length_km.toFixed(3) }} km /
                {{ object.metrics.total_length_nm.toFixed(3) }} NM
              </dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-slate-500">Puntos</dt>
              <dd class="font-mono text-slate-300">{{ object.metrics.point_count }}</dd>
            </div>
          </dl>
        </section>

        <!-- Type-specific payload -->
        <section v-if="typePayload" class="border-b border-slate-800 p-2.5">
          <h3 class="mb-2 text-[10px] uppercase tracking-widest text-slate-500">
            {{ typePayload.title }}
          </h3>
          <div class="space-y-1.5">
            <div v-for="row in typePayload.rows" :key="row.key" class="flex justify-between gap-2 text-[11px]">
              <span class="text-slate-500">{{ row.label }}</span>
              <span class="font-mono text-slate-300">
                {{ row.value ?? 'dato no disponible' }}
              </span>
            </div>
          </div>
          <button
            v-if="typePayload.editable"
            class="gis-mini-btn mt-2 w-full"
            :disabled="locked"
            @click="openTypeEditor = !openTypeEditor"
          >
            {{ openTypeEditor ? 'Cerrar editor' : 'Editar atributos' }}
          </button>

          <div v-if="openTypeEditor && typePayload.editable" class="mt-2 space-y-1.5 rounded border border-slate-800 bg-slate-950/50 p-2">
            <label v-for="field in typePayload.fields" :key="field.key" class="block">
              <span class="mb-0.5 block text-[10px] text-slate-500">{{ field.label }}</span>
              <component
                :is="field.options ? 'select' : 'input'"
                v-model="typeDraft[field.key]"
                :type="field.type || 'text'"
                :step="field.step"
                class="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-[11px] text-slate-100"
              >
                <option v-if="field.options" v-for="opt in field.options" :key="opt" :value="opt">
                  {{ opt }}
                </option>
              </component>
            </label>
            <button class="gis-mini-btn w-full" :disabled="locked" @click="saveTypePayload">
              Guardar atributos
            </button>
          </div>
        </section>

        <!-- Distances to this object (spec §30) -->
        <section v-if="object.latitude != null" class="border-b border-slate-800 p-2.5">
          <div class="mb-2 flex items-center justify-between">
            <h3 class="text-[10px] uppercase tracking-widest text-slate-500">
              Distancia desde el cursor
            </h3>
            <button class="gis-mini-btn" @click="measureFromCursor">Medir</button>
          </div>
          <p v-if="distanceFromCursor === null" class="text-[11px] text-slate-500">
            Mueva el cursor sobre el mapa.
          </p>
          <p v-else class="font-mono text-[11px] text-cyan-300">
            {{ distanceFromCursor.km }} km / {{ distanceFromCursor.nm }} NM
          </p>
        </section>

        <!-- Notes (spec §14, §42) -->
        <section class="border-b border-slate-800 p-2.5">
          <h3 class="mb-2 text-[10px] uppercase tracking-widest text-slate-500">
            Notas (append-only)
          </h3>
          <div class="mb-2 space-y-1.5">
            <p v-if="!notes.length" class="text-[11px] italic text-slate-500">
              Sin notas. Las notas se conservan para siempre y nunca se sobrescriben.
            </p>
            <div
              v-for="note in notes"
              :key="note.id"
              class="rounded border border-slate-800 bg-slate-950/60 p-1.5"
            >
              <div class="text-[11px] text-slate-200">{{ note.text }}</div>
              <div class="mt-0.5 text-[9px] text-slate-600">
                {{ formatDate(note.timestamp) }}<span v-if="note.user"> · {{ note.user }}</span>
              </div>
            </div>
          </div>
          <div class="flex gap-1">
            <input
              v-model="noteDraft"
              placeholder="Nueva nota…"
              class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-[11px] text-slate-100"
              @keyup.enter="addNote"
            />
            <button class="gis-mini-btn" :disabled="!noteDraft.trim()" @click="addNote">+</button>
          </div>
        </section>

        <!-- History (spec §41) -->
        <section class="p-2">
          <div class="mb-2 flex items-center justify-between">
            <h3 class="text-[10px] uppercase tracking-widest text-slate-500">
              Historial ({{ history.length }})
            </h3>
            <button
              v-if="history.length > 12"
              class="gis-mini-btn"
              @click="showAllHistory = !showAllHistory"
            >
              {{ showAllHistory ? 'Ver menos' : 'Ver todo' }}
            </button>
          </div>
          <ol v-if="history.length" class="space-y-1">
            <li
              v-for="row in visibleHistory"
              :key="row.id"
              class="rounded border border-slate-800/60 bg-slate-950/40 p-1.5 text-[10px]"
            >
              <div class="flex justify-between gap-2">
                <span class="font-semibold text-slate-300">{{ row.field }}</span>
                <span class="text-slate-600">{{ formatDate(row.changed_at) }}</span>
              </div>
              <div class="font-mono text-slate-500">
                <span class="text-rose-400/80 line-through">{{ row.old_value ?? '—' }}</span>
                <span class="mx-1">→</span>
                <span class="text-emerald-400/90">{{ row.new_value ?? '—' }}</span>
              </div>
              <div v-if="row.comment" class="mt-0.5 text-slate-600 italic">
                {{ row.comment }}
              </div>
            </li>
          </ol>
          <p v-else class="text-[11px] italic text-slate-500">Sin cambios registrados.</p>
        </section>
      </template>
    </div>
  </div>
</template>

<script setup>
/**
 * components/gis/InspectorPanel.vue
 * ────────────────────────────────
 * Dynamic inspector (spec §9): general properties for any object, plus
 * type-specific fields, notes (spec §14) and the full change history
 * (spec §41).
 */
import { computed, ref, watch } from 'vue'

import { provenanceLabel } from '@/map/MapEngine'
import { haversine } from '@/map/geo'
import { describeError, mapObjects, updateTyped } from '@/api/client'
import { useMapStore, typeName } from '@/stores/map'
import { useSystemStore } from '@/stores/system'
import { useFlightsStore } from '@/stores/flights'
import { useExpedientesStore } from '@/stores/expedientes'
import { formatDistance } from '@/map/geo'

const mapStore = useMapStore()
const systemStore = useSystemStore()
const flightsStore = useFlightsStore()
const expedientesStore = useExpedientesStore()

const object = computed(() => mapStore.selected)
const locked = computed(() => object.value?.locked === true)

// ─── The aircraft that was clicked ────────────────────────────────────────────
//
// Clicking an aeroplane on the map has always set `selectedIcao24`; nothing
// displayed it, so the panel went on saying "select an object" while the operator
// had just picked a flight. Everything below exists to put that selection on
// screen.
//
// Live state is preferred over the cached trajectory, because the marker the
// operator clicked *is* the live position and showing the older one next to it
// would put two different positions in the same panel.
const aircraft = computed(() => {
  const icao = flightsStore.selectedIcao24
  if (!icao) return null
  const key = String(icao).trim().toLowerCase()
  return flightsStore.liveStates?.[key] || flightsStore.liveStates?.[icao] || null
})

/**
 * Whether the position is live rather than remembered.
 *
 * `position_age_s` is how old the state is. Under a minute is a position the
 * operator is watching arrive; anything older is a last-known fix, and the panel
 * says so instead of implying the aeroplane is still there.
 */
const aircraftIsLive = computed(
  () => aircraft.value?.position_age_s != null && aircraft.value.position_age_s < 60,
)

const trajectory = computed(() => {
  const icao = flightsStore.selectedIcao24
  if (!icao) return null
  return flightsStore.trackFor(icao)
})

const trajectoryPoints = computed(() => trajectory.value?.points?.length ?? 0)

const trajectoryProvenance = computed(() => {
  const points = trajectory.value?.points || []
  const counts = {}
  points.forEach((p) => {
    const key = p.provenance || 'other'
    counts[key] = (counts[key] || 0) + 1
  })
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([key, n]) => `${provenanceLabel(key)} ${n}`)
    .join(' · ') || '—'
})

const trajectoryLength = computed(() => {
  const points = trajectory.value?.points || []
  let total = 0
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1]
    const b = points[i]
    if (a.latitude == null || b.latitude == null) continue
    total += haversine(a.latitude, a.longitude, b.latitude, b.longitude)
  }
  return points.length > 1 ? formatDistance(total) : '—'
})

const distances = computed(() => flightsStore.aircraftDistances || [])

const distancesRadius = computed(
  () => distances.value[0]?.radius_nm ?? distances.value[0]?.radii_nm ?? 50,
)

/**
 * What is observed and what is not, said plainly.
 *
 * The project's rule from the start: never imply that an aircraft caused an RF
 * event. The counts are per source so the operator can see that the historical
 * part came from OpenSky and the AeroRF part from this application's own
 * recordings, which are not the same kind of evidence.
 */
const provenanceNotes = computed(() => {
  const points = trajectory.value?.points || []
  if (!points.length) return []
  const counts = {}
  points.forEach((p) => {
    const key = p.provenance || 'other'
    counts[key] = (counts[key] || 0) + 1
  })
  const notes = []
  if (counts.historical) {
    notes.push({
      text:
        `${counts.historical} puntos históricos de OpenSky: son los reportes de la ` +
        'fuente, no mediciones propias.',
    })
  }
  if (counts.aerorf) {
    notes.push({
      text: `${counts.aerorf} puntos grabados por AeroRF en esta estación.`,
    })
  }
  if (counts.live) {
    notes.push({ text: `${counts.live} puntos en vivo de la posición actual.` })
  }
  return notes
})

function fmtAge(seconds) {
  const s = Number(seconds)
  if (!Number.isFinite(s)) return '—'
  if (s < 60) return `${Math.round(s)} s`
  if (s < 3600) return `${Math.round(s / 60)} min`
  if (s < 86400) return `${Math.round(s / 3600)} h`
  return `${Math.round(s / 86400)} d`
}

function fmtTime(unixSeconds) {
  const n = Number(unixSeconds)
  if (!Number.isFinite(n)) return '—'
  return new Date(n * 1000).toLocaleTimeString('es-AR')
}

/** Close whichever thing is being inspected, not just an object. */
function closeInspection() {
  mapStore.clearSelection()
  flightsStore.selectedIcao24 = null
}

/** Send the operator to the aircraft in the flights panel. */
function openFlights() {
  systemStore.setPanel('flights')
}

/** Centre the map on an RF object listed as near this aircraft. */
function centerOn(row) {
  if (row.latitude == null) return
  mapStore.engine?.setView(row.latitude, row.longitude, Math.max(mapStore.engine.getZoom(), 11))
}

const notes = ref([])
const history = ref([])
const noteDraft = ref('')
const showAllHistory = ref(false)
const openTypeEditor = ref(false)
const typeDraft = ref({})

const units = ['nm', 'km', 'm']
const states = computed(() => mapStore.vocabulary.states || [])

const isPoint = computed(() => object.value?.geometry_type === 'Point')
const hasRadius = computed(() => object.value?.radius != null)
const hasGeometry = computed(
  () => isPoint.value || hasRadius.value || !!object.value?.radial ||
    object.value?.metrics?.total_length_nm != null,
)

// Draft mirrors
const nameDraft = ref('')
const descriptionDraft = ref('')
const statusDraft = ref('')
const latDraft = ref(null)
const lonDraft = ref(null)
const radiusDraft = ref(null)
const radiusUnitDraft = ref('nm')
const azimuthDraft = ref(null)
const lengthDraft = ref(null)
const lengthUnitDraft = ref('nm')

watch(
  object,
  (obj) => {
    notes.value = []
    history.value = []
    showAllHistory.value = false
    openTypeEditor.value = false
    if (!obj) return

    nameDraft.value = obj.name || ''
    descriptionDraft.value = obj.description || ''
    statusDraft.value = obj.status
    latDraft.value = obj.latitude
    lonDraft.value = obj.longitude
    radiusDraft.value = obj.radius
    radiusUnitDraft.value = obj.radius_unit || 'nm'
    azimuthDraft.value = obj.azimuth
    lengthDraft.value = obj.length_value
    lengthUnitDraft.value = obj.length_unit || 'nm'
    typeDraft.value = {}

    mapStore.loadNotes(obj.id).then((rows) => {
      notes.value = rows
    })
    mapStore.loadHistory(obj.id).then((rows) => {
      history.value = rows
    })
  },
  { immediate: true },
)

const visibleHistory = computed(() =>
  showAllHistory.value ? history.value : history.value.slice(0, 12),
)

// ── Derived measurements ────────────────────────────────────────────────────
const radiusKm = computed(() => {
  const value = Number(radiusDraft.value) || 0
  const unit = radiusUnitDraft.value
  if (unit === 'km') return value.toFixed(2)
  if (unit === 'm') return (value / 1000).toFixed(2)
  return (value * 1.852).toFixed(2)
})
const radiusValue = computed(() => (Number(radiusDraft.value) || 0).toFixed(2))

const distanceFromCursor = computed(() => {
  const obj = object.value
  const { lat, lon } = mapStore.cursor
  if (!obj || lat === null || obj.latitude == null) return null
  const metres = haversine(lat, lon, obj.latitude, obj.longitude)
  return {
    m: metres.toFixed(0),
    km: (metres / 1000).toFixed(3),
    nm: (metres / 1852).toFixed(3),
  }
})

// ── Type-specific payload ───────────────────────────────────────────────────
const typePayload = computed(() => {
  const obj = object.value
  if (!obj) return null
  const p = obj.properties || {}

  if (p.rf) {
    return {
      title: 'Atributos RF',
      editable: true,
      endpoint: 'rf/sources',
      rows: [
        { key: 'kind', label: 'Tipo', value: p.rf.kind },
        { key: 'frequency_mhz', label: 'Frecuencia', value: fmt(p.rf.frequency_mhz, ' MHz') },
        { key: 'power_dbm', label: 'Nivel', value: fmt(p.rf.power_dbm, ' dBm') },
        { key: 'power_w', label: 'Potencia', value: fmt(p.rf.power_w, ' W') },
        { key: 'bandwidth_khz', label: 'Ancho de banda', value: fmt(p.rf.bandwidth_khz, ' kHz') },
        { key: 'height_m', label: 'Altura', value: fmt(p.rf.height_m, ' m') },
        { key: 'provenance', label: 'Procedencia', value: provenanceLabel(p.rf.provenance) },
      ],
      fields: [
        { key: 'kind', label: 'Tipo', options: mapStore.vocabulary.rf_source_kinds },
        { key: 'frequency_mhz', label: 'Frecuencia (MHz)', type: 'number', step: '0.001' },
        { key: 'power_dbm', label: 'Nivel (dBm)', type: 'number', step: '0.1' },
        { key: 'power_w', label: 'Potencia (W)', type: 'number', step: '0.01' },
        { key: 'bandwidth_khz', label: 'Ancho de banda (kHz)', type: 'number', step: '0.1' },
        { key: 'height_m', label: 'Altura (m)', type: 'number', step: '0.1' },
        { key: 'observations', label: 'Observaciones' },
      ],
    }
  }

  if (p.antenna) {
    return {
      title: 'Atributos de antena',
      editable: true,
      endpoint: 'antennas',
      rows: [
        { key: 'kind', label: 'Tipo', value: p.antenna.kind },
        { key: 'frequency_mhz', label: 'Frecuencia', value: fmt(p.antenna.frequency_mhz, ' MHz') },
        { key: 'gain_dbi', label: 'Ganancia', value: fmt(p.antenna.gain_dbi, ' dBi') },
        { key: 'height_m', label: 'Altura', value: fmt(p.antenna.height_m, ' m') },
        { key: 'azimuth_deg', label: 'Azimut', value: fmt(p.antenna.azimuth_deg, '°') },
        { key: 'sector_deg', label: 'Sector', value: fmt(p.antenna.sector_deg, '°') },
        { key: 'tilt_deg', label: 'Inclinación', value: fmt(p.antenna.tilt_deg, '°') },
        { key: 'polarization', label: 'Polarización', value: p.antenna.polarization },
        { key: 'power_w', label: 'Potencia', value: fmt(p.antenna.power_w, ' W') },
      ],
      fields: [
        { key: 'kind', label: 'Tipo', options: mapStore.vocabulary.antenna_kinds },
        { key: 'frequency_mhz', label: 'Frecuencia (MHz)', type: 'number', step: '0.001' },
        { key: 'height_m', label: 'Altura (m)', type: 'number', step: '0.1' },
        { key: 'gain_dbi', label: 'Ganancia (dBi)', type: 'number', step: '0.1' },
        { key: 'power_w', label: 'Potencia (W)', type: 'number', step: '0.01' },
        { key: 'azimuth_deg', label: 'Azimut (°)', type: 'number', step: '1' },
        { key: 'sector_deg', label: 'Sector (°)', type: 'number', step: '1' },
        { key: 'tilt_deg', label: 'Inclinación (°)', type: 'number', step: '1' },
        { key: 'polarization', label: 'Polarización', options: mapStore.vocabulary.polarizations },
      ],
    }
  }

  if (p.reference) {
    return {
      title: 'Atributos de referencia',
      editable: true,
      endpoint: 'references',
      rows: [
        { key: 'code', label: 'Código', value: p.reference.code },
        { key: 'kind', label: 'Tipo', value: p.reference.kind },
        {
          key: 'radius',
          label: 'Radio',
          value: p.reference.radius != null
            ? `${p.reference.radius} ${p.reference.radius_unit}`
            : null,
        },
      ],
      fields: [
        { key: 'code', label: 'Código' },
        { key: 'kind', label: 'Tipo' },
        { key: 'radius', label: 'Radio', type: 'number', step: '0.5' },
        { key: 'radius_unit', label: 'Unidad', options: units },
      ],
    }
  }

  if (obj.type === 'rf_event') {
    return {
      title: 'Atributos del evento',
      editable: true,
      endpoint: 'rf/events',
      rows: [
        // El payload viaja anidado en `properties.event`, igual que `rf`,
        // `antenna` y `reference` (F2-03): antes se leía en plano y estaba
        // siempre vacío porque el backend no lo serializaba.
        { key: 'frequency_mhz', label: 'Frecuencia', value: fmt(p.event?.frequency_mhz, ' MHz') },
        { key: 'level_dbm', label: 'Nivel', value: fmt(p.event?.level_dbm, ' dBm') },
        { key: 'classification', label: 'Clasificación', value: p.event?.classification },
      ],
      fields: [
        { key: 'frequency_mhz', label: 'Frecuencia (MHz)', type: 'number', step: '0.001' },
        { key: 'level_dbm', label: 'Nivel (dBm)', type: 'number', step: '0.1' },
        { key: 'bandwidth_khz', label: 'Ancho de banda (kHz)', type: 'number', step: '0.1' },
        {
          key: 'classification',
          label: 'Clasificación',
          options: mapStore.vocabulary.rf_event_classifications,
        },
        { key: 'observations', label: 'Observaciones' },
      ],
    }
  }

  if (p.measurement) {
    return {
      title: 'Detalle de la medición',
      editable: false,
      rows: [
        { key: 'mode', label: 'Modo', value: p.measurement.mode },
        { key: 'total_km', label: 'Total', value: fmt(p.measurement.total_km, ' km') },
        { key: 'total_nm', label: 'Total', value: fmt(p.measurement.total_nm, ' NM') },
        { key: 'segments', label: 'Tramos', value: (p.measurement.segments || []).length },
      ],
    }
  }

  return null
})

// ── Actions ─────────────────────────────────────────────────────────────────
function saveField(field, value) {
  mapStore.updateObject(object.value.id, { [field]: value })
}

async function saveStatus() {
  await mapStore.setStatus(object.value.id, statusDraft.value, `Cambiado desde el Inspector`)
  reloadHistory()
}

function savePosition() {
  if (!locked.value) mapStore.moveObject(object.value.id, latDraft.value, lonDraft.value)
}

function saveRadius() {
  mapStore.updateObject(object.value.id, {
    radius: radiusDraft.value,
    radius_unit: radiusUnitDraft.value,
  })
}

function saveRadial() {
  mapStore.updateObject(object.value.id, {
    azimuth: azimuthDraft.value,
    length_value: lengthDraft.value,
    length_unit: lengthUnitDraft.value,
  })
}

async function saveTypePayload() {
  if (!typePayload.value) return
  try {
    await updateTyped(object.value.type, object.value.id, { ...typeDraft.value })
    const fresh = await mapObjects.get(object.value.id)
    mapStore.upsert(fresh)
    mapStore.notice = 'Atributos actualizados'
    openTypeEditor.value = false
    reloadHistory()
  } catch (e) {
    mapStore.error = describeError(e)
  }
}

async function addNote() {
  const text = noteDraft.value.trim()
  if (!text) return
  const ok = await mapStore.addNote(object.value.id, text)
  if (ok) {
    noteDraft.value = ''
    notes.value = await mapStore.loadNotes(object.value.id)
  }
}

function reloadHistory() {
  mapStore.loadHistory(object.value.id).then((rows) => {
    history.value = rows
  })
}

function toggleVisibility() {
  mapStore.updateObject(object.value.id, { visible: !object.value.visible })
}

function toggleLock() {
  mapStore.updateObject(object.value.id, { locked: !object.value.locked })
}

async function copyCoords() {
  const text = `${object.value.latitude.toFixed(6)}, ${object.value.longitude.toFixed(6)}`
  try {
    await navigator.clipboard.writeText(text)
    mapStore.notice = `Coordenadas copiadas: ${text}`
  } catch {
    systemStore.notify('No se pudo copiar. Coordenadas: ' + text, { kind: 'warn', ms: 6000 })
  }
}

function measureFromCursor() {
  const { lat, lon } = mapStore.cursor
  if (lat === null) return
  const p = object.value
  const metres = haversine(lat, lon, p.latitude, p.longitude)
  mapStore.notice = `Distancia al cursor: ${(metres / 1000).toFixed(3)} km / ${(metres / 1852).toFixed(3)} NM`
}

async function linkExpediente() {
  if (!expedientesStore.expedientes.length) {
    await expedientesStore.fetchExpedientes()
  }
  const list = expedientesStore.expedientes
  if (!list.length) {
    mapStore.notice = 'Cree primero un expediente en el panel Expediente.'
    return
  }
  const first = list[0]
  await mapStore.updateObject(object.value.id, { expediente_id: first.id })
  mapStore.notice = `Asociado a ${first.numero_expediente}`
}

async function remove() {
  const obj = object.value
  if (!obj) return
  const ok = await systemStore.ask({
    title: 'Eliminar objeto',
    message: `¿Eliminar «${obj.name || typeName(obj.type)}»? Esta acción no se puede deshacer.`,
    confirmLabel: 'Eliminar',
    danger: true,
  })
  if (ok) mapStore.deleteObject(obj.id, true)
}

// ── Formatting ──────────────────────────────────────────────────────────────
function fmt(value, suffix = '') {
  return value === null || value === undefined ? null : `${value}${suffix}`
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString('es-AR', {
    year: '2-digit', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}
</script>
