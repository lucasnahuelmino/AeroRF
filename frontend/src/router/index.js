import { createRouter, createWebHistory } from 'vue-router'

/**
 * Router
 * ──────
 * The map is the application, so `/` resolves to the GIS shell and the
 * remaining views are supporting workspaces.
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
    path: '/calculadora',
    name: 'CalculadoraRF',
    component: () => import('../views/CalculadoraRFView.vue'),
  },
  {
    path: '/situacion',
    name: 'Situacion',
    component: () => import('../views/SituationView.vue'),
    meta: { title: 'Centro de Situación' },
  },
  // Expedientes queda archivado y fuera de la navegación activa: la ruta
  // histórica se redirige al mapa para conservar el acceso a la aplicación
  // sin exponer un módulo de trabajo ya sin estrategia de preservación.
  { path: '/expedientes', redirect: '/' },
  { path: '/expedientes/:id', redirect: '/' },
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
