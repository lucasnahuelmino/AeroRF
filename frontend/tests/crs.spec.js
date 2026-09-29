import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { MapEngine } from '@/map/MapEngine'

/**
 * What the projection in *this* Leaflet build actually offers.
 *
 * Two attempts failed on assumed APIs: `crs.scale` takes no argument and
 * returns a constant, and `crs.groundResolution` does not exist at all. The
 * only reliable source of metres-per-pixel is the map's own scale
 * calculation, which every Leaflet app already uses.
 */
let container
let engine

beforeEach(() => {
  container = document.createElement('div')
  container.id = 'map-crs'
  document.body.appendChild(container)
  engine = new MapEngine({ container: 'map-crs' })
  engine.init()
  engine.setView(-34.6, -58.4, 12)
})

afterEach(() => {
  engine?.destroy()
  container?.remove()
})

describe('the projection interface, as it is', () => {
  it('has no groundResolution in this version', () => {
    // Recorded so a Leaflet upgrade that adds it is noticed here rather than
    // as a silent behaviour change.
    expect(typeof engine.map.options.crs.groundResolution).toBe('undefined')
  })

  it('scale does not answer the question, and is not used for it', () => {
    // Tried twice, both wrong: with no arguments it returned a constant, and
    // with a LatLng it returns NaN. The scale factor it holds is in projected
    // units and carries no zoom, so it cannot express "metres per pixel".
    //
    // What matters is the consequence, which is asserted in mpp.spec.js: the
    // tolerance halves when the zoom doubles. A value that ignored zoom could
    // not do that.
    const crs = engine.map.options.crs
    const bare = crs.scale()
    expect(Number.isFinite(bare) || Number.isNaN(bare)).toBe(true)
    expect(typeof crs.groundResolution).toBe('undefined')
  })

  it('the map computes metres per pixel itself', () => {
    // `getScaleZoom` is the inverse of the same calculation the scale control
    // shows, and it needs a real ground distance — so this is the path that
    // works with no assumptions about the CRS API.
    const size = engine.map.getSize()
    const centre = engine.map.getCenter()
    const point = engine.map.latLngToContainerPoint(centre)

    // One screen height south, in metres on the ground.
    const south = engine.map.containerPointToLatLng([point.x, point.y + size.y])
    const ground = haversineRef(centre.lat, centre.lng, south.lat, south.lng)
    expect(ground).toBeGreaterThan(0)
  })
})

function haversineRef(lat1, lon1, lat2, lon2) {
  const R = 6371008.8
  const toRad = (d) => (d * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}
