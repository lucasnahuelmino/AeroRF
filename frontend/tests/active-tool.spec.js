/**
 * tests/active-tool.spec.js
 * ────────────────────────
 * Which tool button reads as pressed.
 *
 * The complaint: pressing a tool button does not visibly stick. The operator
 * cannot tell which tool is armed, which on a map with ten tools is the
 * difference between drawing a circle and placing a point.
 *
 * Three things have to hold, and the class alone is not enough:
 *   - the pressed tool is marked,
 *   - the mark survives while the operator draws,
 *   - switching tools moves the mark rather than adding a second one.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { readFileSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))

vi.mock('@/api/client', () => {
  const R = (p) => Promise.resolve(p)
  return {
    API_PREFIX: '/api/v1',
    default: { get: R, post: R, put: R, delete: R },
    describeError: (e) => String(e?.message || e),
    system: {
      status: R({ status: 'ok' }),
      config: R({}),
      vocabulary: R({
        object_types: [], states: [], point_categories: [], rf_source_kinds: [],
        rf_event_classifications: [], antenna_kinds: [], polarizations: [], units: [],
        reference_radii_nm: [], correlation_radii_nm: [], provenance: [], provenance_labels: {},
      }),
      logs: { recent: R([]) },
    },
    mapObjects: {
      list: R({ count: 0, objects: [] }), all: R({ count: 0, objects: [] }),
      create: R({}), update: R({}), remove: R({}), setStatus: R({}), move: R({}),
      duplicate: R({}), near: R({ count: 0, results: [] }),
      distances: R({ count: 0, results: [] }), stats: R({ total: 0, by_type: {} }),
      history: R([]), notes: R([]), addNote: R({}), importGeoJson: R({ created: [], errors: [] }),
    },
    layers: { list: R({ count: 0, layers: [] }), create: R({}), update: R({}), remove: R({}) },
    rf: { summary: R({}) },
    flights: {
      search: R({ flights: [] }), get: R({ flights: [] }), track: R({ points: [] }),
      liveTrack: R({ points: [] }), live: R({ states: [] }), all: R({ flights: [] }),
      byAircraft: R({ flights: [] }), arrivals: R({ flights: [] }), departures: R({ flights: [] }),
      sessions: R({ sessions: [] }), createSession: R({}), startSession: R({}), stopSession: R({}),
      session: R({ session: {}, positions: [], tracks: [] }), deleteSession: R({}),
      tracked: R({ count: 0, max: 5, slots: [] }), trackAircraft: R({}), untrackAircraft: R({}),
      patchTracked: R({}),
    },
    correlation: { rfAircraft: R({ bands: [] }) },
    exporter: { geojsonUrl: () => '/g', kmlUrl: () => '/k', csvUrl: () => '/c' },
    expedientes: { list: R([]), get: R({}), create: R({}), update: R({}), remove: R({}) },
  }
})

async function mountShell() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()
  const { default: GisShell } = await import('@/views/GisShell.vue')
  const w = mount(GisShell, { global: { plugins: [pinia, router] } })
  await flushPromises()
  const { useMapStore } = await import('@/stores/map')
  return { w, map: useMapStore() }
}

describe('the pressed tool', () => {
  let w
  let map

  beforeEach(async () => {
    const mounted = await mountShell()
    w = mounted.w
    map = mounted.map
  })

  /** Indexes of the buttons currently marked active. */
  const pressed = () =>
    w.findAll('.gis-tool')
      .map((b, i) => (b.classes('active') ? i : -1))
      .filter((i) => i >= 0)

  it('marks exactly one tool when the shell opens', () => {
    // The select tool is the default, so it starts marked.
    // Eight, not ten: poligono and traza were taken off the palette at the
      // operator's request, because they duplicated cobertura and linea. The
      // assertion is on the count rather than on 'more than one', so a tool
      // going missing has to be a deliberate edit here too.
      expect(w.findAll('.gis-tool').length).toBe(8)
    expect(pressed().length, 'mas de un boton apretado, o ninguno').toBe(1)
  })

  it('marks the tool that was pressed', async () => {
    const buttons = w.findAll('.gis-tool')
    const circleIndex = buttons.findIndex((b) => b.text().includes('Círculo'))
    expect(circleIndex, 'no se encontro el boton de circulo').toBeGreaterThanOrEqual(0)

    await buttons[circleIndex].trigger('click')
    await flushPromises()

    expect(pressed(), 'el circulo no quedo apretado').toEqual([circleIndex])
  })

  it('moves the mark instead of adding a second one', async () => {
    const buttons = w.findAll('.gis-tool')
    const circle = buttons.findIndex((b) => b.text().includes('Círculo'))
    const point = buttons.findIndex((b) => b.text().includes('Punto'))

    await buttons[circle].trigger('click')
    await flushPromises()
    await buttons[point].trigger('click')
    await flushPromises()

    expect(pressed(), 'al cambiar de herramienta quedo mas de un boton apretado')
      .toEqual([point])
  })

  it('stays pressed while the operator draws', async () => {
    const buttons = w.findAll('.gis-tool')
    const lineIndex = buttons.findIndex((b) => b.text().includes('Línea'))
    await buttons[lineIndex].trigger('click')
    await flushPromises()
    expect(pressed()).toEqual([lineIndex])

    const engine = map.engine
    expect(engine, 'sin motor').toBeTruthy()

    // Placing vertices must not clear the pressed state: the tool is still
    // armed and the operator is mid-drawing.
    engine.map.fire('click', { latlng: { lat: -34.6, lng: -58.4 } })
    await flushPromises()
    expect(pressed(), 'el boton se solto al empezar a dibujar').toEqual([lineIndex])

    engine.map.fire('click', { latlng: { lat: -34.5, lng: -58.3 } })
    await flushPromises()
    expect(pressed(), 'el boton se solto al agregar un vertice').toEqual([lineIndex])
  })

  it('reports the pressed state to assistive technology', async () => {
    const buttons = w.findAll('.gis-tool')
    const circleIndex = buttons.findIndex((b) => b.text().includes('Círculo'))
    await buttons[circleIndex].trigger('click')
    await flushPromises()

    // The visual class is not the whole story: a screen reader announces
    // aria-pressed, and a toggle button that lies about its state is worse
    // than one with no state at all.
    const marked = w.findAll('.gis-tool').filter((b) => b.attributes('aria-pressed') === 'true')
    expect(marked.length).toBe(1)
    expect(marked[0].text()).toContain('Círculo')
  })

  it('keeps the size the operator was shown, and releases the tool', async () => {
    // The ToolManager subscribes to the map's click event itself, and the
    // shell subscribed too. Both ran on every click: the shell sized and
    // committed the circle, then the manager's own handler — still armed —
    // started a second one. The stored circle came out at the wrong size and
    // the tool stayed armed, so no other tool could be picked.
    //
    // This can only be observed through the shell: driving the ToolManager
    // alone leaves no second handler, which is why the same test written
    // against the engine passed against the broken shell.
    const { TOOLS } = await import('@/map/draw')
    const created = []
    const real = map.createObject
    map.createObject = (payload) => {
      created.push(payload)
      return Promise.resolve({ id: created.length, ...payload, latlngs: [], latlng: null })
    }

    const buttons = w.findAll('.gis-tool')
    const circleIndex = buttons.findIndex((b) => b.text().includes('Círculo'))
    await buttons[circleIndex].trigger('click')
    await flushPromises()

    const engine = map.engine
    const CENTRE = { lat: -34.6, lng: -58.4 }
    const FURTHER = { lat: -34.4, lng: -58.4 }

    // First click: the centre.
    engine.map.fire('click', { latlng: CENTRE })
    await flushPromises()
    expect(created.length, 'el primer clic no debe crear nada').toBe(0)

    // The operator drags out to the size they want.
    map.toolManager.previewAt(FURTHER)
    const shownM = map.toolManager.draft.radiusM
    expect(shownM, 'la guia no midio nada').toBeGreaterThan(1000)

    // Second click: keep it.
    engine.map.fire('click', { latlng: FURTHER })
    await flushPromises()

    expect(created.length, 'el segundo clic debe crear un unico circulo').toBe(1)
    // And at the size that was on screen, not a stale one.
    expect(created[0].radius_m).toBeCloseTo(shownM, 3)
    // The tool is released, which is what lets another tool be picked.
    expect(pressed().length, 'la herramienta quedo armada tras confirmar').toBe(0)

    // A line can start immediately, with no leftover state.
    await buttons[1].trigger('click')
    await flushPromises()
    expect(pressed().length).toBe(1)

    map.createObject = real
  })

  it('un-presses when the same tool is pressed again', async () => {
    const buttons = w.findAll('.gis-tool')
    const point = buttons.findIndex((b) => b.text().includes('Punto'))
    await buttons[point].trigger('click')
    await flushPromises()
    expect(pressed()).toEqual([point])

    // Pressing an armed tool releases it, which is the toggle every other
    // toolbar in the application follows.
    await buttons[point].trigger('click')
    await flushPromises()
    expect(pressed().length, 'el boton quedo apretado tras desactivarlo').toBe(0)
  })
})

describe('the pressed state is visible, not just a class', () => {
  it('is carried by three signals that reinforce each other', () => {
    // A class that changes nothing is not a state an operator can see. Read
    // the built CSS, because jsdom does not lay out.
    const dist = join(here, '..', 'dist', 'assets')
    const file = readdirSync(dist).find((f) => /^GisShell-.*\.css$/.test(f))
    const css = readFileSync(join(dist, file), 'utf8')
    const m = css.match(/\.gis-tool\.active(?:\[[^\]]*\])?[^{}]*\{([^}]*)\}/)
    expect(m, 'sin estado activo en el CSS construido').toBeTruthy()
    const body = m[1]
    // A filled ground, a bright border, and a lit bar under the label.
    expect(body, 'sin fondo propio').toMatch(/background:\s*#[0-9a-f]{3,6}/i)
    expect(body, 'sin borde propio').toMatch(/border-color:\s*#[0-9a-f]{3,6}/i)
    expect(body, 'sin marca adicional bajo la etiqueta').toMatch(/box-shadow/i)
  })

  it('does not change the button size when pressed', () => {
    // A "pressed" button that grows is a layout jump, and the operator's
    // pointer moves off it. The active state is paint only.
    const dist = join(here, '..', 'dist', 'assets')
    const file = readdirSync(dist).find((f) => /^GisShell-.*\.css$/.test(f))
    const css = readFileSync(join(dist, file), 'utf8')
    const m = css.match(/\.gis-tool\.active(?:\[[^\]]*\])?[^{}]*\{([^}]*)\}/)
    expect(m[1]).not.toMatch(/padding/i)
    expect(m[1]).not.toMatch(/font-size/i)
    expect(m[1]).not.toMatch(/(?:^|;)\s*(?:width|height)\s*:/i)
  })
})
