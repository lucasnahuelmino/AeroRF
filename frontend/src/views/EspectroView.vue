<template>
  <div class="page-doc">
    <header class="page-doc-head">
      <h1 class="page-doc-title">Análisis espectral</h1>
      <p class="page-doc-sub">
        Mediciones de campo en frecuencia. Cargue una captura del instrumental
        como CSV y examínela junto a las bandas aeronáuticas.
      </p>
    </header>

    <div class="grid gap-4 lg:grid-cols-3">
      <!-- ── The spectrum ────────────────────────────────────────────── -->
      <section class="lg:col-span-2">
        <Chart
          v-if="points.length"
          :data="points"
          type="line"
          :height="380"
          title="Espectro cargado"
        />
        <div
          v-else
          class="grid place-items-center rounded-lg border border-dashed border-borde bg-[var(--fondo)] p-10 text-center"
        >
          <div>
            <div class="mb-2 text-2xl opacity-30">∿</div>
            <p class="text-sm text-texto-tenue">
              Todavía no hay ninguna medición cargada.
            </p>
            <p class="mt-1 text-xs text-texto-invisible">
              Use el panel de la derecha para elegir un archivo o pegar datos.
            </p>
          </div>
        </div>

        <!-- Which peaks land on an aeronautical band. This is the reason the
             screen exists, so it is a first-class result, not a footnote. -->
        <section v-if="inBand.length" class="mt-4">
          <h2 class="card-title">Picos dentro de banda aeronáutica</h2>
          <div class="card">
            <ul class="space-y-1.5">
              <li
                v-for="peak in inBand"
                :key="peak.freq"
                class="flex items-baseline justify-between gap-3 text-xs"
              >
                <span class="font-mono text-amber-200">
                  {{ peak.freq.toFixed(3) }} MHz
                </span>
                <span class="text-texto-tenue">{{ peak.band }}</span>
                <span class="font-mono text-texto-medio">{{ peak.db }} dB</span>
              </li>
            </ul>
            <p class="mt-2.5 text-[10px] leading-snug text-texto-invisible">
              Un pico dentro de una banda aeronáutica no prueba que exista
              interferencia: hay que comparar con la fuente conocida antes de
              sostener algo.
            </p>
          </div>
        </section>
      </section>

      <!-- ── Input ───────────────────────────────────────────────────── -->
      <section class="space-y-3">
        <div class="card">
          <h2 class="card-title">Cargar medición</h2>

          <label
            class="mb-2 flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border border-dashed border-borde-fuerte px-3 py-4 text-center transition-colors hover:border-sky-600 hover:bg-panel-hondo"
          >
            <span class="text-xs text-texto-tenue">
              Elegir archivo CSV o TXT
            </span>
            <span class="text-[10px] text-texto-invisible">
              Dos columnas: frecuencia en MHz y nivel en dB
            </span>
            <input
              type="file"
              accept=".csv,.txt,text/csv,text/plain"
              class="hidden"
              @change="onFile"
            />
          </label>

          <textarea
            v-model="pasted"
            rows="7"
            placeholder="…o pegue aquí las columnas, una por línea:&#10;100.000, -45&#10;108.700, -38&#10;121.500, -60"
            class="w-full rounded border border-borde-fuerte bg-panel-hondo px-2 py-1.5 font-mono text-[11px] text-texto outline-none placeholder:text-texto-invisible focus:border-sky-600"
          />

          <div class="mt-2 flex gap-1.5">
            <button
              class="flex-1 rounded bg-sky-700 px-2 py-1.5 text-xs font-medium text-white transition-colors hover:bg-sky-600"
              @click="onPaste"
            >
              Procesar
            </button>
            <button
              v-if="points.length"
              class="rounded border border-borde-fuerte px-2 py-1.5 text-xs text-texto-tenue hover:bg-panel-alto"
              title="Descartar la medición"
              @click="clear"
            >
              Limpiar
            </button>
          </div>

          <p v-if="error" class="mt-2 text-[11px] text-rose-300">
            {{ error }}
          </p>
          <p v-else-if="note" class="mt-2 text-[11px] text-texto-tenue">
            {{ note }}
          </p>
        </div>

        <!-- ── Reference bands ─────────────────────────────────────────
             Kept in the client on purpose: these are published reference
             values, not something the server has to know about, and putting
             them in an endpoint would make them look like measurements. -->
        <div class="card">
          <h2 class="card-title">Bandas aeronáuticas de referencia</h2>
          <ul class="space-y-1">
            <li
              v-for="band in AERO_BANDS"
              :key="band.label"
              class="flex items-baseline justify-between gap-2 text-[11px]"
            >
              <span class="text-texto-medio">{{ band.label }}</span>
              <span class="font-mono text-texto-tenue">
                {{ band.from }}–{{ band.to }} MHz
              </span>
            </li>
          </ul>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
/**
 * EspectroView.vue
 * ─────────────────
 * Loads a field measurement and plots it against the aeronautical bands.
 *
 * ── Why this is implemented and not stubbed ───────────────────────────────
 * The view was a placeholder: a box with the words "Gráfico de espectro
 * (Plotly)" and a "Procesar" button with no handler behind it. From the
 * sidebar it looked like a working section. A control that does nothing is
 * worse than no control, because it tells the operator a capability exists
 * that does not.
 *
 * The parsing is on the client because the measurement arrives as a file the
 * operator picks, and there is no spectrum table on the server: a measurement
 * is an observation the operator holds, not a record the system invented.
 *
 * The CSV format is deliberately forgiving, because field instruments never
 * agree: separators may be comma, semicolon or whitespace; rows may carry a
 * header; levels may be in dBm, dB or dBuV and are read as given, with the
 * unit stated rather than assumed.
 */
import { computed, ref } from 'vue'
import Chart from '@/components/Chart.vue'

/** Published aeronautical bands, for reference only. */
const AERO_BANDS = [
  { label: 'VHF banda aérea', from: 118.0, to: 137.0 },
  { label: 'Guionizada militar', from: 225.0, to: 400.0 },
  { label: 'Banda de vuelo ILS', from: 108.0, to: 117.95 },
  { label: 'VOR / Doppler', from: 108.0, to: 118.0 },
]

const pasted = ref('')
const points = ref([])
const error = ref('')
const note = ref('')

/** Peaks within `tolerance` dB of the maximum. */
const inBand = computed(() => {
  if (!points.value.length) return []
  const peak = points.value.reduce((a, b) => (b.db > a.db ? b : a))
  // A peak is only interesting if it stands above the noise of its own
  // measurement, so the threshold is relative rather than a magic number.
  const tolerance = Math.max(6, peak.db * 0.2)
  return points.value
    .filter((p) => p.db >= peak.db - tolerance)
    .map((p) => {
      const band = AERO_BANDS.find((b) => p.freq >= b.from && p.freq <= b.to)
      return { ...p, band: band ? band.label : 'fuera de banda aeronáutica' }
    })
    .filter((p) => p.band !== 'fuera de banda aeronáutica')
    .sort((a, b) => b.db - a.db)
    .slice(0, 12)
})

/**
 * Parse a measurement.
 *
 * Accepts `frecuencia, nivel` in either column order, with comma, semicolon
 * or whitespace as separator, and an optional header line. Rows that do not
 * parse are counted and reported rather than silently dropped: an operator
 * needs to know that half their file was not read.
 */
function parse(text) {
  const out = []
  let skipped = 0
  const lines = String(text || '').split(/\r?\n/)

  for (const raw of lines) {
    const line = raw.trim()
    if (!line || line.startsWith('#') || line.startsWith('//')) continue

    // Split on the first separator that is actually present.
    const parts = line.split(/[,;\t]|\s{1,}/).map((p) => p.trim()).filter(Boolean)
    if (parts.length < 2) {
      skipped += 1
      continue
    }

    const a = Number(parts[0].replace(',', '.'))
    const b = Number(parts[1].replace(',', '.'))
    if (!Number.isFinite(a) || !Number.isFinite(b)) {
      // A header row lands here, which is expected and not an error.
      if (parts.some((p) => Number.isNaN(Number(p.replace(',', '.'))))) continue
      skipped += 1
      continue
    }

    // Frequency first, in MHz. If the first column is the smaller of the two
    // and the second is large, the file has the columns the other way round.
    const [freq, db] = a > b ? [b, a] : [a, b]
    if (freq <= 0 || freq > 100000) {
      skipped += 1
      continue
    }
    out.push({ x: freq, y: db, db, freq, label: `${freq.toFixed(3)} MHz` })
  }

  out.sort((p, q) => p.freq - q.freq)
  return { out, skipped }
}

function apply(text, source) {
  error.value = ''
  note.value = ''
  const { out, skipped } = parse(text)
  if (!out.length) {
    error.value =
      'No se leyó ningún punto. Se esperan dos columnas numéricas por línea: ' +
      'frecuencia en MHz y nivel en dB.'
    points.value = []
    return
  }
  points.value = out
  const f0 = out[0].freq.toFixed(3)
  const f1 = out[out.length - 1].freq.toFixed(3)
  note.value =
    `${out.length} puntos de ${f0} a ${f1} MHz` +
    (skipped ? ` · ${skipped} línea(s) sin datos válidos omitidas` : '')
  if (skipped) {
    // Reported, because half a measurement read is worse than none.
    note.value += ` (${source})`
  }
}

function onPaste() {
  apply(pasted.value, 'texto pegado')
}

async function onFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  error.value = ''
  try {
    const text = await file.text()
    apply(text, file.name)
  } catch (e) {
    error.value = `No se pudo leer el archivo: ${e.message}`
  } finally {
    // Allow re-picking the same file.
    event.target.value = ''
  }
}

function clear() {
  points.value = []
  pasted.value = ''
  note.value = ''
  error.value = ''
}
</script>
