<template>
  <div id="app" class="min-h-screen bg-slate-950 text-slate-100">
    <header class="bg-slate-950 border-b border-slate-800 sticky top-0 z-50 shadow-sm">
      <!-- Fila superior: Logo e información del sistema -->
      <div class="max-w-8xl mx-auto px-4 sm:px-6 lg:px-8 py-2 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div class="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-4">
          <div class="flex items-center gap-3">
            <img :src="logo" alt="AeroRF" class="h-10 w-auto rounded-md" />
            <div>
              <div class="text-lg font-semibold tracking-wide text-primary">AeroRF</div>
              <div class="text-xs text-slate-400">Centro operativo RF-Aeronáutico</div>
            </div>
          </div>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] text-slate-300">
          <div class="rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2">
            <div class="text-slate-500 uppercase">Backend</div>
            <div class="font-semibold">{{ backendStatus }}</div>
          </div>
          <div class="rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2">
            <div class="text-slate-500 uppercase">OpenSky</div>
            <div class="font-semibold">{{ openSkyStatus }}</div>
          </div>
          <div class="rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2">
            <div class="text-slate-500 uppercase">Vuelos cargados</div>
            <div class="font-semibold">{{ flightsLoaded }}</div>
          </div>
          <div class="rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2">
            <div class="text-slate-500 uppercase">Cursor</div>
            <div class="font-semibold">{{ cursorText }}</div>
          </div>
        </div>
      </div>

      <!-- Fila de navegación -->
      <nav class="max-w-8xl mx-auto px-4 sm:px-6 lg:px-8 border-t border-slate-800">
        <div class="flex flex-wrap gap-1 py-2 overflow-x-auto">
          <router-link 
            v-for="item in navItems" 
            :key="item.path"
            :to="item.path"
            :class="[
              'px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap',
              isActive(item.path)
                ? 'bg-blue-600/20 text-blue-300 border border-blue-500'
                : 'text-slate-400 hover:text-slate-200 border border-transparent hover:border-slate-700'
            ]"
          >
            {{ item.label }}
          </router-link>
        </div>
      </nav>
    </header>

    <main class="min-h-[calc(100vh-120px)] bg-slate-950 px-2 py-2">
      <div class="max-w-8xl mx-auto h-full">
        <div class="h-full">
          <router-view />
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import logo from './assets/aerorf.png'
import { useRoute } from 'vue-router'
import { useFlightsStore } from './stores/flights'
import { useSystemStore } from './stores/system'

const route = useRoute()
const flightsStore = useFlightsStore()
const systemStore = useSystemStore()

const backendStatus = computed(() => systemStore.backendStatus)
const openSkyStatus = computed(() => systemStore.openSkyStatus)
const flightsLoaded = computed(() => flightsStore.routes.length)
const cursorText = computed(() => {
  const { lat, lon } = systemStore.cursor
  return lat != null && lon != null ? `${lat.toFixed(5)}, ${lon.toFixed(5)}` : 'n/a'
})

const navItems = [
  { path: '/', label: 'Dashboard' },
  { path: '/expedientes', label: 'Expedientes' },
  { path: '/calculadora', label: 'Calculadora RF' },
  { path: '/mapas', label: 'Mapas' },
  { path: '/espectro', label: 'Espectro' },
]

const isActive = (path) => route.path === path || route.path.startsWith(path + '/')

const refreshSystemStatus = async () => {
  const backendBase = 'http://localhost:8000'
  try {
    const response = await fetch(`${backendBase}/health`)
    if (!response.ok) throw new Error('offline')
    const data = await response.json()
    systemStore.backendStatus = data.status || 'ok'
  } catch (err) {
    systemStore.backendStatus = 'desconectado'
  }

  try {
    const response = await fetch(`${backendBase}/api/v1/flights/search?source=opensky`)
    systemStore.openSkyStatus = response.ok ? 'conectado' : 'fallo'
  } catch (err) {
    systemStore.openSkyStatus = 'fallo'
  }
}

onMounted(refreshSystemStatus)
</script>

<style scoped>
</style>
