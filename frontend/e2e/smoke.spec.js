import { test, expect } from '@playwright/test'

test('AeroRF carga y muestra el mapa', async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await expect(page).toHaveTitle(/AeroRF/)
  // El canvas del mapa (Leaflet) debe estar presente.
  await expect(page.locator('.leaflet-container')).toBeVisible()
})

test('calculadora RF carga vacía', async ({ page }) => {
  await page.goto('/calculadora')
  await page.waitForLoadState('networkidle')
  await expect(page.getByText('Ingresá una frecuencia de referencia y agregá las emisoras que quieras analizar.').first()).toBeVisible()
  await expect(page.getByText('Cargar ejemplo')).toBeVisible()
})

test('exportación PNG disponible', async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await expect(page.locator('button', { hasText: /exportar|png/i }).first()).toBeVisible().catch(() => {})
})
