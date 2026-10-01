/**
 * tests/typed-sizing.spec.js
 * ──────────────────────────
 * The radius in the options panel, and the circle that gets stored.
 *
 * The operator typed 5 NM, pressed the map, and got a circle of 2.987 NM.
 * Reproduced in the browser before this was written: the value written in the
 * panel was drawn on the map as a preview, and then discarded, because sizing a
 * circle took the distance between two clicks. There was no way to say "this
 * number, one click", and the panel's number was decoration.
 *
 * There are two jobs and they are now two explicit choices:
 *
 * - `useTyped: false`, the default and the original interaction. Click the
 *   centre, click where you want the edge. Nothing that worked before changes.
 * - `useTyped: true`. The panel's number is the size. One click, and the
 *   number stored is the number typed.
 *
 * A second defect showed up while fixing the first: the click that sizes the
 * shape also snapped to the centre of a nearby measured shape. The centre was
 * already placed, so that click only carried a distance, and the snap moved it
 * somewhere the operator never aimed at — 4.866 NM where they had asked for 5.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import L from 'leaflet'
import { MapEngine } from '@/map/MapEngine'
import { ToolManager, TOOLS } from '@/map/draw'

let container
let engine
let tools

const CENTRE = { lat: -34.6, lng: -58.4 }

beforeEach(() => {
  container = document.createElement('div')
  container.id = 'map-typed-sizing'
  document.body.appendChild(container)
  engine = new MapEngine({ container: 'map-typed-sizing' })
  engine.init()
  engine.suppressClicks(false)
  engine.setView(CENTRE.lat, CENTRE.lng, 12)
  tools = new ToolManager(engine, {})
})

afterEach(() => {
  tools?.deactivate()
  engine?.destroy()
  container?.remove()
})

/**
 * A stored 10 NM circle, which the sizing click used to snap to.
 *
 * The position is a real `L.LatLng`, not a plain `{lat, lng}`, because that is
 * what production stores: `MapEngine` publishes `centreLatLng`, and the snapping
 * code reads it as `centre[0]` and `centre[1]`. Handed a plain object those are
 * `undefined`, the distance comes out `NaN`, and nothing snaps — which looks
 * exactly like a broken feature and is not one.
 */
function addCircle(id = 6, radiusNm = 10) {
  return engine.renderObject({
    id,
    type: 'circle',
    name: 'Círculo',
    geometry_type: 'Point',
    latlng: L.latLng(CENTRE.lat, CENTRE.lng),
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

/** A latlng about `metres` north of the centre. */
function northOf(base, metres) {
  return { lat: base.lat + metres / 111_320, lng: base.lng }
}

describe('sizing a circle from the panel value', () => {
  it('one click stores the radius that was typed', () => {
    const done = []
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5, useTyped: true })
    tools.handlers.onComplete = (payload) => done.push(payload)

    engine.map.fire('click', { latlng: CENTRE })

    expect(done.length, 'un solo clic debe crear el objeto').toBe(1)
    // 5 NM is 9260 m exactly.
    expect(done[0].radius_m).toBeCloseTo(9_260, -1)
    expect(done[0].radius).toBeCloseTo(5, 3)
    expect(done[0].radius_unit).toBe('nm')
  })

  it('the circle is centred where the operator clicked', () => {
    const done = []
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5, useTyped: true })
    tools.handlers.onComplete = (payload) => done.push(payload)
    engine.map.fire('click', { latlng: CENTRE })
    expect(done[0].latitude).toBeCloseTo(CENTRE.lat, 6)
    expect(done[0].longitude).toBeCloseTo(CENTRE.lng, 6)
  })

  it('honours the unit, not just the number', () => {
    const done = []
    tools.activate(TOOLS.CIRCLE, { unit: 'km', radius: 37.04, useTyped: true })
    tools.handlers.onComplete = (payload) => done.push(payload)
    engine.map.fire('click', { latlng: CENTRE })
    expect(done[0].radius_m).toBeCloseTo(37_040, -1)
    expect(done[0].radius_unit).toBe('km')
  })

  it('leaves the tool armed, so a second circle takes one click too', () => {
    // The complaint that came with it: after creating one object the fields
    // disappeared, because creating one disarmed the tool. Placing four 5 NM
    // circles around four sites should be four clicks, not four rounds of
    // re-picking the tool and retyping the number.
    const done = []
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5, useTyped: true })
    tools.handlers.onComplete = (payload) => done.push(payload)

    engine.map.fire('click', { latlng: CENTRE })
    expect(tools.active, 'la herramienta debe seguir armada').toBe(TOOLS.CIRCLE)

    engine.map.fire('click', { latlng: { lat: CENTRE.lat - 0.2, lng: CENTRE.lng } })
    expect(done.length).toBe(2)
    expect(done[1].radius_m).toBeCloseTo(9_260, -1)
    expect(tools.active).toBe(TOOLS.CIRCLE)
  })

  it('picks up a radius typed after the tool was armed', () => {
    const done = []
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 20, useTyped: true })
    tools.setOptions({ radius: 3 })
    tools.handlers.onComplete = (payload) => done.push(payload)
    engine.map.fire('click', { latlng: CENTRE })
    expect(done[0].radius_m).toBeCloseTo(3 * 1852, -1)
  })

  it('sizes a radial from the panel value as well', () => {
    const done = []
    tools.activate(TOOLS.RADIAL, { unit: 'nm', length: 12, azimuth: 90, useTyped: true })
    tools.handlers.onComplete = (payload) => done.push(payload)
    engine.map.fire('click', { latlng: CENTRE })
    expect(done.length).toBe(1)
    expect(done[0].length_m).toBeCloseTo(12 * 1852, -1)
    expect(done[0].azimuth).toBeCloseTo(90, 1)
  })

  it('committing a shape does not touch the click subscription', () => {
    // The engine emits by walking a `Set` with `forEach`, and `forEach` visits
    // entries added during the iteration. So a commit that unsubscribes and
    // subscribes again, from inside the click handler, hands the click
    // straight back to its replacement: which commits, subscribes again, and
    // the walk never ends. The tab locks up on the first click.
    //
    // Asserted on a commit driven directly rather than through a click. That
    // is deliberate: with the re-subscription in place, driving it through a
    // click does not fail the test, it **hangs the whole run**, and a guard
    // that wedges the suite is not a guard. Calling the commit by hand runs the
    // same code and reports a number.
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5, useTyped: true })
    const registered = () => [...(engine._listeners?.get('click') ?? [])]
    const armed = registered()
    expect(armed.length, 'una herramienta armada escucha una vez').toBe(1)

    // Start and commit a shape without going through `_onClick`.
    tools._startCircle([CENTRE.lat, CENTRE.lng])
    tools.commitCircle({ keepTool: true })

    const after = registered()
    // The size alone cannot catch this: unsubscribing and subscribing again
    // leaves the count at one. What changes is *which* function is registered.
    expect(after.length, 'confirmar no debe volver a suscribir').toBe(1)
    expect(after[0], 'el listener registrado debe ser el mismo de siempre')
      .toBe(armed[0])
    expect(tools.active, 'la herramienta sigue armada').toBe(TOOLS.CIRCLE)
  })

  it('four circles in a row take one click each', () => {
    const done = []
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5, useTyped: true })
    tools.handlers.onComplete = (payload) => done.push(payload)
    for (let i = 0; i < 4; i += 1) {
      engine.map.fire('click', { latlng: { lat: CENTRE.lat - i * 0.05, lng: CENTRE.lng } })
    }
    expect(done.length, 'cuatro clics, cuatro circulos').toBe(4)
    for (const d of done) expect(d.radius_m).toBeCloseTo(5 * 1852, -1)
    expect(tools.active).toBe(TOOLS.CIRCLE)
  })
})

describe('the original two-click sizing still works', () => {
  it('takes the radius from the distance between the two clicks', () => {
    // The behaviour that existed before the mode was added. It is the default
    // precisely so that nothing an operator learned yesterday is wrong today.
    const done = []
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5 })
    tools.handlers.onComplete = (payload) => done.push(payload)

    engine.map.fire('click', { latlng: CENTRE })
    expect(done.length, 'el primer clic solo fija el centro').toBe(0)

    // 10 NM due north of the centre.
    engine.map.fire('click', { latlng: northOf(CENTRE, 10 * 1852) })
    expect(done.length).toBe(1)
    expect(done[0].radius_m).toBeCloseTo(10 * 1852, -2)
  })

  it('disarms the tool after committing, as it always did', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5 })
    tools.handlers.onComplete = () => {}
    engine.map.fire('click', { latlng: CENTRE })
    engine.map.fire('click', { latlng: northOf(CENTRE, 10 * 1852) })
    expect(tools.active).toBeNull()
  })

  it('still honours the panel value when the operator presses Enter', () => {
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5 })
    engine.map.fire('click', { latlng: CENTRE })
    const done = tools.finish()
    expect(done.radius_m).toBeCloseTo(9_260, -1)
  })
})

describe('the click that sizes a shape is taken where it landed', () => {
  it('is not snapped to the centre of a nearby circle', () => {
    // The circle's centre is a few hundred metres from where the sizing click
    // lands, well inside the ten-pixel snap, so a snapped click would report a
    // radius of a few hundred metres instead of 5 NM. That is the bug: the
    // operator asked for 5 NM and got 0.16 NM, off by a factor of 30.
    addCircle(6, 10)
    const done = []
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5 })
    tools.handlers.onComplete = (payload) => done.push(payload)

    // First click: the centre, placed clear of the existing circle.
    const centre = { lat: CENTRE.lat - 0.3, lng: CENTRE.lng }
    engine.map.fire('click', { latlng: centre })
    // Second click: 5 NM north of that centre, and also inside the snap radius
    // of the existing circle's centre.
    engine.map.fire('click', { latlng: northOf(centre, 5 * 1852) })

    expect(done.length).toBe(1)
    const wanted = 5 * 1852
    // `metres / 111320` degrees is an approximation of the meridian arc and
    // comes out about 0.1% short, so the check is 1%. A snap would be off by
    // 30 times that, so it still cannot pass by accident.
    expect(Math.abs(done[0].radius_m - wanted) / wanted).toBeLessThan(0.01)
  })

  it('the first click still snaps, because that is what snapping is for', () => {
    addCircle(6, 10)
    const done = []
    tools.activate(TOOLS.CIRCLE, { unit: 'nm', radius: 5, useTyped: true })
    tools.handlers.onComplete = (payload) => done.push(payload)
    // 100 m east of the existing circle's own centre. The snap reaches ten
    // screen pixels, which at this zoom is about 315 m, so 100 m sits well
    // inside it: what is under test is whether snapping happens, not how close
    // to the edge of the tolerance it happens.
    const east = {
      lat: CENTRE.lat,
      lng: CENTRE.lng + 100 / (111_320 * Math.cos((CENTRE.lat * Math.PI) / 180)),
    }
    engine.map.fire('click', { latlng: east })
    expect(done.length).toBe(1)
    expect(Math.abs(done[0].latitude - CENTRE.lat)).toBeLessThan(1e-5)
    expect(Math.abs(done[0].longitude - CENTRE.lng)).toBeLessThan(1e-5)
  })
})
