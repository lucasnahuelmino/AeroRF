<template>
  <div class="space-y-4 h-full min-h-[calc(100vh-72px)]">
    <div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4 h-full min-h-[60vh]">
      <!-- Mapa central -->
      <section class="relative flex min-h-[60vh] flex-col overflow-hidden rounded-3xl border border-slate-800 bg-slate-950 shadow-inner">
        <div class="absolute left-4 top-4 z-20 w-[22rem] max-h-[calc(100vh-18rem)] overflow-y-auto rounded-3xl border border-slate-800 bg-slate-950/95 p-4 shadow-2xl backdrop-blur-xl">
          <div class="mb-4 text-sm font-semibold uppercase tracking-widest text-slate-400">Herramientas GIS</div>

          <div class="grid grid-cols-2 gap-2">
            <button @click="setTool('select')" :class="buttonClass(toolMode === 'select')">Seleccionar</button>
            <button @click="setTool('point')" :class="buttonClass(toolMode === 'point')">Punto</button>
            <button @click="setTool('line')" :class="buttonClass(toolMode === 'line')">Línea</button>
            <button @click="setTool('polygon')" :class="buttonClass(toolMode === 'polygon')">Polígono</button>
            <button @click="setTool('circle')" :class="buttonClass(toolMode === 'circle')">Círculo</button>
            <button @click="setTool('radius')" :class="buttonClass(toolMode === 'radius')">Radio</button>
            <button @click="setTool('measure')" :class="buttonClass(toolMode === 'measure')">Medir</button>
            <button @click="setTool('event')" :class="buttonClass(toolMode === 'event')">Evento RF</button>
          </div>

          <div class="rounded-2xl border border-slate-800 bg-slate-900 p-3 mt-4">
            <div class="text-xs uppercase tracking-wide text-slate-400">Modo activo</div>
            <div class="mt-2 text-sm font-semibold text-white">{{ toolLabel }}</div>
            <div class="mt-2 text-xs text-slate-400">{{ toolInstructions }}</div>
          </div>

          <div v-if="toolMode === 'line' || toolMode === 'polygon'" class="rounded-2xl border border-slate-800 bg-slate-900 p-3 space-y-2 mt-4">
            <div class="text-xs text-slate-400">Puntos en edición: {{ activePoints.value.length }}</div>
            <button @click="commitShape" class="w-full rounded-xl bg-slate-800 px-3 py-2 text-sm text-slate-100 hover:bg-slate-700">Guardar {{ toolMode === 'line' ? 'línea' : 'polígono' }}</button>
          </div>

          <div v-if="toolMode === 'circle' || toolMode === 'radius'" class="rounded-2xl border border-slate-800 bg-slate-900 p-3 space-y-3 mt-4">
            <div class="text-xs text-slate-400">Centro de círculo definido al hacer clic en el mapa.</div>
            <div class="grid grid-cols-2 gap-2">
              <input v-model.number="activeCircleRadius" type="number" min="1" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
              <select v-model="activeRadiusUnit" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100">
                <option value="km">km</option>
                <option value="nm">NM</option>
              </select>
            </div>
            <button @click="commitCircle" class="w-full rounded-xl bg-slate-800 px-3 py-2 text-sm text-slate-100 hover:bg-slate-700">Guardar círculo</button>
          </div>

          <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4 mt-4">
            <div class="flex items-center justify-between mb-3 text-sm font-semibold uppercase tracking-widest text-slate-400">Capas</div>
            <div class="space-y-3 text-sm">
              <label class="flex items-center gap-2"><input type="checkbox" v-model="layers.airports" class="rounded bg-slate-700" /> Aeropuertos</label>
              <label class="flex items-center gap-2"><input type="checkbox" v-model="layers.fmStations" class="rounded bg-slate-700" /> FM</label>
              <label class="flex items-center gap-2"><input type="checkbox" v-model="layers.rfEvents" class="rounded bg-slate-700" /> Eventos RF</label>
              <label class="flex items-center gap-2"><input type="checkbox" v-model="layers.hotspots" class="rounded bg-slate-700" /> Hotspots</label>
              <label class="flex items-center gap-2"><input type="checkbox" v-model="layers.expedientes" class="rounded bg-slate-700" /> Expedientes</label>
              <label class="flex items-center gap-2"><input type="checkbox" v-model="layers.antennas" class="rounded bg-slate-700" /> Antenas</label>
              <label class="flex items-center gap-2"><input type="checkbox" v-model="layers.flights" class="rounded bg-slate-700" /> Vuelos</label>
              <label class="flex items-center gap-2"><input type="checkbox" v-model="layers.heatmap" class="rounded bg-slate-700" /> Heatmap RF</label>
              <label class="flex items-center gap-2"><input type="checkbox" v-model="layers.userMarkers" class="rounded bg-slate-700" /> Marcadores</label>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3 mt-4">
            <div class="text-sm font-semibold uppercase tracking-widest text-slate-400">Acciones</div>
            <button @click="resetMapView" class="w-full rounded-xl bg-primary px-3 py-2 text-sm font-semibold text-slate-900">Centrar mapa</button>
            <button @click="refreshOpenSky" class="w-full rounded-xl bg-slate-800 px-3 py-2 text-sm text-slate-200 hover:bg-slate-700">Actualizar OpenSky</button>
            <button @click="clearUserData" class="w-full rounded-xl bg-rose-700 px-3 py-2 text-sm font-semibold text-white hover:bg-rose-600">Limpiar datos de usuario</button>
          </div>

          <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3 mt-4">
            <div class="text-sm font-semibold uppercase tracking-widest text-slate-400">Buscar vuelos</div>
            <input v-model="flightSearch.origin" placeholder="Origen ICAO" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <input v-model="flightSearch.destination" placeholder="Destino ICAO" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <input v-model="flightSearch.callsign" placeholder="Callsign" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <select v-model="flightSearch.source" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100">
              <option value="sample">Demo de ruta</option>
              <option value="opensky">OpenSky en vivo</option>
            </select>
            <div class="grid grid-cols-2 gap-2">
              <button @click="searchFlights" class="rounded-xl bg-slate-800 px-3 py-2 text-sm text-slate-100 hover:bg-slate-700">Buscar</button>
              <button @click="refreshOpenSky" class="rounded-xl bg-primary px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-blue-700">Buscar en OpenSky</button>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3 mt-4">
            <div class="text-sm font-semibold uppercase tracking-widest text-slate-400">Agregar aeropuerto</div>
            <input v-model="airportForm.icao" placeholder="ICAO" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <input v-model="airportForm.iata" placeholder="IATA" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <input v-model="airportForm.name" placeholder="Nombre" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <div class="grid gap-2 sm:grid-cols-2">
              <input v-model.number="airportForm.lat" placeholder="Latitud" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
              <input v-model.number="airportForm.lon" placeholder="Longitud" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            </div>
            <input v-model.number="airportForm.elev" placeholder="Elevación (ft)" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <button @click="saveAirport" class="w-full rounded-xl bg-slate-800 px-3 py-2 text-sm text-slate-100 hover:bg-slate-700">Guardar aeropuerto</button>
          </div>

          <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3 mt-4">
            <div class="text-sm font-semibold uppercase tracking-widest text-slate-400">Agregar emisora FM</div>
            <input v-model="fmForm.name" placeholder="Nombre" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <input v-model.number="fmForm.frequency_mhz" placeholder="Frecuencia MHz" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <input v-model.number="fmForm.lat" placeholder="Latitud" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <input v-model.number="fmForm.lon" placeholder="Longitud" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <button @click="saveFMStation" class="w-full rounded-xl bg-slate-800 px-3 py-2 text-sm text-slate-100 hover:bg-slate-700">Guardar FM</button>
          </div>

          <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3 mt-4">
            <div class="text-sm font-semibold uppercase tracking-widest text-slate-400">Registrar evento RF</div>
            <input v-model.number="eventForm.frecuencia_mhz" placeholder="Frecuencia MHz" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <input v-model.number="eventForm.nivel_dbm" placeholder="Nivel dBm" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <input v-model="eventForm.expediente" placeholder="Expediente" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
            <textarea v-model="eventForm.descripcion" placeholder="Descripción" rows="2" class="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100"></textarea>
            <button @click="createRfEvent" class="w-full rounded-xl bg-slate-800 px-3 py-2 text-sm text-slate-100 hover:bg-slate-700">Registrar evento</button>
          </div>
        </div>

        <div id="map" class="flex-1 w-full min-h-[60vh]"></div>
        <div class="pointer-events-none absolute inset-x-0 top-4 mx-4 rounded-3xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-100 shadow-lg backdrop-blur md:mx-6">
          <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div class="space-y-1">
              <div class="font-semibold">Mapa operacional</div>
              <div class="text-xs text-slate-400">Use herramientas, capas y seleccione objetos para ver detalles.</div>
            </div>
            <div class="flex flex-wrap items-center gap-2 text-xs text-slate-300">
              <span class="rounded-full bg-slate-900/90 px-2 py-1">{{ flightsStore.routes.length }} vuelos</span>
              <span class="rounded-full bg-slate-900/90 px-2 py-1">{{ airports.value.length }} aeropuertos</span>
              <span class="rounded-full bg-slate-900/90 px-2 py-1">{{ fmStations.value.length }} emisoras FM</span>
            </div>
          </div>
        </div>
        <div class="pointer-events-none absolute bottom-4 left-4 rounded-3xl border border-slate-800 bg-slate-950/90 px-4 py-3 text-xs text-slate-300 shadow-lg">
          <div class="font-semibold text-slate-100">Estado de dibujo</div>
          <div>{{ drawStatus }}</div>
        </div>
      </section>

      <!-- Panel contextual derecho -->
      <aside class="space-y-4 rounded-2xl border border-slate-800 bg-slate-950 p-4 text-slate-200 overflow-y-auto">
        <div class="mb-4 text-sm font-semibold uppercase tracking-widest text-slate-400">Contexto</div>
        <div v-if="selectedFeature" class="space-y-4 rounded-2xl border border-slate-800 bg-slate-900 p-4">
          <div class="text-sm font-semibold text-white">{{ selectedFeature.title }}</div>
          <div class="text-xs text-slate-400">Tipo: {{ selectedType }}</div>
          <div class="grid gap-2 text-sm">
            <template v-for="(value, key) in selectedFeature.details" :key="key">
              <div class="grid grid-cols-[110px_minmax(0,1fr)] gap-2">
                <span class="text-slate-500">{{ key }}</span>
                <span class="break-all">{{ value }}</span>
              </div>
            </template>
          </div>
        </div>
        <div v-else class="rounded-2xl border border-slate-800 bg-slate-900 p-4 text-sm text-slate-400">
          Seleccione un aeropuerto, vuelo, evento RF o marcador en el mapa para ver su ficha completa.
        </div>

        <div class="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3">
          <div class="text-sm font-semibold uppercase tracking-widest text-slate-400">Resumen</div>
          <div class="grid gap-2 text-sm">
            <div class="flex items-center justify-between rounded-xl bg-slate-950 px-3 py-2"><span>Eventos RF</span><span>{{ rfEvents.value.length }}</span></div>
            <div class="flex items-center justify-between rounded-xl bg-slate-950 px-3 py-2"><span>Hotspots</span><span>{{ userCircles.value.length }}</span></div>
            <div class="flex items-center justify-between rounded-xl bg-slate-950 px-3 py-2"><span>Marcas</span><span>{{ userMarkers.value.length }}</span></div>
            <div class="flex items-center justify-between rounded-xl bg-slate-950 px-3 py-2"><span>Líneas/Polígonos</span><span>{{ shapeCount }}</span></div>
          </div>
        </div>
      </aside>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-[1.3fr_minmax(0,320px)] gap-4">
      <section class="rounded-2xl border border-slate-800 bg-slate-950 p-4 text-slate-200">
        <div class="flex items-center justify-between mb-4">
          <div class="text-sm font-semibold uppercase tracking-widest text-slate-400">Consola de eventos</div>
          <span class="text-xs text-slate-400">Registros recientes</span>
        </div>
        <div class="h-48 overflow-y-auto rounded-3xl border border-slate-800 bg-slate-900 p-3 text-xs leading-5 text-slate-300">
          <div v-if="logs.length === 0" class="text-slate-500">No hay entradas recientes.</div>
          <div v-for="entry in logs" :key="entry.id" class="mb-3 border-b border-slate-800 pb-2 last:border-none">
            <div class="text-slate-100 font-medium">{{ entry.title }}</div>
            <div class="text-slate-500">{{ entry.subtitle }}</div>
            <div class="mt-1 text-slate-400">{{ entry.detail }}</div>
          </div>
        </div>
      </section>

      <section class="rounded-2xl border border-slate-800 bg-slate-950 p-4 text-slate-200">
        <div class="text-sm font-semibold uppercase tracking-widest text-slate-400 mb-3">Mediciones</div>
        <div class="grid gap-3 text-sm">
          <div class="rounded-2xl bg-slate-900 p-3">
            <div class="text-slate-400">Puntos</div>
            <div class="mt-2 text-white">{{ measurementPoints.value.length }} / 2</div>
          </div>
          <div v-if="measurementResult.value" class="rounded-2xl bg-slate-900 p-3">
            <div class="text-slate-400">Distancia</div>
            <div class="mt-2 text-white">{{ measurementResult.value.distance_km.toFixed(2) }} km</div>
            <div class="text-slate-400">{{ measurementResult.value.distance_nm.toFixed(2) }} NM</div>
            <div class="text-slate-400">{{ measurementResult.value.distance_mi.toFixed(2) }} mi</div>
            <div class="text-slate-400">Bearing</div>
            <div class="text-white">{{ measurementResult.value.bearing.toFixed(1) }}°</div>
          </div>
          <button @click="clearMeasurement" class="w-full rounded-xl bg-slate-800 px-3 py-2 text-sm text-slate-200 hover:bg-slate-700">Borrar medición</button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted, watch, nextTick } from 'vue'
import { useExpedientesStore } from '../stores/expedientes'
import { useFlightsStore } from '../stores/flights'
import { useSystemStore } from '../stores/system'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { loadAirports, addAirport } from '../data/airports'
import { loadFMStations, addFMStation } from '../data/fmStations'
import { loadPoints, savePoints, addPoint } from '../data/points'
import { loadRfEvents, addRfEvent } from '../data/rfEvents'

const expedientesStore = useExpedientesStore()
const flightsStore = useFlightsStore()
const systemStore = useSystemStore()

const map = ref(null)
const markerLayer = ref(null)
const flightLayer = ref(null)
const userLayer = ref(null)
const eventLayer = ref(null)
const heatmapLayer = ref(null)
const drawLayer = ref(null)

const toolMode = ref('select')
const activePoints = ref([])
const activeCircleCenter = ref(null)
const activeCircleRadius = ref(5)
const activeRadiusUnit = ref('nm')
const measurementPoints = ref([])
const measurementResult = ref(null)
const selectedFeature = ref(null)
const selectedType = ref(null)
const logs = ref([])

const airportForm = reactive({ icao: '', iata: '', name: '', lat: -34.82, lon: -58.54, elev: 0 })
const fmForm = reactive({ name: '', frequency_mhz: 98.1, lat: -34.82, lon: -58.54 })
const eventForm = reactive({ frecuencia_mhz: 118.0, nivel_dbm: -60, expediente: '', descripcion: '', lat: null, lon: null })
const flightSearch = reactive({ origin: 'EZE', destination: 'COR', callsign: '', source: 'sample' })

const airports = ref(loadAirports())
const fmStations = ref(loadFMStations())
const pointsList = ref(loadPoints())
const rfEvents = ref(loadRfEvents())
const antennaSites = [
  { lat: -34.780, lon: -58.560, label: 'Antena A' },
  { lat: -34.790, lon: -58.520, label: 'Antena B' },
]

const layers = reactive({
  airports: true,
  fmStations: true,
  rfEvents: true,
  hotspots: true,
  expedientes: true,
  antennas: true,
  flights: true,
  heatmap: false,
  userMarkers: true,
})

const toolLabel = computed(() => {
  switch (toolMode.value) {
    case 'point': return 'Agregar punto'
    case 'line': return 'Dibujar línea'
    case 'polygon': return 'Dibujar polígono'
    case 'circle': return 'Dibujar círculo'
    case 'radius': return 'Crear radio'
    case 'measure': return 'Medir distancia'
    case 'event': return 'Registrar evento'
    default: return 'Seleccionar elemento'
  }
})

const toolInstructions = computed(() => {
  switch (toolMode.value) {
    case 'point': return 'Haga clic en el mapa para crear un marcador de usuario.'
    case 'line': return 'Haga clic en múltiples puntos para definir una línea. Pulse Guardar cuando termine.'
    case 'polygon': return 'Haga clic en al menos tres puntos para crear un polígono.'
    case 'circle': return 'Haga clic en el centro del círculo y luego guarde el radio.'
    case 'radius': return 'Haga clic en el centro y elija el radio en NM.'
    case 'measure': return 'Haga clic en dos puntos para medir distancia y bearing.'
    case 'event': return 'Haga clic donde se registró el evento RF.'
    default: return 'Seleccione un elemento para ver detalles y herramientas.'
  }
})

const drawStatus = computed(() => {
  if (toolMode.value === 'line' || toolMode.value === 'polygon') {
    return `${activePoints.value.length} puntos cargados`
  }
  if (toolMode.value === 'circle' && activeCircleCenter.value) {
    return `Centro marcado · radio ${activeCircleRadius.value} ${activeRadiusUnit.value}`
  }
  if (toolMode.value === 'measure') {
    return `${measurementPoints.value.length} puntos` 
  }
  return 'Listo'
})

const userMarkers = computed(() => pointsList.value.filter((p) => p.type === 'marker'))
const userLines = computed(() => pointsList.value.filter((p) => p.type === 'line'))
const userPolygons = computed(() => pointsList.value.filter((p) => p.type === 'polygon'))
const userCircles = computed(() => pointsList.value.filter((p) => p.type === 'circle'))
const shapeCount = computed(() => userLines.value.length + userPolygons.value.length)

const addLog = (title, subtitle, detail) => {
  logs.value.unshift({ id: Date.now() + Math.random(), title, subtitle, detail })
  if (logs.value.length > 30) logs.value.pop()
}

const saveAirport = () => {
  if (!airportForm.icao || !airportForm.name) return
  const next = addAirport({
    icao: airportForm.icao.toUpperCase(),
    iata: airportForm.iata.toUpperCase(),
    name: airportForm.name,
    lat: airportForm.lat || -34.82,
    lon: airportForm.lon || -58.54,
    elev: airportForm.elev || 0,
  })
  airports.value = next
  addLog('Aeropuerto agregado', airportForm.icao.toUpperCase(), airportForm.name)
  airportForm.icao = ''
  airportForm.iata = ''
  airportForm.name = ''
  airportForm.elev = 0
  renderMapLayers()
}

const saveFMStation = () => {
  if (!fmForm.name || !fmForm.frequency_mhz) return
  const next = addFMStation({
    id: `fm-${Date.now()}`,
    name: fmForm.name,
    frequency_mhz: Number(fmForm.frequency_mhz),
    lat: Number(fmForm.lat),
    lon: Number(fmForm.lon),
    power_dbm: 30,
    height_m: 100,
    description: 'Emisora FM agregada por el operador',
  })
  fmStations.value = next
  addLog('Emisora FM guardada', fmForm.name, `${fmForm.frequency_mhz} MHz`)
  fmForm.name = ''
  fmForm.frequency_mhz = 98.1
  fmForm.lat = -34.82
  fmForm.lon = -58.54
  renderMapLayers()
}

const createRfEvent = () => {
  if (!eventForm.frecuencia_mhz || !eventForm.descripcion) return
  const event = {
    id: `rf-${Date.now()}`,
    fecha: new Date().toISOString(),
    frecuencia_mhz: Number(eventForm.frecuencia_mhz),
    nivel_dbm: Number(eventForm.nivel_dbm),
    lat: systemStore.cursor.lat || -34.8186,
    lon: systemStore.cursor.lon || -58.5358,
    expediente: eventForm.expediente,
    descripcion: eventForm.descripcion,
    notas: '',
  }
  rfEvents.value = addRfEvent(event)
  addLog('Evento RF creado', `${event.frecuencia_mhz} MHz`, event.descripcion)
  eventForm.frecuencia_mhz = 118.0
  eventForm.nivel_dbm = -60
  eventForm.expediente = ''
  eventForm.descripcion = ''
  renderMapLayers()
}

const setTool = (mode) => {
  toolMode.value = mode
  if (mode !== 'measure') {
    measurementPoints.value = []
    measurementResult.value = null
  }
  if (mode !== 'line' && mode !== 'polygon') {
    activePoints.value = []
  }
  if (mode !== 'circle' && mode !== 'radius') {
    activeCircleCenter.value = null
  }
  renderMapLayers()
}

const initMap = () => {
  if (map.value) return

  map.value = L.map('map', { zoomControl: false }).setView([-34.8186, -58.5358], 9)

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map.value)

  L.control.zoom({ position: 'topright' }).addTo(map.value)
  L.control.scale({ position: 'bottomleft', imperial: false, metric: true }).addTo(map.value)

  markerLayer.value = L.layerGroup().addTo(map.value)
  flightLayer.value = L.layerGroup().addTo(map.value)
  userLayer.value = L.layerGroup().addTo(map.value)
  eventLayer.value = L.layerGroup().addTo(map.value)
  heatmapLayer.value = L.layerGroup().addTo(map.value)
  drawLayer.value = L.layerGroup().addTo(map.value)

  map.value.on('mousemove', (event) => {
    systemStore.cursor = { lat: event.latlng.lat, lon: event.latlng.lng }
  })

  map.value.on('click', (event) => handleMapClick(event.latlng))
}

const formatPopup = (title, details) => {
  const lines = Object.entries(details).map(([label, value]) => `<div><strong>${label}:</strong> ${value}</div>`)
  return `<div class="text-sm"><strong>${title}</strong>${lines.join('')}</div>`
}

const selectFeature = (feature, type) => {
  selectedType.value = type
  selectedFeature.value = feature
}

const renderMapLayers = () => {
  if (!map.value) return

  markerLayer.value.clearLayers()
  flightLayer.value.clearLayers()
  userLayer.value.clearLayers()
  eventLayer.value.clearLayers()
  heatmapLayer.value.clearLayers()
  drawLayer.value.clearLayers()

  if (layers.airports) {
    airports.value.forEach((airport) => {
      const marker = L.circleMarker([airport.lat, airport.lon], {
        color: '#38bdf8',
        radius: 8,
        fillOpacity: 0.9,
      }).addTo(markerLayer.value)
      marker.bindPopup(formatPopup(airport.name, {
        ICAO: airport.icao,
        IATA: airport.iata,
        Elevación: `${airport.elev} ft`, 
      }))
      marker.on('click', () => selectFeature({ title: airport.name, details: { ICAO: airport.icao, IATA: airport.iata, Elevación: `${airport.elev} ft`, Lat: airport.lat.toFixed(5), Lon: airport.lon.toFixed(5) } }, 'Aeropuerto'))
    })
  }

  if (layers.fmStations) {
    fmStations.value.forEach((station) => {
      const marker = L.marker([station.lat, station.lon], {
        icon: L.divIcon({ className: 'text-slate-100', html: '📻', iconSize: [24, 24] }),
      }).addTo(markerLayer.value)
      marker.bindPopup(formatPopup(station.name, {
        Frecuencia: `${station.frequency_mhz} MHz`, 
        Potencia: `${station.power_dbm} dBm`, 
        Altura: `${station.height_m} m`, 
      }))
      marker.on('click', () => selectFeature({ title: station.name, details: { Frecuencia: `${station.frequency_mhz} MHz`, Potencia: `${station.power_dbm} dBm`, Lat: station.lat.toFixed(5), Lon: station.lon.toFixed(5) } }, 'FM'))
    })
  }

  if (layers.rfEvents) {
    rfEvents.value.forEach((event) => {
      const marker = L.circleMarker([event.lat, event.lon], {
        color: '#f97316',
        radius: 10,
        fillOpacity: 0.7,
      }).addTo(eventLayer.value)
      marker.bindPopup(formatPopup(`RF ${event.frecuencia_mhz} MHz`, {
        Nivel: `${event.nivel_dbm} dBm`,
        Expediente: event.expediente || 'N/A',
        Descripción: event.descripcion,
      }))
      marker.on('click', () => selectFeature({ title: `Evento RF ${event.frecuencia_mhz} MHz`, details: { Fecha: new Date(event.fecha).toLocaleString(), Nivel: `${event.nivel_dbm} dBm`, Expediente: event.expediente || 'N/A', Descripción: event.descripcion } }, 'Evento RF'))
    })
  }

  if (layers.hotspots) {
    userCircles.value.forEach((circle) => {
      const shape = L.circle([circle.lat, circle.lon], {
        radius: circle.radius || 5000,
        color: '#ef4444',
        fillOpacity: 0.16,
      }).addTo(userLayer.value)
      shape.on('click', () => selectFeature({ title: circle.label || 'Zona radial', details: { Radio: `${circle.radius || 5000} m`, Lat: circle.lat.toFixed(5), Lon: circle.lon.toFixed(5) } }, 'Radio'))
    })
  }

  if (layers.antennas) {
    antennaSites.forEach((antenna) => {
      const marker = L.marker([antenna.lat, antenna.lon], {
        icon: L.divIcon({ className: 'text-slate-100', html: '📡', iconSize: [24, 24] }),
      }).addTo(markerLayer.value)
      marker.bindPopup(formatPopup(antenna.label, {
        Tipo: 'Antena', Lat: antenna.lat.toFixed(5), Lon: antenna.lon.toFixed(5),
      }))
      marker.on('click', () => selectFeature({ title: antenna.label, details: { Tipo: 'Antena', Lat: antenna.lat.toFixed(5), Lon: antenna.lon.toFixed(5) } }, 'Antena'))
    })
  }

  if (layers.expedientes) {
    expedienteMarkers.value.forEach((exp) => {
      const marker = L.circleMarker([exp.lat, exp.lon], {
        color: exp.severidad === 'crítica' ? '#dc2626' : '#22c55e',
        radius: 9,
        fillOpacity: 0.85,
      }).addTo(markerLayer.value)
      marker.bindPopup(formatPopup(exp.numero_expediente, {
        Aeropuerto: exp.aeropuerto,
        Frecuencia: `${exp.freq_mhz?.toFixed(3) || 'N/A'} MHz`,
        Estado: exp.estado,
      }))
      marker.on('click', () => selectFeature({ title: exp.numero_expediente, details: { Aeropuerto: exp.aeropuerto, Frecuencia: `${exp.freq_mhz?.toFixed(3) || 'N/A'} MHz`, Estado: exp.estado, Lat: exp.lat.toFixed(5), Lon: exp.lon.toFixed(5) } }, 'Expediente'))
    })
  }

  if (layers.flights) {
    flightsStore.routes.forEach((flight) => {
      const path = normalizeFlightPath(flight.path)
      if (path.length < 2) return
      const line = L.polyline(path, { color: '#a855f7', weight: 4, opacity: 0.9 }).addTo(flightLayer.value)
      line.bindPopup(formatPopup(flight.callsign, {
        Origen: `${flight.origin}`,
        Destino: `${flight.destination}`,
        Estado: flight.status,
      }))
      line.on('click', () => {
        selectFeature({
          title: flight.callsign,
          details: {
            Origen: flight.origin,
            Destino: flight.destination,
            Estado: flight.status,
            'Salida': flight.departure_time ? new Date(flight.departure_time).toLocaleString() : 'N/A',
            'Llegada': flight.arrival_time ? new Date(flight.arrival_time).toLocaleString() : 'N/A',
          },
        }, 'Vuelo')
        zoomToFlight(flight)
      })
    })
  }

  if (layers.userMarkers) {
    userMarkers.value.forEach((markerData) => {
      const marker = L.marker([markerData.lat, markerData.lon]).addTo(userLayer.value)
      marker.bindPopup(formatPopup(markerData.label || 'Marcador', {
        Tipo: markerData.type,
        Lat: markerData.lat.toFixed(5),
        Lon: markerData.lon.toFixed(5),
      }))
      marker.on('click', () => selectFeature({ title: markerData.label || 'Marcador', details: { Tipo: markerData.type, Lat: markerData.lat.toFixed(5), Lon: markerData.lon.toFixed(5) } }, 'Marcador'))
    })
    userLines.value.forEach((shape) => {
      const polyline = L.polyline(shape.path, { color: '#10b981', weight: 3, dashArray: '6,4' }).addTo(userLayer.value)
      polyline.on('click', () => selectFeature({ title: shape.label || 'Línea', details: { Puntos: shape.path.length, Tipo: 'Línea' } }, 'Línea'))
    })
    userPolygons.value.forEach((shape) => {
      const polygon = L.polygon(shape.path, { color: '#818cf8', weight: 3, fillOpacity: 0.12 }).addTo(userLayer.value)
      polygon.on('click', () => selectFeature({ title: shape.label || 'Polígono', details: { Puntos: shape.path.length, Tipo: 'Polígono' } }, 'Polígono'))
    })
    userCircles.value.forEach((circle) => {
      const circleLayer = L.circle([circle.lat, circle.lon], { radius: circle.radius || 5000, color: '#f59e0b', fillOpacity: 0.14 }).addTo(userLayer.value)
      circleLayer.on('click', () => selectFeature({ title: circle.label || 'Círculo', details: { Radio: `${circle.radius || 5000} m` } }, 'Círculo'))
    })
  }

  if (measurementResult.value && measurementResult.value.points.length === 2) {
    const [a, b] = measurementResult.value.points
    L.polyline([a, b], { color: '#38bdf8', weight: 2, dashArray: '8,4' }).addTo(drawLayer.value)
    L.circleMarker(a, { radius: 6, color: '#38bdf8', fillOpacity: 1 }).addTo(drawLayer.value)
    L.circleMarker(b, { radius: 6, color: '#38bdf8', fillOpacity: 1 }).addTo(drawLayer.value)
  }

  if (toolMode.value === 'line' && activePoints.value.length > 0) {
    L.polyline(activePoints.value, { color: '#38bdf8', weight: 3, dashArray: '6,4' }).addTo(drawLayer.value)
    activePoints.value.forEach((coord) => L.circleMarker(coord, { radius: 5, color: '#38bdf8' }).addTo(drawLayer.value))
  }

  if (toolMode.value === 'polygon' && activePoints.value.length > 0) {
    if (activePoints.value.length >= 3) {
      L.polygon(activePoints.value, { color: '#8b5cf6', weight: 2, fillOpacity: 0.08 }).addTo(drawLayer.value)
    }
    activePoints.value.forEach((coord) => L.circleMarker(coord, { radius: 5, color: '#8b5cf6' }).addTo(drawLayer.value))
  }

  if ((toolMode.value === 'circle' || toolMode.value === 'radius') && activeCircleCenter.value) {
    const radiusMeters = activeRadiusUnit.value === 'nm' ? activeCircleRadius.value * 1852 : activeCircleRadius.value * 1000
    L.circle(activeCircleCenter.value, { radius: radiusMeters, color: '#f97316', fillOpacity: 0.08 }).addTo(drawLayer.value)
    L.circleMarker(activeCircleCenter.value, { radius: 6, color: '#f97316', fillOpacity: 1 }).addTo(drawLayer.value)
  }
  if (map.value && map.value.invalidateSize) {
    map.value.invalidateSize()
  }
}

const normalizeFlightPath = (path) => {
  if (!Array.isArray(path)) return []
  return path.map((coord) => {
    if (!Array.isArray(coord) || coord.length < 2) return null
    const lat = Number(coord[0])
    const lon = Number(coord[1])
    return Number.isFinite(lat) && Number.isFinite(lon) ? [lat, lon] : null
  }).filter(Boolean)
}

const zoomToFlight = (flight) => {
  if (!map.value || !flight?.path) return
  const bounds = normalizeFlightPath(flight.path)
  if (bounds.length > 0) {
    map.value.fitBounds(bounds, { padding: [40, 40] })
  }
}

const handleMapClick = (latlng) => {
  if (toolMode.value === 'point') {
    const marker = {
      id: `marker-${Date.now()}`,
      type: 'marker',
      label: `Ubicación ${latlng.lat.toFixed(4)}, ${latlng.lng.toFixed(4)}`,
      lat: latlng.lat,
      lon: latlng.lng,
    }
    pointsList.value = addPoint(marker)
    addLog('Marcador agregado', marker.label, `Lat ${marker.lat.toFixed(5)}, Lon ${marker.lon.toFixed(5)}`)
    renderMapLayers()
    return
  }

  if (toolMode.value === 'line' || toolMode.value === 'polygon') {
    activePoints.value.push([latlng.lat, latlng.lng])
    addLog('Punto de dibujo agregado', `${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`, `Total: ${activePoints.value.length}`)
    renderMapLayers()
    return
  }

  if (toolMode.value === 'circle' || toolMode.value === 'radius') {
    activeCircleCenter.value = [latlng.lat, latlng.lng]
    addLog('Centro de círculo marcado', `${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`, `Radio: ${activeCircleRadius.value} ${activeRadiusUnit.value}`)
    renderMapLayers()
    return
  }

  if (toolMode.value === 'measure') {
    measurementPoints.value.push([latlng.lat, latlng.lng])
    if (measurementPoints.value.length === 2) {
      const [a, b] = measurementPoints.value
      const distance_km = getHaversineDistance(a, b)
      measurementResult.value = {
        points: [a, b],
        distance_km,
        distance_nm: distance_km / 1.852,
        distance_mi: distance_km * 0.621371,
        bearing: getBearing(a, b),
      }
      addLog('Medición completada', `Distancia ${measurementResult.value.distance_km.toFixed(2)} km`, `Bearing ${measurementResult.value.bearing.toFixed(1)}°`)
    }
    renderMapLayers()
    return
  }

  if (toolMode.value === 'event') {
    eventForm.lat = latlng.lat
    eventForm.lon = latlng.lng
    createRfEvent()
    return
  }
}

const getHaversineDistance = ([lat1, lon1], [lat2, lon2]) => {
  const R = 6371
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLon = (lon2 - lon1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return R * c
}

const getBearing = ([lat1, lon1], [lat2, lon2]) => {
  const φ1 = lat1 * Math.PI / 180
  const φ2 = lat2 * Math.PI / 180
  const Δλ = (lon2 - lon1) * Math.PI / 180
  const y = Math.sin(Δλ) * Math.cos(φ2)
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ)
  const θ = Math.atan2(y, x)
  return (θ * 180 / Math.PI + 360) % 360
}

const commitShape = () => {
  if (toolMode.value === 'line' && activePoints.value.length >= 2) {
    const line = {
      id: `line-${Date.now()}`,
      type: 'line',
      label: `Línea ${new Date().toLocaleTimeString()}`,
      path: [...activePoints.value],
    }
    pointsList.value = addPoint(line)
    activePoints.value = []
    addLog('Línea guardada', line.label, `Puntos: ${line.path.length}`)
    renderMapLayers()
    return
  }
  if (toolMode.value === 'polygon' && activePoints.value.length >= 3) {
    const polygon = {
      id: `polygon-${Date.now()}`,
      type: 'polygon',
      label: `Polígono ${new Date().toLocaleTimeString()}`,
      path: [...activePoints.value],
    }
    pointsList.value = addPoint(polygon)
    activePoints.value = []
    addLog('Polígono guardado', polygon.label, `Puntos: ${polygon.path.length}`)
    renderMapLayers()
    return
  }
}

const commitCircle = () => {
  if (!activeCircleCenter.value) return
  const radiusMeters = activeRadiusUnit.value === 'nm' ? activeCircleRadius.value * 1852 : activeCircleRadius.value * 1000
  const circle = {
    id: `circle-${Date.now()}`,
    type: 'circle',
    label: `Radio ${activeCircleRadius.value}${activeRadiusUnit.value}`,
    lat: activeCircleCenter.value[0],
    lon: activeCircleCenter.value[1],
    radius: radiusMeters,
  }
  pointsList.value = addPoint(circle)
  activeCircleCenter.value = null
  addLog('Círculo guardado', circle.label, `Radio ${radiusMeters.toFixed(0)} m`)
  renderMapLayers()
}

const clearMeasurement = () => {
  measurementPoints.value = []
  measurementResult.value = null
  addLog('Medición borrada', 'Regla reiniciada', '')
  renderMapLayers()
}

const clearUserData = () => {
  const preserved = loadPoints().filter((item) => !['marker', 'line', 'polygon', 'circle', 'measurement', 'hotspot'].includes(item.type))
  savePoints(preserved)
  pointsList.value = preserved
  addLog('Datos de usuario borrados', 'Se eliminaron pines, líneas, polígonos y mediciones', '')
  renderMapLayers()
}

const resetMapView = () => {
  if (!map.value) return
  const bounds = []
  airports.value.forEach((airport) => bounds.push([airport.lat, airport.lon]))
  fmStations.value.forEach((station) => bounds.push([station.lat, station.lon]))
  pointsList.value.forEach((point) => {
    if (point.type === 'marker' || point.type === 'circle') bounds.push([point.lat, point.lon])
    if (point.type === 'line' || point.type === 'polygon') point.path.forEach((coord) => bounds.push(coord))
  })
  rfEvents.value.forEach((event) => bounds.push([event.lat, event.lon]))
  flightsStore.routes.forEach((flight) => normalizeFlightPath(flight.path).forEach((coord) => bounds.push(coord)))
  if (bounds.length > 0) map.value.fitBounds(bounds, { padding: [50, 50] })
}

const searchFlights = async () => {
  try {
    await flightsStore.searchFlights({
      origin: flightSearch.origin,
      destination: flightSearch.destination,
      callsign: flightSearch.callsign,
      source: flightSearch.source,
    })
    addLog('Búsqueda de vuelos', 'Ruta actualizada', `${flightsStore.routes.length} vuelos cargados`)
    renderMapLayers()
  } catch (err) {
    addLog('Error de vuelos', err.message || 'Error desconocido', '')
  }
}

const loadSampleFlights = async () => {
  flightSearch.origin = ''
  flightSearch.destination = ''
  flightSearch.callsign = ''
  flightSearch.source = 'sample'
  await searchFlights()
}

const refreshOpenSky = async () => {
  try {
    await flightsStore.searchFlights({
      origin: flightSearch.origin,
      destination: flightSearch.destination,
      callsign: flightSearch.callsign,
      source: 'opensky',
    })
    addLog('OpenSky actualizado', 'Vuelos en tiempo real recargados', `${flightsStore.routes.length} rutas`)
    renderMapLayers()
  } catch (err) {
    addLog('OpenSky fallo', err.message || 'No se pudo actualizar', '')
  }
}

const loadData = () => {
  airports.value = loadAirports()
  fmStations.value = loadFMStations()
  pointsList.value = loadPoints()
  rfEvents.value = loadRfEvents()
}

const expedienteMarkers = computed(() => (expedientesStore.expedientes || []).filter((exp) => exp.lat != null && exp.lon != null))

watch([() => layers, () => flightsStore.routes.length, pointsList, rfEvents], renderMapLayers, { deep: true })

onMounted(async () => {
  await nextTick()
  initMap()
  loadData()
  await searchFlights()
  renderMapLayers()
  if (map.value && map.value.invalidateSize) {
    map.value.invalidateSize()
  }
})

const buttonClass = (active) => {
  return [
    'rounded-2xl px-3 py-2 text-xs font-semibold transition-colors',
    active ? 'bg-primary text-slate-950' : 'bg-slate-800 text-slate-200 hover:bg-slate-700',
  ]
}
</script>

<style scoped>
#map {
  min-height: 100%;
  height: 100%;
}
</style>
