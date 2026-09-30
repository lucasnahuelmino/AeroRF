# Punto de retorno — AeroRF

**Fecha:** 2026-09-30
**Estado:** funcional. La selección de objetos quedó resuelta en 0.27.3 y el
popup de los objetos se quitó en 0.27.4.

---

## Dos cosas que conviene no volver a tropezar

**Medir en el navegador, no simular.** El bug de 0.27.3 estuvo escondido porque
`layer.fire('click')` se salta el hit-testing. Cuando me puse a medir en el
navegador, una parte de mis mediciones **también estaba mal**: convertía un
punto geográfico a coordenadas de pantalla con el rectángulo del canvas, que
está desplazado (-42, -63) respecto del contenedor del mapa, porque Leaflet lo
pinta con margen. Todos los clics iban 75 px desviados. Con la conversión
correcta —el rectángulo del **contenedor del mapa**, despachando sobre el
canvas— todo responde. Cuando una medición da «no funciona», comprobar primero
la medición.

**No corregir datos a ojo.** `frontend/src/data/airports.js` perdió todos los
acentos al escribirse: `Martn Miguel de Gemes`, `Presidente Pern`, `Capitan`.
La `ñ` sobrevivió, así que no es una limpieza de acentos sino corrupción de la
escritura. El popup lo muestra tal cual, sin pérdida. Está pendiente y hay que
resolverlo volviendo a derivar el archivo de su fuente, no escribiendo los
nombres de memoria.

---

## 0.27.4 — el popup de los objetos salió

Al seleccionar, la información se lee en el Inspector del panel lateral, no en
un globo sobre el mapa. No se perdió nada: el Inspector mostraba todo lo que
el globo mostraba, más la carga por tipo y el formulario de edición.

**Los popups de aeropuerto y de aeronave se quedan a propósito.** Ninguno de
los dos tiene panel lateral, así que su globo es el único sitio donde se lee
esa información. Quitarlos sería perder datos.

Con él salieron `objectPopup()`, y también un `TYPE_LABELS` duplicado en
`MapEngine` que nadie leía —el vivo está en `stores/map.js` como `typeName`—.

Detalle en `AERORF_CHANGELOG.md`, sección 0.27.4.

---

## 0.27.3 — la selección volvió a funcionar

**Síntoma que-was abierto:** ningún objeto del mapa se seleccionaba. Ni puntos,
ni círculos, ni radiales. Como consecuencia no se podía borrar, anotar, mover
ni medir desde un objeto.

**Ahora:** los objetos seleccionan con un clic real, los tres tipos, verificado
en el navegador. También verificados: el clic en suelo vacío deselecciona, y
ocultar y volver a mostrar una capa no altera el orden de dibujo.

Había **tres** causas, no una, y ninguna era la que se había diagnosticado antes:

1. **Un lienzo invisible encima de todo el mapa.** El punto central de un
   círculo o un radial llevaba `pane: 'markerPane'`. Con `preferCanvas` eso le
   da **su propio lienzo de tamaño completo** con `pointer-events: auto`, y el
   markerPane está por encima del overlayPane: tapaba el mapa entero y se comía
   cada clic, incluidos los del suelo. El lienzo estaba vacío, con cero píxeles
   pintados.
2. **Seleccionar reordenaba el lienzo compartido.** `highlight()` llamaba a
   `bringToFront()`, que con un solo lienzo es un reordenamiento global y
   permanente. El área de impacto de un círculo es su disco entero, y el lienzo
   entrega el clic solo a la capa más alta: tras seleccionar el círculo de 16 km
   una vez, todo lo que estaba dentro quedaba inalcanzable.
3. **El orden de dibujo dependía del historial de la sesión.** Las categorías
   llegan con `radials` antes que `circles`, así que un radial perdía contra un
   círculo en el punto de cruce; y volver a mostrar una capa la dejaba clavada
   arriba. Ahora `restack()` lo fija de forma determinista.

Se eliminó además `setCategoryOrder()`, código muerto que reordenaba paneles y
movía el overlayPane dentro del markerPane — el mismo tipo de error que la causa
1.

**Detalle completo en `AERORF_CHANGELOG.md`, sección 0.27.3.**

---

## La lección, que es lo que hay que llevarse

**Los 306 tests de jsdom no podían ver este bug, y por eso tres intentos
seguidos fallaron.** Usan `layer.fire('click', …)`, que entrega el evento a la
capa y se salta el hit-testing que hace el navegador. El bug vivía en los pasos
*anteriores* al evento: dónde se pintaban las capas y en qué orden.

Lo que faltaba era un navegador, y en cuanto lo hubo el primer `elementFromPoint`
sobre un círculo devolvió el lienzo equivocado. **Para cualquier bug de
interacción que se resista a los tests: abrir el navegador y medir, antes de
escribir nada.**

Dos reglas que quedaron escritas como tests:

- **Un test que nunca falló no es una guarda.** Las 8 guardas de
  `frontend/tests/canvas-hit-targets.spec.js` se verificaron revirtiendo cada
  arreglo: 3 fallan sin el arreglo 1, 1 sin el 2, 2 sin el 3.
- **No afirmar más de lo que se midió.** Tres veces se presentó *una* causa
  plausible como si fuera *la* causa. El dato que debía importar desde el
  principio era que **tampoco fallaban los puntos simples**, y eso descartaba de
  entrada cualquier explicación sobre grupos de capas.

### Una suposición que era falsa

`npm run lint` figuraba como limpio en sesiones anteriores. **No lo es, y nunca
lo fue:** no hay configuración de ESLint en el repositorio, en ninguna rama, en
ningún commit. El script fallaba y se reportaba como correcto. La comprobación
real es el build.

---

## Estado del proyecto

| Suite | Estado |
|---|---|
| Python (no integración) | 376 pasan, 7 deseleccionadas |
| Python integración | 7, requieren backend en 8010 |
| Frontend (vitest) | 314 pasan (306 + 8 nuevas) |
| Paridad geodesica | 675 pasan |
| Build | limpio, ~25 s |
| Lint | **roto, sin configuración** — ver arriba |

Un test de `flight-history.spec.js` da timeout esporádicamente con la suite
completa en paralelo; aislado pasa en 3 s. Es saturación, no un fallo.

### Cómo arrancar

Doble clic en `start.bat`, o:

```powershell
start.bat            # backend + frontend
start.bat test       # suite de pruebas
start.bat stop       # detener
```

- Frontend: `http://localhost:5199` (Vite escucha en `::1`; usar `localhost`,
  no `127.0.0.1`)
- Backend: `http://127.0.0.1:8010`
- Logs: `logs/backend.log`, `logs/frontend.log`

El puerto 8000 es del proyecto hermano `rni-app-4.0` — no tocarlo.

---

## Pendiente

### Seguridad — lo único urgente

**Rotar `OPENSKY_CLIENT_SECRET`.** Aparece en claro en el historial de
conversación de esta sesión y de las dos anteriores. Está en `.env` (ignorado
por git, verificado en cada commit) y en ningún archivo trackeado. Hay que
generar uno nuevo en OpenSky y actualizar `.env`.

### Opcional

- `npm run lint` no funciona. Se puede dejar así, o añadir una configuración
  mínima de ESLint. No se añadió aquí porque no se pidió y el build ya cubre
  la comprobación.
- **Los acentos de `frontend/src/data/airports.js`.** Ver arriba. 67 nombres de
  aeropuerto, la mayoría con la ortografía rota. Se arregla rederivando el
  archivo de su fuente, no corrigiéndolo a mano.

### Limitación conocida y documentada

El muestreo de posiciones corre en el bucle de sondeo del WebSocket, así que
**"Grabar vuelo" no registra nada con el navegador cerrado**. Está documentado en
`MANUAL.md`.

---

## Documentos

| Archivo | Qué es |
|---|---|
| `README.md` | Entrada al proyecto |
| `MANUAL.md` | Guía de uso para el operador |
| `AERORF_ARCHITECTURE.md` | Decisiones de diseño |
| `AERORF_CHANGELOG.md` | Cada cambio, con su motivo (0.16.0 → 0.27.4) |
| `docs/archive/AERORF_AUDIT.md` | Por qué se quitó cada parte del SIARI |
