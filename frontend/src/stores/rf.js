import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useRFStore = defineStore('rf', () => {
  const results = ref([])
  const loading = ref(false)
  const error = ref(null)

  // Fase 4 (AeroRF 2.5): la última corrida queda en memoria — solicitud y
  // respuesta completas — para poder exportarla en JSON sin recalcular.
  // Se guarda una copia del pedido en el momento del fetch: si se exporta una
  // hora después, tiene que salir lo que se mandó, no el formulario de hoy.
  const lastRequest = ref(null)
  const lastResponse = ref(null)

  const calculateRF = async (payload) => {
    loading.value = true
    error.value = null
    lastRequest.value = JSON.parse(JSON.stringify(payload))
    try {
      const response = await fetch('/api/v1/rf/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error('Failed to calculate')
      const data = await response.json()
      // API returns an object with `matches`; store the array of matches for the UI
      results.value = data.matches || []
      lastResponse.value = data
      return results.value
    } catch (err) {
      error.value = err.message
      lastResponse.value = null
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Tabla de armónicos del backend (`GET /rf/harmonics/{freq}`).
   * `max_order` lo pide la vista: el modo Armónicos mira órdenes 2 a 4.
   * El backend calcula; el frontend sólo resta contra la referencia para mostrar
   * la diferencia en kHz.
   */
  const getHarmonics = async (freq, maxOrder = 6) => {
    try {
      const response = await fetch(`/api/v1/rf/harmonics/${freq}?max_order=${maxOrder}`)
      if (!response.ok) throw new Error('Failed to fetch harmonics')
      return await response.json()
    } catch (err) {
      error.value = err.message
      throw err
    }
  }

  /** «Limpiar cálculo»: vacía resultados y el rastro de la última corrida. */
  const clearCalculation = () => {
    results.value = []
    lastRequest.value = null
    lastResponse.value = null
    error.value = null
  }

  return {
    results,
    loading,
    error,
    lastRequest,
    lastResponse,
    calculateRF,
    getHarmonics,
    clearCalculation,
  }
})
