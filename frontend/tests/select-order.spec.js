import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import L from 'leaflet'
import { MapEngine } from '@/map/MapEngine'

/**
 * Does the selection survive the click?
 *
 * The operator clicks an object and nothing is selected. Not a circle, not a
 * point, not a radial — and the earlier claim that a missing `setStyle` threw
 * before the id was recorded does not hold: the old code guarded every call
 * with `if (layer.setStyle)`, so nothing raised.
 *
 * So the id is recorded and then something takes it away. The only candidate
 * is the map's own click handler, which with the select tool clears the
 * selection on any click. Whether the map sees a click that landed on an
 * object is the question, and it is answerable rather than arguable.
 *
 * The renderer matters here: this map is `preferCanvas`, so every vector object
 * is painted on one shared canvas element and there is no per-object DOM node
 * for a click to be stopped at. Whatever `stopPropagation` means there, it
 * cannot be doing what it would do with one SVG path per object.
 */
let container
let engine

const CENTRE = [-34.6, -58.4]

beforeEach(() => {
  container = document.createElement('div')
  container.id = 'map-order'
  document.body.appendChild(container)
  engine = new MapEngine({ container: 'map-order' })
  engine.init()
  engine.setView(CENTRE[0], CENTRE[1], 12)
})

afterEach(() => {
  engine?.destroy()
  container?.remove()
})

const OBJECTS = {
  circle: {
    id: 6, type: 'circle', name: 'Círculo', geometry_type: 'Point',
    latlng: CENTRE, radius: 10, radius_unit: 'nm',
    metrics: { radius_m: 18520 }, color: '#3b82f6', weight: 3, opacity: 1,
    fill_opacity: 0.15, visible: true, layer: 'circles', show_label: true,
    properties: {},
  },
  point: {
    id: 1, type: 'point', name: 'Punto', geometry_type: 'Point',
    latlng: CENTRE, color: '#38bdf8', weight: 3, opacity: 1,
    visible: true, layer: 'user', show_label: true, properties: {},
  },
  radial: {
    id: 9, type: 'radial', name: 'Radial', geometry_type: 'Point',
    latlng: CENTRE, azimuth: 45, length_value: 10, length_unit: 'nm',
    color: '#a855f7', weight: 3, opacity: 1, visible: true,
    layer: 'radials', show_label: true, properties: {},
  },
}

describe('what the operator actually does: click an object', () => {
  it.each(['circle', 'point', 'radial'])(
    'a %s click reaches the map as well as the object',
    (kind) => {
      const object = OBJECTS[kind]
      // Both listeners, wired the way the app wires them: the object handler
      // from the store, the map handler from the shell.
      const objectClicks = []
      const mapClicks = []
      const layer = engine.renderObject(object)
      engine.onObjectClick(object.id, (id) => objectClicks.push(id))
      engine.on('click', (p) => mapClicks.push(p))

      // A real pointer click on the shape. With a canvas renderer, Leaflet
      // hit-tests the canvas, fires on the layer, and the same event continues
      // to the map — one DOM event, two handlers. So only the layer is fired
      // here; firing the map as well would double-count and would not describe
      // anything the browser does.
      const target = engine.vectorLayersFor(layer)[0] || layer
      target.fire('click', { latlng: L.latLng(CENTRE) }, true)

      expect(objectClicks, 'el objeto no recibio el clic').toEqual([object.id])
      // The map does see the click — a canvas renderer gives it nowhere to be
      // stopped — and that is correct now, because the click carries the id of
      // the object it landed on. The shell uses exactly that to tell "clicked
      // an object" from "clicked empty ground", and only the second clears the
      // selection. Asserting the id is what makes this a real guard: a test
      // that merely counted clicks would pass with the id missing.
      expect(mapClicks.length, 'el mapa no vio el clic del objeto').toBe(1)
      expect(
        String(mapClicks[0].overObject),
        'el clic al mapa no dice sobre que objeto fue',
      ).toBe(String(object.id))
    },
  )

  it('a click on empty ground carries no object id', () => {
    // The other half of the distinction the shell makes. A click on nothing
    // clears the selection; a click on an object selects it. Both reach the
    // map, and only the id tells them apart.
    const mapClicks = []
    engine.on('click', (p) => mapClicks.push(p))
    engine.map.fire('click', { latlng: L.latLng(CENTRE) })

    expect(mapClicks.length).toBe(1)
    // Absent rather than null: the map's own handler builds the payload
    // without the key. The shell's guard is `overObject == null`, which covers
    // both, and the check below is what pins that the two cases really are
    // distinguishable.
    expect(mapClicks[0].overObject, 'un clic en el vacio no debe traer id')
      .toBeFalsy()
  })

  it('a canvas renderer gives stopPropagation nowhere to stop the event', () => {
    // Why the object click reaches the map at all. The map is configured with
    // `preferCanvas`, so every vector object is painted on one shared canvas
    // element: there is no per-object DOM node for a click to be stopped at,
    // and `stopPropagation` has nothing to act on.
    //
    // This is the assumption the previous two fixes were built on, and it is
    // the one that made "nothing selects" hard to explain. Recorded here so it
    // is a fact about the app rather than a belief about Leaflet.
    expect(engine.map.options.preferCanvas, 'el mapa ya no dibuja en canvas')
      .toBe(true)

    // The canvas is created lazily, when the first vector layer is added, so
    // this is asserted with an object on the map. The point is the count: one
    // canvas serves every vector object, which is why there is no per-object
    // DOM node for a click to be stopped at.
    engine.renderObject(OBJECTS.point)
    const canvases = engine.map.getPanes().overlayPane.querySelectorAll('canvas')
    expect(canvases.length, 'deberia haber al menos un canvas de vectores')
      .toBeGreaterThan(0)
  })
})
