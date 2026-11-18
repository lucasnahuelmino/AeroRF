const { defineConfig } = require('@playwright/test')
module.exports = defineConfig({
  testDir: './e2e',
  timeout: 60000,
  use: {
    baseURL: 'http://localhost:5199',
    viewport: { width: 1366, height: 768 },
    headless: true,
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5199',
    reuseExistingServer: true,
    timeout: 120000,
  },
})
