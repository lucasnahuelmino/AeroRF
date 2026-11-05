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

/**
 * The value a property ends up with, following `var(--token)` to its declaration.
 *
 * Every colour now goes through `assets/tokens.css`, so a test that reads the
 * built stylesheet finds `background:var(--panel)` and not a colour. Asserting on
 * the literal a property used to carry is how a test ends up protecting the
 * spelling instead of the thing: the right-click menu test failed the moment its
 * background became a token, against a menu that was perfectly opaque.
 *
 * Resolution takes one hop, and a second if the token is itself a reference.
 * Anything it cannot resolve comes back as the raw string, so a typo shows up as a
 * wrong value rather than as null.
 */
function tokenValue(css, className, property) {
  const cuerpo = ruleFor(css, className)
  if (!cuerpo) return null
  const bruto = cuerpo.match(new RegExp(`(?:^|;)\\s*${property}\\s*:\\s*([^;}]+)`))
  if (!bruto) return null
  const valor = bruto[1].trim()

  const ref = valor.match(/^var\(\s*(--[a-z-]+)\s*(?:,\s*([^)]+))?\)$/i)
  if (!ref) return valor
  const buscar = (nombre) => {
    const m = css.match(new RegExp(`${nombre}\\s*:\\s*([^;}]+)`))
    return m ? m[1].trim() : null
  }
  const declarada = buscar(ref[1])
  if (!declarada) return ref[2] || null
  if (/^var\(/i.test(declarada)) {
    const otra = declarada.match(/^var\(\s*(--[a-z-]+)\s*\)$/i)
    if (otra) return buscar(otra[1]) ?? ref[2] ?? null
  }
  return declarada
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

  it('uses a single contextual Workspace instead of a separate tool strip and tabs', () => {
    const home = ruleFor(css, 'gis-workspace-home')
    const category = ruleFor(css, 'gis-workspace-category')
    expect(home, 'falta la navegación principal del Workspace').toBeTruthy()
    expect(category, 'faltan las categorías contextuales').toBeTruthy()
    expect(css).not.toContain('.gis-toolstrip')
    expect(css).not.toContain('.gis-tab')
  })

  it('offers one adjustable Workspace on either side of the map', () => {
    const resizer = ruleFor(css, 'gis-resizer')
    expect(resizer, 'falta .gis-resizer').toBeTruthy()
    expect(resizer).toContain('cursor:col-resize')
    expect(ruleFor(css, 'gis-resizer-r')).toBeTruthy()
    expect(ruleFor(css, 'gis-resizer-l')).toBeTruthy()
    expect(ruleFor(css, 'gis-workspace-right')).toContain('flex-direction:row-reverse')
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

  it('puts the AeroRF mark at 34px, big enough to read and small enough for a 48px bar', () => {
    // The operator asked for it a little larger. 30px was the previous size; 34
    // is what it is now, and it is pinned here so "a little larger" does not
    // quietly become "fills the bar" later. The compact bar is 48px, so 34
    // leaves 7px above and below: the mark grows without the header growing,
    // and on the map the header's height comes out of the map's.
    const logo = ruleFor(css, 'aerorf-logo')
    expect(logo, 'falta .aerorf-logo').toBeTruthy()
    expect(logo).toMatch(/height:\s*34px/)
    expect(logo).toMatch(/width:\s*34px/)
  })

  it('keeps the institutional mark in the header', () => {
    const header = ruleFor(css, 'brandbar-enacom-img')
    expect(header, 'falta .brandbar-enacom-img').toBeTruthy()
    expect(Number.isFinite(Number(header.match(/height:\s*(\d+)px/)?.[1]))).toBe(true)
    expect(ruleFor(css, 'footerbar-logo')).toBeNull()
    const chip = ruleFor(css, 'brandbar-enacom-chip')
    expect(chip, 'falta el fondo blanco del logo oficial').toMatch(
      /background(-color)?:\s*(#fff(fff)?|white|rgb\(255,\s*255,\s*255\))/i,
    )
  })

  it('takes only the header out of the map height', () => {
    const shell = ruleFor(css, 'gis-shell')
    expect(shell, 'falta .gis-shell').toBeTruthy()
    expect(shell, 'la altura del shell debe descontar la cabecera')
      .toMatch(/height:\s*calc\([^}]*var\(--brandbar-h/)
    expect(shell).not.toContain('--footerbar-h')
  })

  it('replaces Leaflet\'s grab hand with a crosshair over the map', () => {
    // Leaflet's own stylesheet sets `cursor: grab` on the map container, so the
    // pointer over open ground was an open hand — and a hand hides the exact
    // point under the cursor, which is the whole job on a map.
    //
    // The selector needs two classes to beat Leaflet's rule no matter which
    // stylesheet is emitted last, so the test requires the qualifier rather
    // than just any cursor declaration.
    expect(css, 'el mapa debe definir su cursor').toMatch(
      /\.gis-map-area[^{]*\.leaflet-container[^{]*\{[^}]*cursor:\s*crosshair/i,
    )
  })

  it('keeps the pointer on interactive objects, so a clickable thing still says so', () => {
    expect(css).toMatch(/\.gis-map-area[^{]*\.leaflet-interactive[^{]*\{[^}]*cursor:\s*pointer/i)
  })

  it('gives the right-click menu a solid ground of its own', () => {
    // It was `bg-slate-900/98` in the template. Tailwind's opacity scale stops at
    // 95, so **98 was never generated**: the menu had no background at all and
    // the map showed through its text. Checked against the built CSS — the only
    // `.bg-slate-900/N` rule in the bundle was `/60`.
    const menu = ruleFor(css, 'aerorf-context')
    expect(menu, 'falta .aerorf-context').toBeTruthy()

      // Resolved through its token, so this asserts the colour that reaches the
      // screen and not how it was spelled. When the palette moved to tokens.css
      // this background became a var() reference and the old hex test failed
      // against a menu that was perfectly opaque. That is the shape of assertion
      // that gets deleted rather than fixed, and the original bug then walks
      // back in through it.
      //
      // Opacity is still checked, on the resolved colour: an eight-digit hex or a
      // fractional rgba() would still fail, which is the defect this covered.
      const fondo = tokenValue(css, 'aerorf-context', 'background')
      expect(fondo, 'el menu necesita un fondo propio').toBeTruthy()
      expect(fondo, 'el fondo debe ser opaco: seis digitos, sin canal alfa').toMatch(
        /^#(?:[0-9a-f]{6})$/i,
      )
  })

  it('keeps Workspace category and task labels readable in a narrow panel', () => {
    const sidebar = ruleFor(css, 'gis-sidebar')
    const category = ruleFor(css, 'gis-workspace-category')
    const label = ruleFor(css, 'gis-workspace-category strong')
    expect(sidebar, 'falta el panel Workspace').toContain('min-width:0')
    expect(category, 'faltan las filas de categoría').toContain('display:flex')
    expect(label, 'los nombres de categoría deben conservar jerarquía tipográfica').toContain('font-weight:600')
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
