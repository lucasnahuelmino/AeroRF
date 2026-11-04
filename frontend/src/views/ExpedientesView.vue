<template>
  <div class="page-doc">
    <div class="flex justify-between items-center mb-6">
      <h1 class="page-doc-title">📋 Expedientes</h1>
      <button
        @click="showNewForm = true"
        class="px-4 py-2 bg-sky-600 hover:bg-blue-600 rounded-lg transition-colors font-semibold"
      >
        ✚ Nuevo Expediente
      </button>
    </div>

    <!-- Filtros -->
    <FilterPanel @filter="applyFilters" />

    <!-- Modal crear expediente -->
    <div v-if="showNewForm" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-panel-alto rounded-lg p-6 w-full max-w-md border border-borde-fuerte max-h-96 overflow-y-auto">
        <h2 class="text-xl font-semibold mb-4">Crear Expediente</h2>
        <form @submit.prevent="createNewExpediente" class="space-y-4">
          <input
            v-model="newForm.numero_expediente"
            placeholder="Número de expediente"
            class="w-full px-3 py-2 bg-panel-hondo border border-borde-fuerte rounded text-texto placeholder:text-texto-invisible focus:outline-none focus:border-sky-600"
          />
          <input
            v-model.number="newForm.freq_mhz"
            type="number"
            placeholder="Frecuencia (MHz)"
            step="0.001"
            class="w-full px-3 py-2 bg-panel-hondo border border-borde-fuerte rounded text-texto placeholder:text-texto-invisible focus:outline-none focus:border-sky-600"
          />
          <input
            v-model="newForm.aeropuerto"
            placeholder="Aeropuerto"
            class="w-full px-3 py-2 bg-panel-hondo border border-borde-fuerte rounded text-texto placeholder:text-texto-invisible focus:outline-none focus:border-sky-600"
          />
          <select
            v-model="newForm.severidad"
            class="w-full px-3 py-2 bg-panel-hondo border border-borde-fuerte rounded text-texto focus:outline-none focus:border-sky-600"
          >
            <option value="baja">Baja</option>
            <option value="media" selected>Media</option>
            <option value="alta">Alta</option>
            <option value="crítica">Crítica</option>
          </select>
          <textarea
            v-model="newForm.observaciones"
            placeholder="Observaciones"
            rows="3"
            class="w-full px-3 py-2 bg-panel-hondo border border-borde-fuerte rounded text-texto placeholder:text-texto-invisible focus:outline-none focus:border-sky-600"
          ></textarea>
          <div class="flex gap-2">
            <button
              type="submit"
              class="flex-1 px-4 py-2 bg-sky-600 hover:bg-blue-600 rounded-lg font-semibold transition-colors"
            >
              Crear
            </button>
            <button
              @click="showNewForm = false"
              type="button"
              class="flex-1 px-4 py-2 bg-panel-alto hover:bg-on-ink-wash rounded-lg font-semibold transition-colors"
            >
              Cancelar
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Tabla expedientes -->
    <DataTable
      :columns="['Expediente', 'Frecuencia', 'Aeropuerto', 'Estado']"
      :rows="filteredExpedientes"
      :actions="[
        { label: '👁️ Ver', event: 'view', class: 'px-3 py-1 bg-blue-900 hover:bg-blue-800 rounded text-xs transition-colors' },
        { label: '✎ Edit', event: 'edit', class: 'px-3 py-1 bg-yellow-900 hover:bg-yellow-800 rounded text-xs transition-colors' },
        { label: '🗑️ Del', event: 'delete', class: 'px-3 py-1 bg-red-900 hover:bg-red-800 rounded text-xs transition-colors' },
      ]"
      @view="goToExpediente"
      @delete="deleteExp"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useExpedientesStore } from '../stores/expedientes'
import DataTable from '../components/DataTable.vue'
import FilterPanel from '../components/FilterPanel.vue'

const router = useRouter()
const expedientesStore = useExpedientesStore()

const showNewForm = ref(false)
const filters = ref({})
const newForm = ref({
  numero_expediente: '',
  freq_mhz: '',
  aeropuerto: '',
  observaciones: '',
  severidad: 'media',
  estado: 'abierto',
})

const filteredExpedientes = computed(() => {
  let result = (expedientesStore.expedientes || []).map(exp => ({
    'Expediente': exp.numero_expediente || 'N/A',
    'Frecuencia': exp.freq_mhz?.toFixed(3) || 'N/A',
    'Aeropuerto': exp.aeropuerto || 'N/A',
    'Estado': exp.estado || 'abierto',
    id: exp.id,
  }))

  if (filters.value.estado) {
    result = result.filter(e => e.Estado === filters.value.estado)
  }
  if (filters.value.severidad) {
    result = result.filter(e => expedientesStore.expedientes.find(x => x.id === e.id)?.severidad === filters.value.severidad)
  }
  if (filters.value.search) {
    const search = filters.value.search.toLowerCase()
    result = result.filter(e => 
      e.Expediente.toLowerCase().includes(search) ||
      e.Frecuencia.includes(search)
    )
  }

  return result
})

const applyFilters = (newFilters) => {
  filters.value = newFilters
}

const createNewExpediente = async () => {
  try {
    await expedientesStore.createExpediente({
      ...newForm.value,
    })
    showNewForm.value = false
    newForm.value = {
      numero_expediente: '',
      freq_mhz: '',
      aeropuerto: '',
      observaciones: '',
      severidad: 'media',
      estado: 'abierto',
    }
  } catch (err) {
    alert('Error creando expediente: ' + err.message)
  }
}

const deleteExp = async (row) => {
  if (!confirm(`¿Eliminar expediente ${row.Expediente}?`)) return
  try {
    await expedientesStore.deleteExpediente(row.id)
  } catch (err) {
    alert('Error eliminando expediente')
  }
}

const goToExpediente = (row) => {
  router.push(`/expedientes/${row.id}`)
}

onMounted(() => {
  expedientesStore.fetchExpedientes()
})
</script>
