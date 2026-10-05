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

// El stub de /espectro se quitó con la baja total de la sección (0.30.32):
// esta lista imita el enrutador real, y el enrutador real ya no registra
// esa ruta. Las guardas de la baja están al final del archivo.
const ROUTES = [
  { path: '/', name: 'Map', component: { template: '<div class="gis-map" />' } },
  { path: '/map', name: 'Mapa', component: { template: '<div class="gis-map" />' } },
  { path: '/dashboard', name: 'Panel', component: { template: '<div />' } },
  { path: '/expedientes', name: 'Expedientes', component: { template: '<div />' } },
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
  })

  it('renders on every other section', async () => {
    // /espectro se quitó de la lista con la baja total de la sección
    // (0.30.32): la ruta ya no existe, el enlace tampoco. Las guardas de
    // esa baja están al final del archivo.
    for (const path of ['/dashboard', '/expedientes', '/calculadora', '/map']) {
      const { w } = await mountApp({ path })
      expect(w.find('.brandbar').exists(), `sin menu en ${path}`).toBe(true)
      w.unmount()
    }
  })

  it('links to every section', async () => {
    const { w } = await mountApp({ path: '/' })
    const hrefs = w.findAll('.brandbar-link').map((a) => a.attributes('href'))
    // La lista es la de las secciones que quedan: Espectro se dio de baja
    // total (0.30.32), y la guarda al final del archivo comprueba que no
    // vuelva a aparecer.
    for (const p of ['/', '/dashboard', '/expedientes', '/calculadora']) {
      expect(hrefs, `falta el enlace a ${p}`).toContain(p)
    }
    w.unmount()
  })

  it('is a flat menu, never a dropdown', async () => {
    // "Always visible" was the requirement. A menu behind a hamburger does not
    // satisfy it, and the shell used to have exactly that.
    const { w } = await mountApp({ path: '/' })
    const nav = w.find('.brandbar-nav').element
    // The links are in the document, not behind a click.
    // Cuatro enlaces desde la baja de Espectro (0.30.32): Mapa, Panel,
    // Expedientes y Calculadora RF.
    expect(nav.querySelectorAll('a').length).toBeGreaterThanOrEqual(4)
    expect(w.find('.brandbar-nav [aria-expanded]').exists()).toBe(false)
    w.unmount()
  })

  it('marks the current section', async () => {
    const { w } = await mountApp({ path: '/expedientes' })
    const on = w.findAll('.brandbar-link').filter((a) => a.classes('brandbar-link-on'))
    expect(on.length).toBe(1)
    expect(on[0].attributes('href')).toBe('/expedientes')
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
    const link = w.findAll('.brandbar-link').find((a) => a.attributes('href') === '/dashboard')
    await link.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/dashboard')
    w.unmount()
  })
})

// ─── The brand and the lockup ───────────────────────────────────────────────

describe('the brand', () => {
  it('is visible and returns to the map', async () => {
    const { w, router } = await mountApp({ path: '/dashboard' })
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
    const { w } = await mountApp({ path: '/dashboard' })
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

  it('sits the official mark on white, because the mark is dark navy', async () => {
    // Measured off the supplied file: RGB(11, 23, 66) on a transparent
    // ground. On this bar's near-black that is invisible, so the mark goes on a
    // white chip. A filter that lightened it instead would be a different logo,
    // and "put the logo correctly" means the colours as they are.
    const { w } = await mountApp({ path: '/' })
    const chip = w.find('.brandbar-enacom-chip')
    expect(chip.exists(), 'el logo debe ir sobre un fondo blanco').toBe(true)
    expect(chip.find('img').attributes('src')).toContain('logoenacom')
    w.unmount()
  })
})

describe('the institutional footer', () => {
  it('names the Directorate and repeats the mark, smaller', async () => {
    const { w } = await mountApp({ path: '/dashboard' })
    const foot = w.find('.footerbar')
    expect(foot.exists(), 'sin pie institucional').toBe(true)
    expect(foot.text()).toContain('Dirección Nacional de Control y Fiscalización')
    const img = foot.find('img')
    expect(img.exists()).toBe(true)
    expect(img.attributes('alt')).toContain('ENACOM')
    expect(img.attributes('src')).toContain('logoenacom')
    w.unmount()
  })

  it('is on the map too, where the operator spends the day', async () => {
    // It costs the map 26px, which was accepted. A footer that only existed on
    // the screens the operator visits least would be the one missing when it
    // is needed.
    const { w } = await mountApp({ path: '/' })
    expect(w.find('.footerbar').exists()).toBe(true)
    w.unmount()
  })

  it('repeats the mark on a white chip, as the header does', async () => {
    const { w } = await mountApp({ path: '/' })
    expect(w.find('.footerbar .footerbar-chip').exists()).toBe(true)
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
