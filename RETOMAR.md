# Punto de retorno — AeroRF

**Fecha:** 2026-09-30
**Estado:** hay un commit a medio terminar y verificado a medias.
Rama `main` en `origin/main`, commit `57ba41e`, árbol limpio. Se puede cerrar
la máquina.

---

## Lo primero al volver: correr los tests que no llegaron

**Esto es lo único que bloquea.** La máquina se quedó sin memoria (0,7 GB
libres) y vitest se colgaba al arrancar, así que la última tanda no llegó a
correr. No es un fallo del código: es la máquina.

Antes de nada, matar procesos vitest viejos, que se acumulan y son la causa de
que la cosa empeore:

```powershell
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -match "vitest" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Si sigue colgado, cerrar el navegador y el dev server de AeroRF, y mirar la
memoria libre. El proyecto hermano `rni-app-4.0` tiene su dev server en 8000:
**no tocarlo**.

Luego:

```powershell
cd frontend
npx vitest run tests/typed-sizing.spec.js
npx vitest run
npm run build
```

### Qué esperar de `typed-sizing.spec.js`

11 tests. Corrieron **una vez**: 8 pasaron, 3 fallaron.

- **Uno era un bug real y ya está corregido.** La herramienta quedaba armada
  pero sorda: `cleanup()` cancela la suscripción a los clics, así que el
  segundo círculo de la misma serie nunca llegaba. Ahora se re-suscribe en
  `_emitComplete` con `keepTool`.
- **Los otros dos son precisión de los propios tests, no del código.** Uno
  espera 9260 m exactos y el código da 9249,6: `metres / 111320` grados es una
  aproximación de la distancia en latitud. El otro espera un snap con
  tolerancia de 0,00005 grados cuando hace falta más. Si fallan, ajustar el
  test, no `draw.js`.

Hay que confirmar también que el arreglo del snap **sigue fallando el test si
se revierte** — es la única forma de saber que el test guarda algo.

---

## Lo que quedó hecho

### Aeropuertos

- Las etiquetas del mapa muestran el **IATA** (EZE, AEP). Antes el ICAO.
  `airportCode()` degrada a ICAO → gps → local → nombre recortado.
- **105 aeropuertos, antes 67.** El criterio es objetivo y está escrito en el
  generador: entra todo aeropuerto argentino que la fuente tipea
  `medium_airport`, o `small_airport` con vuelo regular, y siga en servicio.
  Entra además **Jujuy**, que era un `large_airport` con vuelo regular y faltaba.
- **El Palomar** está en la fuente como `SADP`, IATA `EPA`. **San Fernando**
  publica ningún ICAO ni IATA: solo `gps_code` SADF y `local_code` FDO. Por eso
  no estaban, no por un olvido. El generador resuelve contra `icao_code` y
  después contra `gps_code`, e informa en pantalla cuáles se resolvieron por la
  segunda vía.
- **Nada inventado:** un token que no coincide se reporta y se deja fuera. El
  generador avisó de cuatro que la fuente no publica: `SCQN`, `SGCI`, `SGPP`,
  `SUCU`. Quedan fuera y son pendientes de decidir.
- **Colores:** azul relleno con vuelo regular, ámbar hueco para los menores
  activos. El panel lleva leyenda, porque si no el color no informa de nada.
- La capa **sigue sin persistirse**.

### Los acentos — la explicación real

No era corrupción al escribir el archivo, como dije ayer. Era una línea del
generador, `name.encode("ascii", "ignore")`, puesta a propósito. El archivo se
escribe en UTF-8 y el navegador lo lee en UTF-8. Ahora quedan los acentos:
"Martín Miguel de Güemes", 26 nombres con acento.

### El radio que no se respetaba

Escribías 5 NM, apretabas el mapa, y salía un círculo de 2,987 NM. Reproducido
en el navegador: el radio salía de la distancia entre los dos clics y el valor
escrito se descartaba. **No había forma de decir "este número, un clic".**

Ahora hay dos modos, y el que existía sigue siendo el default:

- **Ajustar con el cursor** (default, lo de antes): primer clic el centro,
  segundo el borde.
- **Usar el valor del panel:** un clic y el número escrito es el que se guarda.
  Y la herramienta **sigue armada**, para poner cuatro círculos de 5 NM con
  cuatro clics.

El otro reclamo —«al crear un elemento se oculta el panel»— no era que se
ocultara: se **desarmaba la herramienta** y con ella desaparecían los campos.
Mismo arreglo.

Además el clic que dimensiona **ya no hace snap** al centro de otra figura. El
centro ya estaba puesto, ese clic solo lleva una distancia, y el snap lo movía
a donde el operador no apuntó: 4,866 NM donde había pedido 5.

### Las grabaciones

**Se guardaron. Cada una, dos o tres veces.** 34 filas con 8 grupos de
duplicados exactos.

La causa: `_store_track` insertaba siempre, sin preguntar si esa trayectoria ya
estaba. Pedir dos veces el mismo vuelo insertaba una fila nueva cada vez.

Ahora se busca primero. La coincidencia es la misma aeronave, el mismo vuelo
sobre ella y el mismo número de puntos. Dos cosas **no** son repetidas, a
propósito:

- una trayectoria más escasa sobre la misma ventana, que son los datos
  distintos de una grabación parcial;
- otro vuelo de la misma aeronave: `callsign` y `flight_id` son parte de la
  clave, porque colapsarlos colgaba el segundo bajo el callsign del primero, que
  es una etiqueta incorrecta y segura, no una duplicata inofensiva. **Eso lo
  encontró un test mío, no la inspección.**

**Las 16 filas duplicadas que ya hay en la base NO se borraron.** Son datos del
operador y la decisión es suya. Si las quiere limpiar, se puede hacer con un
script que conserve la de menor `id` de cada grupo.

---

## Lo que NO se hizo

De lo que pidió el operador, quedó pendiente:

1. **El contenedor del mapa más ancho**, a todo el ancho de la pantalla.
2. **Los paneles más compactos**, en información, utilidades y espacio.
3. **El logo de AeroRF un poco más grande.**
4. **El logo de ENACOM puesto correctamente**, desde
   `frontend/src/assets/logoenacom.png`, con un pie de página abajo que diga
   "Dirección Nacional de Control y Fiscalización" y el logo más pequeño.

El archivo `logoenacom.png` **ya está commiteado** (estaba sin versionar), así
que no se pierde.

**Un dato que hay que tener antes de maquetar el logo:** el archivo es azul
oscuro —RGB(11, 23, 66)— sobre fondo transparente. Sobre la barra oscura
(`#070d1a`) **no se ve**. Hay que ponerlo sobre un blanco redondeado, que es lo
que respeta los colores oficiales, y no invertirlo con un filtro.

Los estilos `.aerorf-popup*` viven en el bloque `<style>` **global** de
`GisShell.vue` (línea 1193), no en el `scoped`, y los necesitan los popups de
aeropuerto y aeronave, que **se quedan**: ninguno de los dos tiene panel lateral,
así que su globo es el único sitio donde se lee esa información.

---

## Verificación

| Suite | Estado |
|---|---|
| Python (no integración) | **382 pasan**, 7 deseleccionadas |
| `tests/geo_parity.mjs` | 675 pasan |
| `tests/airports.spec.js` | **39 pasan** (31 antes, 8 nuevos) |
| `tests/test_track_dedup.py` | **6 pasan** |
| `frontend/tests/typed-sizing.spec.js` | **sin confirmar** — ver arriba |
| Frontend completo | **sin ejecutar** — falta memoria |
| Build | **sin ejecutar** — falta memoria |

El arreglo de deduplicación **sí** se verificó revirtiéndolo: 3 de sus 6 tests
fallan sin él.

---

## Otros dos pendientes de siempre

- **Rotar `OPENSKY_CLIENT_SECRET`.** Sigue en claro en el historial de
  conversación. Está en `.env`, ignorado por git, y en ningún archivo
  versionado. Re-verificado en este commit.
- **`npm run lint` no funciona**: no hay configuración de ESLint en el
  repositorio, en ninguna rama ni en ningún commit. Figuraba como limpio y era
  falso.

---

## Documentos

| Archivo | Qué es |
|---|---|
| `README.md` | Entrada al proyecto |
| `MANUAL.md` | Guía de uso para el operador |
| `AERORF_ARCHITECTURE.md` | Decisiones de diseño |
| `AERORF_CHANGELOG.md` | Cada cambio, con su motivo (0.16.0 → 0.27.4) |
| `docs/archive/AERORF_AUDIT.md` | Por qué se quitó cada parte del SIARI |
