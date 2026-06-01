<template>
  <div class="space-y-6">
    <!-- KPIs -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <StatCard
        title="Expedientes"
        :value="stats.totalExpedientes"
        label="Total"
        :secondary="stats.abiertos"
        secondary-label="Abiertos"
        :tertiary="stats.investigacion"
        tertiary-label="En inv."
      />
      <StatCard
        title="Interferencias"
        :value="stats.interferenciasActivas"
        label="Activas"
        :secondary="stats.interferenciasResuelta"
        secondary-label="Resueltas"
      />
      <StatCard
        title="Frecuencias"
        :value="stats.frecuenciasAnalizado"
        label="Analizadas"
        :secondary="stats.frecuenciasAltaRiesgo"
        secondary-label="Alto riesgo"
      />
      <StatCard
        title="Sistema"
        :value="stats.baseDataQuality"
        label="Calidad BD"
        :secondary="stats.uptime"
        secondary-label="Uptime"
      />
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Expedientes recientes -->
      <div class="lg:col-span-2">
        <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
            <div>
              <h2 class="text-lg font-semibold flex items-center gap-2">📋 Casos Recientes</h2>
              <p class="text-sm text-gray-400">Filtra los expedientes más recientes por aeropuerto y estado.</p>
            </div>
            <div class="flex flex-col sm:flex-row gap-3">
              <select v-model="filterAirport" class="px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 focus:outline-none focus:border-primary">
                <option value="">Todos los aeropuertos</option>
                <option v-for="airport in airportOptions" :key="airport" :value="airport">{{ airport }}</option>
              </select>
              <select v-model="filterStatus" class="px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm text-gray-200 focus:outline-none focus:border-primary">
                <option value="">Todos los estados</option>
                <option v-for="status in statusOptions" :key="status" :value="status">{{ status }}</option>
              </select>
            </div>
          </div>
          <DataTable
            :columns="['Expediente', 'Frecuencia', 'Aeropuerto', 'Estado']"
            :rows="casosRecientes"
            :actions="[
              { label: 'Ver', event: 'view', class: 'px-3 py-1 bg-blue-900 hover:bg-blue-800 rounded text-xs transition-colors' },
            ]"
            @view="goToExpediente"
          />
        </div>
      </div>

      <!-- Frecuencias críticas -->
      <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
        <h2 class="text-lg font-semibold mb-4">🔥 Frecuencias Críticas</h2>
        <div class="space-y-2">
          <div
            v-for="(freq, idx) in topFrequencies"
            :key="idx"
            class="p-3 bg-gray-700 rounded flex justify-between items-center"
          >
            <div>
              <div class="font-mono font-semibold text-warning">{{ freq.mhz }} MHz</div>
              <div class="text-xs text-gray-400">{{ freq.aeropuerto }}</div>
            </div>
            <div class="text-right">
              <div class="font-bold text-danger">{{ freq.count }}</div>
              <div class="text-xs text-gray-400">casos</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div class="lg:col-span-2 bg-gray-800 border border-gray-700 rounded-lg p-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold">✈️ Vuelos recientes</h2>
          <button @click="goToMapas" class="text-xs px-3 py-1 bg-blue-900 hover:bg-blue-800 rounded transition-colors">Ver en Mapas</button>
        </div>
        <div v-if="flightsStore.routes.length === 0" class="text-gray-400 text-sm">No se encontraron rutas de vuelo. Ejecuta la búsqueda de vuelos para cargar datos.</div>
        <div class="space-y-3">
          <div
            v-for="flight in flightsStore.routes"
            :key="flight.callsign"
            class="p-4 bg-gray-700 rounded border border-gray-700 cursor-pointer hover:bg-gray-700/80"
            @click="focusFromDashboard(flight)"
          >
            <div class="text-sm font-semibold">{{ flight.callsign }}</div>
            <div class="text-xs text-gray-400">{{ flight.origin }} → {{ flight.destination }}</div>
            <div class="text-xs text-gray-400">Salida: {{ flight.departure_time }} | Llegada: {{ flight.arrival_time }}</div>
            <div class="text-xs text-gray-400">Estado: {{ flight.status }}</div>
          </div>
        </div>
      </div>
      <div class="bg-gray-800 border border-gray-700 rounded-lg p-4">
        <h2 class="text-lg font-semibold mb-4">📍 Mapa de Rutas</h2>
        <p class="text-sm text-gray-400">Vista previa rápida del mapa con capas RF y rutas.</p>
        <div class="mt-4">
          <RFMap compact />
        </div>
      </div>
    </div>

    <!-- Gráficos -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Chart
        title="Distribución de Severidad"
        type="bar"
        :data="[
          { label: 'Baja', value: 3 },
          { label: 'Media', value: 7 },
          { label: 'Alta', value: 4 },
          { label: 'Crítica', value: 1 },
        ]"
      />
      <Chart
        title="Tendencia de Casos (últimas 6 semanas)"
        type="line"
        :data="[
          { x: 'Sem 1', y: 2 },
          { x: 'Sem 2', y: 4 },
          { x: 'Sem 3', y: 3 },
          { x: 'Sem 4', y: 5 },
          { x: 'Sem 5', y: 8 },
          { x: 'Sem 6', y: 12 },
        ]"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useExpedientesStore } from '../stores/expedientes'
import { useFlightsStore } from '../stores/flights'
import StatCard from '../components/StatCard.vue'
import DataTable from '../components/DataTable.vue'
import Chart from '../components/Chart.vue'
import RFMap from '../components/maps/RFMap.vue'

const router = useRouter()
const expedientesStore = useExpedientesStore()
const flightsStore = useFlightsStore()

const stats = computed(() => {
  const expedientes = expedientesStore.expedientes || []
  const total = expedientes.length
  const abiertos = expedientes.filter((exp) => exp.estado === 'abierto').length
  const investigacion = expedientes.filter((exp) => exp.estado === 'investigacion').length
  const resueltos = expedientes.filter((exp) => exp.estado === 'resuelto').length
  const altas = expedientes.filter((exp) => ['alta', 'crítica'].includes(exp.severidad)).length
  const mapped = expedientes.filter((exp) => exp.lat != null && exp.lon != null).length

  return {
    totalExpedientes: total,
    abiertos,
    investigacion,
    interferenciasActivas: abiertos + investigacion,
    interferenciasResuelta: resueltos,
    frecuenciasAnalizado: total,
    frecuenciasAltaRiesgo: altas,
    baseDataQuality: total === 0 ? 0 : Math.round((mapped / total) * 100),
    uptime: '99.8%',
  }
})

const topFrequencies = computed(() => {
  const counts = {}
  expedientesStore.expedientes.forEach((exp) => {
    const key = exp.freq_mhz != null ? exp.freq_mhz.toFixed(3) : 'N/A'
    if (!counts[key]) {
      counts[key] = {
        mhz: exp.freq_mhz || 0,
        aeropuerto: exp.aeropuerto || 'N/A',
        count: 0,
      }
    }
    counts[key].count += 1
  })
  return Object.values(counts)
    .sort((a, b) => b.count - a.count)
    .slice(0, 3)
})

const statusOptions = ['abierto', 'investigacion', 'resuelto', 'cerrado']
const airportOptions = computed(() => {
  const airports = new Set()
  expedientesStore.expedientes.forEach((exp) => {
    if (exp.aeropuerto) airports.add(exp.aeropuerto)
  })
  return Array.from(airports).sort()
})

const filterAirport = ref('')
const filterStatus = ref('')

const filteredExpedientes = computed(() => {
  return (expedientesStore.expedientes || []).filter((exp) => {
    if (filterAirport.value && exp.aeropuerto !== filterAirport.value) return false
    if (filterStatus.value && exp.estado !== filterStatus.value) return false
    return true
  })
})

const casosRecientes = computed(() => {
  return filteredExpedientes.value.slice(0, 5).map((exp) => ({
    Expediente: exp.numero_expediente || 'N/A',
    Frecuencia: exp.freq_mhz != null ? exp.freq_mhz.toFixed(3) : 'N/A',
    Aeropuerto: exp.aeropuerto || 'N/A',
    Estado: exp.estado || 'abierto',
    id: exp.id,
  }))
})

const goToExpediente = (row) => {
  router.push(`/expedientes/${row.id}`)
}

const goToMapas = () => {
  router.push('/map')
}

const focusFromDashboard = (flight) => {
  if (!flight || !flight.callsign) return
  flightsStore.selectedCallsign = flight.callsign
  router.push('/map')
}

onMounted(async () => {
  expedientesStore.fetchExpedientes()
  try {
    await flightsStore.searchFlights({ origin: 'EZE', destination: 'COR' })
  } catch (_err) {
    // ignore flight lookup errors for dashboard preview
  }
})
</script>
