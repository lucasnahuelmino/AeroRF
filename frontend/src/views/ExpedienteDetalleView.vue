<template>
  <div class="page-doc">
    <div class="flex items-center gap-4 mb-6">
      <button
        @click="$router.back()"
        class="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
      >
        ← Volver
      </button>
      <h1 class="page-doc-title">Expediente {{ expediente?.numero_expediente }}</h1>
    </div>

    <div v-if="!expediente" class="text-center text-gray-400 py-12">Cargando...</div>
    <div v-else class="space-y-6">
      <!-- Info básica -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <h2 class="text-lg font-semibold mb-4">Información General</h2>
          <div class="space-y-2 text-sm">
            <div><span class="text-gray-400">Número:</span> {{ expediente.numero_expediente }}</div>
            <div><span class="text-gray-400">Frecuencia:</span> <span class="font-mono text-primary">{{ expediente.freq_mhz }} MHz</span></div>
            <div><span class="text-gray-400">Aeropuerto:</span> {{ expediente.aeropuerto }}</div>
            <div><span class="text-gray-400">Estado:</span> <span :class="statusClass(expediente.estado)">{{ expediente.estado }}</span></div>
            <div><span class="text-gray-400">Severidad:</span> {{ expediente.severidad }}</div>
          </div>
        </div>

        <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <h2 class="text-lg font-semibold mb-4">Coordenadas</h2>
          <div class="space-y-2 text-sm">
            <div><span class="text-gray-400">Latitud:</span> {{ expediente.lat }}</div>
            <div><span class="text-gray-400">Longitud:</span> {{ expediente.lon }}</div>
            <button class="mt-4 px-3 py-1 bg-primary hover:bg-blue-600 rounded text-sm transition-colors">
              📍 Ver en mapa
            </button>
          </div>
        </div>
      </div>

      <!-- Cálculos RF -->
      <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
        <h2 class="text-lg font-semibold mb-4">🧮 Análisis RF</h2>
        <div class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <input
              v-model="rfForm.freq_mhz"
              type="number"
              placeholder="Frecuencia (MHz)"
              step="0.001"
              class="px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:border-primary"
            />
            <input
              v-model="rfForm.tolerance_khz"
              type="number"
              placeholder="Tolerancia (kHz)"
              step="0.1"
              class="px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:border-primary"
            />
          </div>
          <button
            @click="calculateRF"
            :disabled="rfStore.loading"
            class="px-4 py-2 bg-primary hover:bg-blue-600 disabled:bg-gray-600 rounded-lg font-semibold transition-colors"
          >
            {{ rfStore.loading ? 'Calculando...' : 'Calcular' }}
          </button>

          <!-- Resultados -->
          <div v-if="rfStore.results.length > 0" class="mt-4">
            <h3 class="font-semibold mb-2">Resultados:</h3>
            <div class="space-y-2 max-h-64 overflow-y-auto">
              <div
                v-for="(result, idx) in rfStore.results"
                :key="idx"
                class="p-3 bg-gray-700 rounded text-sm"
              >
                <div class="font-mono text-primary">{{ result.formula }}</div>
                <div class="text-gray-400">Tipo: <span class="text-white">{{ result.tipo }}</span> | Error: <span class="text-warning">{{ result.error_khz }} kHz</span></div>
                <div class="text-right font-semibold text-success">Score: {{ result.score }}%</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Observaciones -->
      <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
        <h2 class="text-lg font-semibold mb-4">Observaciones</h2>
        <textarea
          v-model="expediente.observaciones"
          rows="4"
          class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:border-primary"
        ></textarea>
        <button
          @click="updateExpediente"
          class="mt-3 px-4 py-2 bg-primary hover:bg-blue-600 rounded-lg font-semibold transition-colors"
        >
          Guardar
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useRFStore } from '../stores/rf'
import { useExpedientesStore } from '../stores/expedientes'

const route = useRoute()
const rfStore = useRFStore()
const expedientesStore = useExpedientesStore()

const expediente = ref(null)
const rfForm = ref({
  freq_mhz: '',
  tolerance_khz: 10,
})

const statusClass = (status) => {
  const classes = {
    abierto: 'text-blue-300',
    investigacion: 'text-yellow-300',
    resuelto: 'text-green-300',
    cerrado: 'text-gray-300',
  }
  return classes[status] || classes.abierto
}

const calculateRF = async () => {
  try {
    await rfStore.calculateRF({
      target_mhz: parseFloat(expediente.value.freq_mhz),
      tolerance_khz: parseFloat(rfForm.value.tolerance_khz),
      frequencies: [
        {
          freq_mhz: parseFloat(rfForm.value.freq_mhz),
          signal_type: 'UNKNOWN',
        },
      ],
    })
  } catch (err) {
    alert('Error en cálculo: ' + err.message)
  }
}

const updateExpediente = async () => {
  try {
    await expedientesStore.updateExpediente(expediente.value.id, expediente.value)
    alert('Expediente actualizado')
  } catch (err) {
    alert('Error actualizando: ' + err.message)
  }
}

onMounted(async () => {
  const id = route.params.id
  try {
    const response = await fetch(`/api/v1/expedientes/${id}`)
    if (!response.ok) throw new Error('No encontrado')
    expediente.value = await response.json()
  } catch (err) {
    alert('Error cargando expediente')
  }
})
</script>
