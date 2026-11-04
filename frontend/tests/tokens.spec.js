/**
 * tests/tokens.spec.js
 * ────────────────────
 * The design tokens, and the bridge that puts the templates onto them.
 *
 * What this file exists for
 * ────────────────────────
 * The tokens were written, the build was green, and nothing changed on screen.
 *
 * `@import` is only valid before any other rule, and the import for
 * `assets/tokens.css` sat after the three `@tailwind` directives, so it was
 * silently dropped. Every `var(--ink)` in the application then resolved to
 * nothing: `getComputedStyle` returned empty strings, `body` fell back to
 * transparent over black, and the compatibility layer pointed at tokens that did
 * not exist. The build never complained, because nothing in it is wrong — the
 * stylesheet it produced was a valid stylesheet.
 *
 * Nothing in the source says a token is missing. The browser has to be asked, or
 * the output has to be read. That is what this file does, and that is why it
 * reads the **built** CSS rather than the source: the source can contain a token
 * that never arrives.
 */
import { describe, it, expect, beforeAll } from 'vitest'
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const frontend = join(here, '..')

/**
 * Every built stylesheet, concatenated.
 *
 * Not "the first one that ends in `.css`". The build emits two — the entry chunk
 * and the route chunk for the map — and the tokens live in the entry one. Reading
 * whichever came first alphabetically found the other file and reported that not
 * one token existed, which is the opposite of true.
 *
 * Concatenating is also the honest model: the browser loads all of them.
 */
function builtCss() {
  const dir = join(frontend, 'dist', 'assets')
  if (!existsSync(dir)) return null
  const files = readdirSync(dir).filter((f) => f.endsWith('.css'))
  if (!files.length) return null
  return files.map((f) => readFileSync(join(dir, f), 'utf8')).join('\n')
}

/**
 * A colour as `r,g,b,a`, so two ways of writing one colour compare equal.
 *
 * The minifier rewrites `rgba(11, 23, 66, 0.12)` as `rgba(11,23,66,.12)`, so
 * comparing the text of a token against the value written in this file would fail
 * on spelling rather than on colour.
 */
function comoRGBA(valor) {
  const v = valor.replace(/\s+/g, '').toLowerCase()
  const hex = v.match(/^#([0-9a-f]{6})$/i)
  if (hex) {
    const n = parseInt(hex[1], 16)
    return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},1`
  }
  const rgb = v.match(/^rgba?\(([^)]+)\)$/)
  if (rgb) {
    const [r, g, b, a = '1'] = rgb[1].split(',')
    const alpha = a.startsWith('.') ? `0${a}` : a
    return `${+r},${+g},${+b},${+alpha}`
  }
  return v
}

/**
 * The rule for one selector, or null.
 *
 * The bundle is minified, so a selector is written `.bg-slate-900{...}` with no
 * space. Matching the selector and then reading to the matching brace is enough:
 * these are flat rules, none of them nested.
 */
function ruleFor(css, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const m = css.match(new RegExp(`${escaped}\\s*\\{[^}]*\\}`))
  return m ? m[0] : null
}

/**
 * The tokens of the family, copied from `rni-app-4.0`.
 *
 * The values are asserted, not just the names. A token whose name is right and
 * whose value drifted is worse than a missing one: it looks deliberate.
 */
const TOKENS_FAMILIA = {
  '--ink': '#0b1742',
  '--ink-soft': '#3d4670',
  '--paper': '#f4f6fa',
  '--surface': '#ffffff',
  '--line': 'rgba(11, 23, 66, 0.12)',
  '--signal': '#1a4fbf',
  '--signal-deep': '#0e2e73',
  '--signal-on-ink': '#6e96ff',
  '--risk-ok': '#26794d',
  '--risk-mid': '#9c6208',
  '--risk-high': '#b23a3a',
  '--sin-dato': '#9aa5ab',
}

/** The ones AeroRF adds, because a map is a dark surface with layers on it. */
const TOKENS_AERORF = [
  '--fondo', '--panel', '--panel-alto', '--panel-hondo',
  '--texto', '--texto-medio', '--texto-tenue', '--texto-invisible',
  '--borde', '--borde-fuerte',
  '--trazo', '--trazo-medido', '--trazo-observado', '--aviso', '--seleccion',
  // El velo y su versión suave: los fondos de diálogo translúcidos que la
  // migración de plantillas (0.30.28) sacó de las opacidades sueltas.
  '--velo', '--velo-suave',
]

let css
beforeAll(() => {
  css = builtCss()
})

describe('the tokens have to reach the browser', () => {
  it('the built stylesheet exists, or this file cannot say anything', () => {
    // Silently passing because the bundle is missing would make every assertion
    // below vacuous, which is how a guard stops guarding.
    if (!existsSync(join(frontend, 'dist', 'assets'))) {
      throw new Error('falta dist/assets: hay que correr el build antes de las pruebas de layout')
    }
    expect(css, 'no se encontro ningun CSS construido').toBeTruthy()
    expect(css.length, 'el CSS construido esta sospechosamente vacio').toBeGreaterThan(5000)
  })

  it.each(Object.entries(TOKENS_FAMILIA))('%s conserva el valor de la familia', (nombre, valor) => {
    const declarado = css.match(new RegExp(`${nombre.replace(/[-]/g, '\\-')}\\s*:\\s*([^;}]+)`))
    expect(declarado, `${nombre} no esta en el CSS construido`).toBeTruthy()
    expect(comoRGBA(declarado[1]), `${nombre} cambio de valor`).toBe(comoRGBA(valor))
  })

  it.each(TOKENS_AERORF)('%s llega al bundle', (nombre) => {
    expect(css, `${nombre} no esta en el CSS construido`).toMatch(
      new RegExp(`${nombre.replace(/[-]/g, '\\-')}\\s*:`),
    )
  })

  it('--ink is exactly the ENACOM mark blue, which is why it is the family blue', () => {
    // Measured off `src/assets/logoenacom.png`: RGB(11, 23, 66) = #0b1742. The
    // whole institutional palette is derived from it, so this is the one value
    // that must not drift: it is what makes the logo on the bar part of the
    // design rather than a sticker on top of it.
    expect(TOKENS_FAMILIA['--ink']).toBe('#0b1742')
    expect(css).toMatch(/--ink\s*:\s*#0b1742/i)
  })

  it('imports the tokens before the @tailwind directives, because @import has to be first', () => {
    // The exact defect this file was written for. The import for `tokens.css` sat
    // after the three `@tailwind` directives, which is invalid: an `@import` that
    // follows any other statement is dropped, and PostCSS passes it through.
    //
    // What is asserted is the real rule, not "the tokens import is line 1": this
    // file also imports the web fonts, and two `@import`s in a row are perfectly
    // valid. What is not valid is anything else coming first.
    const source = readFileSync(join(frontend, 'src', 'assets', 'styles.css'), 'utf8')
    const lineOf = (re) => source.split('\n').findIndex((l) => re.test(l))
    const tokens = lineOf(/@import\s+'\.\/tokens\.css'/)
    const primerTailwind = lineOf(/^\s*@tailwind/)

    expect(tokens, 'no hay @import de tokens.css').toBeGreaterThan(-1)
    expect(primerTailwind, 'no hay directivas @tailwind').toBeGreaterThan(-1)
    expect(
      tokens,
      'el import de los tokens tiene que ir antes de @tailwind, o se descarta en silencio',
    ).toBeLessThan(primerTailwind)
  })
})

describe('las utilidades semánticas ponen a las plantillas sobre la paleta', () => {
  /**
   * Cada utilidad semántica que una plantilla usa tiene que resolver a un token.
   *
   * Es la continuación del guardia del puente (0.30.0), que existía para que
   * un `bg-slate-700` nuevo no cayera en el gris de Tailwind sin que nadie lo
   * notara. Con las plantillas migradas el peligro es el mismo con otro nombre:
   * una utilidad sin regla propia es una ausencia, no un error — el elemento
   * se pinta con lo que Tailwind tenga a mano.
   */
  const UTILIDADES = [
    'bg-panel', 'bg-panel-alto', 'bg-panel-hondo', 'bg-on-ink-wash',
    'bg-velo', 'bg-velo-suave',
    'text-texto', 'text-texto-medio', 'text-texto-tenue', 'text-texto-invisible',
    'text-ink',
    'border-borde', 'border-borde-fuerte',
  ]

  it.each(UTILIDADES)('%s resuelve a un token, no a un valor escrito a mano', (utilidad) => {
    const regla = ruleFor(css, `.${utilidad}`)
    expect(regla, `${utilidad} no tiene regla propia: no se pinta como la familia`).toBeTruthy()
    expect(regla, `${utilidad} deberia apuntar a un token`).toMatch(/var\(--/)
  })

  it('el puente slate no sobrevivió: ni una regla con esa escala', () => {
    // Antes había dos reglas por clase (la de Tailwind y la del puente) y
    // ganaba la del final por posición en el archivo. Ahora cada utilidad
    // semántica nace una sola vez, desde el color del config, y la escala
    // que mentía no queda ni en el CSS construido.
    expect(css, 'el puente sigue en el bundle').not.toMatch(/slate-\d/)
  })

  it('el anillo de foco no amarra al token ilegible (2.52:1 sobre --ink)', () => {
    // Medido en el proyecto hermano: `--signal` sobre `--ink` da 2.52:1,
    // por debajo de los 3:1 que pide WCAG para un elemento gráfico;
    // `--signal-on-ink` da 6.15:1. El puente cubría el anillo por eso.
    // Con el puente borrado esa regla muerta ya no existe (los focos reales
    // de las plantillas son `focus:ring-blue-500`), así que lo que queda por
    // garantizar es la contra: ningún ring del bundle puede quedar amarrado
    // al token que no se lee.
    expect(
      css,
      'un ring quedó amarrado a --signal: no se lee sobre --ink',
    ).not.toMatch(/--tw-ring-color:\s*var\(--signal\)/)
  })

  it('there is exactly one token block, so no name can be defined twice', () => {
    // `--surface` meant `#0f1724`, a dark panel, in the old block here, and
    // `#ffffff`, a light surface, in the family. Both were `:root` in this one
    // stylesheet and the later one won, which would have made every text token
    // over the dark backgrounds resolve to dark-on-dark.
    const declaraciones = css.match(/--(surface|fondo|panel|texto)\s*:/g) || []
    const unicos = new Set(declaraciones)
    expect(
      declaraciones.length,
      `--surface y compañía están declarados ${declaraciones.length} veces; el juego nuevo no puede redefinir un nombre que ya existía con otro significado`,
    ).toBe(unicos.size)
  })
})