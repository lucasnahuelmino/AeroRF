import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useRFStore = defineStore('rf', () => {
  const results = ref([])
  const loading = ref(false)
  const error = ref(null)

  const calculateRF = async (payload) => {
    loading.value = true
    error.value = null
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
      return results.value
    } catch (err) {
      error.value = err.message
      throw err
    } finally {
      loading.value = false
    }
  }

  const getHarmonics = async (freq) => {
    try {
      const response = await fetch(`/api/v1/rf/harmonics/${freq}`)
      if (!response.ok) throw new Error('Failed to fetch harmonics')
      return await response.json()
    } catch (err) {
      error.value = err.message
      throw err
    }
  }

  return {
    results,
    loading,
    error,
    calculateRF,
    getHarmonics,
  }
})
