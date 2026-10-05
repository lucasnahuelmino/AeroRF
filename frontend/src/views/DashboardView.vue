<template>
  <div class="page-doc">
    <header class="page-doc-head">
      <h1 class="page-doc-title">Panel operativo</h1>
      <p class="page-doc-sub">
        Resumen del estado del sistema. El mapa es la herramienta principal:
        <router-link to="/" class="text-sky-400 hover:text-sky-300 underline">
          abrir el GIS
        </router-link>
      </p>
    </header>

    <!-- System status -->
    <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatCard title="Objetos en el mapa" :value="mapStore.stats?.total ?? 0" :subtitle="objectSummary" />
      <StatCard title="Expedientes" :value="stats.totalExpedientes" :subtitle="`${stats.abiertos} abiertos`" />
      <StatCard title="Fuentes / Eventos" :value="rfCounts" :subtitle="`${rfSummary?.events_total ?? 0} eventos RF`" />
      <StatCard title="Aeronaves en seguimiento" :value="flightsStore.trackedCount" :subtitle="`máximo ${5}`" />
    </div>

    <!--
      Only what the header dots cannot say. Backend, database and OpenSky are
      three coloured dots in BrandBar now; repeating them here in full cards
      was noise. What is left is the detail an operator needs and the one
      warning that actually needs a sentence: OpenSky is not configured.
    -->
    <section class="rounded-lg border border-borde bg-on-ink-wash p-4">
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-widest text-texto-medio">
        Estado del sistema
      </h2>
      <dl class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt class="text-[10px] uppercase tracking-widest text-texto-tenue">Backend</dt>
          <dd class="mt-0.5 text-sm text-texto">{{ systemStore.backendStatus }}</dd>
        </div>
        <div>
          <dt class="text-[10px] uppercase tracking-widest text-texto-tenue">Base de datos</dt>
          <dd class="mt-0.5 text-sm text-texto">
            {{ systemStore.dbConnected ? `${systemStore.dbStatus.tables.length} tablas` : 'no disponible' }}
          </dd>
        </div>
        <div>
          <dt class="text-[10px] uppercase tracking-widest text-texto-tenue">OpenSky Network</dt>
          <dd class="mt-0.5 text-sm text-texto">
            {{ flightsStore.openskyConfigured ? 'configurado' : 'sin configurar' }}
          </dd>
        </div>
        <div>
          <dt class="text-[10px] uppercase tracking-widest text-texto-tenue">Objetos por capa</dt>
          <dd class="mt-0.5 text-sm text-texto">{{ mapStore.layers.length }} capas</dd>
        </div>
      </dl>
      <p
        v-if="!flightsStore.openskyConfigured"
        class="mt-3 rounded border border-amber-800/60 bg-amber-950/30 px-3 py-2 text-[11px] leading-snug text-amber-200/90"
      >
        OpenSky no está configurado: no hay vuelos en vivo ni trayectorias.
        Defina las credenciales OAuth2 en el <code>.env</code> del backend y
        reinícielo. Sin ellas AeroRF sigue funcionando para el resto del
        trabajo.
      </p>
    </section>

    <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <!-- Object census by type -->
      <section class="rounded-lg border border-borde bg-on-ink-wash p-4">
        <h2 class="mb-3 text-sm font-semibold uppercase tracking-widest text-texto-medio">
          Objetos por tipo
        </h2>
        <DataTable
          v-if="objectRows.length"
          :columns="[
            { key: 'type', label: 'Tipo' },
            { key: 'count', label: 'Cantidad', align: 'right' },
          ]"
          :rows="objectRows"
        />
        <p v-else class="text-sm text-texto-tenue">
          Sin objetos. Cree el primero desde el mapa.
        </p>
      </section>

      <!-- Expedientes -->
      <section class="rounded-lg border border-borde bg-on-ink-wash p-4">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-widest text-texto-medio">
            Expedientes recientes
          </h2>
          <router-link to="/expedientes" class="text-xs text-blue-400 hover:text-blue-300">
            ver todos
          </router-link>
        </div>
        <DataTable
          v-if="expedienteRows.length"
          :columns="[
            { key: 'numero_expediente', label: 'Expediente' },
            { key: 'freq_mhz', label: 'MHz' },
            { key: 'aeropuerto', label: 'Aeropuerto' },
            { key: 'estado', label: 'Estado' },
          ]"
          :rows="expedienteRows"
        />
        <p v-else class="text-sm text-texto-tenue">Sin expedientes.</p>
      </section>
    </div>

    <!-- RF summary -->
    <section class="rounded-lg border border-borde bg-on-ink-wash p-4">
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-widest text-texto-medio">
        Resumen del dominio RF
      </h2>
      <div class="grid gap-3 md:grid-cols-4">
        <div class="rounded border border-borde bg-on-ink-wash p-3">
          <div class="text-[10px] uppercase tracking-wide text-texto-tenue">Fuentes</div>
          <div class="text-lg font-semibold text-orange-300">{{ rfSummary?.sources_total ?? 0 }}</div>
        </div>
        <div class="rounded border border-borde bg-on-ink-wash p-3">
          <div class="text-[10px] uppercase tracking-wide text-texto-tenue">Eventos</div>
          <div class="text-lg font-semibold text-red-300">{{ rfSummary?.events_total ?? 0 }}</div>
        </div>
        <div class="rounded border border-borde bg-on-ink-wash p-3">
          <div class="text-[10px] uppercase tracking-wide text-texto-tenue">Antenas</div>
          <div class="text-lg font-semibold text-emerald-300">{{ rfSummary?.antennas_total ?? 0 }}</div>
        </div>
        <div class="rounded border border-borde bg-on-ink-wash p-3">
          <div class="text-[10px] uppercase tracking-wide text-texto-tenue">Banda de eventos</div>
          <div class="text-sm text-texto-medio">
            <template v-if="rfSummary?.event_frequencies?.count">
              {{ rfSummary.event_frequencies.min_mhz }}–{{ rfSummary.event_frequencies.max_mhz }} MHz
            </template>
            <template v-else>n/d</template>
          </div>
        </div>
      </div>
    </section>

    <!-- Recording sessions -->
    <section v-if="flightsStore.sessions.length" class="rounded-lg border border-borde bg-on-ink-wash p-4">
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-widest text-texto-medio">
        Sesiones de grabación
      </h2>
      <DataTable
        :columns="[
          { key: 'icao24', label: 'ICAO24' },
          { key: 'callsign', label: 'Callsign' },
          { key: 'status', label: 'Estado' },
          { key: 'sample_count', label: 'Muestras', align: 'right' },
          { key: 'started_at', label: 'Inicio' },
        ]"
        :rows="flightsStore.sessions.slice(0, 10)"
      />
    </section>
  </div>
</template>

<script setup>
/**
 * views/DashboardView.vue
 * ────────────────────────
 * Operational summary.
 *
 * Rewritten during the AeroRF refactor. The previous version embedded
 * `RFMap` (a third copy of the map implementation) and listed
 * `flightsStore.routes`, which were the fabricated demo flights. Both are
 * gone by design: the map lives in the GIS shell, and flight data now
 * comes only from OpenSky.
 */
import { computed, onMounted, ref } from 'vue'

import { rf as rfApi } from '@/api/client'
import { useExpedientesStore } from '@/stores/expedientes'
import { useFlightsStore } from '@/stores/flights'
import { useMapStore, typeName } from '@/stores/map'
import { useSystemStore } from '@/stores/system'
import StatCard from '@/components/StatCard.vue'
import DataTable from '@/components/DataTable.vue'

const expedientesStore = useExpedientesStore()
const flightsStore = useFlightsStore()
const mapStore = useMapStore()
const systemStore = useSystemStore()

const rfSummary = ref(null)

const stats = computed(() => {
  const expedientes = expedientesStore.expedientes || []
  return {
    totalExpedientes: expedientes.length,
    abiertos: expedientes.filter((e) => e.estado === 'abierto').length,
  }
})

const objectRows = computed(() =>
  Object.entries(mapStore.stats?.by_type || {})
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => ({ type: typeName(type), count })),
)

const objectSummary = computed(() => {
  const s = mapStore.stats
  if (!s) return '—'
  return `${s.visible} visibles · ${s.hidden} ocultos`
})

const rfCounts = computed(
  () => (rfSummary.value?.sources_total ?? 0),
)

const expedienteRows = computed(() =>
  (expedientesStore.expedientes || []).slice(0, 10).map((e) => ({
    numero_expediente: e.numero_expediente,
    freq_mhz: e.freq_mhz,
    aeropuerto: e.aeropuerto,
    estado: e.estado,
  })),
)

onMounted(async () => {
  await Promise.all([
    systemStore.checkBackend(),
    flightsStore.probeBackend(),
    expedientesStore.fetchExpedientes(),
    mapStore.loadStats(),
    flightsStore.loadSessions(),
  ])
  try {
    rfSummary.value = await rfApi.summary()
  } catch {
    rfSummary.value = null
  }
})
</script>
