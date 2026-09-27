/**
 * tests/theme.spec.js
 * ──────────────────
 * One palette across every section.
 *
 * Why this is a test and not a preference
 * ───────────────────────────────────────
 * Two of the five views were still on `gray-*` and the old custom `primary`
 * while everything else had moved to `slate-*` and `sky-*`. An operator moving
 * between the map and an expediente saw a different application. Nothing in
 * the build, the linter or any other test noticed, because every one of those
 * classes is valid Tailwind — they are just the wrong ones.
 *
 * The sharp edge was `border-primary`: the old config defined the colour but
 * generated no border utility for it, so those borders were invisible. A class
 * that resolves to nothing is the worst kind: it is not an error, it is just
 * an absence.
 *
 * So the check is over the source: no view or component may reintroduce a
 * retired token, and every `gray-*`/`primary` must be gone.
 */

import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const src = join(here, '..', 'src')

/** Every .vue under src/, so a new view is covered without editing this file. */
function vueFiles(dir = src, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) vueFiles(full, out)
    else if (entry.endsWith('.vue')) out.push(full)
  }
  return out
}

const files = vueFiles()

/** Tokens that no longer belong. */
const RETIRED = [
  /\bgray-\d{2,3}\b/,
  /\b(?:text|bg|border|ring|from|to|via|fill|stroke|decoration|divide|outline|shadow|accent|caret)-primary\b/,
  /\bfile:bg-primary\b/,
  /\bhover:(?:bg|text|border)-primary\b/,
]

describe('one palette everywhere', () => {
  it('found the source files to check', () => {
    // If this fails the glob silently matched nothing and every assertion
    // below would pass for the wrong reason.
    expect(files.length).toBeGreaterThan(10)
  })

  it('no component uses a retired token', () => {
    const offenders = []
    for (const file of files) {
      const text = readFileSync(file, 'utf8')
      for (const pattern of RETIRED) {
        const m = text.match(pattern)
        if (m) {
          const line = text.slice(0, m.index).split('\n').length
          offenders.push(`${file.split(/[\\/]/).pop()}:${line} ${m[0]}`)
        }
      }
    }
    expect(
      offenders,
      `clases del tema viejo, mezcladas con slate/sky:\n  ${offenders.join('\n  ')}`,
    ).toEqual([])
  })

  it('actually uses the current palette', () => {
    // The mirror of the check above: a file that had every token replaced by
    // deletion would pass. The theme has to be present, not merely absent.
    let slate = 0
    let sky = 0
    for (const file of files) {
      const text = readFileSync(file, 'utf8')
      slate += (text.match(/(?:text|bg|border)-slate-\d+/g) || []).length
      sky += (text.match(/(?:text|bg|border)-sky-\d+/g) || []).length
    }
    expect(slate, 'nada usa la paleta slate').toBeGreaterThan(20)
    expect(sky, 'nada usa el acento sky').toBeGreaterThan(2)
  })
})

describe('the built CSS generates what the templates ask for', () => {
  let css = ''

  // Resolved lazily inside the test: the CSS only exists after a build.
  const load = () => {
    if (css) return css
    const dist = join(here, '..', 'dist', 'assets')
    if (!existsSync(dist)) {
      throw new Error('Ejecutá `npm run build` antes de esta suite.')
    }
    for (const f of readdirSync(dist)) {
      if (f.endsWith('.css')) css += readFileSync(join(dist, f), 'utf8')
    }
    return css
  }

  it('has a rule for every class the templates reference', () => {
    // The `border-primary` failure in general form. A class that is never
    // generated is not an error at build time: it is simply an absence, and
    // the element renders with no border and no warning.
    const built = load()
    // Utility names as they appear in class attributes: plain, no variant.
    const USED = [
      'border-slate-700', 'border-slate-800', 'bg-slate-900', 'bg-slate-950',
      'text-slate-300', 'text-slate-400', 'text-slate-500', 'text-slate-600',
      'text-sky-400', 'bg-sky-700', 'text-amber-300', 'text-emerald-400',
      'border-rose-700', 'bg-amber-950', 'text-rose-300',
    ]
    const missing = USED.filter((c) => !built.includes(`.${c}`))
    expect(missing, `clases usadas pero no generadas: ${missing.join(', ')}`).toEqual([])
  })
})
