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

  // ─── Historial propio de análisis (AeroRF 2.6 · Bloque 1) ─────────────────
  //
  // La calculadora ya no guarda en Expedientes: cada corrida que el operador
  // decide conservar vive en `POST /rf/analisis`, con identidad propia. No hay
  // segundo sistema de almacenamiento: el request y la response guardados son
  // los mismos objetos que alimentan las exportaciones.
  const historial = ref([])
  const historialLoading = ref(false)
  const historialError = ref(null)

  /** `detail` en español del backend si lo trae; si no, el mensaje dado. */
  const detalleDeError = async (response, porDefecto) => {
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string' && body.detail.trim()) return body.detail
    } catch {
      // Sin cuerpo legible: se usa el mensaje genérico.
    }
    return porDefecto
  }

  const cargarHistorial = async () => {
    historialLoading.value = true
    historialError.value = null
    try {
      const response = await fetch('/api/v1/rf/analisis')
      if (!response.ok) throw new Error('Failed to fetch')
      const lista = await response.json()
      historial.value = Array.isArray(lista) ? lista : []
    } catch {
      historialError.value =
        'No se pudo cargar el historial de análisis. Revisá que el backend esté levantado.'
    } finally {
      historialLoading.value = false
    }
  }

  const guardarAnalisis = async (modo) => {
    if (!lastRequest.value || !lastResponse.value) {
      throw new Error('No hay ningún cálculo para guardar.')
    }
    let response
    try {
      response = await fetch('/api/v1/rf/analisis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          modo,
          parametros: lastRequest.value,
          resultados: lastResponse.value,
        }),
      })
    } catch {
      throw new Error('No se pudo hablar con el backend. ¿Está levantado?')
    }
    if (!response.ok) {
      throw new Error(await detalleDeError(response, 'No se pudo guardar el análisis.'))
    }
    const creado = await response.json()
    historial.value = [creado, ...historial.value]
    return creado
  }

  const eliminarAnalisis = async (id) => {
    let response
    try {
      response = await fetch(`/api/v1/rf/analisis/${id}`, { method: 'DELETE' })
    } catch {
      throw new Error('No se pudo hablar con el backend. ¿Está levantado?')
    }
    if (!response.ok) {
      throw new Error(await detalleDeError(response, 'No se pudo eliminar el análisis.'))
    }
    historial.value = historial.value.filter((a) => a.id !== id)
  }

  /**
   * Restaura una corrida guardada en la pantalla: los resultados del motor
   * vuelven a la tabla sin recalcular, para que «ver» un análisis muestre lo
   * que se guardó y no una corrida nueva.
   */
  const loadRun = (parametros, resultados) => {
    lastRequest.value = JSON.parse(JSON.stringify(parametros))
    lastResponse.value = JSON.parse(JSON.stringify(resultados))
    results.value = Array.isArray(resultados?.matches) ? [...resultados.matches] : []
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
    historial,
    historialLoading,
    historialError,
    cargarHistorial,
    guardarAnalisis,
    eliminarAnalisis,
    loadRun,
  }
})
