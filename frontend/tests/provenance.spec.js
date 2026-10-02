/**
 * tests/provenance.spec.js
 * ========================
 * Que «de dónde salió esta dirección de aeronave» se lea en español.
 *
 * Por qué este archivo existe
 * ---------------------------
 * El panel de vuelos muestra, en cada resultado de búsqueda, una fila de
 * procedencia: si la aeronave se identificó con los vectores en vivo de OpenSky,
 * con la dirección que escribió el operador, o con el archivo de vuelos de la
 * propia instalación. Esa fila se mostraba con la clave tal cual
 * (`callsign_live_state`, luego `callsign_archivo_aerorf`), y eso no es
 * información para quien opera: es el nombre interno de un campo.
 *
 * La fila importa más de lo que parece. Que una dirección venga de lo que la
 * aeronave está transmitiendo ahora o de un registro guardado hace meses son dos
 * clases de evidencia distintas, y confundirlas es exactamente el error que este
 * proyecto no quiere cometer. Traducir la etiqueta no es pulido: es parte de que
 * la procedencia signifique algo.
 *
 * Y hay un contrato entre dos languages que nadie lee: si el backend emite una
 * procedencia nueva y el panel no la conoce, el texto se queda en blanco. Un
 * blanco en la fila de procedencia es peor que un texto raro, porque no parece
 * un error: parece que no hay procedencia. Estas pruebas atan las dos puntas.
 */

import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const frontend = join(here, '..')
const PANEL = join(frontend, 'src', 'components', 'gis', 'FlightPanel.vue')

const pythonFiles = (dir) =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = join(dir, e.name)
    if (e.isDirectory()) return pythonFiles(full)
    return e.name.endsWith('.py') ? [full] : []
  })

const panel = readFileSync(PANEL, 'utf8')

/** Claves de procedencia que el backend le asigna a `resolved_via`. */
function procedenciasDelBackend() {
  const fuente = pythonFiles(join(frontend, '..', 'app'))
    .map((f) => readFileSync(f, 'utf8'))
    .join('\n')
  const encontradas = new Set()
  for (const m of fuente.matchAll(/resolved_via"?\]?\s*=\s*"([a-z0-9_]+)"/g)) {
    encontradas.add(m[1])
  }
  return [...encontradas].sort()
}

/** Claves que el panel tiene traducidas. */
function procedenciasDelPanel() {
  const bloque = panel.match(/ORIGEN_DE_LA_IDENTIFICACION\s*=\s*\{([^}]*)\}/)
  expect(bloque, 'FlightPanel.vue debe seguir declarando ORIGEN_DE_LA_IDENTIFICACION').toBeTruthy()
  return [...bloque[1].matchAll(/([a-z0-9_]+)\s*:/g)].map((m) => m[1]).sort()
}

describe('la procedencia de una búsqueda se lee en español', () => {
  it('el backend emite al menos una procedencia', () => {
    // Si el extractor se rompe, esta prueba falla antes que las demás y avisa de
    // que el problema es la lectura, no el contrato. Una lista vacía haría que
    // «todo está traducido» pasara sin comprobar nada.
    expect(procedenciasDelBackend().length).toBeGreaterThan(0)
  })

  it('toda procedencia que el backend emite está traducida en el panel', () => {
    // El contrato de las dos puntas. Una procedencia nueva que no se tradujera
    // aparecería cruda en pantalla, y una crude es un nombre interno.
    const sinTraducir = procedenciasDelBackend().filter(
      (p) => !procedenciasDelPanel().includes(p),
    )
    expect(
      sinTraducir,
      `procedencias sin traducir en FlightPanel.vue: ${sinTraducir.join(', ')}`,
    ).toEqual([])
  })

  it('el panel no traduce ninguna procedencia que el backend no emita', () => {
    // Al revés: una entrada de sobra es texto muerto, y peor, es una etiqueta
    // que alguien va a leer creyendo que el backend la produce.
    const deMas = procedenciasDelPanel().filter(
      (p) => !procedenciasDelBackend().includes(p),
    )
    expect(deMas, `procedencias que el backend nunca emite: ${deMas.join(', ')}`).toEqual([])
  })

  it('ninguna traducción está en inglés', () => {
    // La traducción que no traduce. Se comprueba sobre las etiquetas, que es
    // donde se escapa el fallo: un mapa `callsign_live_state: 'callsign
    // live state'` pasa cualquier prueba que sólo mire las claves.
    //
    // «OpenSky» y «AeroRF» quedan fuera de la lista a propósito: son nombres
    // propios, y traducirlos sería inventar. La primera versión de esta prueba
    // los prohibía y falló contra «vectores en vivo de OpenSky», que es
    // justamente la etiqueta correcta. Una guarda demasiado dura enseña a
    // desactivarla.
    const bloque = panel.match(/ORIGEN_DE_LA_IDENTIFICACION\s*=\s*\{([^}]*)\}/)[1]
    const etiquetas = [...bloque.matchAll(/:\s*'([^']*)'/g)].map((m) => m[1])
    expect(etiquetas.length).toBe(procedenciasDelPanel().length)
    for (const etiqueta of etiquetas) {
      for (const palabra of ['live', 'state', 'direct', 'resolved', 'matched', 'found', 'archive']) {
        expect(
          etiqueta.toLowerCase(),
          `«${etiqueta}» sigue en inglés: contiene «${palabra}»`,
        ).not.toContain(palabra)
      }
    }
  })

  it('una procedencia desconocida no deja la fila en blanco', () => {
    // El peor resultado posible no es una etiqueta rara: es una celda vacía en
    // la fila de procedencia, porque no parece un error y parece que no hay
    // procedencia. El panel tiene que mostrar la clave desconocida.
    expect(panel).toMatch(/origen desconocido \(\$\{[^}]+\}\)/)
  })

  it('sin procedencia se dice que no hubo coincidencia', () => {
    expect(panel).toMatch(/if \(!origen\) return 'sin coincidencia'/)
  })

  it('la plantilla usa la traducción y no la clave', () => {
    // Lo importante no es que el mapa de traducciones exista, es que la
    // plantilla lo use. La primera versión de esta prueba sólo comprobaba el
    // mapa, y revertir la plantilla a la clave cruda pasaba en verde: el mapa
    // seguía completo, sin dejar de ser inútil.
    expect(panel).toMatch(/\{\{\s*comoSeIdentifico\(\s*flightsStore\.searchResult\.resolved_via\s*\)\s*\}\}/)
    expect(
      panel,
      'la fila de procedencia se está llenando con la clave del backend',
    ).not.toMatch(/\{\{\s*flightsStore\.searchResult\.resolved_via\s*(\|\||\?)/)
  })

  it('la fila dice qué está mostrando', () => {
    // «Resuelto por» describía una operación interna; lo que el operador quiere
    // saber es de dónde salió el dato.
    expect(panel).toContain('Identificado por')
    expect(panel).not.toContain('Resuelto por')
  })
})