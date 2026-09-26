/**
 * tests/toolbar.spec.js
 * ────────────────────
 * The tool buttons, checked against the built CSS.
 *
 * Why the CSS and not the markup
 * ─────────────────────────────
 * jsdom does not lay anything out: `getBoundingClientRect()` returns zeros
 * and `getComputedStyle` returns empty strings for styles from a `scoped`
 * block. A test that asked "how wide is the button" in jsdom would measure
 * nothing and pass for the wrong reason. So the geometry assertions read the
 * built stylesheet, which is where a rule that is missing or overridden
 * actually shows up.
 *
 * The bug this exists for
 * ──────────────────────
 * `.gis-tool` had a fixed `width: 52px`. The longest label, "Seleccionar",
 * needs about 48px at 0.5rem and "Anotación" about 40px, and the label was
 * clipped with an ellipsis. A toolbar whose labels are cut off is one the
 * operator cannot read at a glance, and one they hesitate to press.
 */

import { describe, it, expect, beforeAll } from 'vitest'
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import { TOOL_META } from '@/map/draw'

const here = dirname(fileURLToPath(import.meta.url))
const distAssets = join(here, '..', 'dist', 'assets')

let shellCss = ''

beforeAll(() => {
  if (!existsSync(distAssets)) {
    throw new Error(
      'No hay CSS construido. Ejecutá `npm run build` antes de esta suite: ' +
        'comprobar la salida es justamente el punto de estas pruebas.',
    )
  }
  const file = readdirSync(distAssets).find((f) => /^GisShell-.*\.css$/.test(f))
  shellCss = readFileSync(join(distAssets, file), 'utf8')
})

/** Body of a rule. Scoped styles compile to `.x[data-v-hash]`. */
function ruleFor(css, className) {
  const re = new RegExp(`(?<![a-z0-9_-])\\.${className}(?![a-z0-9_-])[^{}]*\\{([^}]*)\\}`, 'i')
  const m = css.match(re)
  return m ? m[1] : null
}

const px = (body, prop) => {
  const m = body.match(new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([\\d.]+)px`))
  return m ? Number(m[1]) : null
}

describe('the tool buttons', () => {
  it('are not a fixed width, because the labels differ in length', () => {
    const body = ruleFor(shellCss, 'gis-tool')
    expect(body, 'falta .gis-tool').toBeTruthy()
    expect(body).not.toMatch(/(?:^|;)\s*width\s*:\s*\d+px/)
    // A minimum keeps the short labels ("Medir", "Punto") clickable.
    const min = px(body, 'min-width')
    expect(min, 'sin min-width los botones cortos son diminutos').toBeTruthy()
    expect(min).toBeGreaterThanOrEqual(40)
  })

  it('are tall enough to press comfortably', () => {
    const body = ruleFor(shellCss, 'gis-tool')
    const h = px(body, 'height')
    expect(h, 'sin altura fija').toBeTruthy()
    expect(h).toBeGreaterThanOrEqual(36)
  })

  it('do not truncate the label', () => {
    // The label must not be clipped, because the button is now sized to fit.
    const label = ruleFor(shellCss, 'gis-tool-label')
    expect(label, 'falta .gis-tool-label').toBeTruthy()
    expect(label).not.toMatch(/text-overflow\s*:\s*ellipsis/)
    expect(label).not.toMatch(/overflow\s*:\s*hidden/)
    expect(label).toMatch(/white-space\s*:\s*nowrap/)
  })

  it('show a readable label size', () => {
    const label = ruleFor(shellCss, 'gis-tool-label')
    const rem = label.match(/font-size\s*:\s*([\d.]+)rem/)
    expect(rem, 'sin font-size en rem').toBeTruthy()
    // 0.5rem is about 8px: technically legible, but at the limit. Anything
    // below that is a caption, not a control label.
    expect(Number(rem[1])).toBeGreaterThanOrEqual(0.5)
  })

  it('do not select their own text when clicked', () => {
    // Clicking the same tool twice used to select the label, and the
    // selection highlight made a working button look broken.
    for (const selector of ['gis-toolbar', 'gis-toolstrip', 'gis-tool']) {
      const body = ruleFor(shellCss, selector)
      expect(body, `falta .${selector}`).toBeTruthy()
      expect(body, `.${selector} permite seleccionar texto`).toMatch(
        /user-select\s*:\s*none/,
      )
    }
  })

  it('take a tap immediately rather than after the 300ms delay', () => {
    // The strip is a scroll container, so the browser would otherwise treat a
    // slightly-off click as a scroll gesture and the tool would not fire.
    const strip = ruleFor(shellCss, 'gis-toolstrip')
    expect(strip).toMatch(/touch-action\s*:\s*manipulation/)
    const tool = ruleFor(shellCss, 'gis-tool')
    expect(tool).toMatch(/touch-action\s*:\s*manipulation/)
  })

  it('show a press feedback while the button is held', () => {
    // `:active` is its own rule, not a declaration inside `.gis-tool`, so it
    // has to be matched against the selector rather than the body. The
    // scope hash sits between the class and the pseudo-class, as in
    // `.gis-tool[data-v-abc]:active`, so no character may sit between them.
    const press = shellCss.match(/\.gis-tool(?:\[[^\]]*\])?:active[^{}]*\{([^}]*)\}/)
    expect(press, 'sin :active, no hay sensacion de pulsar').toBeTruthy()
    expect(press[1]).toMatch(/background/)
  })

  it('keep the active tool visible', () => {
    const active = shellCss.match(/\.gis-tool\.active[^{}]*\{([^}]*)\}/)
    expect(active, 'sin estado activo').toBeTruthy()
    expect(active[1]).toMatch(/background/)
    // Not just a colour change: the state has to be obvious.
    expect(active[1]).toMatch(/border-color/)
  })
})

describe('the toolbar container', () => {
  it('still lets the tool strip scroll when the window is narrow', () => {
    // Ten labelled tools do not fit on a laptop. Scrolling is the answer, and
    // it is why touch-action matters above.
    const strip = ruleFor(shellCss, 'gis-toolstrip')
    expect(strip).toMatch(/overflow-x\s*:\s*auto/)
  })

  it('stays short enough to leave the map room', () => {
    const bar = ruleFor(shellCss, 'gis-toolbar')
    const h = px(bar, 'height')
    expect(h).toBeLessThanOrEqual(52)
  })
})

describe('every tool has a label worth reading', () => {
  it('no label is long enough to need truncating at this size', () => {
    // At 0.5rem an average glyph is roughly 4.4px wide. A label wider than
    // the strip can offer is a label that will be clipped on some screen.
    for (const [id, meta] of Object.entries(TOOL_META)) {
      expect(meta.label, `${id} sin etiqueta`).toBeTruthy()
      const estimated = meta.label.length * 4.4
      expect(
        estimated,
        `"${meta.label}" necesita ${Math.round(estimated)}px: es demasiado larga para la barra`,
      ).toBeLessThan(90)
    }
  })

  it('every tool carries a hint, so the title is useful', () => {
    for (const [id, meta] of Object.entries(TOOL_META)) {
      expect(meta.hint, `${id} sin explicación`).toBeTruthy()
    }
  })
})
