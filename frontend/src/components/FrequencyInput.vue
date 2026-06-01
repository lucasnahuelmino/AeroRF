<template>
  <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
    <h3 class="text-lg font-semibold mb-4">{{ title }}</h3>
    <form @submit.prevent="$emit('submit', formData)" class="space-y-4">
      <div>
        <label class="block text-sm text-gray-400 mb-1">Frecuencia (MHz)</label>
        <input
          v-model.number="formData.freq_mhz"
          type="number"
          step="0.001"
          placeholder="Ej: 119.0"
          required
          class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:border-primary"
        />
      </div>

      <div>
        <label class="block text-sm text-gray-400 mb-1">Tipo de Señal</label>
        <select
          v-model="formData.signal_type"
          class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 focus:outline-none focus:border-primary"
        >
          <option value="UNKNOWN">Desconocido</option>
          <option value="FM">FM</option>
          <option value="TV_VHF">TV VHF</option>
          <option value="TV_UHF">TV UHF</option>
          <option value="VHF">VHF</option>
          <option value="UHF">UHF</option>
          <option value="CELLULAR">Celular</option>
          <option value="LINK">Link</option>
        </select>
      </div>

      <div>
        <label class="block text-sm text-gray-400 mb-1">Potencia (dBm, opcional)</label>
        <input
          v-model.number="formData.power_dbm"
          type="number"
          step="0.1"
          placeholder="Ej: 30"
          class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:border-primary"
        />
      </div>

      <div>
        <label class="block text-sm text-gray-400 mb-1">Descripción (opcional)</label>
        <input
          v-model="formData.label"
          type="text"
          placeholder="Ej: FM Radio Local"
          class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:border-primary"
        />
      </div>

      <div class="flex gap-2">
        <button
          type="submit"
          class="flex-1 px-4 py-2 bg-primary hover:bg-blue-600 rounded-lg font-semibold transition-colors"
        >
          Agregar
        </button>
        <button
          v-if="showClear"
          @click="resetForm"
          type="button"
          class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
        >
          Limpiar
        </button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  title: String,
  showClear: {
    type: Boolean,
    default: true,
  },
})

defineEmits(['submit'])

const formData = ref({
  freq_mhz: '',
  signal_type: 'UNKNOWN',
  power_dbm: '',
  label: '',
})

const resetForm = () => {
  formData.value = {
    freq_mhz: '',
    signal_type: 'UNKNOWN',
    power_dbm: '',
    label: '',
  }
}

defineExpose({ formData, resetForm })
</script>
