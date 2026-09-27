<template>
  <div class="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
    <table class="w-full">
      <thead class="bg-slate-900 border-b border-slate-700">
        <tr>
          <th v-for="col in columns" :key="col" class="px-4 py-3 text-left text-sm font-semibold">
            {{ col }}
          </th>
          <th v-if="actions" class="px-4 py-3 text-left text-sm font-semibold">Acciones</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, idx) in rows"
          :key="idx"
          class="border-b border-slate-700 hover:bg-slate-700/50 transition-colors"
        >
          <td v-for="(col, colIdx) in columns" :key="colIdx" class="px-4 py-3">
            <template v-if="col === 'Frecuencia'">
              <span class="font-mono text-sky-600">{{ row[col] }} MHz</span>
            </template>
            <template v-else-if="col === 'Score' || col === 'Proximidad'">
              <div class="flex items-center gap-2">
                <div class="h-2 bg-slate-700 rounded-full w-16">
                  <div
                    class="h-full bg-success rounded-full transition-all"
                    :style="{ width: row[col] + '%' }"
                  ></div>
                </div>
                <span class="text-sm font-semibold">{{ row[col] }}%</span>
              </div>
            </template>
            <template v-else-if="col === 'Estado'">
              <span class="text-xs px-2 py-1 rounded-full" :class="statusClass(row[col])">
                {{ row[col] }}
              </span>
            </template>
            <template v-else>
              {{ row[col] }}
            </template>
          </td>
          <td v-if="actions" class="px-4 py-3 space-x-2">
            <button
              v-for="(action, idx) in actions"
              :key="idx"
              @click="$emit(action.event, row)"
              :class="action.class || 'px-2 py-1 bg-blue-900 hover:bg-blue-800 rounded text-xs transition-colors'"
            >
              {{ action.label }}
            </button>
          </td>
        </tr>
        <tr v-if="rows.length === 0">
          <td :colspan="columns.length + (actions ? 1 : 0)" class="px-4 py-8 text-center text-slate-400">
            No hay datos disponibles
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
defineProps({
  columns: {
    type: Array,
    required: true,
  },
  rows: {
    type: Array,
    required: true,
  },
  actions: Array,
})

defineEmits(['view', 'edit', 'delete', 'analyze'])

const statusClass = (status) => {
  const classes = {
    abierto: 'bg-blue-900 text-blue-200',
    investigacion: 'bg-yellow-900 text-yellow-200',
    resuelto: 'bg-green-900 text-green-200',
    cerrado: 'bg-slate-700 text-slate-300',
    'En progreso': 'bg-yellow-900 text-yellow-200',
    'Completado': 'bg-green-900 text-green-200',
  }
  return classes[status] || 'bg-slate-700 text-slate-300'
}
</script>
