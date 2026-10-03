/**
 * tests/track-above.spec.js
 * =========================
 * Que el avión se vea por encima de cualquier cosa, sin repetir el corte total
 * de clics que causó una capa dibujada por delante del mapa.
 *
 * El pedido
 * ---------
 * El operador, después de reportar que una trayectoria no se veía: «el avión debe
 * verse por encima de cualquier cosa». Es la primera vez que el orden de dibujo se
 * fija por una frase del operador y no por una preferencia nuestra, así que la
 * prueba tiene que comprobar exactamente eso y nada más.
 *
 * Por qué no bastaba con `CATEGORY_DRAW_RANK`
 * -------------------------------------------
 * El mapa usa `preferCanvas`: **un** canvas y **una** lista de dibujo, ordenada
 * por `_leaflet_id`, que se asigna cuando la capa se *crea*. Medido: los ids del
 * grupo eran idénticos antes y después de un `restack()`, porque quitar y volver a
 * añadir una capa no la renumera. O sea que el rango decide en qué orden se
 * re-agregan los grupos, y **no puede** mover una trayectoria por encima de una
 * forma creada después.
 *
 * Y eso era justo lo que pasaba: `aircraft_tracks` se crea al montar el shell,
 * mucho antes de que el operador dibuje nada, así que quedaba en el fondo.
 *
 * Un pane sí funciona, porque cada renderer es un elemento del DOM y el navegador
 * los apila por z-index. De ahí `aerorfTracksPane` con su propio canvas.
 *
 * El precio, y por qué el pane es `pointer-events: none`
 * ------------------------------------------------------
 * Una capa vectorial fuera del overlayPane obtiene su propio canvas de tamaño
 * completo, y Leaflet pone `pointer-events: auto` en cada canvas. Ese canvas
 * tapaba el mapa por delante y se comía todos los clics: con la capa presente,
 * `elementFromPoint` devolvía el canvas; sin ella, el del overlayPane. Nada era
 * seleccionable y **arreglar los manejadores no podía servir de nada**, porque
 * ningún clic llegaba a ninguno.
 *
 * Sobre los `expect`, y por qué aquí sólo se comparan cosas planas
 * ---------------------------------------------------------------
 * La primera versión de esta prueba hacía, dentro de un `eachLayer`, un
 * `expect(c._renderer).toBe(engine.trackRenderer)`. Fallaba en la segunda capa —
 * los puntos y los extremos seguían en el canvas compartido, que era el defecto
 * real — y el runner **se quedó colgado para siempre**, sin ningún mensaje. El
 * formateador del diff con dos renderers de Leaflet adentro no termina, y como
 * la ejecución es síncrona ni siquiera corre `testTimeout`: un test que cuelga
 * es peor que un test que falla, porque no dice nada.
 *
 * De ahí la regla que sigue esta prueba: se recogen hechos planos (números,
 * strings, booleanos) y se espera sobre *ellos*, con el resumen en el mensaje.
 * Si falla, se ve qué capa y por qué; si no, no cuelga.
 *
 * Estas pruebas cubren las dos mitades, porque una sin la otra es un defecto:
 * el orden sin la guarda de clics, y la guarda sin el orden.
 */

import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it, beforeAll } from 'vitest'
import L from 'leaflet'
import { MapEngine } from '@/map/MapEngine'
import { AircraftRenderer } from '@/map/aircraft'

const here = dirname(fileURLToPath(import.meta.url))
const raiz = join(here, '..')
const distAssets = join(raiz, 'dist', 'assets')

let engine
let renderer

/** Una pista de dos puntos, como la que devuelve el backend. */
const PISTA = {
  icao24: 'e02659',
  points: [
    { latitude: -34.6, longitude: -58.4, provenance: 'historical' },
    { latitude: -34.7, longitude: -58.3, provenance: 'historical' },
  ],
}

beforeAll(() => {
  document.body.innerHTML = '<div id="mapa" style="width:800px;height:600px"></div>'
  engine = new MapEngine({ container: 'mapa' })
  engine.init()
  renderer = new AircraftRenderer(engine, {})
})

/**
 * Lo que `drawTrack` puso en el mapa, como datos planos.
 *
 * Nada de Leaflet sale de aquí: sólo strings y booleanos, para que un fallo se
 * pueda imprimir entero sin tocar el formateador de objetos (leer el encabezado).
 *
 * @param {L.LayerGroup} capa el grupo que devuelve `drawTrack`
 */
function inventario(capa) {
  const filas = []
  capa.eachLayer((c) => {
    const esPath = c instanceof L.Path
    const esMarcador = c instanceof L.Marker
    filas.push({
      clase: esMarcador ? 'marcador' : esPath ? 'path' : 'otro',
      pane: (c.options && c.options.pane) || '(por defecto)',
      enElPaneDePistas: c._renderer === engine.trackRenderer,
      rendererAsignado: !!c._renderer,
    })
  })
  return filas
}

describe('la trayectoria tiene su propio pane', () => {
  it('el motor crea el pane y su renderer', () => {
    expect(engine.trackRenderer, 'falta el renderer de las trayectorias').toBeTruthy()
    expect(engine.trackPaneName).toBe('aerorfTracksPane')
  })

  it('el pane queda por encima de los objetos y por debajo del avión', () => {
    // Por encima del overlayPane (400) para tapar las formas rellenas, y por
    // debajo del markerPane (600) para que el icono esté sobre su propia línea.
    // Al revés el avión desaparecería detrás de su propia trayectoria, que es el
    // mismo síntoma con otra causa.
    expect(Number(engine.trackPane.style.zIndex)).toBeGreaterThan(400)
    expect(Number(engine.trackPane.style.zIndex)).toBeLessThan(600)
  })

  it('todas las formas de la trayectoria se dibujan en ese renderer', () => {
    renderer.drawTrack(PISTA)
    const capa = [...renderer.trackGroup.getLayers()][0]
    expect(capa, 'drawTrack no devolvió ninguna capa').toBeTruthy()

    const filas = inventario(capa)
    expect(filas.length, 'la prueba no dibujó nada').toBeGreaterThan(0)

    // Dos puntos => una polilínea, dos puntos de waypoint y los dos extremos.
    // Medido: eran cinco hijos y **sólo la polilínea** estaba en el renderer
    // nuevo; los otros cuatro se quedaban debajo de cada forma rellena. Ese era
    // el defecto, y este es el número que lo cubre.
    const paths = filas.filter((f) => f.clase === 'path')
    expect(paths.length, 'sin polilínea ni puntos: ' + JSON.stringify(filas)).toBe(3)

    const fuera = paths.filter((f) => !f.enElPaneDePistas)
    expect(
      fuera.length,
      'forms dibujadas en el canvas compartido, o sea debajo de los objetos: ' +
        JSON.stringify(fuera),
    ).toBe(0)
  })

  it('los extremos son marcadores, no paths, y viven en el markerPane', () => {
    const filas = inventario([...renderer.trackGroup.getLayers()][0])
    const marcadores = filas.filter((f) => f.clase === 'marcador')

    // No es un detalle de implementación: un path en el pane de las pistas no
    // recibe puntero (el pane es `pointer-events: none`) y los tooltips
    // «Inicio»/«Fin» se abren con el hover. O son marcadores o la etiqueta deja
    // de funcionar sin que nadie se entere.
    expect(
      marcadores.length,
      'los extremos dejaron de ser marcadores: ' + JSON.stringify(filas),
    ).toBe(2)
    expect(
      marcadores.every((f) => f.pane === 'markerPane'),
      'un extremo fuera del markerPane: ' + JSON.stringify(marcadores),
    ).toBe(true)

    // El markerPane (600) está sobre el pane de las pistas (500): el punto final
    // se ve por encima de la línea que acaba de dibujar.
    const zMarcador = Number(
      engine.map.getPane('markerPane').style.zIndex || 600,
    )
    expect(zMarcador).toBeGreaterThan(Number(engine.trackPane.style.zIndex))
  })

  it('ningún objeto del operador comparte el renderer de las trayectorias', () => {
    // Si un objeto acabara en el pane de las pistas dejaría de estar debajo de
    // ellas, que es al revés de lo pedido. Se comprueba con un círculo, que es
    // el que tiene relleno y por tanto el que tapa.
    const antes = engine.trackRenderer
    const circulo = engine.renderObject({
      id: 99,
      type: 'coverage',
      geometry_type: 'Polygon',
      latlng: { lat: -34.6, lng: -58.4 },
      radius: 5000,
      layer: 'circles',
    })
    expect(circulo, 'el círculo no se dibujó').toBeTruthy()

    let rendererDeLosPaths = []
    const revisar = (c) => {
      if (c instanceof L.Path) rendererDeLosPaths.push(c._renderer === antes)
    }
    if (circulo.eachLayer) circulo.eachLayer(revisar)
    else revisar(circulo)

    expect(rendererDeLosPaths.length, 'el círculo no puso ningún path').toBeGreaterThan(0)
    expect(
      rendererDeLosPaths.filter((mismo) => mismo).length,
      'un objeto dibujado en el pane de las trayectorias',
    ).toBe(0)
  })
})

describe('el pane de las trayectorias no puede comerse los clics', () => {
  it('la hoja de estilos lo declara transparente al puntero', () => {
    const dist = existsSync(distAssets)
      ? readdirSync(distAssets)
          .filter((f) => f.endsWith('.css'))
          .map((f) => readFileSync(join(distAssets, f), 'utf8'))
          .join('\n')
      : ''
    const fuente = readFileSync(join(raiz, 'src', 'assets', 'styles.css'), 'utf8')
    const css = dist || fuente
    expect(
      /\.aerorf-tracks-pane\s*\{[^}]*pointer-events:\s*none/i.test(css),
      'el pane se dibuja por encima del mapa y sin esta regla se come los clics',
    ).toBe(true)
  })

  it('la regla alcanza también al canvas, no sólo al pane', () => {
    // `pointer-events: none` se hereda, pero un `auto` explícito en el hijo lo
    // pisa. Leaflet no lo pone hoy; decirlo explícitamente es lo que evita que
    // un cambio suyo lo haga sin que nadie se entere.
    const fuente = readFileSync(join(raiz, 'src', 'assets', 'styles.css'), 'utf8')
    expect(/\.aerorf-tracks-pane\s+canvas\s*\{[^}]*pointer-events:\s*none/i.test(fuente)).toBe(
      true,
    )
  })

  it('el pane no usa markerPane, que fue el origen del corte total de clics', () => {
    expect(engine.trackPaneName).not.toBe('markerPane')
  })

  it('los extremos se estilan con una regla global, que es lo que el divIcon necesita', () => {
    // El contenido de un `divIcon` se monta como cadena HTML y nunca recibe el
    // atributo `data-v-…` de un estilo acotado: con una regla scoped el punto
    // saldría como un recuadro de 10×10 sin redondear y nadie lo notaría.
    const fuente = readFileSync(join(raiz, 'src', 'assets', 'styles.css'), 'utf8')
    expect(
      /\.aerorf-trazo-punto\s*\{[^}]*border-radius:\s*50%/i.test(fuente),
      'falta la regla global que hace redondo el punto de inicio/fin',
    ).toBe(true)
    expect(
      /\.aerorf-trazo-inicio\s*\{[^}]*var\(--trazo-medido\)/i.test(fuente),
      'el punto de inicio no usa el token de lo medido por nosotros',
    ).toBe(true)
    expect(
      /\.aerorf-trazo-fin\s*\{[^}]*var\(--trazo-fin\)/i.test(fuente),
      'el punto final no usa el token de fin de trayectoria',
    ).toBe(true)
  })
})

describe('el rango por sí solo no alcanza, y la prueba lo dice', () => {
  it('reordenar grupos no renumera las capas, así que el rango no las mueve', () => {
    // La medición que justifica el pane. Si en algún momento Leaflet empieza a
    // renumerar al re-añadir, el pane seguirá funcionando y el rango también:
    // por eso esta prueba es una observación del comportamiento actual, no un
    // requisito. Si falla, hay que releer el comentario de `_addTrackPane` antes
    // de tocar nada.
    const antes = engine.categoryLayers.get('circles')?._leaflet_id
    engine.restack()
    const despues = engine.categoryLayers.get('circles')?._leaflet_id
    expect(antes, 'el id cambió al re-agregar: el comentario de _addTrackPane está viejo').toBe(
      despues,
    )
  })
})
