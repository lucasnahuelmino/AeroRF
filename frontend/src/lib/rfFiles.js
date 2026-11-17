/**
 * src/lib/rfFiles.js
 * ───────────────────
 * Lectura y escritura de archivos de la Calculadora RF (Fase 4, AeroRF 2.5).
 *
 * Tres funciones puras — `parseEmisorasCsv`, `buildCsv`, `buildJson` — y una
 * sola con I/O (`downloadText`), para que el formato se pruebe sin navegador.
 *
 * Lo que NO hace este módulo: matemática de RF. Los armónicos salen de
 * `GET /rf/harmonics/{freq}` y los productos de intermodulación de
 * `POST /rf/calculate`; acá sólo se empaqueta y formatea lo que el backend ya
 * calculó (y la importación, que sólo convierte filas de texto en emisoras).
 */

/** `AeroRF_Intermodulacion_2026-11-10_10-15-00.csv` — mismo formato que la
 *  exportación del mapa (`AeroRF_Mapa_…`), con fecha y hora para que dos
 *  corridas nunca se pisen. */
export function nombreDeArchivo(seccion, ext) {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  const fecha = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
  const hora = `${p(d.getHours())}-${p(d.getMinutes())}-${p(d.getSeconds())}`
  return `AeroRF_${seccion}_${fecha}_${hora}.${ext}`
}

/**
 * Celda CSV segura.
 *
 * Dos reglas, en este orden:
 *  1. Inyección de fórmulas: un valor que arranca con `=`, `+`, `@` (o `-`
 *     seguido de algo que no sea un número) se anteponce con `'`, que es lo
 *     que Excel/Sheets interpretan como «esto es texto, no lo ejecutes».
 *     Un número negativo como `-5` NO se toca: es un número, no una fórmula.
 *  2. Comillas: si el valor trae coma, comilla doble o salto de línea, va
 *     entre comillas dobles, con las comillas internas duplicadas (RFC 4180).
 */
function celdaCsv(valor) {
  let s = valor === null || valor === undefined ? '' : String(valor)
  if (/^[=+@]/.test(s) || /^-(?![\d.])/.test(s)) s = `'${s}`
  if (/[",\n\r]/.test(s)) s = `"${s.replace(/"/g, '""')}"`
  return s
}

/** Filas (arrays de celdas) → texto CSV con BOM, para que Excel lea UTF-8. */
export function buildCsv(filas) {
  const lineas = filas.map((fila) => fila.map(celdaCsv).join(','))
  return `\ufeff${lineas.join('\r\n')}\r\n`
}

/** Objeto → JSON indentado (legible en cualquier editor). */
export function buildJson(objeto) {
  return `${JSON.stringify(objeto, null, 2)}\n`
}

/**
 * CSV de emisoras → filas listas para la lista compartida de la calculadora.
 *
 * Parser CSV robusto (AeroRF 2.6, Bloque 2): soporta comillas, comillas
 * escapadas (`""`), campos multilínea, BOM UTF-8, separadores `,` y `;` y
 * detección del separador decimal por columna y por separador de campos.
 *
 * Contrato de columnas (encabezados aceptados, case/acento-insensibles):
 *   nombre | emisora | estacion | estación | identificador   → label
 *   frecuencia | frecuencia_mhz | mhz | frequency | freq         → freq_mhz
 *   observaciones | observacion | nota | comment              → observaciones
 *   localidad | ciudad                                            → se agrega a observaciones
 *   provincia | province                                         → se agrega a observaciones
 *
 * Sin encabezado se asume el orden `nombre, frecuencia, observaciones`.
 *
 * Rango de frecuencia: mayor a 0 y menor a 6000 MHz, el mismo que valida el
 * motor en `FrequencyInput` (`app/models/rf_models.py`). El rango FM habitual
 * (87.5–108 MHz) es un subconjunto: se aceptan otras bandas porque el motor
 * no las rechaza, y la validación final la hace el backend.
 *
 * Separador decimal:
 *   - Con `;` (formato europeo/argentino) se admite coma o punto decimal
 *     (`88,5` y `88.5`); si aparecen los dos en un mismo valor se rechaza
 *     por ambiguo (no se interpretan miles).
 *   - Con `,` (CSV estándar) el decimal es el punto; una coma sobreviviente
 *     dentro de un campo se considera inválida.
 *
 * Devuelve `{ agregadas, errores, resumen }`:
 *   - `agregadas`: emisoras listas para la lista compartida.
 *   - `errores`: motivos de rechazo (filas inválidas y duplicadas), con el
 *     número de fila del archivo (1-based, incluyendo el encabezado).
 *   - `resumen`: { leidas, validas, importadas, duplicados, rechazadas }.
 *
 * No descarta filas silenciosamente: toda fila leída termina en `agregadas`
 * o en `errores`. Los duplicados (misma etiqueta + frecuencia) se rechazan
 * con aviso en vez de agregarse dos veces.
 */
export function parseEmisorasCsv(texto) {
  const vacio = { agregadas: [], errores: ['El archivo está vacío.'], resumen: { leidas: 0, validas: 0, importadas: 0, duplicados: 0, rechazadas: 0 } }

  const crudo = String(texto || '')
  const sinBom = crudo.charCodeAt(0) === 0xfeff ? crudo.slice(1) : crudo
  if (sinBom.trim() === '') return vacio

  const separador = detectarSeparador(sinBom)
  const registros = parsearCsv(sinBom, separador)
  const filas = registros.filter((r) => r.some((c) => String(c).trim() !== ''))
  if (filas.length === 0) return vacio

  const sinonimos = {
    nombre: ['nombre', 'name', 'emisora', 'estacion', 'identificador', 'id'],
    frecuencia: ['frecuencia', 'frecuenciamhz', 'mhz', 'frequency', 'freq', 'frec'],
    observaciones: ['observaciones', 'observacion', 'nota', 'notes', 'comment', 'comments', 'observ'],
    localidad: ['localidad', 'ciudad', 'city'],
    provincia: ['provincia', 'province', 'estado'],
  }
  const todos = new Set(Object.values(sinonimos).flat())
  const esSinonimo = (n) => todos.has(n)
  const normalizar = (s) =>
    String(s || '')
      .trim()
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]/g, '')

  let tieneEncabezado = filas[0].map(normalizar).some(esSinonimo)
  const columnas = { nombre: -1, frecuencia: -1, observaciones: -1, localidad: -1, provincia: -1 }
  let desde = 0

  if (tieneEncabezado) {
    filas[0].forEach((cell, idx) => {
      const n = normalizar(cell)
      for (const [rol, lista] of Object.entries(sinonimos)) {
        if (columnas[rol] < 0 && lista.includes(n)) {
          columnas[rol] = idx
        }
      }
    })
    if (columnas.frecuencia < 0) {
      return {
        agregadas: [],
        errores: ['El CSV necesita una columna de frecuencia (columnas esperadas: nombre, frecuencia, observaciones).'],
        resumen: { leidas: 0, validas: 0, importadas: 0, duplicados: 0, rechazadas: 0 },
      }
    }
    desde = 1
  } else {
    // Sin encabezado: nombre, frecuencia, observaciones.
    columnas.nombre = 0
    columnas.frecuencia = 1
    columnas.observaciones = 2
    desde = 0
  }

  const FREC_MIN = 0
  const FREC_MAX = 6000

  const agregadas = []
  const errores = []
  const vistos = new Set()
  let leidas = 0
  let validas = 0
  let duplicados = 0
  let rechazadas = 0

  const parsearFrecuencia = (texto) => {
    const raw = String(texto || '').trim()
    if (raw === '') return NaN
    const tieneComa = raw.includes(',')
    const tienePunto = raw.includes('.')
    if (tieneComa && tienePunto) return NaN // ambiguo: no se interpretan miles
    let normalizado = raw
    if (separador === ';') {
      normalizado = raw.replace(',', '.')
    } else if (tieneComa) {
      return NaN
    }
    const n = Number(normalizado)
    return n
  }

  for (let i = desde; i < filas.length; i++) {
    const c = filas[i]
    if (c.every((x) => String(x).trim() === '')) continue
    leidas++

    const textoFreq = columnas.frecuencia >= 0 && c[columnas.frecuencia] !== undefined
      ? String(c[columnas.frecuencia]).trim()
      : ''
    const freq = parsearFrecuencia(textoFreq)
    if (!Number.isFinite(freq) || freq <= FREC_MIN || freq >= FREC_MAX) {
      errores.push(`Fila ${i + 1}: frecuencia inválida («${textoFreq}»).`)
      rechazadas++
      continue
    }

    const nombreRaw = columnas.nombre >= 0 && c[columnas.nombre] !== undefined
      ? String(c[columnas.nombre]).trim()
      : ''
    const nombre = nombreRaw || `Emisora ${agregadas.length + 1}`

    const obsParts = []
    if (columnas.observaciones >= 0 && c[columnas.observaciones] !== undefined) {
      const v = String(c[columnas.observaciones]).trim()
      if (v) obsParts.push(v)
    }
    if (columnas.localidad >= 0 && c[columnas.localidad] !== undefined) {
      const v = String(c[columnas.localidad]).trim()
      if (v) obsParts.push(`Localidad: ${v}`)
    }
    if (columnas.provincia >= 0 && c[columnas.provincia] !== undefined) {
      const v = String(c[columnas.provincia]).trim()
      if (v) obsParts.push(`Provincia: ${v}`)
    }
    const obs = obsParts.join(' · ')

    validas++
    const clave = `${nombre.toLowerCase()}|${Math.round(freq * 1e6)}`
    if (vistos.has(clave)) {
      errores.push(`Fila ${i + 1}: emisora duplicada («${nombre} · ${freq} MHz»).`)
      duplicados++
      continue
    }
    vistos.add(clave)

    agregadas.push({
      freq_mhz: Math.round(freq * 1e6) / 1e6,
      label: nombre.slice(0, 80),
      signal_type: 'FM',
      observaciones: obs,
    })
  }

  if (leidas === 0) return vacio

  const resumen = { leidas, validas, importadas: agregadas.length, duplicados, rechazadas }
  return { agregadas, errores, resumen }
}

// ─── Helpers del parser CSV ─────────────────────────────────────────────────

function detectarSeparador(texto) {
  let enComillas = false
  let comas = 0
  let puntosYComa = 0
  for (let i = 0; i < texto.length; i++) {
    const ch = texto[i]
    if (ch === '"') {
      if (enComillas && texto[i + 1] === '"') { i++; continue }
      enComillas = !enComillas
    } else if (!enComillas) {
      if (ch === '\n' || ch === '\r') break
      if (ch === ',') comas++
      else if (ch === ';') puntosYComa++
    }
  }
  return puntosYComa > comas ? ';' : ','
}

function parsearCsv(texto, separador) {
  const registros = []
  let fila = []
  let campo = ''
  let enComillas = false
  let alInicio = true
  const n = texto.length
  let i = 0
  while (i < n) {
    const ch = texto[i]
    if (enComillas) {
      if (ch === '"') {
        if (texto[i + 1] === '"') {
          campo += '"'
          i += 2
          continue
        }
        enComillas = false
        i++
        continue
      }
      campo += ch
      i++
      continue
    }
    if (ch === '"') {
      if (campo === '' && alInicio) {
        enComillas = true
        i++
        continue
      }
      campo += ch
      alInicio = false
      i++
      continue
    }
    if (ch === separador) {
      fila.push(campo)
      campo = ''
      alInicio = true
      i++
      continue
    }
    if (ch === '\r') {
      i++
      continue
    }
    if (ch === '\n') {
      fila.push(campo)
      registros.push(fila)
      fila = []
      campo = ''
      alInicio = true
      i++
      continue
    }
    campo += ch
    alInicio = false
    i++
    continue
  }
  if (fila.length > 0 || campo !== '') {
    fila.push(campo)
    registros.push(fila)
  }
  return registros
}

/**
 * Descarga un texto como archivo. Mismo patrón que la exportación del mapa:
 * Blob → object URL → clic → revoke. (En los tests esto queda mockeado; lo
 * que se prueba es el contenido, no el clic del navegador.)
 */
export function downloadText(nombre, texto, mime = 'text/plain;charset=utf-8') {
  const blob = new Blob([texto], { type: mime })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = nombre
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
