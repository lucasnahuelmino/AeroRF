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
  localStorage.removeItem('aerorf:workspace-section')
  localStorage.removeItem('aerorf:workspace-category')
  localStorage.removeItem('aerorf:workspace-level')
  localStorage.setItem('aerorf:workspace-mode', 'open')
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
  const category = w.findAll('.gis-workspace-category')
    .find((button) => button.text().includes('Herramientas'))
  await category.trigger('click')
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

  const buttons = () => w.findAll('.gis-workspace-tool')

  async function returnToToolList() {
    if (buttons().length) return
    const category = w.findAll('.gis-workspace-breadcrumb button')
      .find((button) => button.text() === 'Herramientas')
    expect(category, 'falta el breadcrumb de Herramientas').toBeTruthy()
    await category.trigger('click')
    await flushPromises()
  }

  async function chooseTool(label) {
    await returnToToolList()
    const button = buttons().find((item) => item.text().includes(label))
    expect(button, `no se encontro la herramienta ${label}`).toBeTruthy()
    await button.trigger('click')
    await flushPromises()
  }

  /** Indexes of the buttons currently marked active. */
  const pressed = () =>
    buttons()
      .map((b, i) => (b.classes('active') ? i : -1))
      .filter((i) => i >= 0)

  it('marks exactly one tool in the Workspace tool list', () => {
    // The select tool is the default, so it starts marked.
    // Eight, not ten: polígono and traza duplicate cobertura and línea.
    expect(buttons().length).toBe(8)
    expect(pressed().length, 'mas de un boton apretado, o ninguno').toBe(1)
  })

  it('marks the chosen tool in the contextual task view', async () => {
    await chooseTool('Círculo')
    expect(w.find('.gis-workspace-title').text()).toBe('Círculo')
    expect(map.activeTool).toBe('circle')
  })

  it('moves the mark instead of adding a second one', async () => {
    await chooseTool('Círculo')
    await chooseTool('Punto')
    await returnToToolList()
    expect(pressed().length, 'al cambiar de herramienta quedo mas de un boton apretado').toBe(1)
    expect(buttons()[pressed()[0]].text()).toContain('Punto')
  })

  it('stays pressed while the operator draws', async () => {
    await chooseTool('Línea')
    expect(map.activeTool).toBe('line')

    const engine = map.engine
    expect(engine, 'sin motor').toBeTruthy()

    // Placing vertices must not clear the active task: the tool is still
    // armed while the operator is mid-drawing.
    engine.map.fire('click', { latlng: { lat: -34.6, lng: -58.4 } })
    await flushPromises()
    expect(map.activeTool, 'el boton se solto al empezar a dibujar').toBe('line')

    engine.map.fire('click', { latlng: { lat: -34.5, lng: -58.3 } })
    await flushPromises()
    expect(map.activeTool, 'el boton se solto al agregar un vertice').toBe('line')
    await returnToToolList()
    expect(buttons()[pressed()[0]].text()).toContain('Línea')
  })

  it('reports the pressed state to assistive technology', async () => {
    await chooseTool('Círculo')
    await returnToToolList()

    // The visual class is not the whole story: a screen reader announces
    // aria-pressed, and a toggle button that lies about its state is worse
    // than one with no state at all.
    const marked = buttons().filter((b) => b.attributes('aria-pressed') === 'true')
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

    await chooseTool('Círculo')

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
    expect(map.activeTool, 'la herramienta quedo armada tras confirmar').toBe('select')
    expect(w.find('.gis-workspace-context-bar').exists()).toBe(true)

    // The operator can return to tools and arm another tool immediately.
    const { useSystemStore } = await import('@/stores/system')
    useSystemStore().clearWorkspaceContext()
    await flushPromises()
    await chooseTool('Línea')
    expect(map.activeTool).toBe('line')

    map.createObject = real
  }, 20000)

  it('un-presses when the same tool is pressed again', async () => {
    await chooseTool('Punto')
    expect(map.activeTool).toBe('point')

    // Selecting the same armed tool again releases it.
    await returnToToolList()
    await buttons().find((button) => button.text().includes('Punto')).trigger('click')
    await flushPromises()
    await returnToToolList()
    expect(pressed().length, 'el boton quedo apretado tras desactivarlo').toBe(0)
  })
})

describe('the pressed state is visible, not just a class', () => {
  it('is carried by three signals that reinforce each other', () => {
    // A class that changes nothing is not a state an operator can see. Read
    // the built CSS, because jsdom does not lay out.
    const dist = join(here, '..', 'dist', 'assets')
    // Both built stylesheets, not just the map's.
    // The `.gis-workspace-tool.active` rule lives in the route chunk, but every colour in
    // the application now resolves through a token declared in the entry chunk.
    // Reading only the route chunk found `var(--signal)` with nothing pointing at
    // it, and the button looked like it had no background when it had one.
    const css = readdirSync(dist)
      .filter((f) => f.endsWith('.css'))
      .map((f) => readFileSync(join(dist, f), 'utf8'))
      .join('\n')
    const m = css.match(/\.gis-workspace-tool\.active(?:\[[^\]]*\])?[^{}]*\{([^}]*)\}/)
    expect(m, 'sin estado activo en el CSS construido').toBeTruthy()
    const body = m[1]
    // A filled ground and bright border distinguish the armed tool.
    //
    // The value may be a hex or a token reference; what is required is that a
    // colour is painted, not how it is spelled. The background blends the
    // signal token with the panel, and the border resolves to a real token.
    const colorOToken = (valor) => {
      if (/^#(?:[0-9a-f]{3,8})$/i.test(valor)) return true
      const ref = valor.match(/^var\(\s*(--[a-z-]+)\s*\)$/i)
      if (!ref) return false
      const decl = css.match(new RegExp(`${ref[1]}\\s*:\\s*([^;}]+)`))
      return decl ? /^#(?:[0-9a-f]{3,8})$/i.test(decl[1].trim()) : false
    }
    const propiedad = (nombre) => {
      const p = body.match(new RegExp(`(?:^|;)\\s*${nombre}\\s*:\\s*([^;}]+)`))
      return p ? p[1].trim() : ''
    }
    expect(propiedad('background'), 'sin fondo propio').toMatch(
      /^color-mix\(in srgb,var\(--signal\).+var\(--panel\)\)$/i,
    )
    expect(
      colorOToken(propiedad('border-color')),
      `sin borde propio: ${propiedad('border-color') || '(nada)'}`,
    ).toBe(true)
    expect(body, 'sin borde de estado activo').toMatch(/border-color/i)
  })

  it('does not change the button size when pressed', () => {
    // A "pressed" button that grows is a layout jump, and the operator's
    // pointer moves off it. The active state is paint only.
    const dist = join(here, '..', 'dist', 'assets')
    // Both built stylesheets, not just the map's.
    // The `.gis-workspace-tool.active` rule lives in the route chunk, but every colour in
    // the application now resolves through a token declared in the entry chunk.
    // Reading only the route chunk found `var(--signal)` with nothing pointing at
    // it, and the button looked like it had no background when it had one.
    const css = readdirSync(dist)
      .filter((f) => f.endsWith('.css'))
      .map((f) => readFileSync(join(dist, f), 'utf8'))
      .join('\n')
    const m = css.match(/\.gis-workspace-tool\.active(?:\[[^\]]*\])?[^{}]*\{([^}]*)\}/)
    expect(m[1]).not.toMatch(/padding/i)
    expect(m[1]).not.toMatch(/font-size/i)
    expect(m[1]).not.toMatch(/(?:^|;)\s*(?:width|height)\s*:/i)
  })
})
