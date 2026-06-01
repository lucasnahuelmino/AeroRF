import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useExpedientesStore = defineStore('expedientes', () => {
  const expedientes = ref([])
  const loading = ref(false)
  const error = ref(null)

  const fetchExpedientes = async () => {
    loading.value = true
    error.value = null
    try {
      const response = await fetch('/api/v1/expedientes')
      if (!response.ok) throw new Error('Failed to fetch')
      expedientes.value = await response.json()
    } catch (err) {
      error.value = err.message
    } finally {
      loading.value = false
    }
  }

  const createExpediente = async (data) => {
    try {
      const response = await fetch('/api/v1/expedientes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (!response.ok) throw new Error('Failed to create')
      const newExp = await response.json()
      expedientes.value.push(newExp)
      return newExp
    } catch (err) {
      error.value = err.message
      throw err
    }
  }

  const updateExpediente = async (id, data) => {
    try {
      const response = await fetch(`/api/v1/expedientes/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (!response.ok) throw new Error('Failed to update')
      const updated = await response.json()
      const idx = expedientes.value.findIndex((e) => e.id === id)
      if (idx >= 0) expedientes.value[idx] = updated
      return updated
    } catch (err) {
      error.value = err.message
      throw err
    }
  }

  const deleteExpediente = async (id) => {
    try {
      const response = await fetch(`/api/v1/expedientes/${id}`, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error('Failed to delete')
      expedientes.value = expedientes.value.filter((e) => e.id !== id)
    } catch (err) {
      error.value = err.message
      throw err
    }
  }

  return {
    expedientes,
    loading,
    error,
    fetchExpedientes,
    createExpediente,
    updateExpediente,
    deleteExpediente,
  }
})
