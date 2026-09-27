/**
 * tests/chart-loading.spec.js
 * ─────────────────────────
 * The RF calculator must open without waiting for a megabyte of charting.
 *
 * The bug
 * ───────
 * `Chart.vue` imported the plotting library statically. That put it in the
 * module graph of every view showing a chart, so entering the calculator meant
 * downloading and parsing 1085 KB before the page could paint anything. The
 * section looked like it had hung.
 *
 * The fix is a dynamic import: the view renders first and the library arrives
 * behind a placeholder. These tests read the build output, because the claim
 * is about the bundle graph and nothing else can see it.
 */

import { describe, it, expect, beforeAll } from 'vitest'
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const distAssets = join(here, '..', 'dist', 'assets')

let chunks = []

beforeAll(() => {
  if (!existsSync(distAssets)) {
    throw new Error('Ejecutá `npm run build` antes de esta suite.')
  }
  chunks = readdirSync(distAssets)
    .filter((f) => f.endsWith('.js'))
    .map((f) => ({ name: f, size: readFileSync(join(distAssets, f)).length }))
})

const kb = (bytes) => Math.round(bytes / 1024)

describe('the calculator opens without the charting library', () => {
  it('keeps the calculator view small', () => {
    // The view itself: controls, tables, results. It has no business
    // carrying a charting library.
    const view = chunks.find((c) => c.name.startsWith('CalculadoraRFView'))
    expect(view, 'no se encontro el chunk de la calculadora').toBeTruthy()
    expect(
      kb(view.size),
      `CalculadoraRFView pesa ${kb(view.size)} KB: arrastra la libreria de graficos`,
    ).toBeLessThan(60)
  })

  it('keeps the chart wrapper small, so it can render before the library', () => {
    const chart = chunks.find((c) => c.name.startsWith('Chart'))
    expect(chart, 'no se encontro el chunk de Chart').toBeTruthy()
    // 3 KB: the component, not the library.
    expect(
      kb(chart.size),
      `Chart pesa ${kb(chart.size)} KB: la importacion sigue siendo estatica`,
    ).toBeLessThan(60)
  })

  it('leaves the library in a chunk of its own', () => {
    const lib = chunks.find((c) => c.name.startsWith('plotly'))
    expect(lib, 'la libreria no quedo en su propio chunk').toBeTruthy()
    expect(kb(lib.size)).toBeGreaterThan(100)
  })

  it('does not make the map wait for it', () => {
    // The map is the screen an operator lives in. It has to start small.
    for (const prefix of ['vendor', 'index', 'GisShell']) {
      const chunk = chunks.find((c) => c.name.startsWith(prefix))
      expect(chunk, `falta el chunk ${prefix}`).toBeTruthy()
      expect(
        kb(chunk.size),
        `${prefix} pesa ${kb(chunk.size)} KB: el mapa carga de mas`,
      ).toBeLessThan(400)
    }
  })

  it('is not preloaded in the document head', () => {
    // A `modulepreload` in index.html would start the download at first paint,
    // which is the thing being fixed.
    const html = readFileSync(join(here, '..', 'dist', 'index.html'), 'utf8')
    expect(html).not.toMatch(/modulepreload[^>]*plotly/i)
  })
})

describe('the source keeps the import dynamic', () => {
  const source = () => readFileSync(join(here, '..', 'src', 'components', 'Chart.vue'), 'utf8')

  it('has no static import of the library', () => {
    const s = source()
    // A bare `import Plotly from ...` is the defect. A dynamic
    // `await import(...)` is the fix, and the two are not interchangeable.
    expect(
      s,
      'la libreria esta importada de forma estatica: bloquea el pintado',
    ).not.toMatch(/^\s*import\s+\w+\s+from\s+['"]plotly/m)
    expect(s).toMatch(/await\s+import\(\s*['"]plotly/)
  })

  it('shows a placeholder while the library arrives', () => {
    // Without this the box is blank for over a second, which reads as broken
    // rather than slow.
    const s = source()
    expect(s).toMatch(/Cargando el motor de gr/)
  })

  it('offers a retry if the load fails', () => {
    const s = source()
    expect(s).toMatch(/Reintentar/)
    expect(s).toMatch(/catch/)
  })

  it('fetches the library once, not once per chart', () => {
    // Several charts on one page must not each trigger a fetch.
    const s = source()
    const dynamic = s.match(/await\s+import\(\s*['"]plotly/g) || []
    expect(dynamic.length, 'varias importaciones dinamicas: una por instancia')
      .toBeLessThanOrEqual(1)
    expect(s).toMatch(/if\s*\(\s*!library\s*\)/)
  })
})
