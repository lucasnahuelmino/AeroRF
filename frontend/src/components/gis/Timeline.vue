<template>
  <div class="gis-timeline">
    <!-- Transport controls (spec §28) -->
    <div class="flex flex-none items-center gap-1.5 border-r border-borde px-2">
      <button
        class="gis-mini-btn"
        :disabled="!hasSession"
        :title="flightsStore.replayPlaying ? 'Pausar' : 'Reproducir'"
        @click="togglePlay"
      >
        {{ flightsStore.replayPlaying ? '⏸' : '▶' }}
      </button>
      <button class="gis-mini-btn" :disabled="!hasSession" title="Rebobinar" @click="step(-1)">⏮</button>
      <button class="gis-mini-btn" :disabled="!hasSession" title="Avanzar" @click="step(1)">⏭</button>
      <button class="gis-mini-btn" :disabled="!hasSession" title="Ir al inicio" @click="seek(0)">⏹</button>
      <button
        class="gis-mini-btn"
        :title="flightsStore.replayPlaying ? 'Detener' : 'Pausar'"
        :disabled="!hasSession"
        @click="stop"
      >
        ⏹
      </button>
    </div>

    <!-- Track -->
    <div class="relative min-w-0 flex-1 px-2 py-1.5">
      <template v-if="hasSession">
        <input
          type="range"
          min="0"
          :max="Math.max(0, flightsStore.replayPoints.length - 1)"
          :value="flightsStore.replayIndex"
          class="w-full accent-blue-500"
          @input="seek(Number($event.target.value))"
        />
        <div class="mt-0.5 flex justify-between font-mono text-[9px] text-texto-tenue">
          <span>{{ startLabel }}</span>
          <span class="text-texto-tenue">
            {{ currentLabel }}
            <span v-if="flightsStore.replayPlaying" class="ml-1 text-emerald-400">▶</span>
          </span>
          <span>{{ endLabel }}</span>
        </div>
      </template>
      <p v-else class="text-center text-[10px] text-texto-tenue">
        Seleccione una sesión de grabación para reproducirla aquí.
      </p>
    </div>

    <!-- Session identity + provenance -->
    <div class="flex flex-none items-center gap-2 border-l border-borde px-2 text-[10px]">
      <template v-if="hasSession">
        <span class="font-mono text-texto-medio">
          {{ session.callsign || session.icao24 }}
        </span>
        <span class="rounded bg-panel-alto px-1.5 py-1 text-texto-tenue">
          {{ session.source || 'aerorf' }}
        </span>
        <span class="text-texto-tenue">
          {{ flightsStore.replayIndex + 1 }}/{{ flightsStore.replayPoints.length }}
        </span>
        <span class="text-texto-tenue">
          {{ pointTimeLabel }}
        </span>
      </template>
      <button class="gis-mini-btn" @click="systemStore.showTimeline = false">✕</button>
    </div>
  </div>
</template>

<script setup>
/**
 * components/gis/Timeline.vue
 * ───────────────────────────
 * Replay timeline (spec §27, §28): play, pause, step forward/back and
 * seek, driven by the *recorded timestamps* rather than by animation
 * timing, so the marker never outruns the data (spec §56).
 */
import { computed } from 'vue'

import { useFlightsStore } from '@/stores/flights'
import { useSystemStore } from '@/stores/system'
import { useMapStore } from '@/stores/map'

const flightsStore = useFlightsStore()
const systemStore = useSystemStore()
const mapStore = useMapStore()

const hasSession = computed(() => flightsStore.replayPoints.length > 0)
const session = computed(() => flightsStore.replaySession?.session || {})

const startLabel = computed(() => formatClock(flightsStore.replayTimeRange?.start?.timestamp))
const endLabel = computed(() => formatClock(flightsStore.replayTimeRange?.end?.timestamp))

const currentLabel = computed(() => {
  const point = flightsStore.replayCurrent
  if (!point) return '—'
  if (point.latitude == null) return 'dato no disponible'
  return `${point.latitude.toFixed(5)}, ${point.longitude.toFixed(5)}`
})

const pointTimeLabel = computed(() => {
  const point = flightsStore.replayCurrent
  if (!point) return ''
  if (point.altitude != null) return `${Math.round(point.altitude)} m`
  return 'alt n/d'
})

/** Jump the map to the replayed position. */
function seek(index) {
  flightsStore.seekReplay(index)
  const point = flightsStore.replayCurrent
  if (point?.latitude != null) {
    mapStore.engine?.setView(point.latitude, point.longitude, 13)
  }
}

function step(delta) {
  flightsStore.stepReplay(delta)
  seek(flightsStore.replayIndex)
}

function togglePlay() {
  if (flightsStore.replayPlaying) {
    flightsStore.pauseReplay()
  } else {
    flightsStore.playReplay()
    // Follow the marker as it moves.
    watchFollow()
  }
}

function stop() {
  flightsStore.stopReplay()
  seek(0)
}

let followTimer = null
function watchFollow() {
  clearInterval(followTimer)
  followTimer = setInterval(() => {
    const point = flightsStore.replayCurrent
    if (point?.latitude != null) {
      mapStore.engine?.setView(point.latitude, point.longitude, mapStore.engine.getZoom())
    }
  }, 200)
}

function formatClock(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toISOString().slice(11, 16)
}
</script>

<style scoped>
.gis-timeline {
  display: flex;
  align-items: center;
  height: 48px;
  flex: 0 0 48px;
  background: var(--panel);
  border-top: 1px solid var(--panel-alto);
  z-index: 1050;
}
</style>
