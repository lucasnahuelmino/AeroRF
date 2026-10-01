# Punto de retorno — AeroRF

**Fecha:** 2026-09-30
**Estado:** funcional y verificado. Rama `main` en `origin/main`.

---

## 0.29.0 — El mapa toma el ancho que le dan

**Lo que pediste, hecho:** mapa más ancho, paneles más compactos, logo de
AeroRF más grande, y el de ENACOM con pie de página.

**El hallazgo que de verdad explica lo del ancho:** `MapEngine.invalidateSize()`
existía y **no lo llamaba nadie**. Abrir o cerrar un panel, o arrastrar su
borde, dejaba el mapa con el tamaño del momento de cargar. Medido: con el
sidebar abierto el contenedor mide 584 px y Leaflet sigue dibujando en 800 — los
216 px del sidebar muertos y el mapa aplastado a la izquierda. Por más que se
agranden los paneles, eso no se arregla: el mapa no se redibuja en el espacio que
le acaban de dar. Ahora un watcher le avisa.

**Verificado revirtiéndolo en el navegador**, porque en los tests de la cabecera
el shell del mapa no se monta: con el watcher neutralizado, 584 contra 800; con
el watcher, los cuatro estados cuadran.

Cambios: paneles de 268+300 a **216+256**; padding de tarjetas de `p-3` a
`p-2`; shell a `calc(100dvh - var(--brandbar-h) - var(--footerbar-h))` — con el
pie, el mapa se salía 74 px de la pantalla; logo de AeroRF de 30 a **34 px**; logo
de ENACOM oficial sobre **ficha blanca**, porque es RGB(11, 23, 66) y sobre la
barra oscura no se ve; pie nuevo de 26 px con el logo a 12 px y el nombre de la
Dirección, en todas las pantallas.

**342 tests frontend en verde.** Detalle en `AERORF_CHANGELOG.md`, sección
0.29.0.

---

## Dos cosas que conviene no volver a tropezar

**Un fixture con otra forma que el dato real hace pasar un test roto.** El
enganche al centro llevaba roto desde 0.27.0 y sus tests en verde: el fixture
armaba el círculo con `latlng` como **array**, y el código lo leía como
`centre[0]`, que en un array funciona y en el `{lat, lng}` que manda la API da
`undefined`. Es la misma trampa que el panel del punto central.

**Un test que cuelga el proceso no es una guarda.** Con el bucle de suscripción
puesto, la corrida no terminaba nunca en vez de fallar. La guarda se reescribió
para confirmar la figura a mano, sin pasar por el clic, y comparar la
*identidad* del handler: desuscribirse y volver a suscribirse deja el conteo en
uno igual, y el conteo no ve nada.

---

## Aviso sobre la memoria de la máquina

Si vitest se cuelga en «RUN» y no imprime nada, **no es el código**: es memoria.
La máquina bajó a 0,7 GB libres de 5,8 y mis ejecuciones en segundo plano
dejaban procesos vitest zombis. Matar primero:

```powershell
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -match "vitest" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Y no tocar el dev server del proyecto hermano `rni-app-4.0`, que tiene el 8000.

**Ojo también con `layout.spec.js`:** lee el CSS *construido*, así que hay que
reconstruir antes de correrlo o pasa con el `dist` viejo. Por eso una guarda
revertida puede dar verde sin motivo.

---

## 0.29.1 — Las cinco herramientas que no guardaban la forma

**El hallazgo de fondo, y no era de aspecto.** `stores/map.js` traducía a GeoJSON
leyendo solo `latlngs`, pero `draw.js` emite los vértices como
`properties.path` (línea, traza, medición) o `properties.ring` (polígono,
cobertura). Para esas cinco, la traducción tomaba la salida temprana: **línea,
polígono, cobertura y traza se guardaban como `Point` en su primer vértice, y
medición sin geometría ninguna.** El pedido era exitoso y aparecía «Creado», así
que se leía como «no guarda» en vez de como un error. Círculos y radiales
funcionaban porque llevan centro y medida.

Ahora `toApiPayload` busca `path` y luego `ring` si no hay `latlngs`.

**Once tests de `objects.spec.js` estaban en verde sobre esto**, porque sus
fixtures usan `latlngs`: un campo real que la traducción maneja bien, y la forma
que **nada en la aplicación produce**. Nueve pruebas nuevas con los payloads
reales; siete fallan al revertir el arreglo.

Las otras tres cosas del mismo lote: las cinco pestañas de la barra lateral —el
strip necesitaba 312 px y tenía 215, y con `flex: 1 1 0` «Expediente» quedaba
completamente fuera— ahora son icono + rótulo corto; el menú de clic derecho **no
tenía fondo**, porque `bg-slate-900/98` no es un paso de opacidad de Tailwind y la
clase nunca se generó; y el cursor del mapa es `crosshair` en vez de la mano que
tapaba el punto del clic.

**355 tests frontend en verde.** Detalle en `AERORF_CHANGELOG.md`, sección
0.29.1.

---

## 0.29.2 — El mapa no se movía: había un escudo invisible encima

**El bug era real y está arreglado.** Detrás del menú de clic derecho había un
escudo `fixed inset-0`, `pointer-events: auto`, `z-index: 1240`, que cerraba el
menú con `@click`. Con el menú abierto ese `DIV` estaba encima del mapa: un
arrastre movía **0 m** en lugar de 16.906 m, y el menú seguía abierto — porque
**un arrastre no produce `click`**, así que el escudo sobrevivía al gesto entero.

**Arreglo:** se eliminó el escudo. El cierre es ahora un listener de `mousedown`
en `document`, en fase de captura y sin detener la propagación, de modo que la
misma pulsación cierra el menú **y** arranca el desplazamiento. Verificado:
primer arrastre con el menú abierto, 16.906 m y el menú se cierra.

**Lo que sigue sin reproducirse** es la forma exacta que describió el operador
(«se mueve y vuelve atrás»). Faltan tres datos suyos: si el **zoom con la rueda**
funciona, si **vuelve exactamente al origen** o se detiene a mitad, y **cuánto se
mueve** antes de volver. Con esos datos se cierra el caso.

**Dos errores míos, corregidos y anotados:**

- Medí «solo se puede desplazar una vez por carga» y estuve a punto de
  «arreglarlo». Era mi arnés: lanzaba `mousemove` sobre `document`, así que
  `e.target` era el `document`, que no tiene `className`, y el `removeClass` de
  Leaflet reventaba a mitad de `finishDrag`. Con los eventos apuntando al elemento
  correcto, cuatro arrastres seguidos funcionaron.
- La primera guarda del escudo filtraba por `getBoundingClientRect()`, y **en
  jsdom no hay layout**: todos los rectángulos valen cero, así que no podía
  encontrar nada, ni siquiera al bug. Pasaba con el escudo puesto. Ahora comprueba
  la estructura renderizada.

**Además, un test que caducó solo:** `test_flight_history.py` falla desde el
2026-10-01 sin que se haya tocado nada. `NOW` estaba fijo en 2026-09-29 pero el
endpoint ancla la ventana al reloj real, así que la distancia crecía un día por
día y el vuelo del fixture quedó fuera. `NOW` ahora sale del reloj real; las doce
afirmaciones del archivo son relativas a `NOW`, así que no se debilitó ninguna.

**358 tests frontend · 382 Python · 675 paridad · build limpio.**

---

## Lo que queda pendiente

- **Las 16 filas duplicadas** de `aircraft_tracks` que ya había. No se borran: son
  datos del operador y la decisión es suya. El código ya no genera más.
- **Rotar `OPENSKY_CLIENT_SECRET`.** Sigue en claro en el historial de
  conversación de las últimas sesiones. Está en `.env`, ignorado por git, y en
  ningún archivo versionado.
- **`npm run lint` no funciona**: no hay configuración de ESLint en el
  repositorio, en ninguna rama ni en ningún commit. Figuraba como limpio y era
  falso. La comprobación real es el build.

---

## Verificación

| Suite | Estado |
|---|---|
| Frontend (vitest) | **358 pasan**, 27 archivos |
| Python (no integración) | **382 pasan**, 7 deseleccionadas |
| `tests/geo_parity.mjs` | 675 pasan |
| Build | limpio |

Objetos en la base: **3, los del operador** — un círculo (id 1), un radial (id 2) y
una anotación (id 3). Los 17 que se crearon al verificar se borraron.

---

## Documentos

| Archivo | Qué es |
|---|---|
| `README.md` | Entrada al proyecto |
| `MANUAL.md` | Guía de uso para el operador |
| `AERORF_ARCHITECTURE.md` | Decisiones de diseño |
| `AERORF_CHANGELOG.md` | Cada cambio, con su motivo (0.16.0 → 0.29.0) |
| `docs/archive/AERORF_AUDIT.md` | Por qué se quitó cada parte del SIARI |
