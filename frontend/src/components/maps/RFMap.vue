<template>
  <div class="space-y-4">
    <div class="flex gap-4">
      <div class="w-72 bg-gray-900 border border-gray-700 rounded-lg p-4">
        <h2 class="text-lg font-bold mb-4">
          Capas RF
        </h2>

        <div class="space-y-2">

          <label class="flex items-center gap-2">
            <input type="checkbox" v-model="layers.airports">
            Aeropuertos
          </label>

          <label class="flex items-center gap-2">
            <input type="checkbox" v-model="layers.routes">
            Rutas vuelos
          </label>

          <label class="flex items-center gap-2">
            <input type="checkbox" v-model="layers.measurements">
            Eventos RF
          </label>

          <label class="flex items-center gap-2">
            <input type="checkbox" v-model="layers.hotspots">
            Hotspots
          </label>

          <label class="flex items-center gap-2">
            <input type="checkbox" v-model="layers.radii">
            Radios NM
          </label>

        </div>

        <div class="mt-6 border-t border-gray-700 pt-4">
          <button
            @click="enableMarkerMode"
            class="w-full bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded"
          >
            📍 Nuevo Evento RF
          </button>
        </div>

      </div>

      <div class="flex-1">
        <div :id="mapId"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const props = defineProps({ compact: { type: Boolean, default: false } })
import { useFlightsStore } from '../../stores/flights'

const map = ref(null)

const airportLayer = ref(null)
const routeLayer = ref(null)
const measurementLayer = ref(null)
const hotspotLayer = ref(null)
const radiusLayer = ref(null)
const flightsStore = useFlightsStore()

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

const markerMode = ref(false)

const layers = ref({
  airports: true,
  routes: true,
  measurements: true,
  hotspots: false,
  radii: true,
})

const airports = [
  {
    id: 1,
    name: 'San Fernando',
    lat: -34.4531,
    lng: -58.5896,
    icao: 'SADF'
  }
]

const rfEvents = [
  {
    id: 1,
    lat: -34.50,
    lng: -58.62,
    frequency: 119.0,
    power: -65,
    expediente: 'EXP-2026-001',
    notes: 'Interferencia detectada'
  }
]

const flightRoutes = [
  [
    [-34.4531, -58.5896],
    [-34.60, -58.80],
    [-34.80, -59.10]
  ]
]

const hotspots = [
  {
    lat: -34.49,
    lng: -58.61,
    radius: 3000
  }
]

const mapId = props.compact ? 'map-dashboard' : 'map'

const initMap = () => {

  map.value = L.map(mapId).setView(
    [-34.4531, -58.5896],
    props.compact ? 9 : 10
  )

  L.tileLayer(
    'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    {
      attribution: '&copy; OpenStreetMap'
    }
  ).addTo(map.value)

  airportLayer.value = L.layerGroup().addTo(map.value)
  routeLayer.value = L.layerGroup().addTo(map.value)
  measurementLayer.value = L.layerGroup().addTo(map.value)
  hotspotLayer.value = L.layerGroup().addTo(map.value)
  radiusLayer.value = L.layerGroup().addTo(map.value)

  renderLayers()

  map.value.on('click', onMapClick)
}

const renderLayers = () => {

  airportLayer.value.clearLayers()
  routeLayer.value.clearLayers()
  measurementLayer.value.clearLayers()
  hotspotLayer.value.clearLayers()
  radiusLayer.value.clearLayers()

  renderAirports()
  renderRoutes()
  renderMeasurements()
  renderHotspots()
  renderRadii()
}

const renderAirports = () => {

  if (!layers.value.airports) return

  airports.forEach((airport) => {

    const marker = L.circleMarker(
      [airport.lat, airport.lng],
      {
        radius: 8,
        color: '#38bdf8',
        fillOpacity: 1
      }
    )

    marker.bindPopup(`
      <strong>${airport.name}</strong><br/>
      ICAO: ${airport.icao}
    `)

    marker.addTo(airportLayer.value)
  })
}

const renderRoutes = () => {

  if (!layers.value.routes) return

  // If in compact mode and flights are available in the store, render them
  if (props.compact && flightsStore.routes && flightsStore.routes.length > 0) {
    flightsStore.routes.forEach((flight) => {
      const normalizedPath = normalizeFlightPath(flight.path)
      if (normalizedPath.length === 0) return
      L.polyline(normalizedPath, {
        color: '#a855f7',
        weight: 3,
        opacity: 0.95,
      }).addTo(routeLayer.value)
    })

    // fit bounds to routes for compact preview
    const allPoints = flightsStore.routes.flatMap((f) => normalizeFlightPath(f.path))
    if (allPoints.length > 0 && map.value) {
      map.value.fitBounds(allPoints, { padding: [20, 20] })
    }

    return
  }

  // fallback: render static demo routes
  flightRoutes.forEach((route) => {
    L.polyline(route, {
      color: '#a855f7',
      weight: 4,
    }).addTo(routeLayer.value)
  })
}

const renderMeasurements = () => {

  if (!layers.value.measurements) return

  rfEvents.forEach((event) => {

    const marker = L.circle(
      [event.lat, event.lng],
      {
        radius: 200,
        color: '#f97316',
        fillOpacity: 0.2
      }
    )

    marker.bindPopup(`
      <strong>Evento RF</strong><br/>
      Frecuencia: ${event.frequency} MHz<br/>
      Potencia: ${event.power} dBm<br/>
      Expediente: ${event.expediente}<br/>
      ${event.notes}
    `)

    marker.addTo(measurementLayer.value)

  })
}

const renderHotspots = () => {

  if (!layers.value.hotspots) return

  hotspots.forEach((zone) => {

    L.circle(
      [zone.lat, zone.lng],
      {
        radius: zone.radius,
        color: '#ef4444',
        fillOpacity: 0.15
      }
    ).addTo(hotspotLayer.value)

  })
}

const renderRadii = () => {

  if (!layers.value.radii) return

  airports.forEach((airport) => {

    const radiiNm = [5, 10, 20, 40]

    radiiNm.forEach((nm) => {

      const meters = nm * 1852

      L.circle(
        [airport.lat, airport.lng],
        {
          radius: meters,
          color: '#3b82f6',
          weight: 1,
          fill: false,
          dashArray: '4,4'
        }
      ).addTo(radiusLayer.value)

    })

  })
}

const enableMarkerMode = () => {
  markerMode.value = true
}

const onMapClick = (event) => {

  if (!markerMode.value) return

  const marker = L.marker(event.latlng)

  marker.bindPopup(`
    Nuevo Evento RF<br/>
    Lat: ${event.latlng.lat.toFixed(5)}<br/>
    Lon: ${event.latlng.lng.toFixed(5)}
  `)

  marker.addTo(measurementLayer.value)

  markerMode.value = false
}

onMounted(() => {
  initMap()
})

watch(layers, () => {
  renderLayers()
}, { deep: true })

watch(
  () => flightsStore.routes,
  () => {
    // re-render routes when store updates
    if (map.value) renderLayers()
  },
  { deep: true }
)

</script>

<style scoped>

/* default full map */
#map { width: 100%; height: 80vh; border-radius: 12px; }

/* compact dashboard map */
#map-dashboard { width: 100%; height: 260px; border-radius: 10px; }

</style>