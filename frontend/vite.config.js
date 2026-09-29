import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

/**
 * Vite configuration.
 *
 * The API target comes from `VITE_API_TARGET`. The fallback is 8010, not 8000:
 * on this machine 8000 belongs to the sibling project `rni-app-4.0`, and a
 * frontend that proxies to it would talk to another application and look
 * merely "broken" rather than obviously misconfigured.
 *
 *   PowerShell:  $env:VITE_API_TARGET='http://127.0.0.1:8010'; npm run dev
 *   bash:        VITE_API_TARGET=http://127.0.0.1:8010 npm run dev
 *
 * `start.bat` sets this automatically; you only need it when running
 * `npm run dev` by hand.
 */
const API_TARGET = process.env.VITE_API_TARGET || 'http://127.0.0.1:8010'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: Number(process.env.VITE_PORT) || 5199,
    // True, not false. With `strictPort: false` Vite silently moves to the
    // next free port, so the URL printed in the terminal is not the URL
    // being served, and the launcher waits on a port nothing is listening on.
    // Failing loudly is the better behaviour: the operator finds out at once.
    strictPort: true,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        ws: true, // the /ws/flights channel
      },
      '/health': {
        target: API_TARGET,
        changeOrigin: true,
      },
      '/ws': {
        target: API_TARGET,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    // Plotly (~3.5 MB) is only needed by the spectrum view, which is
    // lazy-loaded; splitting it keeps the initial bundle small.
    rollupOptions: {
      output: {
        manualChunks: {
          leaflet: ['leaflet'],
          vendor: ['vue', 'vue-router', 'pinia', 'axios'],
        },
      },
    },
    chunkSizeWarningLimit: 900,
  },

  /**
   * Component tests.
   *
   * The point of these is that "it compiles" is not the same as "it
   * works". A component can compile and still throw the moment `mount()`
   * runs its `onMounted` — an undefined helper, a bad store access, a
   * Leaflet call that needs layout. jsdom provides the DOM; the API layer
   * is stubbed so the tests never touch the network.
   */
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.spec.js'],
    setupFiles: ['./tests/setup.js'],
  },
})
