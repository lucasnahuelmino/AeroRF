import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import L from 'leaflet'
import { MapEngine } from '@/map/MapEngine'
import { ToolManager, TOOLS } from '@/map/draw'

/**
 * Placing one object at the centre of another.
 *
 * The operator draws a 10 NM circle, picks the radial tool, and clicks the
 * middle of the circle to start a radial from there. Two things went wrong.
 *
 * The click never reached the tool: the object's own click handler calls
 * `stopPropagation`, so the map's click event was never emitted and the tool
 * stayed silent. The circle got selected instead, with no visible reason — the
 * tool was plainly armed.
 *
 * And even once the click arrives, a hand is not a coordinate. The radial
 * would be stored a few metres off the circle's centre, which is invisible on
 * screen and wrong in the data.
 */
let container
let engine
let tools

const CENTRE = [-34.6, -58.4]

beforeEach(() => {
  container = document.createElement('div')
  container.id = 'map-centre'
  document.body.appendChild(container)
  engine = new MapEngine({ container: 'map-centre' })
  engine.init()
  engine.suppressClicks(false)
  engine.setView(CENTRE[0], CENTRE[1], 12)
  tools = new ToolManager(engine, {})
})

afterEach(() => {
  tools?.deactivate()
  engine?.destroy()
  container?.remove()
})

/** A stored 10 NM circle, as the engine draws it. */
function addCircle(id = 6, radiusNm = 10) {
  return engine.renderObject({
    id,
    type: 'circle',
    name: 'Círculo',
    geometry_type: 'Point',
    latlng: CENTRE,
    radius: radiusNm,
    radius_unit: 'nm',
    metrics: { radius_m: radiusNm * 1852 },
    color: '#3b82f6',
    weight: 3,
    opacity: 1,
    fill_opacity: 0.15,
    visible: true,
    layer: 'circles',
    show_label: false,
    properties: {},
  })
}

/** Move a latlng by roughly `metres`, roughly east. */
function eastOf(base, metres) {
  const dLat = 0
  const dLon = (metres / (111320 * Math.cos((base[0] * Math.PI) / 180)))
  return { lat: base[0] + dLat, lng: base[1] + dLon }
}

describe('a click on an object reaches the armed tool', () => {
  it('the tool receives a click that landed on a circle', () => {
    // The regression. With `stopPropagation` and nothing else, this event was
    // never emitted, so the tool never saw the click and the operator got a
    // selection instead of a shape.
    const seen = []
    engine.on('click', (p) => seen.push(p))
    // The handler has to be registered: the engine only binds a layer's click
    // when an object is made selectable, which is what the shell does on load.
    // Without this the test would pass for the wrong reason once bound.
    engine.onObjectClick(6, () => {})
    const circle = addCircle()
    engine.onObjectClick(6, () => {})
    engine.suppressClicks(true)

    // What Leaflet does when the pointer is over the object: it fires the
    // layer's own click, and the map's own click never happens.
    circle.fire('click', { latlng: L.latLng(CENTRE) })

    expect(seen.length, 'el clic sobre el objeto no llego a la herramienta').toBe(1)
    // The id as the caller supplied it, so a caller can act on it directly
    // rather than having to know how the engine keys its layers.
    expect(String(seen[0].overObject), 'no se sabe sobre que objeto se hizo clic')
      .toBe('6')
  })

  it('the position is the one the operator pointed at', () => {
    const seen = []
    engine.on('click', (p) => seen.push(p))
    engine.onObjectClick(6, () => {})
    const circle = addCircle()
    engine.onObjectClick(6, () => {})
    engine.suppressClicks(true)
    const target = eastOf(CENTRE, 900)

    circle.fire('click', { latlng: L.latLng(target) })

    expect(seen.length, 'no llego ningun clic').toBe(1)
    expect(seen[0].latlng.lat).toBeCloseTo(target.lat, 5)
    expect(seen[0].latlng.lng).toBeCloseTo(target.lng, 5)
  })

  it('the select tool still does not get it, because selecting is the point', () => {
    // With the select tool, a click on an object selects it. Forwarding the
    // position too would fight that: the map's handler clears the selection
    // on any click.
    const seen = []
    engine.on('click', (p) => seen.push(p))
    engine.onObjectClick(6, () => {})
    const circle = addCircle()
    engine.onObjectClick(6, () => {})
    engine.suppressClicks(false)

    circle.fire('click', { latlng: L.latLng(CENTRE) })

    expect(seen.length, 'con la herramienta seleccionar no debe llegar al mapa').toBe(0)
  })
})

describe('a placement snaps onto the centre of a measured shape', () => {
  it('a radial placed near the centre is stored at the centre', () => {
    const done = []
    tools.handlers.onComplete = (p) => done.push(p)
    addCircle(6, 10)

    tools.activate(TOOLS.RADIAL, { unit: 'km', length: 20, azimuth: 45 })
    // A click a few hundred metres east of the centre: close enough to mean
    // "the centre", far enough that a hand tremor explains it.
    engine.map.fire('click', { latlng: eastOf(CENTRE, 300) })

    // A radial takes two clicks: the origin, then the bearing. The origin is
    // the one under test.
    expect(tools.draft.origin, 'el primer clic no coloco el origen').toBeTruthy()
    expect(tools.draft.origin[0], 'el origen no quedo en el centro del circulo')
      .toBeCloseTo(CENTRE[0], 6)
    expect(tools.draft.origin[1]).toBeCloseTo(CENTRE[1], 6)

    engine.map.fire('click', { latlng: eastOf(CENTRE, 20_000) })
    expect(done).toHaveLength(1)
    expect(done[0].type).toBe('radial')
    expect(done[0].latitude).toBeCloseTo(CENTRE[0], 6)
    expect(done[0].longitude).toBeCloseTo(CENTRE[1], 6)
  })

  it('a point placed near the centre is stored at the centre', () => {
    const done = []
    tools.handlers.onComplete = (p) => done.push(p)
    addCircle(6, 10)

    tools.activate(TOOLS.POINT, {})
    engine.map.fire('click', { latlng: eastOf(CENTRE, 200) })

    expect(done[0].type).toBe('point')
    expect(done[0].latitude).toBeCloseTo(CENTRE[0], 6)
    expect(done[0].longitude).toBeCloseTo(CENTRE[1], 6)
  })

  it('a click well away from any centre is left alone', () => {
    // Snapping that reaches too far is worse than none: a point meant in open
    // ground would jump to a circle the operator did not click on.
    const done = []
    tools.handlers.onComplete = (p) => done.push(p)
    addCircle(6, 10)

    const away = eastOf(CENTRE, 30_000) // 30 km, far outside any snap
    tools.activate(TOOLS.POINT, {})
    engine.map.fire('click', { latlng: away })

    expect(done[0].latitude).toBeCloseTo(away.lat, 5)
    expect(done[0].longitude).toBeCloseTo(away.lng, 5)
  })

  it('the centre of a radial is a snap target too', () => {
    // Two radials from one origin should share it, so a second shape drawn
    // there is comparable with the first.
    const done = []
    tools.handlers.onComplete = (p) => done.push(p)
    engine.renderObject({
      id: 9, type: 'radial', geometry_type: 'Point',
      latlng: CENTRE, azimuth: 90, length_value: 10, length_unit: 'nm',
      color: '#a855f7', weight: 3, opacity: 1, visible: true,
      layer: 'radials', show_label: false, properties: {},
    })

    tools.activate(TOOLS.POINT, {})
    engine.map.fire('click', { latlng: eastOf(CENTRE, 150) })

    expect(done[0].latitude).toBeCloseTo(CENTRE[0], 6)
    expect(done[0].longitude).toBeCloseTo(CENTRE[1], 6)
  })

  it('a circle placed near another circle centres on the first', () => {
    const done = []
    tools.handlers.onComplete = (p) => done.push(p)
    addCircle(6, 10)

    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 2 })
    // First click: the centre, which is the point under test.
    engine.map.fire('click', { latlng: eastOf(CENTRE, 250) })

    expect(tools.draft.center, 'el primer clic no coloco el centro').toBeTruthy()
    expect(tools.draft.center[0], 'el centro no se engancho al del otro circulo')
      .toBeCloseTo(CENTRE[0], 6)
    expect(tools.draft.center[1]).toBeCloseTo(CENTRE[1], 6)

    // Second click: the size.
    engine.map.fire('click', { latlng: eastOf(CENTRE, 3704) })
    expect(done).toHaveLength(1)
    expect(done[0].type).toBe('circle')
    expect(done[0].latitude).toBeCloseTo(CENTRE[0], 6)
  })

  it('without any shape on the map, the click is untouched', () => {
    const done = []
    tools.handlers.onComplete = (p) => done.push(p)

    const away = eastOf(CENTRE, 500)
    tools.activate(TOOLS.POINT, {})
    engine.map.fire('click', { latlng: away })

    expect(done[0].latitude).toBeCloseTo(away.lat, 5)
  })
})

describe('the centre is visible on the map', () => {
  it('a circle shows a dot at its centre', () => {
    const layer = addCircle()
    // `L.circle` is itself a `CircleMarker` in Leaflet, so the ring has to be
    // told apart from the centre dot by its radius: the ring is in metres and
    // thousands of them, the dot is 4 pixels.
    const dots = layer.getLayers().filter((l) => l.getRadius?.() < 100)
    expect(dots.length, 'el circulo no muestra su centro').toBe(1)
    expect(dots[0].getLatLng().lat).toBeCloseTo(CENTRE[0], 6)
    expect(dots[0].options.interactive, 'el punto central no debe capturar clics')
      .toBe(false)
  })

  it('a radial shows a dot at its origin', () => {
    const layer = engine.renderObject({
      id: 9, type: 'radial', geometry_type: 'Point',
      latlng: CENTRE, azimuth: 45, length_value: 10, length_unit: 'nm',
      color: '#a855f7', weight: 3, opacity: 1, visible: true,
      layer: 'radials', show_label: false, properties: {},
    })
    const dots = layer.getLayers().filter((l) => l instanceof L.CircleMarker)
    expect(dots.length, 'el radial no muestra su origen').toBe(1)
    expect(dots[0].getLatLng().lng).toBeCloseTo(CENTRE[1], 6)
  })

  it('the layer publishes the centre for the snapping to find', () => {
    // The snap reads this rather than a second list of centres, which would be
    // one more thing to keep in step.
    const circle = addCircle()
    expect(circle.centreLatLng).toEqual(CENTRE)
  })
})
