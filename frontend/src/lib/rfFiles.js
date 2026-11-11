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
 * Contrato de columnas: `nombre`, `frecuencia` (MHz), `observaciones`.
 *  - Con encabezado: se buscan las columnas por nombre (admite también
 *    `name`/`frequency`/`observations`); sin columna de frecuencia, se rinde
 *    con un error claro en lugar de adivinar.
 *  - Sin encabezado: se asume el orden `nombre,frecuencia,observaciones`.
 *  - Delimitador: `;` si la primera línea usa punto y coma y no coma; en ese
 *    formato se admite también la coma decimal (`88,5` → 88.5).
 *  - Frecuencia: tiene que ser > 0 y < 6000 (el mismo rango que valida el
 *    backend en `FrequencyInput`). Las filas malas no frenan a las buenas:
 *    quedan en `errores`, numeradas como en el archivo.
 */
export function parseEmisorasCsv(texto) {
  const agregadas = []
  const errores = []
  const lineas = String(texto || '')
    .split(/\r?\n/)
    .filter((l) => l.trim() !== '')
  if (lineas.length === 0) return { agregadas, errores: ['El archivo está vacío.'] }

  const separador = lineas[0].includes(';') && !lineas[0].includes(',') ? ';' : ','
  const celdas = (linea) => linea.split(separador).map((c) => c.trim())
  const aNumero = (s) => Number(separador === ';' ? String(s).replace(',', '.') : s)
  const esNumero = (s) => s !== '' && Number.isFinite(aNumero(s))

  let iNombre = 0
  let iFreq = 1
  let iObs = 2
  let desde = 0

  const primera = celdas(lineas[0])
  if (!esNumero(primera[1] || '')) {
    // Fila de encabezado: se ubican las columnas por su nombre.
    iNombre = primera.findIndex((c) => /nombre|name|emisora|estaci/i.test(c))
    iFreq = primera.findIndex((c) => /frec|freq/i.test(c))
    iObs = primera.findIndex((c) => /observ|nota|comment/i.test(c))
    if (iFreq < 0) {
      return {
        agregadas,
        errores: [
          'El CSV necesita una columna de frecuencia (columnas esperadas: nombre, frecuencia, observaciones).',
        ],
      }
    }
    desde = 1
  }

  for (let i = desde; i < lineas.length; i++) {
    const c = celdas(lineas[i])
    const textoFreq = c[iFreq] !== undefined ? c[iFreq] : ''
    const freq = aNumero(textoFreq)
    if (!Number.isFinite(freq) || freq <= 0 || freq >= 6000) {
      errores.push(`Fila ${i + 1}: frecuencia inválida («${textoFreq}»).`)
      continue
    }
    const nombre = (iNombre >= 0 ? c[iNombre] : '') || `Emisora ${agregadas.length + 1}`
    const obs = iObs >= 0 ? c[iObs] || '' : ''
    agregadas.push({
      freq_mhz: Math.round(freq * 1e6) / 1e6,
      label: nombre.slice(0, 80),
      signal_type: 'FM',
      observaciones: obs,
    })
  }

  return { agregadas, errores }
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
