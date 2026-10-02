/**
 * assets/tokens.js
 * ────────────────
 * Lee los design tokens de `assets/tokens.css` desde JavaScript.
 *
 * Por qué hace falta
 * ─────────────────
 * Leaflet y Chart.js necesitan el color como cadena: no resuelven `var(--x)`. Si
 * una capa del mapa recibiera `var(--trazo)`, Leaflet lo pasaría tal cual al
 * atributo `stroke` del SVG o al color del canvas, y ahí no hay nada que resuelva
 * una variable: se dibuja literalmente `var(--trazo)`, o no se dibuja.
 *
 * Antes de este archivo cada color del mapa estaba escrito a mano en el punto de
 * uso, repartido entre `MapEngine.js`, `aircraft.js`, `airports.js` y
 * `draw.js`. Cambiar la paleta obligaba a cazarlos uno por uno, y alguno se
 * quedaba atrás: es lo que pasó con la etiqueta de medición, que quedó en un
 * `<style scoped>` y nunca recibió el estilo.
 *
 * Los valores se cachean. Los tokens son constantes de diseño: no hay theming en
 * AeroRF, así que no cambian en runtime. La caché importa sobre todo en el mapa,
 * donde `token()` se llama por capa y por segmento.
 *
 * `tokens.css` y este archivo se mantienen sincronizados **por nombre de token**,
 * nunca por valor.
 */

const cache = new Map()

/**
 * El valor de un token, como cadena lista para Leaflet o Canvas.
 *
 * @param {string} nombre  por ejemplo `--trazo`
 * @param {string} [fallback] para cuando no hay documento (pruebas en Node) o el
 *   token no existe. El valor por defecto debe ser el que la aplicación ya usaba,
 *   para que una prueba sin DOM siga teniendo una respuesta razonable.
 * @returns {string}
 */
export function token(nombre, fallback = '') {
  if (cache.has(nombre)) return cache.get(nombre)
  let valor = fallback
  if (typeof document !== 'undefined' && document.documentElement) {
    valor =
      getComputedStyle(document.documentElement).getPropertyValue(nombre).trim() || fallback
  }
  cache.set(nombre, valor)
  return valor
}

/**
 * `token()` con alfa, para los rellenos que esperan `rgba(...)`.
 *
 * Sólo convierte hex de seis dígitos. Un token que ya viene como `rgba(...)` o
 * como `color-mix(...)` se devuelve tal cual: `color-mix` no se puede convertir
 * sin recalcular la mezcla, y devolver algo inventado sería peor que devolver el
 * valor original.
 *
 * @param {string} nombre
 * @param {number} alfa  0 a 1
 * @param {string} [fallback]
 * @returns {string}
 */
export function tokenConAlfa(nombre, alfa, fallback = '') {
  const color = token(nombre, fallback)
  const hex = color.match(/^#([0-9a-f]{6})$/i)
  if (!hex) return color
  const n = parseInt(hex[1], 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alfa})`
}

/**
 * Vaciar la caché. Sólo para las pruebas: si una prueba cambia un token y otra
 * lo lee, la primera en leer lo deja cacheado para siempre.
 */
export function limpiarCacheTokens() {
  cache.clear()
}