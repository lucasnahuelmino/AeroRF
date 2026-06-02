export const AIRPORTS = [
  {
    icao: 'SAEZ',
    iata: 'EZE',
    name: 'Ministro Pistarini',
    lat: -34.8186,
    lon: -58.5358,
    elev: 24,
  },
  {
    icao: 'SACO',
    iata: 'COR',
    name: 'Ingeniero Ambrosio Taravella',
    lat: -31.3239,
    lon: -64.2088,
    elev: 144,
  },
  {
    icao: 'SAME',
    iata: 'MDZ',
    name: 'Governor Francisco Gabrielli',
    lat: -32.8975,
    lon: -68.8268,
    elev: 2361,
  },
  {
    icao: 'SABE',
    iata: 'AEP',
    name: 'Aeroparque Jorge Newbery',
    lat: -34.5599,
    lon: -58.4154,
    elev: 21,
  },
  {
    icao: 'SAAR',
    iata: 'ROS',
    name: 'Islas Malvinas',
    lat: -32.9039,
    lon: -60.7842,
    elev: 30,
  },
]

const STORAGE_KEY = 'siari:airports'

export function loadAirports() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return AIRPORTS.slice()
    return JSON.parse(raw)
  } catch (e) {
    return AIRPORTS.slice()
  }
}

export function saveAirports(list) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
}

export function addAirport(airport) {
  const list = loadAirports()
  list.push(airport)
  saveAirports(list)
  return list
}

export function updateAirport(code, patch) {
  const list = loadAirports().map((a) => (a.code === code ? { ...a, ...patch } : a))
  saveAirports(list)
  return list
}

export function removeAirport(code) {
  const list = loadAirports().filter((a) => a.code !== code)
  saveAirports(list)
  return list
}
