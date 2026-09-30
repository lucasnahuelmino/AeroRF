import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { MapEngine } from '@/map/MapEngine'

/**
 * What receives a click, on a map drawn with `preferCanvas`.
 *
 * The operator clicked an object and nothing was ever selected. Not a point,
 * not a circle, not a radial — and three previous attempts each found one
 * plausible cause and fixed it, while 306 frontend tests stayed green.
 *
 * The reason those tests could not see it: they call `layer.fire('click', …)`,
 * which hands the event straight to the layer and skips everything the browser
 * does first. The bug lived in the steps *before* the event — where the layers
 * were painted, and in which order — and `fire()` starts after all of them.
 *
 * So these tests do not simulate a click. They assert the three properties the
 * browser was measured to have, each of which is a precondition for any click
 * arriving at all. The measurements they come from are recorded next to each
 * one; they were taken in a real browser, on the real app, and each is the
 * reason a revert of the corresponding fix fails here.
 */
let container
let engine

const CENTRE = [-34.6, -58.4]

beforeEach(() => {
  container = document.createElement('div')
  container.id = 'map-hit'
  document.body.appendChild(container)
  engine = new MapEngine({ container: 'map-hit' })
  engine.init()
  engine.setView(CENTRE[0], CENTRE[1], 12)
})

afterEach(() => {
  engine?.destroy()
  container?.remove()
})

function makeObject(id, type, layer, extra = {}) {
  return {
    id,
    type,
    name: `${type} ${id}`,
    geometry_type: 'Point',
    latlng: [CENTRE[0] + id * 0.0005, CENTRE[1] + id * 0.0005],
    color: '#38bdf8',
    weight: 3,
    opacity: 1,
    fill_opacity: 0.15,
    visible: true,
    layer,
    show_label: true,
    properties: {},
    ...extra,
  }
}

const CIRCLE = makeObject(1, 'circle', 'circles', { radius: 10, radius_unit: 'nm', metrics: { radius_m: 18520 } })
const RADIAL = makeObject(2, 'radial', 'radials', { azimuth: 45, length_value: 10, length_unit: 'nm' })
const POINT = makeObject(3, 'point', 'reference_points')

/**
 * The canvas draw order, bottom to top, as object ids.
 *
 * Measured in the browser, on the running app: with `preferCanvas` every vector
 * object shares one canvas and one draw list, `_drawFirst` is the *bottom* of
 * it, and following `next` walks towards the top. 83 entries — 67 airports,
 * the measured shapes, then the reference points last.
 *
 * The direction is the part that cannot be read off Leaflet's source, because
 * the same property name points the other way in the version's own docs. It was
 * settled by clicking a point inside a circle, seeing the point win, and finding
 * the point at the end of this chain.
 */
function drawOrder() {
  const owner = new Map()
  engine.featureLayers.forEach((group, id) => {
    for (const child of engine.vectorLayersFor(group)) owner.set(child, id)
  })
  const renderer = engine.vectorLayersFor(engine.featureLayers.get('1'))[0]._renderer
  const out = []
  let node = renderer._drawFirst
  while (node && out.length < 200) {
    if (node.layer && owner.has(node.layer)) out.push(owner.get(node.layer))
    node = node.next
  }
  return out
}

describe('a vector layer must not be given a pane of its own', () => {
  it.each([
    ['circle', CIRCLE],
    ['radial', RADIAL],
    ['point', POINT],
  ])('a %s and its centre dot stay in the shared overlay pane', (_label, object) => {
    const layer = engine.renderObject(object)
    const children = engine.vectorLayersFor(layer)
    expect(children.length, 'el objeto debe tener al menos una capa vectorial').toBeGreaterThan(0)

    for (const child of children) {
      // A circle and a radial are drawn as a group — the ring or line plus the
      // centre dot — so the dot is checked here too, and it is the dot that
      // caused the outage.
      //
      // Measured in the browser: with `pane: 'markerPane'` on that dot, the
      // markerPane got its own full-size canvas. Leaflet gives every canvas
      // `pointer-events: auto`, and the markerPane sits above the overlayPane
      // (z-index 600 against 400), so that canvas covered the whole map in
      // front of everything and swallowed every click — including the ones
      // meant for the ground. `document.elementFromPoint` over a circle
      // returned the markerPane canvas; with it hidden, the overlayPane canvas.
      //
      // Nothing was selectable, and no change to any click handler could have
      // fixed it, because no click was reaching a single handler.
      expect(
        child.options.pane ?? 'overlayPane',
        `la capa de un ${object.type} no debe vivir en un panel propio`,
      ).toBe('overlayPane')
    }
  })

  it('a non-interactive centre dot is still a vector layer that would block', () => {
    // `interactive: false` is not the safeguard, and that is worth pinning: the
    // dot was non-interactive from the start and it still covered the map. With
    // a shared canvas, the element that receives the pointer is the canvas, not
    // the shape, so a shape's own `interactive` flag says nothing about whether
    // it stands in the way.
    const layer = engine.renderObject(CIRCLE)
    const dot = engine.vectorLayersFor(layer).find((c) => c.options.interactive === false)
    expect(dot, 'el punto central debe existir y no ser interactivo').toBeTruthy()
    expect(dot.options.pane ?? 'overlayPane').toBe('overlayPane')
  })
})

describe('selecting an object must not reorder the shared canvas', () => {
  it('highlighting a circle leaves the draw order untouched', () => {
    engine.renderObject(CIRCLE)
    engine.renderObject(RADIAL)
    engine.renderObject(POINT)
    const before = drawOrder()
    expect(before, 'los tres objetos deben estar en la lista de dibujo')
      .toEqual(expect.arrayContaining(['1', '2', '3']))

    engine.highlight(1)

    // Measured in the browser: `highlight()` used to call `bringToFront()` on
    // the selected object's layers. With one shared canvas that is a *global*
    // reorder, not a per-object one, and it sticks.
    //
    // A circle's hit area is its whole disc, not its ring — Leaflet's
    // `CircleMarker._containsPoint` is `distance <= radius` — and the canvas
    // fires the click on the topmost layer whose disc contains the point. So
    // after selecting the 16 km circle once, it answered every click inside it
    // for the rest of the session, and the objects inside became unselectable
    // until the page was reloaded.
    //
    // The draw order is the thing that decides who receives a click, so it must
    // not change as a side effect of selecting. Asserted on the whole list, not
    // on the selected object alone: a reorder that put the circle back in its
    // old place would pass a weaker check and still leave the operator unable
    // to reach whatever it covers.
    expect(drawOrder(), 'seleccionar no debe reordenar el lienzo compartido')
      .toEqual(before)
  })

  it('the highlight is still visible without touching the order', () => {
    const layer = engine.renderObject(CIRCLE)
    const ring = engine.vectorLayersFor(layer)[0]
    const baseWeight = ring.options.weight
    engine.highlight(1)
    expect(ring.options.weight, 'el objeto resaltado debe distinguirse del resto')
      .toBeGreaterThan(baseWeight)
  })
})

describe('a broad target must not outrank a precise one', () => {
  /**
   * The objects are rendered in the order the app renders them, which is the
   * order the layer list comes back in: `radials` before `circles`, both
   * alphabetically among the measured shapes. Rendering the circle first would
   * make the test pass on its own and prove nothing.
   */
  function renderInApiOrder() {
    engine.renderObject(RADIAL)
    engine.renderObject(CIRCLE)
    engine.renderObject(POINT)
  }

  it('restack puts circles below radials and below the points', () => {
    renderInApiOrder()
    engine.restack()

    const order = drawOrder()
    const at = (id) => order.indexOf(id)
    // Bottom to top: the circle's disc, then the radial's line, then the point.
    // Measured in the browser at 0.27.3: with the categories in the order the
    // API returned them, the circles were drawn above the radials, and a click
    // on a radial where it crossed a circle returned the circle. The operator
    // clicked the line they could see and got the area they had not aimed at.
    expect(at('1'), 'el disco del circulo debe quedar debajo').toBeLessThan(at('2'))
    expect(at('2'), 'la linea del radial debe quedar encima del circulo')
      .toBeGreaterThan(at('1'))
    expect(at('3'), 'un punto debe quedar por encima de las formas medidas')
      .toBeGreaterThan(at('1'))
  })

  it('re-showing a layer does not leave it stuck on top', () => {
    renderInApiOrder()
    engine.restack()
    const before = drawOrder()

    // Leaflet has no "insert at position": a group that is removed and added
    // back becomes the most recently added, which is the front of the shared
    // canvas. Before the restack, toggling a layer off and on promoted it
    // above everything, and for a circle that locked out every object it
    // covers until the page was reloaded.
    engine.setCategoryVisible('circles', false)
    engine.setCategoryVisible('circles', true)

    expect(drawOrder(), 'ocultar y volver a mostrar no debe alterar el orden')
      .toEqual(before)
  })
})
