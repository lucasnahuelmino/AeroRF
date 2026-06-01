const STORAGE_KEY = 'siari:points'

export function loadPoints() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw)
  } catch (e) {
    return []
  }
}

export function savePoints(list) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
}

export function addPoint(pt) {
  const list = loadPoints()
  list.push(pt)
  savePoints(list)
  return list
}

export function updatePoint(id, patch) {
  const list = loadPoints().map((p) => (p.id === id ? { ...p, ...patch } : p))
  savePoints(list)
  return list
}

export function removePoint(id) {
  const list = loadPoints().filter((p) => p.id !== id)
  savePoints(list)
  return list
}
