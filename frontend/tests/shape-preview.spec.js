import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { MapEngine } from '@/map/MapEngine'
import { ToolManager, TOOLS } from '@/map/draw'
import { arcPoints } from '@/map/geo'

/**
 * The two things the operator asked for.
 *
 * 1. A radial must show the degrees live, measured from something. An azimuth
 *    is a bare number until the operator can see what it is measured from, so
 *    the reference line and the angle arc are part of the reading, not
 *    decoration.
 *
 * 2. Choosing a radius must show the circle. Picking the tool with 5 NM set
 *    used to draw nothing at all until the centre was clicked, so the number
 *    could not be judged against what it would cover.
 */
let container
let engine
let tools

const CENTRE = { lat: -34.6, lng: -58.4 }

beforeEach(() => {
  container = document.createElement('div')
  container.id = 'map-preview'
  document.body.appendChild(container)
  engine = new MapEngine({ container: 'map-preview' })
  engine.init()
  engine.suppressClicks(false)
  tools = new ToolManager(engine, {})
  // A known view centre, so the ghost has somewhere to be drawn.
  engine.setView(CENTRE.lat, CENTRE.lng, 10)
})

afterEach(() => {
  tools?.deactivate()
  engine?.destroy()
  container?.remove()
})

/**
 * Names of the draft layers currently on the map.
 *
 * Reads the engine's own `_draftLayers` map rather than a public accessor,
 * because there is no public one — and inventing a test-only getter on the
 * engine would be adding API for the tests' benefit rather than the app's.
 */
function draftKeys() {
  return [...(engine._draftLayers?.keys?.() || [])]
}

/** A draft layer, or undefined. */
function draft(key) {
  return engine._draftLayers?.get?.(key)
}

describe('a circle is visible at its configured radius before any click', () => {
  it('draws the ring as soon as the tool is picked', () => {
    // Nothing is clicked here. That is the point: the operator set a radius
    // and needs to see it against the map before committing to it.
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5 })

    expect(draftKeys(), 'no se dibuja nada al elegir la herramienta')
      .toContain('ghost')

    const ghost = draft('ghost')
    expect(ghost, 'no hay capa de preview').toBeTruthy()
    // A 5 NM ring is 9 260 m. Asserted in metres because that is what
    // Leaflet takes, and it is the value that has to be right for the circle
    // to be the size the operator asked for.
    expect(ghost.options.radius, 'el circulo no tiene el radio pedido')
      .toBeCloseTo(9260, 0)
  })

  it('redraws when the radius is typed, so the operator sees the change', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5 })
    tools.setOptions({ radius: 20 })

    const ghost = draft('ghost')
    expect(ghost.options.radius, 'el circulo no se redibujo al cambiar el radio')
      .toBeCloseTo(20 * 1852, 0)
  })

  it('redraws when the unit changes, keeping the physical size', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5 })
    tools.setOptions({ unit: 'km', radius: 9.26 })

    const ghost = draft('ghost')
    // 5 NM and 9.26 km are the same distance. A unit switch that changed the
    // drawn size would silently resize the operator's circle.
    expect(ghost.options.radius).toBeCloseTo(9260, 0)
  })

  it('reports the configured size to the panel before anything is clicked', () => {
    // The panel is where the operator reads the value. A ghost with no readout
    // is a circle of unknown provenance.
    const previews = []
    tools.handlers.onPreview = (p) => previews.push(p)

    tools.activate(TOOLS.CIRCLE, { unit: 'km', radius: 12 })

    const ghost = previews.find((p) => p.ghost)
    expect(ghost, 'la vista previa no se reporta').toBeTruthy()
    expect(ghost.type).toBe('circle')
    expect(ghost.radius).toBe(12)
    expect(ghost.radius_m).toBeCloseTo(12000, 0)
    expect(ghost.unit).toBe('km')
  })

  it('goes away when the tool is released, leaving no phantom circle', () => {
    // A preview that outlives the tool would leave a ring on the map that
    // nothing will ever store.
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5 })
    expect(draftKeys()).toContain('ghost')

    tools.deactivate()
    expect(draftKeys(), 'quedo un circulo sin confirmar').not.toContain('ghost')
  })
})

describe('a radial shows the degrees live, against a reference', () => {
  it('draws the north reference and the angle arc while sizing', () => {
    tools.activate(TOOLS.RADIAL, { unit: 'km', length: 20, azimuth: 0 })
    engine.map.fire('click', { latlng: CENTRE })
    tools.previewAt({ lat: -34.4, lng: -58.4 })

    expect(draftKeys(), 'falta la referencia del azimut').toContain('radial-ref')
    expect(draftKeys(), 'falta la linea del radial').toContain('radial')
  })

  it('reports the degrees on every move, not only on the click', () => {
    const previews = []
    tools.handlers.onPreview = (p) => previews.push(p)

    tools.activate(TOOLS.RADIAL, { unit: 'km', length: 20, azimuth: 0 })
    engine.map.fire('click', { latlng: CENTRE })

    // Due east of the centre: 090°.
    tools.previewAt({ lat: -34.6, lng: -58.0 })
    const east = previews[previews.length - 1]
    expect(east.type).toBe('radial')
    expect(east.azimuth, 'no reporta los grados en vivo').toBeCloseTo(90, 0)

    // Due north: 000°.
    tools.previewAt({ lat: -34.2, lng: -58.4 })
    expect(previews[previews.length - 1].azimuth).toBeCloseTo(0, 0)
  })

  it('labels the far end of the line permanently, so it can be read without hovering', () => {
    // The tooltip on the line needs a hover. A permanent label at the end is
    // what makes the value readable while the pointer is sweeping.
    tools.activate(TOOLS.RADIAL, { unit: 'km', length: 20, azimuth: 0 })
    engine.map.fire('click', { latlng: CENTRE })
    tools.previewAt({ lat: -34.6, lng: -58.0 })

    expect(draftKeys()).toContain('radial-end')
    const end = draft('radial-end')
    const label = end.getTooltip?.()?.getContent?.() || ''
    expect(label, 'la etiqueta del extremo no muestra los grados').toMatch(/9[0-9]/)
    expect(label, 'la etiqueta no dice el rumbo').toMatch(/E\b/)
  })

  it('keeps the committed line and the angle it was drawn at', () => {
    // The trace from the origin to where the operator pointed, at the angle
    // that was read off the reference, and stored as that angle.
    const done = []
    tools.handlers.onComplete = (p) => done.push(p)

    tools.activate(TOOLS.RADIAL, { unit: 'km', length: 20, azimuth: 0 })
    engine.map.fire('click', { latlng: CENTRE })
    tools.previewAt({ lat: -34.6, lng: -58.0 })
    const read = tools.draft.azimuth
    engine.map.fire('click', { latlng: { lat: -34.6, lng: -58.0 } })

    expect(done).toHaveLength(1)
    expect(done[0].type).toBe('radial')
    expect(done[0].azimuth, 'no se guardo el azimut leido')
      .toBeCloseTo(read, 1)
    expect(done[0].latitude).toBeCloseTo(CENTRE.lat, 5)
    expect(done[0].longitude).toBeCloseTo(CENTRE.lng, 5)
  })
})

describe('the angle arc', () => {
  it('runs from north to the bearing, the short way round', () => {
    // 45° is a 45° arc, not 315°. Drawing the long way would misrepresent the
    // angle the operator is reading.
    const pts = arcPoints([0, 0], 1000, 0, 45, 4)
    expect(pts).toHaveLength(5)
    const bearings = pts.map(([lat, lon]) => (Math.atan2(lon, lat) * 180) / Math.PI)
    const first = ((bearings[0] % 360) + 360) % 360
    const last = ((bearings[bearings.length - 1] % 360) + 360) % 360
    expect(first).toBeCloseTo(0, 1)
    expect(last).toBeCloseTo(45, 1)
  })

  it('sweeps backwards past north rather than forwards through 350°', () => {
    const pts = arcPoints([0, 0], 1000, 0, 350, 6)
    const bearings = pts.map(([lat, lon]) =>
      (((Math.atan2(lon, lat) * 180) / Math.PI) % 360 + 360) % 360)
    // 350° the short way is -10°, so the arc passes through 355 on its way
    // down. A forward sweep would pass through 90 instead.
    expect(bearings[1]).toBeGreaterThan(350)
  })

  it('degrades to a single point when there is no radius', () => {
    expect(arcPoints([1, 2], 0, 0, 90, 8)).toEqual([[1, 2]])
  })
})
