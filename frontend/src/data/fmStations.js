const STORAGE_KEY = 'siari:fmStations'

export const DEFAULT_FM_STATIONS = [
  {
    id: 'fm-92-3',
    frequency_mhz: 92.3,
    name: 'FM Aeronáutica Central',
    lat: -34.8204,
    lon: -58.5389,
    power_dbm: 38,
    height_m: 120,
    description: 'Emisora de comunicaciones aeropuerto EZE',
  },
  {
    id: 'fm-100-7',
    frequency_mhz: 100.7,
    name: 'FM Radar NOR',
    lat: -31.3242,
    lon: -64.2101,
    power_dbm: 34,
    height_m: 110,
    description: 'Transmisor FM de apoyo aéreo en COR',
  },
]

export function loadFMStations() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_FM_STATIONS.slice()
    return JSON.parse(raw)
  } catch (e) {
    return DEFAULT_FM_STATIONS.slice()
  }
}

export function saveFMStations(list) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
}

export function addFMStation(station) {
  const list = loadFMStations()
  list.push(station)
  saveFMStations(list)
  return list
}

export function updateFMStation(id, patch) {
  const list = loadFMStations().map((item) => (item.id === id ? { ...item, ...patch } : item))
  saveFMStations(list)
  return list
}

export function removeFMStation(id) {
  const list = loadFMStations().filter((item) => item.id !== id)
  saveFMStations(list)
  return list
}
