import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const api = vi.hoisted(() => ({
  systemStatus: vi.fn(),
  tracked: vi.fn(),
  sessions: vi.fn(),
  rfSummary: vi.fn(),
  rfEvents: vi.fn(),
  measurements: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  describeError: (error) => error?.message || 'Error',
  system: { status: api.systemStatus, config: vi.fn() },
  flights: {
    tracked: api.tracked,
    sessions: api.sessions,
    live: vi.fn(),
    search: vi.fn(),
    get: vi.fn(),
    track: vi.fn(),
    liveTrack: vi.fn(),
    all: vi.fn(),
    byAircraft: vi.fn(),
    flightsOf: vi.fn(),
    arrivals: vi.fn(),
    departures: vi.fn(),
    createSession: vi.fn(),
    startSession: vi.fn(),
    stopSession: vi.fn(),
    session: vi.fn(),
    deleteSession: vi.fn(),
    addToWatchlist: vi.fn(),
    untrack: vi.fn(),
    patchTracked: vi.fn(),
  },
  rf: { summary: api.rfSummary, events: api.rfEvents },
  mapObjects: { list: api.measurements },
  correlation: { rfAircraft: vi.fn(), forObject: vi.fn(), forAircraft: vi.fn() },
  layers: {},
  exporter: {},
  expedientes: {},
}))

import SituationView from '@/views/SituationView.vue'

describe('SituationView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.systemStatus.mockResolvedValue({
      status: 'ok',
      database: { connected: true },
      opensky: { configured: false, can_query_states: true },
    })
    api.tracked.mockResolvedValue({
      slots: [{ icao24: 'abc123', callsign: 'ARG123' }],
    })
    api.sessions.mockResolvedValue({
      sessions: [{ id: 8, icao24: 'abc123', status: 'recording' }],
    })
    api.rfSummary.mockResolvedValue({ events_total: 1 })
    api.rfEvents.mockResolvedValue({
      events: [{
        id: 3,
        name: 'Alerta de prueba',
        properties: { event: { frequency_mhz: 121.5 } },
      }],
    })
    api.measurements.mockResolvedValue({ count: 1, objects: [{ id: 4, name: 'Medición reciente' }] })
  })

  it('shows operational data returned by the real API contracts', async () => {
    const wrapper = mount(SituationView, { global: { plugins: [createPinia()] } })
    await flushPromises()

    expect(wrapper.text()).toContain('Disponible')
    expect(wrapper.text()).toContain('Conectada')
    expect(wrapper.text()).toContain('Modo anónimo disponible')
    expect(wrapper.text()).toContain('ARG123')
    expect(wrapper.findAll('.situation-card')[2].text()).toContain('1')
    expect(wrapper.findAll('.situation-card')[2].text()).toContain('sesiones grabando')
    expect(wrapper.text()).toContain('Alerta de prueba')
    expect(wrapper.text()).toContain('Medición reciente')
    expect(wrapper.text()).toContain('no expone un historial de actividad persistido')
    expect(api.measurements).toHaveBeenCalledWith({
      type: 'measurement',
      limit: 8,
      order_by: 'recent',
    })
    expect(api.rfEvents).toHaveBeenCalledWith({ limit: 8 })
    expect(api.sessions).toHaveBeenCalledWith({ status: 'recording', limit: 20 })
    wrapper.unmount()
  })

  it('shows section errors instead of presenting failed calls as empty data', async () => {
    api.rfEvents.mockRejectedValue(new Error('RF endpoint unavailable'))
    const wrapper = mount(SituationView, { global: { plugins: [createPinia()] } })
    await flushPromises()

    expect(wrapper.text()).toContain('RF endpoint unavailable')
    expect(wrapper.text()).not.toContain('No hay eventos RF registrados.')
    wrapper.unmount()
  })
})
