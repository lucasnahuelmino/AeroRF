<template>
  <div class="space-y-6">
    <h1 class="text-3xl font-bold">🧮 Calculadora RF - Motor de Análisis</h1>

    <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
      <!-- Panel control -->
      <div class="lg:col-span-1 space-y-4">
        <!-- Parámetros objetivo -->
        <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <h3 class="text-lg font-semibold mb-4">⚙️ Parámetros</h3>
          <div class="space-y-4">
            <div>
              <label class="block text-sm text-gray-400 mb-1">Frecuencia Objetivo (MHz)</label>
              <input
                v-model.number="form.target_mhz"
                type="number"
                step="0.001"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 focus:outline-none focus:border-primary font-mono"
              />
            </div>
            <div>
              <label class="block text-sm text-gray-400 mb-1">Tolerancia (kHz)</label>
              <input
                v-model.number="form.tolerance_khz"
                type="number"
                step="0.1"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 focus:outline-none focus:border-primary font-mono"
              />
            </div>
            <button
              @click="calculate"
              :disabled="rfStore.loading"
              class="w-full px-4 py-2 bg-primary hover:bg-blue-600 disabled:bg-gray-600 rounded-lg font-semibold transition-colors"
            >
              {{ rfStore.loading ? '⏳ Calculando...' : '🚀 Calcular' }}
            </button>
          </div>
        </div>

        <!-- Agregar frecuencias -->
        <FrequencyInput
          title="Agregar Frecuencia"
          @submit="addFrequency"
        />

        <!-- Lista de frecuencias -->
        <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <h3 class="text-lg font-semibold mb-3">📡 Frecuencias ({{ form.frequencies.length }})</h3>
          <div class="space-y-2 max-h-48 overflow-y-auto">
            <div
              v-for="(freq, idx) in form.frequencies"
              :key="idx"
              class="p-2 bg-gray-700 rounded flex justify-between items-center text-sm"
            >
              <div class="font-mono">{{ freq.freq_mhz }} MHz</div>
              <button
                @click="removeFrequency(idx)"
                class="text-red-400 hover:text-red-300"
              >
                ✕
              </button>
            </div>
            <div v-if="form.frequencies.length === 0" class="text-gray-500 text-sm text-center py-2">
              Sin frecuencias
            </div>
          </div>
        </div>
      </div>

      <!-- Panel resultados -->
      <div class="lg:col-span-3">
        <RankingTable
          title="📊 Resultados Ranked (ordenados por score)"
          :results="rfStore.results"
          @select="selectResult"
        />

        <!-- Análisis detallado -->
        <div v-if="selectedResult" class="mt-6 bg-gray-800 border border-gray-700 rounded-lg p-6">
          <h3 class="text-lg font-semibold mb-4">🔍 Análisis Detallado</h3>
          <div class="grid grid-cols-2 gap-4 mb-4">
            <div class="p-3 bg-gray-700 rounded">
              <div class="text-sm text-gray-400">Fórmula</div>
              <div class="font-mono text-lg text-primary font-bold">{{ selectedResult.formula }}</div>
            </div>
            <div class="p-3 bg-gray-700 rounded">
              <div class="text-sm text-gray-400">Tipo</div>
              <div class="text-lg font-bold text-warning">{{ selectedResult.tipo }}</div>
            </div>
            <div class="p-3 bg-gray-700 rounded">
              <div class="text-sm text-gray-400">Resultado</div>
              <div class="font-mono text-lg text-success">{{ selectedResult.resultado?.toFixed(6) }} MHz</div>
            </div>
            <div class="p-3 bg-gray-700 rounded">
              <div class="text-sm text-gray-400">Error</div>
              <div class="text-lg" :class="selectedResult.error_khz < 5 ? 'text-success' : 'text-warning'">
                {{ selectedResult.error_khz?.toFixed(3) }} kHz
              </div>
            </div>
            <div class="p-3 bg-gray-700 rounded">
              <div class="text-sm text-gray-400">Score</div>
              <div class="text-3xl font-bold text-success">{{ selectedResult.score }}%</div>
            </div>
            <div class="p-3 bg-gray-700 rounded">
              <div class="text-sm text-gray-400">Proximidad</div>
              <div class="text-lg font-bold">{{ (selectedResult.proximity * 100).toFixed(0) }}%</div>
            </div>
          </div>
          <button
            @click="storeResult"
            class="w-full px-4 py-2 bg-success hover:bg-green-600 rounded-lg font-semibold transition-colors"
          >
            💾 Guardar en Expediente
          </button>
        </div>
      </div>
    </div>

    <!-- Histograma -->
    <div v-if="rfStore.results.length > 0">
      <Chart
        title="Distribución de Scores"
        type="bar"
        :data="rfStore.results.map(r => ({ label: r.formula, value: r.score }))"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRFStore } from '../stores/rf'
import FrequencyInput from '../components/FrequencyInput.vue'
import RankingTable from '../components/RankingTable.vue'
import Chart from '../components/Chart.vue'

const rfStore = useRFStore()
const frequencyInputRef = ref(null)
const selectedResult = ref(null)

const form = ref({
  target_mhz: 119.0,
  tolerance_khz: 10,
  frequencies: [
    { freq_mhz: 88.5, signal_type: 'FM', label: 'FM Radio' },
    { freq_mhz: 58.0, signal_type: 'TV_UHF', label: 'TV Señal' },
  ],
})

const addFrequency = async (data) => {
  form.value.frequencies.push({
    freq_mhz: data.freq_mhz,
    signal_type: data.signal_type,
    label: data.label,
    power_dbm: data.power_dbm,
  })
}

const removeFrequency = (idx) => {
  form.value.frequencies.splice(idx, 1)
}

const calculate = async () => {
  try {
    await rfStore.calculateRF({
      target_mhz: form.value.target_mhz,
      tolerance_khz: form.value.tolerance_khz,
      frequencies: form.value.frequencies.filter((f) => f.freq_mhz),
    })
    selectedResult.value = rfStore.results[0] || null
  } catch (err) {
    alert('Error: ' + err.message)
  }
}

const selectResult = (result) => {
  selectedResult.value = result
}

const storeResult = () => {
  // TODO: Integrar con expediente actual
  alert('Resultado guardado (próximamente integrado con expediente)')
}

onMounted(() => {
  // Cálculo inicial automático
  calculate()
})
</script>
