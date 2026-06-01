import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import ExpedientesView from '../views/ExpedientesView.vue'
import ExpedienteDetalleView from '../views/ExpedienteDetalleView.vue'
import CalculadoraRFView from '../views/CalculadoraRFView.vue'
import MapasView from '../views/MapasView.vue'
import EspectroView from '../views/EspectroView.vue'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: DashboardView,
  },
  {
    path: '/map',
    name: 'Map',
    component: MapasView,
    alias: '/mapas',
  },
  {
    path: '/expedientes',
    name: 'Expedientes',
    component: ExpedientesView,
  },
  {
    path: '/expedientes/:id',
    name: 'ExpedienteDetalle',
    component: ExpedienteDetalleView,
  },
  {
    path: '/calculadora',
    name: 'Calculadora',
    component: CalculadoraRFView,
  },
  {
    path: '/espectro',
    name: 'Espectro',
    component: EspectroView,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
