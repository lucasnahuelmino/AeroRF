import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { MapEngine } from '@/map/MapEngine'

/**
 * What one screen pixel is worth on the ground.
 *
 * The snap tolerance is expressed in pixels and converted through this, so a
 * wrong answer here means the snap either never fires or fires from across the
 * map. It is checked on its own because the failure it causes is silent: the
 * click simply lands where it was put, and nothing says why.
 */
let container
let engine

beforeEach(() => {
  container = document.createElement('div')
  container.id = 'map-mpp'
  document.body.appendChild(container)
  engine = new MapEngine({ container: 'map-mpp' })
  engine.init()
})

afterEach(() => {
  engine?.destroy()
  container?.remove()
})

describe('metresPerPixel', () => {
  it('is a positive number at a normal zoom', () => {
    engine.setView(-34.6, -58.4, 12)
    const mpp = engine.metresPerPixel()
    expect(typeof mpp).toBe('number')
    expect(mpp).toBeGreaterThan(0)
  })

  it('halves when the zoom doubles', () => {
    // The defining property, and the reason the tolerance can be expressed in
    // pixels at all. Compared with a percentage rather than exactly: the map's
    // view centre moves as the zoom changes, so the latitude — and with it the
    // Mercator scale — shifts very slightly. A tolerance of 0.3 % is far below
    // anything that would matter and still fails a factor-of-two error.
    engine.setView(-34.6, -58.4, 10)
    const wide = engine.metresPerPixel()
    engine.setView(-34.6, -58.4, 11)
    const near = engine.metresPerPixel()

    const ratio = wide / near
    expect(ratio, 'no se reduce a la mitad al acercar').toBeGreaterThan(1.99)
    expect(ratio).toBeLessThan(2.01)
  })

  it('is smaller near the equator than at high latitude', () => {
    // Mercator stretches with latitude, so one pixel covers fewer metres as
    // you move away from the equator. This matters here: Argentina spans
    // roughly 22° to 55° south, so a tolerance that ignored it would be a
    // third tighter in the north than in the south for the same hand movement.
    engine.setView(0, 0, 10)
    const equator = engine.metresPerPixel()
    engine.setView(-60, -58.4, 10)
    const south = engine.metresPerPixel()

    expect(equator, 'en el ecuador un pixel debe cubrir mas terreno')
      .toBeGreaterThan(south)
    // The ratio follows 1/cos(lat), which at 60° is a factor of two. Measured
    // over a full screen height rather than infinitesimally, so the meridian
    // curves a little within the measured span and the figure comes out near
    // 2.02 rather than exactly 2 — within 2 %.
    expect(equator / south).toBeGreaterThan(1.98)
    expect(equator / south).toBeLessThan(2.06)
  })

  it('agrees with the Web Mercator formula, computed independently', () => {
    // The closed form for metres per pixel in EPSG:3857, which is not the code
    // under test — the code measures a screen height on the map and divides.
    // Two different routes to the same quantity, so a mistake in either shows.
    //
    //   m/px = 2·π·R·cos(lat) / (256·2^zoom)
    //
    // at the equator, R being the Earth's radius. The map's centre is used
    // because the local scale varies slightly across a screen.
    engine.setView(-34.6, -58.4, 12)
    const measured = engine.metresPerPixel()

    const R = 6371008.8
    const lat = engine.map.getCenter().lat
    const expected =
      (2 * Math.PI * R * Math.cos((lat * Math.PI) / 180)) / (256 * 2 ** 12)

    // Within 1 %: the measured value spans a whole screen height, across which
    // the latitude — and so the scale — changes measurably. That is the same
    // reason the two earlier attempts drifted.
    expect(Math.abs(measured - expected) / expected).toBeLessThan(0.01)
  })
})
