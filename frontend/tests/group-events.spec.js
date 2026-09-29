import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import L from 'leaflet'
import { MapEngine } from '@/map/MapEngine'

/**
 * Does a group forward the events of its children?
 *
 * This is the whole question behind the selection bug, and it was assumed
 * rather than checked. A `FeatureGroup` is documented to propagate, the
 * circles were changed to one, and the objects were still unselectable. So the
 * behaviour is observed here, in this version, rather than trusted.
 *
 * Built through the MapEngine rather than a bare `L.map`, because a plain map
 * on a bare div in jsdom has no renderer and every vector layer throws on add.
 * That is a test-environment problem, and the engine already solves it.
 */
let container
let engine

beforeEach(() => {
  container = document.createElement('div')
  container.id = 'prop-test'
  document.body.appendChild(container)
  engine = new MapEngine({ container: 'prop-test' })
  engine.init()
  engine.setView(-34.6, -58.4, 11)
})

afterEach(() => {
  engine?.destroy()
  container?.remove()
})

/**
 * What a click on `child` reaches, listening on `group`.
 *
 * The `true` matters and is not decoration. Leaflet propagates an event up the
 * layer tree only when `fire` is called with `propagate` set — which is what
 * its own map click handler does when it dispatches to the layer under the
 * pointer. A bare `fire` stays on the layer it was called on and never reaches
 * the group, so a test written that way would report that no group propagates
 * anything, which is not what happens on screen.
 */
function clicksThatReach(group, child) {
  const seen = []
  group.on('click', (e) => seen.push(e))
  child.fire('click', { latlng: L.latLng(-34.6, -58.4) }, true)
  return seen
}

describe('event propagation through a group', () => {
  it('a FeatureGroup forwards a click from its child', () => {
    const group = L.featureGroup([L.circle([-34.6, -58.4], { radius: 5000 })])
    group.addTo(engine.map)
    const seen = clicksThatReach(group, group.getLayers()[0])

    expect(seen.length, 'un FeatureGroup deberia reenviar el clic').toBe(1)
  })

  it('a LayerGroup does not forward it', () => {
    // The original bug in miniature. A plain LayerGroup keeps its children's
    // events to itself, so a shape inside one is invisible to anything
    // listening on the group — and the store listens on the group.
    const group = L.layerGroup([L.circle([-34.6, -58.4], { radius: 5000 })])
    group.addTo(engine.map)
    const seen = clicksThatReach(group, group.getLayers()[0])

    expect(seen.length, 'un LayerGroup no reenvia, y ese fue el fallo').toBe(0)
  })

  it('a non-interactive child does not swallow the ring behind it', () => {
    // The centre dot is deliberately non-interactive so it cannot become a
    // 4-pixel target that eats clicks. The ring behind it must still answer.
    const group = L.featureGroup([
      L.circleMarker([-34.6, -58.4], { radius: 4, interactive: false }),
      L.circle([-34.6, -58.4], { radius: 5000 }),
    ])
    group.addTo(engine.map)
    const [dot, ring] = group.getLayers()

    const seen = clicksThatReach(group, ring)
    expect(seen.length, 'el punto central esta tapando el anillo').toBe(1)
    expect(dot.options.interactive).toBe(false)
  })
})
