<template>
  <main class="page-doc situation">
    <header class="situation-heading">
      <div>
        <p class="situation-kicker">AeroRF · Operaciones</p>
        <h1 class="page-doc-title">Centro de Situación</h1>
        <p class="page-doc-sub">
          Estado operativo, seguimiento y actividad geográfica registrada.
        </p>
      </div>
      <button class="gis-mini-btn" :disabled="refreshing" @click="refresh">
        {{ refreshing ? 'Actualizando…' : 'Actualizar' }}
      </button>
    </header>

    <section class="situation-grid" aria-label="Estado operativo">
      <article class="situation-card">
        <h2>Servicios</h2>
        <p v-if="sections.services.loading" class="situation-muted">Consultando estado…</p>
        <p v-else-if="sections.services.error" class="situation-error">{{ sections.services.error }}</p>
        <template v-else-if="sections.services.data">
          <div class="situation-status-row">
            <span>API</span>
            <strong :class="sections.services.data.status === 'ok' ? 'is-good' : 'is-warn'">
              {{ sections.services.data.status === 'ok' ? 'Disponible' : 'Degradada' }}
            </strong>
          </div>
          <div class="situation-status-row">
            <span>Base de datos</span>
            <strong :class="sections.services.data.database?.connected ? 'is-good' : 'is-warn'">
              {{ sections.services.data.database?.connected ? 'Conectada' : 'Sin conexión' }}
            </strong>
          </div>
          <div class="situation-status-row">
            <span>OpenSky</span>
            <strong>{{ openSkyMode }}</strong>
          </div>
          <p class="situation-note">
            El estado de OpenSky indica capacidad/configuración reportada por el backend,
            no una prueba de conectividad en tiempo real.
          </p>
        </template>
      </article>

      <article class="situation-card">
        <h2>Aeronaves seguidas</h2>
        <p v-if="sections.aircraft.loading" class="situation-muted">Consultando seguimiento…</p>
        <p v-else-if="sections.aircraft.error" class="situation-error">{{ sections.aircraft.error }}</p>
        <template v-else>
          <div class="situation-metric">
            <strong>{{ trackedAircraft.length }}</strong>
            <span>en lista · {{ liveAircraftCount }} con estado recibido</span>
          </div>
          <ul v-if="trackedAircraft.length" class="situation-list">
            <li v-for="aircraft in trackedAircraft" :key="aircraft.icao24">
              <span>{{ aircraft.callsign || aircraft.icao24 }}</span>
              <span class="situation-mono">
                {{ aircraft.state ? 'posición recibida' : 'sin posición recibida' }}
              </span>
            </li>
          </ul>
          <p v-else class="situation-muted">No hay aeronaves en la lista de seguimiento.</p>
          <p class="situation-note">
            Se muestran solo aeronaves seguidas por el operador; no es un recuento del tráfico aéreo global.
          </p>
        </template>
      </article>

      <article class="situation-card">
        <h2>Sesiones de seguimiento</h2>
        <p v-if="sections.sessions.loading" class="situation-muted">Consultando sesiones…</p>
        <p v-else-if="sections.sessions.error" class="situation-error">{{ sections.sessions.error }}</p>
        <template v-else>
          <div class="situation-metric">
            <strong>{{ activeSessions.length }}</strong>
            <span>sesiones grabando</span>
          </div>
          <ul v-if="sections.sessions.data?.length" class="situation-list">
            <li v-for="session in sections.sessions.data" :key="session.id">
              <span>{{ session.callsign || session.icao24 }}</span>
              <span class="situation-mono">{{ session.status }}</span>
            </li>
          </ul>
          <p v-else class="situation-muted">No hay sesiones de seguimiento en curso.</p>
        </template>
      </article>

      <article class="situation-card">
        <h2>Actividad RF</h2>
        <p v-if="sections.rf.loading" class="situation-muted">Consultando eventos…</p>
        <p v-else-if="sections.rf.error" class="situation-error">{{ sections.rf.error }}</p>
        <template v-else-if="sections.rf.data">
          <div class="situation-metric">
            <strong>{{ sections.rf.data.summary?.events_total ?? '—' }}</strong>
            <span>eventos RF GIS registrados</span>
          </div>
          <ul v-if="sections.rf.data.events.length" class="situation-list">
            <li v-for="event in sections.rf.data.events" :key="event.id">
              <span>{{ event.name || event.properties?.event?.classification || `Evento #${event.id}` }}</span>
              <span class="situation-mono">{{ event.properties?.event?.frequency_mhz ?? '—' }} MHz</span>
            </li>
          </ul>
          <p v-else class="situation-muted">No hay eventos RF registrados.</p>
        </template>
      </article>

      <article class="situation-card">
        <h2>Mediciones recientes</h2>
        <p v-if="sections.measurements.loading" class="situation-muted">Consultando mediciones…</p>
        <p v-else-if="sections.measurements.error" class="situation-error">{{ sections.measurements.error }}</p>
        <template v-else-if="sections.measurements.data">
          <ul v-if="sections.measurements.data.objects.length" class="situation-list">
            <li v-for="measurement in sections.measurements.data.objects" :key="measurement.id">
              <span>{{ measurement.name || `Medición #${measurement.id}` }}</span>
              <span class="situation-mono">{{ formatDate(measurement.created_at) }}</span>
            </li>
          </ul>
          <p v-else class="situation-muted">No hay mediciones GIS registradas.</p>
        </template>
      </article>

      <article class="situation-card">
        <h2>Actividad del sistema</h2>
        <p class="situation-muted">
          Esta instalación no expone un historial de actividad persistido. Los registros técnicos
          se escriben en la salida del backend; no se muestran aquí como eventos simulados.
        </p>
      </article>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { flights, mapObjects, rf, system } from '@/api/client'
import { useFlightsStore } from '@/stores/flights'

const flightsStore = useFlightsStore()
const refreshing = ref(false)

const sections = reactive({
  services: { loading: true, error: null, data: null },
  aircraft: { loading: true, error: null, data: null },
  sessions: { loading: true, error: null, data: null },
  rf: { loading: true, error: null, data: null },
  measurements: { loading: true, error: null, data: null },
})

const trackedAircraft = computed(() =>
  (sections.aircraft.data || []).map((slot) => ({
    ...slot,
    state: flightsStore.liveStates[slot.icao24] || null,
  })),
)
const liveAircraftCount = computed(() =>
  trackedAircraft.value.filter((aircraft) => aircraft.state).length,
)
const activeSessions = computed(() =>
  (sections.sessions.data || []).filter((session) => session.status === 'recording'),
)
const openSkyMode = computed(() => {
  const opensky = sections.services.data?.opensky
  if (!opensky) return 'Sin información'
  if (opensky.configured) return 'Credenciales configuradas'
  return opensky.can_query_states ? 'Modo anónimo disponible' : 'No disponible'
})

async function loadSection(name, request, select = (value) => value) {
  const section = sections[name]
  section.loading = true
  section.error = null
  section.data = null
  try {
    section.data = select(await request())
  } catch (error) {
    section.error = error?.response?.data?.detail || error?.message || 'Error al cargar los datos.'
  } finally {
    section.loading = false
  }
}

async function refresh() {
  refreshing.value = true
  try {
    await Promise.all([
      loadSection('services', () => system.status()),
      loadSection('aircraft', async () => {
        const result = await flights.tracked()
        flightsStore.watchlist = result.slots || []
        flightsStore.subscribeSocket()
        return flightsStore.watchlist
      }),
      loadSection(
        'sessions',
        () => flights.sessions({ status: 'recording', limit: 20 }),
        (result) => result.sessions || [],
      ),
      loadSection('rf', async () => {
        const [summary, events] = await Promise.all([
          rf.summary(),
          rf.events({ limit: 8 }),
        ])
        return { summary, events: events.events || [] }
      }),
      loadSection(
        'measurements',
        () => mapObjects.list({ type: 'measurement', limit: 8, order_by: 'recent' }),
      ),
    ])
  } finally {
    refreshing.value = false
  }
}

function formatDate(value) {
  if (!value) return 'fecha no informada'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'fecha no informada' : date.toLocaleString()
}

onMounted(refresh)
</script>

<style scoped>
.situation {
  max-width: 1440px;
}

.situation-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.situation-kicker {
  margin-bottom: 0.3rem;
  color: var(--signal);
  font: 600 0.625rem var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.situation-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}

.situation-card {
  min-width: 0;
  padding: 1rem;
  border: 1px solid var(--borde);
  border-radius: 0.5rem;
  background: var(--panel);
}

.situation-card h2 {
  margin-bottom: 0.8rem;
  color: var(--texto-secundario, var(--texto-tenue));
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.situation-status-row,
.situation-list li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.8rem;
  padding: 0.45rem 0;
  border-bottom: 1px solid var(--borde);
  color: var(--texto);
  font-size: 0.75rem;
}

.situation-list {
  max-height: 12rem;
  overflow: auto;
  margin-top: 0.5rem;
}

.situation-list li:last-child {
  border-bottom: 0;
}

.situation-metric {
  display: flex;
  align-items: baseline;
  gap: 0.55rem;
  color: var(--texto-tenue);
  font-size: 0.7rem;
}

.situation-metric strong {
  color: var(--texto);
  font: 600 1.65rem var(--font-mono);
}

.situation-mono {
  flex: none;
  color: var(--texto-tenue);
  font: 0.625rem var(--font-mono);
}

.situation-muted,
.situation-note,
.situation-error {
  color: var(--texto-tenue);
  font-size: 0.7rem;
  line-height: 1.45;
}

.situation-note {
  margin-top: 0.75rem;
  font-size: 0.625rem;
}

.situation-error {
  color: var(--risk-high);
}

.is-good {
  color: var(--risk-ok);
}

.is-warn {
  color: var(--risk-mid);
}

@media (max-width: 900px) {
  .situation-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .situation-heading {
    align-items: center;
  }

  .situation-grid {
    grid-template-columns: 1fr;
  }
}
</style>
