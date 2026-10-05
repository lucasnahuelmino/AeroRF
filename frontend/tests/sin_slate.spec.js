/**
 * tests/sin_slate.spec.js
 * ───────────────────────
 * Ningún template vuelve a la escala `slate-N`.
 *
 * El puente de 0.30.0 reescribía unas treinta utilidades para que
 * `bg-slate-900` resolviera a `--panel` — con el costo escrito en su
 * propio comentario: «the class names now lie». Esta guarda es la otra
 * mitad del ítem «migrar las plantillas»: **cero** utilidades `slate-N`
 * en el fuente, porque todas pasaron a nombres semánticos
 * (`bg-panel`, `text-texto-medio`, `border-borde`…) y el puente se borró.
 *
 * Escanea `src/**` (vue, js y css): si una clase nueva reaparece, la
 * prueba falla con archivo y línea, y si alguien resucita el puente en
 * `styles.css` también.
 */

import { it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const src = join(here, '..', 'src')

/** Todo el código que el navegador llega a leer: plantillas, lógica y CSS. */
function archivos(dir = src, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) archivos(full, out)
    else if (/\.(vue|js|css)$/.test(entry)) out.push(full)
  }
  return out
}

it('la escala slate no vuelve a aparecer en ninguna plantilla', () => {
  const files = archivos()
  // Si el glob no encuentra nada, las aserciones de abajo pasarían en
  // vacío: que esté lleno es lo que hace que valga algo.
  expect(files.length, 'no hay archivos que escanear').toBeGreaterThan(10)

  const offenders = []
  for (const file of files) {
    const lineas = readFileSync(file, 'utf8').split('\n')
    lineas.forEach((linea, i) => {
      const m = linea.match(/slate-\d+/)
      if (m) {
        offenders.push(`${file.slice(src.length + 1)}:${i + 1} ${m[0]}`)
      }
    })
  }

  expect(
    offenders,
    `utilidades slate-N en el fuente (eran grises de Tailwind o mentiras del puente ` +
      `resueltas a otro color; ahora van por tokens):\n  ${offenders.join('\n  ')}`,
  ).toEqual([])
})
