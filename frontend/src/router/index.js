import { createRouter, createWebHistory } from 'vue-router'

/**
 * Router
 * ──────
 * The map is the application, so `/` resolves to the GIS shell and the
 * remaining views are supporting workspaces.
 *
 * Every view except the shell is lazy-loaded: the initial bundle carries
 * the map, and each workspace arrives in its own chunk. The rule started
 * when a ~3.5 MB charting library still rode along with the calculator;
 * AeroRF 2.5 removed it, and lazy views stayed because they keep the first
 * paint small.
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
  // Expedientes quedó retirado como dependencia funcional (AeroRF 2.6,
  // Bloque 1): su interfaz ya no existe y ninguna pantalla lo necesita. La
  // ruta histórica sigue redirigiendo al mapa para no romper enlaces
  // viejos, y los datos — así como el API legado `/expedientes/*` — siguen
  // intactos en el backend.
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
