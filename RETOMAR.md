# Punto de retorno — AeroRF

**Fecha:** 2026-09-30
**Estado:** funcional y verificado. Rama `main` en `origin/main`, árbol limpio.

---

## Lo que se resolvió al final del 0.28

Verificar el modo «Usar el valor del panel» destapó **dos bugs más**, ambos
presentes desde antes y ambos del mismo tipo: una suposición que nadie comprobó.

**Un clic congelaba la pestaña.** El motor emite recorriendo un `Set` con
`forEach`, y `forEach` visita las entradas agregadas durante el propio recorrido.
Al dejar la herramienta armada, cada confirmación se desuscribía del clic y se
volvía a suscribir, así que la suscripción nueva entraba en el `Set` mientras se
recorría: confirmaba, se suscribía otra vez, y el recorrido no terminaba jamás.
No lanzaba, no fallaba un test: solo colgaba el hilo principal. Ahora la
suscripción no se toca nunca — un handler estable, suscrito una vez al armar la
herramienta — y `cleanup()` se partió en `_clearDrawing()`.

**El enganche al centro nunca funcionó.** `centreLatLng` es lo que venga de la
API, un objeto `{lat, lng}`, y el código lo leía como `centre[0]` y `centre[1]`:
`undefined`, distancia `NaN`, `NaN <= tolerancia` falso, y nada se enganchaba
nunca. La función tenía un bug desde 0.27.0. Los tests lo daban por bueno porque
su fixture arma el círculo con `latlng` como **array**, y un array sí tiene
índices. Ahora `_collectCentres()` normaliza a `[lat, lng]`.

**Verificado en el navegador:** 4 clics → 4 círculos de exactamente 5 NM
(9260 m), la herramienta sigue armada después de cada uno, sin fuga de
listeners, 2,36 s. Y el modo de siempre sigue igual: el primer clic fija el
centro, el segundo crea con la distancia entre ambos, y la herramienta se
desarma después.

**Una lección sobre las guardas:** con el bucle puesto, el test que hace clic
**cuelga la corrida** en lugar de fallar. Un guard que cuelga el proceso no puede
avisar. Por eso el test confirma la figura a mano, sin pasar por el clic, y
comprueba que el handler registrado es **la misma función** que antes:
desuscribirse y volver a suscribirse deja el conteo en uno igual, y el conteo no
ve nada.

Detalle en `AERORF_CHANGELOG.md`, secciones 0.28.0 y 0.28.1.

---

## Aviso sobre la memoria de la máquina

Vitest se colgaba al arrancar y parecía un problema del código. No lo era: la
máquina se había quedado con **0,7 GB libres de 5,8**, y las ejecuciones en
segundo plano dejaban procesos vitest zombis que lo empeoraban. Al matarlos y
cerrar el navegador, todo corrió normal.

**Si vitest se cuelga en «RUN» y no imprime nada, no es el código.** Es memoria.
Matar primero:

```powershell
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -match "vitest" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Y no tocar el dev server del proyecto hermano `rni-app-4.0`, que tiene el 8000.

---

## Lo que falta maquetar

De lo que pidió el operador, queda pendiente:

1. **El contenedor del mapa más ancho**, a todo el ancho de la pantalla.
2. **Los paneles más compactos**, en información, utilidades y espacio.
3. **El logo de AeroRF un poco más grande.**
4. **El logo de ENACOM puesto correctamente**, desde
   `frontend/src/assets/logoenacom.png`, con un pie de página abajo que diga
   "Dirección Nacional de Control y Fiscalización" y el logo más pequeño.

El `logoenacom.png` ya está versionado, que estaba sin seguimiento.

**Un dato medido sobre el logo, antes de maquetarlo:** es RGB(11, 23, 66) sobre
fondo transparente. Sobre la barra oscura (`#070d1a`) **no se ve**. Hay que
ponerlo sobre un blanco redondeado —que respeta los colores oficiales— y **no**
invertirlo con un filtro.

Los estilos `.aerorf-popup*` viven en el bloque `<style>` **global** de
`GisShell.vue` (línea 1193), no en el `scoped`, y los necesitan los popups de
aeropuerto y aeronave, que **se quedan**: ninguno de los dos tiene panel lateral,
así que su globo es el único sitio donde se lee esa información.

---

## Lo que también queda pendiente

- **Las 16 filas duplicadas** de `aircraft_tracks` que ya había. No se borran: son
  datos del operador y la decisión es suya. El código ya no genera más.
- **Rotar `OPENSKY_CLIENT_SECRET`.** Sigue en claro en el historial de
  conversación de las últimas sesiones. Está en `.env`, ignorado por git, y en
  ningún archivo versionado. Re-verificado en este commit.
- **`npm run lint` no funciona**: no hay configuración de ESLint en el
  repositorio, en ninguna rama ni en ningún commit. Figuraba como limpio y era
  falso. La comprobación real es el build.

---

## Verificación

| Suite | Estado |
|---|---|
| Frontend (vitest) | **335**, 334 en verde |
| Python (no integración) | **382 pasan**, 7 deseleccionadas |
| `tests/geo_parity.mjs` | 675 pasan |
| Build | limpio, ~39 s |

El único fallo es el `flight-history.spec.js` de siempre por timeout con la suite
entera en paralelo; aislado pasa en 6,7 s. Es saturación, no un fallo.

**Nota sobre la base:** al verificar en el navegador el backend estaba caído y
parecía que la base estaba vacía. No lo estaba. Los objetos del operador siguen
ahí (ids 5, 6, 10, 11, 14); los cinco círculos que creé para probar el radio los
borré.

---

## Documentos

| Archivo | Qué es |
|---|---|
| `README.md` | Entrada al proyecto |
| `MANUAL.md` | Guía de uso para el operador |
| `AERORF_ARCHITECTURE.md` | Decisiones de diseño |
| `AERORF_CHANGELOG.md` | Cada cambio, con su motivo (0.16.0 → 0.28.1) |
| `docs/archive/AERORF_AUDIT.md` | Por qué se quitó cada parte del SIARI |
