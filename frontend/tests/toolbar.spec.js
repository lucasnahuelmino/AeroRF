/**
 * tests/toolbar.spec.js
 * ────────────────────
 * The contextual Workspace controls, checked against the built CSS.
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
 * The compact toolbar was replaced by a single contextual Workspace. Its
 * category, task, and tool rows need a reliable hit area and readable labels.
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

describe('the Workspace task controls', () => {
  it('gives category and tool rows a full-width, comfortable hit area', () => {
    for (const selector of ['gis-workspace-category', 'gis-workspace-task', 'gis-workspace-tool']) {
      const body = ruleFor(shellCss, selector)
      expect(body, `falta .${selector}`).toBeTruthy()
      expect(body).toMatch(/width\s*:\s*100%/)
      expect(px(body, 'min-height')).toBeGreaterThanOrEqual(44)
    }
  })

  it('keeps task labels readable in the available panel width', () => {
    const label = ruleFor(shellCss, 'gis-workspace-category strong')
    const description = ruleFor(shellCss, 'gis-workspace-category small')
    expect(label).toMatch(/font-size\s*:\s*\.8125rem/)
    expect(description).toMatch(/font-size\s*:\s*\.6875rem/)
    expect(description).toMatch(/line-height\s*:\s*1\.4/)
  })

  it('does not clip category labels or descriptions', () => {
    const label = ruleFor(shellCss, 'gis-workspace-category strong')
    const description = ruleFor(shellCss, 'gis-workspace-category small')
    for (const body of [label, description]) {
      expect(body).not.toMatch(/text-overflow\s*:\s*ellipsis/)
      expect(body).not.toMatch(/overflow\s*:\s*hidden/)
      expect(body).not.toMatch(/white-space\s*:\s*nowrap/)
    }
  })

  it('keeps button presses from selecting text and accepts taps immediately', () => {
    for (const selector of ['gis-workspace-category', 'gis-workspace-task', 'gis-workspace-tool']) {
      const body = ruleFor(shellCss, selector)
      expect(body).toMatch(/user-select\s*:\s*none/)
      expect(body).toMatch(/touch-action\s*:\s*manipulation/)
    }
  })

  it('shows the active tool with a filled surface and signal border', () => {
    const active = shellCss.match(/\.gis-workspace-tool\.active[^{}]*\{([^}]*)\}/)
    expect(active, 'sin estado activo').toBeTruthy()
    expect(active[1]).toMatch(/background/)
    expect(active[1]).toMatch(/border-color/)
  })

  it('provides tactile press feedback for category and task rows', () => {
    const active = shellCss.match(
      /\.gis-workspace-category(?:\[[^\]]+\])?:active,\s*\.gis-workspace-task(?:\[[^\]]+\])?:active,\s*\.gis-workspace-tool(?:\[[^\]]+\])?:active\{([^}]*)\}/,
    )
    expect(active, 'falta feedback activo en las filas').toBeTruthy()
    expect(active[1]).toMatch(/background/)
  })

  it('keeps the category and task lists vertically scrollable', () => {
    expect(ruleFor(shellCss, 'gis-workspace-home')).toMatch(/overflow-y\s*:\s*auto/)
    expect(ruleFor(shellCss, 'gis-workspace-submenu')).toMatch(/overflow-y\s*:\s*auto/)
  })

  it('does not ship the removed horizontal tool strip or tab bar', () => {
    expect(shellCss).not.toContain('.gis-toolstrip')
    expect(shellCss).not.toContain('.gis-tab')
  })
})

describe('the map toolbar container', () => {
  it('stays short enough to leave the map room', () => {
    const bar = ruleFor(shellCss, 'gis-toolbar')
    const h = px(bar, 'height')
    expect(h).toBeLessThanOrEqual(52)
  })
})

describe('every tool has a label worth reading', () => {
  it('keeps labels concise enough for a contextual tool row', () => {
    // Concise labels leave room for a useful hint within the panel width.
    for (const [id, meta] of Object.entries(TOOL_META)) {
      expect(meta.label, `${id} sin etiqueta`).toBeTruthy()
      const estimated = meta.label.length * 4.4
      expect(
        estimated,
        `"${meta.label}" necesita ${Math.round(estimated)}px: es demasiado larga para la fila`,
      ).toBeLessThan(120)
    }
  })

  it('every tool carries an explanation for its Workspace row', () => {
    for (const [id, meta] of Object.entries(TOOL_META)) {
      expect(meta.hint, `${id} sin explicación`).toBeTruthy()
    }
  })
})
