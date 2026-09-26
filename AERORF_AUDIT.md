# AERORF — Auditoría de repositorio

> Auditoría ejecutada sobre el código real, con el backend y el frontend levantados
> y cada afirmación verificada por ejecución, no por lectura estática.
>
> Fecha: 2026-09-25 · Commit base: `b3f432c` · Python 3.13.9 · Node 24.19.0

---

## 1) Resumen ejecutivo

El repositorio es **SIARI**, un motor de cálculo de interferencias RF (armónicas,
intermodulación, ranking) montado sobre FastAPI + Vue 3 + SQLite. La matemática RF es
sólida y está bien testeada. La capa **GIS no existe**: no hay persistencia espacial,
no hay motor cartográfico, no hay seguimiento de vuelos real, no hay historial.

Tres hallazgos dominan el diagnóstico:

1. **El sistema de vuelos inventa datos.** `flights.py` genera rutas rectas de tres
   puntos entre aeropuertos con horarios fabricados. Esto viola directamente el
   principio de no inventar datos y es el mayor riesgo de credibilidad del proyecto.
2. **Hay tres implementaciones de mapa** en el repositorio, de las cuales solo una
   está conectada. La más completa (839 líneas) es **código muerto**.
3. **Ningún objeto GIS se persiste.** Todo el "GIS" actual vive en `localStorage`.
   Si se cierra el navegador, se pierde todo. Falla el criterio de aceptación #28.

La base es reutilizable. La estrategia correcta es **extender y reconectar**, no
reescribir: se conserva el motor RF, la gestión de expedientes y el stack, y se
construye encima la capa GIS que falta.

---

## 2) Arquitectura actual verificada

### Backend — funciona

| Elemento | Estado verificado |
|---|---|
| Framework | FastAPI 0.141.1 (instalado); `requirements.txt` pide 0.109.0 |
| Servidor ASGI | Uvicorn — arranca correctamente |
| ORM | SQLAlchemy 2.1.1 |
| Base de datos | SQLite `siari.db` — 4 tablas, **0 filas** |
| Validación | Pydantic 2.13.5 |
| Testing | pytest 7.4.4 — **29 pasan, 1 falla** |
| Dependencias nativas | El motor RF es Python puro. **No necesita numpy ni pandas** |

**15 endpoints registrados** (verificados vía OpenAPI):

```
GET    /health
GET    /api/v1/expedientes/            POST   /api/v1/expedientes/
GET    /api/v1/expedientes/{id}        PUT    /api/v1/expedientes/{id}
DELETE /api/v1/expedientes/{id}
GET    /api/v1/expedientes/{id}/mediciones
GET    /api/v1/expedientes/{id}/eventos
GET    /api/v1/flights/search
POST   /api/v1/rf/calculate            POST   /api/v1/rf/validate
GET    /api/v1/rf/harmonics/{freq_mhz} GET    /api/v1/rf/frequency-conflicts
POST   /api/v1/rf/expedientes/{id}/calculate
GET    /api/v1/rf/expedientes/{id}/candidates
```

### Frontend — compila

Vue 3.4 + Vite 5.4 + Pinia + vue-router + Leaflet 1.9 + Tailwind 3.4 + axios +
plotly.js. `npm run build` transforma 55 módulos sin errores. El dev server sirve
todos los `.vue` sin errores de transformación.

### Base de datos

| Tabla | Filas | Nota |
|---|---|---|
| `expedientes` | 0 | Esquema usable |
| `mediciones` | 0 | |
| `eventos_rf` | 0 | Es el **producto de cálculo**, no el evento geográfico |
| `registros_espectrales` | 0 | |

**No existe ninguna tabla geográfica.** Faltan las 16 tablas del objetivo.

---

## 3) Qué funciona — reutilizar sin tocar

Estos componentes son sólidos y se conservan:

- **`app/rf_engine/`** — completo y testeado (tolerancia, armónicas, intermod,
  ranking, clasificador). Es el activo más valioso del repositorio. **No tocar.**
- **`app/models/expediente.py`, `medicion.py`, `espectro.py`** — esquemas sanos,
  ya tienen `lat`/`lon`, se integran con la capa GIS mediante `expediente_id`.
- **`app/api/routes/expedientes.py`** — CRUD completo y funcional (verificado:
  POST + GET devuelven 200 con datos correctos). Es el andamiaje de expedientes
  que exige el objetivo.
- **`app/api/routes/rf.py` y `rf_expediente.py`** — API del motor RF, ya operativa.
- **`app/services/rf_service.py`** — puente motor RF ↔ BD, reutilizable.
- **Leaflet 1.9 ya instalado** — no hace falta añadir ninguna librería de mapas.
- **Pinia, vue-router, Tailwind, axios ya instalados** — no añadir más.
- **`frontend/src/data/airports.js`** — 5 aeropuertos argentinos con lat/lon reales;
  sirven de semilla para la capa `AIRPORTS`.

---

## 4) Problemas detectados

### P1 — El motor de vuelos inventa datos *(crítico)*

`app/api/routes/flights.py`, función `build_route()`:

```python
'midpoint': [(origin['lat'] + destination['lat']) / 2 + 0.2,
             (origin['lon'] + destination['lon']) / 2 - 0.2]
```

Construye una **recta de dos puntos con un desplazamiento fijo de +0.2/−0.2 grados**
entre dos aeropuertos, y `sample_flights()` la devuelve como si fuera un vuelo real.
Resultado verificado en ejecución:

```json
{"callsign":"AR101","origin":"EZE","destination":"COR",
 "departure_time":"2026-09-25T16:12:47Z","arrival_time":"2026-09-25T17:37:47Z",
 "path":[[-34.8186,-58.5358],[-32.871,-61.5723],[-31.3239,-64.2088]]}
```

`AR101` no existe. La ruta, los horarios y el trazado son ficticios. La UI los
presenta al inspector como vuelos. **Esto es lo opuesto al objetivo del proyecto.**
Además, `arrival_time` se calcula como `now + 1h25` para cualquier vuelo.

Además, la ruta OpenSky real tiene estos defectos:

- Sin autenticación. Usa `urllib` anónimo (hoy OpenSky **exige** OAuth2).
- `urlopen` sin manejo de 401 / 404 / 429 / 5xx ni timeout diferenciado.
- Sin caché: cada búsqueda es un credit de `states`.
- Confunde `last_contact` con `time_position` (línea 126: `state[3] or state[4]`) —
  el `last_contact` es un entero 17, y se usa como si fuera un timestamp Unix.
- `build_opensky_route()` inserta el aeropuerto en la ruta como si la aeronave
  hubiera despegado de ahí, y devuelve `destination: 'N/A'`. Infiere origen sin dato.

**Decisión:** eliminar el modo `sample` por completo y reescribir el módulo sobre
`OpenSkyService` real. No se conserva ni un solo dato fabricado.

### P2 — Tres implementaciones de mapa, una sola conectada *(crítico)*

| Archivo | Líneas | Estado | Persistencia |
|---|---|---|---|
| `views/MapView.vue` | 330 | **Enrutado** (`/map`) | ninguna |
| `components/maps/RFMap.vue` | 355 | Usado en Dashboard (compacto) | ninguna |
| `views/MapasView.vue` | **839** | **CÓDIGO MUERTO** | ninguna |

`MapasView.vue` no está en el router ni importado en ningún archivo — verificado por
grep, cero referencias. Contiene la lógica de herramientas más avanzada del repo
(punto, línea, polígono, círculo, radio, medición, registro de evento) pero todo
es efímero y se pierde al recargar.

Las tres duplican: `normalizeFlightPath()`, la capa de tiles OSM, los layer groups
y el render de marcadores. Cambiar un estilo exige tres ediciones.

**Decisión:** construir un `MapEngine` único. La lógica de herramientas de
`MapasView.vue` se recupera como referencia; el archivo se elimina al migrarla.

### P3 — Ningún objeto GIS se persiste *(crítico)*

`frontend/src/data/` guarda **todos** los puntos, airports, estaciones FM y eventos
RF en `localStorage` bajo claves `siari:*`:

```js
const STORAGE_KEY = 'siari:points'
localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
```

`MapasView` (incluso muerto) escribe con `addPoint` / `savePoints`. Nada llega a
SQL. Se pierde al cerrar el navegador y no sobrevive a otra máquina. Falla el
criterio de aceptación #28 ("cerrar y volver a abrir sin perder los objetos").

**Decisión:** todos los objetos pasan a `map_objects` en SQL. `localStorage` se
elimina como sistema de verdad; sólo queda para preferencias de UI (capas, formato
de coordenadas, tool activa).

### P4 — OpenSky sin autenticación, caché ni control de créditos *(crítico)*

Ya detallado en P1. Sin `OpenSkyTokenManager` no hay renovación de token; sin caché
no hay respeto de límites; ante un `429` la app lanza excepción y el frontend ve un
`502` opaco. El riesgo de agotar créditos es real, tal como advierte el enunciado.

### P5 — El cursor nunca se registra *(alto)*

`stores/system.js` declara `cursor = ref({lat:null, lon:null})` y `App.vue` lo
muestra en la cabecera. **Ningún código escribe ese ref.** El `mousemove` del mapa
no existe. La casilla "Cursor" del encabezado muestra `n/a` para siempre.
Es una funcionalidad declarada y ausente.

### P6 — URL de backend hardcodeada *(medio)*

`App.vue:95` — `const backendBase = 'http://localhost:8000'`

Ruta absoluta que **evita el proxy de Vite**. En dev sirve; en cualquier otro
origen falla, y salta directo al backend sin CORS compartido. Además dispara
`/flights/search?source=opensky` sin parámetros, que consulta el mundo entero y
gasta un credit en cada carga de página.

### P7 — Conflicto de puerto y PID obsoleto *(medio)*

El puerto **8000 está ocupado por `rni-app-4.0`**, un proyecto hermano
(`C:\Users\lucas\...\VSCODE\rni-app-4.0`, PID 4936). `AeroRF/.backend.pid` contiene
`2290`, un proceso muerto. `start.bat` no puede arrancar el backend en esta máquina.

**Decisión:** parametrizar el puerto por variable de entorno en backend y proxy
(`VITE_API_TARGET`). No se toca el proceso del otro proyecto: no es de este
repositorio.

### P8 — Test roto *(bajo)*

`test_rf_engine.py:168` — `_saez_request()` pasa `tolerance_khz=10.0` explícito y
después `**kwargs` con `tolerance_khz` → `TypeError: got multiple values`.
Es un bug del propio test, no del motor. 29/30 pasan.

### P9 — Estructura de paquetes y dependencias *(bajo)*

Faltan `app/__init__.py`, `app/api/__init__.py`, `app/api/routes/__init__.py`.
Funciona sólo por *namespace packages* implícitos de Python 3.

`requirements.txt` fija `fastapi==0.109.0` y `pydantic==2.6.1`, incompatibles con
el Python 3.13 del entorno. Declara `numpy` y `pandas` que **el código nunca
importa**. No hay `.env` ni `.env.example`, y `DATABASE_URL` se lee sin cargar
`python-dotenv`, que sí está declarado.

### P10 — Bundle de 5 MB *(bajo)*

`npm run build` produce 5.058 kB (1.53 MB gzip). Causa: `plotly.js` (~3.5 MB) se
carga de forma eagerly porque `DashboardView` importa `Chart.vue` en el bundle
inicial. Se resuelve con rutas *lazy-loaded*.

### P11 — Nomenclatura *(bajo)*

El código, la API y la documentación hablan de SIARI; el objetivo es AeroRF.
`app/main.py` titula la app "SIARI — RF Interference Analysis API". Renombrar la
identidad sin romper las rutas `/api/v1` existentes.

---

## 5) Componentes a eliminar

| Componente | Motivo |
|---|---|
| `app/api/routes/flights.py::build_route` | Genera datos ficticios |
| `app/api/routes/flights.py::sample_flights` | Genera datos ficticios |
| `views/MapasView.vue` (839 líneas) | Código muerto; se migra su lógica de herramientas al MapEngine |
| `frontend/src/data/points.js` | `localStorage` como sistema de verdad |
| `data/airports.js`, `fmStations.js`, `rfEvents.js` (funciones de escritura) | Los datos pasan a SQL; conservar solo la semilla |
| `components/maps/RFMap.vue` | Duplica MapView; el Dashboard se migra al MapEngine |
| Esquemas `FlightRouteResponse` | Describen un vuelo ficticio; se sustituyen por esquemas reales |

## 6) Componentes a refactorizar

| Componente | Acción |
|---|---|
| `app/main.py` | Título AeroRF, registrar routers nuevos, WebSocket, logging |
| `app/database/database.py` | Cargar `.env`, `pool_pre_ping`, soporte PostGIS, `create_all` |
| `app/api/routes/flights.py` | Reescribir sobre `OpenSkyService`; mantener el path `/api/v1/flights` |
| `app/api/routes/expedientes.py` | Mantener; agregar associations con objetos GIS |
| `views/MapView.vue` | Convertir en shell GIS; toda la lógica pasa al MapEngine |
| `stores/flights.js` | Reescribir: buscar, seleccionar, seguir, grabar |
| `stores/system.js` | Cablear `cursor`; estado de herramientas |
| `App.vue` | Quitar URL hardcodeada; shell nuevo |
| `app/rf_engine/test_rf_engine.py` | Mover a `tests/` y arreglar el bug |

## 7) Funcionalidades faltantes

Las 16 tablas del objetivo; GeoJSON bidireccional; coordenadas de cursor
persistentes; sistema de herramientas GIS; inspector dinámico; círculos;
radiales; trazas; medición; notas append-only (`object_notes`); estados con
historial (`object_history`); OpenSky OAuth2 + `OpenSkyTokenManager`; caché por
tipo de crédito; búsqueda de vuelo; trayectorias históricas; vuelo en vivo;
grabación local (`flight_sessions`, `aircraft_positions`); seguimiento de hasta
5 aeronaves; WebSocket; `LayerManager`; correlación espacial; timeline/replay;
exportación GeoJSON/KML/CSV.

---

## 8) Arquitectura propuesta

Se **extiende** la arquitectura existente. No hay rama paralela.

```
app/
  core/
    config.py          Settings desde .env (Pydantic Settings)
    logging.py         Logging estructurado, sin secretos
    geo.py             Haversine, NM/KM/m, rumbo, destino, círculo, polígono
    units.py           1 NM = 1852 m
  database/
    database.py        Engine, sesión, init, soporte PostGIS
  models/
    (existentes)       Expediente, Medicion, EventoRF, RegistroEspectral
    map_object.py      MapObject — raíz GIS
    layer.py           Layer
    rf.py              RFSource, Antenna, ReferencePoint
    flight.py          FlightSession, AircraftPosition
    tracking.py        ObjectNote, ObjectHistory, Annotation
  services/
    (existente)        rf_service.py
    opensky_client.py  OpenSkyTokenManager
    opensky_service.py OpenSkyService (states, tracks, flights)
    cache.py           Cache por tipo de crédito + backoff 429
    map_service.py     CRUD de objetos, historial, notas
    geojson_service.py DB ↔ GeoJSON ↔ Leaflet
    flight_service.py  Sesiones, grabación, replay
    export_service.py  GeoJSON, KML, CSV
  api/routes/
    (existentes)       rf.py, rf_expediente.py, expedientes.py
    flights.py         Reescrito
    map.py             /api/map/objects
    layers.py          /api/map/layers
    rf_events.py       /api/rf/events
    rf_sources.py      /api/rf/sources
    antenas.py         /api/antennas
    objects.py         /api/objects/{id}/history | /notes
    correlation.py     /api/correlation
    export.py          /api/export
    ws.py              /ws/flights
```

Frontend:

```
frontend/src/
  map/
    MapEngine.js       Leaflet: init, capas, geometrías, selección, eventos
    layers.js          Leaflet layer factories por tipo de objeto
    draw.js            Herramientas: punto, línea, polígono, círculo, radial
    measure.js         Medición simple y multipunto
    geojson.js         Leaflet ↔ GeoJSON
  stores/
    map.js             Objetos, selección, capas, herramientas
    flights.js         Búsqueda, seguimiento (máx 5), grabación
    system.js          Cursor, backend, OpenSky, formato de coordenadas
  components/gis/
    Toolbar.vue  ToolPanel.vue  Inspector.vue  LayerPanel.vue
    CoordinateBar.vue  ContextMenu.vue  FlightPanel.vue  Timeline.vue
  views/
    GisShell.vue       El mapa, centro de la aplicación
```

### Nota sobre Flask vs FastAPI

El enunciado nombra Flask. El repositorio usa FastAPI con Uvicorn, que ya es el
servidor ASGI requerido. FastAPI cubre el mismo contrato REST más WebSocket nativo
— Flask necesitaría `flask-sock` aparte — y usa el mismo Pydantic que el enunciado
pide. Reescribir a Flask sería una arquitectura paralela prohibida por la regla 55
y obligaría a rehacer rutas, validación y WebSocket a cambio de perder
funcionalidad. **Se mantiene FastAPI.**

---

## 9) Orden de ejecución

| Fase | Contenido |
|---|---|
| 0 | Auditoría y estabilización — *completada* |
| 1 | Núcleo: config, logging, geometría, unidades, BD, modelos |
| 2 | MapEngine + objetos persistentes + inspector + coordenadas |
| 3 | OpenSky OAuth2 + búsqueda de vuelos |
| 4 | Tracks históricos |
| 5 | Vuelo en vivo |
| 6 | Grabación local de vuelos |
| 7 | Seguimiento de hasta 5 aeronaves |
| 8 | RF events, fuentes, antenas |
| 9 | Círculos, radiales, mediciones |
| 10 | Correlación espacial RF/aeronaves |
| 11 | Timeline y replay |
| 12 | Expedientes, historial y exportación |

---

## 10) Conclusión

Lo que hay es un **buen motor de cálculo RF** con un **caso de gestión de
expedientes** alrededor, envuelto en una interfaz que aparenta ser un sistema GIS.
Lo que falta es el sistema en sí: la capa geográfico persistente, el motor
cartográfico y el seguimiento real de vuelos.

La prioridad absoluta es **dejar de fabricar datos de vuelo**. Un inspector que ve
una ruta recta inventada entre EZE y COR pierde la confianza en la herramienta
para siempre, y un expediente de ENACOM sostenido sobre datos ficticios es peor
que no tener sistema.

El motor RF se conserva intacto. Los expedientes se conservan. La capa GIS se
construye encima, con `map_objects` como raíz de todo lo que el operador dibuja,
mide, sigue y documenta.

---

## 11) Auditoria de ejecucion: la interfaz nunca se habia visto

Las fases 0 a 15 se auditaron leyendo codigo y verificando la API. El shell
GIS nunca se abrio en un navegador. La compilacion SFC no lo detecta: un
componente puede pasar el compilador y lanzar en el instante en que
`onMounted` se ejecuta.

Se resolvio montando los componentes reales en jsdom (vitest + @vue/test-utils),
con la capa de API simulada. "Compila" dejo de ser la unica evidencia.
Aparecieron **cinco defectos que habrian llegado a produccion**:

| # | Defecto | Efecto real |
|---|---------|-------------|
| E1 | `MapEngine` reconstruia `this.options` y descartaba `container` | `init()` resolvia `undefined` y lanzaba. **El mapa no se inicializaba nunca: el shell entero estaba roto.** |
| E2 | `CoordinateBar.vue` usaba `onMounted` sin importarlo | `ReferenceError` al montar: la barra de coordenadas no renderizaba |
| E3 | `ContextMenu.vue` llamaba `watch_selected()`, funcion inexistente | `ReferenceError` al montar: el menu contextual no renderizaba |
| E4 | `draw.js` importaba `bearing as bearingBetween` pero llamaba `bearing()` | **La herramienta radial estaba rota por completo** en cada repintado |
| E5 | `_startCircle` / `_startRadial` se median a si mismos | El radio y el azimut tecleados se destruian: un circulo de 20 NM salia de 0 m, un radial de 135 grados salia de 0 grados |

E5 merece detalle. `_startCircle(center)` calculaba el radio desde las opciones
y acto seguido llamaba `_updateCircle(center)`, que mide la distancia del centro
a si mismo: cero. El operador que tecleaba 20 NM y hacia clic sin mover el
raton obtenia un circulo de radio cero. Se separo medicion de renderizado
(`_renderCircle` / `_renderRadial`) para que el borrador se pinte tal como se
escribio y el puntero solo lo ajuste.

Ademas, un sexto defecto de la misma familia: **`normaliseAzimuth` discrepaba
entre los dos lenguajes**. En JavaScript `-90 % 360` es `-90`; en Python es
`270`. El operador puede escribir un azimut negativo, y la misma linea se
dibujaba en bearings distintos segun donde corriera la matematica. El test de
paridad no lo detectaba porque nunca ejercito esa funcion.

Todos los defects tienen ahora un test que falla si regressan, y cada
verificacion fue comprobada revirtiendo el arreglo: sin el fix, el test cae.

### Nota sobre el alcance

Cinco de los seis solo se ven ejecutando. Ninguno aparecia en el build, en el
linter, ni en la suite de Python. La leccion se escribe sola y se suma a la de
OpenSky: **los fixtures construidos a partir de la documentacion pasan mientras
el codigo esta roto en produccion**. Un documento de API no es un contrato; el
unico contrato es lo que el servidor devuelve de verdad.
