/**
 * tests/layout.spec.js
 * ────────────────────
 * Layout regressions in the GIS shell.
 *
 * Why a separate file
 * ───────────────────
 * The three complaints that started this file were all *proportion*
 * problems, and none of them is a JavaScript problem:
 *
 *   - the map was too small
 *   - the logo covered the screen
 *   - the tools were awkward
 *
 * Every one of them had the same root cause: `styles.css` had no
 * `@tailwind` directives, so the content scanner ran and produced nothing
 * and every utility class was a dead class. `h-6` on a 1024x1024 PNG did
 * nothing, so the browser drew it at its natural size.
 *
 * These assertions read the built CSS, because that is where a dead utility
 * class is actually visible. Asserting on the stylesheet is the only way to
 * catch "the class is absent from the output", which is precisely the bug
 * that shipped.
 */

import { describe, it, expect, beforeAll } from 'vitest'
import { readFileSync, existsSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const frontend = join(here, '..')
const distAssets = join(frontend, 'dist', 'assets')

/** Concatenate every built CSS chunk: Tailwind lands in one, SFC styles in others. */
function readBuiltCss() {
  if (!existsSync(distAssets)) return null
  return readdirSync(distAssets)
    .filter((f) => f.endsWith('.css'))
    .map((f) => readFileSync(join(distAssets, f), 'utf8'))
    .join('\n')
}

/**
 * Return the body of a rule for `className`.
 *
 * Scoped SFC styles compile to `.gis-toolbar[data-v-abc123]`, so a plain
 * `\.gis-toolbar\s*\{` never matches. The hash is part of the selector, not
 * the rule, and matching on the boundary keeps `.gis-toolbar` from also
 * matching `.gis-toolbar-extra`.
 */
function ruleFor(css, className) {
  const re = new RegExp(
    `(?<![a-z0-9_-])\\.${className}(?![a-z0-9_-])[^{}]*\\{([^}]*)\\}`
  )
  const m = css.match(re)
  return m ? m[1] : null
}

describe('Tailwind is actually generating utilities', () => {
  let css = null

  beforeAll(() => {
    css = readBuiltCss()
    if (!css) {
      throw new Error(
        'No hay CSS construido. Ejecutá `npm run build` antes de esta suite: ' +
          'comprobar la salida es justamente el punto de estas pruebas.',
      )
    }
  })

  it('emits the utilities the shell layout depends on', () => {
    // Leaflet's own reset supplies display:flex, position:absolute and
    // overflow:hidden regardless, so their presence proves nothing about
    // Tailwind. These are the declarations only Tailwind can produce: the
    // toolbar alignment and the flex shrink guard are written in no vendor
    // stylesheet.
    for (const decl of ['align-items:center', 'justify-content:center', 'min-width:0']) {
      expect(css, `falta la propiedad ${decl}`).toContain(decl)
    }
  })

  it('emits the spacing and sizing utilities the templates use', () => {
    // This is the assertion that reproduces the original bug. Removing the
    // `@tailwind` directives leaves every one of these absent, because the
    // SFC styles that use them are scoped and never mention them.
    for (const cls of ['.inset-0', '.min-w-0', '.flex-1', '.truncate', '.overflow-y-auto']) {
      expect(css, `falta la clase ${cls}`).toContain(cls)
    }
  })

  it('does not style buttons globally', () => {
    // The old stylesheet had a bare `button { background: var(--primary);
    // padding: 8px 12px }`, which turned each of the ten map tools into an
    // oversized blue rectangle. Tailwind's preflight is the correct answer,
    // and it must not be overridden by a page-level rule.
    const bare = css.match(/(^|[},;])\s*button\s*\{[^}]*\}/g) || []
    for (const rule of bare) {
      expect(rule).not.toMatch(/background:\s*(var\(--primary\)|#2563eb|#1d4ed8)/)
    }
  })

  it('caps the document column but not the map', () => {
    // max-width: 1180px on <main> was leaving a wide monitor with the map
    // floating in the middle of empty space. The cap belongs to .page-doc.
    expect(css).toContain('.page-doc')
    expect(css).toMatch(/main\.gis-map-area\s*\{[^}]*max-width:\s*none/)
  })
})

describe('Shell proportions', () => {
  let css = null

  beforeAll(() => {
    css = readBuiltCss()
  })

  it('gives the map the leftover width', () => {
    // Without min-width:0 a flex item refuses to shrink below its content and
    // a wide panel pushes the map off screen instead of the map growing.
    const mapArea = ruleFor(css, 'gis-map-area')
    expect(mapArea, 'falta .gis-map-area').toBeTruthy()
    expect(mapArea).toContain('flex:1 1 auto')
    expect(mapArea).toContain('min-width:0')
  })

  it('positions the map absolutely inside its area', () => {
    const map = ruleFor(css, 'gis-map')
    expect(map, 'falta .gis-map').toBeTruthy()
    expect(map).toContain('position:absolute')
    // The minifier expands `inset:0` into the four longhands.
    const zeroed = ['top', 'right', 'bottom', 'left'].every(
      (side) => new RegExp(`${side}:0`).test(map),
    )
    expect(zeroed, 'el mapa no esta pegado a los cuatro bordes').toBe(true)
  })

  it('keeps the toolbar short enough to stay out of the way', () => {
    const bar = ruleFor(css, 'gis-toolbar')
    expect(bar, 'falta .gis-toolbar').toBeTruthy()
    // 46px: tall enough for an icon and a readable label.
    const px = bar.match(/height:\s*(\d+(?:\.\d+)?)px/)
    expect(px, 'la barra deberia tener una altura fija en px').toBeTruthy()
    expect(Number(px[1])).toBeLessThanOrEqual(52)
    expect(Number(px[1])).toBeGreaterThanOrEqual(40)
  })

  it('gives the tools a hit area big enough to use', () => {
    const tool = ruleFor(css, 'gis-tool')
    expect(tool, 'falta .gis-tool').toBeTruthy()
    // 38px tall and 52px wide: comfortably clickable without dominating.
    const h = tool.match(/height:\s*(\d+(?:\.\d+)?)px/)
    const w = tool.match(/width:\s*(\d+(?:\.\d+)?)px/)
    expect(Number(h[1])).toBeGreaterThanOrEqual(34)
    expect(Number(w[1])).toBeGreaterThanOrEqual(44)
  })

  it('has a visible state for the active tool', () => {
    // The selector keeps the scope hash, so match the combined name directly.
    const m = css.match(/\.gis-tool\.active[^{}]*\{([^}]*)\}/)
    expect(m, 'falta el estado activo de la herramienta').toBeTruthy()
    expect(m[1]).toContain('background')
  })

  it('lets the tool strip scroll instead of pushing the status pills off', () => {
    const strip = ruleFor(css, 'gis-toolstrip')
    expect(strip, 'falta .gis-toolstrip').toBeTruthy()
    expect(strip).toContain('overflow-x:auto')
    expect(strip).toContain('min-width:0')
  })

  it('collapses the tool hint when it is empty', () => {
    // An always-visible empty hint would reserve a gap in the toolbar and
    // steal width from the map for no reason.
    const hint = ruleFor(css, 'gis-hint')
    expect(hint, 'falta .gis-hint').toBeTruthy()
    expect(hint).toMatch(/opacity:\s*0/)
    expect(ruleFor(css, 'gis-hint-on')).toBeTruthy()
  })

  it('offers a drag handle on both side panels', () => {
    // The map is the working surface: the operator decides how much window
    // the panels take, rather than the stylesheet deciding for them.
    const resizer = ruleFor(css, 'gis-resizer')
    expect(resizer, 'falta .gis-resizer').toBeTruthy()
    expect(resizer).toContain('cursor:col-resize')
    expect(ruleFor(css, 'gis-resizer-r')).toBeTruthy()
    expect(ruleFor(css, 'gis-resizer-l')).toBeTruthy()
  })
})

describe('The brand mark cannot size itself again', () => {
  let css = null

  beforeAll(() => {
    css = readBuiltCss()
  })

  it('pins the logo size in CSS, not in a utility class', () => {
    // The bug was `class="h-6 w-auto"` where `h-6` did not exist, so the
    // browser drew a 1024x1024 square over the whole screen. The size must
    // live in a rule that cannot silently stop being generated.
    const logo = ruleFor(css, 'aerorf-logo')
    expect(logo, 'falta .aerorf-logo').toBeTruthy()
    expect(logo).toMatch(/height:\s*\d+px/)
    expect(logo).toMatch(/width:\s*\d+px/)
  })

  it('never lets an image overflow its box', () => {
    expect(css).toMatch(/img[^{]*\{[^}]*max-width:\s*100%/)
  })

  it('ships a small logo, not the 1.4 MB master', () => {
    const src = join(frontend, 'src', 'assets', 'aerorf-128.png')
    expect(existsSync(src), 'falta aerorf-128.png').toBe(true)
    const size = readFileSync(src).length
    expect(size).toBeLessThan(64 * 1024)

    // And nothing may still import the master.
    for (const p of ['src/App.vue', 'src/views/GisShell.vue']) {
      const text = readFileSync(join(frontend, p), 'utf8')
      expect(text, `${p} todavia importa el PNG de 1.4 MB`).not.toMatch(
        /assets\/aerorf\.png/,
      )
    }
  })
})
