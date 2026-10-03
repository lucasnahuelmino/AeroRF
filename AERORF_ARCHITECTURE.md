# AERORF_ARCHITECTURE.md

Cómo está construido AeroRF y por qué.

---

## 1. Principio rector

> **Todo es un objeto. Todo es una capa. Todo ocurre sobre el mapa.**

De ahí se deriva la mayor decisión del diseño: `MapObject` es la raíz
única de todo lo que el operador crea. Un círculo, una fuente
interferente y una antena son filas de la misma tabla, con tablas
satélite para sus atributos específicos.

Consecuencias:

- **Un solo CRUD.** No hay un endpoint por tipo de objeto.
- **Un historial.** `object_history` funciona para todos.
- **Un modelo de selección.** El mapa no distingue entre tipos.
- **Un camino de exportación.** GeoJSON, KML y CSV salen de la misma
  representación.

Lo que **no** es un objeto: coordenadas del cursor, el estado del zoom, la
capa activa. Eso es estado efímero de la interfaz, y vive en el store.

---

## 2. Vista general

```
┌───────────────────────────────────────────────────────────────────┐
│  Navegador — Vue 3 + Vite + Pinia + Leaflet                       │
│                                                                   │
│  GisShell.vue ── toolbar · sidebar · mapa · inspector · status    │
│       │                                                           │
│       ├── MapEngine      cartografía imperativa (sin Vue)          │
│       ├── ToolManager    estado de las herramientas GIS            │
│       ├── MeasureEngine  medición en vivo                          │
│       ├── AircraftRenderer  mentoring y trayectorias               │
│       └── stores/        map · flights · system · expedientes     │
│              │                                                        │
│              └── api/client.js (axios) ──┐                          │
└──────────────────────────────────────────┼──────────────────────────┘
                                           │  /api/v1  ·  /ws/flights
┌──────────────────────────────────────────┼──────────────────────────┐
│  Backend — FastAPI + Uvicorn            ▼                          │
│                                                                   │
│  api/routes/   map · rf_objects · flights · correlation           │
│                 export · system · ws · (rf, rf_expediente,        │
│                                          expedientes  heredados)  │
│       │                                                           │
│  services/     map_service · flight_service · opensky_service     │
│                 opensky_client · cache · geojson_service          │
│                 export_service                                    │
│       │                                                           │
│  core/         config · logging · geo · units · time               │
│       │                                                           │
│  models/       MapObject · Layer · RFSource · Antenna · …         │
│       │                                                           │
│  database/     SQLAlchemy (SQLite ahora, PostgreSQL/PostGIS luego) │
└───────────────────────────────────────────────────────────────────┘
```

---

## 3. Backend

### 3.1 Por qué FastAPI y no Flask

El enunciado nombra Flask. El repositorio ya usaba FastAPI con Uvicorn,
que es el servidor ASGI requerido. FastAPI cubre el mismo contrato REST
y además:

- **WebSocket nativo**, que el spec exige (§48). Flask necesitaría
  `flask-sock` aparte.
- **Validación con Pydantic**, que el spec también nombra (§0).
- Documentación automática de 86 endpoints.

Reescribir a Flask habría sido una arquitectura paralela —prohibida por la
regla 55— y habría costado rehacer rutas, validación y WebSocket a cambio
de perder funcionalidad. Se mantiene FastAPI.

### 3.2 `MapObject` como raíz

```sql
map_objects
  id, type, name, description, category, status
  latitude, longitude            -- posición principal, Float indexado
  geometry                       -- GeoJSON: Point|LineString|Polygon
  radius, radius_unit            -- círculo
  azimuth, length_value, length_unit  -- radial
  color, icon, opacity, weight, fill_opacity, label
  layer_id, visible, locked, z_index
  expediente_id, parent_id
  source, created_by
  observed_at, valid_from, valid_to
  properties                     -- JSON libre
  fecha_creacion, fecha_actualizacion
```

Satélites 1:1 por `object_id`: `rf_sources`, `antennas`,
`reference_points`, `measurements`, `rf_events`.

Una fuente interferente es, a la vez:

- un objeto del mapa (seleccionable, movible, ocultable, con capa),
- una fuente con frecuencia, potencia y tipo de señal,
- una fila con historial de cambios,
- una nota con historial propio,
- un elemento de una capa,
- un exportable en GeoJSON.

Sin duplicar nada de eso.

### 3.3 Trazabilidad

Tres tablas, deliberadamente separadas porque responden a preguntas
distintas:

| Tabla | Pregunta | Naturaleza |
|---|---|---|
| `object_notes` | «¿Qué se anotó y cuándo?» | **Solo-append.** No hay método de actualización en el servicio |
| `object_history` | «¿Cómo llegó este objeto a su estado actual?» | Un renglón por campo modificado, con valor anterior |
| `annotations` | «¿Qué hay anotado en este lugar del mapa?» | Nota geolocalizada |

El caso del enunciado —hoy `ACTIVA`, mañana `APAGADA`, después
`REACTIVADA`— produce tres renglones en `object_history` con
`Activo → Apagado → Activo → Cerrado` y los tres textos en `object_notes`.
Ningún cambio borra el anterior.

### 3.4 Geometría: por qué dos representaciones

`MapObject` guarda la posición **dos veces**, a propósito:

| Columna | Tipo | Para qué |
|---|---|---|
| `latitude`, `longitude` | `Float`, indexado | Toda consulta espacial real: caja envolvente, orden por distancia, correlación dentro de N NM. SQL plano, idéntico en SQLite y PostgreSQL |
| `geometry` | `JSON` | La forma autoritativa para geometría arbitraria (vértices de traza, anillos de polígono) y fuente directa de la exportación GeoJSON |

**Por qué no PostGIS desde el primer día:** la columna JSON mantiene
SQLite como ciudadano de primera clase. AeroRF debe poder arrancar y
operar sin un servidor de base de datos. La migración a PostGIS es:

```sql
ALTER TABLE map_objects
  ADD COLUMN geom geometry(Geometry, 4326);
UPDATE map_objects
  SET geom = ST_GeomFromGeoJSON(geometry::text)
  WHERE geometry IS NOT NULL;
CREATE INDEX ON map_objects USING GIST (geom);
```

Ninguna línea de código de aplicación cambia. El servicio de mapas sigue
usando las columnas `Float` para las consultas (PostGIS también las
soporta) y `geometry` para exportar.

### 3.5 OpenSky: créditos y procedencia

Tres pools de créditos independientes. El sistema entero está diseñado
alrededor de eso:

| Medición | Dónde |
|---|---|
| **No se sondea si no hay nada en seguimiento** | `Hub._tick` — una consulta sin `icao24` es global: 4 créditos |
| Caché particionada por pool | `CreditAwareClient` — un track cacheado nunca sirve para states |
| TTL distintos por pool | states 10 s, tracks/flights 300 s |
| Estimación de coste | `estimate_track_credits()`, `estimate_states_credits()` |
| Un solo query para 5 aviones | `icao24` repetido = 1 crédito |
| Endpoint más específico primero | `/flights/aircraft` si se conoce el ICAO24 |
| Recorte de la ventana al límite del endpoint | `_clamp()` |
| Un solo refresh de token bajo concurrencia | `asyncio.Lock` en `TokenManager` |
| Un solo request upstream bajo concurrencia | *single-flight* en `TTLCache` |
| Pausa total ante 429 | `BackoffController` compartido por los tres pools |
| `upstream_calls` cuenta ejecuciones reales | Envuelve la factory, no la petición |

**Sobre las trayectorias.** OpenSky documenta que `/tracks` es
experimental y que sus waypoints se seleccionan por reglas —al menos uno
cada 15 minutos, un giro superior a 2,5°, un cambio de altitud superior a
100 m, un cambio de estado en tierra—, **no** uno por segundo. Por eso
`t.parse_track()` devuelve `mean_step_s` y una nota legible, y
`build_track()` no interpola jamás. Si faltan datos, la respuesta lo dice.

**Sobre la causalidad.** ADS-B no registra emisiones electromagnéticas. La
distancia entre una aeronave y un evento de intermodulación no identifica
ninguna fuente. `/correlation/*` devuelve la proximidad espacial y
temporal y lleva la advertencia en el payload, para que viaje con los
datos a cualquier exportación.

### 3.6 Procedencia

Cinco valores, aplicados a cada dato y conservados de extremo a extremo
(spec §58):

| Valor | Significado | Ejemplo |
|---|---|---|
| `observed` | Dato observado | Medición en sitio |
| `historical` | Track de OpenSky | Trayectoria histórica |
| `live` | Vector de estado actual | Posición en vivo |
| `calculated` | Derivado por AeroRF | Distancia, correlación, círculo |
| `user` | Tecleado por el operador | Radio, azimut, descripción |

El origen se etiqueta en el modelo (`MapObject.source`,
`AircraftTrack.source`, `RFSource.provenance`), viaja en la respuesta de
la API, aparece en el Inspector del panel lateral, en la leyenda de la capa de
capas, y en las exportaciones.

### 3.7 Seguridad

- Las credenciales viven solo en `backend/.env` (`.env` está en
  `.gitignore`).
- `Settings.masked()` es la única forma de serializar la configuración, y
  expone `opensky_configured: bool`, nunca el valor.
- `SecretValue` envuelve el token: `str()` devuelve `***`. Un
  `logger.info(token)` accidental no puede filtrarlo.
- `RedactingFilter` es la segunda barrera, applied a cada registro.
- No existe ruta de código desde la API hasta las cadenas de secreto.
- Test dedicado: `/system/config` no contiene ninguna clave de secreto.

### 3.8 Logging

`AeroRFLogger` acepta campos estructurados libres. `event`, `msg` y el
nivel son **solo posicionales** (marcador `/` a propósito): sin eso, un
campo llamado `level` —el contador de backoff— colisionaría con el
parámetro del método y lanzaría `TypeError` desde dentro del logger, en el
peor momento posible. Ese fallo ocurrió y está corregido.

---

### 3.9 Datos de referencia: por que NO van en la base

Los puntos de referencia de aeródromo (ARP) son hechos publicados: un código ICAO
y una coordenada no cambian entre sesiones y son los mismos para todo operador.
Viven en `frontend/src/data/airports.js`, generados por
`tools/build_airports.py` desde OurAirports.

No van en `map_objects` a propósito:

- Sembrarlos en cada instalación los mezclaría con el trabajo del operador en la
  misma tabla, donde un punto de referencia podría pasar por algo que él dibujó.
- Una corrección posterior tendría que pelear con las filas que dejó la
  instalación anterior.
- La capa se redibuja del archivo en cada arranque, así que mostrarla, ocultarla
  o filtrarla por país **no cambia nada en la base**.

El archivo es generado, no escrito a mano. La versión manual tenía cuatro códigos
ICAO duplicados, cuatro IATA duplicados, dos pares de coordenadas idénticas con
nombres distintos, y coordenadas que no pertenecían a ningún aeródromo. Todo
parecía verosímil, que es exactamente el riesgo: un operador midiendo protección
contra interferencias alrededor de un ARP equivocado produce un informe
equivocado con absoluta confianza. `SAAD`, por ejemplo, no existe: el de Rosario
es `SAAR`. Eso se verificó contra la fuente.

`tools/build_airports.py` informa los códigos que pidió y no encontró, para que
un vacío nunca sea silencioso.

## 4. Frontend

### 4.1 Por qué `MapEngine` es una clase y no un composable

Leaflet tiene estado propio: panes, registros de capas, manejadores de
eventos, una sesión de dibujo en curso. Si eso viviera en un objeto
reactivo, cada `mousemove` dispararía un render de Vue. El motor es
imperativo y se registra con `markRaw`; Vue se entera por callbacks
explícitos (`engine.on('click', …)`).

Consecuencia práctica: `MapEngine.js` no importa Vue, Pinia ni el router.
Es reutilizable y testeable fuera de la aplicación.

### 4.2 El orden de coordenadas es una frontera, no un detalle

Tres sistemas, tres órdenes:

| Sistema | Orden | Dónde |
|---|---|---|
| Leaflet | `[lat, lon]` | `map/geo.js`, las herramientas, `MapEngine` |
| GeoJSON / la API | `[lon, lat]` | `geometry` en la base, la exportación |
| El operador | lo que escribe | el panel deOBJETOS |

`latlngs` no es un campo que el esquema declare, así que Pydantic lo descarta
en silencio y una línea se guardaba con cero puntos. La conversión vive en
`toApiPayload`, en el store, porque ese es el único punto por el que pasa todo
lo que se escribe. Un `if` en cada componente sería ocho lugares donde las dos
órdenes pueden divergir.

La geometría se valida **al escribir**, no al leer. Leer asumía que lo almacenado
estaba bien formado, así que un anillo con números planos producía un 500 en
todo el listado: un objeto malo vaciaba el mapa.

### 4.3 `map/geo.js` no importa Leaflet

La geodesia vive en un módulo sin dependencias, en lugar de repartida
entre `draw.js`, `measure.js` y el store —que era exactamente el estado
inicial, con tres copias de la conversión NM/KM.

Al no importar Leaflet, se puede ejecutar en Node. Eso habilitó
`tests/geo_parity.mjs`, que pide a Node y a Python el mismo conjunto de
vectores y los compara:

- 615 comprobaciones: distancias, rumbos, puntos de destino, vértices de
  círculo, ida y vuelta de radiales.
- El formato de coordenadas se compara **como texto**, byte a byte.

Si el JS y el Python divergieran un decimal, el operador vería un valor en
la barra de estado y otro en el Inspector, y las distancias de un expediente
no coincidirían con la pantalla. La paridad lo hace imposible por
construcción.

### 4.4 Un solo mapa

| Antes | Después |
|---|---|
| `MapView.vue` (330 líneas, enrutado) | `GisShell.vue` (todo el shell) |
| `RFMap.vue` (355 líneas, dashboard) | `AircraftRenderer` |
| `MapasView.vue` (839 líneas, **código muerto**) | `draw.js` + `measure.js` |

Las tres duplicaban la inicialización de Leaflet, la capa de tiles, los
*layer groups* y `normalizeFlightPath()`. Cambiar un estilo exigía tres
ediciones.

### 4.5 Estado

| Store | Contenido |
|---|---|
| `map` | Objetos, capas, selección, herramientas, cursor, distancias |
| `flights` | Búsqueda, lista de seguimiento, en vivo, sesiones, replay |
| `system` | Conectividad, cursor espejado, panels |
| `expedientes` | Expedientes (store SIARI existente, conservado) |

El cursor se refleja en `map` y en `system` para que los componentes que
no son el mapa puedan leerlo.

### 4.6 WebSocket

El cliente envía `{"action": "track", "icao24": [...]}` para acotar el
feed a lo que realmente sigue, lo que reduce el tráfico de forma
sensible. El servidor compara cada estado con el último enviado y **solo
transmite si algo cambió**: un avión estacionado no genera tráfico. Los
mensajes de estado (`not_configured`, `throttled`) se envían **una vez**,
no en cada tick, porque un Feed que se repite cada 10 s es exactamente lo
que el spec §48 prohíbe.

> **Dependencia no evidente:** uvicorn no trae soporte WebSocket. Sin
> `uvicorn[standard]` o `websockets`, responde *«Unsupported upgrade
> request»* y `/ws/flights` devuelve 404 — el feed en vivo falla entero y
> en silencio. Está en `requirements.txt` con una nota, y cubierto por
> `tests/test_websocket.py`.

---

## 5. Flujo de trabajo del inspector

El recorrido que describe el enunciado, y qué lo implementa:

| Paso | Dónde |
|---|---|
| Buscar `ARG1234` | `FlightPanel` → `flightsStore.search()` |
| Ver la posición actual | `AircraftRenderer` + WebSocket |
| Ver la trayectoria disponible | `/flights/{icao24}/track` → polilínea coloreada por procedencia |
| Activar seguimiento en vivo | `POST /flights/tracked` (máx. 5) |
| Grabar trayectoria | `POST /flights/sessions` |
| Agregar fuente interferente | Menú contextual o `POST /rf/sources` |
| Crear radio de 20 NM | Herramienta Círculo |
| Crear radial de 135° | Herramienta Radial |
| Agregar evento RF 118,300 MHz | `POST /rf/events` |
| Ver todo simultáneamente | Capas + FILTER |
| Distancia avión → fuente | `GET /correlation/aircraft/{icao24}` |
| Guardar y asociar a expediente | `PUT /map/objects/{id}` con `expediente_id` |
| Agregar nota «Fuente apagada» | `POST /map/objects/{id}/notes` |
| Una semana después, editar el estado | `PATCH /map/objects/{id}/status` |
| Mantener el historial | `object_history`, nunca se borra |

---

## 6. Extender el sistema

### Agregar un tipo de objeto

1. Añadir el tipo a `OBJECT_TYPES` en `app/models/constants.py`.
2. Si tiene atributos propios, crear la tabla satélite y la relación en
   `MapObject`.
3. Añadir el payload a `MapObjectCreate` y conectarlo en
   `map_service.create_object()`.
4. Añadir un color e icono por defecto.

No hace falta tocar el router, el historial, el GeoJSON ni la exportación:
todo pasa por `MapObject`.

### Agregar un endpoint de OpenSky

1. Añadir el método a `OpenSkyService`, reutilizando `_request()` para
   el manejo de errores y `_cached()` para el control de créditos.
2. Elegir el pool correcto (`states`, `tracks`, `flights`) — el TTL y la
   contabilidad se heredan solos.
3. Si el endpoint devuelve 404 como «sin datos», devolver `None` en vez
   de lanzar.

### Cambiar la geometría de referencia

`app/core/geo.py` y `frontend/src/map/geo.js` implementan la misma
geodesia. Si se cambia una, hay que cambiar la otra y volver a ejecutar
`node tests/geo_parity.mjs`, que lo verifica.

---

## 7. Pruebas

| Suite | Qué cubre | Comando |
|---|---|---|
| `tests/test_geo.py` (88) | Unidades, distancias, rumbos, círculos, radiales, trazas, formato | `pytest tests/test_geo.py` |
| `tests/test_opensky.py` (74) | TokenManager, parser de states y tracks, caché, backoff, 401/404/429/5xx | `pytest tests/test_opensky.py` |
| `tests/test_opensky_contract.py` (25) | **Contrato contra una captura real** de OpenSky | `pytest tests/test_opensky_contract.py` |
| `tests/test_opensky_anonymous.py` (20) | Modo sin credenciales: qué funciona y qué no | `pytest tests/test_opensky_anonymous.py` |
| `tests/test_geojson.py` (35) | Conversión bidireccional, orden de coordenadas, features | `pytest tests/test_geojson.py` |
| `tests/test_map_objects.py` (70) | CRUD, notas, historial, estados, bloqueo, consultas espaciales, grabación, lista de seguimiento | `pytest tests/test_map_objects.py` |
| `tests/test_opensky_flights_contract.py` (24) | **Contrato real** de `/tracks/*` y `/flights/*`: camelCase, altitudes imposibles, resolución | `pytest tests/test_opensky_flights_contract.py` |
| `tests/walkthrough_real.py` (43) | **Recorrido §57 contra OpenSky real** — gasta créditos | `python tests/walkthrough_real.py` (backend activo) |
| `tests/test_websocket.py` (7) | Ciclo de vida, suscripción, anti-inundación | `pytest tests/test_websocket.py` (backend activo) |
| `app/rf_engine/test_rf_engine.py` (30) | Motor RF heredado | `pytest app/rf_engine` |
| `tests/geo_parity.mjs` (675) | Paridad JS ↔ Python | `node tests/geo_parity.mjs` |
| `tests/smoke_e2e.py` (78) | Recorrido completo por HTTP real | `python tests/smoke_e2e.py` |
| `frontend/tests/geo.spec.js` (36) | Geodesia del navegador: unidades, rumbos, azimuth, formato | `npm run test:geo` |
| `tests/test_geometry_validation.py` (21) | Geometria validada al escribir, lectura defensiva, orden de coordenadas, import de `func` a nivel de modulo | `pytest tests/test_geometry_validation.py` |
| `tests/test_error_icao24.py` (34) | Mensaje en español al rechazar una dirección de aeronave inválida, y que el texto en inglés de antes no sobrevive en el código | `pytest tests/test_error_icao24.py` |
| `tests/test_busqueda_por_archivo.py` (20) | Buscar por callsign cuando la aeronave no está volando: el archivo propio resuelve callsign → ICAO24 | `pytest tests/test_busqueda_por_archivo.py` |
| `tests/test_trayectoria_viva.py` (16) | Por qué la trayectoria en vivo se congelaba: el TTL de la caché contra el intervalo de sondeo | `pytest tests/test_trayectoria_viva.py` |
| `tests/test_p006_base_y_respaldo.py` (14) | **P0-06**: ruta de la base anclada a la raíz y no al directorio de trabajo, respaldo que atraviesa el WAL donde un `copyfile` no llega, y versión de esquema que no avanza si el paso falla | `pytest tests/test_p006_base_y_respaldo.py` |
| `tests/test_flight_history.py` (12) | Histórico de vuelos sin instante: elegir el vuelo del informe y no el último que voló el avión | `pytest tests/test_flight_history.py` |
| `tests/test_trajectory_contract.py` (7) | Contrato de `loadTrack`: la clave duplicada que devolvía la lista de seguimiento en vez de la ruta | `pytest tests/test_trajectory_contract.py` |
| `tests/test_track_dedup.py` (6) | Que pedir el mismo vuelo dos veces no meta la trayectoria dos veces | `pytest tests/test_track_dedup.py` |
| `frontend/tests/objects.spec.js` (11) | Traduccion `latlngs` -> `geometry`, cierre de anillo, acumulacion de lineas | `npm run test:objects` |
| `frontend/tests/airports.spec.js` (31) | Unicidad de los datos, capa conmutable, filtro, medicion desde aeropuerto | `npm run test:airports` |
| `frontend/tests/layout.spec.js` (15) | **Proporciones del shell**, leidas del CSS construido: mapa flexible, paneles plegables, area de las herramientas, logo acotado | `npm run test:layout` |
| `frontend/tests/components.spec.js` (43) | **Montaje real en jsdom**: el shell completo, los 8 paneles, `MapEngine`, `ToolManager`, `MeasureEngine`, `AircraftRenderer` | `npm run test:components` |
| `frontend/tests/canvas-hit-targets.spec.js` (8) | **Que recibe un clic con `preferCanvas`**: ningun panel propio, seleccionar no reordena el lienzo, un disco no le gana a una linea | `npx vitest run tests/canvas-hit-targets.spec.js` |
| `frontend/tests/track-above.spec.js` (10) | **Que el avion se vea por encima de todo**: trayectoria en su propio pane y no en el canvas compartido, extremos como marcadores para conservar el hover, y `pointer-events: none` en el pane. Solo compara datos planos: un `expect` sobre dos renderers de Leaflet deja el runner colgado para siempre | `npx vitest run tests/track-above.spec.js` |

**Total: 466 de Python sin integración (15 archivos) + 7 de integración + 30
del motor RF heredado + 675 de paridad + 448 de frontend + 78 E2E + 43 de
recorrido real.**

El 466 se mide con `pytest -m "not integration"`; el 7 de integración son los de
`test_websocket.py`, que van con `--m integration`. **Los 30 de
`app/rf_engine/test_rf_engine.py` no los recoge un `pytest` a secas**:
`pytest.ini` dice `testpaths = tests`, así que ese directorio queda fuera por
defecto y hay que pedirlo a mano con `pytest app/rf_engine` — lo comprobé:
pasan los 30, pero hasta ahora nadie los estaba ejecutando. (Antes esta línea
decía «357 unitarias», un número que ya no reproducía.)

### 7.1 Segunda capa: montar los componentes de verdad

La suite de Python no alcanza para verificar la interfaz, y no por una cuestion
de cobertura sino de naturaleza: **el compilador SFC acepta codigo que lanza en
cuanto `onMounted` corre**. Una llamada a un helper inexistente, un store
accedido antes de `createPinia()`, un `onMounted` sin importar: todo pasa el
build y revienta en pantalla.

Por eso existe una capa que monta los componentes sobre jsdom. No es
decorativa: en la primera corrida encontro cinco defectos que llevaban a
produccion, entre ellos un `MapEngine` que descartaba la opcion `container` y
dejaba el mapa sin inicializar nunca.

Regla practica: **un componente Vue se considera verificado cuando existe un
test que lo monta**, no cuando compila.

### 7.2 Tres capas, y por que la tercera es obligatoria

| Capa | Que detecta | Que no detecta |
|---|---|---|
| Suites de Python | Logica de negocio, geodesia, API, persistencia | Nada de interfaz: el backend no sabe que existe un `.vue` |
| vitest + jsdom | Errores de ejecucion al montar: helpers inexistentes, `onMounted` sin importar, stores mal accedidos | Proporciones. jsdom no calcula diseno ni renderiza Leaflet |
| `layout.spec.js` sobre el CSS construido | "La clase no esta en la salida", la unica forma de fallar en silencio | Nada de logica |

La tercera capa existe por un motivo concreto. `styles.css` no tenia
directivas `@tailwind`, asi que el escaner de contenido recorria los `.vue`
y no emitia ninguna clase: toda utilidad era una clase muerta. El build
pasaba, el lint pasaba, los tests de Python pasaba, y el mapa se dibujaba a
la mitad de su ancho con un logo de 1024 px encima. Solo una asercion que
mire la salida de PostCSS puede ver eso.

La regla que sale de ahi: **una clase utilitaria de la que depende el layout
tiene que estar verificada en el CSS final**, no en el marcado que la usa.

### 7.3 Que la prueba sea real

Cada correccion de un defecto de ejecucion se comprobo revirtiendo el arreglo
y confirmando que el test correspondiente cae. Un guardian que nunca se ha
visto fallar no es un guardian.

### 7.4 Marcadores

La suite se parte en dos para que el ciclo corto siga siendo corto:

```powershell
pytest -m "not integration"   # 336 tests, ~7 s, sin backend
pytest -m integration         # 7 tests, requiere el backend en 8010
```

Los tests de WebSocket esperan dos intervalos de sondeo para comprobar que el
feed no inunda, y por eso tardaban mas de 240 s junto al resto. El marcador
`real` (recorridos que gastan credenciales de OpenSky) nunca se ejecuta solo.

### 7.5 La red no se toca

Ninguna prueba por defecto contacta OpenSky. Se ejercita con
`httpx.MockTransport`, de modo que la renovacion de token, el replay ante 401,
el backoff ante 429 y el "sin datos" ante 404 se prueban de verdad sin gastar un
credito ni necesitar credenciales. Los contratos estan fijados a capturas
reales, no a lo que dice la documentacion.



---

## 8. Verificación de una sesión

```powershell
# Backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Frontend (en otra terminal)
cd frontend
npm install
npm run dev

# Comprobaciones
.\.venv\Scripts\python.exe -m pytest tests app/rf_engine -q
node tests/geo_parity.mjs
.\.venv\Scripts\python.exe tests\smoke_e2e.py
```

---

## 9. Deuda técnica conocida

Registrada sin adornos, con el motivo:

| Deuda | Motivo |
|---|---|
| Sin Alembic | El esquema se crea con `create_all`. Alembic hace falta antes de la primera migración real de datos |
| Caché en proceso | Correcto para un operador único. Con varias instancias habría que ir a Redis |
| Sin autenticación de usuarios | El spec no la pide. `object_notes.user` y `object_history.user` ya la soportan cuando se añada |
| `Chart.vue` sigue usando plotly | Aislado en un *lazy chunk* de 4,6 MB. Se puede sustituir por un SVG cuando se quiera |
| `Vistas` de expediente no son GIS | Son pantallas de gestión de casos. La vista geográfica es `GisShell.vue` |
| `start.bat` sin verificar | Requiere revision manual tras los cambios de puerto. `start.sh` se elimino en 0.23.0 porque se habia separado del `.bat` sin que nadie lo notara (8000 contra 5173) |
| Suite de frontend con jsdom | Monta los componentes, no los pixels. jsdom no renderiza Leaflet de verdad: la geometria, el layout y el aspecto siguen sin verificar visualmente |
| Sin prueba end-to-end de navegador | Vitest + jsdom detectan fallos de ejecucion, no de apariencia. Un panel que se solapa o un texto que se sale sigue sin detector |
| **jsdom no puede verificar la interaccion del mapa** | `layer.fire('click')` se salta el hit-testing y el apilado de CSS, que es justo donde estuvo el bug de 0.27.3. Un test en jsdom **no puede** detectar que un elemento invisible se come los clics. Para eso hace falta un navegador de verdad, y las guardas se escriben sobre las propiedades que el navegador tiene, no sobre un clic simulado |

---

## 10. Lo que este sistema se niega a hacer

Estas restricciones están en el código, no solo en la documentación:

1. **Fabricar vuelos.** No existe modo de demostración. Si OpenSky no
   tiene datos, la respuesta lo dice.
2. **Interpolar historia.** Los huecos de un track se reportan como huecos.
3. **Rellenar campos ausentes.** Sin velocidad no se pone 0; se pone
   `null` y la interfaz muestra «dato no disponible».
4. **Afirmar causalidad.** La correlación espacial lleva la advertencia en
   el payload.
5. **Perder historial.** Las notas no se sobrescriben; los cambios de
   estado se registran uno a uno.
6. **Borrar sin permiso explícito.** Un objeto ligado a un expediente no
   se borra sin `cascade=true`; vaciar una capa exige lo mismo.
7. **Exponer secretos.** Ni al frontend, ni a los logs, ni por error.
8. **Inundar el cliente.** El WebSocket solo manda cambios.
9. **Gastar créditos sin contarlos.** Tres pools separados, TTL
   distintos, y una estimación del coste antes de cada consulta cara.
