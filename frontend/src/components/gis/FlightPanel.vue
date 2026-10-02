<template>
  <div class="flex h-full flex-col">
    <div class="flex flex-none items-center justify-between border-b border-slate-800 px-3 py-2">
      <h3 class="text-xs font-semibold uppercase tracking-widest text-slate-300">Vuelos</h3>
      <span class="font-mono text-[10px] text-slate-500">
        {{ flightsStore.trackedCount }}/{{ MAX_TRACKED }}
      </span>
    </div>

    <div class="flex-1 overflow-y-auto p-2 space-y-3">
      <!-- OpenSky not configured (honest degradation, spec §18) -->
      <div
        v-if="!flightsStore.openskyConfigured"
        class="rounded-lg border border-sky-800 bg-sky-950/30 p-2.5 text-[11px] text-sky-200"
      >
        <p class="mb-1 font-semibold">
          Modo anónimo de OpenSky
        </p>
        <p class="mb-1.5 leading-snug text-sky-300/80">
          El tráfico en vivo funciona sin cuenta: 400 créditos diarios por IP,
          resolución de 10 s y solo los vectores más recientes.
        </p>
        <p class="leading-snug text-sky-300/80">
          El <b>historial de vuelos</b> (trayectorias, búsquedas, fechas)
          sí requiere credenciales OAuth2 en el <code>.env</code> del backend.
        </p>
      </div>

      <!-- Search (spec §20) -->
      <section class="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5">
        <h4 class="mb-1.5 text-[10px] uppercase tracking-widest text-slate-500">Buscar vuelo</h4>
        <input
          v-model="flightsStore.query.callsign"
          placeholder="Callsign (p. ej. ARG1234)"
          class="mb-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] uppercase text-slate-100"
          @keyup.enter="doSearch()"
        />
        <div class="mb-1.5 grid grid-cols-2 gap-1">
          <input
            v-model="flightsStore.query.icao24"
            placeholder="ICAO24"
            class="rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-[11px] lowercase text-slate-100"
            @keyup.enter="doSearch()"
          />
          <input
            v-model="flightsStore.query.date"
            type="date"
            class="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-[10px] text-slate-100"
          />
        </div>
        <div class="grid grid-cols-2 gap-1">
          <button
            class="gis-mini-btn !py-1.5"
            :disabled="flightsStore.loading"
            @click="doSearch()"
          >
            {{ searchButtonLabel }}
          </button>
          <button class="gis-mini-btn !py-1.5" @click="flightsStore.clearSearch()">Limpiar</button>
        </div>

        <!-- Search result summary -->
        <div v-if="flightsStore.searchResult" class="mt-2 rounded bg-slate-950/60 p-2 text-[10px]">
          <div class="mb-1 flex justify-between">
            <span class="text-slate-500">ICAO24</span>
            <span class="font-mono text-slate-200">{{ flightsStore.searchResult.icao24 || '—' }}</span>
          </div>
          <div class="mb-1 flex justify-between">
            <span class="text-slate-500">Identificado por</span>
            <span class="text-slate-300">
              {{ comoSeIdentifico(flightsStore.searchResult.resolved_via) }}
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-slate-500">Vuelos históricos</span>
            <span class="font-mono text-slate-200">
              {{ flightsStore.searchResult.flights?.length || 0 }}
            </span>
          </div>
          <ul
            v-if="flightsStore.searchResult.flights?.length"
            class="mt-1.5 max-h-28 space-y-0.5 overflow-y-auto"
          >
            <li
              v-for="(f, i) in flightsStore.searchResult.flights"
              :key="i"
              class="rounded bg-slate-900 px-1.5 py-1"
            >
              <div class="font-mono text-slate-200">{{ f.callsign || f.icao24 }}</div>
              <div class="text-slate-500">
                {{ f.departure || '—' }} → {{ f.arrival || '—' }}
              </div>
              <button
                class="mt-0.5 text-[9px] text-blue-400 hover:text-blue-300"
                @click="loadTrackFor(f.icao24, f.first_seen_ts)"
              >
                ver trayectoria
              </button>
            </li>
          </ul>
        </div>

        <ul
          v-if="flightsStore.searchResult?.warnings?.length"
          class="mt-1.5 space-y-1 text-[9px] text-amber-300/90"
        >
          <li v-for="(w, i) in flightsStore.searchResult.warnings" :key="i">{{ w }}</li>
        </ul>
      </section>

      <!-- Watchlist (spec §25, §26) -->
      <section>
        <div class="mb-1.5 flex items-center justify-between">
          <h4 class="text-[10px] uppercase tracking-widest text-slate-500">
            Seguimiento ({{ flightsStore.trackedCount }}/{{ MAX_TRACKED }})
          </h4>
          <button
            v-if="flightsStore.trackedCount"
            class="gis-mini-btn"
            title="Quitar todas del seguimiento"
            @click="untrackAll"
          >
            Quitar todas
          </button>
        </div>

        <p v-if="!flightsStore.watchlist.length" class="rounded-lg border border-dashed border-slate-800 p-2 text-center text-[11px] text-slate-500">
          Sin aeronaves en seguimiento. Busque un vuelo y use «Seguir».
        </p>

        <ul class="space-y-1.5">
          <li
            v-for="(slot, index) in flightsStore.watchlistWithState"
            :key="slot.icao24"
            class="rounded-lg border bg-slate-900/60 p-2"
            :style="{ borderLeftColor: slot.color, borderLeftWidth: '3px' }"
          >
            <!-- Header: slot, callsign, controls -->
            <div class="mb-1 flex items-center gap-1.5">
              <span
                class="flex h-4 w-4 flex-none items-center justify-center rounded-full text-[9px] font-bold text-slate-900"
                :style="{ background: slot.color }"
              >
                {{ index + 1 }}
              </span>
              <button
                class="min-w-0 flex-1 truncate text-left font-mono text-[12px] font-semibold"
                :class="slot.selected ? 'text-emerald-300' : 'text-slate-200'"
                :title="slot.icao24"
                @click="selectAircraft(slot)"
              >
                {{ slot.callsign || slot.icao24 }}
              </button>
              <span
                class="flex-none text-[9px]"
                :title="slot.isRecording ? 'Grabando' : 'Sin grabación'"
              >
                {{ slot.isRecording ? '🔴' : '⚪' }}
              </span>
              <button class="flex-none text-[10px] text-slate-500 hover:text-slate-300" @click="untrack(slot.icao24)">✕</button>
            </div>

            <!-- Live telemetry (spec §26) -->
            <dl class="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px]">
              <div class="flex justify-between">
                <dt class="text-slate-500">Estado</dt>
                <dd class="text-slate-300">{{ aircraftState(slot) }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-slate-500">Altitud</dt>
                <dd class="font-mono text-slate-300">{{ withUnit(slot.state?.altitude, 'm') }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-slate-500">Velocidad</dt>
                <dd class="font-mono text-slate-300">{{ withUnit(slot.state?.velocity, 'm/s') }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-slate-500">Heading</dt>
                <dd class="font-mono text-slate-300">{{ withUnit(slot.state?.heading, '°') }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-slate-500">Posición</dt>
                <dd class="font-mono text-slate-300">
                  <template v-if="slot.state?.latitude != null">
                    {{ slot.state.latitude.toFixed(4) }}, {{ slot.state.longitude.toFixed(4) }}
                  </template>
                  <template v-else>dato no disponible</template>
                </dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-slate-500">Actualizado</dt>
                <dd class="font-mono" :class="stalenessClass(slot)">
                  {{ relativeTime(slot.state?.time_position) }}
                </dd>
              </div>
            </dl>

            <!-- A position can be far older than the last message: a real
                 OpenSky capture on 2026-09-25 held positions 1.5 h old on
                 aircraft still transmitting. Presenting those as "live"
                 would be a lie, so they are called out. -->
            <p
              v-if="stalenessWarning(slot)"
              class="mt-1 rounded bg-amber-950/40 px-1.5 py-0.5 text-[9px] leading-snug text-amber-300"
            >
              ⚠ {{ stalenessWarning(slot) }}
            </p>

            <!-- Track availability (spec §21) -->
            <div class="mt-1 text-[9px] text-slate-500">
              Trayectoria:
              <span v-if="slotTrack(slot)" class="text-slate-300">
                {{ slotTrack(slot).point_count }} puntos ·
                {{ slotTrack(slot).source }}
              </span>
              <span v-else>no cargada</span>
            </div>
            <p
              v-if="slotTrack(slot) && flightsStore.trackNote"
              class="mt-0.5 rounded bg-slate-950/60 p-1 text-[9px] leading-snug text-amber-300/80"
            >
              {{ flightsStore.trackNote }}
            </p>

            <!-- Buttons (spec §26) -->
            <div class="mt-1.5 flex flex-wrap gap-1">
              <button class="gis-mini-btn" :class="{ '!bg-blue-600 !text-white': slot.show_marker }" @click="toggleMarker(slot)">
                {{ slot.show_marker ? '👁 Avión' : '🚫 Avión' }}
              </button>
              <button class="gis-mini-btn" :class="{ '!bg-blue-600 !text-white': slot.show_track }" @click="toggleTrack(slot)">
                {{ slot.show_track ? '∿ Trayectoria' : '∿ Sin tray.' }}
              </button>
              <button class="gis-mini-btn" @click="centerOn(slot)">⊙ Centrar</button>
              <button
                class="gis-mini-btn"
                :class="{ '!bg-rose-600 !text-white !border-rose-500': slot.isRecording }"
                @click="toggleRecording(slot)"
              >
                {{ slot.isRecording ? '⏹ Detener' : '⏺ Grabar' }}
              </button>
              <button
                class="gis-mini-btn"
                :disabled="flightsStore.flightsLoading === slot.icao24"
                @click="toggleFlightList(slot)"
              >
                {{ flightsStore.flightsLoading === slot.icao24 ? '… Buscando' : '☰ Vuelos' }}
              </button>
            </div>

            <!-- Choosing the flight, for reports that name an aircraft which
                 has already landed. -->
            <div
              v-if="flightsStore.flightListFor === slot.icao24"
              class="mt-1.5 rounded border border-slate-700 bg-slate-950/70 p-1.5"
            >
              <p class="mb-1 text-[9px] text-slate-400">
                {{ flightsStore.flightListMessage || 'Vuelos de esta aeronave:' }}
              </p>
              <ul
                v-if="flightsStore.flightsFor(slot.icao24).length"
                class="max-h-44 space-y-0.5 overflow-y-auto"
              >
                <li v-for="(f, i) in flightsStore.flightsFor(slot.icao24)" :key="`${f.start_time}-${i}`">
                  <button
                    class="gis-mini-btn w-full justify-start text-left"
                    :class="{ '!bg-blue-600 !text-white': isLoadedSlot(slot, f) }"
                    :disabled="Boolean(flightsStore.trackLoading)"
                    @click="loadTrackFor(slot.icao24, f.track_time)"
                  >
                    <span class="font-mono">{{ flightWhen(f.start_time) }}</span>
                    <span class="truncate">{{ flightRoute(f) }}</span>
                    <span class="ml-auto flex-none text-[9px] opacity-70">{{ flightDur(f) }}</span>
                  </button>
                </li>
              </ul>
              <p v-else class="text-[9px] text-slate-500">
                No hay vuelos registrados para esta aeronave en el período consultado.
              </p>
              <label class="mt-1.5 flex items-center gap-1 text-[9px] text-slate-500">
                <span class="flex-none">Buscar</span>
                <input
                  v-model.number="historyDays"
                  type="number"
                  min="1"
                  max="30"
                  class="w-14 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[9px] text-slate-200"
                  @keyup.enter="reloadFlightList(slot)"
                />
                <span>días atrás</span>
                <button class="gis-mini-btn ml-auto" @click="reloadFlightList(slot)">↻</button>
              </label>
              <p v-if="flightsStore.flightListNote" class="mt-1 text-[9px] leading-snug text-amber-300/80">
                {{ flightsStore.flightListNote }}
              </p>
            </div>

            <!-- When the answer covers a different flight than the one asked
                 for, the points are real but they are the wrong route. Saying
                 so is the only thing that keeps them from being compared as
                 if they were the right ones. -->
            <p
              v-if="slotTrackMismatch(slot)"
              class="mt-1 rounded bg-amber-950/50 px-1.5 py-1 text-[9px] leading-snug text-amber-200"
            >
              ⚠ La trayectoria devuelta corresponde a otro vuelo
              ({{ flightWhen(slotTrack(slot).covered_window?.start) }}), no al
              seleccionado. Elegí el vuelo correcto en “Vuelos”.
            </p>
          </li>
        </ul>
      </section>

      <!-- Distances aircraft → references (spec §30) -->
      <section
        v-if="flightsStore.aircraftDistances.length"
        class="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5"
      >
        <h4 class="mb-1.5 text-[10px] uppercase tracking-widest text-slate-500">
          Distancia a referencias
        </h4>
        <ul class="max-h-48 space-y-1 overflow-y-auto">
          <li
            v-for="row in flightsStore.aircraftDistances"
            :key="row.object_id"
            class="flex items-center justify-between gap-2 text-[10px]"
          >
            <span class="min-w-0 flex-1 truncate text-slate-300">
              {{ row.name || typeName(row.type) }}
            </span>
            <span class="flex-none font-mono text-cyan-300">
              {{ row.distance_nm?.toFixed(2) }} NM
              <span class="text-slate-500">/ {{ row.distance_km?.toFixed(2) }} km</span>
            </span>
            <span class="flex-none font-mono text-slate-600">{{ row.bearing }}°</span>
          </li>
        </ul>
        <p class="mt-1.5 rounded bg-amber-950/30 p-1.5 text-[9px] leading-snug text-amber-200/90">
          {{ flightsStore.correlationDisclaimer }}
        </p>
      </section>

      <!-- Recording sessions (spec §24) -->
      <section class="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5">
        <div class="mb-1.5 flex items-center justify-between">
          <h4 class="text-[10px] uppercase tracking-widest text-slate-500">Sesiones de grabación</h4>
          <button class="gis-mini-btn" @click="systemStore.showTimeline = !systemStore.showTimeline">
            Timeline
          </button>
        </div>
        <p v-if="!flightsStore.sessions.length" class="text-[10px] text-slate-500">
          Sin sesiones. Use «Grabar» sobre una aeronave seguida.
        </p>
        <ul class="max-h-40 space-y-1 overflow-y-auto">
          <li
            v-for="session in flightsStore.sessions"
            :key="session.id"
            class="rounded bg-slate-950/60 p-1.5 text-[10px]"
          >
            <div class="flex items-center justify-between">
              <span class="font-mono text-slate-200">{{ session.callsign || session.icao24 }}</span>
              <span
                class="rounded px-1 text-[9px]"
                :class="session.status === 'recording' ? 'bg-rose-900 text-rose-200' : 'bg-slate-800 text-slate-400'"
              >
                {{ session.status }}
              </span>
            </div>
            <div class="mt-0.5 flex justify-between text-slate-500">
              <span>{{ session.sample_count }} muestras</span>
              <span>{{ formatDate(session.started_at) }}</span>
            </div>
            <div class="mt-0.5 flex gap-1">
              <button class="gis-mini-btn" @click="flightsStore.loadSessionForReplay(session.id)">▶ Reproducir</button>
              <button
                v-if="session.status === 'recording'"
                class="gis-mini-btn"
                @click="flightsStore.stopRecording(session.icao24)"
              >
                ⏹
              </button>
            </div>
          </li>
        </ul>
      </section>

      <!-- Live feed status -->
      <section class="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 text-[10px]">
        <div class="flex justify-between">
          <span class="text-slate-500">WebSocket</span>
          <span class="text-slate-300">{{ flightsStore.socketState }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-500">Aeronaves en vivo</span>
          <span class="font-mono text-slate-300">{{ Object.keys(flightsStore.liveStates).length }}</span>
        </div>
        <p class="mt-1 text-[9px] leading-snug text-slate-600">
          El backend envía únicamente cambios. Una aeronave detenida no genera tráfico.
        </p>
      </section>
    </div>
  </div>
</template>

<script setup>
/**
 * components/gis/FlightPanel.vue
 * ─────────────────────────────
 * Search, the five-aircraft watchlist (spec §25), per-aircraft telemetry
 * and controls (spec §26), recording (spec §24) and distances to
 * references (spec §30).
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { MAX_TRACKED, useFlightsStore } from '@/stores/flights'
import { useMapStore, typeName } from '@/stores/map'
import { useSystemStore } from '@/stores/system'

const flightsStore = useFlightsStore()
const mapStore = useMapStore()
const systemStore = useSystemStore()

  /**
   * Cómo se identificó la aeronave, en el idioma del operador.
   *
   * El backend devuelve una etiqueta de procedencia —de dónde salió la dirección
   * de aeronave— y esa etiqueta es lo más importante de esta fila: «la vi
   * transmitiendo ahora» y «la tengo guardada de un vuelo anterior» son dos
   * clases de evidencia distinta, y el operador tiene que poder distinguirlas de
   * un vistazo.
   *
   * Se traduce porque se mostraba crudo, y `callsign_live_state` no le dice nada
   * a quien opera. La clave es el contrato con el backend: si aparece una
   * procedencia nueva y no está en el mapa, se ve la clave en vez de quedarse en
   * blanco, que es peor que una etiqueta rara.
   */
  const ORIGEN_DE_LA_IDENTIFICACION = {
    icao24_direct: 'la dirección que usted escribió',
    callsign_live_state: 'vectores en vivo de OpenSky',
    callsign_archivo_aerorf: 'archivo de vuelos de AeroRF',
  }
  const comoSeIdentifico = (origen) => {
    if (!origen) return 'sin coincidencia'
    return ORIGEN_DE_LA_IDENTIFICACION[origen] || `origen desconocido (${origen})`
  }

let timer = null

onMounted(() => {
  timer = setInterval(() => {
    if (flightsStore.watchlist.length) flightsStore.loadWatchlist()
  }, 30000)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  stopLiveTrack()
})

const searchButtonLabel = computed(() =>
  flightsStore.loading ? 'Buscando…' : 'Buscar',
)
async function doSearch() {
  const result = await flightsStore.search()
  if (!result?.icao24) return
  const follow = await systemStore.ask({
    title: 'Seguir aeronave',
    message:
      `¿Seguir ${result.callsign || result.icao24}?\n\n` +
      `Seguir agrega la aeronave a la lista de seguimiento (máximo ${MAX_TRACKED}).`,
    confirmLabel: 'Seguir',
  })
  if (follow) flightsStore.trackAircraft(result.icao24, result.callsign)
}

async function untrack(icao24) {
  await flightsStore.untrackAircraft(icao24)
  mapStore.renderAll()
}

async function untrackAll() {
  const codes = [...flightsStore.watchlist.map((s) => s.icao24)]
  for (const code of codes) {
    await flightsStore.untrackAircraft(code)
  }
}

function selectAircraft(slot) {
  flightsStore.selectedIcao24 = slot.icao24
  flightsStore.patchTracked(slot.icao24, { selected: true })
  flightsStore.loadAircraftDistances(slot.icao24)
  if (slot.state?.latitude != null) {
    mapStore.engine?.setView(slot.state.latitude, slot.state.longitude, 12)
  }
}

function centerOn(slot) {
  const st = slot.state
  if (st?.latitude != null) mapStore.engine?.setView(st.latitude, st.longitude, 12)
  else flightsStore.notice = 'Sin posición conocida para esa aeronave.'
}

async function toggleMarker(slot) {
  await flightsStore.patchTracked(slot.icao24, { show_track: slot.show_track, show_marker: !slot.show_marker })
  mapStore.renderAll()
}

/**
 * The trajectory held for one watchlist entry, or null.
 *
 * Per aircraft rather than a single shared value, so a list of five
 * aircraft reports five trajectories and the map can draw them together.
 */
function slotTrack(slot) {
  return flightsStore.trackFor(slot?.icao24)
}

/**
 * True when the trajectory on screen belongs to a different flight than the
 * one that was chosen.
 *
 * OpenSky answers a track request for an instant with the flight near it, and
 * answers one with no instant with the most recent flight. Either can be the
 * wrong flight, and the points are real when it happens — which is why this
 * cannot be left to the operator to notice.
 */
function slotTrackMismatch(slot) {
  return flightsStore.trackMismatch(slot?.icao24)
}

/** How many days back the flight list searches. */
const historyDays = ref(2)

/** Open the flight list for an aircraft, fetching it the first time. */
function toggleFlightList(slot) {
  const code = slot?.icao24
  if (!code) return
  if (flightsStore.flightListFor === code) {
    flightsStore.closeFlightList()
    return
  }
  flightsStore.loadFlightsOf(code, { days: historyDays.value })
}

/** Re-run the list with a different look-back. */
function reloadFlightList(slot) {
  if (!slot?.icao24) return
  const days = Math.min(30, Math.max(1, Number(historyDays.value) || 2))
  historyDays.value = days
  flightsStore.loadFlightsOf(slot.icao24, { days })
}

/** True when the trajectory on screen is the one for this candidate flight. */
function isLoadedSlot(slot, flight) {
  const data = slotTrack(slot)
  if (!data?.covered_window) return false
  // Within a couple of minutes counts as the same flight: OpenSky's first and
  // last contacts are not the same instants the flight list reports.
  return Math.abs(data.covered_window.start - flight.start_time) < 300
}

const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
  'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

/** A flight instant as local date and time, to the minute. */
function flightWhen(ts) {
  if (!ts) return '?'
  const d = new Date(ts * 1000)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${hh}:${mm}`
}

/** The route, or a dash when OpenSky has no airports for the flight. */
function flightRoute(flight) {
  const dep = flight.departure_airport
  const arr = flight.arrival_airport
  if (dep && arr) return `${dep} → ${arr}`
  if (dep) return `${dep} → ???`
  if (arr) return `??? → ${arr}`
  return 'ruta desconocida'
}

/** Flight duration in hours and minutes. */
function flightDur(flight) {
  if (!flight?.duration_s) return '—'
  const total = Math.round(flight.duration_s / 60)
  return `${Math.floor(total / 60)}h${String(total % 60).padStart(2, '0')}`
}

async function toggleTrack(slot) {
  const next = !slot.show_track
  await flightsStore.patchTracked(slot.icao24, { show_track: next })
  // Turning it on has to fetch the path. It used to only flip the flag, so
  // the button changed its label and the map stayed empty: the layer had
  // nothing to draw because nobody had asked for the data.
  if (next && !flightsStore.trackFor(slot.icao24)) {
    await loadTrackFor(slot.icao24, slot.first_seen_ts)
  } else {
    mapStore.renderAll()
  }
}

async function toggleRecording(slot) {
  if (slot.isRecording) {
    await flightsStore.stopRecording(slot.icao24)
  } else {
    await flightsStore.startRecording(slot.icao24, slot.callsign)
  }
}

/**
 * How often a live trajectory is re-fetched while the flight continues.
 *
 * Deliberately slow. OpenSky charges credits per request, and the track
 * endpoint returns waypoints, not a continuous position: for a typical
 * flight the median gap between waypoints is tens of seconds, so polling
 * faster than this re-reads the same data and spends credits for nothing.
 */
const TRACK_REFRESH_MS = 30000

let liveTrackTimer = null
let liveTrackIcao24 = null

/**
 * Load an aircraft's trajectory, and follow it if the flight is still going.
 *
 * A live flight is a moving target: the line drawn the instant the operator
 * asks for it is out of date a minute later. So an airborne flight starts a
 * poll that re-fetches the track and lets the path grow. It stops by itself
 * when the aircraft lands, when the operator selects a different aircraft, or
 * when the panel unmounts.
 *
 * A historical flight is not polled. Its track is immutable, and re-requesting
 * it would spend credits for data that cannot change.
 */
function loadTrackFor(icao24, time = null) {
  stopLiveTrack()

  return flightsStore.loadTrack(icao24, { time }).then((data) => {
    // Redraw first: the trajectory is already in the store, and the map
    // watcher picks it up. Only then zoom, and only if there is a path.
    mapStore.renderAll()
    if (data?.point_count) {
      const latlngs = flightsStore.trackLatLngsFor(icao24)
      if (latlngs.length) mapStore.engine?.fitBounds(latlngs)
    } else {
      flightsStore.notice =
        'Sin trayectoria disponible para ese vuelo. Los tracks de OpenSky cubren hasta 30 días.'
    }
    if (time === null && isAirborne(data)) startLiveTrack(icao24)
    return data
  })
}

/**
 * True while the aircraft reports a position and is not on the ground.
 *
 * **El feed vivo primero, y la heurística sólo si no hay nada.** Esta función
 * decide si la trayectoria en vivo sigue creciendo, así que equivocarse cuesta
 * una línea que se congela con la aeronave todavía moviéndose en el mapa: el
 * marcador viene de los vectores de estado, que llegan por WebSocket, y la línea
 * viene del sondeo. Son dos caminos independientes, y por eso una trayectoria
 * congelada con la aeronave viva es exactamente el síntoma que había.
 *
 * Antes leía `watchlist`, la lista cruda, buscando un campo `.state` que **esa
 * lista no tiene**: quien lo lleva es `watchlistWithState`, un `computed` hecho
 * para pegárselo a cada fila. Medido sobre las dos aeronaves que estaban
 * siguiendo: `state` era `undefined` en las dos, así que la rama del feed vivo no
 * se ejecutaba nunca y siempre caía a la de abajo.
 *
 * La heurística de los dos minutos es un último recurso, no la regla. La última
 * posición de un track de OpenSky y el vector de estado del mismo avión no se
 * actualizan a la vez: el track es un producto distinto, más lento, y se queda
 * viejo antes de que la aeronave deje de volar. Cuando la heurística se usaba
 * como respuesta principal, bastaba un hueco de datos de un minuto y dos para
 * matar el sondeo.
 */
function isAirborne(track) {
  const code = String(track?.icao24 || '').trim().toLowerCase()
  // `watchlistWithState` es la lista con el estado pegado; `liveStates` es el
  // almacén sin transformar. Se consulta el almacén porque no depende de que el
  // panel se haya montado y llega por el mismo camino que el marcador del mapa.
  const state = code
    ? (flightsStore.watchlistWithState.find((s) => String(s.icao24).toLowerCase() === code)?.state
       ?? flightsStore.liveStates?.[code])
    : null
  if (state) return state.on_ground === false && state.has_position !== false
  // Sin vector de estado no hay nada mejor que el final del track. Dos minutos
  // es un margen generoso a propósito: preferimos seguir dibujando de más a
  // congelar de menos, porque una línea congelada no dice por qué.
  const end = track?.end_time
  return Boolean(end) && Date.now() / 1000 - end < 120
}

function startLiveTrack(icao24) {
  stopLiveTrack()
  liveTrackIcao24 = icao24
  liveTrackTimer = setInterval(() => {
    if (flightsStore.track?.icao24 !== liveTrackIcao24) {
      stopLiveTrack()
      return
    }
    if (!isAirborne(flightsStore.track)) {
      stopLiveTrack()
      flightsStore.notice = 'Vuelo terminado: la trayectoria queda fija.'
      return
    }
    flightsStore.loadTrack(liveTrackIcao24, { fresh: true })
  }, TRACK_REFRESH_MS)
}

function stopLiveTrack() {
  if (liveTrackTimer) clearInterval(liveTrackTimer)
  liveTrackTimer = null
  liveTrackIcao24 = null
}

function aircraftState(slot) {
  const st = slot.state
  if (!st) return 'sin datos'
  if (st.on_ground) return 'en tierra'
  return 'en vuelo'
}

function withUnit(value, unit) {
  return value === null || value === undefined ? 'n/d' : `${Number(value).toFixed(0)}${unit}`
}

/**
 * How old the reported position is, in seconds.
 *
 * `time_position` is when the position was *measured*; the aircraft may
 * still be transmitting other messages long after it stopped reporting a
 * position. A real OpenSky capture (2026-09-25, 13 369 aircraft) held
 * positions up to 1.5 h old, and about 10% were over a minute old, so
 * this is a normal condition rather than an edge case.
 */
function positionAge(slot) {
  const ts = slot.state?.time_position
  if (!ts) return null
  return Math.max(0, Math.floor(Date.now() / 1000 - ts))
}

const STALE_WARNING_S = 60

function stalenessWarning(slot) {
  const age = positionAge(slot)
  if (age === null || slot.state?.latitude == null) return null
  if (age > 3600) {
    return `Posición de hace ${Math.floor(age / 3600)} h ${Math.floor((age % 3600) / 60)} min. La aeronave transmite, pero no reporta posición.`
  }
  if (age > STALE_WARNING_S) {
    return `Posición de hace ${Math.floor(age / 60)} min. Puede no ser actual.`
  }
  return null
}

function stalenessClass(slot) {
  const age = positionAge(slot)
  if (age === null) return 'text-slate-300'
  if (age > 3600) return 'text-rose-400'
  if (age > STALE_WARNING_S) return 'text-amber-400'
  return 'text-slate-300'
}

function relativeTime(ts) {
  if (!ts) return 'n/d'
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - ts))
  if (seconds < 60) return `hace ${seconds}s`
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)}min`
  return `hace ${Math.floor(seconds / 3600)}h`
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString('es-AR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}
</script>
