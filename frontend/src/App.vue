<template>
  <div class="app-root" :class="{ 'app-root-shell': isShell }">
    <!--
      One header for the whole application, thin and always present.

      It used to be two: the map drew its own toolbar with no link out, and
      the other screens grew a ~130px header with four status cards. So the
      menu existed on some routes and not on the one the operator lives in.
    -->
    <BrandBar :compact="isShell" />

    <router-view />

    <!--
      The application's own confirm dialog and notice, once, for the whole
      application. They replace `window.confirm` and `window.prompt`, which the
      browser draws with the page's origin in its title — the operator saw
      "localhost:5199 dice…" — and which cannot be styled to match anything.
    -->
    <DialogHost />
  </div>
</template>

<script setup>
/**
 * App.vue
 * ───────
 * Application shell.
 *
 * The global header lives in BrandBar so it can be compact on the GIS map and
 * consistent across the document views without duplicating navigation.
 *
 * This component is now only the frame. The header lives in BrandBar so it
 * can be thin on the map and slightly taller on the document views without
 * duplicating it.
 */
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'

import BrandBar from '@/components/BrandBar.vue'
import DialogHost from '@/components/DialogHost.vue'
import { useSystemStore } from '@/stores/system'
import { useFlightsStore } from '@/stores/flights'
import { useMapStore } from '@/stores/map'

const route = useRoute()
const systemStore = useSystemStore()
const flightsStore = useFlightsStore()
const mapStore = useMapStore()

/**
 * The map owns the viewport below the global navigation and manages its own
 * scrolling. Every other screen is a document that scrolls normally.
 */
const isShell = computed(() => route.path === '/' || route.path === '/map')

onMounted(async () => {
  await systemStore.checkBackend()
  await flightsStore.probeBackend()
  if (!mapStore.stats) await mapStore.loadStats()
  flightsStore.connectSocket()
})

onBeforeUnmount(() => {
  flightsStore.disconnectSocket()
})
</script>

<style scoped>
/* The shell is exactly one viewport tall and manages its own overflow. The
   document views scroll the page, so the root must not lock them. */
.app-root {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--fondo);
  color: var(--texto);
}

/* The GIS workspace occupies the viewport below this header. */
.app-root {
  --brandbar-h: 56px;
}
.app-root-shell {
  --brandbar-h: 48px;
}
</style>

<style>
/* Document views: a centred column that reads as a page, not as a map.
   The vertical rhythm replaces the `space-y-6` each view used to carry, so
   the gap between sections is the same everywhere. */
.page-doc {
  flex: 1 1 auto;
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 1.25rem 1rem 3rem;
}
.page-doc > * + * {
  margin-top: 1.25rem;
}

.page-doc-head {
  margin-bottom: 1rem;
}
.page-doc-title {
  font-size: 1.0625rem;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--texto);
}
.page-doc-sub {
  font-size: 0.75rem;
  color: var(--texto-tenue);
}

/* Una tarjeta de sección, usada por las vistas de gestión (expedientes). */
.card {
  border-radius: 0.625rem;
  border: 1px solid var(--panel-alto);
  background: var(--fondo);
  padding: 0.875rem 1rem;
}
.card-title {
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  color: var(--texto-invisible);
  margin-bottom: 0.5rem;
}

/* The old stylesheet styled `button` globally with a blue background and
   8px/12px padding, which turned every control in the interface into an
   oversized blue rectangle. Tailwind's preflight resets that; these two rules
   are all that is needed for buttons to look like buttons. */
button {
  font: inherit;
  cursor: pointer;
}
</style>
