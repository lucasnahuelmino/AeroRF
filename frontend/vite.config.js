import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

/**
 * Vite configuration.
 *
 * The API target is read from `VITE_API_TARGET` so the proxy is not
 * hard-coded to port 8000 — which on this machine belongs to another
 * project (audit P7). Default 8000; override per environment:
 *
 *   PowerShell:  $env:VITE_API_TARGET='http://127.0.0.1:8010'; npm run dev
 *   bash:        VITE_API_TARGET=http://127.0.0.1:8010 npm run dev
 */
const API_TARGET = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: Number(process.env.VITE_PORT) || 5173,
    strictPort: false,
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
