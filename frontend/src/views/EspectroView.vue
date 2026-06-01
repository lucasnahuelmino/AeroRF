<template>
  <div class="space-y-6">
    <h1 class="text-3xl font-bold">📊 Análisis Espectral</h1>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div class="lg:col-span-2 bg-gray-800 border border-gray-700 rounded-lg p-6">
        <h2 class="text-lg font-semibold mb-4">Espectro</h2>
        <div id="spectrum" style="height: 300px; background-color: #1f2937" class="rounded flex items-center justify-center text-gray-500">
          Gráfico de espectro (Plotly)
        </div>
      </div>

      <div class="bg-gray-800 border border-gray-700 rounded-lg p-6">
        <h2 class="text-lg font-semibold mb-4">Cargar Datos</h2>
        <div class="space-y-3">
          <input
            type="file"
            accept=".csv,.txt"
            class="block w-full text-sm text-gray-400 file:mr-4 file:px-3 file:py-2 file:rounded file:border-0 file:bg-primary file:text-white cursor-pointer"
          />
          <textarea
            placeholder="O pega CSV aquí..."
            rows="6"
            class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:border-primary text-xs"
          ></textarea>
          <button class="w-full px-3 py-2 bg-primary hover:bg-blue-600 rounded transition-colors text-sm font-semibold">
            Procesar
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
</script>
