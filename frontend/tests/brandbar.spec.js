/**
 * tests/brandbar.spec.js
 * ─────────────────────
 * The persistent header: brand, section menu, status and the institutional
 * lockup.
 *
 * What this protects
 * ──────────────────
 * The application had two unrelated headers. The map drew its own toolbar with
 * no link to the other sections, and the document views grew a ~130px header.
 * So the menu was present on some routes and absent on the one the operator
 * lives in: the only way to reach an expediente from the map was to type the
 * URL.
 *
 * The requirement is that the menu is thin and **always present**, so these
 * tests check both routes render it and that it costs little height. The
 * height assertions read the built CSS, because jsdom does not lay out.
 */

import { describe, it, expect, beforeAll, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useSystemStore } from '@/stores/system'
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const distAssets = join(here, '..', 'dist', 'assets')

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

// Los stubs de /espectro y /dashboard se quitaron con las bajas totales de
// las secciones (0.30.32 y 0.30.33): esta lista imita el enrutador real, y
// el enrutador real ya no registra esas rutas. Las guardas de las dos bajas
// están al final del archivo.
const ROUTES = [
  { path: '/', name: 'Map', component: { template: '<div class="gis-map" />' } },
  { path: '/map', name: 'Mapa', component: { template: '<div class="gis-map" />' } },
  { path: '/expedientes', name: 'Expedientes', component: { template: '<div />' } },
  { path: '/situacion', name: 'Situacion', component: { template: '<div />' } },
  { path: '/calculadora', name: 'CalculadoraRF', component: { template: '<div />' } },
]

async function mountApp({ path = '/' } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({ history: createMemoryHistory(), routes: ROUTES })
  await router.push(path)
  await router.isReady()
  const { default: App } = await import('@/App.vue')
  const w = mount(App, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { w, router }
}

// ─── The menu is everywhere ─────────────────────────────────────────────────

describe('the section menu', () => {
  it('renders on the map', async () => {
    const { w } = await mountApp({ path: '/' })
    expect(w.find('.brandbar').exists(), 'el mapa no tiene menu').toBe(true)
    expect(w.find('.brandbar-nav').exists()).toBe(true)
    w.unmount()
  }, 10000)

  it('renders on every other section', async () => {
    // Expedientes quedó archivado fuera de la navegación activa: las rutas
    // heredadas redirigen al mapa y el menú ya no expone dicho módulo.
    for (const path of ['/situacion', '/calculadora', '/map']) {
      const { w } = await mountApp({ path })
      expect(w.find('.brandbar').exists(), `sin menu en ${path}`).toBe(true)
      w.unmount()
    }
  })

  it('links to every active section', async () => {
    const { w } = await mountApp({ path: '/' })
    const hrefs = w.findAll('.brandbar-link').map((a) => a.attributes('href'))
    for (const p of ['/', '/situacion', '/calculadora']) {
      expect(hrefs, `falta el enlace a ${p}`).toContain(p)
    }
    expect(hrefs, 'Expedientes sigue visible en el menú activo').not.toContain('/expedientes')
    w.unmount()
  })

  it('is a flat menu, never a dropdown', async () => {
    // "Always visible" was the requirement. A menu behind a hamburger does not
    // satisfy it, and the shell used to have exactly that.
    const { w } = await mountApp({ path: '/' })
    const nav = w.find('.brandbar-nav').element
    // The active list is intentionally short: Mapa, Situación y Calculadora RF. The legacy
    // Expedientes module is archived and hidden from navigation.
    expect(nav.querySelectorAll('a').length).toBeGreaterThanOrEqual(3)
    expect(w.find('.brandbar-nav [aria-expanded]').exists()).toBe(false)
    w.unmount()
  })

  it('marks the current section', async () => {
    const { w } = await mountApp({ path: '/calculadora' })
    const on = w.findAll('.brandbar-link').filter((a) => a.classes('brandbar-link-on'))
    expect(on.length).toBe(1)
    expect(on[0].attributes('href')).toBe('/calculadora')
    w.unmount()
  })

  it('treats / and /map as the same section', async () => {
    const { w } = await mountApp({ path: '/map' })
    const on = w.findAll('.brandbar-link').filter((a) => a.classes('brandbar-link-on'))
    expect(on.length).toBe(1)
    expect(on[0].attributes('href')).toBe('/')
    w.unmount()
  })

  it('navigates when a link is followed', async () => {
    const { w, router } = await mountApp({ path: '/' })
    const link = w.findAll('.brandbar-link').find((a) => a.attributes('href') === '/calculadora')
    expect(link, 'falta el enlace a /calculadora').toBeTruthy()
    await link.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/calculadora')
    w.unmount()
  })
})

// ─── The brand and the lockup ───────────────────────────────────────────────

describe('the brand', () => {
  it('is visible and returns to the map', async () => {
    const { w, router } = await mountApp({ path: '/expedientes' })
    const brand = w.find('.brandbar-brand')
    expect(brand.exists(), 'sin marca').toBe(true)
    // The logo is bigger than the 22px it used to be, so it reads as a brand
    // and not as a status dot.
    const img = brand.find('img')
    expect(img.exists()).toBe(true)
    expect(img.attributes('alt')).toBe('')
    await brand.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/')
    w.unmount()
  })
})

describe('the institutional lockup', () => {
  it('names ENACOM and its full title', async () => {
    const { w } = await mountApp({ path: '/expedientes' })
    const lock = w.find('.brandbar-enacom')
    expect(lock.exists(), 'sin lockup institucional').toBe(true)
    // The mark is the institution's own file now, so the name ENACOM is carried
    // by the image's accessible name rather than by a run of text. Asserting
    // `text()` here failed the moment the official mark was used, which said
    // nothing true: what has to be readable is the name, and an `alt` is read by
    // a screen reader exactly as text would be.
    const img = lock.find('img')
    expect(img.exists(), 'el logo oficial debe estar presente').toBe(true)
    expect(img.attributes('alt')).toContain('ENACOM')
    // The full name is still text, and is still on screen.
    expect(lock.text()).toContain('Dirección Nacional de Control')
    expect(lock.text()).toContain('Fiscalización')
    w.unmount()
  })

  it('is present on the map too, so the affiliation is never hidden', async () => {
    const { w } = await mountApp({ path: '/' })
    expect(w.find('.brandbar-enacom').exists()).toBe(true)
    w.unmount()
  })

  it('shows the official mark white on the dark bar, with no white chip', async () => {
    // The supplied file is monochrome navy #0B1742 on transparent ground
    // (md5 1a314c…, the only ENACOM asset that exists). It sits directly on
    // the bar and is rendered white with `brightness(0) invert(1)`, which
    // remaps the ink and leaves the alpha alone — no white chip, no
    // rectangle behind the mark, proportions untouched.
    const { w } = await mountApp({ path: '/' })
    expect(w.find('.brandbar-enacom-chip').exists(), 'la ficha blanca debe desaparecer').toBe(false)
    const img = w.find('.brandbar-enacom-img')
    expect(img.exists(), 'el logo oficial debe estar presente').toBe(true)
    expect(img.attributes('src')).toContain('logoenacom')
    w.unmount()
  })
})

describe('the workspace does not mount a secondary institutional footer', () => {
  it.each(['/', '/situacion', '/calculadora'])('keeps the footer out of %s', async (path) => {
    const { w } = await mountApp({ path })
    expect(w.find('.footerbar').exists()).toBe(false)
    w.unmount()
  })
})

// ─── Height, read from the built CSS ─────────────────────────────────────────

describe('the bar is thin', () => {
  let css = ''

  beforeAll(() => {
    if (!existsSync(distAssets)) {
      throw new Error('Ejecutá `npm run build` antes de esta suite.')
    }
    const file = readdirSync(distAssets).find((f) => /^index-.*\.css$/.test(f))
    css = readFileSync(join(distAssets, file), 'utf8')
  })

  const rule = (name) => {
    const m = css.match(
      new RegExp(`(?<![a-z0-9_-])\\.${name}(?![a-z0-9_-])[^{}]*\\{([^}]*)\\}`, 'i'),
    )
    return m ? m[1] : null
  }

  it('stays at or under 56px, and 48px on the map', () => {
    const body = rule('brandbar')
    expect(body, 'falta .brandbar').toBeTruthy()
    const h = body.match(/height:\s*(\d+(?:\.\d+)?)px/)
    expect(h, 'sin altura fija').toBeTruthy()
    expect(Number(h[1])).toBeLessThanOrEqual(56)

    const compact = css.match(/\.brandbar-shell[^{}]*\{([^}]*)\}/)
    expect(compact, 'falta la variante compacta del mapa').toBeTruthy()
    const ch = compact[1].match(/height:\s*(\d+(?:\.\d+)?)px/)
    expect(Number(ch[1])).toBeLessThanOrEqual(48)
  })

  it('sits above the map controls but below the nav overlay', () => {
    // Leaflet's controls reach 1000. A header under that would be unclickable
    // where it overlaps the map.
    const body = rule('brandbar')
    const z = body.match(/z-index:\s*(\d+)/)
    expect(z, 'sin z-index').toBeTruthy()
    expect(Number(z[1])).toBeGreaterThan(1000)
    expect(Number(z[1])).toBeLessThan(1400)
  })

  it('does not let the operator select its text', () => {
    const body = rule('brandbar')
    expect(body).toMatch(/user-select\s*:\s*none/)
  })

  it('uses one compact, neutral treatment for every section link', () => {
    const link = rule('brandbar-link')
    const active = rule('brandbar-link-on')
    expect(link, 'falta el estilo base del menú').toBeTruthy()
    expect(active, 'falta el estado activo').toBeTruthy()
    expect(link).toMatch(/font-size:\s*\.6875rem/)
    expect(link).toMatch(/min-height:\s*34px/)
    expect(link).toMatch(/padding:\s*0\s+\.45rem/)
    expect(link).toMatch(/border-radius:\s*\.375rem/)
    expect(link).toMatch(/background:\s*transparent/)
    expect(link).toMatch(/color:\s*var\(--texto-tenue\)/)
    // The active link keeps the same transparent background as the rest: it
    // is marked by accent colour and underline only, so the three sections
    // read as one menu and not as differently filled buttons (spec 3.2).
    expect(active).toMatch(/background:\s*transparent/)
    expect(active).not.toMatch(/background:\s*var\(--panel\)/)
    expect(active).toMatch(/color:\s*var\(--signal\)/)
    expect(active).toMatch(/border-bottom-color:\s*var\(--signal\)/)
    expect(css).toMatch(/\.brandbar-link[^{}]*:hover[^{}]*\{[^}]*background:var\(--panel-alto\)/)
  })

  it('keeps section names visible until a narrow mobile viewport', () => {
    expect(css).toMatch(/@media\s*\(max-width:\s*560px\)[^{]*\{[^}]*\.brandbar-link-text/)
    expect(css).not.toMatch(/@media\s*\(max-width:\s*860px\)[^{]*\{[^}]*\.brandbar-link-text/)
  })

  it('shows a logo big enough to read as a brand', () => {
    // It was 22px, which is the size of a status dot. A brand mark has to be
    // recognisable at a glance, and the mark is a 128px raster, so the cost
    // of making it larger is bounded.
    const logo = rule('aerorf-logo')
    expect(logo, 'falta .aerorf-logo').toBeTruthy()
    const h = logo.match(/height:\s*(\d+(?:\.\d+)?)px/)
    expect(h, 'el logo no tiene altura fija en CSS').toBeTruthy()
    expect(Number(h[1])).toBeGreaterThanOrEqual(30)
    // And the size lives in CSS, not in a utility class that can go missing.
    const w = logo.match(/width:\s*(\d+(?:\.\d+)?)px/)
    expect(Number(w[1])).toBeGreaterThanOrEqual(30)
    expect(logo).toMatch(/object-fit\s*:\s*contain/)
  })

  it('fits the logo inside the compact bar', () => {
    // A 30px mark in a 48px bar leaves slack. A taller logo would force the
    // bar taller, which is what the compact variant exists to avoid.
    const logo = rule('aerorf-logo')
    const bar = css.match(/\.brandbar-shell[^{}]*\{([^}]*)\}/)
    const h = logo.match(/height:\s*(\d+(?:\.\d+)?)px/)
    const ch = bar[1].match(/height:\s*(\d+(?:\.\d+)?)px/)
    expect(Number(h[1])).toBeLessThan(Number(ch[1]))
  })
})

// ─── La baja de Espectro ────────────────────────────────────────────────────

describe('Espectro fue dado de baja', () => {
  // El operador decidió la baja total de la sección (0.30.32): el menú, la
  // ruta y la vista desaparecen. Tres guardas, porque son tres archivos que
  // se editan a mano — un menú, un enrutador y un view — y en una baja lo
  // que vuelve a romperse es exactamente eso: una entrada vieja que
  // sobrevive porque nadie miró ese archivo.
  it('no figura en el menú de secciones', async () => {
    const { w } = await mountApp({ path: '/' })
    const hrefs = w.findAll('.brandbar-link').map((a) => a.attributes('href'))
    expect(hrefs, 'el menú volvió a ofrecer /espectro').not.toContain('/espectro')
    expect(w.text(), 'el menú volvió a nombrar Espectro').not.toContain('Espectro')
    w.unmount()
  })

  it('la ruta /espectro ya no está registrada', async () => {
    const { default: router } = await import('@/router')
    const r = router.resolve('/espectro')
    expect(
      r.matched.some((m) => m.path === '/espectro'),
      'el enrutador todavía registra /espectro',
    ).toBe(false)
  })

  it('la vista fue borrada del fuente', () => {
    expect(
      existsSync(join(here, '..', 'src', 'views', 'EspectroView.vue')),
      'sigue src/views/EspectroView.vue: la baja total no se hizo',
    ).toBe(false)
  })
})

// ─── La baja de Panel ───────────────────────────────────────────────────────

describe('Panel fue dado de baja', () => {
  // Mismo motivo que Espectro (0.30.32) y misma estructura, un año después:
  // el operador decidió la baja total de la sección Panel (0.30.33). Otra
  // vez son archivos editados a mano donde una entrada vieja sobrevive sin
  // que nada la contradiga — el menú, el enrutador y el view — más
  // StatCard.vue, que se borró con la vista porque el Panel era su único
  // consumidor (antes de borrar se grepeó).
  it('no figura en el menú de secciones', async () => {
    const { w } = await mountApp({ path: '/' })
    const hrefs = w.findAll('.brandbar-link').map((a) => a.attributes('href'))
    expect(hrefs, 'el menú volvió a ofrecer /dashboard').not.toContain('/dashboard')
    // Sólo el menú: el panel izquierdo del mapa se llama «Panel Herramientas»
    // y eso no es la sección Panel que se dio de baja.
    const etiquetas = w.findAll('.brandbar-link').map((a) => a.text())
    expect(
      etiquetas.some((t) => t.includes('Panel')),
      'el menú volvió a nombrar la sección Panel',
    ).toBe(false)
    w.unmount()
  })

  it('la ruta /dashboard ya no está registrada', async () => {
    const { default: router } = await import('@/router')
    const r = router.resolve('/dashboard')
    expect(
      r.matched.some((m) => m.path === '/dashboard'),
      'el enrutador todavía registra /dashboard',
    ).toBe(false)
  })

  it('la vista y su StatCard fueron borrados del fuente', () => {
    expect(
      existsSync(join(here, '..', 'src', 'views', 'DashboardView.vue')),
      'sigue src/views/DashboardView.vue: la baja total no se hizo',
    ).toBe(false)
    expect(
      existsSync(join(here, '..', 'src', 'components', 'StatCard.vue')),
      'sigue src/components/StatCard.vue, sin consumidor desde la baja',
    ).toBe(false)
  })
})
