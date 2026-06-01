<template>
  <div id="app" class="min-h-screen bg-gray-900 text-gray-100">
    <!-- Navbar -->
    <nav class="bg-gray-950 border-b border-gray-700 sticky top-0 z-50">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between items-center h-16">
          <div class="flex items-center gap-8">
            <div class="text-xl font-bold text-primary">SIARI</div>
            <div class="hidden md:flex gap-4 text-sm">
              <router-link
                v-for="item in navItems"
                :key="item.path"
                :to="item.path"
                class="px-3 py-2 rounded-md hover:bg-gray-800 transition-colors"
                :class="{ 'bg-gray-800 text-primary': isActive(item.path) }"
              >
                {{ item.label }}
              </router-link>
            </div>
          </div>
          <div class="flex items-center gap-4">
            <span class="text-sm text-gray-400">Usuario</span>
            <button class="px-3 py-1 bg-gray-800 hover:bg-gray-700 rounded-md transition-colors">
              ⚙️
            </button>
          </div>
        </div>
      </div>
    </nav>

    <!-- Main Content -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const navItems = [
  { path: '/', label: '🏠 Dashboard' },
  { path: '/expedientes', label: '📋 Expedientes' },
  { path: '/calculadora', label: '🧮 Calculadora RF' },
  { path: '/mapas', label: '🗺️ Mapas' },
  { path: '/espectro', label: '📊 Espectro' },
]

const isActive = (path) => {
  return route.path === path || route.path.startsWith(path + '/')
}
</script>

<style scoped>
</style>
