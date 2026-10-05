import { createRouter, createWebHistory } from 'vue-router'

/**
 * Router
 * ──────
 * The map is the application, so `/` resolves to the GIS shell and the
 * remaining views are supporting screens (expedientes, RF calculator).
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
  // Espectro se dio de baja total (0.30.32): sin ruta propia, la dirección
  // vieja cae en el redireccionamiento de abajo y vuelve al mapa.
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
