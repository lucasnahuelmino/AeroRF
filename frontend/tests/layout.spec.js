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

  it('repeats the ENACOM mark smaller in the footer than in the header', () => {
    // 17px in the header, 12px in the footer. Both are in scoped rules, and
    // jsdom does not compute scoped styles, so the sizes are read from the
    // built CSS — which is the only place they actually exist.
    const header = ruleFor(css, 'brandbar-enacom-img')
    const footer = ruleFor(css, 'footerbar-logo')
    expect(header, 'falta .brandbar-enacom-img').toBeTruthy()
    expect(footer, 'falta .footerbar-logo').toBeTruthy()
    const h = Number(header.match(/height:\s*(\d+)px/)?.[1])
    const f = Number(footer.match(/height:\s*(\d+)px/)?.[1])
    expect(Number.isFinite(h) && Number.isFinite(f), 'ambos tamaños deben estar en px').toBe(true)
    expect(f, 'el logo del pie debe ser mas pequeno que el de la cabecera')
      .toBeLessThan(h)
  })

  it('gives both institutional marks a white ground, because the mark is dark navy', () => {
    // Measured off the supplied file: RGB(11, 23, 66) on transparent. On this
    // interface's near-black that is invisible. A white chip keeps the official
    // colours exactly as they are; a filter that lightened the mark instead
    // would be a different logo.
    for (const cls of ['brandbar-enacom-chip', 'footerbar-chip']) {
      const rule = ruleFor(css, cls)
      expect(rule, `falta .${cls}`).toBeTruthy()
      expect(rule, `.${cls} debe llevar fondo blanco`).toMatch(
        /background(-color)?:\s*(#fff(fff)?|white|rgb\(255,\s*255,\s*255\))/i,
      )
    }
  })

  it('takes the two fixed bars out of the map height, so the shell is exactly one screen', () => {
    // The shell asked for a full viewport *and* sat below a header and above a
    // footer, so the page grew by 74px and the map's bottom edge, with it the
    // status bar, fell off the screen. A scrolling map on a screen meant to be
    // one fixed view.
    const shell = ruleFor(css, 'gis-shell')
    expect(shell, 'falta .gis-shell').toBeTruthy()
    // `[^}]*` rather than `[^)]*`: the declaration carries the bars' fallbacks,
    // `var(--brandbar-h, 48px)`, and a bracket closes the group.
    expect(shell, 'la altura del shell debe descontar las dos barras')
      .toMatch(/height:\s*calc\([^}]*var\(--brandbar-h[^}]*var\(--footerbar-h/)
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

    // Six hex digits and no more. The lookahead matters and was found by
    // reverting: the minifier turns `rgba(15, 23, 42, 0.45)` into the 8-digit
    // `#0f172a73`, and a plain `/#[0-9a-f]{6}/` matches the first six of those
    // and passes a menu that is 45% opaque. A negative lookahead for another hex
    // digit is what tells an opaque colour from a translucent one.
    expect(menu, 'el menu necesita un fondo opaco').toMatch(
      /background(-color)?:\s*#(?:[0-9a-f]{6})(?![0-9a-f])/i,
    )
    expect(menu, 'un fondo con alfa no se ve sobre el mapa').not.toMatch(
      /background(-color)?:\s*#[0-9a-f]{8}(?![0-9a-f])/i,
    )
    // Belt and braces: if the output ever keeps the functional notation instead
    // of the 8-digit hex, a fractional alpha is still a translucent colour.
    expect(menu).not.toMatch(/rgba\([^)]*,\s*0?\.\d+\s*\)/i)
  })

  it('lets the five panel tabs keep their own width instead of shrinking out of sight', () => {
    // `flex: 1 1 0` let all five shrink below what their text needed, and the
    // last one — Expediente — was pushed off the strip entirely: the strip
    // needed 312px and the sidebar has 215. `flex: 0 1 auto` plus a `nowrap`
    // label makes the five fit or visibly truncate, which is a different and
    // recoverable failure.
    const tab = ruleFor(css, 'gis-tab')
    expect(tab, 'falta .gis-tab').toBeTruthy()
    expect(tab).toMatch(/flex:\s*0 1 auto/)
    const label = ruleFor(css, 'gis-tab-label')
    expect(label, 'falta .gis-tab-label').toBeTruthy()
    expect(label, 'el rotulo no debe partirse en dos lineas').toMatch(/white-space:\s*nowrap/)
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
