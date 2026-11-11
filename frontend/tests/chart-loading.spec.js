/**
 * tests/chart-loading.spec.js
 * ─────────────────────────
 * La calculadora tiene que abrir sin una librería de graficación — y en
 * AeroRF 2.5, sin ninguna librería de graficación.
 *
 * Historia en tres actos, porque los tres defectos valen la pena seguir
 * protegiendo:
 *
 *   1. `Chart.vue` importaba plotly de forma estática: entrar en la
 *      calculadora era bajar y parsear 1085 KB antes de pintar nada. La
 *      pantalla parecía colgada.
 *   2. La importación se volvió dinámica (este spec, en su versión anterior):
 *      la vista pintaba primero y la librería llegaba detrás de un
 *      placeholder.
 *   3. AeroRF 2.5 sacó la calculadora del negocio de graficar: el único
 *      gráfico era la «Distribución de Scores», dibujada sobre una
 *      probabilidad que no existía (era un score heurístico). Se fueron el
 *      gráfico, `Chart.vue` y la dependencia `plotly.js`.
 *
 * Lo que queda por defender es la propiedad que justificaba todo: que en el
 * grafo de módulos de la calculadora — y de la app entera — no haya código de
 * graficación. Estos tests leen el build porque eso es lo único que ve el
 * peso real de un bundle.
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

describe('the calculator ships no charting code', () => {
  it('keeps the calculator view small', () => {
    // La vista misma: controles, tablas, detalle. Si algún día vuelve a
    // arrastrar una librería de gráficos, es acá donde aparece el peso.
    const view = chunks.find((c) => c.name.startsWith('CalculadoraRFView'))
    expect(view, 'no se encontro el chunk de la calculadora').toBeTruthy()
    expect(
      kb(view.size),
      `CalculadoraRFView pesa ${kb(view.size)} KB: arrastra la libreria de graficos`,
    ).toBeLessThan(60)
  })

  it('leaves plotly out of the bundle graph', () => {
    // Antes: el chunk `plotly` existía y pesaba >100 KB (bajado aparte, en
    // diferido). Ahora no tiene que existir ni diferido: nadie lo importa.
    const lib = chunks.find((c) => c.name.startsWith('plotly'))
    expect(
      lib,
      'el chunk de plotly volvio al build: alguien volvio a importar la libreria',
    ).toBeUndefined()
  })

  it('leaves no chart wrapper behind', () => {
    // `Chart.vue` se eliminó junto con su único importador. Si reaparece un
    // chunk que arranque con «Chart», es que el componente volvió.
    const chart = chunks.find((c) => c.name.startsWith('Chart'))
    expect(chart, 'aparecio un chunk Chart: el wrapper de graficos regreso').toBeUndefined()
  })

  it('does not make the map wait for it', () => {
    // El mapa es la pantalla donde vive el operador. Arranca liviano.
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
    // Un `modulepreload` de plotly arrancaría la descarga al primer paint,
    // que era exactamente el defecto original.
    const html = readFileSync(join(here, '..', 'dist', 'index.html'), 'utf8')
    expect(html).not.toMatch(/modulepreload[^>]*plotly/i)
  })
})

describe('the source keeps charting out of the app', () => {
  const src = join(here, '..', 'src')
  const fuenteVista = () => readFileSync(join(src, 'views', 'CalculadoraRFView.vue'), 'utf8')

  const recorrer = (dir) =>
    readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
      const ruta = join(dir, e.name)
      return e.isDirectory() ? recorrer(ruta) : [ruta]
    })

  it('has no reference to plotly anywhere in src', () => {
    // Ni import, ni comentario, ni string suelto: si el nombre no está, no
    // hay forma de que el grafo de módulos lo incluya.
    const conPlotly = recorrer(src)
      .filter((p) => /\.(vue|js)$/.test(p))
      .filter((p) => /plotly/i.test(readFileSync(p, 'utf8')))
    expect(
      conPlotly.map((p) => p.replace(/^.*src[\\/]/, '')),
      'src menciona plotly: la libreria de graficos volvio al proyecto',
    ).toEqual([])
  })

  it('does not import a chart component in the calculator', () => {
    const s = fuenteVista()
    expect(s).not.toMatch(/<Chart\b|import\s+Chart\b/)
    // Y la carga de resultados no vende probabilidades falsas: eso era lo
    // que el gráfico único graficaba.
    expect(s).not.toContain('Proximidad')
    expect(s).not.toContain('Distribución de Scores')
  })

  it('deleted the chart wrapper instead of leaving it dead in the tree', () => {
    // Un componente sin importadores no viaja al build, pero sí engaña al
    // siguiente: alguien lo leería como algo que se usa.
    expect(existsSync(join(src, 'components', 'Chart.vue'))).toBe(false)
  })
})
