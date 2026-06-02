import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useSystemStore = defineStore('system', () => {
  const backendStatus = ref('desconocido')
  const openSkyStatus = ref('desconocido')
  const cursor = ref({ lat: null, lon: null })
  const flightCount = ref(0)

  return {
    backendStatus,
    openSkyStatus,
    cursor,
    flightCount,
  }
})
