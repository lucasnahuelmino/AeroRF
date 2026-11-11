/**
 * tests/rf-calculadora.spec.js
 * ────────────────────────────
 * Fase 4 (AeroRF 2.5): la Calculadora RF en dos modos, sin matemática propia
 * y sin probabilidades inventadas.
 *
 * Lo que este archivo defiende, en orden:
 *
 *   1. El modo Armónicos calcula la diferencia en pantalla con la fórmula
 *      que dice la leyenda — `armónica = fundamental × orden` y
 *      `diferencia (kHz) = |armónica − referencia| × 1000` — y la resta la
 *      hace el frontend contra lo que devuelve `GET /rf/harmonics/{freq}`,
 *      no un motor espejo.
 *   2. Los tres estados son Exacta / En tolerancia / Fuera de tolerancia,
 *      con el límite inclusivo (`≤ tolerancia`), y jamás un porcentaje.
 *   3. El modo Intermodulación consume `POST /rf/calculate` y muestra las
 *      columnas del contrato (Emisora, Fundamental, Producto, Orden,
 *      Frecuencia calculada, Diferencia, Estado), el detalle y los
 *      «candidatos matemáticos» de `Referencia / 2|3|4`, etiquetados como
 *      aritmética y no como productos del motor.
 *   4. Exportar CSV/JSON exporta lo que se ve; limpiar no recalcula.
 *   5. Importar CSV agrega emisoras reales y sigue siendo sólo conversión
 *      de filas: `parseEmisorasCsv` no calcula nada.
 *
 * `fetch` se stubbea acá, como en `p011-guardar.spec.js`, para que se vea
 * qué endpoints necesita la pantalla.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'

// Los builders (CSV/JSON/nombre de archivo) y el parser quedan REALES: sólo
// se mockea `downloadText`, que es el clic del navegador — el contenido es
// lo que hay que mirar.
vi.mock('@/lib/rfFiles', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, downloadText: vi.fn() }
})

vi.mock('@/api/client', () => ({
  expedientes: {
    list: () => Promise.resolve([]),
    get: () => Promise.resolve({}),
    create: () => Promise.resolve({}),
    update: () => Promise.resolve({}),
    remove: () => Promise.resolve({}),
    mediciones: () => Promise.resolve([]),
    eventos: () => Promise.resolve([]),
    crearEvento: () => Promise.resolve({ id: 1 }),
  },
}))

import CalculadoraRFView from '@/views/CalculadoraRFView.vue'
import { downloadText, parseEmisorasCsv, buildCsv, nombreDeArchivo } from '@/lib/rfFiles'

// ─── Fixtures ────────────────────────────────────────────────────────────────

// Dos productos como los devuelve el motor en vivo con objetivo 119.0 MHz y
// las dos emisoras por defecto (88.5 y 58): el IM3 cae exacto y el IM5 a
// 4.5 kHz — ambos en tolerancia, que es lo único que el motor devuelve.
const IM3 = {
  result_mhz: 119.0,
  formula: '2×88.5 − 58',
  tipo: 'IM3',
  order: 3,
  error_khz: 0.0,
  score: 99,
  frequencies_involved: [88.5, 58],
}
const IM5 = {
  result_mhz: 119.0045,
  formula: '3×88.5 − 2×58',
  tipo: 'IM5',
  order: 5,
  error_khz: 4.5,
  score: 71,
  frequencies_involved: [88.5, 58],
}

const EXPEDIENTES = [
  { id: 7, numero_expediente: 'E-7', aeropuerto: 'EZE' },
  { id: 8, numero_expediente: 'E-8', aeropuerto: 'Aeroparque' },
]

const json = (body) => ({ ok: true, status: 200, json: async () => body })

/** Armónicos del backend: n × fundamental, sin filtrar (n = 2..max_order). */
const armonicosDe = (freq, maxOrder) => ({
  harmonics: Array.from({ length: Math.max(0, maxOrder - 1) }, (_, i) => {
    const n = i + 2
    return { order: n, freq_mhz: n * freq, tipo: `H${n}` }
  }),
})

const CUERPO_CALCUlADO = { matches: [IM3, IM5] }

let fetchStub
let calculos

const montar = async () => {
  const wrapper = mount(CalculadoraRFView, { global: { plugins: [createPinia()] } })
  await flushPromises()
  return wrapper
}

const pestaña = (wrapper, i) => wrapper.findAll('[role="tab"]')[i]

const boton = (wrapper, texto) =>
  wrapper.findAll('button').find((b) => b.text().includes(texto))

const llamadasCalculo = () =>
  fetchStub.mock.calls.filter(([u]) => String(u).startsWith('/api/v1/rf/calculate'))

const cuerpoCalculo = (i = -1) => {
  const calls = llamadasCalculo()
  const call = calls[i < 0 ? calls.length + i : i]
  return JSON.parse(call[1].body)
}

const tablaDe = (wrapper, modo) => wrapper.find(`[data-modo="${modo}"] table`)

const encabezadosDe = (tabla) => tabla.findAll('th').map((th) => th.text().trim())

const filasDe = (tabla) => tabla.findAll('tbody tr')

beforeEach(() => {
  calculos = 0
  downloadText.mockReset()

  fetchStub = vi.fn(async (url, options) => {
    const u = String(url)
    if (u.startsWith('/api/v1/expedientes')) return json(EXPEDIENTES)
    if (u.startsWith('/api/v1/rf/calculate')) {
      calculos += 1
      return json(CUERPO_CALCUlADO)
    }
    const m = u.match(/\/api\/v1\/rf\/harmonics\/([\d.]+)\?max_order=(\d+)/)
    if (m) return json(armonicosDe(Number(m[1]), Number(m[2])))
    return json({})
  })
  vi.stubGlobal('fetch', fetchStub)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ─── Modo A · Armónicos ──────────────────────────────────────────────────────

describe('modo Armónicos', () => {
  it('es el modo por defecto y trae los armónicos de cada emisora', async () => {
    const w = await montar()

    expect(pestaña(w, 0).attributes('aria-selected')).toBe('true')
    expect(pestaña(w, 1).attributes('aria-selected')).toBe('false')
    expect(w.find('[data-modo="a"]').isVisible()).toBe(true)
    expect(w.find('[data-modo="b"]').isVisible()).toBe(false)

    // Dos emisoras por defecto → dos pedidos de armónicos, con órdenes 2..4.
    const pedidos = fetchStub.mock.calls.filter(([u]) =>
      String(u).includes('/rf/harmonics/')
    )
    expect(pedidos.map(([u]) => String(u))).toEqual([
      '/api/v1/rf/harmonics/88.5?max_order=4',
      '/api/v1/rf/harmonics/58?max_order=4',
    ])
  })

  it('muestra la tabla por emisora con fórmula, diferencia y estado', async () => {
    const w = await montar()
    const tabla = tablaDe(w, 'a')

    expect(encabezadosDe(tabla)).toEqual([
      'Emisora',
      'Fundamental',
      '2.ª armónica',
      '3.ª armónica',
      '4.ª armónica',
      'Mejor diferencia (kHz)',
      'Estado',
    ])

    // Orden por diferencia absoluta: 58 MHz está a 3000 kHz de 119 y
    // 88.5 MHz a 58000 kHz, así que la de 58 va primero.
    const filas = filasDe(tabla)
    expect(filas).toHaveLength(2)

    const [tv, fm] = filas.map((f) => f.text().replace(/\s+/g, ' '))
    expect(tv).toContain('TV Señal')
    expect(tv).toContain('58.000000')
    expect(tv).toContain('116.000000') // 58 × 2
    expect(tv).toContain('Δ 3000.000 kHz') // |116 − 119| × 1000
    expect(tv).toContain('3000.000')
    expect(tv).toContain('Fuera de tolerancia')

    expect(fm).toContain('FM Radio')
    expect(fm).toContain('177.000000') // 88.5 × 2
    expect(fm).toContain('Δ 58000.000 kHz')
    expect(fm).toContain('Fuera de tolerancia')

    // La leyenda dice la cuenta que después se ve hecha en las celdas.
    expect(w.text()).toContain('armónica = fundamental × orden')
    expect(w.text()).toContain('diferencia (kHz) = |armónica − referencia| × 1000')
  })

  it('el Exacta aparece cuando una armónica cae justo sobre la referencia', async () => {
    const w = await montar()

    // 58 × 2 = 116 → Exacta contra 116; 88.5 × 2 = 177 queda a 61000 kHz.
    await w.find('#calc-referencia').setValue('116')
    await flushPromises()

    const filas = filasDe(tablaDe(w, 'a')).map((f) => f.text().replace(/\s+/g, ' '))
    expect(filas[0]).toContain('TV Señal')
    expect(filas[0]).toContain('0.000')
    expect(filas[0]).toContain('Exacta')
    expect(filas[1]).toContain('FM Radio')
    expect(filas[1]).toContain('61000.000')

    // Recalcular la resta no vuelve a llamar al backend: la diferencia es
    // resta contra lo que ya se cargó.
    expect(calculos).toBe(1)
  })

  it('la tolerancia decide En tolerancia o Fuera, con el límite inclusivo', async () => {
    const w = await montar()
    await w.find('#calc-referencia').setValue('116')
    await w.find('#calc-tolerancia').setValue('61000')
    await flushPromises()

    const mejor = () => filasDe(tablaDe(w, 'a'))[1].text().replace(/\s+/g, ' ')
    expect(mejor()).toContain('61000.000')
    expect(mejor()).toContain('En tolerancia')

    // Un kHz menos y la misma diferencia queda afuera: el borde es ≤.
    await w.find('#calc-tolerancia').setValue('60999')
    await flushPromises()
    expect(mejor()).toContain('Fuera de tolerancia')
  })
})

// ─── Modo B · Intermodulación ────────────────────────────────────────────────

describe('modo Intermodulación', () => {
  it('arma las siete columnas del contrato y ordena por diferencia', async () => {
    const w = await montar()
    await pestaña(w, 1).trigger('click')

    const tabla = tablaDe(w, 'b')
    expect(w.find('[data-modo="b"]').isVisible()).toBe(true)

    expect(encabezadosDe(tabla)).toEqual([
      'Emisora',
      'Fundamental',
      'Producto',
      'Orden',
      'Frecuencia calculada',
      'Diferencia (kHz)',
      'Estado',
    ])

    const filas = filasDe(tabla).map((f) => f.text().replace(/\s+/g, ' '))
    expect(filas).toHaveLength(2)

    // Primero la diferencia 0, después la de 4.5 kHz.
    expect(filas[0]).toContain('2×88.5 − 58')
    expect(filas[0]).toContain('IM3')
    expect(filas[0]).toContain('FM Radio + TV Señal')
    expect(filas[0]).toContain('88.5 MHz + 58 MHz')
    expect(filas[0]).toContain('119.000000 MHz')
    expect(filas[0]).toContain('0.000')
    expect(filas[0]).toContain('Exacta')

    expect(filas[1]).toContain('3×88.5 − 2×58')
    expect(filas[1]).toContain('4.500')
    expect(filas[1]).toContain('En tolerancia')
  })

  it('el detalle explica el producto seleccionado con su fórmula', async () => {
    const w = await montar()
    await pestaña(w, 1).trigger('click')

    // Tras calcular, el detalle arranca en la primera fila (menor diferencia).
    const tituloDetalle = () =>
      w.findAll('h3').find((h) => h.text().includes('Análisis detallado'))
    expect(tituloDetalle()).toBeTruthy()
    expect(w.text()).toContain('2×88.5 − 58')
    expect(w.text()).toContain('IM3 · orden 3')
    expect(w.text()).toContain('coincide exactamente con la referencia de 119')

    // Al elegir la otra fila, el detalle cambia con ella.
    const filas = filasDe(tablaDe(w, 'b'))
    await filas[1].trigger('click')
    await flushPromises()

    expect(w.text()).toContain('3×88.5 − 2×58')
    expect(w.text()).toContain('119.004500 MHz')
    expect(w.text()).toContain('4.500 kHz')
    expect(w.text()).toContain('en tolerancia')
    expect(tituloDetalle()).toBeTruthy()
  })

  it('lista los inversos como candidatos matemáticos, no como productos', async () => {
    const w = await montar()
    await pestaña(w, 1).trigger('click')

    expect(w.text()).toContain('Candidatos matemáticos')
    expect(w.text()).toContain('No son productos de intermodulación calculados por el motor')

    // La tabla de inversos es la segunda dentro del modo B (la primera es
    // la del motor): los dos órdenes conviven, con etiquetas distintas.
    const tablas = w.findAll('[data-modo="b"] table')
    expect(tablas.length).toBeGreaterThanOrEqual(2)
    const inversos = tablas[1].findAll('tbody tr').map((r) => r.text().replace(/\s+/g, ' '))

    expect(inversos).toHaveLength(3)
    expect(inversos[0]).toContain('Referencia / 2')
    expect(inversos[0]).toContain('59.500000 MHz')
    expect(inversos[1]).toContain('Referencia / 3')
    expect(inversos[1]).toContain('39.666667 MHz')
    expect(inversos[2]).toContain('Referencia / 4')
    expect(inversos[2]).toContain('29.750000 MHz')
    for (const fila of inversos) {
      expect(fila).toContain('Candidato matemático')
      expect(fila).not.toContain('IM')
    }
  })

  it('exporta CSV y JSON con lo que se está viendo', async () => {
    const w = await montar()
    await pestaña(w, 1).trigger('click')

    await boton(w, 'Exportar CSV').trigger('click')
    expect(downloadText).toHaveBeenCalledTimes(1)
    const [nombreCsv, contenidoCsv, mimeCsv] = downloadText.mock.calls[0]
    expect(nombreCsv).toMatch(/^AeroRF_Intermodulacion_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.csv$/)
    expect(mimeCsv).toContain('text/csv')
    // BOM para que Excel lea UTF-8, encabezados y las dos filas visibles.
    expect(contenidoCsv.startsWith('\ufeff')).toBe(true)
    expect(contenidoCsv).toContain('Emisora,Fundamental (MHz),Producto')
    expect(contenidoCsv).toContain('2×88.5 − 58')
    expect(contenidoCsv).toContain('3×88.5 − 2×58')
    expect(contenidoCsv).toContain('Exacta')
    expect(w.text()).toContain('CSV exportado con 2 productos')

    await boton(w, 'Exportar JSON').trigger('click')
    expect(downloadText).toHaveBeenCalledTimes(2)
    const [nombreJson, contenidoJson, mimeJson] = downloadText.mock.calls[1]
    expect(nombreJson).toMatch(/^AeroRF_Intermodulacion_.*\.json$/)
    expect(mimeJson).toContain('application/json')

    const datos = JSON.parse(contenidoJson)
    expect(datos.calculadora).toContain('Intermodulación')
    expect(datos.parametros.frecuencia_referencia_mhz).toBe(119)
    expect(datos.parametros.tolerancia_khz).toBe(10)
    expect(datos.emisoras.map((e) => e.freq_mhz)).toEqual([88.5, 58])
    expect(datos.candidatos_matematicos.map((c) => c.frecuencia_mhz)).toEqual([
      59.5, 39.666667, 29.75,
    ])
    expect(datos.respuesta.matches).toHaveLength(2)
    expect(datos.solicitud.target_mhz).toBe(119)
  })

  it('limpiar vacía todo sin recalcular, y volver a calcular repite el pedido', async () => {
    const w = await montar()
    await pestaña(w, 1).trigger('click')
    expect(calculos).toBe(1)

    await boton(w, 'Limpiar cálculo').trigger('click')
    await flushPromises()

    expect(w.find('[data-modo="b"]').text()).toContain('Ejecutá un cálculo para ver resultados')
    expect(w.text()).not.toContain('Análisis detallado')
    expect(downloadText).not.toHaveBeenCalled()
    expect(calculos).toBe(1) // limpiar es limpiar, no recalcular

    await boton(w, 'Volver a calcular').trigger('click')
    await flushPromises()
    expect(calculos).toBe(2)
    expect(filasDe(tablaDe(w, 'b'))).toHaveLength(2)
  })

  it('un fallo del motor se muestra al lado del botón, en cualquier modo', async () => {
    fetchStub = vi.fn(async (url) => {
      const u = String(url)
      if (u.startsWith('/api/v1/expedientes')) return json(EXPEDIENTES)
      if (u.startsWith('/api/v1/rf/calculate')) return { ok: false, status: 500, json: async () => ({}) }
      const m = u.match(/\/api\/v1\/rf\/harmonics\/([\d.]+)\?max_order=(\d+)/)
      if (m) return json(armonicosDe(Number(m[1]), Number(m[2])))
      return json({})
    })
    vi.stubGlobal('fetch', fetchStub)

    const w = await montar()
    const alertas = () => w.findAll('[role="alert"]').map((a) => a.text())
    expect(alertas().join(' ')).toContain('No se pudo calcular')

    // El aviso vive en el panel de parámetros: cambiar de pestaña no lo esconde.
    await pestaña(w, 1).trigger('click')
    expect(alertas().join(' ')).toContain('No se pudo calcular')
  })
})

// ─── Sin probabilidades inventadas ───────────────────────────────────────────

describe('el discurso de la calculadora', () => {
  it('habla de diferencias y estados, nunca de scores ni porcentajes', async () => {
    const w = await montar()
    await pestaña(w, 1).trigger('click')
    await flushPromises()

    const texto = w.text()
    expect(texto).not.toMatch(/Proximidad/i)
    expect(texto).not.toMatch(/Distribución/i)
    expect(texto).not.toMatch(/probabilidad/i)
    expect(texto).not.toMatch(/score/i)
    expect(texto).not.toContain('%')

    // Lo que sí tiene que decir son los tres estados y la cuenta.
    expect(texto).toContain('Exacta')
    expect(texto).toContain('En tolerancia')
    expect(texto).toContain('Fuera de tolerancia')
    expect(texto).toContain('diferencia (kHz) = |armónica − referencia| × 1000')
  })
})

// ─── Emisoras: alta manual ───────────────────────────────────────────────────

describe('alta manual de emisoras', () => {
  it('agrega con señal FM por defecto y sin mandar potencia vacía al motor', async () => {
    const w = await montar()

    await w.find('input[placeholder="Ej: 119.0"]').setValue('96.5')
    await w.find('input[placeholder="Ej: FM Radio Local"]').setValue('Link microondas')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(w.text()).toContain('Emisora agregada: Link microondas.')
    expect(w.text()).toContain('Emisoras (3)')

    await boton(w, '🚀 Calcular').trigger('click')
    await flushPromises()

    const payload = cuerpoCalculo()
    expect(payload.frequencies).toHaveLength(3)
    const nueva = payload.frequencies.find((f) => f.freq_mhz === 96.5)
    expect(nueva).toBeTruthy()
    expect(nueva.signal_type).toBe('FM')
    expect(nueva.label).toBe('Link microondas')
    // Sin potencia cargada no se manda el campo: `power_dbm: ""` produciría
    // un 422 del backend. Nunca un valor que no sea número.
    expect('power_dbm' in nueva).toBe(false)
    for (const f of payload.frequencies) {
      expect(typeof f.power_dbm === 'number' || !('power_dbm' in f)).toBe(true)
    }

    // Con potencia cargada, sí viaja como número.
    await w.find('input[placeholder="Ej: 119.0"]').setValue('97.3')
    await w.find('input[placeholder="Ej: 30"]').setValue('25')
    await w.find('form').trigger('submit')
    await flushPromises()
    await boton(w, '🚀 Calcular').trigger('click')
    await flushPromises()

    const conPotencia = cuerpoCalculo().frequencies.find((f) => f.freq_mhz === 97.3)
    expect(conPotencia.power_dbm).toBe(25)
  })

  it('rechaza frecuencias fuera del rango sin agregarlas', async () => {
    const w = await montar()

    for (const invalida of ['0', '6000']) {
      await w.find('input[placeholder="Ej: 119.0"]').setValue(invalida)
      await w.find('form').trigger('submit')
      await flushPromises()
      expect(w.text()).toContain(
        'La frecuencia tiene que ser mayor a 0 y menor a 6000 MHz.'
      )
      expect(w.text()).toContain('Emisoras (2)')
    }
  })

  it('quita una emisora de la lista compartida', async () => {
    const w = await montar()
    expect(w.text()).toContain('Emisoras (2)')
    expect(w.findAll('button[title="Quitar emisora"]')).toHaveLength(2)

    await w.findAll('button[title="Quitar emisora"]')[0].trigger('click')
    await flushPromises()

    // La lista alimenta los dos modos: sacar de acá saca de ambos.
    expect(w.text()).toContain('Emisoras (1)')
    expect(w.findAll('button[title="Quitar emisora"]')).toHaveLength(1)
    await boton(w, '🚀 Calcular').trigger('click')
    await flushPromises()
    const payload = cuerpoCalculo()
    expect(payload.frequencies.map((f) => f.freq_mhz)).toEqual([58])
    expect(
      fetchStub.mock.calls.filter(([u]) => String(u).includes('/rf/harmonics/'))
    ).toHaveLength(3) // 2 en el montaje + 1 al recalcular sin la emisora quitada
  })
})

// ─── Importación CSV ─────────────────────────────────────────────────────────

describe('parseEmisorasCsv (sólo convierte filas)', () => {
  it('lee encabezados y columnas por nombre', () => {
    const { agregadas, errores } = parseEmisorasCsv(
      'nombre,frecuencia,observaciones\nFM Uno,88.5,transmite de noche\n'
    )
    expect(errores).toEqual([])
    expect(agregadas).toEqual([
      {
        freq_mhz: 88.5,
        label: 'FM Uno',
        signal_type: 'FM',
        observaciones: 'transmite de noche',
      },
    ])
  })

  it('admite punto y coma con coma decimal', () => {
    const { agregadas, errores } = parseEmisorasCsv(
      'nombre;frecuencia;observaciones\nFM Dos;88,5;nota\n'
    )
    expect(errores).toEqual([])
    expect(agregadas).toHaveLength(1)
    expect(agregadas[0].freq_mhz).toBe(88.5)
    expect(agregadas[0].label).toBe('FM Dos')
  })

  it('sin encabezado asume nombre,frecuencia,observaciones', () => {
    const { agregadas, errores } = parseEmisorasCsv('Radio Local,101.7\nOtra,92.1,comentario\n')
    expect(errores).toEqual([])
    expect(agregadas.map((a) => [a.label, a.freq_mhz])).toEqual([
      ['Radio Local', 101.7],
      ['Otra', 92.1],
    ])
    expect(agregadas[1].observaciones).toBe('comentario')
  })

  it('las filas malas quedan numeradas y no frenan a las buenas', () => {
    const { agregadas, errores } = parseEmisorasCsv(
      'nombre,frecuencia\nBuena,88.5\nMala,abc\nTambién mala,0\n'
    )
    expect(agregadas).toHaveLength(1)
    expect(errores).toEqual([
      'Fila 3: frecuencia inválida («abc»).',
      'Fila 4: frecuencia inválida («0»).',
    ])
  })

  it('sin columna de frecuencia no adivina: se rinde con un error claro', () => {
    const { agregadas, errores } = parseEmisorasCsv('nombre,observaciones\nA,sin frecuencia\n')
    expect(agregadas).toEqual([])
    expect(errores[0]).toContain('columna de frecuencia')
  })

  it('un archivo vacío se reporta como vacío', () => {
    const { agregadas, errores } = parseEmisorasCsv('\n  \n')
    expect(agregadas).toEqual([])
    expect(errores).toEqual(['El archivo está vacío.'])
  })
})

describe('buildCsv (escritura segura)', () => {
  it('anteponen apóstrofo a lo que una planilla ejecutaría como fórmula', () => {
    const csv = buildCsv([['=1+1', '@SUMA', '+5', '-5', '88,5']])
    expect(csv).toContain("'=1+1")
    expect(csv).toContain("'@SUMA")
    expect(csv).toContain("'+5")
    expect(csv).toContain('-5') // un negativo es número, no fórmula
    expect(csv).toContain('"88,5"') // la coma obliga a comillas
  })

  it('empieza con BOM para que Excel lea UTF-8', () => {
    expect(buildCsv([['a']]).startsWith('\ufeff')).toBe(true)
  })
})

describe('nombreDeArchivo', () => {
  it('sigue el patrón AeroRF con fecha y hora', () => {
    expect(nombreDeArchivo('Intermodulacion', 'csv')).toMatch(
      /^AeroRF_Intermodulacion_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.csv$/
    )
  })
})

describe('importar CSV desde la pantalla', () => {
  it('lee el archivo y agrega las emisoras a la lista', async () => {
    const w = await montar()
    const antes = w.text().match(/Emisoras \((\d+)\)/)[1]

    const archivo = new File(
      ['nombre,frecuencia\nJazz,88.9\nRota,abc\n'],
      'emisoras.csv',
      { type: 'text/csv' }
    )
    const input = w.find('#calc-csv')
    Object.defineProperty(input.element, 'files', { value: [archivo], configurable: true })
    await input.trigger('change')
    await new Promise((resolve) => setTimeout(resolve, 10))
    await flushPromises()

    expect(w.text()).toContain(`Emisoras (${Number(antes) + 1})`)
    expect(w.text()).toContain('CSV importado: 1 emisora agregada.')
    expect(w.text()).toContain('Fila 3: frecuencia inválida («abc»).')
    expect(w.text()).toContain('88.9 MHz')
    expect(w.text()).toContain('Jazz')
  })
})
