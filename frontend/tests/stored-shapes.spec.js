import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import L from 'leaflet'
import { MapEngine } from '@/map/MapEngine'
import { bearing as bearingBetween, haversine } from '@/map/geo'

/**
 * A saved circle and a saved radial have to be on the map.
 *
 * The operator drew one, the values were stored correctly and the panel showed
 * them, and the shape was a dot. Both are stored as a centre plus a
 * measurement — `geometry_type` is `Point`, because that is what the centre is
 * — while the drawing dispatched on `geometry_type` alone, so every stored
 * circle and radial fell into the point branch.
 *
 * The stored rows are reproduced exactly as the database holds them, read back
 * from a real save, because a fixture written from the drawing code would have
 * inherited whatever the bug was.
 */
let container
let engine

beforeEach(() => {
  container = document.createElement('div')
  container.id = 'map-stored'
  document.body.appendChild(container)
  engine = new MapEngine({ container: 'map-stored' })
  engine.init()
})

afterEach(() => {
  engine?.destroy()
  container?.remove()
})

/** A row as it comes back from GET /map/objects, camelCase keys and all. */
const STORED_CIRCLE = {
  id: 6,
  type: 'circle',
  name: 'Círculo',
  geometry_type: 'Point',
  latlng: [-34.44202613062483, -58.98559570312501],
  latlngs: null,
  radius: 5.321,
  radius_unit: 'nm',
  color: '#3b82f6',
  weight: 3,
  opacity: 1,
  fill_opacity: 0.15,
  visible: true,
  layer: 'circles',
  show_label: true,
  properties: {},
  metrics: { radius_m: 9854.5, radius_km: 9.85, radius_nm: 5.321 },
}

const STORED_RADIAL = {
  id: 9,
  type: 'radial',
  name: 'Radial',
  geometry_type: 'Point',
  latlng: [-34.568775557959036, -58.79608154296876],
  latlngs: null,
  azimuth: 323.09,
  length_value: 10.873,
  length_unit: 'nm',
  color: '#a855f7',
  weight: 3,
  opacity: 1,
  visible: true,
  layer: 'radials',
  show_label: true,
  properties: {},
}

/**
 * The circle and the radial inside a stored layer.
 *
 * Both are layer groups now, so the shape is one of the children rather than
 * the layer itself: a circle is its ring plus the dot at its centre, a radial
 * is its line plus the dot at its origin. Reading the group rather than the
 * child is what makes the assertions describe the object on the map instead of
 * one of its parts.
 */
function ring(layer) {
  // A measured circle is a group — the ring plus its centre dot. A coverage
  // polygon is not: it goes through the geometry branch and is the circle
  // itself. So the search starts at the layer and descends only if it is a
  // group.
  if (typeof layer.getRadius === 'function' && layer.getRadius() > 100) return layer
  if (typeof layer.getLayers !== 'function') return undefined
  return layer.getLayers().find(
    (l) => typeof l.getRadius === 'function' && l.getRadius() > 100,
  )
}

function line(layer) {
  if (typeof layer.getLatLngs === 'function') return layer
  if (typeof layer.getLayers !== 'function') return undefined
  return layer.getLayers().find((l) => typeof l.getLatLngs === 'function')
}

describe('a stored circle is drawn as a circle', () => {
  it('is not a dot', () => {
    const layer = engine.renderObject(STORED_CIRCLE)
    expect(layer, 'no se dibujo nada').toBeTruthy()
    // A dot has no radius in metres. The ring does, and it is thousands of
    // them; a bare dot would be 4 pixels.
    const shape = ring(layer)
    expect(shape, 'sigue siendo un punto, no un circulo').toBeTruthy()
    expect(shape.getRadius()).toBeGreaterThan(9000)
  })

  it('has the stored radius, in metres', () => {
    const layer = engine.renderObject(STORED_CIRCLE)
    // 5.321 NM is 9 854.5 m. The stored unit is NM; drawing 5.321 as
    // kilometres would be a circle twenty times too small.
    expect(ring(layer).getRadius()).toBeCloseTo(9854.5, 1)
  })

  it('falls back to the unit when metrics are absent', () => {
    // A row read without `metrics` still has `radius` and `radius_unit`, and
    // the unit is what makes the number mean anything.
    const bare = { ...STORED_CIRCLE, metrics: undefined }
    const layer = engine.renderObject(bare)
    expect(ring(layer).getRadius()).toBeCloseTo(5.321 * 1852, 0)
  })

  it('respects the unit: the same number in km is twenty times further', () => {
    const inKm = { ...STORED_CIRCLE, metrics: undefined, radius: 5.321, radius_unit: 'km' }
    const layer = engine.renderObject(inKm)
    expect(ring(layer).getRadius()).toBeCloseTo(5321, 0)
  })

  it('is placed at the stored centre, not at the origin', () => {
    const layer = engine.renderObject(STORED_CIRCLE)
    const centre = ring(layer).getLatLng()
    expect(centre.lat).toBeCloseTo(-34.44202613062483, 6)
    expect(centre.lng).toBeCloseTo(-58.98559570312501, 6)
  })
})

describe('a stored radial is drawn as a line', () => {
  it('is a polyline, not a dot', () => {
    const layer = engine.renderObject(STORED_RADIAL)
    expect(layer, 'no se dibujo nada').toBeTruthy()
    const shape = line(layer)
    expect(shape, 'sigue siendo un punto').toBeTruthy()
    expect(shape.getLatLngs().length).toBeGreaterThan(1)
  })

  it('starts at the stored origin and runs the stored length', () => {
    const layer = engine.renderObject(STORED_RADIAL)
    const pts = line(layer).getLatLngs()
    const first = pts[0]
    expect(first.lat).toBeCloseTo(-34.568775557959036, 6)
    expect(first.lng).toBeCloseTo(-58.79608154296876, 6)

    // 10.873 NM is about 20.1 km. The endpoints are vertices along that line.
    const last = pts[pts.length - 1]
    const metres = haversine(first.lat, first.lng, last.lat, last.lng)
    expect(metres, 'la linea no mide lo guardado').toBeGreaterThan(19_000)
    expect(metres).toBeLessThan(21_500)
  })

  it('points on the stored bearing, not due north', () => {
    // 323° is north-west. Due north would pass the sanity check on length and
    // still be the wrong object, so the bearing is checked directly.
    const layer = engine.renderObject(STORED_RADIAL)
    const pts = line(layer).getLatLngs()
    const bearing = bearingBetween(pts[0].lat, pts[0].lng, pts[1].lat, pts[1].lng)
    expect(bearing, 'la linea no sale en el azimut guardado')
      .toBeCloseTo(323.09, 0)
  })

  it('carries its azimuth and length on the layer, for later edits', () => {
    const layer = engine.renderObject(STORED_RADIAL)
    expect(layer.azimuth).toBeCloseTo(323.09, 2)
    expect(layer.lengthM).toBeCloseTo(10.873 * 1852, 0)
  })
})

describe('objects that are not measured shapes still draw as before', () => {
  it('a plain point is still a dot', () => {
    const layer = engine.renderObject({
      id: 1, type: 'point', geometry_type: 'Point',
      latlng: [-34.6, -58.4], visible: true, properties: {},
    })
    // A dot has no setRadius and no ring; a circle has both. Checking the class
    // is what distinguishes them, since a circleMarker also answers getRadius
    // with the marker radius in pixels.
    expect(layer instanceof L.CircleMarker, 'un punto normal dejo de ser un punto')
      .toBe(true)
    // A dot is not a group: there is nothing inside it to have a ring.
    expect(typeof layer.getLayers, 'un punto normal no deberia ser un grupo')
      .toBe('undefined')
  })

  it('a line is still a polyline', () => {
    const layer = engine.renderObject({
      id: 2, type: 'line', geometry_type: 'LineString',
      latlngs: [[-34.6, -58.4], [-34.5, -58.3]], visible: true, properties: {},
    })
    expect(layer.getLatLngs()).toHaveLength(2)
  })

  it('a coverage polygon is still drawn as a real circle', () => {
    const layer = engine.renderObject({
      id: 3, type: 'coverage', geometry_type: 'Polygon',
      latlng: [-34.6, -58.4], latlngs: [[-34.6, -58.4], [-34.5, -58.3]],
      radius_m: 3000, visible: true, properties: {},
    })
    expect(ring(layer).getRadius()).toBeCloseTo(3000, 0)
  })
})

describe('a measurement the data does not carry', () => {
  it('a circle with no radius falls back rather than drawing nothing silently', () => {
    // Better a dot the operator can see and ask about than an invisible
    // object that looks like a failed load.
    const layer = engine.renderObject({
      id: 4, type: 'circle', geometry_type: 'Point',
      latlng: [-34.6, -58.4], visible: true, properties: {},
    })
    expect(layer, 'el objeto desaparecio del mapa').toBeTruthy()
    expect(layer instanceof L.Circle, 'sin radio no puede inventarse un circulo')
      .toBe(false)
  })

  it('a radial with no length is still visible', () => {
    const layer = engine.renderObject({
      id: 5, type: 'radial', geometry_type: 'Point',
      azimuth: 90, latlng: [-34.6, -58.4], visible: true, properties: {},
    })
    expect(layer, 'el objeto desaparecio del mapa').toBeTruthy()
  })
})

describe('a stored shape is selectable', () => {
  /**
   * The regression, and the reason it survived a green suite.
   *
   * The circle became a group to carry its centre dot, and a plain
   * `L.layerGroup` does not pass on the events its children receive. Clicking
   * the ring raised nothing on the group, so the store never selected it — and
   * with nothing selected there is no way to delete an object or annotate it.
   *
   * Every other test here reads geometry off the layer, which a group answers
   * perfectly well. Only this one clicks, which is why the suite was green on
   * an object the operator could not touch.
   */
  function selectAndReport(object) {
    const engine = new MapEngine({ container: 'select-box' })
    const box = document.createElement('div')
    box.id = 'select-box'
    document.body.appendChild(box)
    engine.init()

    const chosen = []
    const layer = engine.renderObject(object)
    engine.onObjectClick(object.id, (id) => chosen.push(id))

    // The shape itself, dispatched the way Leaflet dispatches to the layer
    // under the pointer — with `propagate`, so the event climbs to the group
    // the handler is bound to. Without it nothing reaches the handler, and the
    // test would report an object as unselectable for a reason that does not
    // exist on screen.
    const shape = ring(layer) || line(layer) || layer
    shape.fire('click', { latlng: L.latLng(object.latlng) }, true)

    engine.destroy()
    box.remove()
    return chosen
  }

  it('a circle can be selected by clicking it', () => {
    const chosen = selectAndReport(STORED_CIRCLE)
    expect(chosen, 'el circulo no se puede seleccionar').toEqual([STORED_CIRCLE.id])
  })

  it('a radial can be selected by clicking it', () => {
    const chosen = selectAndReport(STORED_RADIAL)
    expect(chosen, 'el radial no se puede seleccionar').toEqual([STORED_RADIAL.id])
  })

  it('a plain point can be selected', () => {
    const chosen = selectAndReport({
      id: 1, type: 'point', geometry_type: 'Point',
      latlng: [-34.6, -58.4], visible: true, properties: {},
    })
    expect(chosen, 'un punto normal no se puede seleccionar').toEqual([1])
  })

  it('the centre dot is not a click target, so it cannot swallow a click', () => {
    // Deliberate, and the reason is the middle of the circle: that is the one
    // place an operator would click, and a 4-pixel target on top of it would
    // make the most natural click in the object do nothing.
    //
    // The flag is what Leaflet's own hit-testing consults, so that is what is
    // asserted. Firing a synthetic click at the dot instead would report that
    // it selects the shape — which is true of the event and irrelevant, because
    // a non-interactive layer never receives a real pointer event to begin with.
    const layer = engine.renderObject(STORED_CIRCLE)
    const dot = layer.getLayers().find((l) => l.getRadius?.() < 100)

    expect(dot, 'no hay punto central').toBeTruthy()
    expect(dot.options.interactive, 'el punto central no debe ser interactivo')
      .toBe(false)
  })
})

// ─── helpers ────────────────────────────────────────────────────────────────
// The geometry helpers are imported at the top, under the names the module
// exports: `bearing` is the bearing between two points, and the test needed it
// to check the radial's direction independently of the code that drew it.
