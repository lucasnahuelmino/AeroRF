import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * The labels a radial is read against.
 *
 * Leaflet tooltips are drawn by the map, outside the Vue tree, and the class
 * that styles them lives in a `scoped` block. A scoped selector compiles to
 * `.aerorf-draft-label[data-v-hash]`, which is why the assertion allows an
 * attribute between the class and anything after it — and why the label
 * styling has to be read from the built CSS rather than trusted.
 *
 * These are static checks on purpose. jsdom does not lay anything out, so a
 * computed-style assertion here would pass against a rule that was never
 * applied.
 */
const SRC = resolve(__dirname, '../src/views/GisShell.vue')

describe('the reference label is styled, and styled apart from the value', () => {
  it('the draft label class exists in the stylesheet', () => {
    const css = readFileSync(SRC, 'utf8')
    expect(css).toMatch(/\.aerorf-draft-label\s*\{/)
  })

  it('the muted variant exists, for the reference and not the measurement', () => {
    // The reference line says "000°, north". The arc and the end label say the
    // value. Rendering both at the same weight would make the value hard to
    // find, which is the one thing the reference is for.
    const css = readFileSync(SRC, 'utf8')
    expect(css).toMatch(/\.aerorf-draft-label--muted\s*\{/)
  })

  it('the tooltip arrow is suppressed on the permanent labels', () => {
    // The label is attached to an invisible guide, so an arrow would point at
    // nothing.
    const css = readFileSync(SRC, 'utf8')
    expect(css).toMatch(/\.aerorf-draft-label::before\s*\{[^}]*display:\s*none/)
  })

  it('the muted variant is applied to the north reference, not to the value', () => {
    // The two must not be swapped: a dim angle arc and a bright reference line
    // would read as the opposite of what they are.
    const draw = readFileSync(resolve(__dirname, '../src/map/draw.js'), 'utf8')
    const reference = draw.slice(draw.indexOf('_renderRadialReference'))
    const arc = reference.slice(0, reference.indexOf('this.engine.setDraft'))

    expect(arc).toMatch(/Referencia 000/)
    expect(arc).toMatch(/aerorf-draft-label--muted/)
    // The arc's own label carries the degrees and is not muted.
    expect(arc).toMatch(/`\$\{this\.draft\.azimuth\.toFixed\(1\)\}°`/)
  })
})
