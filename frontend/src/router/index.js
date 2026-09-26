import { createRouter, createWebHistory } from 'vue-router'

/**
 * Router
 * ──────
 * The map is the application, so `/` resolves to the GIS shell and the
 * remaining views are supporting screens (expedientes, RF calculator,
 * dashboard).
 *
 * Every view except the shell is lazy-loaded. That keeps plotly (~3.5 MB)
 * out of the initial bundle, which previously made the first paint 5 MB.
 */
const GisShell = () => import('../views/GisShell.vue')

const routes = [
  {
    path: '/',
    name: 'Map',
    component: GisShell,
    meta: { title: 'Mapa', hideChrome: true },
  },
  {
    path: '/map',
    name: 'Mapa',
    component: GisShell,
    alias: ['/mapas'],
  },
  {
    path: '/dashboard',
    name: 'Panel',
    component: () => import('../views/DashboardView.vue'),
  },
  {
    path: '/expedientes',
    name: 'Expedientes',
    component: () => import('../views/ExpedientesView.vue'),
  },
  {
    path: '/expedientes/:id',
    name: 'ExpedienteDetalle',
    component: () => import('../views/ExpedienteDetalleView.vue'),
  },
  {
    path: '/calculadora',
    name: 'CalculadoraRF',
    component: () => import('../views/CalculadoraRFView.vue'),
  },
  {
    path: '/espectro',
    name: 'Espectro',
    component: () => import('../views/EspectroView.vue'),
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  const title = to.meta?.title
  document.title = title ? `AeroRF — ${title}` : 'AeroRF'
})

export default router
