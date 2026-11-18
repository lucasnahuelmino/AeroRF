/**
 * tests/p011-guardar.spec.js
 * ─────────────────────────
 * P0-11, evolución AeroRF 2.6 (Bloque 1).
 *
 * El defecto original era este, y no otra cosa:
 *
 *     const storeResult = () => {
 *       alert('Resultado guardado (próximamente integrado con expediente)')
 *     }
 *
 * El `alert` afirmaba que algo se guardó sin que existiera escritura alguna.
 * El arreglo (AeroRF 2.5) fue guardar de verdad en `POST /expedientes/{id}/
 * eventos`; el destino lo eligía un selector de expedientes que la pantalla
 * no tenía por qué tener.
 *
 * AeroRF 2.6 retira esa dependencia: la calculadora guarda en su propio
 * historial (`POST /rf/analisis`), con identidad propia y sin ningún
 * expediente. Estas pruebas protegen lo mismo que antes, ahora contra el
 * nuevo destino:
 *
 *   1. Que no queda rastro del selector ni del botón «Guardar en Expediente»,
 *      ni en el DOM ni en el código fuente de la vista.
 *   2. Que guardar manda al backend exactamente lo que se mandó al motor
 *      (parametros) y lo que el motor devolvió (resultados), y cuenta lo que
 *      el backend respondió — no un texto escrito a mano.
 *   3. Que un error del backend se muestra como error y no se disfraza de
 *      éxito, y que no agrega una fila al historial.
 *   4. Que el historial se consulta al abrir la pantalla y que «Ver
 *      resultados» restaura una corrida guardada sin recalcular.
 *
 * `fetch` se stubbea acá y no en `setup.js`: es deliberado, para que se vea
 * en este archivo qué endpoints necesita la pantalla y cuál no.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'

import CalculadoraRFView from '@/views/CalculadoraRFView.vue'
import { useSystemStore } from '@/stores/system'

// Lo que POST /rf/calculate devolvió en vivo contra el backend real con
// objetivo 177.0 MHz y una sola entrada de 88.5 MHz.
const CALCULO = {
  result_mhz: 177.0,
  formula: '2 × 88.5',
  tipo: 'H2',
  order: 2,
  error_khz: 0.0,
  score: 99,
  frequencies_involved: [88.5],
}

const RESPUESTA_MOTOR = {
  target_mhz: 177.0,
  tolerance_khz: 10.0,
  total_candidates_evaluated: 1,
  total_matches: 1,
  matches: [CALCULO],
  warnings: [],
}

// Un análisis ya guardado, tal como lo devuelve GET /rf/analisis. La
// corrida es otra (3.ª armónica) para que «Ver resultados» se note.
const ANALISIS_GUARDADO = {
  id: 12,
  created_at: '2026-11-02T15:30:00',
  modo: 'armonicos',
  frecuencia_referencia_mhz: 177.0,
  tolerancia_khz: 10.0,
  n_emisoras: 1,
  n_productos: 1,
  objeto_id: null,
  parametros: {
    target_mhz: 177.0,
    tolerance_khz: 10.0,
    frequencies: [
      { freq_mhz: 88.5, label: 'FM Radio', signal_type: 'FM', power_dbm: null },
    ],
    max_harmonic_order: 5,
    include_im7: false,
    max_results: 25,
  },
  resultados: {
    target_mhz: 177.0,
    tolerance_khz: 10.0,
    total_candidates_evaluated: 1,
    total_matches: 1,
    matches: [
      { ...CALCULO, formula: '3 × 88.5', result_mhz: 265.5, tipo: 'H3', order: 3 },
    ],
    warnings: [],
  },
}

const ANALISIS_CREADO = {
  ...ANALISIS_GUARDADO,
  id: 41,
  created_at: '2026-11-02T16:00:00',
}

const json = (body, status = 200) => ({
  ok: true,
  status,
  json: async () => body,
})

let fetchStub
let historialServidor
let guardarResponde

const montar = async () => {
  const pinia = createPinia()
  const wrapper = mount(CalculadoraRFView, { global: { plugins: [pinia] } })
  await flushPromises()

  // La calculadora arranca vacía (AeroRF 2.6): se carga el ejemplo y se
  // calcula, como haría el operador antes de guardar.
  const cargar = wrapper.findAll('button').find((b) => b.text().includes('Cargar ejemplo'))
  if (cargar) {
    await cargar.trigger('click')
    await flushPromises()
  }
  const calcularBtn = wrapper.findAll('button').find((b) => b.text().includes('Calcular') && !b.text().includes('Volver'))
  if (calcularBtn && !calcularBtn.attributes('disabled')) {
    await calcularBtn.trigger('click')
    await flushPromises()
  }
  return { w: wrapper, pinia }
}

const botonGuardar = (wrapper) => wrapper.find('[data-guardar-analisis]')

const cuerpo = (opciones) => JSON.parse(opciones.body)

beforeEach(() => {
  historialServidor = [ANALISIS_GUARDADO]
  guardarResponde = null // null = responde bien

  fetchStub = vi.fn(async (url, options = {}) => {
    const u = String(url)
    if (u.startsWith('/api/v1/rf/analisis') && options.method === 'POST') {
      if (guardarResponde) return guardarResponde
      return json(ANALISIS_CREADO, 201)
    }
    if (u.startsWith('/api/v1/rf/analisis') && options.method === 'DELETE') {
      return { ok: true, status: 204, json: async () => ({}) }
    }
    if (u.startsWith('/api/v1/rf/analisis')) return json(historialServidor)
    if (u.startsWith('/api/v1/rf/calculate')) return json(RESPUESTA_MOTOR)
    const m = u.match(/\/api\/v1\/rf\/harmonics\/([\d.]+)\?max_order=(\d+)/)
    if (m) {
      const base = Number(m[1])
      return json({
        base_freq_mhz: base,
        harmonics: [2, 3, 4].map((order) => ({
          order,
          freq_mhz: base * order,
          formula: `${order} × ${base}`,
        })),
      })
    }
    return json({})
  })
  vi.stubGlobal('fetch', fetchStub)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ─── La dependencia de Expedientes, retirada ─────────────────────────────────

describe('la calculadora ya no depende de Expedientes', () => {
  it('no tiene selector de expedientes ni botón «Guardar en Expediente»', async () => {
    const { w } = await montar()

    expect(w.find('#expediente-destino').exists(), 'sigue el selector').toBe(false)
    expect(w.text()).not.toContain('Guardar en Expediente')
    expect(w.text()).not.toContain('Expediente de destino')
    expect(w.text()).not.toContain('próximamente integrado')
    expect(w.text()).not.toMatch(/Guardado en el expediente/)
  })

  it('el código fuente de la vista no menciona expedientes como destino', async () => {
    const { readFileSync } = await import('node:fs')
    const { join, dirname } = await import('node:path')
    const { fileURLToPath } = await import('node:url')
    const here = dirname(fileURLToPath(import.meta.url))
    const fuente = readFileSync(
      join(here, '..', 'src', 'views', 'CalculadoraRFView.vue'),
      'utf8'
    )

    expect(fuente).not.toContain('expediente-destino')
    expect(fuente).not.toContain('Guardar en Expediente')
    expect(fuente).not.toContain('próximamente integrado')
    expect(fuente).not.toMatch(/const\s+storeResult\s*=\s*\(\)\s*=>\s*\{\s*alert\(/)
    expect(fuente).not.toContain('stores/expedientes')
    expect(fuente).not.toContain('crearEvento')
  })
})

// ─── Guardar en el historial propio ──────────────────────────────────────────

describe('guardar el análisis en /rf/analisis', () => {
  it('manda los parámetros y la respuesta reales del motor', async () => {
    const { w } = await montar()

    const boton = botonGuardar(w)
    expect(boton.exists(), 'falta el botón de guardar análisis').toBe(true)
    expect(boton.attributes('disabled')).toBeUndefined()

    await boton.trigger('click')
    await flushPromises()

    const posts = fetchStub.mock.calls.filter(
      ([url, options = {}]) =>
        String(url).startsWith('/api/v1/rf/analisis') && options.method === 'POST'
    )
    expect(posts, 'no se mandó nada a /rf/analisis').toHaveLength(1)

    const body = cuerpo(posts[0][1])
    expect(body.modo).toBe('armonicos') // pestaña por defecto

    // Lo guardado es lo que se pidió y lo que respondió, sin resumir:
    const corrida = fetchStub.mock.calls.find(([url]) =>
      String(url).startsWith('/api/v1/rf/calculate')
    )
    expect(body.parametros).toEqual(JSON.parse(corrida[1].body))
    expect(body.resultados).toEqual(RESPUESTA_MOTOR)
    expect(body.expediente_id).toBeUndefined()

    // El aviso cuenta lo que devolvió el backend, no un texto fijo.
    expect(w.text()).toContain('Análisis n.º 41 guardado')
    expect(w.text()).toContain('1 producto')
  })

  it('agrega la fila devuelta por el backend al historial visible', async () => {
    const { w } = await montar()
    expect(w.text()).toContain('FM Radio')

    await botonGuardar(w).trigger('click')
    await flushPromises()

    const filas = w.findAll('[data-historial] li')
    expect(filas.length).toBe(2) // la del servidor + la recién guardada
    expect(filas[0].text()).toContain('#41')
  })

  it('un error del backend se muestra como error y no agrega la fila', async () => {
    guardarResponde = {
      ok: false,
      status: 400,
      json: async () => ({ detail: 'Sólo se puede asociar un análisis a una fuente RF, un evento RF o una antena.' }),
    }

    const { w } = await montar()
    await botonGuardar(w).trigger('click')
    await flushPromises()

    const aviso = w.find('[data-historial] [role="status"]')
    expect(aviso.exists()).toBe(true)
    expect(aviso.text()).toContain('fuente RF')
    expect(aviso.classes().join(' ')).toContain('text-red-400')
    expect(w.text()).not.toContain('Análisis n.º 41 guardado')
    expect(w.findAll('[data-historial] li')).toHaveLength(1)
  })

  it('sin corrida no hay nada que guardar y se dice sin afirmar nada', async () => {
    const { w } = await montar()

    // Limpiar el cálculo borra también el rastro de la última corrida.
    const limpiar = w.findAll('button').find((b) => b.text().includes('Limpiar cálculo'))
    await limpiar.trigger('click')
    await flushPromises()

    expect(botonGuardar(w).attributes('disabled')).toBeDefined()

    const posts = fetchStub.mock.calls.filter(
      ([url, options = {}]) =>
        String(url).startsWith('/api/v1/rf/analisis') && options.method === 'POST'
    )
    expect(posts).toHaveLength(0)
  })
})

// ─── Historial consultable ───────────────────────────────────────────────────

describe('el historial de análisis', () => {
  it('se consulta al abrir la pantalla', async () => {
    const { w } = await montar()

    const gets = fetchStub.mock.calls.filter(
      ([url, options = {}]) =>
        String(url).startsWith('/api/v1/rf/analisis') && !options.method
    )
    expect(gets.length).toBeGreaterThanOrEqual(1)
    expect(w.text()).toContain('#12')
    expect(w.text()).toContain('Armónicos')
    expect(w.text(), 'sin asociación no se pinta el chip de objeto GIS').not.toContain(
      '· objeto GIS #'
    )
  })

  it('muestra el estado vacío cuando no hay análisis guardados', async () => {
    historialServidor = []
    const { w } = await montar()

    expect(w.text()).toContain('Todavía no guardaste ningún análisis')
    expect(w.text()).toContain('sin necesidad de ningún expediente')
  })

  it('«Ver resultados» restaura la corrida guardada sin recalcular', async () => {
    const { w } = await montar()

    const calculosAntes = fetchStub.mock.calls.filter(([url]) =>
      String(url).startsWith('/api/v1/rf/calculate')
    ).length

    const ver = w.findAll('button').find((b) => b.text().includes('Ver resultados'))
    expect(ver).toBeTruthy()
    await ver.trigger('click')
    await flushPromises()

    // La tabla muestra lo guardado (3.ª armónica), no el cálculo del día.
    expect(w.text()).toContain('265.500000 MHz')
    expect(w.text()).toContain('Análisis n.º 12 cargado')

    const calculosDespues = fetchStub.mock.calls.filter(([url]) =>
      String(url).startsWith('/api/v1/rf/calculate')
    ).length
    expect(calculosDespues, 'ver un análisis no vuelve a correr el motor').toBe(calculosAntes)
  })

  it('«Eliminar» se confirma en la aplicación antes de borrar', async () => {
    const { w, pinia } = await montar()
    const system = useSystemStore(pinia)
    const confirmaciones = []
    system.ask = vi.fn((cfg) => {
      confirmaciones.push(cfg)
      return Promise.resolve(true)
    })

    const eliminar = w.findAll('button').find((b) => b.text().includes('Eliminar'))
    expect(eliminar).toBeTruthy()
    await eliminar.trigger('click')
    await flushPromises()

    expect(system.ask).toHaveBeenCalledTimes(1)
    expect(confirmaciones[0].danger).toBe(true)
    expect(confirmaciones[0].message).toContain('n.º 12')

    const deletes = fetchStub.mock.calls.filter(
      ([url, options = {}]) =>
        String(url).startsWith('/api/v1/rf/analisis/12') && options.method === 'DELETE'
    )
    expect(deletes).toHaveLength(1)
    expect(w.findAll('[data-historial] li')).toHaveLength(0)
    expect(w.text()).toContain('Análisis n.º 12 eliminado')
  })

  it('si el historial no se pudo cargar se dice como error, sin inventar vacío', async () => {
    fetchStub = vi.fn(async (url, options = {}) => {
      const u = String(url)
      if (u.startsWith('/api/v1/rf/analisis')) {
        return { ok: false, status: 500, json: async () => ({}) }
      }
      if (u.startsWith('/api/v1/rf/calculate')) return json(RESPUESTA_MOTOR)
      return json({ base_freq_mhz: 88.5, harmonics: [] })
    })
    vi.stubGlobal('fetch', fetchStub)

    const { w } = await montar()

    expect(w.find('[data-historial] [role="alert"]').exists()).toBe(true)
    expect(w.text()).toContain('No se pudo cargar el historial')
    expect(w.text()).not.toContain('Todavía no guardaste ningún análisis')
  })
})
