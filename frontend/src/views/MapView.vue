<template>
  <div class="space-y-4 h-full min-h-[calc(100vh-72px)]">
    <!-- Contenedor principal con mapa 80% y panel 20% -->
    <div class="grid grid-cols-1 xl:grid-cols-[1fr_280px] gap-4 h-full min-h-[calc(100vh-120px)]">
      
      <!-- Mapa - 80% -->
      <section class="relative flex flex-col overflow-hidden rounded-3xl border border-slate-800 bg-slate-950 shadow-inner">
        <!-- Panel flotante de información (esquina superior) -->
        <div class="pointer-events-none absolute inset-x-0 top-4 mx-4 rounded-3xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 shadow-lg backdrop-blur z-10">
          <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div class="space-y-1">
              <div class="font-semibold">Mapa de Vuelos en Vivo</div>
              <div class="text-xs text-slate-400">Rutas de vuelos y eventos RF</div>
            </div>
            <div class="flex flex-wrap items-center gap-2 text-xs text-slate-300">
              <span class="rounded-full bg-slate-900/90 px-2 py-1">{{ flightsStore.routes.length }} vuelos</span>
            </div>
          </div>
        </div>

        <!-- Mapa Leaflet -->
        <div id="map" class="flex-1 w-full"></div>

        <!-- Panel de estado en la esquina inferior izquierda -->
        <div class="pointer-events-none absolute bottom-4 left-4 rounded-2xl border border-slate-800 bg-slate-950/90 px-4 py-3 text-xs text-slate-300 shadow-lg">
          <div class="font-semibold text-slate-100">Estado</div>
          <div v-if="flightSearch.callsign">{{ flightSearch.callsign }}</div>
          <div v-else>{{ flightsStore.loading ? 'Cargando...' : 'Listo' }}</div>
        </div>
      </section>

      <!-- Panel de búsqueda y control - 20% -->
      <aside class="space-y-4 rounded-2xl border border-slate-800 bg-slate-950 p-4 text-slate-200 overflow-y-auto">
        <div class="mb-4 text-sm font-semibold uppercase tracking-widest text-slate-400">Buscar Vuelos</div>

        <!-- Formulario de búsqueda -->
        <div class="space-y-3 rounded-2xl border border-slate-800 bg-slate-900 p-4">
          <input 
            v-model="flightSearch.origin" 
            placeholder="Origen (ICAO)" 
            class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500"
            @keyup.enter="searchFlights"
          />
          <input 
            v-model="flightSearch.destination" 
            placeholder="Destino (ICAO)" 
            class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500"
            @keyup.enter="searchFlights"
          />
          <input 
            v-model="flightSearch.callsign" 
            placeholder="Callsign" 
            class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500"
            @keyup.enter="searchFlights"
          />
          
          <select v-model="flightSearch.source" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100">
            <option value="sample">Demo Ruta</option>
            <option value="opensky">OpenSky Vivo</option>
          </select>

          <button 
            @click="searchFlights"
            :disabled="flightsStore.loading"
            class="w-full rounded-xl bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 px-3 py-2 text-sm font-semibold text-white transition"
          >
            {{ flightsStore.loading ? 'Buscando...' : 'Buscar' }}
          </button>
        </div>

        <!-- Error si existe -->
        <div v-if="flightsStore.error" class="rounded-2xl border border-red-800 bg-red-900/20 p-3 text-xs text-red-300">
          {{ flightsStore.error }}
        </div>

        <!-- Lista de vuelos encontrados -->
        <div class="space-y-2">
          <div class="text-xs uppercase tracking-widest text-slate-400">Vuelos Disponibles</div>
          <div v-if="flightsStore.routes.length === 0" class="rounded-2xl border border-slate-800 bg-slate-900 p-3 text-xs text-slate-400">
            Sin vuelos. Realiza una búsqueda.
          </div>
          <div v-else class="space-y-2 max-h-96 overflow-y-auto">
            <button 
              v-for="flight in flightsStore.routes" 
              :key="flight.id || flight.callsign"
              @click="selectFlight(flight)"
              :class="[
                'w-full text-left rounded-xl border px-3 py-2 text-sm transition',
                selectedFlightCallsign === flight.callsign 
                  ? 'border-blue-500 bg-blue-900/30 text-blue-100' 
                  : 'border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800'
              ]"
            >
              <div class="font-semibold">{{ flight.callsign }}</div>
              <div class="text-xs text-slate-400">
                {{ flight.origin }} → {{ flight.destination }}
              </div>
              <div class="text-xs text-slate-500">
                Estado: {{ flight.status }}
              </div>
            </button>
          </div>
        </div>

        <!-- Capas visibles -->
        <div class="space-y-2">
          <div class="text-xs uppercase tracking-widest text-slate-400">Capas</div>
          <div class="space-y-2 rounded-2xl border border-slate-800 bg-slate-900 p-3">
            <label class="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" v-model="layers.flights" class="rounded bg-slate-700" @change="renderMapLayers" />
              <span>Rutas de Vuelos</span>
            </label>
            <label class="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" v-model="layers.airports" class="rounded bg-slate-700" @change="renderMapLayers" />
              <span>Aeropuertos</span>
            </label>
            <label class="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" v-model="layers.rfEvents" class="rounded bg-slate-700" @change="renderMapLayers" />
              <span>Eventos RF</span>
            </label>
          </div>
        </div>

        <!-- Acciones -->
        <button 
          @click="resetMapView"
          class="w-full rounded-xl bg-slate-800 hover:bg-slate-700 px-3 py-2 text-sm text-slate-200 transition"
        >
          Centrar Mapa
        </button>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useFlightsStore } from '../stores/flights'
import { loadAirports } from '../data/airports'
import { loadRfEvents } from '../data/rfEvents'

const flightsStore = useFlightsStore()
const map = ref(null)
const flightLayer = ref(null)
const markerLayer = ref(null)
const eventLayer = ref(null)

const selectedFlightCallsign = ref(null)
const flightSearch = reactive({
  origin: 'EZE',
  destination: 'COR',
  callsign: '',
  source: 'sample'
})

const layers = reactive({
  flights: true,
  airports: true,
  rfEvents: true
})

const airports = ref(loadAirports())
const rfEvents = ref(loadRfEvents())

const initMap = () => {
  if (map.value) return

  map.value = L.map('map', { zoomControl: false }).setView([-34.8186, -58.5358], 9)

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map.value)

  L.control.zoom({ position: 'topright' }).addTo(map.value)
  L.control.scale({ position: 'bottomleft', imperial: false, metric: true }).addTo(map.value)

  flightLayer.value = L.layerGroup().addTo(map.value)
  markerLayer.value = L.layerGroup().addTo(map.value)
  eventLayer.value = L.layerGroup().addTo(map.value)

  map.value.on('click', (e) => {
    console.log('Ubicación:', e.latlng.lat, e.latlng.lng)
  })

  renderMapLayers()
}

const normalizeFlightPath = (path) => {
  if (!Array.isArray(path)) return []
  return path
    .map((coord) => {
      if (!Array.isArray(coord) || coord.length < 2) return null
      const lat = Number(coord[0])
      const lng = Number(coord[1])
      return Number.isFinite(lat) && Number.isFinite(lng) ? [lat, lng] : null
    })
    .filter((coord) => coord !== null)
}

const searchFlights = async () => {
  try {
    await flightsStore.searchFlights(flightSearch)
    renderMapLayers()
  } catch (err) {
    console.error('Error en búsqueda:', err)
  }
}

const selectFlight = (flight) => {
  selectedFlightCallsign.value = flight.callsign
  // Zoom a la ruta del vuelo si existe
  if (flight.path && map.value) {
    const path = normalizeFlightPath(flight.path)
    if (path.length > 0) {
      map.value.fitBounds(path, { padding: [100, 100] })
    }
  }
}

const renderMapLayers = () => {
  if (!map.value) return

  markerLayer.value.clearLayers()
  flightLayer.value.clearLayers()
  eventLayer.value.clearLayers()

  // Renderizar rutas de vuelos
  if (layers.flights && flightsStore.routes.length > 0) {
    flightsStore.routes.forEach((flight) => {
      const path = normalizeFlightPath(flight.path)
      if (path.length < 2) return

      // Dibujar la línea de ruta
      const color = selectedFlightCallsign.value === flight.callsign ? '#22c55e' : '#a855f7'
      const weight = selectedFlightCallsign.value === flight.callsign ? 6 : 3
      const line = L.polyline(path, { 
        color, 
        weight, 
        opacity: 0.9 
      }).addTo(flightLayer.value)

      // Popup en la ruta
      line.bindPopup(`
        <div class="text-sm font-semibold">${flight.callsign}</div>
        <div class="text-xs text-slate-600">${flight.origin} → ${flight.destination}</div>
        <div class="text-xs text-slate-600">Estado: ${flight.status}</div>
      `)

      // Marcador de posición actual (último punto de la ruta)
      if (path.length > 0) {
        const lastPos = path[path.length - 1]
        const marker = L.circleMarker(lastPos, {
          color: color,
          radius: 8,
          fillOpacity: 0.9,
          weight: 2
        }).addTo(flightLayer.value)

        marker.bindPopup(`
          <div class="font-semibold">${flight.callsign}</div>
          <div class="text-xs">Posición actual</div>
          <div class="text-xs">${lastPos[0].toFixed(4)}, ${lastPos[1].toFixed(4)}</div>
        `)
      }
    })
  }

  // Renderizar aeropuertos
  if (layers.airports && airports.value) {
    airports.value.forEach((airport) => {
      const marker = L.circleMarker([airport.lat, airport.lon], {
        color: '#38bdf8',
        radius: 6,
        fillOpacity: 0.8,
        weight: 2
      }).addTo(markerLayer.value)

      marker.bindPopup(`
        <div class="font-semibold">${airport.name}</div>
        <div class="text-xs">ICAO: ${airport.icao}</div>
        <div class="text-xs">IATA: ${airport.iata}</div>
      `)
    })
  }

  // Renderizar eventos RF
  if (layers.rfEvents && rfEvents.value) {
    rfEvents.value.forEach((event) => {
      const marker = L.circleMarker([event.lat, event.lon], {
        color: '#f97316',
        radius: 8,
        fillOpacity: 0.7,
        weight: 2
      }).addTo(eventLayer.value)

      marker.bindPopup(`
        <div class="font-semibold">RF ${event.frecuencia_mhz} MHz</div>
        <div class="text-xs">Nivel: ${event.nivel_dbm} dBm</div>
      `)
    })
  }

  if (map.value && map.value.invalidateSize) {
    map.value.invalidateSize()
  }
}

const resetMapView = () => {
  if (map.value) {
    map.value.setView([-34.8186, -58.5358], 9)
  }
}

onMounted(() => {
  initMap()
  // Cargar vuelos demo inicialmente
  searchFlights()
})

// Vigilar cambios en las rutas del store para actualizar el mapa
watch(
  () => flightsStore.routes,
  () => {
    renderMapLayers()
  },
  { deep: true }
)
</script>