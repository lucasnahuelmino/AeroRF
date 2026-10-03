/**
 * tests/p011-guardar.spec.js
 * ─────────────────────────
 * P0-11: el botón «Guardar en Expediente» dejó de mentir.
 *
 * Lo que había, y no era otra cosa:
 *
 *     const storeResult = () => {
 *       alert('Resultado guardado (próximamente integrado con expediente)')
 *     }
 *
 * El `alert` afirmaba que algo se guardó sin que existiera escritura alguna.
 * `eventos_rf` estaba vacía y `GET /expedientes/{id}/eventos` — que sí existía
 * — devolvía siempre `[]`, así que ni siquiera había dónde mirar después.
 *
 * Estas pruebas protegen tres cosas:
 *
 *   1. Que guardar exige elegir a qué expediente, y que sin elegir no se
 *      manda nada ni se afirma nada.
 *   2. Que lo que se manda son los campos de `EventoRF`, mapeados desde lo que
 *      devuelve `RFMatch` (`result_mhz`, `tipo`, `error_khz`, `score`,
 *      `frequencies_involved`).
 *   3. Que un error del backend se muestra como error, en español, y no se
 *      disfraza de éxito.
 *
 * `fetch` se stubbea acá y no en `setup.js`: es deliberado, para que se vea en
 * este archivo qué endpoints necesita la pantalla y cuál no.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'

const { crearEvento } = vi.hoisted(() => ({ crearEvento: vi.fn() }))

vi.mock('@/api/client', () => ({
  expedientes: {
    list: () => Promise.resolve([]),
    get: () => Promise.resolve({}),
    create: () => Promise.resolve({}),
    update: () => Promise.resolve({}),
    remove: () => Promise.resolve({}),
    mediciones: () => Promise.resolve([]),
    eventos: () => Promise.resolve([]),
    crearEvento,
  },
}))

import CalculadoraRFView from '@/views/CalculadoraRFView.vue'

// Lo que POST /rf/calculate devolvió en vivo contra el backend real con
// objetivo 177.0 MHz y una sola entrada de 88.5 MHz. No es un ejemplo
// escrito a mano: es la respuesta medida, incluida la fórmula con el
// signo × (U+00D7).
const CALCULO = {
  result_mhz: 177.0,
  formula: '2 × 88.5',
  tipo: 'H2',
  order: 2,
  error_khz: 0.0,
  score: 99,
  frequencies_involved: [88.5],
}

const EXPEDIENTES = [
  { id: 7, numero_expediente: 'E-7', aeropuerto: 'EZE' },
  { id: 8, numero_expediente: 'E-8', aeropuerto: 'Aeroparque' },
]

const json = (body) => ({
  ok: true,
  status: 200,
  json: async () => body,
})

let fetchStub

const montar = async () => {
  const wrapper = mount(CalculadoraRFView, {
    global: { plugins: [createPinia()] },
  })
  await flushPromises()
  return wrapper
}

const botonGuardar = (wrapper) =>
  wrapper.findAll('button').find((b) => b.text().includes('Guardar en Expediente'))

beforeEach(() => {
  crearEvento.mockReset()
  crearEvento.mockResolvedValue({ id: 41, expediente_id: 7 })

  fetchStub = vi.fn(async (url) => {
    const u = String(url)
    if (u.startsWith('/api/v1/expedientes')) return json(EXPEDIENTES)
    if (u.startsWith('/api/v1/rf/calculate')) return json({ matches: [CALCULO] })
    return json({})
  })
  vi.stubGlobal('fetch', fetchStub)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('P0-11 · guardar en un expediente', () => {
  it('el botón está inactivo hasta que se elige expediente, y no manda nada', async () => {
    const w = await montar()
    const boton = botonGuardar(w)
    expect(boton, 'no se encontró el botón de guardar').toBeTruthy()
    expect(boton.attributes('disabled'), 'el botón se activaba sin destino').toBeDefined()

    await boton.trigger('click')
    await flushPromises()

    expect(crearEvento, 'se mandó algo sin haber elegido expediente').not.toHaveBeenCalled()
    expect(w.text()).not.toContain('próximamente integrado')
    expect(w.text()).not.toMatch(/Guardado en el expediente/)
  })

  it('con expediente elegido guarda de verdad y cuenta adónde fue', async () => {
    const w = await montar()

    await w.find('#expediente-destino').setValue('7')
    await flushPromises()

    const boton = botonGuardar(w)
    expect(boton.attributes('disabled')).toBeUndefined()

    await boton.trigger('click')
    await flushPromises()

    expect(crearEvento).toHaveBeenCalledTimes(1)
    const [id, payload] = crearEvento.mock.calls[0]

    expect(id).toBe(7)
    expect(payload).toEqual({
      expediente_id: 7,
      frecuencia_resultado_mhz: 177.0,
      tipo_producto: 'H2',
      formula: '2 × 88.5',
      error_khz: 0.0,
      score_probabilidad: 99,
      freq_1_mhz: 88.5,
      freq_2_mhz: null,
    })

    expect(w.text()).toContain('Guardado en el expediente E-7')
    expect(w.text()).toContain('evento 41')
  })

  it('un error del backend se muestra como error, no como éxito', async () => {
    crearEvento.mockRejectedValueOnce({
      response: { data: { detail: 'No existe el expediente 999999' } },
    })

    const w = await montar()
    await w.find('#expediente-destino').setValue('7')
    await flushPromises()
    await botonGuardar(w).trigger('click')
    await flushPromises()

    expect(w.text()).toContain('No existe el expediente 999999')
    expect(w.text()).not.toMatch(/Guardado en el expediente/)
  })

  it('si la carga de expedientes falla no dice que no hay ninguno', async () => {
    fetchStub = vi.fn(async (url) => {
      const u = String(url)
      if (u.startsWith('/api/v1/expedientes')) {
        return { ok: false, status: 500, json: async () => ({}) }
      }
      if (u.startsWith('/api/v1/rf/calculate')) return json({ matches: [CALCULO] })
      return json({})
    })
    vi.stubGlobal('fetch', fetchStub)

    const w = await montar()
    await flushPromises()

    // Las dos cosas suenan parecido y no dicen lo mismo: «todavía no hay
    // expedientes» sería mentira si lo que pasó fue que no se pudieron cargar.
    expect(w.text()).toContain('No se pudieron cargar los expedientes')
    expect(w.text()).not.toContain('No hay expedientes creados todavía')
  })

  it('el texto mentiroso ya no está en la vista', async () => {
    const { readFileSync } = await import('node:fs')
    const { join, dirname } = await import('node:path')
    const { fileURLToPath } = await import('node:url')
    const here = dirname(fileURLToPath(import.meta.url))
    const fuente = readFileSync(
      join(here, '..', 'src', 'views', 'CalculadoraRFView.vue'),
      'utf8'
    )

    expect(fuente).not.toContain('próximamente integrado')
    expect(fuente).not.toMatch(/const\s+storeResult\s*=\s*\(\)\s*=>\s*\{\s*alert\(/)
  })
})
