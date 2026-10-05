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
        <div class="bg-panel border border-borde rounded-2xl p-6">
          <h3 class="text-lg font-semibold mb-4 text-texto">⚙️ Parámetros</h3>
          <div class="space-y-4">
            <div>
              <label class="block text-sm text-texto-tenue mb-2">Frecuencia Objetivo (MHz)</label>
              <input
                v-model.number="form.target_mhz"
                type="number"
                step="0.001"
                class="w-full px-3 py-2 bg-panel-hondo border border-borde rounded-lg text-texto focus:outline-none focus:border-blue-500 font-mono"
              />
            </div>
            <div>
              <label class="block text-sm text-texto-tenue mb-2">Tolerancia (kHz)</label>
              <input
                v-model.number="form.tolerance_khz"
                type="number"
                step="0.1"
                class="w-full px-3 py-2 bg-panel-hondo border border-borde rounded-lg text-texto focus:outline-none focus:border-blue-500 font-mono"
              />
            </div>
            <button
              @click="calculate"
              :disabled="rfStore.loading"
              class="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-panel-alto rounded-lg font-semibold transition-colors text-white"
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
        <div class="bg-panel border border-borde rounded-2xl p-6">
          <h3 class="text-lg font-semibold mb-3 text-texto">📡 Frecuencias ({{ form.frequencies.length }})</h3>
          <div class="space-y-2 max-h-48 overflow-y-auto">
            <div
              v-for="(freq, idx) in form.frequencies"
              :key="idx"
              class="p-3 bg-panel-hondo border border-borde rounded-lg flex justify-between items-center text-sm text-texto"
            >
              <div class="font-mono flex-1">
                <div>{{ freq.freq_mhz }} MHz</div>
                <div class="text-xs text-texto-tenue">{{ freq.signal_type }} · {{ freq.label }}</div>
              </div>
              <button
                @click="removeFrequency(idx)"
                class="text-red-400 hover:text-red-300 transition ml-2"
              >
                ✕
              </button>
            </div>
            <div v-if="form.frequencies.length === 0" class="text-texto-tenue text-sm text-center py-4">
              Sin frecuencias agregadas
            </div>
          </div>
        </div>
      </div>

      <!-- Panel resultados -->
      <div class="lg:col-span-3 space-y-6">
        <!-- Tabla de resultados -->
        <div class="bg-panel border border-borde rounded-2xl p-6">
          <h3 class="text-lg font-semibold mb-4 text-texto">📊 Resultados Ranked</h3>
          
          <div v-if="rfStore.results.length === 0" class="text-texto-tenue text-center py-8">
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
                  : 'border-borde bg-panel-hondo hover:border-borde-fuerte'
              ]"
            >
              <div class="flex justify-between items-start mb-2">
                <div>
                  <div class="font-semibold text-texto">{{ result.formula }}</div>
                  <div class="text-xs text-texto-tenue">{{ result.tipo }}</div>
                </div>
                <div class="text-right">
                  <div class="text-2xl font-bold text-green-400">{{ result.score }}%</div>
                  <div class="text-xs text-texto-tenue">Score</div>
                </div>
              </div>
              <div class="grid grid-cols-3 gap-2 text-sm">
                <div class="bg-panel-alto rounded px-2 py-1">
                  <div class="text-texto-tenue">Resultado</div>
                  <div class="font-mono text-texto">{{ ((result.result_mhz ?? result.resultado) || 0).toFixed(6) }} MHz</div>
                </div>
                <div class="bg-panel-alto rounded px-2 py-1">
                  <div class="text-texto-tenue">Error</div>
                  <div class="font-mono" :class="((result.error_khz ?? 0) < 5) ? 'text-green-400' : 'text-orange-400'">
                    {{ ((result.error_khz ?? 0)).toFixed(3) }} kHz
                  </div>
                </div>
                <div class="bg-panel-alto rounded px-2 py-1">
                  <div class="text-texto-tenue">Proximidad</div>
                  <div class="font-mono text-texto">{{ Math.round(((result.proximity ?? result.score_breakdown?.proximity ?? 0) * 100)) }}%</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Análisis detallado -->
        <div v-if="selectedResult" class="bg-panel border border-borde rounded-2xl p-6">
          <h3 class="text-lg font-semibold mb-4 text-texto">🔍 Análisis Detallado</h3>
          
          <div class="grid grid-cols-2 gap-4 mb-6">
            <div class="p-4 bg-panel-hondo border border-borde rounded-lg">
              <div class="text-sm text-texto-tenue mb-2">Fórmula Matemática</div>
              <div class="font-mono text-lg text-blue-400 font-bold break-all">{{ selectedResult.formula }}</div>
            </div>
            <div class="p-4 bg-panel-hondo border border-borde rounded-lg">
              <div class="text-sm text-texto-tenue mb-2">Tipo de Interferencia</div>
              <div class="text-lg font-bold text-orange-400">{{ selectedResult.tipo }}</div>
            </div>
            <div class="p-4 bg-panel-hondo border border-borde rounded-lg">
              <div class="text-sm text-texto-tenue mb-2">Frecuencia Calculada</div>
              <div class="font-mono text-xl text-green-400 font-bold">{{ ((selectedResult.result_mhz ?? selectedResult.resultado) || 0).toFixed(6) }} MHz</div>
            </div>
            <div class="p-4 bg-panel-hondo border border-borde rounded-lg">
              <div class="text-sm text-texto-tenue mb-2">Error respecto al Objetivo</div>
              <div class="font-mono text-xl font-bold" :class="((selectedResult.error_khz ?? 0) < 5) ? 'text-green-400' : 'text-red-400'">
                {{ ((selectedResult.error_khz ?? 0)).toFixed(3) }} kHz
              </div>
            </div>
          </div>

          <!-- P0-11: la calculadora es una ruta suelta (`/calculadora`), no
               recibe id y en la app no hay «expediente activo», así que el
               destino se elige acá. Sin esto el botón no sabía adónde guardar,
               que era justamente lo que lo hacía mentir. -->
          <div class="mb-4">
            <label for="expediente-destino" class="block text-sm text-texto-tenue mb-1">
              Expediente de destino
            </label>
            <select
              id="expediente-destino"
              v-model="expedienteId"
              class="w-full px-3 py-2 bg-panel-hondo border border-borde-fuerte rounded text-texto focus:outline-none focus:border-sky-600"
            >
              <option :value="null" disabled>Seleccioná un expediente…</option>
              <option v-for="e in expedientes" :key="e.id" :value="e.id">
                {{ e.numero_expediente }}{{ e.aeropuerto ? ' — ' + e.aeropuerto : '' }}
              </option>
            </select>
            <p v-if="expedientesStore.loading" class="text-xs text-texto-tenue mt-1">
              Cargando expedientes…
            </p>
            <!-- Distinguir «no pude cargar» de «no hay ninguno»: decir
                 «todavía no hay expedientes» cuando en realidad falló la
                 carga sería repetir el defecto que arregla este commit. -->
            <p v-else-if="expedientesStore.error" class="text-xs text-red-400 mt-1">
              No se pudieron cargar los expedientes. Revisá que el backend esté
              levantado.
            </p>
            <p v-else-if="expedientes.length === 0" class="text-xs text-texto-tenue mt-1">
              No hay expedientes creados todavía. Creá uno desde Expedientes y volvé
              a esta pantalla.
            </p>
            <p v-else-if="expedientes.length >= 100" class="text-xs text-texto-tenue mt-1">
              Se muestran los primeros 100 expedientes.
            </p>
          </div>

          <button
            @click="storeResult"
            :disabled="!puedeGuardar"
            class="w-full px-4 py-3 bg-green-600 hover:bg-green-700 disabled:bg-panel-alto disabled:text-texto-tenue disabled:cursor-not-allowed rounded-lg font-semibold transition-colors text-white"
          >
            {{ guardando ? 'Guardando…' : '💾 Guardar en Expediente' }}
          </button>

          <!-- El aviso vive en la página: reemplaza al `alert` que decía
               «guardado» sin guardar nada. -->
          <p
            v-if="aviso.texto"
            role="status"
            class="mt-3 text-sm"
            :class="aviso.tipo === 'ok' ? 'text-green-400' : 'text-red-400'"
          >
            {{ aviso.texto }}
          </p>
        </div>
      </div>
    </div>

    <!-- Histograma -->
    <div v-if="rfStore.results.length > 0" class="bg-panel border border-borde rounded-2xl p-6">
      <Chart
        title="Distribución de Scores"
        type="bar"
        :data="rfStore.results.map(r => ({ label: r.formula, value: r.score }))"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRFStore } from '../stores/rf'
import { useExpedientesStore } from '../stores/expedientes'
import { expedientes as apiExpedientes } from '../api/client'
import FrequencyInput from '../components/FrequencyInput.vue'
import Chart from '../components/Chart.vue'

const rfStore = useRFStore()
const expedientesStore = useExpedientesStore()
const selectedResult = ref(null)

// P0-11: el destino del guardado, y el aviso que reemplaza al `alert`.
const expedienteId = ref(null)
const guardando = ref(false)
const aviso = ref({ tipo: null, texto: '' })

const expedientes = computed(() => expedientesStore.expedientes)
const puedeGuardar = computed(
  () => !!selectedResult.value && !!expedienteId.value && !guardando.value
)

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
  // El aviso habla de un resultado concreto: al cambiar de uno deja de ser
  // cierto, así que no queda colgado diciendo «guardado».
  aviso.value = { tipo: null, texto: '' }
}

/**
 * Guarda el resultado seleccionado en el expediente elegido.
 *
 * Este era P0-11: la función no guardaba nada y respondía con un diálogo
 * nativo que daba por hecho el guardado. El texto literal de entonces está
 * en `AERORF_CHANGELOG.md`; acá no se repite a propósito, porque
 * `tests/p011-guardar.spec.js` comprueba que no vuelva a aparecer.
 *
 * Ahora se manda de verdad a `POST /expedientes/{id}/eventos`, que escribe en
 * `eventos_rf`, la tabla que ya leía `GET /expedientes/{id}/eventos`. Los
 * nombres de campo del cuerpo son los de ese modelo, y los del cálculo son los
 * de `RFMatch` (`result_mhz`, `tipo`, `error_khz`, `score`,
 * `frequencies_involved`), medidos en vivo contra `/rf/calculate` antes de
 * escribir esto.
 */
const storeResult = async () => {
  aviso.value = { tipo: null, texto: '' }

  if (!expedienteId.value) {
    aviso.value = {
      tipo: 'error',
      texto: 'Elegí a qué expediente guardarlo.',
    }
    return
  }
  if (!selectedResult.value) {
    aviso.value = {
      tipo: 'error',
      texto: 'No hay ningún resultado seleccionado para guardar.',
    }
    return
  }

  const r = selectedResult.value
  guardando.value = true
  try {
    const guardado = await apiExpedientes.crearEvento(expedienteId.value, {
      expediente_id: expedienteId.value,
      frecuencia_resultado_mhz: r.result_mhz ?? r.resultado,
      tipo_producto: r.tipo,
      formula: r.formula,
      error_khz: r.error_khz ?? 0,
      score_probabilidad: r.score,
      freq_1_mhz: r.frequencies_involved?.[0] ?? null,
      freq_2_mhz: r.frequencies_involved?.[1] ?? null,
    })
    const destino = expedientes.value.find((e) => e.id === expedienteId.value)
    aviso.value = {
      tipo: 'ok',
      texto: `Guardado en el expediente ${
        destino?.numero_expediente ?? expedienteId.value
      } (evento ${guardado.id}).`,
    }
  } catch (err) {
    aviso.value = { tipo: 'error', texto: mensajeDeError(err) }
  } finally {
    guardando.value = false
  }
}

/**
 * Traduce el error a un mensaje que se pueda leer. Los `detail` que salen de
 * nuestros propios endpoints ya vienen en español (404 y 400 del nuevo POST);
 * los 422 de validación los arma FastAPI en inglés, así que esos se reemplazan
 * en vez de mandarlos tal cual al operador.
 */
const mensajeDeError = (err) => {
  const detalle = err?.response?.data?.detail
  if (typeof detalle === 'string' && detalle.trim()) return detalle
  if (Array.isArray(detalle)) {
    return 'El resultado no tiene los datos que hace falta para guardarlo.'
  }
  if (err?.message === 'Network Error') {
    return 'No se pudo hablar con el backend. ¿Está levantado?'
  }
  return 'No se pudo guardar el resultado.'
}

onMounted(() => {
  // `limit: 100` porque el endpoint corta en 10 por defecto.
  expedientesStore.fetchExpedientes({ limit: 100 })
  calculate()
})
</script>
