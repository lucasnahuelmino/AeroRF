<template>
  <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
    <div class="flex gap-4 flex-wrap">
      <div>
        <label class="block text-sm text-gray-400 mb-2">Estado</label>
        <select
          v-model="filters.estado"
          @change="$emit('filter', filters)"
          class="px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 focus:outline-none focus:border-primary"
        >
          <option value="">Todos</option>
          <option value="abierto">Abierto</option>
          <option value="investigacion">En Investigación</option>
          <option value="resuelto">Resuelto</option>
          <option value="cerrado">Cerrado</option>
        </select>
      </div>

      <div>
        <label class="block text-sm text-gray-400 mb-2">Severidad</label>
        <select
          v-model="filters.severidad"
          @change="$emit('filter', filters)"
          class="px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 focus:outline-none focus:border-primary"
        >
          <option value="">Todas</option>
          <option value="baja">Baja</option>
          <option value="media">Media</option>
          <option value="alta">Alta</option>
          <option value="crítica">Crítica</option>
        </select>
      </div>

      <div>
        <label class="block text-sm text-gray-400 mb-2">Búsqueda</label>
        <input
          v-model="filters.search"
          @input="$emit('filter', filters)"
          type="text"
          placeholder="Número o frecuencia..."
          class="px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:border-primary"
        />
      </div>

      <div class="flex items-end">
        <button
          @click="resetFilters"
          class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm transition-colors"
        >
          ⟳ Limpiar
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineEmits(['filter'])

const filters = ref({
  estado: '',
  severidad: '',
  search: '',
})

const resetFilters = () => {
  filters.value = {
    estado: '',
    severidad: '',
    search: '',
  }
}
</script>
