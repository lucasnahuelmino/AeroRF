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

## 0.29.3 — Los objetos borrados volvían a aparecer

**Bug de datos visuales, no de la base.** Los objetos se agregan a un
`LayerGroup` por categoría, y `removeObject()` llamaba solo a `layer.remove()`,
que **lo saca del mapa pero no del grupo**. `LayerGroup.onAdd` vuelve a agregar
todos sus hijos, así que la capa regresaba dibujada en el siguiente `restack()` —
sin handler de selección, o sea «visibles pero inactivos». Con un solo `restack()`
volvían los tres.

Lo difícil: **`map.hasLayer` y `featureLayers` decían que no**, los dos
indicadores obvios eran correctos mientras el bug estaba vivo. Las ocho pruebas
nuevas afirman sobre los **hijos del grupo**, que es lo que estaba mal. Al
revertir el arreglo fallan 8 de 16.

El mismo bug pasaba con cada actualización, porque `renderObject()` empieza
llamando a `removeObject()`: tres renderizados del mismo objeto dejaban tres
capas. `clearObjects()` y `destroy()` ahora pasan por `removeObject()` para que
haya un solo camino de baja.

**366 tests frontend · 382 Python · 675 paridad · build limpio.**

**La base quedó con 0 objetos.** Los tres del operador ya estaban borrados; los
que veías eran las capas que no se quitaban. Al reabrir no vas a ver ninguno, y
eso es lo correcto.

---

## 0.29.4 — Trayectorias, «Limpiar», y diálogos propios

**Las trayectorias se acumulaban: mismo bug de 0.29.3 en otra clase.**
`drawTrack` usa `layer.addTo(this.trackGroup)` y `removeTrack` solo llamaba
`layer.remove()`, que saca la capa del mapa pero no del grupo. Medido con dos
vuelos de `e02659`: el grupo tenía **2** hijos después del primero y **3** después
del segundo, y un `restack()` los devolvía. `clearTracks` — lo que llama «Quitar
todas» — tenía la misma fuga. Arreglado igual que 0.29.3.

**El botón «Limpiar» no limpiaba:** reseteaba todo lo *derivado* de la búsqueda y
nada de lo que el operador había escrito en la caja. Ahora vacía los cuatro campos
de `query`. No toca `tracks`: lo que limpia las trayectorias es «Quitar todas».

**Los diálogos los dibuja ahora la aplicación.** Eran siete nativos — cuatro
`confirm` y tres `prompt` usados como respaldo del portapapeles — y por eso
decían «localhost:5199 dice…». Ahora hay `systemStore.ask()` (devuelve promesa) y
`systemStore.notify()`, con `DialogHost.vue` montado una vez. «Eliminar» sale en
rojo, Escape cancela, y el fondo se cierra con `mousedown` y no con `click`, la
misma trampa del escudo del menú en 0.29.2.

Una guarda que **no deja pasar ningún `window.confirm`/`alert`/`prompt`** en todo
`src/`, y que señala archivo y línea. A propósito es de fuente: afirmar que cada
uno de los siete lugares renderiza algo pasaría igual con un octavo.

**379 tests frontend · 382 Python · 675 paridad · build limpio.**

---

## 0.29.5 — El avión que no se iba, ocho herramientas, medir en vivo, inspector

**Tercera instancia del bug del `LayerGroup`:** `syncMarkers` y `clear` llamaban
`marker.remove()`, que saca el marcador del mapa pero no lo suelta del grupo. Los
cuatro caminos de baja pasan ahora por un solo `_detach(layer)`.

**TRAZA y POLÍGONO fuera de la paleta**, que queda con 8 botones. Se van de las
herramientas, **no** de los tipos: un objeto guardado como `polygon` o `trace`
tiene que seguir dibujándose y exportándose, y borrar el tipo dejaría huérfano lo
que ya está en la base.

**MEDIR ahora lee en vivo.** Antes creaba el objeto pero **no mostraba ninguna
cifra** mientras el operador se movía. Ahora hay una caja en el punto medio del
segmento: `977.8 m · 0.528 NM · 0.978 km`, y con tres puntos el total. De paso,
las etiquetas de medición estaban en el `<style scoped>` de `GisShell.vue`, y
Leaflet construye el `divIcon` en tiempo de ejecución: nunca reciben el
`data-v-…` de un selector con scope. Medidas en **10×19 px sin fondo**; ahora
**169×19 px** con su estilo, en el bloque global junto a `.aerorf-popup`.

**El clic en un avión llena el inspector.** El clic siempre puso
`selectedIcao24` y nada lo mostraba. Ahora abre el panel con identidad,
**procedencia**, altitud, velocidad, rumbo, trayectoria con su desglose, y los
objetos RF cercanos con la nota de que proximidad no es causalidad. Si la
posición tiene más de un minuto, dice «última posición conocida».

**Un error mío que tumbó el mapa entero:** añadí el bloque de aeronave con
`v-if`, y eso le **robó el `v-else` al panel del objeto**. `v-else` se empareja con
el condicional hermano inmediatamente anterior; con nada seleccionado se
renderizaban los dos y el del objeto leía `object.color` sobre un `object` nulo.
Lo detectó que `engine` fuera `null` en el navegador, y lo confirmaron ocho
pruebas que estaban en verde.

**386 tests frontend · 382 Python · 675 paridad · build limpio.**

---

## 0.30.0 - La paleta institucional: azul oscuro, la misma familia

El operador pidió «misma familia» que `rni-app-4.0`. La paleta de ese proyecto es
`--ink: #0b1742`, que es **exactamente** el azul del logo oficial de ENACOM: no
una paleta parecida, el mismo color del que salen todos los demás.

Los tokens se copiaron **por nombre** de `frontend/src/assets/tokens.css` del
proyecto hermano, más quince propios porque un mapa es una superficie oscura
permanente con capas una sobre otra. Y existe `tokens.js` porque Leaflet pasa el
color tal cual al atributo `stroke` y ahí no hay nada que resuelva una variable.

Verificado en el navegador: fondo y barra `rgb(11, 23, 66)`, panel
`rgb(16, 29, 77)`, pestaña activa `rgb(110, 150, 255)`.

**430 tests frontend · 382 Python · 675 paridad.**

### Tres cosas que esta sección debe evitar que se repitan

1. **Un `@import` después de `@tailwind` se descarta en silencio.** El build
   salió limpio y en pantalla no había ningún color. Nada en el código fuente
   dice que falta un token: hay que preguntarle al navegador, o leer el CSS
   construido. Por eso las 44 pruebas de `tokens.spec.js` leen `dist/assets`.
2. **Había un segundo juego de tokens, y `--surface` significaba lo contrario**
   (panel oscuro acá, superficie clara en la familia). Como estaba después en el
   archivo, ganaba, y todo el texto sobre fondo oscuro iba a quedar oscuro sobre
   oscuro. Sólo `--muted` se usaba, dos veces. Borrado.
3. **Escribir código con backticks a través de PowerShell.** Cada backtick se
   come el carácter siguiente: `assets/` quedó `ssets/` y quedaron dos caracteres
   BEL dentro de un archivo de pruebas, que dejó de parsear. Salió porque la
   corrida dio «no tests» en vez de un fallo. Para acentos o backticks, la
   herramienta de escritura.

## 0.30.1 - Buscar un vuelo pasado: el archivo propio responde antes de rendirse

El operador buscó el vuelo de ayer por su nombre de vuelo y la aplicación dijo que
no había ninguna aeronave. El mensaje era cierto e inútil.

Dos defectos y una imposibilidad:

- El error de ICAO24 inválido salía **en inglés**, sin decir qué hacer, y
  **repetido cuatro veces** en cuatro rutas. Ahora hay un solo
  `_explicar_icao24_invalido`, en español, y la rama del callsign sólo se abre con
  caracteres **fuera** del alfabeto hexadecimal: decir «tiene letras» de `abc`
  sería falso, y hay una prueba con ese caso.
- El aviso de callsign ya estaba en español y **sí se veía**. Lo que no hacía era
  usar lo que la aplicación sabía.

**El arreglo de fondo.** OpenSky sólo publica vectores en vivo, así que un callsign
que no está transmitiendo no aparece, y sin dirección no hay forma de preguntar
por el historial. Pero la propia aplicación guarda la dirección de cada aeronave
que alguien siguió: medido el 2026-10-02, **45 de 47 pistas archivadas llevan
callsign, y son 17 llamadas distintas**. `search_flight` consulta ese archivo
después de los vectores en vivo —lo que está volando manda— y si lo encuentra sigue
por el historial como si le hubieran dado la dirección.

Contra el backend real: `callsign=ARG1763` → `e02659` vía
`callsign_archivo_aerorf`, 1 vuelo.

**Lo que no se inventó.** La dirección sale de una fila que el sistema escribió.
`states` —los vectores en vivo— queda vacío, y hay una prueba que lo exige:
presentar un vuelo de ayer como señal de ahora es el error que este proyecto no
quiere cometer. La procedencia se ve: «vectores en vivo de OpenSky» frente a
«archivo de vuelos de AeroRF», en el panel, no como clave interna.

**Una afirmación que no podía sostener.** La primera versión devolvía una lista
vacía cuando el archivo no se podía consultar, y el mensaje decía que no había
ningún vuelo con ese nombre —sin haberlo abierto—. Ahora `_direcciones_en_archivo`
devuelve `None` para «no pude mirar» y `[]` para «miré y no estaba», y son dos
mensajes distintos. El que sí pudo mirar dice además cuántas pistas hay.

**Sigue sin ser posible**: OpenSky no tiene búsqueda histórica por callsign, con
credenciales o sin ellas. Hay una prueba que falla si ese texto desaparece.

**438 tests frontend · 436 Python · 675 paridad · build limpio.**

### Dos guardas que no mordían

Verificar por reversión es lo único que prueba una guarda, y dos no fallaron:

- Una comprobaba que el aviso contuviera «archivo» —que tienen **los dos**
  mensajes—, así que revertir el `None` por `[]` pasaba en verde.
- La guarda de la plantilla sólo miraba que el mapa de traducciones existiera, no
  que la plantilla lo usara.

Y el arnés de reverts mentía: reportaba «todo verde» para dos reverts que **nunca
se aplicaron**, porque una cadena de PowerShell con comilla simple conserva `\n`
como dos caracteres, y los archivos son LF mientras el literal era CRLF. Un revert
que no entra es indistinguible de una guarda que no funciona. El arnés ahora
exige que cada sustitución quede escrita antes de reportar.

---

## 0.30.2 — La trayectoria en vivo se congelaba con la aeronave todavía volando

Síntoma: el operador seguía una trayectoria, la aeronave seguía moviéndose en
vivo, y la línea dejó de crecer. Dos defectos, y **ninguno era «está tapada»**.

**1. La condición que decide si la línea crece leía la lista equivocada.** El
estado vivo llega a `liveStates` y se le pega a cada fila en un `computed`
llamado `watchlistWithState`. La condición leía `watchlist`, la lista cruda,
buscando un `.state` que esa lista **no tiene**: la rama del feed vivo era código
muerto. Medido sobre sus dos aeronaves: `state` era `AUSENTE` en las dos, y
`watchlistWithState` sí las traía, con `e06543` en vuelo.

Con el defecto caía siempre a la heurística de los dos minutos sobre el final del
track, que es una mala señal: el track de OpenSky y el vector de estado son
productos distintos, y el track se queda viejo antes de que el avión deje de volar.
El síntoma era confuso porque el marcador viene del WebSocket y la línea del
sondeo: congelar uno no toca el otro.

**2. El sondeo corre cada 30 s y el caché de tracks dura 300 s.** Nueve de cada
diez sondeos recibían los mismos bytes. Ahora hay dos TTL:
`CACHE_TTL_TRACKS_S` (300 s) y `CACHE_TTL_TRACKS_LIVE_S` (30 s), y sólo el segundo
gasta créditos de más, y sólo mientras se sigue una aeronave en el aire. La vía es
explícita: `fresh` en la ruta, `ttl` en `build_track`, `ttl` en `get_track`, hasta
`_cached`.

**Yo rompí dos pruebas.** Al pasar `ttl=` a `service.get_track`, cuatro dobles de
prueba con la firma vieja recibieron un `TypeError`, que `build_track` captura y
convierte en «no hay track de OpenSky». Las dos pruebas fallaron apuntando al lugar
equivocado: no a mi cambio, sino a datos de OpenSky que estaban bien. Lo comprobé
contra la API viva antes de culpar a nadie. Un `except Exception` que convierte
cualquier fallo en «el proveedor no tiene datos» no es robustez: es ceguera.

**452 Python · 438 frontend · 675 de paridad · build limpio.** 16 pruebas nuevas,
todas verificadas revirtiendo el arreglo. La quinta no fallaba la primera vez:
nadie comprobaba que el ttl llegara hasta la caché, que es donde se vuelve efectivo.

### Lo que encontré y **no** toqué

El orden real de dibujo del canvas compartido deja `aircraft_tracks` segunda de
abajo, así que cualquier objeto con relleno se pinta encima de la trayectoria
(medido con ids). No es el defecto reportado —el relleno es de 15 % y no oculta una
línea— pero es incorrecto. Y `CATEGORY_DRAW_RANK` no consigue lo que su comentario
promete con `preferCanvas`: el canvas dibuja por orden de inserción. Queda para
decidir con calma, no para tocar a último momento.

---

## 0.30.3 - El avión por encima de cualquier cosa

**Lo que pediste, hecho:** el avión se ve por encima de todo.

**Por qué no alcanzaba `CATEGORY_DRAW_RANK`:** el mapa es `preferCanvas`, hay un
solo canvas con una sola lista ordenada por `_leaflet_id`, que se asigna al
**crear** la capa. Medido: los ids del grupo eran idénticos antes y después de
un `restack()`, porque re-agregar una capa no la renumera. El rango decide en qué
orden se re-agregan los grupos y nada más — y `aircraft_tracks` se crea al montar
el shell, antes de que exista cualquier objeto, así que estaba **segundo de
abajo** en la lista real.

**El mecanismo que sí funciona:** un pane propio, `aerorfTracksPane`, z-index
**500** (sobre `overlayPane` 400, bajo `markerPane` 600), con su canvas
`L.canvas({ pane })`. Los pane se apilan por z-index, que es DOM puro.

**Y `pointer-events: none` no es opcional:** una capa vectorial fuera del
overlayPane obtiene su propio canvas a pantalla completa y Leaflet le pone
`pointer-events: auto`; ese canvas tapa el mapa y se come todos los clics. Es el
mismo corte que ya causó un punto central en el markerPane. La regla está en
`assets/styles.css` con una guarda que falla si se borra.

**Lo que encontré al implementarlo:** la primera versión movía sólo la polilínea.
Para una pista de dos puntos `drawTrack` hace **cinco** hijos y tres seguían en el
canvas compartido (los dos puntos de waypoint y los dos extremos): la línea se
veía y los puntos no. Los extremos **no podían** pasar al pane nuevo, porque un
path ahí no recibe puntero y los tooltips «Inicio»/«Fin» se abren con el hover —
la etiqueta habría dejado de funcionar sin que nadie se enterara. Se convirtieron
en `L.marker` con `divIcon` (markerPane) y su círculo quedó en una regla global:
el contenido de un `divIcon` se monta como cadena HTML y nunca recibe el
`data-v-…` de un estilo acotado.

**Ojo con el `expect` sobre objetos de Leaflet.** La primera guarda hacía
`expect(c._renderer).toBe(engine.trackRenderer)` dentro de un `eachLayer`.
**Fallaba y el runner se quedó colgado para siempre, sin ningún mensaje**: el
formateador del diff con dos renderers adentro no termina, y al ser síncrono ni
siquiera corre `testTimeout`. Diagnosticado marcando el avance en disco con
`appendFileSync`. La regla ahora escrita en el encabezado del archivo: recoger
hechos **planos** y esperar sobre ellos.

**Verificado revirtiendo cada cosa por separado:**

| revertido | guarda que falló |
|---|---|
| `renderer: render` de los puntos | `expected 2 to be +0` |
| `L.marker` → `L.circleMarker` | `expected +0 to be 2` |
| regla `pointer-events: none` | `expected false to be true` |

---

## 0.30.4 - Las filas duplicadas de `aircraft_tracks`

Decidido por vos y borrado. **El «16» que venía arrastrando no reproduce de
ninguna forma**: ninguna agrupación da 16. Dos independientes dan **11** —misma
geometría (sha1 del `geometry`) e icao24+callsign+conteo— y es lo único
inequívoco. 53 → 42 filas, con copia previa, comprobado que **0 posiciones**
estaban apoyadas en las borradas (la clave es `ondelete="CASCADE"`), y verificado
contra la base después: **0 grupos repetidos y 0 filas sin geometría**.

La copia está en el temporal del sistema
(`C:\Users\lucas\AppData\Local\Temp\opencode\aerorf-antes-de-borrar.db`); si
querés conservarla hay que moverla. `aerorf.db` no está trackeado por git.

---

## 0.30.5 - La base en el mismo sitio, con respaldo y con versión

**Estado:** completada · auditoría de Claude, ítem **P0-06**, primero porque lo
elegiste vos.

### Por qué este y no otro

La auditoría pone P0-06 en sexto lugar y no puede ir ahí: P0-01 quiere
`nullable=False` y P0-03 quiere limpiar filas ya guardadas, y **los dos
necesitan esto primero** —una versión de esquema y un respaldo previo— para no
romper cada base que ya está instalada.

### Qué estaba mal

El default era `sqlite:///./aerorf.db`: una ruta **relativa**, resuelta contra
el directorio desde el que arrancara el proceso. `start.bat`, `uvicorn` desde
otra carpeta y el IDE cada uno creaba su propio `aerorf.db`, y lo guardado en
uno no existía en el otro. Ése es el «se perdieron los expedientes»: **no se
perdió ninguna fila, la app miraba a otra parte.**

Antes de tocar nada busqué todas las `aerorf*.db` del disco: **sólo hay una**.
No se había partido en dos todavía — esto es para que no lo haga.

También vi un `-wal` de 4 MB junto a un `.db` de 647 KB y dije que eran
transacciones sin llegar al archivo. **No lo eran**: los conteos eran
idénticos con y sin él, eran imágenes de páginas. Aquí queda corregido. Lo que
un respaldo ingenuo sí pierde es lo que se escribe con el servidor corriendo,
que es cuando se respalda: por eso el respaldo va por la API de SQLite y no por
un `copyfile`.

### Qué quedó

- Ruta **anclada a la raíz** en vez de al directorio de trabajo. No moví el
  archivo: la ubicación no era el defecto, moverlo habría sido otro riesgo.
- **Respaldo automático en cada arranque**, antes de escribir nada, en
  `respaldos/` (ignorado por git), con rotación (`RESPALDOS_CONSERVAR`, 10).
- **`VERSION_ESQUEMA` + `MIGRACIONES`.** La versión no avanza si el paso falla
  —sentencias y sello en la misma transacción— y una base de una AeroRF más
  nueva no se toca, con el aviso en español.
- Un respaldo fallido **se registra y se arranca igual**; una app que no levanta
  porque no pudo copiar es peor que una que levanta sin copiar.

### Seis reverts, once guardas que mordieron

| revert | qué falló |
|---|---|
| vuelta a la ruta relativa | 2 — *«ruta relativa, seguiría al directorio de trabajo: aerorf.db»* |
| `Connection.backup` → `shutil.copyfile` | 1 — *«el respaldo no trajo la fila escrita en el WAL»* |
| no lanzar con base más nueva | 2 — `DID NOT RAISE` |
| sello de versión que no avanza | 2 — `assert 0 == 1` |
| rotación que no borra | 2 — *«sobrevivieron los equivocados»* |
| `init_db` sin mantenimiento | 2 — *«esperaba un respaldo y hay 0»* |

La prueba del WAL demuestra el defecto, no sólo el arreglo: deja la fila en el
WAL a propósito, compara la copia del archivo (0 filas) con el respaldo (1) y
revienta si alguien vuelve al `copyfile`.

### Dos cosas de la auditoría, decididas por vos

- **P0-02 — borrar un expediente con objetos GIS vinculados: bloquear con 409.**
  Igual que ya pasa al revés, donde borrar un objeto vinculado sí está bloqueado.
- **El modelo de despliegue sigue sin decidir**, así que el middleware de
  `Origin` va acotado a los orígenes de CORS configurados: sirve tanto si cada
  técnico tiene su PC como si hay servidor compartido.

---

## 0.30.6 - El WebSocket se rendía en modo anónimo

**Estado:** completada · auditoría de Claude, ítem **P0-04**

### Lo que pasaba

Salvo credenciales, `GET /flights/live` respondía **200** y el WebSocket
mandaba `not_configured` y no consultaba nunca. Medido con dos instancias a la
vez sobre la misma base; la cuenta de peticiones es la prueba: en el log de la
instancia anónima hay **0** líneas `auth=oauth2` y **una sola** petición a
`states/all`, que es la de la ruta REST.

### Por qué

`ws.py` hacía `if not service.configured`, que pregunta «¿hay credenciales?».
Lo que importa es «¿puedo consultar estados?», que es `can_query_states` — y
OpenSky sirve `/states/all` a llamadas anónimas. **La ruta REST ya lo tenía
bien** (`flights.py::_service_or_503`: `configured or can_query_states`); el
canal de WebSocket era el único que no.

También le cambié el mensaje: decía «defina `OPENSKY_CLIENT_ID`…», que era
inútil donde lo que faltaba era activar lo anónimo.

### Un detalle de medición que vale la pena no volver a cometer

En PowerShell `$env:X = ""` **borra** la variable. `.env` la rellenaba con
`override=False` y la primera «reproducción» salió *con credenciales* sin que
se notara. Lo que funcionó fue dejarla presente pero en blanco, que `_env`
trata como ausente. El `hello` lo anunciaba (`opensky_configured`) y así se
descartó el falso negativo.

### Guardas

Cinco en `tests/test_p004_websocket_anonimo.py`, llamando a `Hub._tick` con
falsos: sin servidor, sin esperas y sin gastar crédito.

- **Antes del arreglo**: `assert 0 == 1` — «estados de salida
  `['not_configured']`».
- **Después**: 5 en verde.
- Entre ellas: que **la compuerta siga cerrada** cuando de verdad no hay forma
  de consultar (si no, la lectura obvia sería borrar el chequeo y dejar el feed
  mudo), y que la lista vacía siga ganando al chequeo de credenciales —lo que
  evita la consulta global de 4 créditos.

En vivo, con el arreglo: `opensky_configured=False`, **0** `not_configured`, y
el WebSocket pidió `states/all?icao24=e06543&icao24=e0b354`.

### Tres cosas que encontré al verificar

1. **`lost` se reenvía cada 10 s y cuelga al propio test.**
   `test_feed_does_not_flood` mide 22 s con un `while True` cuyo timeout es de
   22 s por lectura: un frame cada 10 s hace que nunca expire. **Con vigilante:
   sigue corriendo a los 150 s, sin salida.** La causa es del servidor, no del
   test: el aviso de aeronave perdida se repite sin deduplicar, justo lo que
   la §48 prohíbe. Va en su commit.
2. **`test_idle_when_nothing_is_tracked` exige lista vacía y hay 2**
   (`ARG1646`, `LVKMT`, del 02/10): falla en su precondición, no en lo que
   mide. **No se borra**; hay que adaptarlo o saltarlo si la lista no está
   vacía.
3. **`ws.py:446` manda `Unknown action: ...` en inglés**, y el aviso de
   arranque dice «flight features disabled» cuando en modo anónimo sí
   funcionan.

Los dos rojos de integración salieron contra el **código original**: el
backend del 8010 se arrancó a las 10:35, antes del arreglo, y sin `--reload`.

---

## 0.30.7 - El botón que decía «guardado» y no guardaba

P0-11, con la forma que eligió el operador (**selector de expediente en la
calculadora**).

**El defecto**, texto completo y sin suavizar:

```js
const storeResult = () => {
  alert('Resultado guardado (próximamente integrado con expediente)')
}
```

**Lo que había que saber antes de cablearlo**: eran dos arquitecturas RF
paralelas y el botón apuntaba a la fácil de confundir.

- **`eventos_rf`** (español) tiene los campos exactos del cálculo — `formula`,
  `tipo_producto`, `error_khz`, `score_probabilidad`, `expediente_id` —, no
  tiene coordenadas, **tenía `GET /expedientes/{id}/eventos` y no tenía
  escritura**. Las cuatro tablas RF estaban en **0 filas**.
- **`rf_events`** (inglés) es el acompañante de `MapObject`: exige lat/lon y
  **sí** tiene `POST /rf/events`, que es el `client.js.rf.createEvent` que
  **nadie llamaba**.

Un armónico calculado no es un punto del mapa, así que `createEvent` habría
sido guardar en la tabla equivocada. El guardado va a `eventos_rf`.

**Lo que se hizo**: `POST /expedientes/{id}/eventos` (URL manda; 404 y 400 en
español), `expedientes.crearEvento` en el mismo commit, desplegable de destino
en la calculadora, aviso en la página que distingue éxito de error, y
**«Guardados en este expediente»** en el detalle, aparte de **«Resultados del
último cálculo»**, que es memoria de sesión.

**Guardas**: 6 de backend + 5 de frontend. Por reversión, quitado el endpoint
**6 de 6 fallan**; restaurada la vista original de git **5 de 5 fallan**.

**En vivo, contra una base temporal** (no contra `aerorf.db`: no hay `DELETE`
de `eventos_rf` y una fila de prueba no se podría deshacer sin borrar el
expediente): `201` al guardar, `1` fila en el `GET` que antes daba `0`, `404`
«No existe el expediente 999999», `400` «El expediente del cuerpo (501) no
coincide con el de la ruta (1)», y el `400` **no escribió nada**.

**Un error mío que vale anotar**: el primer chequeo del `×` (U+00D7) lo hice en
PowerShell y salió `C3 83 C2 97`, o sea mojibake — parecía que el servidor
corrompía la fórmula. Repetido en Python: **`32 20 C3 97 20 38 38 2E 35`
idéntico en ida y vuelta**. PowerShell 5.1 leyó mi comando como CP1252. El
código estaba bien; el instrumento no.

**Hallazgos nuevos, sin tocar** (cada uno con su commit):

- **`GET /expedientes` corta en 10** (`limit: int = 10`) y **nadie pagina**:
  los cinco llamadores de `fetchExpedientes()` van sin parámetro y
  `ExpedientesView` no pagina. Leído en el código, **no reproducido** — con un
  solo expediente en la base no se puede ver fallar.
- **`toolbar.spec.js` falló una vez al cargar** (441/453, 12 sin correr);
  sola 12/12 y la corrida siguiente 453/453. Mismo síntoma que el flake ya
  registrado; **sin repro y sin atribución posible**.
- **Inglés en `expedientes.py`**: «Expediente not found» y «Expediente …
  already exists». Los del endpoint nuevo sí están en español.
- **Los 422 de FastAPI siguen en inglés**; la vista los traduce antes de
  mostrarlos, pero el JSON crudo sigue con «Field required».

---

## Lo que queda pendiente

### La cola de la auditoría de Claude

**Hechos: P0-06, P0-04, P0-11, el `lost` de 0.30.8, la precondición de
`test_idle` de 0.30.9, y de la fase 2: F2-01 en 0.30.10 y F2-02 en 0.30.11.**
Lo demás, con el criterio acordado: rama nueva, un commit por ítem, prueba que
falle antes y pase después, y **preguntar antes de tocar nada de «Decisiones
pendientes»**.

- **P0-01 y P0-03** — `nullable=False` sobre `numero_expediente` y limpiar las
  filas ya guardadas. **Van juntos y ya se pueden**: P0-06 les dio el respaldo y
  la versión de esquema que les faltaba.

### Fase 2 de Claude (los F2)

**Hechos:**

- **F2-01** en 0.30.10 — el candado se salteaba por los campos RF en las
  cuatro rutas tipadas. Reproducido (5 rojas, 2 verdes), arreglado con
  `require_unlocked` **antes** de escribir el satélite, una sola transacción y
  `rollback` si algo falla; el mensaje del candado pasó a español.
- **F2-02** en 0.30.11 — el historial inventaba: `getattr(obj, "rf.k")` sobre
  el objeto en vez del satélite daba `None`, así que decía que se borraron la
  frecuencia y el tipo y el cambio real (40 → 41) no aparecía. Arreglado con
  `record_typed_history`, que difumina el satélite contra su propio snapshot
  **y** al objeto padre (el `azimuth` y el `radius` copiados ahí mismo se
  iban sin registrar). 7 rojas antes, 8 verdes después.

- **F2-03** en 0.30.12 — el payload de `rf_events` no se serializaba: ni la
  respuesta del mapa, ni el GeoJSON, ni el CSV (`export_service` ya leía
  `props["event"]` y salía vacío), ni el duplicado. Arreglado con la relación
  `MapObject.rf_event` (la única que faltaba), `props["event"]` en
  `object_to_feature`, `event=` en `duplicate_object` y el Inspector pasando
  a leer `p.event.*`. 4 rojas antes, 7 verdes después; +1 en frontend,
  verificada por revertida. **La decisión de arquitectura: no unificar**
  (la comparación campo por campo queda abajo, como referencia) y
  `calculated_evento_id` **sigue sin escribirse** por decisión del
  operador: queda declarado hasta que exista un caso de uso real.

- **F2-04** en 0.30.13 — el borrado no miraba nada: `clear_layer` borraba
  por `layer_id` a secas (sin `locked`, sin `expediente_id`) y el cascade
  destruía notas, historial y anotaciones; `delete_object` bloqueaba
  expediente e hijo pero **no el candado**. **Decisión del operador:
  borrado físico con los filtros** (no baja lógica): lo libre se borra, lo
  protegido no se toca, y si tras limpiar queda algo,
  `DELETE /map/layers/{id}` **no borra la capa** y contesta 409 — con
  `Layer.objects` sin cascade, borrarla dejaría `layer_id = NULL` en los
  supervivientes. Mensajes de esa ruta en español. 4 rojas antes, 6 verdes
  después.

- **F2-05** en 0.30.15 — las entradas inválidas llegaban hasta SQLite y
  estallaban en 500: `layer_id` y `expediente_id` inexistentes (FK),
  `null` en columnas NOT NULL (`visible` al actualizar), `kind` inválido
  validado **dentro** del handler, y `opacity`/`object_id` convertidos con
  `float()`/`int()` sobre el cuerpo crudo. Arreglado en tres capas:
  chequeo de referencias y de nulidad **antes** de escribir (`map_service`),
  traductor global de validación (422 con `msg` en español, pisa el
  inglés de FastAPI) y red de `IntegrityError` → 400 para lo que no tenga
  chequeo propio. Los 14 mensajes de los validadores de `schemas_gis.py`
  pasaron a español: el traductor los muestra tal cual. 11 verdes; el
  rojo-antes quedó registrado (7 de 8 en la primera corrida, y el corte de
  `correlation` verificado por revertida: sin él, `ValueError` otra vez).
  Detalle en 0.30.15.

- **F2-06** en 0.30.16 — el update escribía `geometry` sin validar:
  `create_object` llamaba a `gjs.validate_geometry` (y el docstring de
  esa función prometía estar en el alta **y** el update), pero el PUT no
  lo hacía. El PUT contestaba **200**, guardaba el anillo roto y el
  objeto después desaparecía del mapa como «sin geometría derivable»,
  sin avisar por qué. Arreglado con el mismo chequeo, junto a los
  pre-cheques de F2-05, **antes** de tocar la fila: o entra todo el
  patch, o no entra nada. 1 roja antes (200 y `fields=geometry` en el
  log), 3 verdes después; la roja repetida **por revertida**.

Faltan, en el orden del anexo (F2-03 ya no está: el bug quedó en 0.30.12 y
la decisión de no unificar, confirmada — la tabla se mantiene como
referencia):

- **Anexo de F2-03 — comparación campo por campo de las dos arquitecturas**
  (hecha; el bug quedó en 0.30.12 y la decisión fue **no unificar**, además
  de **dejar `calculated_evento_id` como está**):

  | | **A — `eventos_rf`** (legacy SIARI) | **B — `rf_events`** (spec §34) |
  |---|---|---|
  | dueño | `expediente_id` → el **documento** | `object_id` → el **objeto del mapa** (CASCADE) |
  | qué es | **salida calculada**: `formula`, `tipo_producto`, `error_khz`, `score_probabilidad`, `proximidad` | **evento medido/reportado**: `level_dbm`, `classification`, `event_kind`, `provenance` |
  | frecuencia | `frecuencia_resultado_mhz` + `freq_1_mhz`, `freq_2_mhz` | `frequency_mhz` + `bandwidth_khz` |
  | tiempo | `timestamp` | `event_at` (duplicado de `observed_at` del padre) |
  | posición | **no tiene** | la tiene, vía su `MapObject` |
  | quién escribe | `rf_service` (motor) y el botón de P0-11 | el Inspector del mapa |
  | en la API | `GET/POST /expedientes/{id}/eventos`, `/candidates` | `GET/POST/PUT /rf/events` |

  **Recomendación: no unificar.** Son dueños distintos (documento vs.
  dibujo), semánticas distintas (producto intermodulado vs. medición) y ya
  están enlazadas por `rf_events.calculated_evento_id → eventos_rf.id`. Una
  tabla única tendría ~10 columnas nulas sin sentido en un lado y rompería
  el `ORDER BY score_probabilidad` del motor y el cascade del mapa. **El
  modelo ya lo dice en su docstring** («kept untouched for the RF engine»).
  Lo único flojo de ese enlace: `calculated_evento_id` **está declarado y
  nadie lo escribe** (3 apariciones: modelo, schema y changelog) —
  **resuelto: se queda como está.** Decisión del operador en esta fase:
  no se inventa el vínculo, y se elimina el día que haya un caso de uso real
  (o nunca).
- **F2-07** — un `BackoffController` para los tres pools: un 429 de `/tracks`
  pausa también el feed en vivo.
- **F2-08** — `import_geojson` no pasa `source` y queda `"user"`. No necesita
  migración (no hay `CheckConstraint` en ningún modelo), pero sí hay que agregar
  la etiqueta en `MapEngine.js:1028` o muestra el valor crudo en inglés.
- **Decisión de Épsilon: el historial ya contaminado de F2-02** — y antes de
  decidir, **contarlo** (`field LIKE 'rf.%' AND new_value IS NULL`).

**Correcciones que le hice a la fase 2** (verificadas contra el código): los
números «reales» que da están desactualizados (**482 + 30 / 453**, no 452/438);
«86 endpoints» hoy son **88** (66 paths, medido con `openapi()`); 19 tablas sí;
`update_reference` **sí** tiene el candado salteable (no lo había leído) y además
cambia `db_obj.radius` sin historial; y **el repo es público** (`"private":
false`), con `r1.txt`…`r6.txt` y `siari.db` en el historial — **el `.env`
nunca entró**, sólo `.env.example`.

**Encontrado al verificar P0-04 y P0-11, sin tocar** — cada uno con su repro, cada uno
con su commit propio:

- **Nadie lee `lost`.** El inundador se arregló en 0.30.8 (se deduplica y
  `test_feed_does_not_flood` volvió a pasar), pero el frontend **no tiene
  manejador**: una búsqueda por `frontend/src` da una sola coincidencia y es
  prosa. El marcador de una aeronave que se fue sigue quedando en pantalla,
  que era justo lo que el comentario del código quería evitar. O se agrega el
  manejo, o se quita el frame — **decisión del operador**, porque cambia cómo
  se ve el mapa.
- **`ws.py:446` manda `Unknown action: ...` en inglés** al navegador.
- **El aviso de arranque dice «flight features disabled»** cuando en modo
  anónimo las de vuelo sí funcionan.
- **`GET /expedientes` corta en 10 y nadie pagina** — los cinco llamadores van
  sin parámetro y la pantalla de expedientes muestra a lo sumo 10 sin decirlo.
- **`toolbar.spec.js` flaky, tres veces.** Una al cargar en corrida completa
  (441/453), sola 12/12 y 453/453 después; después 4 pruebas en 3 archivos
  distintos en una corrida que tardó 210 s, con los mismos 3 archivos en verde
  (37/37) y la completa en verde (453/453). **Sin repro.**
- **`smoke_e2e.py` espera 15 capas y hoy se siembran 17** (`lines` y
  `polygons`, del 26/09): el chequeo `count == 15` **falla también en base
  limpia**, o sea que es expectativa vieja del script y no una regresión.
- **El E2E contra `aerorf.db` deja basura.** La corrida de la verificación de
  F2-01 dejó 3 aviones falsos (`abc001`-`abc003`), 8 objetos en el mapa, una
  fuente enganchada a un expediente y un `EXP-SMOKE-001`. Todo se repuso por la
  API pública y se volvió a leer de la base (2 aviones, 2 objetos, 1 expediente,
  `eventos_rf` en 0), pero desde ahora **se corre contra una base temporal**:
  `DATABASE_URL` descartable en un puerto aparte. La prueba de ese método dio
  **77 de 78**, con la única falla del chequeo de capas de arriba.
- **P0-07** — middleware de `Origin`/`Host`, **acotado a los orígenes de CORS
  configurados**. Con el proxy de Vite el `Origin` es `5199` y el `Host` es
  `8010`: sin esa lista rechaza la interfaz entera y los tests salen verdes.
- **P0-09** — inyección de fórmulas en el CSV, **sólo en campos de texto libre**.
  Prefijar lo que empieza con `-` convertiría las latitudes negativas en texto.
- **P0-02** — decidido: **bloquear con 409**.
- **P1, `async def` → `def`** — con SQLite hay que mirar `check_same_thread`
  antes; Claude lo marca como no medido.
- **P1, correlación temporal** — subiría de prioridad. Compara el evento con las
  posiciones *actuales* y la documentación dice «espacial y temporal»; eso
  correlaciona un evento de hace tres días con tráfico de hoy. Primero corregir
  la redacción, después comparar con `observed_at`. Y `get_states()` global en
  vez de `get_states_in_box` **quema créditos de OpenSky** en cada correlación.

### Las que ya venían

- **Migrar las plantillas** de `slate-N` a nombres semánticos y borrar el puente
  de 0.30.0. Decidido por vos. Es lo que hace que los nombres dejen de mentir:
  `bg-slate-900` ahora es azul, y un desarrollador que lo escriba mañana obtiene
  `--panel` sin saber por qué. Es el cambio más grande que queda y va solo.
- **Tipografías: decidido, no implementado.** Vos elegiste adoptar las de
  `rni-app-4.0` (Space Grotesk, IBM Plex Sans, IBM Plex Mono) **y subir el
  peldaño**: IBM Plex Sans no tiene mayúsculas tan esbeltas como las del panel de
  9 px, así que la barra lateral y la de herramientas necesitan un tamaño más.
- **Pantalla de credenciales: decidida, no implementada.** Querés que si falta la
  credencial pueda ponerla el agente, con **una sola clave para todas las PCs**,
  priorizando que les funcione sin trabas. Siguen en pie dos condiciones que no
  cuestan nada y no frenan a nadie: **verificar antes de guardar** (un error de
  teclado no puede romper la instalación de todos) y **acotar a loopback**, que
  mientras el servidor escuche en `127.0.0.1` no le quita facilidad a nadie.
- **Rotar `OPENSKY_CLIENT_SECRET`.** Sigue en claro en el historial de
  conversación de las últimas sesiones. Está en `.env`, ignorado por git, y en
  ningún archivo versionado. Hay que generar una clave nueva en OpenSky y
  reemplazar la vieja; eso requiere entrar a la cuenta, así que no se puede hacer
  desde acá.
- **Un mensaje en inglés en una ruta:** «OpenSky does not accept future
  timestamps.», en las líneas 298 y 767 de `app/api/routes/flights.py`.
- **`npm run lint` no funciona**: no hay configuración de ESLint en el
  repositorio, en ninguna rama ni en ningún commit. Figuraba como limpio y era
  falso. La comprobación real es el build.
- **`CATEGORY_DRAW_RANK` sigue mintiendo en un punto:** `circles: -1` promete
  poner el disco de un círculo debajo de un radial y el rango no lo consigue. El
  avión ya no depende de él (0.30.3 usa el pane), pero esa intención sigue sin
  cumplirse.

### Si algo reaparece al cambiar una visibilidad

Lo que se corrigió en 0.29.3, 0.29.4 y 0.29.5 fue que las capas **no se quedaran
atadas al `LayerGroup`**: `layer.remove()` las saca del mapa pero no del grupo, y
`LayerGroup.onAdd` reagrega todo lo que todavía tenga.

Eso está resuelto en los cuatro caminos (`_detach` en el renderizador de
aeronaves, `removeObject`/`clearObjects` en el motor del mapa). **Lo que no se
tocó es el `restack()` en sí**: sigue invocándose desde la lógica de capas, y es
lo que reagregan los hijos de un grupo. Si alguna vez reaparece algo al cambiar
una visibilidad, el sitio a mirar es quién llama a `restack()` y con qué estado,
no la remoción.

---

## Verificación

| Suite | Estado |
|---|---|
| Frontend (vitest) | **453 pasan**, 31 archivos |
| Python (no integración) | **497 pasan**, 7 deseleccionadas |
| Integration (`-m integration`) | **7 pasan** contra el 8010 |
| `tests/geo_parity.mjs` | 675 pasan |
| `tests/smoke_e2e.py` (base temporal) | **77 de 78** |
| Build | limpio (`✓ built in 1m 30s`) |

**Observado y sin explicar, tres veces.** La primera corrida de vitest de esta
sesión falló **1 archivo de 30**; no volvió en **10 corridas seguidas** y el
detalle se perdió por un filtro mal puesto en la salida. La segunda, ya con
31 archivos, falló **`toolbar.spec.js` al cargar** (441 de 453, 12 pruebas sin
correr): pasó sola 12/12 y la corrida siguiente dio **453/453**. La tercera,
durante la verificación de 0.30.9: **4 pruebas en 3 archivos** en una corrida
de 210 s (lo normal, 55 s), y los mismos 3 archivos solos dieron **37/37 en
10 s** y la completa **453/453 en 99 s**. Mismo síntoma, distinto archivo,
**sin repro y sin atribución posible** — en particular, no se puede decir que
sea por ningún commit ni que no lo sea; en la tercera no había ni un solo
archivo de frontend tocado. Si vuelve a fallar, no lo atribuya a la
casualidad: capture la salida entera la primera vez.

**Sobre la suite de integración** (`pytest -m integration`, 7 pruebas): no entra
en la cifra de arriba. Se corrió **contra el backend del 8010 levantado con el
código de 0.30.9**, y quedó en **7 pasan, 0 caen** en **28 s**:

- `test_feed_does_not_flood` **pasa**. Antes se colgaba — sin salida a los 150 s
  — porque `lost` llegaba cada 10 s y el timeout de 22 s por lectura nunca
  expiraba. Arreglado el inundador, el test se cae en silencio y termina.
  **(04/10: volvió a colgarse — pero ahora por `states` cada 10 s, con
  OpenSky configurado y una aeronave real transmitiendo. La dedupe de
  `lost` no alcanzaba: el test seguía midiendo *silencio* y no *tiempo*.
  En **0.30.14** la ventana pasó a ser de tiempo total, así que el corte
  ya no depende del entorno.)**
- `test_idle_when_nothing_is_tracked` **pasa desde 0.30.9**: la precondición se
  arregla sola en la prueba (vacía la lista por la API pública y la restaura en
  un `finally`), en vez de saltarse. **Costo conocido: `added_at` no se puede
  restaurar**, porque ni `GET /flights/tracked` ni `update_selection` lo
  exponen — cada corrida lo mueve a la fecha de hoy. Lo demás (`icao24`,
  `callsign`, `slot`, `color` y los tres flags) vuelve idéntico, y se comprobó
  leyendo la base después de la corrida.

Base de objetos: **0**. Los tres del operador fueron borrados; lo que se veia eran capas que no se quitaban.
una anotación (id 3). 
---

## Documentos

| Archivo | Qué es |
|---|---|
| `README.md` | Entrada al proyecto |
| `MANUAL.md` | Guía de uso para el operador |
| `AERORF_ARCHITECTURE.md` | Decisiones de diseño |
| `AERORF_CHANGELOG.md` | Cada cambio, con su motivo (0.16.0 → 0.30.11) |
| `docs/archive/AERORF_AUDIT.md` | Por qué se quitó cada parte del SIARI |
