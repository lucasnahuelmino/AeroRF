<template>
  <div class="bg-panel border border-borde rounded-2xl p-6">
    <h3 class="text-lg font-semibold mb-4 text-texto">{{ title }}</h3>
    <form @submit.prevent="handleSubmit" class="space-y-4">
      <div>
        <label class="block text-sm text-texto-tenue mb-2">Frecuencia (MHz)</label>
        <input
          v-model.number="formData.freq_mhz"
          type="number"
          step="0.001"
          placeholder="Ej: 119.0"
          required
          class="w-full px-3 py-2 bg-panel-hondo border border-borde rounded-lg text-texto placeholder:text-texto-invisible focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 font-mono"
        />
      </div>

      <div>
        <label class="block text-sm text-texto-tenue mb-2">Tipo de Señal</label>
        <select
          v-model="formData.signal_type"
          class="w-full px-3 py-2 bg-panel-hondo border border-borde rounded-lg text-texto focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
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
        <label class="block text-sm text-texto-tenue mb-2">Potencia (dBm, opcional)</label>
        <input
          v-model.number="formData.power_dbm"
          type="number"
          step="0.1"
          placeholder="Ej: 30"
          class="w-full px-3 py-2 bg-panel-hondo border border-borde rounded-lg text-texto placeholder:text-texto-invisible focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 font-mono"
        />
      </div>

      <div>
        <label class="block text-sm text-texto-tenue mb-2">Descripción (opcional)</label>
        <input
          v-model="formData.label"
          type="text"
          placeholder="Ej: FM Radio Local"
          class="w-full px-3 py-2 bg-panel-hondo border border-borde rounded-lg text-texto placeholder:text-texto-invisible focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
      </div>

      <div class="flex gap-2">
        <button
          type="submit"
          class="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold transition-colors text-white"
        >
          Agregar
        </button>
        <button
          v-if="showClear"
          @click="resetForm"
          type="button"
          class="px-4 py-2 bg-panel-alto hover:bg-on-ink-wash rounded-lg transition-colors text-texto"
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

const emit = defineEmits(['submit'])

const formData = ref({
  freq_mhz: '',
  signal_type: 'UNKNOWN',
  power_dbm: '',
  label: '',
})

const handleSubmit = () => {
  emit('submit', formData.value)
  resetForm()
}

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
