import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import L from 'leaflet'
import { MapEngine } from '@/map/MapEngine'

/**
 * Selecting an object, all the way through.
 *
 * The circle became a group to carry its centre dot, and a group has no
 * `setStyle` of its own. `select()` in the store calls `clearHighlight()`
 * *before* recording the id, so the style call raised on a grouped layer and
 * the id was never stored — the object was clicked and nothing was selected.
 *
 * The same hole was in the tooltip and in the popup, both of which bind to a
 * layer and both of which do nothing useful on a group.
 *
 * These tests go through the sequence the store performs, in order, because
 * that ordering is the bug: it is not that highlighting a group is wrong, it is
 * that it throws before the id is written.
 */
let container
let engine

const CENTRE = [-34.6, -58.4]

beforeEach(() => {
  container = document.createElement('div')
  container.id = 'map-sel'
  document.body.appendChild(container)
  engine = new MapEngine({ container: 'map-sel' })
  engine.init()
  engine.setView(CENTRE[0], CENTRE[1], 12)
})

afterEach(() => {
  engine?.destroy()
  container?.remove()
})

const CIRCLE = {
  id: 6, type: 'circle', name: 'Cobertura', geometry_type: 'Point',
  latlng: CENTRE, radius: 10, radius_unit: 'nm',
  metrics: { radius_m: 18520, radius_nm: 10, radius_km: 18.52 },
  color: '#3b82f6', weight: 3, opacity: 1, fill_opacity: 0.15,
  visible: true, layer: 'circles', show_label: true, properties: {},
}

const RADIAL = {
  id: 9, type: 'radial', name: 'Radial', geometry_type: 'Point',
  latlng: CENTRE, azimuth: 45, length_value: 10, length_unit: 'nm',
  color: '#a855f7', weight: 3, opacity: 1,
  visible: true, layer: 'radials', show_label: true, properties: {},
}

const POINT = {
  id: 1, type: 'point', name: 'Antena', geometry_type: 'Point',
  latlng: CENTRE, color: '#38bdf8', weight: 3, opacity: 1,
  visible: true, layer: 'user', show_label: true, properties: {},
}

/** What the store does on a click, in the order it does it. */
function selectThrough(object) {
  const layer = engine.renderObject(object)
  const chosen = []
  engine.onObjectClick(object.id, (id) => {
    // The order in `select()`: clear the highlight of everything, then
    // highlight this one, and only then is the id recorded by the store.
    engine.clearHighlight()
    engine.highlight(id)
    chosen.push(id)
  })

  const shape = engine.vectorLayersFor(layer)[0] || layer
  shape.fire('click', { latlng: L.latLng(object.latlng) }, true)
  return { layer, chosen }
}

describe('highlighting does not throw, whatever the layer is', () => {
  it('a circle survives clearHighlight and highlight', () => {
    const { chosen } = selectThrough(CIRCLE)
    expect(chosen, 'el clic no llego a registrar la seleccion').toEqual([CIRCLE.id])
  })

  it('a radial survives it', () => {
    const { chosen } = selectThrough(RADIAL)
    expect(chosen).toEqual([RADIAL.id])
  })

  it('a plain point survives it', () => {
    const { chosen } = selectThrough(POINT)
    expect(chosen).toEqual([POINT.id])
  })

  it('highlighting a group reaches its children', () => {
    // The point of the exercise: a group has no setStyle, so the descent has
    // to happen rather than being skipped.
    const layer = engine.renderObject(CIRCLE)
    const children = engine.vectorLayersFor(layer)
    expect(children.length, 'no se低压n los hijos del grupo').toBeGreaterThan(0)
    // Would throw on a group.
    expect(() => engine.highlight(CIRCLE.id)).not.toThrow()
    expect(() => engine.clearHighlight()).not.toThrow()
  })

  it('the highlighted layer really changes weight, and comes back', () => {
    const layer = engine.renderObject(CIRCLE)
    const children = engine.vectorLayersFor(layer)
    const before = children[0].options.weight

    engine.highlight(CIRCLE.id)
    expect(children[0].options.weight, 'el resaltado no se aplico')
      .toBeGreaterThan(before)

    engine.clearHighlight()
    expect(children[0].options.weight, 'no se restauro el grosor')
      .toBeCloseTo(before, 5)
  })

  it('selecting the same object twice does not thicken it', () => {
    // `setStyle` writes through to `options`, so restoring from `options`
    // restores the *highlighted* weight and the object grows by three points
    // on every click. Only visible after a few selections, and impossible to
    // attribute to a cause once it has happened.
    const layer = engine.renderObject(CIRCLE)
    const ring = layer.getLayers().find((l) => l.getRadius?.() > 100)
    const start = ring.options.weight

    for (let i = 0; i < 5; i += 1) {
      engine.highlight(CIRCLE.id)
      engine.clearHighlight()
    }
    expect(ring.options.weight, 'el grosor se acumula con cada seleccion')
      .toBeCloseTo(start, 5)
  })

  it('selecting a different object restores the first', () => {
    const a = engine.renderObject(CIRCLE)
    const b = engine.renderObject({ ...RADIAL, id: 10 })
    const ringA = a.getLayers().find((l) => l.getRadius?.() > 100)
    const lineB = engine.vectorLayersFor(b).find((l) => typeof l.getLatLngs === 'function')
    const startA = ringA.options.weight
    const startB = lineB.options.weight

    engine.highlight(CIRCLE.id)
    engine.highlight(10)

    expect(ringA.options.weight, 'el anterior quedo resaltado').toBeCloseTo(startA, 5)
    expect(lineB.options.weight, 'el nuevo no se resalto').toBeGreaterThan(startB)
  })

  it('the centre dot is not restyled into a ring', () => {
    // The dot shares the group but not the shape's role. It is left alone, so
    // highlighting does not turn a 4-pixel dot into a blob.
    const layer = engine.renderObject(CIRCLE)
    const dot = layer.getLayers().find((l) => l.getRadius?.() < 100)
    const ring = layer.getLayers().find((l) => l.getRadius?.() > 100)

    engine.highlight(CIRCLE.id)
    expect(dot.options.weight).not.toBe(ring.options.weight)
  })
})

describe('the name and the details of a grouped shape', () => {
  it('the tooltip is bound to something that can show it', () => {
    const layer = engine.renderObject(CIRCLE)
    // A group has no tooltip of its own, so binding to the group silently did
    // nothing and the name never appeared.
    const bound = engine
      .vectorLayersFor(layer)
      .filter((c) => typeof c.getTooltip === 'function' && c.getTooltip())
    expect(bound.length, 'el nombre del circulo no se muestra').toBeGreaterThan(0)
  })

  it('a popup can be bound to a child of the group', () => {
    // What the store does. A group accepts `bindPopup` without complaint and
    // shows nothing, so the binding has to reach the children.
    const layer = engine.renderObject(CIRCLE)
    const targets = engine.vectorLayersFor(layer)
    expect(targets.length).toBeGreaterThan(0)
    targets.forEach((c) => c.bindPopup('<p>detalle</p>'))
    expect(targets.some((c) => c.getPopup())).toBe(true)
  })
})
