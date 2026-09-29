# Punto de retorno — AeroRF

**Fecha:** 2026-09-29
**Estado:** funcional salvo **la selección de objetos en el mapa, que NO
funciona**. Ese es el único asunto abierto conocido.

Todo lo demás fue verificado por el operador: dibujo de círculos y radiales,
trayectorias de vuelos, elección de vuelo histórico, enganche al centro,
lanzador, raíz limpia.

---

## Lo que hay que resolver mañana

**Síntoma exacto, reportado por el operador:** ningún objeto del mapa se
selecciona. Ni puntos, ni círculos, ni radiales. Como consecuencia no se puede
borrar, anotar, mover ni medir desde un objeto.

Lo que el operador ve: hace clic y no pasa absolutamente nada. No hay selección
visible, no se abre el panel, no aparece el menú contextual.

**Nada más que eso está en duda.** El resto de la sesión se confirmó
funcionando.

---

## Lo que ya se intentó, y por qué falló

Esto importa: **tres intentos在前 fallaron, todos con la suite en verde.** La
lección es que los tests de jsdom no están viendo este bug.

### 1. `L.layerGroup` → `L.featureGroup` (`6fc93a2`)

Hipótesis: un `LayerGroup` no reenvía los clics de sus hijos, así que el clic
en el anillo no llegaba al handler.

**Parcialmente cierto.** Arregla que el círculo no seleccione, pero no explica
que tampoco fallen los puntos simples. El operador siguió sin poder seleccionar
nada.

### 2. El clic en un objeto no llega al mapa (`8067f50`)

Hallazgo real: el mapa dibuja con `preferCanvas`, así que todos los objetos
comparten un canvas y `stopPropagation` no tiene nada donde actuar. El handler
del mapa corre también para clics sobre objetos.

El clic ahora lleva `overObject` con el id, y el shell distingue "sobre un
objeto" de "en el vacío".

**No alcanzó.** El operador volvió a reportar que nada selecciona.

### 3. `active === TOOLS.SELECT` → `!toolManager.isDrawing`

Real: `active` es `null` hasta que se elige una herramienta, y "seleccionar"
solo se activa desde la medición de aeropuerto. La condición nunca se cumplía.

**No alcanzó por sí solo.** Pero es un bug genuino, y queda arreglado.

### El error de método

En cada intento afirmé haber explicado el problema cuando solo había encontrado
*una* causa plausible. El dato que debí tomar en serio desde el principio: el
síntomo es "**nada** selecciona, ni siquiera puntos simples", y eso descartaba de
entrada cualquier explicación que dependiera de los grupos de capas.

---

## Por qué los tests no servían

**Esta es la hipótesis principal para mañana, y no está verificada.**

Los tests de `frontend/tests/` corren en jsdom, y los que escribí para esto
pasan sobre el código roto:

- `select-shell.spec.js` monta el shell completo y hace clic en un objeto real
- `select-order.spec.js` fija el orden de los clics y la presencia del id
- `selection.spec.js` cubre el resaltado atravesando el grupo

Los tres fueron verificados revirtiendo el arreglo, y los tres fallaron
correctamente. **Aun así el operador sigue sin poder seleccionar.**

La conclusión honesta: **o bien los tests reproducen un camino que no es el del
navegador, o bien el bug está en una capa que los tests no montan.**

Lo que los tests hacen: `layer.fire('click', {...}, true)`.
Lo que hace el navegador: un `MouseEvent` real sobre el canvas, que Leaflet
detecta con hit-testing (`_containsPoint`) antes de emitir nada.

**Esa diferencia es el lugar donde mirar primero.** Un clic sintético sobre la
capa salta el hit-testing por completo; si el problema está en que Leaflet no
detecta el objeto bajo el puntero — por `interactive`, por el `pane`, por el
`zIndex`, o por un `pointer-events` mal puesto — ningún test de jsdom que use
`fire()` lo va a detectar jamás.

---

## Plan sugerido para mañana

1. **Mirar la consola del navegador** al hacer clic en un objeto. Es lo primero
   y lo más barato. Si hay una excepción, dice exactamente dónde.
2. **Comprobar si el clic llega al objeto** con un `console.log` temporal en el
   handler de `_applySelectionHandler`.
3. **Verificar el hit-testing**: si el clic no llega, el problema es que Leaflet
   no considera que el puntero esté sobre el objeto. Sospechosos, en orden:
   - `interactive: false` en la capa del objeto o en un padre
   - el `pane` del punto central interfering
   - un `canvas` superpuesto de otra capa por encima
   - `zIndex`
4. **Revisar `suppressClicks`.** El handler del mapa empieza con
   `if (this._clickSuppressed) return`. Hoy el flag nunca se inicializa (queda
   `undefined`, falsy) y solo `ToolManager.activate` lo pone en `false`. Si
   quedara en `true` por algún camino, el mapa no publicaría ningún clic. Hay un
   test (`click-suppression.spec.js`) que fija el comportamiento actual, pero
   **no cubre lo que pasa en el navegador real**.
5. **Probar en el navegador antes de escribir un test.** Si algo no se puede ver
   en un navegador abierto, no se puede fijar en jsdom, y un test que lo fije va
   a mentir.

---

## Estado del proyecto

### Commits

```
8067f50  La seleccion seguia rota por dos razones, no una
6fc93a2  No se podia seleccionar nada: lo rompi al hacer el circulo un LayerGroup
f58f900  El punto central, y poder colocar un objeto en el centro de otro
8921e3b  Grados en vivo en el radial y el circulo visible al elegir la herramienta
0a42135  Elegir el vuelo, no solo la aeronave: la trayectoria podia ser de otro
cd2c95c  La trayectoria no se cargaba nunca: una clave repetida en el cliente
f36c043  Raiz limpia y un solo lanzador, con los puertos reales
```

Rama `main`, sincronizada con `origin/main`, árbol limpio.

### Verificación

| Suite | Estado |
|---|---|
| Python (no integración) | 376 pasan, 7 deseleccionadas |
| Python integración | 7, requieren backend en 8010 |
| Frontend (vitest) | 306 pasan |
| Paridad geodesica | 675 pasan |
| Build | limpio, ~23 s |

**Advertencia:** la suite frontend pasa, y el operador reporta el bug. Es decir:
**la suite en verde no es evidencia de nada respecto a la selección.**

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

### Pendiente de seguridad

**Rotar `OPENSKY_CLIENT_SECRET`.** Aparece en claro en el historial de
conversación de esta sesión y de la anterior. Está en `.env` (ignorado por git,
verificado en cada commit) y en ningún archivo trackeado. Hay que generar uno
nuevo en OpenSky y actualizar `.env`.

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
| `AERORF_CHANGELOG.md` | Cada cambio, con su motivo (0.16.0 → 0.27.2) |
| `docs/archive/AERORF_AUDIT.md` | Por qué se quitó cada parte del SIARI |

> Nota: `RETOMAR.md` anterior fue eliminado a pedido del usuario (obsoleto) y
> `AERORF_AUDIT.md` se movió a `docs/archive/`. Este archivo reemplaza al
> anterior.
