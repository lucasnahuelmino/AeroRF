<template>
  <div class="flex h-full flex-col">
    <header class="border-b border-borde p-3">
      <div class="mb-2 flex items-center justify-between">
        <h2 class="text-xs font-semibold uppercase tracking-widest text-texto-medio">
          Objetos GIS
        </h2>
        <button class="gis-mini-btn" :disabled="loading" @click="loadPage(page)">
          Actualizar
        </button>
      </div>

      <form class="space-y-2" @submit.prevent="loadPage(1)">
        <label class="sr-only" for="objects-search">Buscar objeto por nombre o ID</label>
        <div class="flex gap-1">
          <input
            id="objects-search"
            v-model="filters.search"
            class="min-w-0 flex-1 rounded border border-borde bg-panel-hondo px-2 py-1.5 text-xs text-texto"
            placeholder="Nombre o ID"
          />
          <button class="gis-mini-btn" type="submit">Buscar</button>
        </div>

        <div class="grid grid-cols-2 gap-1">
          <select v-model="filters.type" aria-label="Filtrar por tipo" @change="loadPage(1)">
            <option value="">Todos los tipos</option>
            <option v-for="type in objectTypes" :key="type" :value="type">
              {{ typeName(type) }}
            </option>
          </select>
          <select v-model="filters.layer_key" aria-label="Filtrar por capa" @change="loadPage(1)">
            <option value="">Todas las capas</option>
            <option value="__without_layer__">Sin capa</option>
            <option v-for="layer in mapStore.layers" :key="layer.key" :value="layer.key">
              {{ layer.name }}
            </option>
          </select>
          <input
            v-model="filters.category"
            aria-label="Filtrar por categoría"
            list="object-categories"
            placeholder="Categoría"
            @change="loadPage(1)"
          />
          <datalist id="object-categories">
            <option v-for="category in categories" :key="category" :value="category" />
          </datalist>
          <select v-model="filters.source" aria-label="Filtrar por origen" @change="loadPage(1)">
            <option value="">Todos los orígenes</option>
            <option v-for="source in sources" :key="source" :value="source">
              {{ provenanceLabel(source) }}
            </option>
          </select>
          <select v-model="filters.status" aria-label="Filtrar por estado" @change="loadPage(1)">
            <option value="">Todos los estados</option>
            <option v-for="state in states" :key="state" :value="state">{{ state }}</option>
          </select>
          <select
            v-model="filters.visible"
            class="col-span-2"
            aria-label="Filtrar por visibilidad"
            @change="loadPage(1)"
          >
            <option value="">Visibles y ocultos</option>
            <option value="true">Solo visibles</option>
            <option value="false">Solo ocultos</option>
          </select>
        </div>
      </form>

      <p class="mt-2 text-[10px] text-texto-tenue" aria-live="polite">
        {{ total }} objeto{{ total === 1 ? '' : 's' }} · página {{ page }} ·
        {{ filters.visible === 'false' ? 'incluye ocultos' : 'visibilidad independiente' }}
      </p>
      <div v-if="objects.length" class="mt-2 flex items-center justify-between gap-2">
        <label class="flex items-center gap-1 text-[10px] text-texto-tenue">
          <input
            type="checkbox"
            :checked="allPageSelected"
            aria-label="Seleccionar todos los objetos de esta página"
            @change="selectPage($event.target.checked)"
          />
          Seleccionar página
        </label>
        <div v-if="selectedObjects.length" class="flex gap-1">
          <button class="gis-mini-btn" @click="setSelectedVisibility(true)">Mostrar</button>
          <button class="gis-mini-btn" @click="setSelectedVisibility(false)">Ocultar</button>
          <button class="gis-mini-btn" @click="deleteSelected">Eliminar</button>
        </div>
      </div>
    </header>

    <p v-if="error" class="m-2 rounded border border-red-500/40 bg-red-950/30 p-2 text-xs text-red-200" role="alert">
      {{ error }}
    </p>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="loading && !objects.length" class="p-4 text-xs text-texto-tenue">
        Cargando objetos…
      </p>
      <p v-else-if="!objects.length" class="p-4 text-xs text-texto-tenue">
        No hay objetos que coincidan con los filtros.
      </p>
      <ul v-else class="divide-y divide-borde">
        <li v-for="object in objects" :key="object.id" class="p-2.5">
          <div class="flex items-start gap-2">
            <span
              class="mt-1 h-2.5 w-2.5 flex-none rounded-full"
              :style="{ background: object.color || 'var(--texto-tenue)' }"
              aria-hidden="true"
            />
            <div class="min-w-0 flex-1">
              <button
                class="block max-w-full truncate text-left text-xs font-medium text-texto hover:text-sky-300"
                :title="`Seleccionar ${object.name || typeName(object.type)}`"
                @click="selectObject(object)"
              >
                {{ object.name || typeName(object.type) }}
              </button>
              <p class="mt-0.5 truncate font-mono text-[10px] text-texto-tenue">
                ID {{ object.id }} · {{ typeName(object.type) }}
              </p>
              <p class="truncate text-[10px] text-texto-tenue">
                {{ object.layer_name || object.layer || 'Sin capa' }} ·
                {{ object.status || 'Estado desconocido' }}
                <span v-if="object.category"> · {{ object.category }}</span>
                <span v-if="object.source || object.provenance">
                  · {{ provenanceLabel(object.source || object.provenance) }}
                </span>
              </p>
              <p
                v-if="!object.layer || !object.layer_name"
                class="mt-1 text-[10px] text-amber-300"
              >
                Verificar asignación de capa
              </p>
              <div class="mt-2 flex flex-wrap gap-1">
                <label class="sr-only" :for="`object-${object.id}-selected`">
                  Seleccionar objeto {{ object.id }}
                </label>
                <input
                  :id="`object-${object.id}-selected`"
                  type="checkbox"
                  class="float-right"
                  :checked="selectedIds.has(object.id)"
                  @change="setObjectSelected(object.id, $event.target.checked)"
                />
                <button class="gis-mini-btn" @click="centerObject(object)">Centrar</button>
                <button class="gis-mini-btn" @click="editObject(object)">Editar</button>
                <button
                  class="gis-mini-btn"
                  :aria-label="`${object.visible === false ? 'Mostrar' : 'Ocultar'} objeto ${object.id}`"
                  @click="toggleVisibility(object)"
                >
                  {{ object.visible === false ? 'Mostrar' : 'Ocultar' }}
                </button>
                <button
                  class="gis-mini-btn"
                  :disabled="object.locked"
                  :title="object.locked ? 'Desbloquee el objeto antes de eliminarlo' : 'Eliminar objeto'"
                  @click="deleteObject(object)"
                >
                  Eliminar
                </button>
              </div>
            </div>
            <span
              class="flex-none rounded border border-borde px-1 py-0.5 text-[9px]"
              :class="object.visible === false ? 'text-texto-tenue' : 'text-emerald-300'"
            >
              {{ object.visible === false ? 'Oculto' : 'Visible' }}
            </span>
          </div>
        </li>
      </ul>
    </div>

    <footer class="flex items-center justify-between border-t border-borde p-2">
      <button class="gis-mini-btn" :disabled="loading || page <= 1" @click="loadPage(page - 1)">
        Anterior
      </button>
      <span class="font-mono text-[10px] text-texto-tenue">{{ page }} / {{ pageCount || 1 }}</span>
      <button class="gis-mini-btn" :disabled="loading || page >= pageCount" @click="loadPage(page + 1)">
        Siguiente
      </button>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { describeError, mapObjects } from '@/api/client'
import { typeName, useMapStore } from '@/stores/map'
import { useSystemStore } from '@/stores/system'

const pageSize = 50
const mapStore = useMapStore()
const systemStore = useSystemStore()

const filters = reactive({
  search: '',
  type: '',
  layer_key: '',
  category: '',
  source: '',
  status: '',
  visible: '',
})
const objects = ref([])
const selectedIds = ref(new Set())
const loading = ref(false)
const error = ref('')
const page = ref(1)
const total = ref(0)

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const displayedObjects = computed(() =>
  objects.value.map((object) => mapStore.byId.get(object.id) || object),
)
const selectedObjects = computed(() =>
  displayedObjects.value.filter((object) => selectedIds.value.has(object.id)),
)
const allPageSelected = computed(() =>
  displayedObjects.value.length > 0 &&
  displayedObjects.value.every((object) => selectedIds.value.has(object.id)),
)
const objectTypes = computed(() =>
  mapStore.vocabulary.object_types?.length
    ? mapStore.vocabulary.object_types
    : [...new Set(mapStore.objects.map((object) => object.type))].sort(),
)
const states = computed(() =>
  mapStore.vocabulary.states?.length
    ? mapStore.vocabulary.states
    : [...new Set(mapStore.objects.map((object) => object.status).filter(Boolean))].sort(),
)
const sources = computed(() =>
  mapStore.vocabulary.provenance?.length
    ? mapStore.vocabulary.provenance
    : [...new Set(mapStore.objects.map((object) => object.source).filter(Boolean))].sort(),
)
const categories = computed(() =>
  [...new Set(mapStore.objects.map((object) => object.category).filter(Boolean))].sort(),
)

async function loadPage(nextPage = 1) {
  loading.value = true
  error.value = ''
  try {
    const params = {
      limit: pageSize,
      offset: (nextPage - 1) * pageSize,
      format: 'leaflet',
    }
    for (const [key, value] of Object.entries(filters)) {
      if (value !== '') params[key] = value
    }
    if (filters.layer_key === '__without_layer__') {
      delete params.layer_key
      params.layer_missing = true
    }
    if (filters.visible !== '') params.visible = filters.visible === 'true'

    const response = await mapObjects.list(params)
    objects.value = response.objects || []
    total.value = response.total ?? response.count ?? 0
    page.value = nextPage
    selectedIds.value = new Set(
      [...selectedIds.value].filter((id) => objects.value.some((object) => object.id === id)),
    )
  } catch (requestError) {
    error.value = describeError(requestError)
  } finally {
    loading.value = false
  }
}

function selectObject(object) {
  mapStore.upsert(object)
  mapStore.select(object.id)
  systemStore.requestWorkspaceContext({ type: 'object', id: object.id })
}

function centerObject(object) {
  mapStore.upsert(object)
  mapStore.select(object.id)
  mapStore.engine?.fitObject(object)
  systemStore.requestWorkspaceContext({ type: 'object', id: object.id })
}

function editObject(object) {
  selectObject(object)
}

async function toggleVisibility(object) {
  const updated = await mapStore.updateObject(object.id, { visible: object.visible === false })
  if (!updated) {
    error.value = mapStore.error || 'No se pudo actualizar la visibilidad.'
    return
  }
  replaceObject(updated)
}

async function deleteObject(object) {
  const name = object.name || typeName(object.type)
  const confirmed = await systemStore.ask({
    title: 'Eliminar objeto',
    message: `Se eliminará «${name}» (ID ${object.id}). Esta acción no se puede deshacer.`,
    confirmLabel: 'Eliminar',
    danger: true,
  })
  if (!confirmed) return

  const deleted = await mapStore.deleteObject(object.id)
  if (!deleted) {
    error.value = mapStore.error || 'No se pudo eliminar el objeto.'
    return
  }
  objects.value = objects.value.filter((item) => item.id !== object.id)
  total.value = Math.max(0, total.value - 1)
  if (!objects.value.length && page.value > 1) await loadPage(page.value - 1)
}

function setObjectSelected(id, selected) {
  const next = new Set(selectedIds.value)
  if (selected) next.add(id)
  else next.delete(id)
  selectedIds.value = next
}

function selectPage(selected) {
  const next = new Set(selectedIds.value)
  displayedObjects.value.forEach((object) => {
    if (selected) next.add(object.id)
    else next.delete(object.id)
  })
  selectedIds.value = next
}

async function setSelectedVisibility(visible) {
  const failures = []
  for (const object of selectedObjects.value) {
    if (object.visible === visible) continue
    const updated = await mapStore.updateObject(object.id, { visible })
    if (updated) replaceObject(updated)
    else failures.push(`${object.id}: ${mapStore.error || 'error desconocido'}`)
  }
  if (failures.length) {
    error.value = `No se pudieron actualizar ${failures.length} objetos: ${failures.join('; ')}`
  }
}

async function deleteSelected() {
  const selected = selectedObjects.value
  const names = selected.map((object) => `${object.name || typeName(object.type)} (ID ${object.id})`)
  const confirmed = await systemStore.ask({
    title: 'Eliminar objetos seleccionados',
    message: `Se eliminarán ${selected.length} objetos:\n${names.join('\n')}\n\nEsta acción no se puede deshacer.`,
    confirmLabel: 'Eliminar seleccionados',
    danger: true,
  })
  if (!confirmed) return

  const deletedIds = []
  const failures = []
  for (const object of selected) {
    if (await mapStore.deleteObject(object.id)) deletedIds.push(object.id)
    else failures.push(`${object.id}: ${mapStore.error || 'error desconocido'}`)
  }
  objects.value = objects.value.filter((object) => !deletedIds.includes(object.id))
  total.value = Math.max(0, total.value - deletedIds.length)
  selectedIds.value = new Set([...selectedIds.value].filter((id) => !deletedIds.includes(id)))
  if (failures.length) {
    error.value = `No se pudieron eliminar ${failures.length} objetos: ${failures.join('; ')}`
  } else if (!objects.value.length && page.value > 1) {
    await loadPage(page.value - 1)
  }
}

function replaceObject(updated) {
  const index = objects.value.findIndex((object) => object.id === updated.id)
  if (index >= 0) objects.value.splice(index, 1, updated)
}

function provenanceLabel(source) {
  return mapStore.vocabulary.provenance_labels?.[source] || source
}

onMounted(() => {
  loadPage()
})
</script>

<style scoped>
select,
input[list] {
  min-width: 0;
  border: 1px solid var(--borde);
  border-radius: 0.25rem;
  background: var(--panel-hondo);
  padding: 0.375rem 0.5rem;
  color: var(--texto);
  font-size: 0.6875rem;
}
</style>
