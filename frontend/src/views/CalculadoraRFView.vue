<template>
  <div class="page-doc">
    <div class="mb-6">
      <h1 class="page-doc-title">🧮 Calculadora RF</h1>
      <p class="page-doc-sub">Motor de análisis de frecuencias, armónicas e intermodulación</p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
      <!-- Panel control -->
      <div class="lg:col-span-1 space-y-4">
        <!-- Parámetros objetivo -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <h3 class="text-lg font-semibold mb-4 text-slate-100">⚙️ Parámetros</h3>
          <div class="space-y-4">
            <div>
              <label class="block text-sm text-slate-400 mb-2">Frecuencia Objetivo (MHz)</label>
              <input
                v-model.number="form.target_mhz"
                type="number"
                step="0.001"
                class="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-blue-500 font-mono"
              />
            </div>
            <div>
              <label class="block text-sm text-slate-400 mb-2">Tolerancia (kHz)</label>
              <input
                v-model.number="form.tolerance_khz"
                type="number"
                step="0.1"
                class="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-blue-500 font-mono"
              />
            </div>
            <button
              @click="calculate"
              :disabled="rfStore.loading"
              class="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 rounded-lg font-semibold transition-colors text-white"
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
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <h3 class="text-lg font-semibold mb-3 text-slate-100">📡 Frecuencias ({{ form.frequencies.length }})</h3>
          <div class="space-y-2 max-h-48 overflow-y-auto">
            <div
              v-for="(freq, idx) in form.frequencies"
              :key="idx"
              class="p-3 bg-slate-950 border border-slate-800 rounded-lg flex justify-between items-center text-sm text-slate-200"
            >
              <div class="font-mono flex-1">
                <div>{{ freq.freq_mhz }} MHz</div>
                <div class="text-xs text-slate-500">{{ freq.signal_type }} · {{ freq.label }}</div>
              </div>
              <button
                @click="removeFrequency(idx)"
                class="text-red-400 hover:text-red-300 transition ml-2"
              >
                ✕
              </button>
            </div>
            <div v-if="form.frequencies.length === 0" class="text-slate-500 text-sm text-center py-4">
              Sin frecuencias agregadas
            </div>
          </div>
        </div>
      </div>

      <!-- Panel resultados -->
      <div class="lg:col-span-3 space-y-6">
        <!-- Tabla de resultados -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <h3 class="text-lg font-semibold mb-4 text-slate-100">📊 Resultados Ranked</h3>
          
          <div v-if="rfStore.results.length === 0" class="text-slate-400 text-center py-8">
            Ejecuta un cálculo para ver resultados
          </div>

          <div v-else class="space-y-2 max-h-96 overflow-y-auto">
            <div
              v-for="result in rfStore.results"
              :key="result.id"
              @click="selectResult(result)"
              :class="[
                'p-4 rounded-lg border-2 cursor-pointer transition-all',
                selectedResult?.id === result.id
                  ? 'border-blue-500 bg-blue-900/20'
                  : 'border-slate-800 bg-slate-950 hover:border-slate-700'
              ]"
            >
              <div class="flex justify-between items-start mb-2">
                <div>
                  <div class="font-semibold text-slate-100">{{ result.formula }}</div>
                  <div class="text-xs text-slate-500">{{ result.tipo }}</div>
                </div>
                <div class="text-right">
                  <div class="text-2xl font-bold text-green-400">{{ result.score }}%</div>
                  <div class="text-xs text-slate-400">Score</div>
                </div>
              </div>
              <div class="grid grid-cols-3 gap-2 text-sm">
                <div class="bg-slate-800 rounded px-2 py-1">
                  <div class="text-slate-400">Resultado</div>
                  <div class="font-mono text-slate-100">{{ ((result.result_mhz ?? result.resultado) || 0).toFixed(6) }} MHz</div>
                </div>
                <div class="bg-slate-800 rounded px-2 py-1">
                  <div class="text-slate-400">Error</div>
                  <div class="font-mono" :class="((result.error_khz ?? 0) < 5) ? 'text-green-400' : 'text-orange-400'">
                    {{ ((result.error_khz ?? 0)).toFixed(3) }} kHz
                  </div>
                </div>
                <div class="bg-slate-800 rounded px-2 py-1">
                  <div class="text-slate-400">Proximidad</div>
                  <div class="font-mono text-slate-100">{{ Math.round(((result.proximity ?? result.score_breakdown?.proximity ?? 0) * 100)) }}%</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Análisis detallado -->
        <div v-if="selectedResult" class="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <h3 class="text-lg font-semibold mb-4 text-slate-100">🔍 Análisis Detallado</h3>
          
          <div class="grid grid-cols-2 gap-4 mb-6">
            <div class="p-4 bg-slate-950 border border-slate-800 rounded-lg">
              <div class="text-sm text-slate-400 mb-2">Fórmula Matemática</div>
              <div class="font-mono text-lg text-blue-400 font-bold break-all">{{ selectedResult.formula }}</div>
            </div>
            <div class="p-4 bg-slate-950 border border-slate-800 rounded-lg">
              <div class="text-sm text-slate-400 mb-2">Tipo de Interferencia</div>
              <div class="text-lg font-bold text-orange-400">{{ selectedResult.tipo }}</div>
            </div>
            <div class="p-4 bg-slate-950 border border-slate-800 rounded-lg">
              <div class="text-sm text-slate-400 mb-2">Frecuencia Calculada</div>
              <div class="font-mono text-xl text-green-400 font-bold">{{ ((selectedResult.result_mhz ?? selectedResult.resultado) || 0).toFixed(6) }} MHz</div>
            </div>
            <div class="p-4 bg-slate-950 border border-slate-800 rounded-lg">
              <div class="text-sm text-slate-400 mb-2">Error respecto al Objetivo</div>
              <div class="font-mono text-xl font-bold" :class="((selectedResult.error_khz ?? 0) < 5) ? 'text-green-400' : 'text-red-400'">
                {{ ((selectedResult.error_khz ?? 0)).toFixed(3) }} kHz
              </div>
            </div>
          </div>

          <button
            @click="storeResult"
            class="w-full px-4 py-3 bg-green-600 hover:bg-green-700 rounded-lg font-semibold transition-colors text-white"
          >
            💾 Guardar en Expediente
          </button>
        </div>
      </div>
    </div>

    <!-- Histograma -->
    <div v-if="rfStore.results.length > 0" class="bg-slate-900 border border-slate-800 rounded-2xl p-6">
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
import Chart from '../components/Chart.vue'

const rfStore = useRFStore()
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
  alert('Resultado guardado (próximamente integrado con expediente)')
}

onMounted(() => {
  calculate()
})
</script>
