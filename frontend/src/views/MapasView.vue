<template>
  <div class="space-y-6">
    <h1 class="text-3xl font-bold">🗺️ Mapas e Interferencias</h1>

    <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
      <div class="lg:col-span-3 bg-gray-800 border border-gray-700 rounded-lg overflow-hidden h-96">
        <div id="map" class="w-full h-full"></div>
      </div>

      <div class="bg-gray-800 border border-gray-700 rounded-lg p-6 space-y-6">
        <div>
          <h2 class="text-lg font-semibold mb-4">Capas</h2>
          <div class="space-y-3">
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="layers.airports" class="rounded" />
              <span class="text-sm">Aeropuertos</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="layers.antennas" class="rounded" />
              <span class="text-sm">Antenas</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="layers.measurements" class="rounded" />
              <span class="text-sm">Mediciones</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="layers.flights" class="rounded" />
              <span class="text-sm">Vuelos</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="layers.hotspots" class="rounded" />
              <span class="text-sm">Zonas calientes</span>
            </label>
          </div>

          <div class="mt-6 bg-gray-900 border border-gray-700 rounded-lg p-4">
            <h3 class="text-sm font-semibold mb-3">Buscador de vuelos</h3>
            <div class="space-y-3">
              <input
                v-model="flightSearch.origin"
                placeholder="Origen (ICAO, e.g. EZE)"
                class="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:border-primary text-sm"
              />
              <input
                v-model="flightSearch.destination"
                placeholder="Destino (ICAO, e.g. COR)"
                class="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:border-primary text-sm"
              />
              <input
                v-model="flightSearch.callsign"
                placeholder="Callsign (opcional)"
                class="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:border-primary text-sm"
              />
              <select
                v-model="flightSearch.source"
                class="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:border-primary text-sm"
              >
                <option v-for="option in sourceOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <div class="grid grid-cols-2 gap-2">
                <button
                  @click="searchFlights"
                  class="w-full px-3 py-2 bg-primary hover:bg-blue-600 rounded text-sm font-semibold transition-colors"
                >
                  🔎 Buscar vuelos
                </button>
                <button
                  @click="searchAllFlights"
                  class="w-full px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm font-semibold transition-colors"
                >
                  📍 Mostrar todas
                </button>
              </div>
            </div>
          </div>

          <div class="mt-6 bg-gray-900 border border-gray-700 rounded-lg p-4">
            <div class="flex items-center justify-between mb-3">
              <div>
                <h3 class="text-sm font-semibold">Filtros avanzados</h3>
                <p class="text-xs text-gray-400">Refina los casos y rutas que se muestran en el mapa.</p>
              </div>
            </div>
            <div class="space-y-3">
              <select v-model="mapFilters.airport" class="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-100 focus:outline-none focus:border-primary">
                <option value="">Todos los aeropuertos</option>
                <option v-for="airport in airportOptions" :key="airport" :value="airport">{{ airport }}</option>
              </select>
              <div class="grid grid-cols-2 gap-2">
                <select v-model="mapFilters.severity" class="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-100 focus:outline-none focus:border-primary">
                  <option value="">Todas las severidades</option>
                  <option v-for="severity in severityOptions" :key="severity" :value="severity">{{ severity }}</option>
                </select>
                <select v-model="mapFilters.status" class="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-100 focus:outline-none focus:border-primary">
                  <option value="">Todos los estados</option>
                  <option v-for="status in statusOptions" :key="status" :value="status">{{ status }}</option>
                </select>
              </div>
              <select v-model="mapFilters.flightStatus" class="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-100 focus:outline-none focus:border-primary">
                <option value="">Todos los estados de vuelo</option>
                <option v-for="status in flightStatusOptions" :key="status" :value="status">{{ status }}</option>
              </select>
            </div>
          </div>
        </div>

        <div class="bg-gray-900 border border-gray-700 rounded-lg p-4">
          <div class="flex items-center justify-between mb-3">
            <div>
              <h3 class="text-sm font-semibold">Estado de búsqueda</h3>
              <p class="text-xs text-gray-400">Actualiza las rutas cargadas en el mapa.</p>
            </div>
            <span class="text-xs text-gray-400">
              {{ flightsStore.loading ? 'Buscando...' : flightsStore.routes.length + ' rutas' }}
            </span>
          </div>
          <div class="flex gap-2 mb-3">
            <button @click="exportGeoJSON" class="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded">Exportar GeoJSON</button>
            <button @click="exportGPX" class="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded">Exportar GPX</button>
          </div>
          <div class="text-xs text-gray-400">
            <div v-if="flightsStore.error" class="text-red-400">Error: {{ flightsStore.error }}</div>
            <div v-else-if="!flightsStore.loading && flightsStore.routes.length === 0">Sin rutas cargadas. Usa el buscador para cargar las rutas.</div>
            <div v-else-if="!flightsStore.loading">Se muestran las rutas actuales en el mapa.</div>
          </div>
        </div>

        <div class="bg-gray-900 border border-gray-700 rounded-lg p-4">
          <div class="flex items-center justify-between mb-3">
            <div>
              <h3 class="text-sm font-semibold">Leyenda</h3>
              <p class="text-xs text-gray-400">Colores y capas del mapa.</p>
            </div>
            <button @click="resetView" class="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded transition-colors">Ajustar vista</button>
          </div>
          <div class="space-y-2 text-xs text-gray-400">
            <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-sky-400"></span>Aeropuertos</div>
            <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-yellow-400"></span>Antenas</div>
            <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-orange-500"></span>Mediciones</div>
            <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-lime-500"></span>Expedientes</div>
            <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-violet-500"></span>Rutas de vuelo</div>
            <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-red-500"></span>Zonas calientes</div>
          </div>
        </div>

        <div class="bg-gray-900 border border-gray-700 rounded-lg p-4">
          <div class="flex items-center justify-between mb-3">
            <div>
              <h3 class="text-sm font-semibold">Casos visibles</h3>
              <p class="text-xs text-gray-400">Expedientes con ubicación</p>
            </div>
            <span class="text-sm font-bold text-primary">{{ mappedCount }}/{{ totalCount }}</span>
          </div>
          <div class="text-sm text-gray-400 space-y-1">
            <div>Mostrar {{ expedienteMarkers.length }} casos en el mapa</div>
            <div>{{ unmappedCount }} sin coordenadas</div>
          </div>
        </div>

        <div class="bg-gray-900 border border-gray-700 rounded-lg p-4 max-h-64 overflow-y-auto space-y-3">
          <h3 class="text-sm font-semibold mb-3">Expedientes geolocalizados</h3>
          <div v-if="expedienteMarkers.length === 0" class="text-gray-500 text-sm">No hay casos con coordenadas definidas.</div>
          <div v-for="exp in expedienteMarkers" :key="exp.id" class="p-3 bg-gray-800 rounded border border-gray-700">
            <div class="text-sm font-semibold">{{ exp.numero_expediente }}</div>
            <div class="text-xs text-gray-400">{{ exp.aeropuerto }} · {{ exp.freq_mhz?.toFixed(3) }} MHz</div>
            <div class="text-xs text-gray-400">{{ exp.lat?.toFixed(5) }}, {{ exp.lon?.toFixed(5) }}</div>
          </div>
        </div>

        <div class="bg-gray-900 border border-gray-700 rounded-lg p-4 max-h-64 overflow-y-auto space-y-3">
          <h3 class="text-sm font-semibold mb-3">Vuelos encontrados</h3>
          <div v-if="flightsStore.routes.length === 0" class="text-gray-500 text-sm">Realiza una búsqueda para ver rutas.</div>
          <div v-for="flight in flightsStore.routes" :key="flight.callsign" class="p-3 bg-gray-800 rounded border border-gray-700">
            <div class="text-sm font-semibold">{{ flight.callsign }}</div>
            <div class="text-xs text-gray-400">{{ flight.origin }} → {{ flight.destination }}</div>
            <div class="text-xs text-gray-400">Estado: {{ flight.status }}</div>
          </div>
        </div>

        <div class="mt-4 bg-gray-900 border border-gray-700 rounded-lg p-4">
          <h3 class="text-sm font-semibold mb-3">Puntos personalizados</h3>
          <div class="space-y-2">
            <div v-for="p in pointsList" :key="p.id" class="p-2 bg-gray-800 rounded flex items-center justify-between">
              <div>
                <div class="text-sm font-semibold">{{ p.label }}</div>
                <div class="text-xs text-gray-400">{{ p.type }} · {{ p.lat?.toFixed(5) }}, {{ p.lon?.toFixed(5) }}</div>
              </div>
              <div class="flex gap-2">
                <button @click="onRemovePoint(p.id)" class="px-2 py-1 bg-red-700 hover:bg-red-600 rounded text-xs">Eliminar</button>
              </div>
            </div>
            <div v-if="pointsList.length === 0" class="text-gray-400 text-sm">No hay puntos personalizados.</div>
          </div>
        </div>

        <div class="mt-2 pt-2 border-t border-gray-700">
          <button @click="startMarkerPlacement" class="w-full px-3 py-2 bg-primary hover:bg-blue-600 rounded text-sm transition-colors">
            📍 Click en mapa
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted, watch } from 'vue'
import { useExpedientesStore } from '../stores/expedientes'
import { useFlightsStore } from '../stores/flights'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { loadAirports, addAirport, updateAirport, removeAirport } from '../data/airports'
import { loadPoints, addPoint, updatePoint, removePoint } from '../data/points'

const expedientesStore = useExpedientesStore()
const flightsStore = useFlightsStore()
const map = ref(null)
const markerLayer = ref(null)
const routeLayer = ref(null)
const flightLayer = ref(null)
const hotspotLayer = ref(null)
const routeLines = ref({})

const layers = ref({
  airports: true,
  antennas: true,
  measurements: true,
  expedientes: true,
  routes: true,
  flights: true,
  hotspots: false,
})

const flightSearch = reactive({
  origin: 'EZE',
  destination: 'COR',
  callsign: '',
  source: 'sample',
})

const sourceOptions = [
  { value: 'sample', label: 'Datos de ejemplo' },
  { value: 'opensky', label: 'OpenSky' },
]

const mapFilters = reactive({
  airport: '',
  severity: '',
  status: '',
  flightStatus: '',
})

const severityOptions = ['baja', 'media', 'alta', 'crítica']
const statusOptions = ['abierto', 'investigacion', 'resuelto', 'cerrado']
const flightStatusOptions = ['en ruta', 'despegando', 'aterrizando']

const airports = [
  ...loadAirports().map(a => ({ lat: a.lat, lng: a.lon, label: a.code })),
]

const antennaSites = [
  { lat: -34.780, lng: -58.560, label: 'Antena A' },
  { lat: -34.790, lng: -58.520, label: 'Antena B' },
]

const measurementPoints = [
  ...loadPoints().filter(p => p.type === 'measurement'),
]

const hotspotZones = [
  // hotspots will be loaded from points of type 'hotspot'
  ...loadPoints().filter(p => p.type === 'hotspot').map(h => ({ lat: h.lat, lng: h.lon, radius: h.radius }))
]

// state for editing/adding points
const customPoint = reactive({ id: null, type: 'measurement', lat: '', lon: '', label: '', radius: 500 })
const pointsList = ref(loadPoints())

const expedienteMarkers = computed(() =>
  (expedientesStore.expedientes || []).filter((exp) => exp.lat != null && exp.lon != null)
)

const airportOptions = computed(() => {
  const airports = new Set()
  expedientesStore.expedientes.forEach((exp) => {
    if (exp.aeropuerto) airports.add(exp.aeropuerto)
  })
  return Array.from(airports).sort()
})

const filteredExpedienteMarkers = computed(() => {
  return expedienteMarkers.value.filter((exp) => {
    if (mapFilters.airport && exp.aeropuerto !== mapFilters.airport) return false
    if (mapFilters.severity && exp.severidad !== mapFilters.severity) return false
    if (mapFilters.status && exp.estado !== mapFilters.status) return false
    return true
  })
})

const filteredFlightRoutes = computed(() => {
  return flightsStore.routes.filter((flight) => {
    if (mapFilters.flightStatus && flight.status !== mapFilters.flightStatus) return false
    return true
  })
})

const totalCount = computed(() => expedientesStore.expedientes.length)
const mappedCount = computed(() => filteredExpedienteMarkers.value.length)
const unmappedCount = computed(() => totalCount.value - mappedCount.value)

const initMap = () => {
  if (map.value) return
  map.value = L.map('map').setView([-34.8186, -58.5358], 10)

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map.value)

  markerLayer.value = L.layerGroup().addTo(map.value)
  routeLayer.value = L.layerGroup().addTo(map.value)
  flightLayer.value = L.layerGroup().addTo(map.value)
  hotspotLayer.value = L.layerGroup().addTo(map.value)

  map.value.on('click', (event) => addMarker(event.latlng))
}

const renderMapLayers = () => {
  if (!map.value) return

  markerLayer.value.clearLayers()
  routeLayer.value.clearLayers()
  flightLayer.value.clearLayers()
  hotspotLayer.value.clearLayers()
  routeLines.value = {}

  if (layers.value.airports) {
    airports.forEach((airport) => {
      L.circleMarker([airport.lat, airport.lng], {
        color: '#38bdf8',
        radius: 8,
        fillOpacity: 0.9,
      })
        .bindPopup(`<strong>${airport.label}</strong>`)
        .addTo(markerLayer.value)
    })
  }

  if (layers.value.antennas) {
    antennaSites.forEach((site) => {
      L.marker([site.lat, site.lng], {
        icon: L.divIcon({
          className: 'bg-yellow-400 text-black rounded-full p-1',
          html: '📡',
          iconSize: [28, 28],
        }),
      })
        .bindPopup(`<strong>${site.label}</strong>`)
        .addTo(markerLayer.value)
    })
  }

  if (layers.value.measurements) {
    measurementPoints.forEach((measurement) => {
      L.circle([measurement.lat, measurement.lng], {
        color: '#f97316',
        radius: 120,
        fillOpacity: 0.18,
      })
        .bindPopup(`<strong>${measurement.label}</strong><br/>${measurement.freq} MHz<br/>${measurement.power} dBm`)
        .addTo(markerLayer.value)
    })
  }

  // custom points from local storage
  pointsList.value.forEach((p) => {
    if (p.type === 'measurement') {
      L.circle([p.lat, p.lon], { color: '#f97316', radius: 120, fillOpacity: 0.18 })
        .bindPopup(`<strong>${p.label}</strong><br/>${p.meta || ''}`)
        .addTo(markerLayer.value)
    }
    if (p.type === 'fms' || p.type === 'source') {
      L.marker([p.lat, p.lon]).bindPopup(`<strong>${p.label}</strong><br/>${p.type}`).addTo(markerLayer.value)
    }
    if (p.type === 'hotspot') {
      L.circle([p.lat, p.lon], { radius: p.radius || 500, color: '#ef4444', fillOpacity: 0.12 })
        .bindPopup(`<strong>${p.label}</strong><br/>Radio: ${p.radius} m`).addTo(markerLayer.value)
    }
  })

  if (layers.value.expedientes) {
    expedienteMarkers.value.forEach((exp) => {
      L.circleMarker([exp.lat, exp.lon], {
        color: exp.severidad === 'crítica' ? '#dc2626' : '#22c55e',
        radius: 10,
        fillOpacity: 0.85,
      })
        .bindPopup(`
          <strong>${exp.numero_expediente}</strong><br/>
          ${exp.aeropuerto || 'Aeropuerto no definido'}<br/>
          ${exp.freq_mhz?.toFixed(3) || 'N/A'} MHz<br/>
          Estado: ${exp.estado}
        `)
        .addTo(markerLayer.value)
    })
  }

  if (layers.value.flights) {
    filteredFlightRoutes.value.forEach((flight) => {
      const routeLine = L.polyline(flight.path, {
        color: '#a855f7',
        weight: 4,
        opacity: 0.9,
      }).addTo(flightLayer.value)

      // store reference for external focus
      try {
        if (flight.callsign) routeLines.value[flight.callsign] = routeLine
      } catch (e) {}

      routeLine.bindPopup(`
        <strong>${flight.callsign}</strong><br/>
        ${flight.origin} → ${flight.destination}<br/>
        Estado: ${flight.status}
      `)
      // on click, zoom to route and open popup
      routeLine.on('click', () => {
        if (map.value) {
          try {
            map.value.fitBounds(routeLine.getBounds(), { padding: [60, 60] })
          } catch (e) {
            /* ignore fitBounds errors */
          }
        }
        routeLine.openPopup()
      })
    })
  }

  if (layers.value.hotspots) {
    hotspotZones.forEach((zone) => {
      L.circle([zone.lat, zone.lng], {
        radius: zone.radius,
        color: '#ef4444',
        fillOpacity: 0.18,
      }).addTo(hotspotLayer.value)
    })
  }
}

const focusFlight = (flight) => {
  if (!map.value || !flight) return
  const key = flight.callsign
  const line = routeLines.value[key]
  if (line) {
    try { map.value.fitBounds(line.getBounds(), { padding: [60, 60] }) } catch (e) {}
    line.openPopup()
    return
  }
  // fallback: draw temporary line then fit
  if (flight.path && flight.path.length > 0) {
    const tmp = L.polyline(flight.path, { color: '#a855f7', weight: 3, dashArray: '6,6' }).addTo(flightLayer.value)
    try { map.value.fitBounds(tmp.getBounds(), { padding: [60,60] }) } catch (e) {}
    tmp.bindPopup(`<strong>${flight.callsign}</strong>`).openPopup()
    setTimeout(() => { flightLayer.value.removeLayer(tmp) }, 5000)
  }
}

watch(() => flightsStore.selectedCallsign, (cs) => {
  if (!cs) return
  const f = flightsStore.routes.find((r) => r.callsign === cs)
  if (f) focusFlight(f)
  // clear selection after focusing
  flightsStore.selectedCallsign = null
})

const exportGeoJSON = () => {
  const features = filteredFlightRoutes.value.map((f) => ({
    type: 'Feature',
    properties: { callsign: f.callsign, origin: f.origin, destination: f.destination, status: f.status },
    geometry: { type: 'LineString', coordinates: f.path.map((p) => [p[1], p[0]]) },
  }))
  const geo = { type: 'FeatureCollection', features }
  const blob = new Blob([JSON.stringify(geo, null, 2)], { type: 'application/vnd.geo+json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'flight_routes.geojson'
  a.click()
  URL.revokeObjectURL(url)
}

const exportGPX = () => {
  const header = `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="SIARI">\n`;
  const footer = `</gpx>`
  const tracks = filteredFlightRoutes.value.map((f) => {
    const trkseg = f.path.map((p) => `  <trkpt lat="${p[0]}" lon="${p[1]}"></trkpt>`).join('\n')
    return `<trk><name>${f.callsign}</name>\n<trkseg>\n${trkseg}\n</trkseg>\n</trk>`
  }).join('\n')
  const content = header + tracks + '\n' + footer
  const blob = new Blob([content], { type: 'application/gpx+xml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'flight_routes.gpx'
  a.click()
  URL.revokeObjectURL(url)
}

const searchAllFlights = async () => {
  flightSearch.origin = ''
  flightSearch.destination = ''
  flightSearch.callsign = ''
  await searchFlights()
}

const resetView = () => {
  if (!map.value) return
  const bounds = []
  expedienteMarkers.value.forEach((exp) => bounds.push([exp.lat, exp.lon]))
  flightsStore.routes.forEach((flight) => flight.path.forEach((pos) => bounds.push(pos)))
  if (bounds.length > 0) {
    map.value.fitBounds(bounds, { padding: [60, 60] })
  }
}

const addMarkerMode = ref(false)
const startMarkerPlacement = () => {
  addMarkerMode.value = true
  alert('Haga clic en el mapa para colocar un nuevo punto de medición.')
}

const addMarker = (latlng) => {
  if (!addMarkerMode.value || !map.value) return
  // open a mini-form to create a custom point
  customPoint.id = Date.now()
  customPoint.type = 'measurement'
  customPoint.lat = latlng.lat
  customPoint.lon = latlng.lng
  customPoint.label = `Medición ${new Date().toISOString().slice(0,19)}`
  // persist
  pointsList.value = addPoint({ id: customPoint.id, type: customPoint.type, lat: customPoint.lat, lon: customPoint.lon, label: customPoint.label })
  renderMapLayers()
  addMarkerMode.value = false
}

const searchFlights = async () => {
  try {
    await flightsStore.searchFlights({
      origin: flightSearch.origin,
      destination: flightSearch.destination,
      callsign: flightSearch.callsign,
      source: flightSearch.source,
    })

    renderMapLayers()

    if (flightsStore.routes.length > 0 && map.value) {
      const bounds = flightsStore.routes.flatMap((flight) => flight.path)
      map.value.fitBounds(bounds, { padding: [60, 60] })
    }
  } catch (err) {
    alert('Error buscando vuelos: ' + err.message)
  }
}

// helpers to manage custom points from UI
const onAddCustomPoint = (payload) => {
  const id = Date.now()
  const p = { id, ...payload }
  pointsList.value = addPoint(p)
  renderMapLayers()
}

const onRemovePoint = (id) => {
  pointsList.value = removePoint(id)
  renderMapLayers()
}

const onUpdatePoint = (id, patch) => {
  pointsList.value = updatePoint(id, patch)
  renderMapLayers()
}

const loadExpedientes = async () => {
  await expedientesStore.fetchExpedientes()
  if (filteredExpedienteMarkers.value.length > 0 && map.value) {
    map.value.fitBounds(filteredExpedienteMarkers.value.map((exp) => [exp.lat, exp.lon]))
  }
  renderMapLayers()
}

onMounted(async () => {
  initMap()
  await loadExpedientes()
  await searchFlights()
})

watch([layers, filteredExpedienteMarkers, () => filteredFlightRoutes.value.length, () => flightsStore.routes], renderMapLayers, { deep: true })
</script>

<style scoped>
#map {
  min-height: 100%;
}
</style>