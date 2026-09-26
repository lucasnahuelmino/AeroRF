/**
 * components/BrandBar.vue
 * ──────────────────────
 * The persistent header: brand, section menu and the institutional lockup.
 *
 * Why this exists
 * ───────────────
 * The application had two unrelated headers. The map drew its own full-height
 * toolbar with no link to the other sections, and every other screen grew a
 * ~130px header with four status cards. So the menu was only present on some
 * screens, and on the map — the one an operator lives in — it was absent, so
 * the only way to reach an expediente was to type the URL.
 *
 * This component is the single header. It is thin, fixed, and present in every
 * section, which is what a working tool needs: you always know where you are
 * and you can always get somewhere else.
 *
 * On the map it is compact — the map owns the height budget there. Elsewhere it
 * grows slightly to carry the section title. Both are 48px or less, so it costs
 * the map almost nothing.
 *
 * ── The institutional lockup ───────────────────────────────────────────────
 * ENACOM's mark is not drawn here. Official logotypes are protected, and
 * shipping an imitation of one inside a tool that carries its name would be
 * wrong. What is here is a typographic lockup: the acronym in the
 * institution's weight with its full name beneath. If ENACOM supplies the
 * official file, drop it at `src/assets/enacom.svg` and set `hasLogo` to true
 * here; the layout does not change.
 */

<template>
  <header class="brandbar" :class="{ 'brandbar-shell': compact }">
    <!-- Brand: returns to the map, which is the home of the application. -->
    <button
      type="button"
      class="brandbar-brand"
      :title="compact ? 'Ir al mapa' : 'Mapa'"
      :aria-label="compact ? 'Ir al mapa' : 'Mapa'"
      @click="go('/')"
    >
      <img :src="logo" alt="" class="aerorf-logo" />
      <span class="brandbar-name">
        <b>AeroRF</b>
        <i v-if="!compact">Interferencias aeronáuticas</i>
      </span>
    </button>

    <!-- Section menu. Always visible, never a dropdown: an operator should
         not have to open something to find out where they can go. -->
    <nav class="brandbar-nav" aria-label="Secciones">
      <router-link
        v-for="item in sections"
        :key="item.path"
        :to="item.path"
        class="brandbar-link"
        :class="{ 'brandbar-link-on': isActive(item.path) }"
      >
        <span class="brandbar-link-icon" aria-hidden="true">{{ item.icon }}</span>
        <span class="brandbar-link-text">{{ item.label }}</span>
      </router-link>
    </nav>

    <div class="brandbar-spacer" />

    <!-- Live status, three dots and nothing more. The old header used four
         cards that took 60px of height to say the same thing. -->
    <div class="brandbar-status" :title="statusDetail">
      <span class="brandbar-dot" :class="dotClass('ok', systemStore.connected)" :title="`Backend: ${systemStore.backendStatus}`" />
      <span class="brandbar-dot" :class="dotClass('warn', flightsStore.openskyConfigured)" :title="`OpenSky: ${flightsStore.openskyConfigured ? 'configurado' : 'sin configurar'}`" />
      <span class="brandbar-dot" :class="dotClass('off', flightsStore.socketState === 'connected')" :title="`Vivos: ${flightsStore.socketState}`" />
    </div>

    <!-- Institutional lockup. Typographic, not a drawn mark; see the note
         at the top of this file. -->
    <div class="brandbar-enacom" title="Dirección Nacional de Control y Fiscalización">
      <img v-if="hasEnacomLogo" :src="enacomLogo" alt="ENACOM" class="brandbar-enacom-img" />
      <span v-else class="brandbar-enacom-mark" aria-label="ENACOM">ENACOM</span>
      <span v-if="!compact" class="brandbar-enacom-full">
        Dirección Nacional de Control<br />y Fiscalización
      </span>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import logo from '@/assets/aerorf-128.png'
import { useSystemStore } from '@/stores/system'
import { useFlightsStore } from '@/stores/flights'

const props = defineProps({
  /** Thin variant, used on the map where height is scarce. */
  compact: { type: Boolean, default: false },
})

const route = useRoute()
const router = useRouter()
const systemStore = useSystemStore()
const flightsStore = useFlightsStore()

/**
 * Set to true once ENACOM supplies the official file at
 * `src/assets/enacom.svg`. Until then the lockup is typographic.
 */
const hasEnacomLogo = false
const enacomLogo = null

const sections = [
  { path: '/', label: 'Mapa', icon: '◈' },
  { path: '/dashboard', label: 'Panel', icon: '▤' },
  { path: '/expedientes', label: 'Expedientes', icon: '▣' },
  { path: '/calculadora', label: 'Calculadora RF', icon: '∑' },
  { path: '/espectro', label: 'Espectro', icon: '∿' },
]

const isActive = (path) =>
  path === '/' ? route.path === '/' || route.path === '/map' : route.path.startsWith(path)

const statusDetail = computed(() => {
  const parts = [
    `Backend: ${systemStore.backendStatus}`,
    `Base: ${systemStore.dbConnected ? 'conectada' : 'sin conexión'}`,
    `OpenSky: ${flightsStore.openskyConfigured ? 'configurado' : 'sin configurar'}`,
    `Vivos: ${flightsStore.socketState}`,
  ]
  return parts.join(' · ')
})

function dotClass(okClass, ok) {
  return ok ? `brandbar-dot-${okClass}` : 'brandbar-dot-off'
}

function go(path) {
  if (route.path !== path) router.push(path)
}
</script>

<style scoped>
/* ─── The bar ───────────────────────────────────────────────────────────────
 * 48px in the compact variant, 56px elsewhere. Institutional means restrained:
 * a thin rule, a dark ground, and no gradient competing with the data.
 * ------------------------------------------------------------------------- */

.brandbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  height: 56px;
  padding: 0 0.875rem;
  background: #070d1a;
  border-bottom: 1px solid #1b2740;
  /* Above Leaflet's controls (1000) and below the nav overlay (1400). */
  z-index: 1150;
  flex: 0 0 auto;
  user-select: none;
  -webkit-user-select: none;
}

.brandbar-shell { height: 48px; gap: 0.625rem; }

/* ─── Brand ──────────────────────────────────────────────────────────────── */

.brandbar-brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem 0.25rem 0.25rem;
  border-radius: 0.375rem;
  border: 1px solid transparent;
  background: transparent;
  flex: 0 0 auto;
  transition: background 0.12s, border-color 0.12s;
}
.brandbar-brand:hover { background: #0f1a30; border-color: #24344f; }

/* The mark is 30px, so the 48px compact bar has little room for padding
   around it. Keeping the brand flush keeps the logo as large as it can be. */
.brandbar-shell .brandbar-brand { padding: 0 0.5rem 0 0.25rem; }

.brandbar-name {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.15;
}
.brandbar-name b {
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: #e6edf7;
}
.brandbar-name i {
  font-style: normal;
  font-size: 0.5625rem;
  letter-spacing: 0.04em;
  color: #5b6b85;
  text-transform: uppercase;
}

/* ─── Section menu ──────────────────────────────────────────────────────────
 * A flat row of links, not pills. Institutional software reads as calm; the
 * active state is a single accent underline, which is enough and does not
 * make the bar look like a website.
 * ------------------------------------------------------------------------- */

.brandbar-nav {
  display: flex;
  align-items: stretch;
  gap: 0.125rem;
  height: 100%;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}
.brandbar-nav::-webkit-scrollbar { display: none; }

.brandbar-link {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0 0.625rem;
  font-size: 0.75rem;
  color: #8fa3bf;
  text-decoration: none;
  white-space: nowrap;
  border-bottom: 2px solid transparent;
  transition: color 0.12s, border-color 0.12s, background 0.12s;
  touch-action: manipulation;
}
.brandbar-link:hover { color: #dbe6f5; background: #0f1a30; }

.brandbar-link-on {
  color: #7dd3fc;
  border-bottom-color: #38bdf8;
}

.brandbar-link-icon { font-size: 0.8125rem; line-height: 1; opacity: 0.85; }

/* The map owns the height budget, so its own tabs already name the panels.
 * Repeating "Mapa" there would be noise. */
.brandbar-link-on .brandbar-link-icon { opacity: 1; }

.brandbar-spacer { flex: 1 1 auto; min-width: 0; }

/* ─── Status ──────────────────────────────────────────────────────────────── */

.brandbar-status {
  display: flex;
  align-items: center;
  gap: 0.3125rem;
  padding: 0 0.125rem;
  flex: 0 0 auto;
}

.brandbar-dot {
  width: 6px;
  height: 6px;
  border-radius: 9999px;
  flex: 0 0 auto;
}
.brandbar-dot-ok { background: #34d399; }
.brandbar-dot-warn { background: #fbbf24; }
.brandbar-dot-off { background: #3b4a63; }

/* ─── ENACOM lockup ────────────────────────────────────────────────────────
 * The acronym set in the institution's weight, with the full name beside it.
 * Deliberately not a drawn mark: see the note at the top of the file.
 * ------------------------------------------------------------------------- */

.brandbar-enacom {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding-left: 0.75rem;
  border-left: 1px solid #1b2740;
  flex: 0 0 auto;
}

.brandbar-enacom-mark {
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: #c7d6ea;
  white-space: nowrap;
}

.brandbar-enacom-img { height: 26px; width: auto; }

.brandbar-enacom-full {
  font-size: 0.5rem;
  line-height: 1.25;
  letter-spacing: 0.02em;
  color: #5b6b85;
  white-space: nowrap;
}

@media (max-width: 1100px) {
  /* Below this the full institution name no longer fits beside the menu.
     Dropping it keeps the menu complete, which matters more. */
  .brandbar-enacom-full { display: none; }
  .brandbar-name i { display: none; }
}

@media (max-width: 860px) {
  .brandbar-link-text { display: none; }
  .brandbar-link { padding: 0 0.5rem; }
}
</style>
