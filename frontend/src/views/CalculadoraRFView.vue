<template>
  <div class="page-doc">
    <div class="mb-6">
      <h1 class="page-doc-title">🧮 Calculadora RF</h1>
      <p class="page-doc-sub">Motor de análisis de frecuencias, armónicas e intermodulación</p>
    </div>

    <!--
      Dos modos, una sola entrada de datos (Fase 4 · AeroRF 2.5):

        A — Armónicos: por emisora, contra la referencia. Los productos los
            calcula `GET /rf/harmonics/{freq}`; la diferencia en kHz es sólo
            la resta contra la referencia, para mostrar.
        B — Intermodulación: el motor completo (`POST /rf/calculate`), con
            detalle, candidatos inversos y exportaciones.

      Ambos paneles están en el DOM (`v-show`): el de Armónicos es el que se
      ve primero, pero el guardado en expediente del modo B sigue siendo
      alcanzable por los tests y por quien navegue por teclado.
    -->
    <div class="calc-modos" role="tablist" aria-label="Modo de análisis">
      <button
        type="button"
        role="tab"
        class="calc-modo"
        :class="{ 'calc-modo-on': modo === 'a' }"
        :aria-selected="modo === 'a'"
        @click="modo = 'a'"
      >
        Armónicos
      </button>
      <button
        type="button"
        role="tab"
        class="calc-modo"
        :class="{ 'calc-modo-on': modo === 'b' }"
        :aria-selected="modo === 'b'"
        @click="modo = 'b'"
      >
        Intermodulación
      </button>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
      <!-- ══════════ Panel de control ══════════ -->
      <div class="lg:col-span-1 space-y-4">
        <!-- Parámetros compartidos por los dos modos -->
        <div class="bg-panel border border-borde rounded-2xl p-6">
          <h3 class="text-lg font-semibold mb-4 text-texto">⚙️ Parámetros</h3>
          <div class="space-y-4">
            <div>
              <label for="calc-referencia" class="block text-sm text-texto-tenue mb-2">
                Frecuencia de referencia (MHz)
              </label>
              <input
                id="calc-referencia"
                v-model.number="form.target_mhz"
                type="number"
                step="0.001"
                min="0.001"
                max="5999.999"
                class="w-full px-3 py-2 bg-panel-hondo border border-borde rounded-lg text-texto focus:outline-none focus:border-blue-500 font-mono"
              />
              <p class="text-xs text-texto-invisible mt-1">El motor la acepta entre 0 y 6000 MHz.</p>
            </div>
            <div>
              <label for="calc-tolerancia" class="block text-sm text-texto-tenue mb-2">
                Tolerancia (kHz)
              </label>
              <input
                id="calc-tolerancia"
                v-model.number="form.tolerance_khz"
                type="number"
                step="0.1"
                min="0.1"
                max="500"
                class="w-full px-3 py-2 bg-panel-hondo border border-borde rounded-lg text-texto focus:outline-none focus:border-blue-500 font-mono"
              />
              <p class="text-xs text-texto-invisible mt-1">El motor la acepta entre 0 y 500 kHz.</p>
            </div>
            <button
              type="button"
              class="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-panel-alto rounded-lg font-semibold transition-colors text-white"
              :disabled="calculando || !!problemaParametros"
              @click="calcular"
            >
              {{ calculando ? '⏳ Calculando...' : '🚀 Calcular' }}
            </button>

            <!-- Un error de cálculo se ve sin importar el modo activo: vive
                 al lado del botón que lo dispara, no adentro de una pestaña.
                 Primero se chequea lo que el motor va a rechazar igual
                 (`RFCalculationRequest`): preferible decirlo acá que mandar
                 un 422 y devolver un error genérico. -->
            <p v-if="problemaParametros || errorCalculo" role="alert" class="text-sm text-red-400">
              {{ problemaParametros || errorCalculo }}
            </p>
          </div>
        </div>

        <!-- Alta manual de emisoras -->
        <FrequencyInput title="Agregar emisora" @submit="addFrequency" />

        <!-- Lista compartida: alimenta los dos modos -->
        <div class="bg-panel border border-borde rounded-2xl p-6">
          <h3 class="text-lg font-semibold mb-3 text-texto">📡 Emisoras ({{ form.frequencies.length }})</h3>
          <div class="space-y-2 max-h-64 overflow-y-auto">
            <div
              v-for="(freq, idx) in form.frequencies"
              :key="idx"
              class="p-3 bg-panel-hondo border border-borde rounded-lg flex justify-between items-center text-sm text-texto"
            >
              <div class="font-mono flex-1">
                <div>{{ freq.freq_mhz }} MHz</div>
                <div class="text-xs text-texto-tenue">{{ freq.signal_type }} · {{ freq.label }}</div>
                <div v-if="freq.observaciones" class="text-xs text-texto-invisible">
                  {{ freq.observaciones }}
                </div>
              </div>
              <button
                type="button"
                class="text-red-400 hover:text-red-300 transition ml-2"
                title="Quitar emisora"
                @click="removeFrequency(idx)"
              >
                ✕
              </button>
            </div>
            <div v-if="form.frequencies.length === 0" class="text-texto-tenue text-sm text-center py-4">
              Sin emisoras agregadas
            </div>
          </div>

          <button type="button" class="calc-accion mt-4 w-full" @click="abrirCsv">
            Importar CSV
          </button>
          <input
            id="calc-csv"
            ref="csvInput"
            type="file"
            accept=".csv,text/csv"
            class="hidden"
            @change="importarCsv"
          />
          <p class="text-xs text-texto-invisible mt-2">
            Columnas: nombre, frecuencia (MHz), observaciones. Admite coma o punto y coma.
          </p>
          <p
            v-if="csvMsg"
            role="status"
            class="text-xs mt-2"
            :class="csvMsg.tipo === 'error' ? 'text-red-400' : csvMsg.tipo === 'aviso' ? 'text-orange-400' : 'text-emerald-300'"
          >
            {{ csvMsg.texto }}
          </p>
        </div>
      </div>

      <!-- ══════════ Resultados ══════════ -->
      <div class="lg:col-span-3 space-y-6">
        <!-- ─── MODO A · Armónicos ─── -->
        <div
          v-show="modo === 'a'"
          data-modo="a"
          class="bg-panel border border-borde rounded-2xl p-6"
        >
          <h3 class="text-lg font-semibold mb-1 text-texto">🎯 Armónicas contra la referencia</h3>
          <p class="text-sm text-texto-tenue mb-4">
            Referencia {{ fmtMhz(form.target_mhz) }} MHz · tolerancia ±{{ fmtKhz(form.tolerance_khz) }} kHz.
            armónica = fundamental × orden · diferencia (kHz) = |armónica − referencia| × 1000.
          </p>

          <p v-if="cargandoArmonicas" class="text-texto-tenue text-sm py-6 text-center">
            Calculando armónicas…
          </p>

          <template v-else>
            <p v-if="armonicasFallo" role="alert" class="text-sm text-orange-400 mb-3">
              No se pudieron cargar algunas armónicas. Volvé a calcular.
            </p>

            <div v-if="filasArmonicas.length === 0" class="text-texto-tenue text-center py-8">
              Ejecutá un cálculo para ver las armónicas de cada emisora.
            </div>

            <div v-else class="calc-tabla-wrap">
              <table class="calc-tabla">
                <thead>
                  <tr>
                    <th>Emisora</th>
                    <th>Fundamental</th>
                    <th>2.ª armónica</th>
                    <th>3.ª armónica</th>
                    <th>4.ª armónica</th>
                    <th>Mejor diferencia (kHz)</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(fila, i) in filasArmonicas" :key="i">
                    <td>
                      <div class="text-texto">{{ fila.estacion.label }}</div>
                      <div class="calc-sub">
                        {{ fila.estacion.signal_type
                        }}<template v-if="fila.estacion.observaciones"> · {{ fila.estacion.observaciones }}</template>
                      </div>
                    </td>
                    <td class="calc-celda-mono">{{ fmtMhz(fila.estacion.freq_mhz) }}</td>
                    <td v-for="celda in fila.celdas" :key="celda.orden" class="calc-celda-mono">
                      <template v-if="celda.freq !== null">
                        {{ fmtMhz(celda.freq) }}
                        <span class="calc-sub">Δ {{ fmtKhz(celda.diffKhz) }} kHz</span>
                      </template>
                      <span v-else class="text-texto-invisible">—</span>
                    </td>
                    <td class="calc-celda-mono">{{ fmtKhz(fila.mejorDiff) }}</td>
                    <td>
                      <span class="calc-estado" :class="estadoClase(fila.estado)">
                        {{ fila.estado }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>

        <!-- ─── MODO B · Intermodulación ─── -->
        <div v-show="modo === 'b'" data-modo="b" class="space-y-6">
          <div class="bg-panel border border-borde rounded-2xl p-6">
            <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
              <h3 class="text-lg font-semibold text-texto">🎯 Intermodulación contra la referencia</h3>
              <div class="calc-acciones">
                <button
                  type="button"
                  class="calc-accion"
                  :disabled="filasMotor.length === 0"
                  @click="exportarCsv"
                >
                  Exportar CSV
                </button>
                <button
                  type="button"
                  class="calc-accion"
                  :disabled="filasMotor.length === 0"
                  @click="exportarJson"
                >
                  Exportar JSON
                </button>
                <button
                  type="button"
                  class="calc-accion"
                  :disabled="filasMotor.length === 0"
                  @click="limpiarCalculo"
                >
                  Limpiar cálculo
                </button>
                <button type="button" class="calc-accion" :disabled="calculando || !!problemaParametros" @click="calcular">
                  Volver a calcular
                </button>
              </div>
            </div>

            <p
              v-if="accionMsg"
              role="status"
              class="text-sm mb-3"
              :class="accionMsg.tipo === 'error' ? 'text-red-400' : 'text-emerald-300'"
            >
              {{ accionMsg.texto }}
            </p>

            <p v-if="rfStore.loading" class="text-texto-tenue text-sm py-6 text-center">
              Calculando…
            </p>

            <div v-else-if="filasMotor.length === 0" class="text-texto-tenue text-center py-8">
              Ejecutá un cálculo para ver resultados
            </div>

            <div v-else class="calc-tabla-wrap">
              <table class="calc-tabla">
                <thead>
                  <tr>
                    <th>Emisora</th>
                    <th>Fundamental</th>
                    <th>Producto</th>
                    <th>Orden</th>
                    <th>Frecuencia calculada</th>
                    <th>Diferencia (kHz)</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="r in filasMotor"
                    :key="r.formula"
                    class="calc-fila"
                    :class="{ 'calc-fila-on': selectedResult && selectedResult.formula === r.formula }"
                    tabindex="0"
                    @click="selectResult(r)"
                    @keydown.enter.prevent="selectResult(r)"
                  >
                    <td>{{ r.emisoras || '—' }}</td>
                    <td class="calc-celda-mono">{{ r.fundamentales || '—' }}</td>
                    <td class="calc-celda-mono">
                      <span class="calc-tipo">{{ r.tipo }}</span>
                      {{ r.formula }}
                    </td>
                    <td>{{ r.order }}.ª</td>
                    <td class="calc-celda-mono">{{ fmtMhz(r.result_mhz) }} MHz</td>
                    <td class="calc-celda-mono">{{ fmtKhz(r.errorKhz) }}</td>
                    <td>
                      <span class="calc-estado" :class="estadoClase(r.estado)">{{ r.estado }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Inversos de la referencia: aritmética pura, no el motor. -->
          <div class="bg-panel border border-borde rounded-2xl p-6">
            <h3 class="text-lg font-semibold mb-1 text-texto">
              📐 Candidatos matemáticos ({{ fmtMhz(form.target_mhz) }} MHz ÷ orden)
            </h3>
            <p class="text-sm text-texto-tenue mb-4">
              Si una emisora opera en esta frecuencia, su armónica n.ª cae exactamente sobre la
              referencia. No son productos de intermodulación calculados por el motor.
            </p>
            <div class="calc-tabla-wrap">
              <table class="calc-tabla">
                <thead>
                  <tr>
                    <th>Orden</th>
                    <th>Operación</th>
                    <th>Frecuencia candidata</th>
                    <th>Nota</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="n in [2, 3, 4]" :key="n">
                    <td>{{ n }}.ª</td>
                    <td>Referencia / {{ n }}</td>
                    <td class="calc-celda-mono">
                      {{ candidatoInverso(n) === null ? '—' : `${fmtMhz(candidatoInverso(n))} MHz` }}
                    </td>
                    <td>
                      <span class="calc-estado calc-estado-candidato">Candidato matemático</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Detalle + guardado en expediente -->
          <div v-if="selectedResult" class="bg-panel border border-borde rounded-2xl p-6">
            <h3 class="text-lg font-semibold mb-4 text-texto">🔍 Análisis detallado</h3>

            <div class="grid grid-cols-2 gap-4 mb-4">
              <div class="p-4 bg-panel-hondo border border-borde rounded-lg col-span-2">
                <div class="text-sm text-texto-tenue mb-1">Fórmula</div>
                <div class="font-mono text-lg text-blue-400 font-bold break-all">
                  {{ selectedResult.formula }}
                </div>
              </div>
              <div class="p-4 bg-panel-hondo border border-borde rounded-lg">
                <div class="text-sm text-texto-tenue mb-1">Emisoras</div>
                <div class="text-texto">{{ selectedResult.emisoras || '—' }}</div>
              </div>
              <div class="p-4 bg-panel-hondo border border-borde rounded-lg">
                <div class="text-sm text-texto-tenue mb-1">Orden y producto</div>
                <div class="text-texto">{{ selectedResult.tipo }} · orden {{ selectedResult.order }}</div>
              </div>
              <div class="p-4 bg-panel-hondo border border-borde rounded-lg">
                <div class="text-sm text-texto-tenue mb-1">Frecuencia calculada</div>
                <div class="font-mono text-xl text-green-400 font-bold">
                  {{ fmtMhz(selectedResult.result_mhz) }} MHz
                </div>
              </div>
              <div class="p-4 bg-panel-hondo border border-borde rounded-lg">
                <div class="text-sm text-texto-tenue mb-1">Diferencia</div>
                <div class="font-mono text-xl font-bold" :class="estadoTextoClase(estadoDelSeleccionado)">
                  {{ fmtKhz(selectedResult.error_khz) }} kHz
                </div>
              </div>
              <div class="p-4 bg-panel-hondo border border-borde rounded-lg">
                <div class="text-sm text-texto-tenue mb-1">Tolerancia</div>
                <div class="font-mono text-xl text-texto">±{{ fmtKhz(form.tolerance_khz) }} kHz</div>
              </div>
              <div class="p-4 bg-panel-hondo border border-borde rounded-lg">
                <div class="text-sm text-texto-tenue mb-1">Estado</div>
                <span class="calc-estado" :class="estadoClase(estadoDelSeleccionado)">
                  {{ estadoDelSeleccionado }}
                </span>
              </div>
              <div class="p-4 bg-panel-hondo border border-borde rounded-lg col-span-2">
                <div class="text-sm text-texto-tenue mb-1">Qué está pasando</div>
                <p class="text-sm text-texto">{{ explicacion(selectedResult) }}</p>
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
              type="button"
              class="w-full px-4 py-3 bg-green-600 hover:bg-green-700 disabled:bg-panel-alto disabled:text-texto-tenue disabled:cursor-not-allowed rounded-lg font-semibold transition-colors text-white"
              :disabled="!puedeGuardar"
              @click="storeResult"
            >
              {{ guardando ? 'Guardando…' : '💾 Guardar en Expediente' }}
            </button>

            <!-- El aviso vive en la página: reemplaza al diálogo nativo que
                 decía «guardado» sin guardar nada. -->
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
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRFStore } from '../stores/rf'
import { useExpedientesStore } from '../stores/expedientes'
import { expedientes as apiExpedientes } from '../api/client'
import FrequencyInput from '../components/FrequencyInput.vue'
import { parseEmisorasCsv, buildCsv, buildJson, downloadText, nombreDeArchivo } from '../lib/rfFiles'

const rfStore = useRFStore()
const expedientesStore = useExpedientesStore()

// ── Estado de la vista ────────────────────────────────────────────────────────
const modo = ref('a') // 'a' = armónicos (por defecto), 'b' = intermodulación
const selectedResult = ref(null)
const errorCalculo = ref(null)
const accionMsg = ref(null)

// Límites del motor (`RFCalculationRequest` en `app/models/rf_models.py`):
// `tolerance_khz` con `gt=0, le=500`, `target_mhz` con `gt=0, lt=6000` y
// `frequencies` con `min_length=1, max_length=50`. Fuera de esos rangos el
// backend responde 422, así que la vista los chequea antes de pedir.
const TOLERANCIA_MAX_KHZ = 500
const REFERENCIA_MAX_MHZ = 6000
const EMISORAS_MAX = 50

// Modo A: una fila de armónicos por emisora, cargadas con
// `GET /rf/harmonics/{freq}?max_order=4` (2.ª, 3.ª y 4.ª).
const armonicasPorEstacion = ref([])
const cargandoArmonicas = ref(false)
const armonicasFallo = ref(false)

// Lista de emisoras compartida por los dos modos. La señal por defecto es FM
// (el caso de uso de la pantalla); el CSV trae el nombre y las observaciones.
const form = ref({
  target_mhz: 119.0,
  tolerance_khz: 10,
  frequencies: [
    { freq_mhz: 88.5, signal_type: 'FM', label: 'FM Radio', observaciones: '', power_dbm: null },
    { freq_mhz: 58.0, signal_type: 'TV_UHF', label: 'TV Señal', observaciones: '', power_dbm: null },
  ],
})

// P0-11: el destino del guardado, y el aviso que reemplaza al diálogo nativo.
const expedienteId = ref(null)
const guardando = ref(false)
const aviso = ref({ tipo: null, texto: '' })

// Importación CSV de emisoras.
const csvInput = ref(null)
const csvMsg = ref(null)

const expedientes = computed(() => expedientesStore.expedientes)
const puedeGuardar = computed(
  () => !!selectedResult.value && !!expedienteId.value && !guardando.value
)
const calculando = computed(() => rfStore.loading || cargandoArmonicas.value)

/**
 * Parámetros que el motor rechazaría igual (422). Se dice antes de pedir,
 * en español y al lado del botón, en vez de un error genérico. `null` =
 * todo en rango.
 */
const problemaParametros = computed(() => {
  const refMhz = Number(form.value.target_mhz)
  if (!Number.isFinite(refMhz) || refMhz <= 0 || refMhz >= REFERENCIA_MAX_MHZ) {
    return 'La frecuencia de referencia tiene que ser mayor a 0 y menor a 6000 MHz.'
  }
  const tol = Number(form.value.tolerance_khz)
  if (!Number.isFinite(tol) || tol <= 0 || tol > TOLERANCIA_MAX_KHZ) {
    return `La tolerancia tiene que ser mayor a 0 y como máximo ${TOLERANCIA_MAX_KHZ} kHz.`
  }
  const validas = form.value.frequencies.filter((f) => Number(f.freq_mhz) > 0)
  if (validas.length < 1) return 'Agregá al menos una emisora para calcular.'
  if (validas.length > EMISORAS_MAX) {
    return `El motor acepta como máximo ${EMISORAS_MAX} emisoras por cálculo.`
  }
  return null
})

// ── Formato ───────────────────────────────────────────────────────────────────
// MHz con 6 decimales (precisión hasta 1 Hz) y kHz con 3; lo que no sea un
// número se muestra como «—» en vez de «NaN».
const fmtMhz = (v) => {
  const n = Number(v)
  return v === null || v === undefined || v === '' || !Number.isFinite(n) ? '—' : n.toFixed(6)
}
const fmtKhz = (v) => {
  const n = Number(v)
  return v === null || v === undefined || v === '' || !Number.isFinite(n) ? '—' : n.toFixed(3)
}

/** Redondea kHz a 1 Hz: borra el ruido de coma flotante de la resta. */
const redondearKhz = (v) => Math.round(Number(v) * 1000) / 1000

/**
 * Estado de una diferencia contra la tolerancia — el mismo criterio que el
 * motor (`≤ tolerancia` entra; en el borde exacto sigue entrando):
 * Exacta (0) / En tolerancia / Fuera de tolerancia. Nunca «probabilidad».
 * Con una tolerancia fuera del rango del motor no se juzga: «Sin datos»
 * (la vista ya lo dice con `problemaParametros`).
 */
const estadoDe = (diffKhz, tolerancia) => {
  const d = Number(diffKhz)
  if (!Number.isFinite(d)) return 'Sin datos'
  const dif = redondearKhz(d)
  if (dif === 0) return 'Exacta'
  const tol = Number(tolerancia)
  if (!Number.isFinite(tol) || tol <= 0 || tol > TOLERANCIA_MAX_KHZ) return 'Sin datos'
  if (dif <= tol) return 'En tolerancia'
  return 'Fuera de tolerancia'
}

const estadoClase = (estado) => {
  if (estado === 'Exacta') return 'calc-estado-ok'
  if (estado === 'En tolerancia') return 'calc-estado-tol'
  if (estado === 'Fuera de tolerancia') return 'calc-estado-fuera'
  return 'calc-estado-sd'
}

const estadoTextoClase = (estado) => {
  if (estado === 'Exacta') return 'text-green-400'
  if (estado === 'En tolerancia') return 'text-sky-300'
  return 'text-red-400'
}

// ── Modo A · armónicas ────────────────────────────────────────────────────────
const filasArmonicas = computed(() => {
  const refMhz = Number(form.value.target_mhz)
  const tol = Number(form.value.tolerance_khz)

  const filas = armonicasPorEstacion.value.map(({ estacion, armonicas }) => {
    const celdas = [2, 3, 4].map((orden) => {
      const h = armonicas.find((x) => Number(x.order) === orden)
      if (!h) return { orden, freq: null, diffKhz: null }
      const diffKhz = Math.abs(Number(h.freq_mhz) - refMhz) * 1000
      return { orden, freq: Number(h.freq_mhz), diffKhz }
    })
    const conDiff = celdas.filter((c) => c.diffKhz !== null)
    const mejor = conDiff.length
      ? conDiff.reduce((a, b) => (redondearKhz(a.diffKhz) <= redondearKhz(b.diffKhz) ? a : b))
      : null
    return {
      estacion,
      celdas,
      mejorDiff: mejor ? mejor.diffKhz : null,
      estado: mejor ? estadoDe(mejor.diffKhz, tol) : 'Sin datos',
    }
  })

  // De la menor diferencia a la mayor; a igual distancia, el orden de carga.
  const clave = (fila) => (fila.mejorDiff === null ? Infinity : redondearKhz(fila.mejorDiff))
  return filas
    .map((fila, indice) => ({ fila, indice, k: clave(fila) }))
    .sort((a, b) => (a.k === b.k ? a.indice - b.indice : a.k - b.k))
    .map((x) => x.fila)
})

// ── Modo B · intermodulación ─────────────────────────────────────────────────
const etiquetaDe = (frecuencia) => {
  const est = form.value.frequencies.find(
    (e) => Math.abs(Number(e.freq_mhz) - Number(frecuencia)) < 1e-6
  )
  return est && est.label ? est.label : `${frecuencia} MHz`
}

const filasMotor = computed(() => {
  const tol = Number(form.value.tolerance_khz)
  const filas = rfStore.results.map((r) => {
    const freqs = Array.isArray(r.frequencies_involved) ? r.frequencies_involved : []
    const errorKhz = Number(r.error_khz ?? 0)
    return {
      ...r,
      errorKhz,
      estado: estadoDe(errorKhz, tol),
      emisoras: freqs.map((f) => etiquetaDe(f)).join(' + '),
      fundamentales: freqs.length ? freqs.map((f) => `${f} MHz`).join(' + ') : '',
    }
  })
  // La fila más cercana primero: lo que importa es la diferencia, no el score.
  return filas
    .map((fila, indice) => ({ fila, indice }))
    .sort((a, b) => {
      const da = Math.abs(a.fila.errorKhz)
      const db = Math.abs(b.fila.errorKhz)
      return da === db ? a.indice - b.indice : da - db
    })
    .map((x) => x.fila)
})

const estadoDelSeleccionado = computed(() =>
  selectedResult.value
    ? estadoDe(selectedResult.value.error_khz ?? 0, Number(form.value.tolerance_khz))
    : 'Sin datos'
)

/** `Referencia / 2|3|4` en MHz, redondeado a 1 Hz (sólo aritmética). */
const candidatoInverso = (n) => {
  const refMhz = Number(form.value.target_mhz)
  if (!Number.isFinite(refMhz) || refMhz <= 0) return null
  return Math.round((refMhz / n) * 1e6) / 1e6
}

/**
 * Qué significa el producto seleccionado, en una oración. No hay
 * probabilidades en el discurso porque no las hay en los datos: hay una
 * fórmula, una diferencia en kHz y una tolerancia.
 */
const explicacion = (r) => {
  if (!r) return ''
  const refMhz = Number(form.value.target_mhz)
  const tol = Number(form.value.tolerance_khz)
  const freqs = Array.isArray(r.frequencies_involved) ? r.frequencies_involved : []
  const esArmonica = /^H\d+$/.test(String(r.tipo))
  const base = esArmonica
    ? `La emisora en ${freqs[0] ?? '—'} MHz multiplica su frecuencia por ${r.order} (armónica ${r.order}.ª) y el producto cae en ${fmtMhz(r.result_mhz)} MHz.`
    : `La mezcla de ${
        freqs.map((f) => `${f} MHz`).join(' y ') || '—'
      } en un dispositivo no lineal produce un producto de orden ${r.order} (${r.tipo}) en ${fmtMhz(r.result_mhz)} MHz.`
  const error = redondearKhz(Number(r.error_khz ?? 0))
  const cierre =
    error === 0
      ? `El resultado coincide exactamente con la referencia de ${refMhz} MHz.`
      : `Queda a ${fmtKhz(error)} kHz de la referencia de ${refMhz} MHz (tolerancia ±${fmtKhz(
          tol
        )} kHz): ${error <= tol ? 'en tolerancia' : 'fuera de tolerancia'}.`
  return `${base} ${cierre}`
}

// ── Cálculo ───────────────────────────────────────────────────────────────────
const calcular = async () => {
  errorCalculo.value = null
  accionMsg.value = null
  // Si el motor va a rechazar los parámetros (422), no se pide nada: la
  // pantalla ya lo dice con `problemaParametros` y el botón está fuera de
  // rango. Esta guarda es el respaldo por si algo llama a `calcular()`.
  if (problemaParametros.value) return
  // Los dos modos comparten parámetros y emisoras: se calculan juntos para
  // que ninguna pestaña quede desactualizada respecto de la otra.
  await Promise.all([calcularMotor(), calcularArmonicas()])
}

const calcularMotor = async () => {
  try {
    await rfStore.calculateRF({
      target_mhz: Number(form.value.target_mhz),
      tolerance_khz: Number(form.value.tolerance_khz),
      frequencies: form.value.frequencies
        .filter((f) => Number(f.freq_mhz) > 0)
        .map((f) => ({
          freq_mhz: f.freq_mhz,
          label: f.label,
          signal_type: f.signal_type || 'FM',
          ...(f.power_dbm === null || f.power_dbm === undefined || f.power_dbm === ''
            ? {}
            : { power_dbm: Number(f.power_dbm) }),
        })),
    })
    selectedResult.value = filasMotor.value[0] || null
    aviso.value = { tipo: null, texto: '' }
  } catch (err) {
    // El backend no calculó: se dice como error, en español, sin alarmas.
    errorCalculo.value =
      err?.message === 'Network Error'
        ? 'No se pudo hablar con el backend. ¿Está levantado?'
        : 'No se pudo calcular. Revisá los parámetros y volvé a intentar.'
  }
}

const calcularArmonicas = async () => {
  cargandoArmonicas.value = true
  armonicasFallo.value = false
  try {
    const estaciones = form.value.frequencies.filter((f) => Number(f.freq_mhz) > 0)
    const filas = await Promise.all(
      estaciones.map(async (estacion) => {
        try {
          const data = await rfStore.getHarmonics(estacion.freq_mhz, 4)
          const armonicas = Array.isArray(data?.harmonics) ? data.harmonics : []
          return { estacion, armonicas }
        } catch {
          armonicasFallo.value = true
          return { estacion, armonicas: [] }
        }
      })
    )
    armonicasPorEstacion.value = filas
  } finally {
    cargandoArmonicas.value = false
  }
}

// ── Emisoras ──────────────────────────────────────────────────────────────────
const addFrequency = (data) => {
  const freq = Number(data.freq_mhz)
  if (!Number.isFinite(freq) || freq <= 0 || freq >= 6000) {
    csvMsg.value = {
      tipo: 'error',
      texto: 'La frecuencia tiene que ser mayor a 0 y menor a 6000 MHz.',
    }
    return
  }
  const nombre = String(data.label || '').trim() || `${Math.round(freq * 1e6) / 1e6} MHz`
  const potencia =
    data.power_dbm === '' || data.power_dbm === null || data.power_dbm === undefined
      ? null
      : Number(data.power_dbm)
  form.value.frequencies.push({
    freq_mhz: Math.round(freq * 1e6) / 1e6,
    signal_type: data.signal_type || 'FM',
    label: nombre.slice(0, 80),
    power_dbm: Number.isFinite(potencia) ? potencia : null,
    observaciones: '',
  })
  csvMsg.value = { tipo: 'ok', texto: `Emisora agregada: ${nombre}.` }
}

const removeFrequency = (idx) => {
  form.value.frequencies.splice(idx, 1)
}

const abrirCsv = () => {
  if (csvInput.value) csvInput.value.click()
}

const importarCsv = (event) => {
  const input = event.target
  const archivo = input.files && input.files[0]
  if (!archivo) return
  const lector = new FileReader()
  lector.onload = () => {
    const { agregadas, errores } = parseEmisorasCsv(String(lector.result || ''))
    if (agregadas.length) form.value.frequencies.push(...agregadas)
    const partes = []
    partes.push(
      agregadas.length
        ? `CSV importado: ${agregadas.length} ${
            agregadas.length === 1 ? 'emisora agregada' : 'emisoras agregadas'
          }.`
        : 'CSV importado: no se agregó ninguna emisora.'
    )
    if (errores.length) partes.push(errores.slice(0, 3).join(' '))
    csvMsg.value = { tipo: errores.length ? 'aviso' : 'ok', texto: partes.join(' ') }
    input.value = ''
  }
  lector.onerror = () => {
    csvMsg.value = { tipo: 'error', texto: 'No se pudo leer el archivo CSV.' }
    input.value = ''
  }
  lector.readAsText(archivo)
}

// ── Exportaciones del modo B ──────────────────────────────────────────────────
const exportarCsv = () => {
  try {
    const filas = [
      [
        'Emisora',
        'Fundamental (MHz)',
        'Producto',
        'Orden',
        'Tipo',
        'Frecuencia calculada (MHz)',
        'Diferencia (kHz)',
        'Estado',
      ],
      ...filasMotor.value.map((r) => [
        r.emisoras,
        r.fundamentales,
        r.formula,
        r.order,
        r.tipo,
        r.result_mhz,
        r.errorKhz,
        r.estado,
      ]),
    ]
    downloadText(nombreDeArchivo('Intermodulacion', 'csv'), buildCsv(filas), 'text/csv;charset=utf-8')
    accionMsg.value = { tipo: 'ok', texto: `CSV exportado con ${filasMotor.value.length} productos.` }
  } catch {
    accionMsg.value = { tipo: 'error', texto: 'No se pudo exportar el CSV.' }
  }
}

const exportarJson = () => {
  try {
    const texto = buildJson({
      generado: new Date().toISOString(),
      calculadora: 'AeroRF — modo Intermodulación',
      parametros: {
        frecuencia_referencia_mhz: Number(form.value.target_mhz),
        tolerancia_khz: Number(form.value.tolerance_khz),
      },
      emisoras: form.value.frequencies.map((f) => ({ ...f })),
      candidatos_matematicos: [2, 3, 4].map((n) => ({
        orden: n,
        frecuencia_mhz: candidatoInverso(n),
        nota: 'Candidato matemático: si una emisora opera acá, su armónica n.ª cae sobre la referencia.',
      })),
      solicitud: rfStore.lastRequest,
      respuesta: rfStore.lastResponse,
    })
    downloadText(nombreDeArchivo('Intermodulacion', 'json'), texto, 'application/json;charset=utf-8')
    accionMsg.value = { tipo: 'ok', texto: 'JSON exportado con la última corrida del motor.' }
  } catch {
    accionMsg.value = { tipo: 'error', texto: 'No se pudo exportar el JSON.' }
  }
}

const limpiarCalculo = () => {
  rfStore.clearCalculation()
  selectedResult.value = null
  errorCalculo.value = null
  aviso.value = { tipo: null, texto: '' }
  accionMsg.value = { tipo: 'ok', texto: 'Cálculo limpiado.' }
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
 * escribir esto. `score` viaja como `score_probabilidad` porque así se llama
 * la columna histórica; en la pantalla no se muestra como probabilidad.
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
  // Arranca con los dos modos listos: la pestaña por defecto es Armónicos,
  // pero el motor se corre también para que el detalle y el guardado del
  // modo Intermodulación no dependan de un clic previo.
  calcular()
})
</script>

<style scoped>
/* Pestañas de modo — mismo lenguaje que los enlaces de la brandbar: el activo
   se marca con la señal, sin relleno de otro color. */
.calc-modos {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.25rem;
}

.calc-modo {
  font-family: var(--font-ui);
  font-size: 0.9rem;
  font-weight: 600;
  padding: 0.5rem 1.1rem;
  border: 1px solid var(--borde);
  border-radius: 0.65rem;
  background: var(--panel);
  color: var(--texto-tenue);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}

.calc-modo:hover {
  color: var(--texto);
  background: var(--panel-alto);
}

.calc-modo-on {
  color: var(--signal);
  border-color: var(--signal);
  background: var(--panel-alto);
}

/* Acciones secundarias (exportar/limpiar/volver, importar CSV). */
.calc-acciones {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.calc-accion {
  font-family: var(--font-ui);
  font-size: 0.8rem;
  font-weight: 600;
  padding: 0.4rem 0.85rem;
  border: 1px solid var(--borde);
  border-radius: 0.55rem;
  background: var(--panel-alto);
  color: var(--texto);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}

.calc-accion:hover:not(:disabled) {
  border-color: var(--signal);
  color: var(--signal);
}

.calc-accion:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* Tablas de análisis: scroll horizontal propio para que la página nunca
   desborde en pantallas angostas. */
.calc-tabla-wrap {
  overflow-x: auto;
}

.calc-tabla {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.calc-tabla th {
  text-align: left;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--texto-tenue);
  padding: 0.55rem 0.7rem;
  border-bottom: 1px solid var(--borde-fuerte);
  white-space: nowrap;
}

.calc-tabla td {
  padding: 0.65rem 0.7rem;
  border-bottom: 1px solid var(--borde);
  vertical-align: top;
  color: var(--texto);
}

.calc-tabla tbody tr:last-child td {
  border-bottom: none;
}

.calc-celda-mono {
  font-family: var(--font-mono);
  white-space: nowrap;
}

.calc-sub {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--texto-tenue);
  margin-top: 0.15rem;
}

.calc-tipo {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--signal);
  border: 1px solid var(--borde);
  border-radius: 0.35rem;
  padding: 0.05rem 0.35rem;
  margin-right: 0.35rem;
  vertical-align: middle;
}

.calc-fila {
  cursor: pointer;
}

.calc-fila:hover {
  background: var(--panel-alto);
}

.calc-fila-on {
  background: var(--panel-alto);
  box-shadow: inset 3px 0 0 var(--signal);
}

.calc-fila:focus-visible {
  outline: 2px solid var(--signal);
  outline-offset: -2px;
}

/* Estados: exacta / en tolerancia / fuera — sin porcentajes ni «scores». */
.calc-estado {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  border: 1px solid transparent;
  white-space: nowrap;
}

.calc-estado-ok {
  color: var(--risk-ok);
  border-color: var(--risk-ok);
  background: rgba(57, 182, 122, 0.12);
}

.calc-estado-tol {
  color: var(--signal);
  border-color: var(--signal);
  background: rgba(24, 182, 199, 0.12);
}

.calc-estado-fuera {
  color: var(--risk-high);
  border-color: var(--risk-high);
  background: rgba(228, 93, 104, 0.12);
}

.calc-estado-sd {
  color: var(--texto-invisible);
  border-color: var(--borde);
  background: var(--panel-hondo);
}

.calc-estado-candidato {
  color: var(--signal-on-ink);
  border-color: var(--borde);
  background: var(--panel-hondo);
}
</style>
