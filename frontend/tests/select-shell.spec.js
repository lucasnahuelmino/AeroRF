import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

/**
 * The selection, in the shell: the click is listened for in two places and one
 * of them undoes the other's work.
 *
 * This is the level at which the bug lived, and it is why nothing selected.
 * The object handler selects, the map handler — which sees the same click,
 * because a canvas renderer gives `stopPropagation` nowhere to stop it — clears
 * the selection. Both ran, in that order, and the operator saw no effect.
 *
 * A test on the engine or the store cannot see this: neither one clears
 * anything. It takes the mounted shell, with a real object on the map and a
 * real click on it.
 */
vi.mock('@/api/client', () => {
  const RESP = (payload) => Promise.resolve(payload)
  return {
    API_PREFIX: '/api/v1',
    describeError: (e) => String(e?.message || e),
    client: {
      get: () => RESP({}), post: () => RESP({}),
      put: () => RESP({}), patch: () => RESP({}), delete: () => RESP({}),
    },
    default: { get: () => RESP({}), post: () => RESP({}), put: () => RESP({}), delete: () => RESP({}) },
    system: { vocabulary: () => RESP({}) },
    layers: { list: () => RESP({ layers: [] }) },
    mapObjects: { all: () => RESP({ objects: [] }), stats: () => RESP({}) },
    flights: {
      live: () => RESP({ states: {} }),
      tracked: () => RESP({ slots: [] }),
      sessions: () => RESP({ sessions: [] }),
    },
    rf: {}, correlation: {}, expedientes: {}, exporter: {},
  }
})

const CENTRE = [-34.6, -58.4]

const CIRCLE = {
  id: 6, type: 'circle', name: 'Círculo', geometry_type: 'Point',
  latlng: CENTRE, radius: 10, radius_unit: 'nm',
  metrics: { radius_m: 18520, radius_nm: 10, radius_km: 18.52 },
  color: '#3b82f6', weight: 3, opacity: 1, fill_opacity: 0.15,
  visible: true, layer: 'circles', show_label: true,
  properties: { layer_name: 'Círculos' },
}

let shell
let box
let engine

beforeEach(() => {
  vi.resetModules()
  setActivePinia(createPinia())
  box = document.createElement('div')
  box.id = 'shell-map'
  document.body.appendChild(box)
})

afterEach(() => {
  shell?.unmount()
  box?.remove()
})

async function mountShellWithObject(object) {
  const api = await import('@/api/client')
  vi.spyOn(api.mapObjects, 'all').mockResolvedValue({ objects: [object] })
  vi.spyOn(api.mapObjects, 'stats').mockResolvedValue({})

  const GisShell = (await import('@/views/GisShell.vue')).default
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  router.push('/')
  await router.isReady()

  shell = mount(GisShell, { global: { plugins: [router] } })
  await flushPromises()

  const { useMapStore } = await import('@/stores/map')
  const store = useMapStore()
  engine = store.engine
  return { shell, store, engine }
}

describe('clicking an object in the mounted shell', () => {
  it('leaves it selected, with the select tool', async () => {
    // The reported symptom, end to end: click the object, and nothing is
    // selected — so it cannot be deleted, annotated, moved or measured.
    const { store, engine: eng } = await mountShellWithObject(CIRCLE)
    const { useMapStore } = await import('@/stores/map')
    const mapStore = useMapStore()

    expect(mapStore.objects.length, 'el objeto no se cargo').toBe(1)

    const layer = eng.featureLayers.get(String(CIRCLE.id))
    expect(layer, 'el objeto no se dibujo').toBeTruthy()

    // A real click on the shape. One DOM event; Leaflet fires it on the layer
    // and it continues to the map, which is the whole problem.
    const target = eng.vectorLayersFor(layer)[0] || layer
    target.fire('click', { latlng: { lat: CENTRE[0], lng: CENTRE[1] } }, true)
    await flushPromises()

    expect(
      mapStore.selectedId,
      'el objeto no quedo seleccionado: no se puede borrar ni anotar',
    ).toBe(CIRCLE.id)
  })

  it('a click on empty ground does clear the selection', async () => {
    // The other half. If this stopped working, objects would be impossible to
    // deselect, which is the same kind of trap in the other direction.
    const { engine: eng } = await mountShellWithObject(CIRCLE)
    const { useMapStore } = await import('@/stores/map')
    const mapStore = useMapStore()

    const layer = eng.featureLayers.get(String(CIRCLE.id))
    eng.vectorLayersFor(layer)[0].fire(
      'click', { latlng: { lat: CENTRE[0], lng: CENTRE[1] } }, true,
    )
    await flushPromises()
    expect(mapStore.selectedId).toBe(CIRCLE.id)

    // Now somewhere with nothing on it. Read straight from the engine's own
    // publication, which is what a click on empty ground produces: no object
    // handler is involved, so there is no `overObject` and the shell's guard
    // must let the clear through.
    const published = []
    eng.on('click', (p) => published.push(p))
    eng.map.fire('click', { latlng: { lat: -35.2, lng: -57.2 } })
    await flushPromises()

    expect(published.length, 'el motor no publico el clic en el vacio').toBe(1)
    expect(published[0].overObject, 'el clic en el vacio no deberia traer id')
      .toBeFalsy()

    // Is the shell even listening? If it is not, the clear never runs and the
    // selection survives a click on nothing — which is what this test has been
    // reporting, and which is a different bug from the one it was written for.
    const seenByShell = []
    eng.on('click', (p) => seenByShell.push(p))
    eng.map.fire('click', { latlng: { lat: -35.3, lng: -57.3 } })
    await flushPromises()
    // Two listeners now on the engine: the earlier `published` one and this.
    expect(seenByShell.length, 'nadie escucha el clic del mapa').toBeGreaterThan(0)

    // The shell clears when no drawing tool is armed. Read rather than assumed:
    // `active` is null until a tool is picked, and the select tool is only
    // ever activated from the airport measurement, so a test that asserted
    // `active === 'select'` would have failed here and described a different
    // problem.
    expect(
      mapStore.toolManager?.isDrawing,
      'no deberia haber ninguna herramienta de dibujo armada',
    ).toBe(false)

    expect(mapStore.selectedId, 'el clic en el vacio no deselecciono')
      .toBeNull()
  })

  it('an object is still selectable after another one was', async () => {
    const second = { ...CIRCLE, id: 7, name: 'Otro', latlng: [-34.5, -58.3] }
    const { engine: eng } = await mountShellWithObject(CIRCLE)
    const { useMapStore } = await import('@/stores/map')
    const mapStore = useMapStore()
    mapStore.objects = [CIRCLE, second]
    mapStore.renderAll()
    await flushPromises()

    const a = eng.featureLayers.get(String(CIRCLE.id))
    eng.vectorLayersFor(a)[0].fire(
      'click', { latlng: { lat: CENTRE[0], lng: CENTRE[1] } }, true,
    )
    await flushPromises()
    expect(mapStore.selectedId).toBe(CIRCLE.id)

    const b = eng.featureLayers.get(String(second.id))
    eng.vectorLayersFor(b)[0].fire(
      'click', { latlng: { lat: -34.5, lng: -58.3 } }, true,
    )
    await flushPromises()
    expect(mapStore.selectedId, 'la segunda seleccion no se registro')
      .toBe(second.id)
  })
})
