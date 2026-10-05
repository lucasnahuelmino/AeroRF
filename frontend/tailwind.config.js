/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#1e40af',
        secondary: '#64748b',
        danger: '#dc2626',
        success: '#16a34a',
        warning: '#ea580c',
        // ── La familia (0.30.28) ─────────────────────────────────────────
        // Los nombres semánticos con los que las plantillas dejan de mentir:
        // `bg-panel` dice panel y es panel, y el valor vive una sola vez, en
        // tokens.css. Cada color es `var(--token)`; Tailwind genera una regla
        // por utilidad usada y no queda ningún puente que reescriba clases
        // de otra escala por detrás (el de 0.30.0 se borró con la migración).
        // Los tokens de acento del mapa (trazo, velo de carga) también están
        // acá: una utilidad que no apunta a un token no es de la familia.
        fondo: 'var(--fondo)',
        panel: 'var(--panel)',
        'panel-alto': 'var(--panel-alto)',
        'panel-hondo': 'var(--panel-hondo)',
        texto: 'var(--texto)',
        'texto-medio': 'var(--texto-medio)',
        'texto-tenue': 'var(--texto-tenue)',
        'texto-invisible': 'var(--texto-invisible)',
        borde: 'var(--borde)',
        'borde-fuerte': 'var(--borde-fuerte)',
        velo: 'var(--velo)',
        'velo-suave': 'var(--velo-suave)',
        'on-ink': 'var(--on-ink)',
        'on-ink-soft': 'var(--on-ink-soft)',
        'on-ink-faint': 'var(--on-ink-faint)',
        'on-ink-wash': 'var(--on-ink-wash)',
        ink: 'var(--ink)',
        signal: 'var(--signal)',
        'signal-on-ink': 'var(--signal-on-ink)',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
