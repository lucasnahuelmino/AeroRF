import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  updateObject: vi.fn(),
  upsert: vi.fn(),
  select: vi.fn(),
  fitObject: vi.fn(),
  requestWorkspaceContext: vi.fn(),
  ask: vi.fn(),
  deleteObject: vi.fn(),
  duplicateObject: vi.fn(),
  mapStore: null,
  systemStore: null,
}))

vi.mock('@/api/client', () => ({
  describeError: (error) => String(error?.message || error),
  mapObjects: { list: mocks.list },
}))

vi.mock('@/stores/map', () => ({
  typeName: (type) => type,
  useMapStore: () => mocks.mapStore,
}))

vi.mock('@/stores/system', () => ({
  useSystemStore: () => mocks.systemStore,
}))

import ObjectsPanel from '@/components/gis/ObjectsPanel.vue'

const HIDDEN_OBJECT = {
  id: 41,
  name: 'Fuente oculta',
  type: 'rf_source',
  layer: 'rf_sources',
  layer_name: 'Fuentes RF',
  category: 'Fuente interferente',
  source: 'user',
  status: 'Activo',
  visible: false,
  color: '#f97316',
}

describe('GIS object administrator', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.list.mockResolvedValue({
      count: 1,
      total: 1,
      objects: [{ ...HIDDEN_OBJECT }],
    })
    mocks.updateObject.mockImplementation(async (id, patch) => ({
      ...HIDDEN_OBJECT,
      ...patch,
      id,
    }))
    mocks.mapStore = {
      layers: [{ key: 'rf_sources', name: 'Fuentes RF' }],
      objects: [{ ...HIDDEN_OBJECT }],
      byId: new Map([[HIDDEN_OBJECT.id, { ...HIDDEN_OBJECT }]]),
      vocabulary: {
        object_types: ['rf_source'],
        states: ['Activo'],
        provenance: ['user'],
        provenance_labels: { user: 'Ingresado por operador' },
      },
      error: null,
      engine: { fitObject: mocks.fitObject },
      upsert: mocks.upsert,
      select: mocks.select,
      updateObject: mocks.updateObject,
      deleteObject: mocks.deleteObject,
      duplicateObject: mocks.duplicateObject,
    }
    mocks.systemStore = {
      requestWorkspaceContext: mocks.requestWorkspaceContext,
      ask: mocks.ask,
    }
  })

  it('lists hidden objects without requiring them to be rendered on the map', async () => {
    const wrapper = mount(ObjectsPanel)
    await flushPromises()

    expect(mocks.list).toHaveBeenCalledWith({
      limit: 50,
      offset: 0,
      format: 'leaflet',
    })
    expect(wrapper.text()).toContain('Fuente oculta')
    expect(wrapper.text()).toContain('Oculto')
    expect(wrapper.get('[aria-label="Mostrar objeto 41"]').exists()).toBe(true)
  })

  it('filters hidden records via the API and persists visibility changes', async () => {
    const wrapper = mount(ObjectsPanel)
    await flushPromises()
    mocks.list.mockClear()

    await wrapper.get('[aria-label="Filtrar por visibilidad"]').setValue('false')
    await flushPromises()
    expect(mocks.list).toHaveBeenCalledWith(
      expect.objectContaining({ visible: false, offset: 0 }),
    )

    await wrapper.get('[aria-label="Mostrar objeto 41"]').trigger('click')
    await flushPromises()
    expect(mocks.updateObject).toHaveBeenCalledWith(41, { visible: true })
  })

  it('opens the selected object in the contextual inspector', async () => {
    const wrapper = mount(ObjectsPanel)
    await flushPromises()

    await wrapper.get('[title="Seleccionar Fuente oculta"]').trigger('click')

    expect(mocks.select).toHaveBeenCalledWith(41)
    expect(mocks.requestWorkspaceContext).toHaveBeenCalledWith({ type: 'object', id: 41 })
  })
})
