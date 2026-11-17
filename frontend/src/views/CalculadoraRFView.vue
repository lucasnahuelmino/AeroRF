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

            <p
              v-if="!form.target_mhz || form.frequencies.length === 0"
              class="text-sm text-texto-tenue mt-2"
            >
              Ingresá una frecuencia de referencia y agregá las emisoras que quieras analizar.
            </p>

            <div class="flex flex-wrap items-center gap-2 mt-3">
              <button type="button" class="calc-accion" @click="cargarEjemplo">
                Cargar ejemplo
              </button>
              <span
                v-if="ejemploCargado"
                class="text-xs font-semibold uppercase tracking-wide text-amber-300 border border-amber-500/40 rounded px-2 py-1"
              >
                DATOS DE EJEMPLO
              </span>
              <button v-if="ejemploCargado" type="button" class="calc-accion" @click="quitarEjemplo">
                Quitar ejemplo
              </button>
            </div>

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
          <div v-if="csvPendiente" class="mt-3 p-3 bg-panel-hondo border border-borde rounded-lg text-xs space-y-2">
            <p class="text-texto">
              Se van a importar {{ csvPendiente.agregadas.length }} emisoras
              ({{ csvPendiente.resumen?.leidas ?? 0 }} leídas,
              {{ csvPendiente.resumen?.rechazadas ?? 0 }} rechazadas,
              {{ csvPendiente.resumen?.duplicados ?? 0 }} duplicadas).
            </p>
            <ul
              v-if="csvPendiente.errores.length"
              class="text-orange-400 space-y-1 max-h-24 overflow-y-auto"
            >
              <li v-for="(e, i) in csvPendiente.errores" :key="i">{{ e }}</li>
            </ul>
            <div class="calc-acciones">
              <button
                type="button"
                class="calc-accion"
                :disabled="!csvPendiente.agregadas.length"
                @click="confirmarCsv"
              >
                Confirmar importación
              </button>
              <button type="button" class="calc-accion" @click="cancelarCsv">
                Cancelar
              </button>
            </div>
          </div>
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
              <p v-if="!form.target_mhz || form.frequencies.length === 0">
                Ingresá una frecuencia de referencia y agregá las emisoras que quieras analizar.
              </p>
              <p v-else>
                Ejecutá un cálculo para ver resultados
              </p>
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
          </div>

        </div>

        <!-- ══════════ Historial propio de análisis (AeroRF 2.6) ══════════
             La calculadora ya no guarda en Expedientes: la corrida que el
             operador decide conservar vive en `POST /rf/analisis`, con
             identidad propia, y se puede volver a consultar desde acá.
             Vive fuera de las pestañas: guardar y consultar es de los dos
             modos, no de uno. -->
        <div class="bg-panel border border-borde rounded-2xl p-6" data-historial>
          <div class="flex flex-wrap items-center justify-between gap-3 mb-3">
            <h3 class="text-lg font-semibold text-texto">🗂 Historial de análisis</h3>
            <div class="calc-acciones">
              <button
                type="button"
                class="calc-accion"
                data-guardar-analisis
                :disabled="!rfStore.lastResponse || guardando"
                @click="guardarAnalisis"
              >
                {{ guardando ? 'Guardando…' : '💾 Guardar análisis actual' }}
              </button>
              <button
                type="button"
                class="calc-accion"
                :disabled="historialCargando"
                @click="recargarHistorial"
              >
                Actualizar
              </button>
            </div>
          </div>

          <p
            v-if="historialMsg.texto"
            role="status"
            class="text-sm mb-3"
            :class="historialMsg.tipo === 'error' ? 'text-red-400' : 'text-emerald-300'"
          >
            {{ historialMsg.texto }}
          </p>

          <p v-if="historialCargando" class="text-texto-tenue text-sm py-4 text-center">
            Cargando historial…
          </p>
          <p v-else-if="historialError" role="alert" class="text-orange-400 text-sm py-4 text-center">
            {{ historialError }}
          </p>
          <div
            v-else-if="rfStore.historial.length === 0"
            class="text-texto-tenue text-sm text-center py-4"
          >
            Todavía no guardaste ningún análisis. «Guardar análisis actual» conserva la corrida
            con sus parámetros y sus resultados, sin necesidad de ningún expediente.
          </div>
          <ul v-else class="space-y-2">
            <li
              v-for="a in rfStore.historial"
              :key="a.id"
              class="p-3 bg-panel-hondo border border-borde rounded-lg flex flex-wrap items-center justify-between gap-2"
            >
              <div class="min-w-0">
                <div class="text-sm text-texto">
                  #{{ a.id }} · {{ fechaCorta(a.created_at) }} ·
                  {{ a.modo === 'armonicos' ? 'Armónicos' : 'Intermodulación' }}
                </div>
                <div class="text-xs text-texto-tenue font-mono">
                  Ref {{ fmtMhz(a.frecuencia_referencia_mhz) }} MHz ·
                  ±{{ fmtKhz(a.tolerancia_khz) }} kHz ·
                  {{ a.n_emisoras }} {{ a.n_emisoras === 1 ? 'emisora' : 'emisoras' }} ·
                  {{ a.n_productos }} {{ a.n_productos === 1 ? 'producto' : 'productos' }}
                  <template v-if="a.objeto_id"> · objeto GIS #{{ a.objeto_id }}</template>
                </div>
              </div>
              <div class="calc-acciones">
                <button type="button" class="calc-accion" @click="cargarAnalisis(a)">
                  Ver resultados
                </button>
                <button
                  type="button"
                  class="calc-accion"
                  :disabled="borrandoId === a.id"
                  @click="eliminarAnalisis(a)"
                >
                  {{ borrandoId === a.id ? 'Eliminando…' : 'Eliminar' }}
                </button>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRFStore } from '../stores/rf'
import { useSystemStore } from '../stores/system'
import FrequencyInput from '../components/FrequencyInput.vue'
import { parseEmisorasCsv, buildCsv, buildJson, downloadText, nombreDeArchivo } from '../lib/rfFiles'

const rfStore = useRFStore()
const systemStore = useSystemStore()

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

// Lista de emisoras compartida por los dos modos. La calculadora arranca
// vacía (AeroRF 2.6): sin frecuencia de referencia ni emisoras, y un
// mensaje guía invita a ingresarlas. «Cargar ejemplo» repone los datos de
// ejemplo (que antes eran el preset) marcados como «DATOS DE EJEMPLO».
const EJEMPLO_FORM = {
  target_mhz: 119.0,
  tolerance_khz: 10,
  frequencies: [
    { freq_mhz: 88.5, signal_type: 'FM', label: 'FM Radio', observaciones: '', power_dbm: null },
    { freq_mhz: 58.0, signal_type: 'TV_UHF', label: 'TV Señal', observaciones: '', power_dbm: null },
  ],
}

const form = ref({
  target_mhz: null,
  tolerance_khz: 10,
  frequencies: [],
})

const ejemploCargado = ref(false)

const cargarEjemplo = () => {
  form.value = {
    target_mhz: EJEMPLO_FORM.target_mhz,
    tolerance_khz: EJEMPLO_FORM.tolerance_khz,
    frequencies: EJEMPLO_FORM.frequencies.map((f) => ({ ...f })),
  }
  ejemploCargado.value = true
  errorCalculo.value = null
  accionMsg.value = { tipo: 'ok', texto: 'Datos de ejemplo cargados.' }
}

const quitarEjemplo = () => {
  form.value = { target_mhz: null, tolerance_khz: 10, frequencies: [] }
  ejemploCargado.value = false
  rfStore.clearCalculation()
  selectedResult.value = null
  errorCalculo.value = null
  accionMsg.value = { tipo: 'ok', texto: 'Datos de ejemplo quitados.' }
}

// Guardado en el historial propio de análisis (AeroRF 2.6): `guardando`
// acompaña al botón de guardar, `historialMsg` cuenta qué pasó y
// `borrandoId` evita dobles clics sobre «Eliminar».
const guardando = ref(false)
const borrandoId = ref(null)
const historialMsg = ref({ tipo: null, texto: '' })

// Importación CSV de emisoras.
const csvInput = ref(null)
const csvMsg = ref(null)
const csvPendiente = ref(null)

const historialCargando = computed(() => rfStore.historialLoading)
const historialError = computed(() => rfStore.historialError)
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
    const resultado = parseEmisorasCsv(String(lector.result || ''))
    csvPendiente.value = resultado
    const r = resultado.resumen || {}
    const partes = []
    partes.push(
      resultado.agregadas.length
        ? `CSV leído: ${r.leidas ?? resultado.agregadas.length} filas, ${resultado.agregadas.length} para importar.`
        : 'CSV leído: no hay emisoras para importar.'
    )
    if (resultado.errores.length) partes.push(`${resultado.errores.length} rechazadas.`)
    csvMsg.value = { tipo: resultado.errores.length ? 'aviso' : 'ok', texto: partes.join(' ') }
    input.value = ''
  }
  lector.onerror = () => {
    csvMsg.value = { tipo: 'error', texto: 'No se pudo leer el archivo CSV.' }
    input.value = ''
  }
  lector.readAsText(archivo)
}

const confirmarCsv = () => {
  if (!csvPendiente.value) return
  const { agregadas } = csvPendiente.value
  if (agregadas.length) form.value.frequencies.push(...agregadas)
  csvMsg.value = {
    tipo: 'ok',
    texto: `Importadas ${agregadas.length} ${agregadas.length === 1 ? 'emisora' : 'emisoras'}.`,
  }
  csvPendiente.value = null
}

const cancelarCsv = () => {
  csvPendiente.value = null
  csvMsg.value = { tipo: 'aviso', texto: 'Importación cancelada.' }
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
  accionMsg.value = { tipo: 'ok', texto: 'Cálculo limpiado.' }
}

const selectResult = (result) => {
  selectedResult.value = result
}

// ── Historial propio de análisis (AeroRF 2.6) ───────────────────────────────
/**
 * Guarda la corrida actual en `POST /rf/analisis`.
 *
 * Reemplaza al guardado de entonces (el destino era un expediente elegido
 * con un selector): el análisis tiene identidad propia — los parámetros que
 * se mandaron al motor y la respuesta que devolvió — y no depende de ningún
 * expediente. Lo que se persiste no es un resumen escrito a mano: es
 * exactamente `lastRequest` y `lastResponse`, los mismos objetos que ya
 * alimentan las exportaciones CSV/JSON. El `alert` mentiroso del P0-11 sigue
 * fuera: si el backend no guarda, el aviso lo dice como error.
 */
const guardarAnalisis = async () => {
  historialMsg.value = { tipo: null, texto: '' }

  if (!rfStore.lastRequest || !rfStore.lastResponse) {
    historialMsg.value = {
      tipo: 'error',
      texto: 'No hay ningún cálculo para guardar. Ejecutá un cálculo primero.',
    }
    return
  }

  guardando.value = true
  try {
    const modoAnalisis = modo.value === 'a' ? 'armonicos' : 'intermodulacion'
    const creado = await rfStore.guardarAnalisis(modoAnalisis)
    historialMsg.value = {
      tipo: 'ok',
      texto: `Análisis n.º ${creado.id} guardado: ${creado.n_productos} ${
        creado.n_productos === 1 ? 'producto' : 'productos'
      } contra ${fmtMhz(creado.frecuencia_referencia_mhz)} MHz.`,
    }
  } catch (err) {
    historialMsg.value = {
      tipo: 'error',
      texto: err?.message || 'No se pudo guardar el análisis.',
    }
  } finally {
    guardando.value = false
  }
}

/** Refresca la lista desde el backend; el estado queda en el store. */
const recargarHistorial = () => rfStore.cargarHistorial()

/**
 * Carga un análisis guardado en la pantalla: los parámetros vuelven al
 * formulario y los resultados del motor vuelven a la tabla, así «Ver
 * resultados» muestra lo que se guardó, no un cálculo nuevo.
 */
const cargarAnalisis = async (a) => {
  historialMsg.value = { tipo: null, texto: '' }
  try {
    rfStore.loadRun(a.parametros, a.resultados)
    form.value.target_mhz = a.parametros.target_mhz
    form.value.tolerance_khz = a.parametros.tolerance_khz
    form.value.frequencies = (a.parametros.frequencies || []).map((f) => ({
      freq_mhz: f.freq_mhz,
      signal_type: f.signal_type || 'FM',
      label: f.label || `${f.freq_mhz} MHz`,
      power_dbm: f.power_dbm ?? null,
      observaciones: '',
    }))
    modo.value = a.modo === 'armonicos' ? 'a' : 'b'
    selectedResult.value = filasMotor.value[0] || null
    errorCalculo.value = null
    // La pestaña Armónicas se deriva de las emisoras del formulario:
    // se vuelven a pedir las armónicas de la corrida cargada.
    await calcularArmonicas()
    historialMsg.value = {
      tipo: 'ok',
      texto: `Análisis n.º ${a.id} cargado en la tabla.`,
    }
  } catch {
    historialMsg.value = {
      tipo: 'error',
      texto: 'No se pudo cargar el análisis guardado.',
    }
  }
}

/**
 * Borra un análisis propio. Antes de mandar nada se confirma: es la única
 * escritura destructiva de esta pantalla, y acá se confirma en la aplicación
 * (mismo diálogo que el resto de AeroRF), no con un `confirm()` nativo.
 */
const eliminarAnalisis = async (a) => {
  const ok = await systemStore.ask({
    title: 'Eliminar análisis',
    message: `¿Eliminar el análisis n.º ${a.id} del ${fechaCorta(a.created_at)}? Esta acción no se puede deshacer.`,
    confirmLabel: 'Eliminar',
    danger: true,
  })
  if (!ok) return

  borrandoId.value = a.id
  historialMsg.value = { tipo: null, texto: '' }
  try {
    await rfStore.eliminarAnalisis(a.id)
    historialMsg.value = { tipo: 'ok', texto: `Análisis n.º ${a.id} eliminado.` }
  } catch (err) {
    historialMsg.value = {
      tipo: 'error',
      texto: err?.message || 'No se pudo eliminar el análisis.',
    }
  } finally {
    borrandoId.value = null
  }
}

/** Fecha corta para las filas del historial; sin fecha legible, «—». */
const fechaCorta = (iso) => {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('es-AR', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

onMounted(() => {
  // Arranca con los dos modos listos: la pestaña por defecto es Armónicos,
  // pero el motor se corre también para que el detalle del modo
  // Intermodulación no dependa de un clic previo.
  calcular()
  // El historial propio es parte de la pantalla desde AeroRF 2.6.
  recargarHistorial()
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
