const STORAGE_KEY = 'siari:rfEvents'

export const DEFAULT_RF_EVENTS = [
  {
    id: 'rf-1',
    fecha: new Date().toISOString(),
    frecuencia_mhz: 118.0,
    nivel_dbm: -55,
    lat: -34.8186,
    lon: -58.5358,
    expediente: 'EXP-001',
    descripcion: 'Captura de señal en pista principal',
    notas: 'Posible interferencia local',
  },
]

export function loadRfEvents() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_RF_EVENTS.slice()
    return JSON.parse(raw)
  } catch (e) {
    return DEFAULT_RF_EVENTS.slice()
  }
}

export function saveRfEvents(list) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
}

export function addRfEvent(event) {
  const list = loadRfEvents()
  list.push(event)
  saveRfEvents(list)
  return list
}

export function updateRfEvent(id, patch) {
  const list = loadRfEvents().map((item) => (item.id === id ? { ...item, ...patch } : item))
  saveRfEvents(list)
  return list
}

export function removeRfEvent(id) {
  const list = loadRfEvents().filter((item) => item.id !== id)
  saveRfEvents(list)
  return list
}
