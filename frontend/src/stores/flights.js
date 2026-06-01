import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useFlightsStore = defineStore('flights', () => {
  const routes = ref([])
  const loading = ref(false)
  const error = ref(null)
  const selectedCallsign = ref(null)
  const query = ref({ origin: '', destination: '', callsign: '', source: 'sample' })

  const searchFlights = async (search) => {
    loading.value = true
    error.value = null
    query.value = {
      origin: search.origin || '',
      destination: search.destination || '',
      callsign: search.callsign || '',
      source: search.source || 'sample',
    }

    try {
      const params = new URLSearchParams()
      if (query.value.origin) params.append('origin', query.value.origin)
      if (query.value.destination) params.append('destination', query.value.destination)
      if (query.value.callsign) params.append('callsign', query.value.callsign)
      if (query.value.source) params.append('source', query.value.source)

      const response = await fetch(`/api/v1/flights/search?${params.toString()}`)
      if (!response.ok) throw new Error('No se pudo buscar vuelos')
      routes.value = await response.json()
      return routes.value
    } catch (err) {
      error.value = err.message || 'Error de red'
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    routes,
    loading,
    error,
    query,
    selectedCallsign,
    searchFlights,
  }
})
