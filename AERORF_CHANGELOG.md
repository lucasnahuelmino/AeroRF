# AERORF_CHANGELOG.md

Registro de cambios por fase. Cada fase deja la aplicación funcionando.

---

## Fase 0 — Auditoría y estabilización

**Estado:** completada

### Hallazgos verificados ejecutando el sistema

El repositorio se llamaba AeroRF pero implementaba SIARI: un motor de
cálculo de interferencias RF envuelto en una interfaz que aparentaba ser un
GIS. Tres problemas dominaban el diagnóstico.

1. **El motor de vuelos fabricaba datos.** `build_route()` construía una
   recta de dos puntos entre aeropuertos con un desplazamiento fijo de
   `+0.2 / −0.2` grados, y `sample_flights()` devolvía tres vuelos
   ficticios (`AR101`, `LA305`, `AV212`) con horarios inventados. La UI los
   mostraba al inspector como vuelos reales. Además la ruta OpenSky usaba
   `urllib` sin autenticación, sin caché y sin manejar 401/429/5xx, y
   confundía `last_contact` con `time_position`.
2. **Había tres implementaciones de mapa**, de las que solo una estaba
   enrutada. `MapasView.vue` (839 líneas, 41 KB) no estaba en el router
   ni importada en ningún archivo: código muerto.
3. **Ningún objeto GIS se persistía.** Todo vivía en `localStorage`
   bajo claves `siari:*`.

Otros: `store/system.js` declaraba un `cursor` que ningún código
escribía (la casilla «Cursor» mostraba `n/a` para siempre), `App.vue`
tenía `http://localhost:8000` hardcodeado saltándose el proxy de Vite, el
puerto 8000 estaba ocupado por el proyecto hermano `rni-app-4.0`, un test
del motor RF estaba roto, y el bundle de producción pesaba 5 MB.

### Acciones

- Auditoría completa documentada en `AERORF_AUDIT.md`.
- Entorno reproducible: `.venv` con versiones fijadas, `.env` y
  `.env.example`.
- Corregido el test roto de `app/rf_engine/test_rf_engine.py`
  (`_saez_request` pasaba `tolerance_khz` dos veces). 30/30 pasan.
- Confirmado que la base de datos estaba vacía (sin riesgo de pérdida de
  datos).

---

## Fase 1 — Núcleo: configuración, geometría, unidades, base de datos

**Estado:** completada

### Añadido

| Módulo | Responsabilidad |
|---|---|
| `app/core/config.py` | `Settings` congelado desde `.env`; credenciales OpenSky nunca exposed ni registradas |
| `app/core/logging.py` | Logging estructurado con redacción de secretos |
| `app/core/geo.py` | Haversine, rumbo, destino, círculos, radiales, trazas, formato de coordenadas |
| `app/core/units.py` | NM/KM/m y azimut; `1 NM = 1852 m` exacto |
| `app/core/time.py` | `utcnow()` compartido, reemplaza el `datetime.utcnow()` obsoleto |
| `app/models/constants.py` | Vocabularios cerrados (15 tipos, 7 estados, 10 clases RF, 7 categorías) |

### Esquema — 19 tablas (16 del objetivo + 3 heredadas)

`map_objects` es la raíz de todo objeto geográfico. Los atributos
específicos viven en tablas satélite 1:1 (`rf_sources`, `antennas`,
`reference_points`, `measurements`), de modo que una fuente interferente
es a la vez un objeto normal del mapa —seleccionable, movible, ocultable,
con historial— y una fuente con frecuencia y potencia.

La geometría se guarda dos veces a propósito: `latitude`/`longitude` como
columnas `Float` indexadas (consultas espaciales en SQL plano, idénticas
en SQLite y PostgreSQL) y `geometry` como columna JSON GeoJSON (fuente
autoritativa para exportación y geometría arbitraria). Eso hace que SQLite
sea un ciudadano de primera clase y que la migración a PostGIS sea añadir
una columna `geometry(Geometry, 4326)` poblada con `ST_GeomFromGeoJSON`,
sin tocar código de aplicación.

### Corregido

- `app/database/database.py` ahora carga `.env`, aplica WAL y
  `foreign_keys=ON` en SQLite, y siembra las 15 capas por defecto.
- Faltaban `app/__init__.py`, `app/api/__init__.py`,
  `app/api/routes/__init__.py`; el proyecto dependía de *namespace
  packages* implícitos.
- `requirements.txt` declaraba `numpy` y `pandas`, que el código nunca
  importaba. El motor RF es Python puro.

---

## Fase 2 — Motor cartográfico, objetos persistentes, inspector

**Estado:** completada

### Añadido

- **`app/services/geojson_service.py`** — conversión bidireccional
  DB ↔ GeoJSON ↔ Leaflet. GeoJSON es siempre `[lon, lat]`, Leaflet
  `[lat, lon]`. Centralizado porque el orden invertido de coordenadas es
  la causa más común de mapas silenciosamente espejados.
- **`app/services/map_service.py`** — un único camino de escritura para
  todos los objetos. Cada cambio de campo se registra en
  `object_history`; las notas son solo-append; los borrados exigen
  `cascade` explícito.
- **`app/api/routes/map.py`** — un endpoint por operación, no por tipo de
  objeto: `GET/POST /map/objects`, `GET/PUT/DELETE /map/objects/{id}`,
  más `/status`, `/move`, `/duplicate`, `/history`, `/notes`,
  `/annotations`, `/near`, `/distances`, `/from-geojson`, y
  `/map/layers`.

### Por qué un solo endpoint de creación

Un círculo, una fuente y una antena difieren únicamente en su payload, no
en su ruta. Un CRUD por tipo habría producido cuatro tablas de rutas, cuatro
historiales y cuatro selectores en el mapa. Con un `MapObject` raíz hay
una geometría, un historial, un GeoJSON y un modelo de selección.

### Corregido

- **Un bloqueo no era una trampa de ida y vuelta.** `update_object`
  rechazaba toda edición de un objeto bloqueado, incluido el
  desbloqueo: el objeto quedaba bloqueado para siempre. Ahora se permite
  exactamente una operación sobre un objeto bloqueado, `locked: false`.

---

## Fase 3 — OpenSky OAuth2 y búsqueda de vuelos

**Estado:** completada

### Añadido

| Módulo | Responsabilidad |
|---|---|
| `app/services/opensky_client.py` | `OpenSkyTokenManager` + `SecretValue` |
| `app/services/opensky_service.py` | `OpenSkyService`: states, tracks, flights |
| `app/services/cache.py` | Caché con TTL por tipo de crédito y backoff 429 |

Implementado contra el contrato publicado de OpenSky, no de memoria:

- **OAuth2 client credentials** en
  `auth.opensky-network.org/.../openid-connect/token`. La autenticación
  básica por usuario/contraseña ya no se acepta.
- Renovación `expires_in - 60 s` (los tokens duran 30 minutos), con
  `asyncio.Lock` para que diez llamadas simultáneas gasten **un** refresh.
- Reintento único ante `401`, con invalidación del token.
- `404` se traduce a «sin datos», no a error: es el comportamiento
  documentado de los endpoints `/flights/*`.
- `429` respeta `X-Rate-Limit-Retry-After-Seconds` y abre un backoff
  exponencial compartido por los tres pools.

### Créditos

OpenSky cobra `/states`, `/tracks` y `/flights` en **pools separados**, y
el coste de tracks escala con las particiones de día cruzadas (4 créditos
en vivo; 30 para 1–2; 60×N a partir de 3). Por eso:

- La caché está particionada por pool; un track cacheado nunca se sirve
  para una consulta de states.
- `estimate_track_credits()` y `estimate_states_credits()` exponen el
  coste para poder avisar antes de una consulta cara.
- `get_flights()` elige el endpoint más específico disponible —
  `/flights/aircraft` si se conoce el ICAO24 — en lugar delrangueo.
- La lista de seguimiento se consulta con **un** `icao24` repetido, que
  cuesta 1 crédito para hasta cinco aeronaves.
- El `/tracks` se limita a 30 días, y la ventana de flights se recorta al
  límite del endpoint.

### Eliminado

`app/api/routes/flights.py` completo: `build_route()`, `sample_flights()`,
`fetch_opensky_states()` con `urllib`, `find_nearest_airport()` y
`AIRPORTS` hardcodeado. **No queda ni un solo dato fabricado en el sistema.**

---

## Fase 4 y 5 — Trayectorias históricas y vuelo en vivo

**Estado:** completada

- `build_track()` combina el track histórico de OpenSky con las
  posiciones grabadas por AeroRF, **sin interpolar**. Ordena por timestamp
  y descarta duplicados exactos.
- La respuesta declara la procedencia de cada punto
  (`provenance_counts`), el número de waypoints y el paso temporal medio,
  con una nota explícita: *«los waypoints de OpenSky no son un punto por
  segundo»*.
- `parse_state_vector()` distingue `time_position` de `last_contact`
  (el error del código anterior) y prefiere la altitud geométrica
  etiquetando cuál se usó.

---

## Fase 6 — Grabación local de vuelos

**Estado:** completada

- `FlightSession` + `AircraftPosition`. Se muestrea en el bucle del
  WebSocket, no en un hilo aparte.
- Una muestra sin posición **se registra igual**, con `latitude = NULL`:
  prueba que el avión estaba seguido. La UI muestra «dato no disponible».
- Al detener la sesión se materializa un `AircraftTrack` con
  `source = "aerorf"`.

### Corregido

- **`_store_track()` no fijaba `session_id`.** Las pistas de una sesión
  quedaban huérfanas, de modo que la reproducción no encontraba nada y
  `/flights/sessions/{id}` nunca devolvía la trayectoria. Ahora se pasa
  el `session_id` y `get_session_detail()` incluye las pistas.

---

## Fase 7 — Seguimiento de hasta 5 aeronaves

**Estado:** completada

- Slots 0–4 con color fijo, límite duro en el backend (`MAX_TRACKED = 5`)
  y en la UI. La sexta aeronave se rechaza con un mensaje que explica por
  qué. Al quitar una, su slot se libera y se reutiliza.

---

## Fase 8 — Fuentes, antenas y eventos RF

**Estado:** completada

- `app/api/routes/rf_objects.py` expone `/rf/sources`, `/rf/events`,
  `/antennas`, `/references` y `/rf/summary`.
- `_coerce()` acepta tanto el cuerpo anidado de la documentación como el
  plano que se produce en trabajo de campo (`{"latitude": …,
  "frequency_mhz": …}`).
- El acimut de una antena se propaga al `azimuth` del objeto, para que la
  línea radial que dibuja el mapa coincida siempre con el ángulo
  registrado.

### Corregido

- **`_coerce()` movía el `kind` de una antena al bloque RF.** `kind:
  "Direccional"` acababa validado contra el vocabulario de fuentes FM/AM/
  5G y la creación fallaba con un 500. La Routine ahora solo rellena el
  bloque que corresponde al tipo del endpoint.
- `MapObjectCreate.model_dump()` ya devuelve dicts; el código llamaba
  `.model_dump()` sobre un dict en cinco sitios (500 en cada creación con
  payload).

---

## Fase 9 — Círculos, radiales y mediciones

**Estado:** completada

- Círculos con radio en NM/KM/m; `20 NM = 37040 m = 37.04 km` exacto.
- El inspector muestra siempre la equivalencia en la otra unidad.
- Radiales con azimut y longitud, dibujados **siguiendo la curvatura de la
  Tierra** (4 segmentos), no como una recta cartesiana: a 20 NM la
  diferencia es visible sobre Web Mercator.
- Medición simple y multipunto con distancia por tramo, rumbo por tramo,
  área y total en m/km/NM. Efímera por defecto; guardable como objeto.

### Corregido

- `midpoint()` usaba una forma cerrada de la ley del coseno esférico que
  degenera a `atan2(0, 0)` en trayectorias ecuatorianas: `midpoint(0,0,0,2)`
  devolvía longitud 0 en vez de 1. Reimplementado como «caminar media
  distancia por el rumbo inicial», reutilizando `destination_point()`, que
  ya estaba verificado.

---

## Fase 10 — Correlación espacial

**Estado:** completada

- `/api/v1/correlation/rf-aircraft`, `/object/{id}`, `/aircraft/{icao24}`.
- Bandas de 5 / 10 / 20 / 50 NM.
- **Toda respuesta lleva la advertencia de que la correlación no implica
  causalidad**, en el propio payload, para que viaje con los datos a
  cualquier exportación. ADS-B no registra emisiones electromagnéticas.

---

## Fase 11 — Línea temporal y replay

**Estado:** completada

- `Timeline.vue`: reproducir, pausar, avanzar, retroceder, buscar.
- El marcador se mueve según los **timestamps grabados**, no según la
  animación: nunca adelanta a los datos.

---

## Fase 12 — Expedientes, historial y exportación

**Estado:** completada

- `app/services/export_service.py`: GeoJSON, KML 2.2 y CSV desde la misma
  representación en memoria, para que una coordenada no pueda diferir
  entre formatos.
- El CSV usa `;` como separador para abrir directamente en Excel en
  configuración regional española.
- El GeoJSON puede embeber el historial completo.
- Los expedientes existentes de SIARI se conservan intactos y ahora se
  asocian a objetos GIS.

---

## Fase 14 — Validación contra OpenSky real

**Estado:** completada

El usuario no tenía credenciales. En lugar de esperar, se descubrió que
**OpenSky sirve `/states/all` a clientes anónimos** desde un pool de 400
créditos diarios. Eso permitió validar la mitad de vuelos contra la API
real, y encontró un bug que ningún mock podía detectar.

### El bug: el feed en vivo estaba muerto

`parse_state_vector` exigía `len(row) >= 18`. La primera llamada real
devolvió **13 369 aeronaves con 17 campos cada una**.

La causa: la documentación de OpenSky lista los 18 campos en una sola
tabla, pero esa es la forma de **`extended=1`**. El índice 17 (`category`)
solo viene cuando se pide explícitamente.

Resultado sobre la respuesta real:

```
filas en la respuesta : 13360
parseadas OK          : 0
RECHAZADAS            : 13360
```

`get_states()` habría devuelto `count: 0` para siempre, sin error y con
el mapa vacío. **Todas las pruebas con mock pasaban**, porque el fixture
lo había construido desde la tabla de la documentación — es decir, con
18 campos.

### El fix y el contrato

- `SV_MIN_FIELDS = 17`, `SV_MIN_FIELDS_EXTENDED = 18`. `category` se lee
  solo si está presente.
- `tests/fixtures/opensky_states_contract.json`: captura real de 7 KB
  (de 1,9 MB) con 24 filas que cubren las 6 formas que OpenSky emite de
  verdad, más las estadísticas de la captura completa.
- `tests/test_opensky_contract.py` (25 pruebas) fija el contrato a la
  realidad. Los mocks pueden discrepar de la realidad; una captura real no
  se puede discutir.

Después del fix: **13 360 / 13 360** parseadas.

### Segundo hallazgo: posiciones rancias

En la captura real, el `time_position` más antiguo tenía **1,5 horas**,
y 1 404 aeronaves tenían posiciones de más de 60 s — sigue
transmitiendo otros mensajes, pero no posición.

Para una herramienta de investigación, presentar eso como «en vivo» es
una mentira. Por eso:

- `parse_state_vector` calcula `position_age_s` contra el `time` de la
  propia respuesta de OpenSky (no contra el reloj local, que derivaría
  contra la ventana del servidor).
- `FlightPanel` marca en ámbar y luego en rojo la posición vencida, con el
  texto explícito: *«Posición de hace 1 h 30 min. La aeronave transmite,
  pero no reporta posición.»*

### Tercero: modo anónimo como funcionalidad

No como truco de test, sino como capacidad: un inspector de ENACOM sin
cuenta de OpenSky puede ver tráfico en vivo.

Sondeado en vivo el 2026-09-25:

| Endpoint | Anónimo | Coste |
|---|---|---|
| `/states/all` global | 200 | 4 créditos |
| `/states/all?icao24=…` | 200 | 1 crédito |
| `/states/all` bbox Argentina | 200 | 1–3 créditos |
| `/tracks/all` | 200 pero **vacío** | pool propio |
| `/flights/*` | **403** | requiere OAuth2 |

- `OPENSKY_ALLOW_ANONYMOUS` (por defecto `true`).
- Sin credenciales no se manda cabecera `Authorization`.
- `403` y `401` anónimos se traducen a un mensaje que dice qué
  configurar; no se intenta renovar un token que no existe.
- `/flights/live` responde 200; los 7 endpoints de historial devuelven
  503 **antes de gastar una petición**.
- La respuesta declara `auth: "anonymous"|"oauth2"` y lleva el aviso de
  los límites.

### Verificación real, de punta a punta

El servicio propio de AeroRF, anónimo, contra OpenSky real:

```
1) get_states(icao24=5 aeronaves)
   count=3  auth=anonymous
     39de4f  TVF26SK    40.7188,   18.7515  alt=11864.34 (geometric) v=219.07 age=0s
     ab5cb7  N831GR     36.5440, -114.5651  alt=1249.68  (geometric) v=73.05  age=0s
     4ca7b5  RYR61NG    43.3904,    5.8496  alt=11536.68 (geometric) v=226.69 age=0s

2) get_states_in_box(Buenos Aires) -> 6 aeronaves
     e80218  LAN455   -34.5567, -58.4148  alt=None      ground=True  age=150s
     e90041  CXIPR    -34.3882, -57.8703  alt=723.9     ground=False age=2s
     ...

3) cache: upstream calls 2 -> 2   (no se gastó otro crédito)
```

Y a través de la API completa, con respuesta real:

```
200  /flights/live?bbox=Buenos Aires   count=8  auth=anonymous
       e90041  CXIPR      -34.2791,  -57.9436  alt=876.3   age=2s
       e06542  ARG1817    -34.8404,  -58.9686  alt=3421.38 age=2s
       e80628  JAT731     -34.5569,  -58.4144  alt=        ground=True age=217s
       ...
```

`e80218 LAN455` y `e80628 JAT731` estaban literalmente sobre Aeroparque.
`ARG1817` es una aeronave de Aerolíneas Argentinas. Y aparecieron de
verdad los dos casos borde: aviones en tierra **sin altitud publicada**,
y una posición con 217 s de antigüedad.

### Lo que sigue sin verificar

- `/tracks/*` y `/flights/*`: requieren credenciales. El parser de tracks
  está probado contra el fixture de la documentación y contra
  `httpx.MockTransport`, **no contra una respuesta real**. Es el punto
  que queda abierto y que se cierra con un `client_id`.
- La renderización visual de `GisShell.vue`.

---

## Fase 15 — Validación con credenciales OpenSky

**Estado:** completada

Con credenciales reales se validaron los endpoints que la Fase 14 no pudo
tocar. **Dos bugs más de la misma clase que los de la Fase 14**, y una
corrección de diseño.

### OAuth2 real

| Comprobación | Resultado |
|---|---|
| Token obtenido | 1491 chars, `expires_in: 1800` |
| Margen de renovación | 60 s → 1740 s restantes (correcto) |
| Reutilización | 2ª llamada devuelve el mismo token |
| 10 llamadas concurrentes | **1 solo refresh**, 1 token distinto, 717 ms |
| Secreto en `masked()` | no aparece |
| Secreto en logs | no aparece |

### Segundo bug: `/flights/*` usa camelCase

La respuesta real contiene:

```
firstSeen  lastSeen  estDepartureAirport  estArrivalAirport
departureAirportCandidatesCount  arrivalAirportCandidatesCount
```

**No existe** `firstseen`, ni `estdepartureairport`, ni `dep_lat`,
`dep_lon`, `arr_lat`, `arr_lon`.

El código leía los nombres en minúscula de la documentación, así
que `_normalise_flight()` devolvía **todos los tiempos y aeropuertos en
`None`**. La búsqueda de vuelo funcionaría pero no mostraría nada útil.

Corregido con `_pick()`, que acepta ambas escrituras. Tras el fix:

```
first_seen   2026-09-25 17:06:14
last_seen    2026-09-25 18:54:31
duration_s   6497          <- coherente con el span del track (6451 s)
departure    None          (candidates 0: OpenSky no lo resolvió)
```

Que los aeropuertos sean `None` es legítimo y ahora **se explica**:
`departure_candidates: 0`. No se inventa nada.

### Más allá de lo mismo

Un fixture abreviado tomando índices dispersos inventó un hueco de
4202 s que nunca existió — una captura que miente es peor que no
tenerla. Rehecha como **ventana contigua** de 30 waypoints reales, y
agregado un test que verifica que los huecos del fixture no exceden el
máximo real del vuelo.

### Corrección de diseño: la resolución no es uniforme

Medido sobre tres tracks reales:

| Aircraft | min | mediana | media | max |
|---|---|---|---|---|
| TVF26SK | 5 s | 28 s | 79 s | 588 s |
| RYR61NG | 8 s | 11 s | 68 s | 890 s |
| CMP278 | 2 s | 28 s | 81 s | 852 s |

Informar «la media es 80 s» engaña: la está arrastrada por los
tramos rectos largos, y oculta que un avión en viraje genera waypoints
cada pocos segundos. Ahora `parse_track` expone `step_min_s`,
`step_median_s`, `step_max_s` y la nota dice:

> *80 waypoints en 1 h 47 min · paso mediano 28 s, mínimo 5 s, máximo
> 588 s. OpenSky agrega un waypoint al cambiar el rumbo más de 2,5°, la
> altitud más de 100 m o el estado en tierra, y al menos uno cada 15 min:
> la resolución NO es uniforme y no es de un punto por segundo.*

### Altitudes imposibles

`RYR61NG` publicó **-304 m** y `CMP278` publicó **0 m**. No son
descensos: son artefactos barométricos. En una investigación
aeronáutica, una altitud falsa en un perfil es peor que una faltante, así
que `_suspect_altitudes()` los marca en lugar de graficarlos como hecho.
`FlightPanel` lo muestra como aviso.

### Recorrido § 57 completo, con datos reales

`tests/walkthrough_real.py` — 43 comprobaciones, todas en verde, sobre
**LAN777 (`e8048a`)** en vuelo:

```
4. Trayectoria en vivo   49 waypoints, span 860 s, mediana 11 s
5. Track fusionado       49 puntos, provenance {historical: 49, aerorf: 0}
6. Seguimiento           slot 0, color #22c55e
7. Grabación           sesión creada y detenida limpiamente
8-11. Fuente 20 NM / radial 135° / evento 118.300 MHz
   → 20 NM == 37040 m == 37.04 km
12. Todo junto           4 objetos en un mismo mapa
13. Distancia            fuente a 0.0 km / 0.0 NM de la aeronave
14. Correlación        disclaimer presente
15. Exportación         GeoJSON y KML con procedencia
```

### Cuarto hallazgo: se quemaban 24 créditos por hora sin motivo

Con credenciales configuradas, los tests de WebSocket
empezaron a fallar de forma intermitente. La causa no era el test: el
bucle de sondeo estaba haciendo llamadas **reales** a OpenSky
(`auth=oauth2`, 1-2,5 s cada una, cada 10 s) durante la suite.

Al investigating, un problema mayor: si la lista de seguimiento está
vacía, `icao24` se omiteía y la petición se convertía en una
consulta **global** de 4 créditos — cada 10 s, para datos que nadie
pedía. 24 créditos por hora, todas las horas, con el navegador
abierto y nada seguido.

Ahora, sin nada en seguimiento, el servidor **no consulta** y lo dice:
`{"type": "status", "opensky": "idle"}`. Además, si una aeronave
seguida desaparece de la respuesta, el cliente recibe `{"type": "lost"}`
en vez de dejar un marcador congelado en el mapa.

Los tests de WebSocket también se hicieron independientes del estado:
ahora toleran tramas `states` y `lost` entre los mensajes de control, y
el test de inundación mide la tasa de tramas en vez de contar un
`status` concreto que con credenciales nunca se emite. Bajó de 11,5
minutos a 45 s.

### Limitación documentada de la grabación

El muestreo ocurre en el bucle del WebSocket, que arranca cuando un
cliente se conecta. Por lo tanto **grabar sin el navegador abierto no
registra nada**: AeroRF solo puede guardar lo que está observando. Es el
comportamiento correcto para una herramienta de observación, pero tiene
que estar escrito.

---

## Fase 13 — Interfaz GIS

**Estado:** completada

### El mapa es la aplicación

```
┌───────────────────────────────────────────────────────────┐
│ TOOLBAR                                                  │
├──────────────┬──────────────────────────┬─────────────────┤
│ HERRAMIENTAS │                          │ INSPECTOR       │
│ CAPAS        │      MAPA (Leaflet)      │ PROPIEDADES     │
│ VUELOS       │                          │ NOTAS           │
│ EXPEDIENTE   │                          │ HISTORIAL       │
├──────────────┴──────────────────────────┴─────────────────┤
│ CAPAS / COORDENADAS / TIEMPO                              │
└───────────────────────────────────────────────────────────┘
```

### Motor cartográfico independiente

`MapEngine` no conoce Vue, Pinia ni el router. Es imperativo a propósito:
el estado de Leaflet no debe pasar por un proxy reactivo, o cada
`mousemove` dispararía un render. Vue se entera por callbacks explícitos.

| Archivo | Responsabilidad |
|---|---|
| `map/MapEngine.js` | Leaflet, OSM, zoom, pan, clics, selección, capas, popups |
| `map/geo.js` | Geodesia pura, **sin Leaflet** — fuente única y testeable en Node |
| `map/draw.js` | Sistema de herramientas: punto, línea, polígono, círculo, radial, traza, cobertura, anotación |
| `map/measure.js` | Medición simple y multipunto |
| `map/aircraft.js` | Marcadores de aeronaves y trayectorias coloreadas por procedencia |

### Coordenadas del cursor

`CoordinateBar` muestra LAT/LON permanentemente, en decimal o GMS, con
copia al portapapeles. **Este era el punto P5 de la auditoría**: el ref
existía en el store y nada lo escribía. Ahora está conectado al
`mousemove` del motor.

### Herramientas

Diez herramientas, cada una con estado activo, cursor propio,
cancelación con `ESC`, preview en vivo, y confirmación con `Enter` o
doble clic. `Retroceso` quita el último vértice.

### Inspector

Propiedades generales para cualquier objeto, más campos específicos por
tipo, notas append-only e historial completo de cambios. Un objeto
bloqueado se puede desbloquear pero no editar.

### Capas

15 capas con visibilidad, opacidad, orden, bloqueo y zoom. Dos mapas base
(OSM y relieve). Leyenda de procedencia de datos.

### Menú contextual

Clic derecho: crear punto, evento RF, fuente, antena, círculo, radial,
referencia, anotación; dibujar línea, polígono, traza, cobertura; medir
desde aquí; copiar coordenadas.

### Vuelos

Búsqueda por callsign/ICAO24/fecha, lista de hasta 5 aeronaves con
telemetría en vivo, trayectoria, grabación, y distancias a cada referencia
con aviso de no-causalidad.

### Eliminado

| Archivo | Motivo |
|---|---|
| `views/MapasView.vue` (839 líneas) | Código muerto, no enrutado ni importado |
| `views/MapView.vue` | Reemplazado por `GisShell.vue` |
| `components/maps/RFMap.vue` | Tercera copia del mapa |
| `data/points.js`, `airports.js`, `fmStations.js`, `rfEvents.js` | `localStorage` como sistema de verdad |

Se pasó de **tres** implementaciones de mapa a **una**.

### Rendimiento

El bundle inicial bajó de **5 058 kB a ~436 kB**: `plotly` (4,6 MB) está
aislado en la vista de la calculadora, que se carga bajo demanda, y las
rutas que no son el mapa están en *lazy chunks*.

---

## Corregido en la verificación

| Problema | Dónde | Por qué importa |
|---|---|---|
| `timed()` colisionaba con el campo `event` | `core/logging.py` | `TypeError` en **toda** llamada OpenSky |
| `_emit()` colisionaba con el campo `level` | `core/logging.py` | `TypeError` al activar el backoff por 429 |
| `get_or_set` sobrecontaba llamadas upstream | `services/cache.py` | Contabilidad de créditos falsa |
| `estimate_states_credits` multiplicaba el área por 4 | `services/opensky_service.py` | Coste de crédito mal calculado |
| `Path` con valor por defecto / `Query` en path param | `api/routes/export.py` | La app no arrancaba |
| `this._toMetres()` inexistente | `map/draw.js` | La herramienta de círculo fallaría en runtime |
| `class` duplicado en un botón | `views/GisShell.vue` | Fallo de compilación |
| uvicorn sin soporte WebSocket | `requirements.txt` | **Todo el feed en vivo devolvía 404** |
| `status` repetido cada 10 s | `api/routes/ws.py` | Inundaba al cliente, contra spec §48 |

Los dos últimos se encontraron porque la verificación se hizo de verdad:
arrancando el servidor, abriendo un WebSocket y contando los mensajes.

---

## Verificación

| Suite | Resultado |
|---|---|
| `pytest tests/ app/rf_engine` | **348 pasan**, 0 avisos |
| `tests/smoke_e2e.py` (HTTP real) | **78 pasan** |
| `tests/test_websocket.py` | **6 pasan** |
| `tests/geo_parity.mjs` (JS ↔ Python) | **615 pasan** |
| `npm run build` | 123 módulos, sin errores |

`geo_parity.mjs` merece mención: pide a Node y a Python el mismo conjunto
de vectores (distancias, rumbos, puntos de destino, vértices de círculo,
formato de coordenadas) y los compara. El formato de coordenadas se
compara **como texto**, byte a byte. Si el JS y el Python divergieran, el
operador vería un valor en la barra de estado y otro en el popup, y las
distancias de un expediente no coincidirían con la pantalla.

### La lección de esta fase

`test_opensky_contract.py` existe por una razón concreta. El fixture
original lo construí desde la tabla de la documentación de OpenSky, que
documenta la forma `extended=1`. Todas las pruebas pasaban. La primera
llamada real rechazó **las 13 369 aeronaves**.

Un mock prueba lo que el programista creyó. Solo una captura real prueba
lo que el servidor manda. Los parsers de APIs de terceros deberían
fijarse a una captura real, no a la documentación.

## [0.16.0] - 2026-09-25 - Verificacion de la interfaz en tiempo de ejecucion

El shell GIS nunca se habia abierto en un navegador. Se monto en jsdom para
verificarlo de verdad, y aparecieron seis defectos que la compilacion no ve.

### Corregido

- **`MapEngine` descartaba la opcion `container`**: reconstruia `this.options`
  desde cero y no copiaba la clave, asi que `init()` resolvia `undefined` y
  lanzaba. El mapa no se inicializaba nunca.
- **`CoordinateBar.vue` usaba `onMounted` sin importarlo**: `ReferenceError` al
  montar; la barra de coordenadas no renderizaba.
- **`ContextMenu.vue` llamaba `watch_selected()`**, funcion que no existe en
  ningun archivo del proyecto. Resto de una refactorizacion.
- **`draw.js` importaba `bearing as bearingBetween` y lo invocaba como
  `bearing()`**: la herramienta radial fallaba en cada repintado.
- **El radio y el azimut tecleados se destruian al iniciar la forma**:
  `_startCircle` y `_startRadial` se median a si mismos, dejando 0 m y 0
  grados. Se separo medicion de renderizado.
- **`normaliseAzimuth` discrepaba entre JS y Python** para todo azimut
  negativo: `%` conserva el signo del dividendo en JavaScript y no en Python.
  Con doble modulo, ambos dan el mismo resultado.

### Anadido

- Suite de componentes con vitest + @vue/test-utils sobre jsdom: monta el
  shell completo, los ocho paneles, `MapEngine`, `ToolManager`,
  `MeasureEngine` y `AircraftRenderer`, y ejercita las herramientas de
  dibujo. Sin stub de canvas en la base: `MapEngine` usa `preferCanvas`, y el
  canvas se simula en `tests/setup.js` en lugar de degradar la eleccion de
  produccion.
- El test de paridad JS/Python cubre ahora `normalise_azimuth` y
  `compass_point`, con vectores negativos, mayores de 360 y en la costura de
  180. Pasa de 615 a 675 comprobaciones.
- Marcadores de pytest: `integration` (requiere backend) y `real` (gasta
  credenciales de OpenSky). La suite por defecto ya no incluye los tests de
  WebSocket, que tardaban mas de 240 s.
- Scripts `npm test`, `npm run test:geo`, `npm run test:components` y
  `npm run test:parity`.

### Verificado

- 336 tests de Python (suite rapida, sin backend) en 7 s.
- 7 tests de integracion con el backend arriba.
- 79 tests de frontend.
- 675 comprobaciones de paridad geodesica.
- Build de produccion limpio.
- Servidor de desarrollo: el proxy responde `/health`, `/api/v1/system/status`
  y `/api/v1/map/objects`; Vite transforma `GisShell.vue` y `CoordinateBar.vue`
  sin errores.

### Sin cambios en el modelo de datos

Ninguno de estos defectos afectaba la persistencia. No se toco el esquema.

## [0.17.0] - 2026-09-26 - Layout del shell: Tailwind nunca estuvo activo

Reorganizacion del frontend a partir de tres quejas concretas: el mapa era
muy chico, el logo tapaba casi todo, y las herramientas eran incomodas. Las
tres tenian la misma causa raiz.

### Causa raiz

`src/assets/styles.css` no tenia directivas `@tailwind`. Tailwind estaba
instalado, `postcss.config.js` y `tailwind.config.js` existian, y el escaner
de contenido recorria los `.vue` correctamente, pero sin directivas no se
emitia ninguna clase. **Toda clase utilitaria era una clase muerta.**

En vez de eso, alguien habia escrito a mano unas veinticinco utilidades
falsas (`.text-xs`, `.rounded-lg`, `.border`, `.text-gray-400`...) mas un
regla global `button { background: var(--primary); padding: 8px 12px }` que
convertia cada una de las diez herramientas en un rectangulo azul sobredimensionado.

La imagen de marca es un cuadrado de 1024x1024. Con `class="h-6 w-auto"`
sobre una clase que no existia, el navegador la dibujaba a su tamano
natural: un cuadrado azul de 1024 px encima de todo.

Ademas, `main { max-width: 1180px }` alcanzaba al `<main>` del shell, que es
la zona del mapa, y en un monitor ancho dejaba el mapa flotando en el medio
de espacio vacio.

### Corregido

- `styles.css`: directivas `@tailwind` activadas de verdad. Las utilidades
  falsas y la regla global de botones, eliminadas: el preflight de Tailwind
  hace ese trabajo correctamente.
- El limite de 1180 px paso de `main` a `.page-doc`, y `main.gis-map-area`
  queda sin tope para que el mapa ocupe todo el ancho disponible.
- `.aerorf-logo` y `.aerorf-logo-lg` fijan el tamano del logo en CSS, no en
  una utilidad. Una utilidad que falta no puede volver a poner 1024 px en
  pantalla.
- Logo reducido a 128x128 sin dependencias: 1409 kB -> 6,9 kB. El maestro de
  1024 px queda en el repo como original, fuera del bundle.
- `tailwindcss` declarado en `devDependencies`. Estaba en `node_modules` sin
  declararse, asi que una instalacion limpia no reproducible el build.
- Hojas de estilo de Leaflet en el CSS global: controles de zoom mas chicos,
  atribucion discreta.
- Scrollbar de 7 px en vez de 8, y sin pista visible, para que un inspector
  de 300 px no pierda ancho.

### Layout del shell

- Mapa: `flex: 1 1 auto` con `min-width: 0`. Sin esa guarda, un panel ancho
  empuja el mapa fuera de pantalla en vez de el mapa crecer.
- Inspector: ahora se pliega y se arrastra. Antes ocupaba 340 px fijos, sin
  salida.
- Panel izquierdo: 268 px por defecto (antes 320), plegable y arrastrable.
- Anchos recordados en `localStorage`.
- Barra de herramientas: 46 px, con area de accion y etiqueta, marca
  reducida, y el texto de la herramienta centrado en el espacio libre.
- Herramientas: 52 x 38 px, con etiqueta legible en vez de 0.55 rem, foco
  visible por teclado, y franja con scroll en vez de empujar los indicadores
  fuera de pantalla.
- El indicador de la herramienta activa desaparece cuando no hay ninguna
  activa, en vez de reservar un hueco.

### Anadido

- `frontend/tests/layout.spec.js` (15 tests): lee el CSS construido y
  comprueba el layout. Es la unica forma de detectar "la clase no esta en la
  salida", que es exactamente el bug que llego a produccion. Verificado
  revirtiendo el arreglo: sin las directivas `@tailwind` cae.

**Totales: 336 + 7 Python, 94 frontend (79 + 15 de layout), 675 de paridad.**

## [0.18.0] - 2026-09-26 - Vuelos en vivo, aeropuerto y persistencia de formas

Chequeo completo de functionality, con foco en vuelos en tiempo real, una capa
de aeropuertos, y el defecto que impedia dibujar lineas y poligonos.

### Corregido: las lineas y poligonos se guardaban vacios

El drafter emite `latlngs` en orden Leaflet, `[[lat, lon], ...]`, porque asi
dibuja. La API declara `geometry` en GeoJSON, `[lon, lat]`. Nada traducía
entre ambos, y `latlngs` no es un campo que el esquema declare, asi que Pydantic
lo descartaba en silencio.

El resultado era la peor clase de fallo: **la peticion era exitosa**. Volvia un
id, aparecia un aviso "Creado", y un objeto con cero puntos caia en la base de
datos. Una linea dibujada en el mapa no se podia guardar.

La traduccion vive ahora en `toApiPayload`, en el unico punto de escritura del
store, convertida e inference del `geometry_type`, y cierra el anillo de un
poligono porque GeoJSON lo exige. Verificado revirtiendo el arreglo: 8 tests
caen.

### Corregido: la geometria no se validaba al escribir

La lectura asumia la geometria bien formada. Un anillo guardado con numeros
planos hacia `TypeError` y **toda** la ruta `GET /map/objects` devolvia 500: un
objeto malo dejaba el mapa vacio. Ahora `validate_geometry` rechaza en la
escritura con un mensaje que nombra el problema, y la lectura omite un objeto
que no se puede dibujar en vez de tumbar la respuesta.

### Corregido: el panel de capas no podia cambiar nada

`from sqlalchemy import func` estaba importado **dentro** de `list_layers`, lo
que lo hacia un nombre local. Toda otra ruta que contara objetos lanzaba
NameError, incluida `PUT /map/layers/{id}`: 500. Ninguna capa se podia mostrar,
ocultar, reordenar ni volver transparente. El import es ahora de modulo.

### Corregido: la trayectoria en vivo no crecia, y no declaraba su procedencia

`/flights/{icao}/live-track` llamaba a `service.get_live_track`, que devuelve
otra forma que `/track`: sin `provenance_counts` y sin procedencia por punto, de
modo que la leyenda nunca podia llenarse y los dos endpoints discrepaban sobre
la misma aeronave. Ahora ambas pasan por `fsvc.build_track`.

Ademas la trayectoria se cargaba una sola vez y quedaba congelada. Ahora, si el
vuelo sigue en tierra, un sondeo de 30 s la deja crecer y se detiene solo al
aterrizar, al cambiar de aeronave o al cerrar el panel. Un vuelo historico no se
sondea: su track es inmutable y repetirlo gastaria credenciales.

### Anadido: capa de aeropuertos

`frontend/src/data/airports.js`: 67 aerodromos de 8 paises, **generados** por
`tools/build_airports.py` desde OurAirports.

El archivo es generado a proposito. Una version escrita a mano tenia cuatro
codigos ICAO duplicados, cuatro IATA duplicados, dos pares de coordenadas
identicas con nombres distintos, y un conjunto de coordenadas que no
pertenecian a ningun aerodromo. Todo parecia verosimil, que es el problema: un
operador calculando proteccion contra interferencias alrededor de un ARP
equivocado produce un informe equivocado con total confianza.

`SAAD` no existe; el de Rosario es `SAAR`. Eso se verifico contra la fuente.

La capa no se persiste. Las posiciones del ARP son hechos publicados, asi que
se redibujan del archivo cada vez: mostrarla, ocultarla o filtrarla no cambia
nada en la base de datos, y ningun punto de referencia puede confundirse con
algo que el operador dibujo.

- Conmutable desde la pestana Aeropuertos y desde el panel de capas.
- Filtro por pais, remembered en `localStorage`.
- Etiquetas ICAO conmutables.
- Cada simbolo se rotula como referencia, no como observacion.

### Anadido: distancia desde aeropuerto

Codigo ICAO o IATA, un clic en el destino, y la linea dibujada con la distancia
en m, km y NM, el rumbo y su nombre de rumbal. La medicion es una lectura: no
entra en `map_objects` salvo que el operador la guarde.

### Anadido: capas propias para lineas y poligonos

Compartian la capa `traces` con las trazas, asi que no habia forma de mostrar u
ocultar una sin las demas. Ahora `lines` y `polygons` son capas propias. La
siembra es idempotente: aparecieron solas, sin migracion.

### Verificado contra OpenSky real

- 12.991 aeronaves en `/flights/live`, 99,4% con posicion.
- Trayectorias en vivo de 79 a 97 puntos, todas con posicion y con
  `provenance: live`.
- WebSocket: la aeronave se mueve entre mensajes (51,3856 a 51,3656) con
  altitud, velocidad y rumbo reales.

### Tests

- `tests/test_geometry_validation.py` (21): validacion, lectura defensiva, orden
  de coordenadas, y el import de `func` a nivel de modulo.
- `frontend/tests/objects.spec.js` (11): la traduccion `latlngs` -> `geometry`,
  cierre de anillo, y que crear una linea no altera la anterior.
- `frontend/tests/airports.spec.js` (31): unicidad de los datos, capa
  conmutable, filtro, y medicion.

**Totales: 357 + 7 Python, 136 frontend, 675 de paridad.**

## [0.18.1] - 2026-09-26 - El mapa no tenia salida

El unico control de navegacion del shell empujaba a `/`, **que es el mapa**.
Un clic en el logo navegaba al mapa: un no-op silencioso. Ademas el shell
suprime el header de la aplicacion, asi que desde el mapa no se llegaba al
panel, a expedientes, a la calculadora ni al espectro.

### Corregido

- El logo lleva al panel de control, no al mapa.
- Boton explicito **Panel** en la barra de herramientas, con etiqueta y no solo
  un icono: un operador no deberia tener que descubrir una marca de 22 px para
  poder salir del mapa.
- Menu **Otras vistas** con Expedientes, Calculadora RF y Espectro. Cerrado por
  defecto, se abre bajo la barra, se cierra con Escape o con un clic fuera, y
  va teletransportado a `body` para que el z-index del mapa no lo tape.
- El logo ahora se ve como un control, con borde propio.

### Tests

Dos tests en `components.spec.js`: uno comprueba que hay un control visible
hacia el panel **y que el logo no navega al mapa**; el otro comprueba que el
menu abre y lista las tres vistas. El primero se verifico revirtiendo el
arreglo: con el logo apuntando a `/` falla.

**Totales: 357 + 7 Python, 138 frontend, 675 de paridad.**

## [0.19.0] - 2026-09-26 - Revision completa: navegacion, diseno y documentacion

Chequeo de toda la aplicacion de punta a punta, y reordenamiento de la
navegacion y del diseno.

### El menu no existia en todas partes

Habia dos cabeceras sin relacion entre si. El mapa dibujaba su propia barra de
herramientas, **sin un solo enlace** a las demas secciones; las otras vistas
tenian una cabecera de unos 130 px con cuatro tarjetas de estado. O sea: el menu
estaba en unas rutas y no en la que el operador usa todo el dia. Desde el mapa,
la unica forma de llegar a un expediente era escribir la URL a mano.

`BrandBar.vue` es ahora la unica cabecera. Fina — 48 px en el mapa, 56 px en las
vistas de documento — y **presente en las cinco secciones**, con el menu siempre
a la vista. No es un desplegable: un operador no deberia tener que abrir algo
para descubrir a donde puede ir.

Al unificarla desaparecieron de GisShell el boton del logo, el boton «Panel» y
el menu «Otras vistas», mas 3.188 caracteres de codigo muerto.

### Estilo institucional

- Fondo sobrio, filo de 1 px, sin degradados que compitan con los datos.
- Seccion activa marcada con un unico filo celeste, no con una pastilla.
- Las vistas de documento comparten escala de titulo y ritmo vertical: antes
  una era `text-3xl` y otra `text-4xl`, y parecian cuatro aplicaciones
  distintas.
- La barra ya no roba altura: 48 px frente a los 130 px anteriores.

### Logo mas grande y visible

De 22 px a 30 px. A 22 px la marca se leia como un punto de estado, no como
una marca. El tamano vive en CSS, no en una clase utilitaria, para que una
utilitaria faltante no pueda volver a dibujar el PNG de 1024 px.

### Lockup institucional ENACOM

«Dirección Nacional de Control y Fiscalización» aparece en la barra, en todas
las secciones, con su sigla.

**La marca de ENACOM no se dibuja.** Los logotipos oficiales estan protegidos,
y reproducir una imitacion dentro de una herramienta que lleva el nombre de la
institucion seria incorrecto. Lo que hay es un lockup tipografico. Si ENACOM
suministra el archivo, se coloca en `src/assets/enacom.svg` y se activa una
variable en `BrandBar.vue`; el diseno no cambia. La decision queda escrita en el
propio archivo y hay un test que la sostiene.

### Los botones de las herramientas

Los botones eran de **52 px fijos** y la etiqueta se recortaba: «Seleccionar»
necesita unos 48 px a ese tamano de fuente y «Anotación» unos 40. Un toolbar con
las etiquetas cortadas es un toolbar que no se lee de un vistazo.

Ahora el ancho lo define el contenido, con un minimo de 44 px para las
cortas. Ademas: `user-select: none` en la barra y en los botones — al apretar dos
veces la misma herramienta se seleccionaba el texto y el resaltado hacia
parecer un boton roto —, `touch-action: manipulation` para que un clic
desplazado no se convierta en un gesto de scroll, y estado `:active` al presionar.

### Documentacion

- **README.md**: que hace y que no hace, instalacion, las cinco secciones,
  arquitectura y pruebas.
- **MANUAL.md**: guia de uso. Cada seccion, las diez herramientas una por una,
  los atajos, el flujo de trabajo recomendado para una denuncia de
  interferencia y para un estudio de proteccion, y preguntas frecuentes.

### Hallazgos de la auditoria

86 endpoints en 65 rutas, todos respondiendo. El vocabulario que llena los
selectores esta completo: 16 tipos de objeto, 7 estados, 10 tipos de fuente RF,
7 clasificaciones de evento, 4 polarizaciones, 3 unidades, 7 radios de referencia
y 4 radios de correlacion.

Un unico 404: `/api/v1/measurements` no existe. No es un defecto — las
mediciones se guardan como objetos de mapa, no en un recurso aparte — pero
conviene saberlo.

### Tests

- `frontend/tests/brandbar.spec.js` (16): el menu en las cinco rutas, que no sea
  desplegable, el lockup, y altura y z-index leidos del CSS construido.
- `frontend/tests/toolbar.spec.js` (12): ancho por contenido, sin recorte,
  seleccion de texto, `touch-action` y sensacion de pulsar.

**Totales: 357 + 7 Python, 164 frontend, 675 de paridad.**

## [0.20.0] - 2026-09-27 - Revision intensiva de punta a punta

Barrido del backend y del frontend buscando defectos reales, no preferencias.

### Corregido: un id desbordado devolvia 500

Un id mayor que 2**63-1 llegaba a SQLite y lanzaba `OverflowError`, que salia
al cliente como 500. Un id que no puede existir es un error del cliente: la
respuesta es 404.Habia cinco sitios que filtraban por id, y cinco era el numero
de oportunidades de olvidarse del sexto, asi que ahora todos pasan por
`_find_by_id`.

### Corregido: `flightStore` en Timeline

La insignia de procedencia leia `flightStore.track` cuando el store es
`flightsStore`. Solo se renderiza con una sesion cargada, asi que estaba
detras de un `v-if` falso en todos los demas tests: el build, el linter y las
165 pruebas pasaban con un `ReferenceError` esperando. Hay un test que carga una
sesion y lo comprueba.

### Corregido: Espectro era un cascaron

La vista mostraba una caja con el texto "Grafico de espectro (Plotly)" y un
boton "Procesar" sin manejador. Desde el menu parecía una seccion que funcionaba.
Un control que no hace nada es peor que ningun control: le promete una
capacidad al operador que no existe.

Ahora lee CSV o TXT, en cualquiera de los formatos que usan los instrumentos de
campo (coma, punto y coma o espacios, con o sin encabezado), grafica, y señala
los picos que caen dentro de banda aeronautica con la advertencia de que un
pico no prueba interferencia. Las lineas que no se pueden leer se cuentan y se
informan, no se descartan en silencio.

### Corregido: dos gráficos en una pagina se pisaban

`Chart.vue` usaba `id="chart"` fijo. Dos graficos compartian el mismo nodo y
el segundo sobrescribia al primero sin error en ninguna parte. Ahora el id es
por instancia, y el grafico se libera al desmontar.

### Plotly: 4.640 KB a 1.095 KB

El componente dibuja scatter, bar y line, que es un 3 % de plotly. La
importacion ahora es parcial. El build bajo de 50 s a 29 s, y como el chunk es
lazy el mapa nunca lo cargo.

### Tema unificado

Las vistas de expedientes usaban `gray-*` y el color `primary` viejo, mientras
el resto usaba `slate-*` y `sky-*`. Cuatro secciones de una misma herramienta
parecian cuatro aplicaciones. Ademas `border-primary` no se genera: el=config
deja el color pero no esa utilidad, asi que esos bordes eran invisibles.

Todo mapeado por luminosidad, para que no cambie la jerarquia, solo el tono. Hay
un test que prohibe el regreso de cualquier token retirado y, en espejo,
comprueba que la paleta actual este presente: un archivo vaciado pasaria el
primer chequeo.

### Rendimiento: falso alarma aclarada

`/map/objects` tardaba 187 ms con un solo objeto. Medido por partes: 389 ms en
frio y 14,6 ms en caliente. Es el arranque del pool de conexiones, no la
consulta. No se cambio nada porque no habia nada que cambiar.

### Lo que se comprobo y estaba bien

Sin timeouts faltantes en las llamadas a OpenSky, sin consultas N+1, sin
commits dentro de bucles, sin botones sin nombre accesible, sin imagenes sin
`alt`. Los tres `except Exception` silenciosos degradan con elegancia y estan
comentados. Las funciones largas lo son por tener muchos parametros, no por
complejidad: `create_object` son 30 argumentos porque es un unico endpoint
para todos los tipos, que es exactamente lo que pide la especificacion.

### Tests

- `frontend/tests/theme.spec.js` (4): ningun token retirado, la paleta actual
  presente, y las clases usadas existen en el CSS construido.
- `components.spec.js`: Timeline con sesion cargada, sin `ReferenceError`.

**Totales: 357 + 7 Python, 169 frontend, 675 de paridad.**

## [0.20.1] - 2026-09-27 - La calculadora RF tarda en abrir

### Corregido

`Chart.vue` importaba la libreria de graficos de forma **estatica**, asi que
quedaba en el grafo de modulos de toda vista que mostrara un grafico. Abrir la
calculadora significaba descargar y parsear 1085 KB antes de que la pagina
pudiera pintar nada: la seccion parecia colgada.

La importacion ahora es dinamica. La vista se pinta primero y la libreria
llega detras, con un placeholder que dice que esta pasando. En la segunda visita
el modulo ya esta en la cache del navegador y no hay espera ninguna.

Ademas:
- El wrapper `Chart` paso de 1085 KB a **3,3 KB**: queda como un modulo
  chico que se renderiza de inmediato.
- Plotly quedo aislado en su propio chunk, que solo se descarga si hay un
  grafico que dibujar.
- La libreria se pide **una vez por pagina**, no una por grafico.
- Si la carga falla, aparece el motivo y un boton de reintento, en vez de una
  caja vacia.
- Un `modulepreload` en el HTML la descargaria desde el primer pintado, que es
  justo lo que se esta corrigiendo. Un test lo verifica.

### Como se comprueba

El bundle se lee directamente: `CalculadoraRFView` pesa 10 KB, `Chart` 3 KB, y
la libreria esta en su propio chunk. Un test comprueba las tres cosas, mas que
el mapa no crezca.

**Totales: 357 + 7 Python, 178 frontend, 675 de paridad.**

## [0.21.0] - 2026-09-27 - El circulo no se podia crear, ni medir desde un punto

Cuatro problemas reportados en la misma sesion, todos en el flujo de dibujo.

### 1. El radio tecleado se ignoraba

`ToolManager.activate` copia las opciones **una sola vez**, al activar la
herramienta. El panel de opciones si escribia en el store, pero la herramienta
ya habia capturado sus valores: poner 20 NM, hacer clic, y el circulo salia
con el valor por defecto anterior.

Ahora existe `setOptions`, y el panel empuja el cambio a la herramienta viva.
Una forma en curso no se redimensiona: su centro ya esta puesto y el operador
puede estar arrastrando, asi que moverle el radio debajo del puntero lo
confundiria. El valor nuevo aplica a la siguiente forma.

### 2. Mientras extendias el circulo no decia el radio

La etiqueta estaba sobre el anillo, y un anillo no se puede hoverar mientras se
arrastra. Extender el puntero no daba ningun numero.

Ahora hay una guia punteada del centro al puntero, con el radio en vivo
encima. Se borra al confirmar.

### 3. El circulo no se podia confirmar con un clic

Este era el grave. **Cada** clic se enviaba a `previewAt`, nunca a confirmar. La
unica forma de terminar era `Enter`, y un operador que hacia clic dos veces para
ajustar el tamano se quedaba con nada en el mapa.

Ahora el primer clic pone el centro, el puntero ajusta, y el **segundo clic
confirma**. Lo mismo para el radial. `Esc` sigue abandonando sin crear nada.

### 4. Medir desde un punto seleccionado hasta el cursor

Pedia poder medir desde un objeto ya ubicado en el mapa. Existia la medicion por
clics, pero el origen tambien se colocaba a clic, cuando lo que se quiere es
usar la posicion del objeto y mover el cursor.

Agregado `fromOrigin` y `previewToPoint`: el objeto queda como origen, el
cursor muestra la distancia en vivo, y el clic la fija. Boton nuevo en la barra
del objeto seleccionado.

### Pruebas

`drawing-flow.spec.js` (22). El control negativo resulto informativo: la primera
version ejercitaba el `ToolManager` directamente y **no detecto** el bug del
segundo clic, porque el shell es quien decide que significa un clic. Se
reescribio para montar el shell y hacer clic en el mapa real, y ahi si cae.

## [0.22.0] - 2026-09-27 - Los botones de herramienta no quedaban apretados

### Causa raiz: un bucle reactivo infinito

Un watcher en GisShell observaba `measure.value` y le asignaba una copia
atras. Un efecto reactivo que muta su propia dependencia no converge: Vue
aborta tras cien actualizaciones y lanza *Maximum recursive updates
exceeded*.

Disparaba con el primer clic de **cualquier** herramienta, porque `activate`
emite un cambio. El sintoma no era un watcher portado mal: era la barra entera
deja de responder, y el operador lo leia como "los botones no se quedan
apretados".

El watcher no hacia nada util: `MeasureEngine` ya llama a su handler
`onChange`, que asigna `measure.value` directamente.

### Estado visible de la herramienta activa

El marcado y el CSS existian, pero el bucle los impedia llegar a pintar. Una vez
eliminado, el estado se refuerzo con tres senales que se refuerzan entre si,
porque un fondo relleno solo no se lee de un vistazo en una barra de diez
herramientas:

- fondo propio,
- borde brillante,
- una barra luminosa bajo la etiqueta.

Y el estado activo **no cambia el tamano** del boton: solo pintura. Un boton
que crece al apretarse mueve el puntero del operador y lo hace fallar el
siguiente clic.

### Pruebas

`active-tool.spec.js` (8): exactamente un boton apretado, se mueve al cambiar de
herramienta, **se mantiene apretado mientras se dibuja**, `aria-pressed`
refleja el estado, y se suelta al apretarlo otra vez. Ademas dos comprobaciones
sobre el CSS construido, porque una clase que no cambia nada no es un estado que
un operador pueda ver.

Verificado revirtiendo el watcher: los tests caen con *Maximum recursive
updates*.

**Totales: 357 + 7 Python, 204 frontend, 675 de paridad.**

## [0.22.1] - 2026-09-27 - El circulo no conservaba la medida al confirmar

### Causa: dos dueños para el mismo clic

`ToolManager` se suscribe al evento de clic del mapa al activarse, y el shell
tambien estaba suscrito. Los dos se ejecutaban en cada clic.

Peor: el `Set` de listeners de `MapEngine` se itera con `forEach`, y `cleanup()`
borra el handler **mientras se itera**. El handler de la herramienta ya estaba
en la cola, asi que se ejecutaba igual: con `active` en `null` caia al `default`
y no hacia nada. Por eso el fallo era **intermitente** ydependia del orden de
suscripcion, en lugar de romper siempre.

### Un solo dueño

El shell dejo de interpretar clics para las herramientas de dibujo. Solo le
quedan los dos casos que el manager no posee: una medicion de aeropuerto
pendiente, y limpiar la seleccion con la herramienta de seleccionar.

Ahora el segundo clic lo gestiona `_onClick`: recalcula el radio desde el
punto del clic y confirma. El radio que se guarde es el que estaba en pantalla.

### Idempotencia

Un clic crea **un** circulo. Con el doble manejo, un tercer clic resucitaba la
herramienta y abria un segundo circulo.

### Pruebas

Cuatro nuevos, y uno que solo podía fallar asi:

- el arrastre real conserva la medida mostrada,
- queda un unico circulo por operacion,
- la herramienta queda liberada, y otra arranca limpia,
- y a traves del shell montado: `active-tool.spec.js` comprueba que el objeto
  guardado tiene el radio que se veia y que la herramienta se suelta.

**Totales: 357 + 7 Python, 209 frontend, 675 de paridad.**

## [0.23.0] - 2026-09-29 - Raiz limpia y un solo lanzador

### Limpieza de la raiz

Se borro lo que no servia para nada:

- `package.json` y `package-lock.json` de la raiz: vacios, `"packages": {}`,
  sin dependencias. El proyecto real es `frontend/package.json`.
- `upload.sh`: un ayudante de una sola vez para agregar el remoto de GitHub.
  El remoto ya esta.
- `rf-interference-system.rar`: 94 KB de un `.rar` del SIARI original que
  nunca estuvo en el arbol de trabajo, solo en el indice de git.
- `siari.db`: 44 KB, cuatro tablas, **cero filas**, y ninguna referencia en el
  codigo. `.env` apunta a `aerorf.db`.
- `start.sh`: duplicaba la logica del lanzador en otro lenguaje.
- Los cuatro `.log` sueltos de la raiz y los cuatro de `frontend/`.
- `RETOMAR.md` y `TODO.md`, ya obsoletos.

`AERORF_AUDIT.md` se movio a `docs/archive/`: es el registro de por que se
quito cada parte del SIARI, y conviene conservarlo, pero no en la raiz.

Quedan cuatro documentos en la raiz: `README.md`, `MANUAL.md`,
`AERORF_ARCHITECTURE.md` y `AERORF_CHANGELOG.md`.

### Un solo lanzador

`start.bat` arranca backend y frontend, y hace de los dos modos internos
`_backend` y `_frontend` que cada uno corre en su propia ventana. Se borra
`start.sh` justamente para que no haya dos copias de la misma logica que
deriven: las dos ya habian divergido, una ponia `8000` y la otra `5173`.

Modos: `dev` (por defecto), `test`, `build`, `stop`.

Espera de verdad a que cada servidor responda antes de dar por bueno el
arranque, y si uno no responde muestra las ultimas lineas de su log.

### Puertos: ya no es posible caer en 8000 por accidente

El backend nunca debe caer en 8000, que en esta maquina pertenece al proyecto
hermano `rni-app-4.0`. Con el valor por defecto en 8000, un `.env` ausente
mandaba el frontend aSpeaking con otra aplicacion, y eso se ve como "esta
roto" en lugar de "esta mal configurado".

- El valor por defecto pasa a 8010, en `start.bat` y en `vite.config.js`.
- `VITE_PORT` pasa a 5199, y se documento en `.env.example` y `.env`.
- `CORS_ORIGINS` se actualizo a los origenes nuevos, con `::1` incluido
  porque Vite puede escuchar en IPv6.
- `strictPort: true` en Vite. Con `false` Vite se corria solo al siguiente
  puerto libre, asi que la URL que se imprime no era la que se servia, y el
  lanzador esperaba un puerto donde nadie escuchaba.

### Si el puerto esta ocupado, no arranca

Antes el lanzador avisaba y seguia. La comprobacion de `/health` la
respondia el proceso que ya estaba escuchando, y el script anunciaba "listo"
mientras la ventana nueva habia fallado al tomar el puerto. Ahora se niega a
arrancar y lo dice.

### Cuatro fallos del lanzador, encontrados probandolo

- **El archivo estaba con finales de linea LF.** `cmd.exe` lo leia como una
  sola linea y cada instruccion quedaba cortada: `echo` se converia en `cho`,
  `if` en `f`. Ahora se escribe con CRLF.
- **`echo Backend -> http://...`**: el `>` se interpretaba como redireccion, y
  cmd intentaba crear un archivo llamado `http://127.0.0.1:8010`, que no es un
  nombre valido. Eso era el error de "sintaxis de etiqueta del volumen" que
  salia al final, y hacia que las lineas de Backend y Frontend no se
  imprimieran nunca. La flecha va escapada.
- **`isbusy` leia al reves los codigos de `findstr`.** `findstr` devuelve 0
  cuando encuentra la linea, y ese 0 es el que significa "el puerto esta
  ocupado". La routine daba los puertos libres por ocupados y al reves, asi
  que la comprobacion no servia para nada.
- **`stop` no paraba el backend.** Con `--reload`, uvicorn lanza un supervisor
  y un hijo, y el hijo hereda el socket de escucha. Matar el PID que muestra
  `netstat` dejaba a los dos python vivos y el puerto ocupado. Ahora se mata
  por puerto **y** por linea de comandos.

### El secreto de OpenSky ya no se imprime

Al trazar el lanzador con `@echo on` aparecio el `OPENSKY_CLIENT_SECRET` en
claro: el volcaba entero al entorno. Ahora solo se leen `PORT`, `VITE_PORT` y
`HOST` del `.env`, que es todo lo que el lanzador necesita; uvicorn lee el
`.env` por su cuenta. Una lista blanca no puede filtrar lo que no nombra.

> Sigue pendiente **rotar `OPENSKY_CLIENT_SECRET`**: aparece en este historial
> de conversacion y en el de la sesion anterior.

## [0.24.0] - 2026-09-29 - La trayectoria no se cargaba nunca

### Causa: una clave repetida en el cliente de la API

`flights` definia `track` **dos veces** en el mismo objeto literal:

- `GET /flights/{icao24}/track`, la trayectoria,
- `POST /flights/tracked`, agregar una aeronave a la lista de seguimiento.

En JavaScript la segunda definicion reemplaza a la primera sin avisar. Asi que
`loadTrack` nunca pedia la ruta: **agregaba la aeronave a la lista** y
guardaba esa fila en el lugar de la trayectoria. Una fila de la lista no tiene
puntos ni recorrido, y el panel mostraba "Trayectoria: no cargada" mientras el
backend tenia la ruta entera, lista para devolver.

Comprobado contra el backend en ejecucion: `GET /api/v1/flights/e06491/track`
devolvia 88 puntos, 1057 km, 83 historicos de OpenSky y 10 de la grabacion
propia. El dato existia. La peticion nunca salia.

El alta en la lista ahora se llama `addToWatchlist`. Un nombre para cada cosa.

### Varias trayectorias a la vez

Solo havia un lugar para la trayectoria, asi que la de un avion tapaba a la del
anterior y no habia forma de ver dos vuelos juntos. Eso es justo lo que hace
falta para comparar rutas, que es el uso que le da el operador.

- El store guarda una trayectoria por aeronave, en `tracks`, con `trackFor`,
  `allTracks` y `forgetTrack`.
- El panel lee la de cada avion, y la cuenta es la de esa, no la de la ultima.
- `drawTrack` ya no llama a `clearTracks()`: borra solo la de esa aeronave y
  deja las demas en el mapa.
- Un avion que sale de la lista se borra del mapa con su trayectoria.

### El boton de trayectoria ahora trae los datos

`toggleTrack` solo cambiaba una bandera y llamaba a `renderAll`. La capa no
tenia nada que dibujar porque nadie habia pedido los datos, asi que el boton
cambiaba de etiqueta y el mapa seguia vacio. Ahora, al activarlo, pide la
trayectoria.

Ademas, al **terminar una grabacion** la trayectoria se carga sola. La
grabacion es lo que el operador pidio, y solo sirve si se puede ver; tener que
pedirla aparte hacia que una grabacion terminada pareciera no haber producido
nada.

### Dos fallos mas, de paso

- `time = 0` se descartaba por una comprobacion de verdad. Cero significa "el
  vuelo en curso" y el backend lo lee para marcar los puntos como `live` en
  lugar de `historical`; la peticion salia sin tiempo y volvia con el ultimo
  track, mal etiquetado.
- El cache se indexaba con el texto crudo de la peticion, mientras el backend
  devuelve el ICAO24 en minusculas. Con distinta mayuscula la busqueda fallaba
  y el panel caia a "no cargada" teniendo el dato. Ahora la clave se normaliza.

### `start.bat test` nunca corria la paridad geodesica

La ruta estaba mal: el archivo vive en `tests/` del proyecto, no en
`frontend/tests/`. El `if` no se cumplia y los 675 casos se saltaban en
silencio. Corregido.

### La suite no dependia de un backend, pero decia lo contrario

Montar el shell hacia peticiones contra un puerto sin nada escuchando, y jsdom
soltaba un `AggregateError` por cada una. Vitest los imprimia como stderr
atribuidos al test que este corriendo, y el ruido tapaba los resultados. Ahora
`drawing-flow.spec.js` reemplaza el modulo de la API entero con `vi.mock`, que
se levanta antes de cualquier import. Un intento con un stub global de
`XMLHttpRequest` en `setup.js` **no funciono** y se elimino: `super()` igual
abria un socket real. La ausencia de un backend corriendo tiene que verse en
el archivo que monta el componente, no esconderse en un shim global.

### Pruebas

- 7 de contrato en Python: los dos endpoints son recursos distintos, la
  respuesta trae lo que el panel lee, `time=0` llega al servicio, una
  grabacion terminada forma parte de la trayectoria y no borra la ruta de
  OpenSky, un avion sin datos devuelve una trayectoria vacia y no un error, y
  un codigo mal formado no llega a OpenSky.
- 7 de frontend: entre ellas una que **lee el fuente** y falla si el objeto
  `flights` vuelve a tener una clave repetida. Un espia no serviria: se
  instalaria sobre la clave que hubiera y pasaria igual.

Cada una verificada revirtiendo el arreglo.

**Totales: 364 + 7 Python, 216 frontend, 675 de paridad.**

## [0.25.0] - 2026-09-29 - Elegir el vuelo, no solo la aeronave

### El problema: sin instante, OpenSky devuelve otro vuelo

Un reporte nombra un vuelo que **ya aterrizo**, a veces de dias anteriores. El
boton pedia la trayectoria sin indicar momento, y OpenSky responde entonces con
el vuelo **mas reciente** de esa aeronave.

Medido contra la API, no contra documentacion:

- mismo avion `a101c3`, vuelo del reporte AAL3139 del 09-28 10:10,
- sin instante: 129 puntos, del 09-29 13:14 al 15:48, 225 km — **otro vuelo**,
- con el instante del vuelo: 308 puntos, del 09-28 10:10 al 11:20, 812 km.

Los puntos son reales, la procedencia es correcta y la ruta es la equivocada.
Nada aguas abajo puede distinguirlo. Para un operador que compara rutas, eso es
peor que no tener dato: contaminaba comparaciones.

Verificado ademas que el historico existe: hoy, ayer, 3 dias y 7 dias devuelven
trayectorias; 15 dias ya no. El limite de 30 dias es real.

### Que se implemento

**`GET /api/v1/flights/{icao24}/flights`** lista los vuelos de una aeronave, del
mas reciente al mas antiguo, con lo que identifica un vuelo: hora, duracion,
aeropuerto de salida y llegada, y el instante para pedir la trayectoria.

**El panel** tiene un boton **Vuelos** que abre la lista. Cada fila trae fecha,
hora, ruta y duracion; al elegir una, se pide la trayectoria **de ese vuelo**.

Cada dia hacia atras es una consulta con costo a OpenSky, asi que la respuesta
dice cuanto costaba y si la busqueda se corto. Una lista corta no se confunde
con "esta aeronave no volo".

**La trayectoria declara su ventana.** Cada respuesta trae `covered_window` y
`matches_request`. Cuando lo devuelto pertenece a otro vuelo, el panel lo
avisa en vez de mostrarlo como si fuera el correcto.

### Un limite mal medido, de paso

`MAX_FLIGHTS_AIRCRAFT_WINDOW_S` valia 48 h, con un comentario que decia "2 dias".
OpenSky **rechaza** desde 47 h y responde bien hasta 25 h. Medido: 1, 6, 12, 23,
24 y 25 h funcionan; 47, 48, 49, 50 y 72 h devuelven 400. Ahora es 24 h, con la
medida anotada.

El recorte a 48 h no era conservador, estaba fuera de rango: la salia, OpenSky
la rechazaba, y la lista de vuelos de ayer no se podia construir.

Ademas, las ventanas se armaban mal: con `begin`/`end` explicitos, el limite
`days` cortaba por el extremo equivocado y los dias mas antiguos se perdian en
silencio. Ahora cubren todo el rango pedido, sin huecos, con tope de 30 ventanas
y `search_truncated` avisando.

### Pruebas

19 de Python y 12 de frontend nuevas, entre ellas:

- el instante del vuelo elegido llega a la peticion, y **no** es el del vuelo
  mas reciente,
- una trayectoria de otro vuelo se marca como desajuste, y una vacia no,
- las ventanas cubren el rango pedido sin huecos ni desbordes,
- una busqueda truncada lo dice,
- y una que monta el panel y hace clic en la fila, porque la decision de que
  instante se manda vive en la plantilla y una prueba del store no la alcanza.

Cada una verificada revirtiendo el arreglo. Al reponer el fallo real —la fila
eligiendo `null` en vez del instante— el test del panel falla, que es lo unico
que lo hacia util.

**Totales: 376 + 7 Python, 228 frontend, 675 de paridad.**

## [0.26.0] - 2026-09-29 - Grados en vivo y el circulo a la vista

### El radial mostraba un numero sin referencia

Un azimut no significa nada solo. 045° es una cifra hasta que se puede ver
**respecto de que** esta medido, y la herramienta no dibujaba nada de
referencia: solo la linea y un tooltip que exigia pasar el puntero por encima.

Ahora, al dimensionar un radial:

- una linea discontinua hacia el **norte (000°)**, de la misma longitud que el
  radial, para que el angulo sea el de la pantalla y no una deformacion por
  escala,
- el **arco del angulo** entre la referencia y la linea, con los grados
  rotulados en el origen,
- una **etiqueta permanente en el extremo** de la linea, con grados, rumbo y
  longitud, que se lee sin hacer hover,
- y el panel muestra el valor en vivo: `Midiendo: 90.0° E · 24.31 KM`.

El arco se dibuja por el camino corto: 045° son 45°, no 315°. Y al pasar de
360° no barre 350° al reves.

### El circulo no se veia hasta el primer clic

Elegir la herramienta de circulo con 5 NM configurados **no mostraba nada**. El
anillo solo aparecia al colocar el centro, de modo que el numero del panel no
se podia juzgar contra el terreno que ibia a cubrir. Fijar un radio sin ver que
abarca es fijarlo a ciegas, que es justamente lo contrario de lo que sirve
configurarlo.

Ahora la figura se dibuja al elegir la herramienta, en el centro de la vista, y
**se redibuja al cambiar el radio o la unidad** — tambien sin hacer clic. Se
dibuja tenue y sin relleno, para que se lea como guia y no como el objeto.

La guia desaparece al soltar la herramienta: una vista previa que sobrevive
dejaria un circulo en el mapa que nada va a guardar.

### El panel distingue lo configurado de lo medido

Son dos numeros distintos y el operador tiene que poder separarlos: lo
configurado es lo que escribio, y lo medido es lo que esta midiendo el
puntero, que cambia en cuanto se coloca el centro. El panel rotula
`En el mapa` y `Midiendo` en vez de dejar que se deduzca de la posicion de una
cifra.

### Pruebas

12 nuevas de comportamiento y 4 de estilos.

Las de comportamiento cubren lo que el operador pidio: que el circulo aparezca
al elegir la herramienta, que 5 NM sean 9 260 m, que cambiar el radio o la
unidad lo redibuje, que 5 NM y 9,26 km sigan siendo la misma distancia, que los
grados se reporten en cada movimiento, que la etiqueta del extremo sea legible
sin hover, y que el radial se guarde con el azimut que se leyo.

Las de estilos comprueban que la etiqueta de referencia exista y que se aplique
a la referencia y no al valor: una referencia tenue con un arco brillante
diria lo contrario de lo que son. Son estaticas a proposito, porque jsdom no
maqueta nada y una asercion de estilo calculado pasaria contra una regla que
nunca se aplico.

Cada arreglo verificado revirtiendolo: quitar el preview de `activate` deja 3
tests en rojo, y quitar el redibujado de `setOptions` deja 5.

**Totales: 376 + 7 Python, 244 frontend, 675 de paridad.**

## [0.27.0] - 2026-09-29 - El punto central, y colocar un objeto en el centro de otro

### El circulo guardado era un punto

Al confirmar un circulo se veia completo, y al seleccionarlo de la lista
aparecia **solo el punto central**, con los valores correctos en el panel. Un
radial guardado era lo mismo: la linea no existia.

La causa, en la base y no en la teoria. Circulo y radial se guardan como un
centro mas una medida, y su `geometry_type` es `Point`, porque eso es el centro.
El dibujo despachaba solo sobre `geometry_type`, asi que **todo** circulo y
radial guardado caia en la rama del punto. Los valores estaban bien y por eso
el panel los mostraba; la figura nunca se dibujo.

Ahora el tipo se consulta antes que la geometria. El circulo se dibuja con
`L.circle` a partir de `radius_m`, y el radial como polilinea desde el centro
con el azimut y la longitud guardados. Se prefiere `radius_m`; si no esta, se
convierte desde `radius` **usando su unidad**, porque 5 NM y 5 km no son el
mismo circulo y usar el numero sin unidad seria dibujar uno de los dos veinte
veces mas chico.

El azimut se normaliza al leer: un valor redondeado puede quedar en 360.0 o en
un negativo pequeno del cruce de 0, y un rumbo fuera de rango produce una linea
en una direccion que el operador no pidio.

### El centro visible

Un anillo no dice de donde sale, y una linea tampoco. Sin una marca en el
origen no se puede leer el rumbo de un radial, ni colocar otra cosa en el
centro de un circulo, que es lo mas probable que se quiera hacer despues.

Circulo y radial llevan ahora un punto pequeno en su centro u origen. No
captura clics: el punto no debe Difficulty el centro, debe volverlo alcanzable.

### El clic sobre un objeto no llegaba a la herramienta

Este era el que reportaste: hiciste un circulo de 10 NM, agarraste el radial,
quisiste poner el origen en el medio, y selecciono el circulo.

El handler de clic de cada objeto llama `stopPropagation`, que frena el evento
**antes** de que llegue al mapa. La herramienta no lo veia nunca. Con la
herramienta visible y armada, no habia ninguna pista de por que no pasaba nada.

Ahora, con una herramienta de dibujo armada, la posicion se reenvia
explicitamente. `stopPropagation` se mantiene para la herramienta de
seleccionar, donde seleccionar el objeto bajo el puntero es justamente lo que
se quiere, y el handler del mapa limpiaria la seleccion.

### El enganche al centro

Una mano no es una coordenada. El radial quedaria guardado a unos metros del
centro del circulo, una distancia invisible en pantalla y equivocada en los
datos, y los dos objetos no coincidirian en nada que se pueda ver.

Un clic a menos de **10 pixeles** del centro de una figura medida se pega a ese
centro. En pixeles, no en metros, y convertidos a la latitud actual: una
tolerancia fija en metros seria inalcanzable alejada y inevitable acercarse. En
Argentina, que va de 22 a 55 de latitud sur, la escala Mercator varia lo
suficiente como para que la diferencia se note.

El radio de 10 pixeles es amplio para ser deliberado y chico para pelearse con
el operador: un punto en terreno abierto, lejos de cualquier figura, no se
mueve.

### Dos medidas por pixel, y por que

La tolerancia se convierte usando `metresPerPixel` del motor, y eso salio mal
**dos veces** antes de estar bien:

1. Proyectar el centro en dos zooms y medir el hueco daba 9,5 m por pixel
   donde corresponden ~62. La tolerancia quedaba diez veces mas ajustada de lo
   debido, y el enganche no disparaba nunca: la funcion estaba inerte sin decir
   nada.
2. `crs.groundResolution` **no existe** en esta version de Leaflet, y
   `crs.scale` no acepta zoom y devuelve un valor constante.

La tercera, medir una pantalla de alto sobre la proyeccion del propio mapa y
dividir, acierta. Y hay tests que lo fijan por propiedades — se reduce a la
mitad al acercar, es menor en el ecuador, y coincide con la formula cerrada de
EPSG:3857 dentro del 1 %—, mas uno que documenta que las dos APIs que no
funcionan no existen, para que una actualizacion de Leaflet se note aca y no
como un cambio silencioso.

### De paso: un bloque duplicado

El manejador de clic del shell tenia dos copias identicas de la medicion de
aeropuerto, una dead desde antes de la otra. La segunda no se ejecutaba nunca.

### Pruebas

33 nuevas: 12 de enganche y centro, 4 de la conversion de pixeles, 3 de la
interfaz de proyeccion, y 14 actualizadas para el grupo de capas.

Los 14 de formas guardadas necesitaba ajuste: el circulo y el radial ahora son
grupos — la figura y su punto central — y las aserciones apuntaban a la capa
directa. Se reescribieron para leer a traves del grupo, que es lo que describe
el objeto en el mapa y no una de sus partes. El helper distingue el anillo del
punto por el radio en metros, porque `L.circle` **tambien** es un
`CircleMarker` en Leaflet.

Verificadas revirtiendo el arreglo: quitar el reenvio del clic deja 2 tests en
rojo, y volver a dibujar por `geometry_type` deja 8.

**Totales: 376 + 7 Python, 277 frontend, 675 de paridad.**

## [0.27.1] - 2026-09-29 - No se podia seleccionar nada (lo rompí yo)

### Que pasó

En 0.27.0 el circulo paso a ser un grupo de capas para poder llevar el punto
central, y se creo con `L.layerGroup`. **Un `LayerGroup` no reenvia los eventos
de sus hijos**; un `FeatureGroup` si.

El clic lo manejaba el store, que escucha en la capa del objeto. Con un
`LayerGroup` el clic en el anillo no llegaba ahi, la seleccion nunca se
producia, y sin seleccion no se puede borrar, anotar, mover ni medir desde el
objeto. Todo lo que se hace despues de seleccionar, dejo de funcionar.

Un `FeatureGroup` propaga los eventos de sus capas hijas, que es justo lo que
hacia falta. Ese es el arreglo.

### Por que la suite estaba en verde

Todos los tests de formas guardadas leian la geometria de la capa, y un grupo
responde eso perfectamente. **Ninguno hacia clic.** El unico test que hace clic
es el nuevo, y es el que fallo.

Es la misma trampa de siempre, y ya la tercera vez en este trabajo: "compila" y
"responde lo que se le pregunta" no es "funciona". Un objeto puede tener la
forma correcta y ser intocable.

### El punto central y los clics

El punto central es `interactive: false`, y eso es lo que se verifica. Con esa
bandera, Leaflet no lo considera objetivo de puntero, de modo que el clic pasa
al anillo de atras: el centro del circulo, que es justo donde el operador
queria hacer clic, sigue funcionando.

Un test que le dispara un evento sintetico al punto central|reportaria que si
selecciona, porque un `FeatureGroup` reenvia cualquier evento. Seria cierto del
evento e irrelevante: una capa no interactiva nunca recibe un evento de puntero
real. La asercion va sobre la bandera, que es lo que Leaflet mira de verdad.

### Un detalle sobre como se dispara el clic

Leaflet propaga un evento hacia arriba **solo si `fire` recibe `propagate`**. Un
`fire` a secas se queda en la capa donde se llamo y no llega al grupo.

Mis primeros tests de esto usaban `fire` sin la bandera, y reportaban que
**ningun** grupo reenvia nada — lo que habria hecho concluir que la solucion no
era posible. El mecanismo real es el bubbling que Leaflet hace al despachar al
objeto bajo el puntero, y los tests ahora lo reproducen con la bandera.

### Pruebas

7 nuevas: 4 de seleccion (circulo, radial, punto normal, y el punto central que
no captura clics) y 3 que documentan la propagacion de eventos entre grupo e
hijos en esta version de Leaflet.

Verificadas revirtiendo el arreglo: volver a `layerGroup` deja 2 tests en rojo.

**Totales: 376 + 7 Python, 284 frontend, 675 de paridad.**

## [0.27.2] - 2026-09-29 - follow-up: la seleccion seguia rota por otra razon

### Mi primera explicacion estaba mal

En 0.27.1 atribuí el problema a que un `LayerGroup` no reenvía clics y cambié a
`FeatureGroup`. Era **una causa real pero no la que rompía la selección**, y lo
dije como si lo fuera. El `LayerGroup`, sí impedía seleccionar en su momento,
pero el síntoma que reportaste — que **nada** se selecciona, ni siquiera un
punto simple — no lo explicaba.

### Las dos causas, juntas

**1. El clic en un objeto también lo ve el mapa, y el shell borraba la
selección justo después de fijarla.**

Este mapa dibuja con `preferCanvas`: todos los objetos vectoriales se pintan
sobre **un mismo elemento canvas**. No hay un nodo DOM por objeto, así que
`stopPropagation` no tiene nada donde actuar. El handler del mapa se ejecutaba
también para un clic sobre un objeto, y con la herramienta de selección
llamaba a `clearSelection()`.

El orden era: el handler del objeto selecciona, el del mapa borra. El operador
no veía ningún efecto. Por eso no seleccionaba **nada**, y por eso el arreglo
del `FeatureGroup` no lo cambió.

Lo que faltaba era distinguir los dos casos, y para eso está el id del objeto en
el evento: `overObject` presente es clic sobre un objeto, ausente es clic en el
vacío.

**2. La condición que deselecciona nunca se cumplía.**

Era `toolManager?.active === TOOLS.SELECT`. Pero `ToolManager.active` es `null`
hasta que se elige una herramienta, y la herramienta de selección **solo** se
activa desde la medición de aeropuerto. Al cargar la página, `active` es `null`
para siempre: la condición no se cumplía nunca.

Ahora la condición es "no hay herramienta de dibujo armada", que es lo que el
shell realmente quiere expresar.

### Sobre el resaltado y los textos

Al revisar, el mismo grupo sin `setStyle` rompía también el resaltado de la
selección y el nombre del objeto: `setStyle`, `bindTooltip` y `bindPopup` se
llamaban sobre el grupo, donde no hacen nada. Ahora atraviesan a las capas
hijas.

También apareció un bug de acumulación: `setStyle` escribe sobre `options`, así
que restaurar el estilo desde `options` devolvía el estilo **resaltado** y el
grosor de cada objeto crecía tres puntos con cada clic. El estilo base se
captura una vez y se guarda aparte.

### Una suposición mía que era falsa

`suppressClicks()` tiene valor por defecto `true` y el handler del mapa empieza
con `if (this._clickSuppressed) return`. Sospeché que eso silenciaba todos los
clics. **No era así**: el flag nunca se inicializa, queda `undefined`, y eso es
falsy. Hay un test que lo fija, para que la suposición no vuelva.

### Pruebas

22 nuevas. La que importa monta **el shell completo**, con un objeto real en el
mapa y un clic real sobre él: es el único nivel donde se ven las dos mitades de
este bug, porque ni el motor ni el store borran nada — lo hace el shell.

También 5 que fijan el orden y la presencia del id, 4 sobre la bandera de
supresión, 10 sobre el resaltado atravesando el grupo, y 3 sobre la propagación
de eventos.

Un test viejo afirmaba lo contrario de lo correcto: que con la herramienta de
selección el mapa no debía ver el clic. Estaba escrito sobre la suposición de
que `stopPropagation` funcionaba, así que se actualizó junto con el código.

Verificadas revirtiendo el arreglo: con las dos causas de vuelta, los tests del
shell fallan.

**Totales: 376 + 7 Python, 306 frontend, 675 de paridad.**

---

## 0.27.3 — La selección de objetos en el mapa

**Síntoma:** ningún objeto del mapa se seleccionaba. Ni puntos, ni círculos, ni
radiales. Como consecuencia no se podía borrar, anotar, mover ni medir desde un
objeto. Tres intentos anteriores habían «arreglado» algo y el operador siguió
reportando lo mismo.

### Por qué los 306 tests no lo veían

Porque usan `layer.fire('click', …)`, que entrega el evento directamente a la
capa y se salta todo lo que el navegador hace antes. El bug vivía en los pasos
**anteriores** al evento: dónde se pintaban las capas y en qué orden. `fire()`
empieza después de todos ellos.

Consecuencia metódica: **ningún test en jsdom podía detectarlo**, y tres
intentos seguidos encontraron *una* causa plausible y la presentaron como *la*
causa. El dato más informativo — que tampoco fallaban los puntos simples, lo que
descartaba de entrada toda explicación sobre grupos de capas — se pasó por alto.

### Causa 1 — un lienzo invisible encima de todo el mapa

`centreDot()`, el punto central de un círculo o un radial, llevaba
`pane: 'markerPane'`. El mapa dibuja con `preferCanvas`, así que una capa
vectorial en un panel que no es el de overlay recibe **su propio lienzo de
tamaño completo**, y Leaflet pone `pointer-events: auto` en cada lienzo. El
markerPane está por encima del overlayPane (z-index 600 contra 400): ese lienzo
tapaba el mapa entero, por delante de todo, y se comía cada clic, incluidos los
dirigidos al suelo.

Medido en el navegador, con la app real:

- `document.elementFromPoint` sobre un círculo devolvía el lienzo del
  markerPane; con ese lienzo oculto, devolvía el del overlayPane.
- El lienzo estaba **completamente vacío** — cero píxeles pintados.

`interactive: false` en el punto no era ninguna protección, y por eso conviene
fijarlo: con lienzo compartido el elemento que recibe el puntero es el lienzo, no
la forma, así que el flag de la forma no dice nada sobre si estorba.

**Arreglo:** el punto central comparte el overlayPane con la forma que marca. No
hay ningún `pane:` en todo el código de la aplicación.

### Causa 2 — seleccionar reordenaba el lienzo compartido

`highlight()` llamaba a `bringToFront()` sobre las capas del objeto elegido. Con
un lienzo compartido eso es un reordenamiento **global**, no por objeto, y es
permanente.

El área de impacto de un círculo es su **disco entero**, no su anillo: el
`_containsPoint` de `CircleMarker` en Leaflet es `distancia <= radio`. Y el
lienzo entrega el clic **solo a la capa más alta** cuyo disco contiene el punto.
Medido: tras seleccionar una vez el círculo de 16 km, ese círculo respondía a
todos los clics de su interior por el resto de la sesión, y los objetos de
dentro quedaban inalcanzables hasta recargar la página.

**Arreglo:** `highlight()` ya no llama a `bringToFront()`. El resaltado se hace
con grosor y color, que no pueden cambiar quién recibe el clic.

### Causa 3 — el orden de dibujo dependía del historial de la sesión

Las categorías llegan en el orden de la lista de capas, donde `radials` precede a
`circles`. Con `circles` encima, un clic sobre un radial **en el punto donde lo
cruza un círculo** devolvía el círculo: el operador hacía clic en la línea que
veía y recibía el área a la que no apuntaba.

Además, Leaflet no tiene «insertar en posición»: un grupo que se quita y se
vuelve a poner queda como el último añadido, es decir, arriba del todo. Mostrar
una capa la dejaba clavada encima.

**Arreglo:** `restack()` reconstruye el orden de dibujo de forma determinista —
el de llegada, con `CATEGORY_DRAW_RANK` resolviendo el único conflicto: el disco
del círculo debajo, la línea del radial encima, y los objetos discretos por
encima de ambos, que es el orden que ya daba la API. Se llama al final de
`renderAll()` y al volver a mostrar una capa.

Se eliminó `setCategoryOrder()`, que reordenaba **panales** para fingir un
«insertar después». Nunca recibió un `order` — nadie lo llamaba — y era el
mecanismo equivocado: con `preferCanvas` hay un solo lienzo y una sola lista, el
orden de paneles no dice qué se dibuja sobre qué. Peor: movía el elemento
overlayPane dentro del markerPane, el mismo tipo de error que el panel propio
del punto central. `ensureCategory()` pierde su opción `order` con ella.

### Verificación

En el navegador real, con un `MouseEvent` de verdad en las coordenadas del
objeto — el mismo camino que un clic de usuario, y lo que jsdom no puede hacer:
**10 de 10 objetos seleccionan**, los tres tipos, cada uno centrado en pantalla.
También: el clic en suelo vacío deselecciona; ocultar y volver a mostrar la capa
`circles` no altera el orden y los objetos de dentro siguen seleccionables; la
herramienta de círculo sigue admitiendo su vista previa en el overlayPane y
sigue habiendo un solo lienzo; la consola está limpia.

Antes: el radial 4 perdía contra el círculo 9 y el punto 5 respondía con el
círculo 1.

### Guardas

8 tests nuevos en `frontend/tests/canvas-hit-targets.spec.js`. No simulan un
clic: afirman las tres propiedades que el navegador tiene y sin las cuales
ningún clic llega a destino. Cada una tiene escrita la medición de la que sale.

**Verificadas revirtiendo cada arreglo**, que es la única forma de saber que
guardan algo:

| Arreglo revertido | Tests que fallan |
|---|---|
| `pane: 'markerPane'` en el punto central | 3 |
| `bringToFront()` en `highlight()` | 1 |
| `CATEGORY_DRAW_RANK` vacío y sin `restack()` | 2 |

Un test viejo de este arreglo pasó por casualidad: renderizaba el círculo antes
que el radial, que es justo al revés de como llegan de la API, así que no
ejercitaba el conflicto. Corregido para usar el orden real.

### Una suposición que era falsa

`npm run lint` figuraba como limpio en sesiones anteriores. **No lo es, y nunca
lo fue:** no hay configuración de ESLint en el repositorio, en ninguna rama,
en ningún commit — `git log --all -- "*eslintrc*" "eslint.config*"` no devuelve
nada. El script fallaba y el resultado se reportaba como correcto. La
comprobación real de esta versión es el build, que pasa en 25 s, y las 314
pruebas de frontend.

**Totales: 376 + 7 Python, 314 frontend, 675 de paridad.**

---

## 0.27.4 — Fuera el popup de los objetos del mapa

**Lo que pidió el operador:** al seleccionar, toda la información en el panel
lateral, no en un globo que tapa las herramientas.

### Qué se quitó y qué se queda

El popup de los objetos del mapa —círculos, radiales, puntos, fuentes,
antenas, eventos, anotaciones— desaparece. No se pierde nada: `InspectorPanel`
muestra todos los campos que mostraba el globo, más la carga por tipo y el
formulario de edición, y además es editable. El globo era la segunda copia de
lo mismo, aparecía encima del panel al que el operador acababa de hacer clic y
tapaba la barra de herramientas y la barra de coordenadas.

**Los popups de aeropuerto y de aeronave se quedan.** Ninguno de los dos tiene
panel: `AirportPanel` es un buscador, y una aeronave en vivo solo aparece en
`selectedAircraft` cuando el panel de vuelos la elige. Para esos dos el globo es
el único sitio donde se lee la información, y la opción de quitarlos sin más que
se le ofreció al operador habría sido perder datos.

### Lo que se borró con él

- `MapEngine.objectPopup()`, que solo servía para eso.
- `MapEngine.typeLabel()` y su `TYPE_LABELS`, que era una **segunda** tabla
  idéntica a la de `stores/map.js` (`typeName`), la que usa toda la aplicación
  incluido el Inspector. Dos tablas que mantener y una que nadie leía.
- `MapEngine.formatDate()`, que solo usaba el popup. El Inspector tiene el
  suyo.
- El test de `components.spec.js` que fijaba el popup. No baja la cobertura:
  el requisito que fijaba —que un círculo muestre **ambas unidades**— ya lo
  cubre el test de `InspectorPanel`, que sigue afirmándolo.
- `stores/map.js`: `bindPopup()` pasó a llamarse `bindInspect()`, y ya solo
  engancha el doble clic. El comentario explica por qué va a los **hijos** del
  grupo: en un grupo `on('dblclick')` nunca se dispara, igual que antes pasaba
  con `bindPopup`.

El test de `selection.spec.js` que probaba el popup en los hijos del grupo ahora
prueba el doble clic, que tiene exactamente el mismo requisito. Y se **añadió**
otro que afirma que un objeto del mapa no trae popup, para que no vuelva por
la puerta de atrás.

Los estilos `.aerorf-popup*` están en el bloque `<style>` **global** de
`GisShell.vue`, no en el `scoped`, y los necesitan los dos popups que quedan. No
se tocaron.

### Dos cosas que aparecieron de paso

**El dataset de aeropuertos perdió todos los acentos.** En `data/airports.js`:
`Martn Miguel de Gemes`, `Presidente Pern`, `Capitan V A Almonacid`,
`Norberto Fernndez`. La `ñ` sí sobrevivió, así que no es una limpieza de
acentos sino una corrupción en la escritura del archivo. El popup muestra lo
que hay en el dato, sin pérdida: el daño es de origen y es previo a este
cambio. **No se corrigió a ojo**, porque adivinar los nombres sería inventar
datos; hay que volver a derivar el archivo de su fuente.

**Una verificación anterior mía era más laxa de lo que parecía.** Al medir en
el navegador había usado el rectángulo del **contenedor del mapa** para
convertir un punto geográfico a coordenadas de pantalla, que es lo correcto. Al
pasar a las pruebas de popup cambié al rectángulo del **canvas**, que está
desplazado (-42, -63) respecto del contenedor porque Leaflet lo pinta con
margen. Todos los clics de esas pruebas iban 75 px desviados, y de ahí que
«el popup del aeropuerto no abría»: no era que no abriera, que el clic no
llegaba. Medido con la conversión correcta, el popup del aeropuerto abre y
muestra SASA con ICAO, IATA, nombre y tipo.

El orden de dibujo quedó confirmado con la conversión buena: 9 de 11 objetos
seleccionan en su propio punto, y el navegador muestra **cero popups** en los
11 casos. Los dos que no son **coincidencias geométricas exactas de los datos
del operador**: la circunferencia del círculo 11 pasa justo por el centro del
círculo 3, y el radial 12 arranca justo en el centro del círculo 11. Ambos
círculos responden por su anillo.

**Totales: 376 + 7 Python, 314 frontend, 675 de paridad, build limpio en 27 s.**

---

## 0.28.0 — Aeropuertos con IATA, y el radio que no se respetaba

**Estado: verificado a medias.** El código está commiteado y los tests de
backend y de aeropuertos en verde, pero la suite de frontend completa y el
build no llegaron a correr: la máquina se quedó sin memoria y vitest se colgaba
al arrancar. Lo pendiente de confirmar está en `RETOMAR.md` y al final de
esta entrada. El commit es `57ba41e`.

### Aeropuertos

**Las etiquetas pasan a mostrar el IATA** —EZE, AEP— en lugar del ICAO. Es el
código que el operador lee en el boarding pass y escribe en la casilla.
`airportCode()` degrada a ICAO, luego a `gps_code`, luego al código local, y
por último al nombre recortado, así que un aeródromo sin IATA no queda sin
etiqueta.

**Más aeródromos, con un criterio y no con un gusto.** Entra todo aeropuerto
argentino que la fuente tipea `medium_airport`, o `small_airport` con vuelo
regular, y que siga en servicio. La regla está escrita en
`tools/build_airports.py`, junto a la lista, para que no dependa de quién la
armó. Entra además **Jujuy**: un `large_airport` con vuelo regular que faltaba,
y el único grande del país que no estaba.

**El Palomar y San Fernando, que el operador pidió.** El Palomar está en la
fuente como `SADP`, con IATA `EPA`. San Fernando publica **ningún ICAO ni
ningún IATA**: solo `gps_code` SADF y `local_code` FDO. No estaban porque la
selección se hacía únicamente por `icao_code`. El generador ahora resuelve un
token contra `icao_code` primero y contra `gps_code` después, e imprime en
pantalla cuáles se resolvieron por la segunda vía. Nada se inventa: un token que
no coincide con ninguna de las dos se reporta y se deja fuera — y al correrlo
aparecieron cuatro que la fuente no publica, `SCQN`, `SGCI`, `SGPP` y `SUCU`,
que quedan fuera y pendientes de decidir.

De 67 a 105 aeródromos.

**Dos familias de símbolo**, porque con 105 puntos un radio regional dibujado
igual que un hub desaparece debajo: azul relleno y etiqueta para los que tienen
tráfico, ámbar hueco y etiqueta más discreta para los menores activos. El panel
lleva la leyenda, porque un color que no se explica no informa de nada. La capa
sigue sin persistirse.

### Los acentos: la explicación que era falsa

Ayer se attributuyó a una corrupción al escribir el archivo. **Era una línea del
generador**, `name.encode("ascii", "ignore")`, puesta a propósito y con un
comentario que lo justificaba con que los nombres eran para una consola. No lo
son: el archivo se escribe en UTF-8 y el navegador lo lee en UTF-8. Los acentos
vuelven: "Martín Miguel de Güemes", 26 nombres con acento.

### El radio que no se respetaba

**Lo que reportó el operador:** escribía 5 NM, apretaba el mapa, y el círculo
salía de 2.987 NM. No se podía crear un objeto desde el panel.

**Reproducido en el navegador:** el radio se tomaba de la distancia entre los
dos clics y el valor escrito se descartaba. El panel dibujaba la previa con el
número correcto y después lo pisaba, así que lo que se veía no era lo que se
guardaba.

Había dos trabajos distintos mezclados en una sola interacción. Ahora son dos
opciones explícitas, y **la que existía sigue siendo el default**, para que
nada que el operador aprendiera ayer le resulte equivocado hoy:

- **Ajustar con el cursor** — primer clic el centro, segundo el borde.
- **Usar el valor del panel** — un clic, y el número escrito es el que se
  guarda.

En el segundo modo la herramienta **sigue armada** después de crear. El otro
reclamo del operador era que «al crear un elemento se oculta el panel»: no se
ocultaba, se desarmaba la herramienta y con ella desaparecían los campos. Poner
cuatro círculos de 5 NM son cuatro clics.

**El clic que dimensiona ya no hace snap.** El centro ya está puesto, así que
ese clic solo lleva una distancia; el snap lo movía al centro de otra figura y
el radio salía de un punto al que el operador no apuntó. Medido: 4.866 NM donde
se habían pedido 5.

### Las grabaciones

**El operador dijo que las de ayer no se guardaron bien. Se guardaron: cada una,
dos o tres veces.** 34 filas con 8 grupos de duplicados exactos.

`_store_track` construía la fila y la insertaba siempre, sin preguntar si esa
trayectoria ya estaba. Pedir dos veces el mismo vuelo —el operador recargando el
panel, un reintento tras un timeout, la caché de trayectoriasstarting vacía en
cada carga— insertaba una fila nueva cada vez.

Ahora busca primero. La coincidencia es la misma aeronave, el mismo vuelo sobre
ella y el mismo número de puntos. Dos cosas **no** son repetidas, a propósito:

- una trayectoria más escasa sobre la misma ventana: son los datos distintos de
  una grabación parcial, y esconderla detrás de la completa sería perderla;
- otro vuelo de la misma aeronave: `callsign` y `flight_id` son parte de la
  clave. Sin ellos, dos vuelos que se solapan en el tiempo se colapsaban y el
  segundo quedaba archivado bajo el callsign del primero — una etiqueta
  incorrecta y segura, no una duplicata inofensiva. **Lo encontró un test
  propio, no la inspección.**

`session_id` no es parte de la clave: una sesión y una trayectoria descargada
pueden describir los mismos puntos, y son la misma trayectoria. Cuando se
encuentran, la sesión se engancha a la fila que ya existe, así que el replay la
sigue encontrando.

**Las 16 filas duplicadas que ya hay en la base no se borraron.** Son datos del
operador y la decisión es suya.

### Lo que falta verificar

`frontend/tests/typed-sizing.spec.js` — 11 tests. Corrieron una vez: 8 pasaron,
3 fallaron. Uno era un bug real (la herramienta quedaba armada pero sorda, porque
`cleanup()` cancela la suscripción a los clics) y está corregido. Los otros dos
son precisión de los propios tests: uno espera 9260 m exactos y el código da
9249,6 porque `metros / 111320` grados es una aproximación; el otro espera un
snap con tolerancia de 0,00005 grados cuando hace falta más. **No volvieron a
correr.** La suite frontend completa y el build tampoco, por lo mismo.

Los 39 tests de `airports.spec.js` pasan y los 6 de `tests/test_track_dedup.py`
pasan, y el arreglo de deduplicación **sí** se verificó revirtiéndolo: 3 de sus
6 tests fallan sin él.

**Totales en verde: 382 + 7 Python, 39 de aeropuertos, 675 de paridad.**

---

## 0.28.0 — Aeropuertos con IATA, y el radio que no se respetaba

**Estado: verificado a medias.** El código está commiteado y los tests de
backend y de aeropuertos en verde, pero la suite de frontend completa y el
build no llegaron a correr: la máquina se quedó sin memoria y vitest se colgaba
al arrancar. Lo pendiente de confirmar está en `RETOMAR.md` y al final de
esta entrada. El commit es `57ba41e`.

### Aeropuertos

**Las etiquetas pasan a mostrar el IATA** —EZE, AEP— en lugar del ICAO. Es el
código que el operador lee en el boarding pass y escribe en la casilla.
`airportCode()` degrada a ICAO, luego a `gps_code`, luego al código local, y
por último al nombre recortado, así que un aeródromo sin IATA no queda sin
etiqueta.

**Más aeródromos, con un criterio y no con un gusto.** Entra todo aeropuerto
argentino que la fuente tipea `medium_airport`, o `small_airport` con vuelo
regular, y que siga en servicio. La regla está escrita en
`tools/build_airports.py`, junto a la lista, para que no dependa de quién la
armó. Entra además **Jujuy**: un `large_airport` con vuelo regular que faltaba,
y el único grande del país que no estaba.

**El Palomar y San Fernando, que el operador pidió.** El Palomar está en la
fuente como `SADP`, con IATA `EPA`. San Fernando publica **ningún ICAO ni
ningún IATA**: solo `gps_code` SADF y `local_code` FDO. No estaban porque la
selección se hacía únicamente por `icao_code`. El generador ahora resuelve un
token contra `icao_code` primero y contra `gps_code` después, e imprime en
pantalla cuáles se resolvieron por la segunda vía. Nada se inventa: un token que
no coincide con ninguna de las dos se reporta y se deja fuera — y al correrlo
aparecieron cuatro que la fuente no publica, `SCQN`, `SGCI`, `SGPP` y `SUCU`,
que quedan fuera y pendientes de decidir.

De 67 a 105 aeródromos.

**Dos familias de símbolo**, porque con 105 puntos un radio regional dibujado
igual que un hub desaparece debajo: azul relleno y etiqueta para los que tienen
tráfico, ámbar hueco y etiqueta más discreta para los menores activos. El panel
lleva la leyenda, porque un color que no se explica no informa de nada. La capa
sigue sin persistirse.

### Los acentos: la explicación que era falsa

Ayer se attributuyó a una corrupción al escribir el archivo. **Era una línea del
generador**, `name.encode("ascii", "ignore")`, puesta a propósito y con un
comentario que lo justificaba con que los nombres eran para una consola. No lo
son: el archivo se escribe en UTF-8 y el navegador lo lee en UTF-8. Los acentos
vuelven: "Martín Miguel de Güemes", 26 nombres con acento.

### El radio que no se respetaba

**Lo que reportó el operador:** escribía 5 NM, apretaba el mapa, y el círculo
salía de 2.987 NM. No se podía crear un objeto desde el panel.

**Reproducido en el navegador:** el radio se tomaba de la distancia entre los
dos clics y el valor escrito se descartaba. El panel dibujaba la previa con el
número correcto y después lo pisaba, así que lo que se veía no era lo que se
guardaba.

Había dos trabajos distintos mezclados en una sola interacción. Ahora son dos
opciones explícitas, y **la que existía sigue siendo el default**, para que
nada que el operador aprendiera ayer le resulte equivocado hoy:

- **Ajustar con el cursor** — primer clic el centro, segundo el borde.
- **Usar el valor del panel** — un clic, y el número escrito es el que se
  guarda.

En el segundo modo la herramienta **sigue armada** después de crear. El otro
reclamo del operador era que «al crear un elemento se oculta el panel»: no se
ocultaba, se desarmaba la herramienta y con ella desaparecían los campos. Poner
cuatro círculos de 5 NM son cuatro clics.

**El clic que dimensiona ya no hace snap.** El centro ya está puesto, así que
ese clic solo lleva una distancia; el snap lo movía al centro de otra figura y
el radio salía de un punto al que el operador no apuntó. Medido: 4.866 NM donde
se habían pedido 5.

### Las grabaciones

**El operador dijo que las de ayer no se guardaron bien. Se guardaron: cada una,
dos o tres veces.** 34 filas con 8 grupos de duplicados exactos.

`_store_track` construía la fila y la insertaba siempre, sin preguntar si esa
trayectoria ya estaba. Pedir dos veces el mismo vuelo —el operador recargando el
panel, un reintento tras un timeout, la caché de trayectoriasstarting vacía en
cada carga— insertaba una fila nueva cada vez.

Ahora busca primero. La coincidencia es la misma aeronave, el mismo vuelo sobre
ella y el mismo número de puntos. Dos cosas **no** son repetidas, a propósito:

- una trayectoria más escasa sobre la misma ventana: son los datos distintos de
  una grabación parcial, y esconderla detrás de la completa sería perderla;
- otro vuelo de la misma aeronave: `callsign` y `flight_id` son parte de la
  clave. Sin ellos, dos vuelos que se solapan en el tiempo se colapsaban y el
  segundo quedaba archivado bajo el callsign del primero — una etiqueta
  incorrecta y segura, no una duplicata inofensiva. **Lo encontró un test
  propio, no la inspección.**

`session_id` no es parte de la clave: una sesión y una trayectoria descargada
pueden describir los mismos puntos, y son la misma trayectoria. Cuando se
encuentran, la sesión se engancha a la fila que ya existe, así que el replay la
sigue encontrando.

**Las 16 filas duplicadas que ya hay en la base no se borraron.** Son datos del
operador y la decisión es suya.

### Lo que falta verificar

`frontend/tests/typed-sizing.spec.js` — 11 tests. Corrieron una vez: 8 pasaron,
3 fallaron. Uno era un bug real (la herramienta quedaba armada pero sorda, porque
`cleanup()` cancela la suscripción a los clics) y está corregido. Los otros dos
son precisión de los propios tests: uno espera 9260 m exactos y el código da
9249,6 porque `metros / 111320` grados es una aproximación; el otro espera un
snap con tolerancia de 0,00005 grados cuando hace falta más. **No volvieron a
correr.** La suite frontend completa y el build tampoco, por lo mismo.

Los 39 tests de `airports.spec.js` pasan y los 6 de `tests/test_track_dedup.py`
pasan, y el arreglo de deduplicación **sí** se verificó revirtiéndolo: 3 de sus
6 tests fallan sin él.

**Totales en verde: 382 + 7 Python, 39 de aeropuertos, 675 de paridad.**

---

## 0.28.1 — Dos bugs que la suite no veía, y uno congelaba la aplicación

Encontrados al verificar el 0.28.0. Los dos están en el camino de dibujo, los
dos estaban presentes desde antes, y los dos son del mismo tipo: **una suposición
que nadie comprobó**.

### 1. Un clic en modo panel congelaba la pestaña

**Síntoma:** con «Usar el valor del panel» activado, el primer clic colgaba el
navegador. No se veía nada: ni un círculo, ni un error, ni forma de
cerrar la pestaña.

**Causa:** el motor emite eventos recorriendo un `Set` con `forEach`, y `forEach`
**visita las entradas agregadas durante el propio recorrido**. Al dejar la
herramienta armada, cada confirmación se desuscribía del clic y se volvía a
suscribir — y como la suscripción nueva entraba en el `Set` mientras se recorría,
era visitada en esa misma vuelta. Confirmaba, se suscribía otra vez, y el
recorrido no terminaba jamás.

Es el peor tipo de bug: no lanza, no falla un test, simplemente el hilo principal
se queda dentro de un bucle.

**Arreglo:** la suscripción no se toca nunca. Un handler estable, suscrito una
sola vez al armar la herramienta, que se queda mientras la herramienta esté
armada. Lo que cambia entre una figura y la siguiente es el borrador, y el
borrador no es la suscripción. `cleanup()` se partió en `_clearDrawing()` —que
limpia borradores, teclado y cursor— y la desuscripción se quedó en el camino de
desarme, que es donde corresponde.

**Cómo se verifica sin colgar la suite:** con el arreglo puesto y un clic, la
pestaña se congela y la corrida **no termina nunca**. Un test que cuelga el
proceso no es una guarda, es una guarda que no puede avisar. Así que el test
confirma una figura llamando al commit a mano, sin pasar por el clic: ejecuta el
mismo código y devuelve un número. Comprueba que el handler registrado es **la
misma función** que antes, no solo que haya uno: desuscribirse y volver a
suscribirse deja el conteo en uno igual, y el conteo no ve nada.

### 2. El enganche al centro nunca funcionó

**Síntoma:** hacer clic cerca del centro de un círculo o un radial no lo tomaba.
La función se agregó en 0.27.0 y llevaba rota desde entonces.

**Causa:** `centreLatLng` es lo que venga en `latlng` desde la API, que es un
objeto `{lat, lng}`. El código de enganche lo leía como `centre[0]` y
`centre[1]`, que en un objeto da `undefined`: la distancia salía `NaN`,
`NaN <= tolerancia` es falso, y **nada se enganchaba nunca**.

**Por qué los tests lo daban por bueno:** el fixture que usa `centre-snap.spec.js`
arma su círculo con `latlng` como **array**. Un array sí tiene índices. El test
pasaba con una forma de dato que la aplicación nunca usa.

**Arreglo:** `_collectCentres()` normaliza a `[lat, lng]` y descarta lo que no
venga en números. Acepta las dos formas, así que un `L.LatLng` real también
funciona.

**Verificado revirtiendo cada arreglo:**

| Arreglo revertido | Qué pasa |
|---|---|
| Normalización de `_collectCentres` | 1 test falla: el enganche no ocurre |
| Re-suscripción al confirmar | 1 test falla con la identidad del listener |

Con la re-suscripción puesta y el test viejo —que sí hacía clic— la corrida se
cuelgaba en lugar de fallar. Por eso el test se reescribió.

### Verificado en el navegador real

Con «Usar el valor del panel» y radio 5 NM: **cuatro clics, cuatro círculos, los
cuatro de 5 NM (9260 m)**, la herramienta sigue armada después de cada uno, el
número de listeners no cambia y los cuatro clics toman 2,36 s. No hay congelamiento.

Con el modo de siempre, «Ajustar con el cursor»: el primer clic solo fija el
centro y no crea nada, el segundo crea el círculo con el radio que marca la
distancia entre los dos clics —4,495 NM para dos clics separados 0,09° de
longitud— y la herramienta se desarma después, como antes.

**Totales: 335 tests de frontend, 334 en verde.** El que falla es el
`flight-history.spec.js` de siempre, por timeout con la suite entera en
paralelo; aislado pasa en 6,7 s. **382 + 7 Python, 675 de paridad, build limpio
en 39 s.**

---

## 0.29.0 — El mapa toma el ancho que le dan, y los logos donde deben

Pediido por el operador: el mapa mas ancho, a todo el ancho de la pantalla; los
paneles mas compactos; el logo de AeroRF mas grande; y el logo de ENACOM puesto
correctamente, con un pie de pagina abajo con el nombre de la Direccion y el
logo mas pequeno.

### El hallazgo: el mapa no se enteraba de su propio espacio

**Este es el que de verdad explica lo del ancho, y no era cosa de los paneles.**

`MapEngine.invalidateSize()` existia y no lo llamaba nadie. Abrir o cerrar un
panel, o arrastrar su borde, dejaba el mapa con el tamano que tenia al cargar la
pagina.

Medido en el navegador: con el sidebar abierto, el contenedor del mapa mide
**584px** y Leaflet sigue dibujando en **800px**. Los 216px del sidebar quedan
muertos y el mapa se ve aplastado a la izquierda. Ese desacuerdo es exactamente
lo que el operador describe como "el contenedor del mapa debe ser mas grande", y
por mas que se agranden los paneles no se arregla: el mapa no se redibuja en el
espacio que le acaban de dar.

**Arreglo:** un watcher en el shell que avisa al motor cuando cambia cualquiera
de las cuatro cosas que mueven el espacio —los dos anchos y las dos Aperturas—
con `flush: 'post'` y un retraso corto, para que no mida una anchura a medio
transicionar.

**Verificado revirtiendo el arreglo, en el navegador:** con el watcher
neutralizado, contenedor 584 y Leaflet 800. Con el watcher, los cuatro estados
comprobados cuadran: 584, 328, 544 y 800, y en todos el tamano de Leaflet
coincide con su contenedor.

Este arreglo se verifico en el navegador y no con un test, a proposito: el shell
del mapa no se monta en los archivos de prueba de la cabecera —el `router-view`
de la ruta `/` no llega a renderizarlo alli—, y forzar la prueba por el store
terminaba midiendo el store equivocado. Un test que pasa por una via que la
aplicacion no usa es la misma trampa del fixture en array del enganche al
centro.

### Paneles: menos cromo, mas mapa

Los anchos por defecto bajan de **268 y 300** a **216 y 256**. Noventa y seis
pixeles menos de cromo. El maximo no se toca, asi que alguien que haya
arrastrado un panel a lo ancho lo sigue teniendo ancho, y un ancho guardado
gana siempre al valor por defecto: nadie pierde el tamano que ya tenia.

El padding de las tarjetas de los paneles baja de `p-3` a `p-2` en las ocho
secciones de herramientas, y de `p-3` a `p-2` la raiz de los cinco paneles
laterales: de 12px a 8px, cuatro pixeles por lado que vuelven al contenido. El
Inspector baja a `p-2.5`, que es lo que ya usaban el de vuelos y el de capas.

### El alto: el shell se salia de la pantalla

Al anadir el pie, el shell del mapa pedia `100vh` **y** estaba debajo de una
cabecera de 48px y encima de un pie de 26px. La pagina crecia 74px y el borde
inferior del mapa —con el, la barra de estado— se caia fuera de la pantalla: un
mapa que scrollea en una pantalla pensada para ser una vista fija.

Las dos barras ahora son variables, `--brandbar-h` y `--footerbar-h`, puestas en
`App.vue` junto a las barras que las miden, y el shell pide
`calc(100dvh - var(--brandbar-h) - var(--footerbar-h)`. Comprobado en el
navegador: 48 + 508 + 26 = 582, que es exactamente la altura de la ventana, sin
desborde.

### Los logos

**El de AeroRF, de 30px a 34px.** La barra compacta mide 48px, asi que deja 7px
arriba y abajo: la marca crece sin que la cabecera crezca, y en el mapa la
altura de la cabecera sale del mapa.

**El de ENACOM, el oficial.** El archivo mide 267x68 y es RGB(11, 23, 66) sobre
fondo transparente, medido sobre el propio archivo. Sobre la barra casi negra
**no se ve**. Va sobre una ficha blanca redondeada, que es lo que conserva los
colores oficiales tal cual; un filtro que lo aclarara para que combinara con el
fondo seria otro logo, y eso no es "poner el logo correctamente".

El comentario del archivo decia antes que no se dibujaba ninguna marca porque los
logotipos oficiales estan protegidos y una imitacion dentro de una herramienta
que lleva el nombre de la institucion estaria mal. El archivo existe porque la
institucion lo aporta, asi que la imitacion no es el caso. El comentario se
corrige y dice por que se usa el que se usa.

**El pie de pagina** es un componente propio, `FooterBar.vue`, 26px, con el logo
en 12px —mas pequeno que el de la cabecera, que es lo pedido— y el nombre
completo de la Direccion al lado. Sale en **todas** las pantallas, incluida el
mapa. Se podria haber hecho solo para las vistas de documento, con el argumento
de que el mapa ya tiene su barra de estado: no. Un pie que existe unicamente en
las pantallas que el operador menos visita es justo el que falta cuando hace
falta. Los 26px son el precio y son un precio conocido, y estan anotados como
tal en el propio componente.

### Pruebas

342 en verde, 27 archivos, contra 335 de antes.

El test de la cabecera afirmaba que el lockup **contenga el texto "ENACOM"**, y
dejo de cumplirlo en cuanto la marca paso a ser una imagen. No es un problema:
comprobaba la forma, no el hecho. Ahora afirma que la imagen lleva
`alt="ENACOM"`, que es como lo lee un lector de pantalla, y que el nombre
completo sigue estando como texto en pantalla. El test que decía "no dibuja una
imitacion de la marca oficial" se sustituyo por el que afirma lo que ahora
importa: que la imagen es el archivo que aporta la institucion y que va sobre
fondo blanco.

Siete pruebas nuevas en `layout.spec.js` y `brandbar.spec.js`, que leen el CSS
construido, que es el unico sitio donde un tamano existe de verdad. Las cuatro
nuevas de layout se verificaron revirtiendo: shell a `100vh` falla, logo a 30px
falla, sin la ficha blanca falla.

**Totales: 342 frontend, 382 + 7 Python, 675 de paridad, build limpio.**
---

## 0.29.1 — Las cinco herramientas que no guardaban nada, las cinco pestañas, el menú sin fondo y el cursor

Cuatro cosas del operador, en un lote. Una era un fallo de datos, no de aspecto.

### LO IMPORTANTE: LÍNEA, POLÍGONO, MEDIR, TRAZA Y COBERTURA NO GUARDABAN LA FORMA

El operador dijo que esas herramientas «deben generar el objeto y persistir».
Generaban el objeto. La forma se perdía.

`draw.js`, en `finish()`, emite los vértices como `properties.path` (línea, traza,
medición) o `properties.ring` (polígono, cobertura). La traducción a GeoJSON de
`stores/map.js` leía **solo** `latlngs`, así que para las cinco tomaba la salida
temprana:

- línea, polígono, cobertura y traza se guardaban como **Point** en su primer
  vértice;
- medición se guardaba **sin geometría ninguna**.

Medido contra la API que está corriendo, antes del arreglo: los cuatro volvieron
`geometry_type=Point` con un vértice. El pedido **era exitoso**: volvía un id,
aparecía «Creado: …», y el objeto entraba en la base. Por eso se leía como «no
guarda» y no como un error: no había error que ver.

Círculos y radiales no estaban afectados: llevan centro y medida, y el backend
arma el anillo. Que es también la única razón por la que esos sí se veían.

**El arreglo** es una línea de precedencia en `toApiPayload`: si no hay `latlngs`,
busca `properties.path` y luego `properties.ring`. Se corrige en el único punto de
escritura, así que ningún llamador tiene que acordarse y las dos formas en que se nombran
los vértices no pueden discrepar en silencio.

Verificado en el navegador, con la herramienta real y clics de verdad: una línea
de tres clics se guardó como `LineString` con sus tres vértices. Y por la misma
ruta, `polygon` → `Polygon` 3 vértices, `coverage` → `Polygon` 3, `trace` →
`LineString` 4, `measurement` → `LineString` 2.

**Por qué once tests de `objects.spec.js` estaban en verde sobre una función rota.**
Sus fixtures usan `latlngs`, que es un campo real y que la traducción maneja bien:
es la forma que **nada en la aplicación produce**. Es la misma trampa que el
fixture en array del enganche al centro. Las once comprobaban la conversión de
una forma que no llega nunca, y por eso no tocaron el fallo real. Hay ahora nueve
pruebas nuevas con los payloads que las herramientas emiten de verdad, y una que
comprueba que `latlngs` sigue gaining precedencia sobre `path`.

Se verificaron revirtiendo: sin el arreglo fallan **siete**.

### LAS CINCO PESTAÑAS DE LA BARRA LATERAL

Medido antes: el strip necesitaba **312 px** y la barra lateral tiene **215**. Con
`flex: 1 1 0` las cinco se encogían por debajo de lo que su texto necesitaba, así
que **«Expediente» quedaba completamente fuera**: no apretado, invisible. Los
otros cuatro se veían recortados.

Cada pestaña es ahora un icono sobre un rótulo corto: `✎ Herram.`, `▩ Capas`,
`✈ Vuelos`, `⌖ Aerop.`, `▣ Exped.`. Suman 162 px en 215, y `flex: 0 1 auto` con
`nowrap` hace que si una ventana llega a ser estrecha se trunquen de forma
visible en vez de empujar una pestaña fuera del strip.

Los iconos se **comprobaron antes de elegirlos**: cada uno se dibujó en un canvas
y se comparó su mapa de bits contra un carácter de uso privado, que siempre
sale como caja. Los catorce candidatos salieron distintos del `.notdef`, así que
ninguno es un rectángulo hueco en la fuente de otra persona.

El nombre completo sigue en el botón, como `title` y como nombre accesible. Eso
no es adorno: dos tests buscaban el texto completo y dejaron de encontrarlo, y lo
correcto era comprobarlos donde el nombre vive ahora.

### EL MENÚ DE CLIC DERECHO NO TENÍA FONDO

El mensaje era «el fondo está muy transparente y no se ve». Estaba escrito como
`bg-slate-900/98`, y **98 no es un paso de la escala de opacidad de Tailwind**,
que va 0, 5, 10 … 95, 100. La clase nunca se generó: el menú no tenía fondo
ninguno y se veía el mapa por detrás de su texto.

Comprobado contra el CSS construido: `.bg-slate-900\/98` no aparece, y la única
regla `.bg-slate-900\/N` de todo el paquete es `/60`.

El fondo ahora está fijado en CSS, en la regla de `.aerorf-context`. Cualquier
cosa que tenga que ser legible no debería depender de un paso de opacidad que
puede no existir.

**Una guarda que no fallaba, y cómo se notó.** La primera versión de la prueba
buscaba `/background:\s*#[0-9a-f]{6}/`, que es verde sobre un color translúcido:
el minificador convierte `rgba(15, 23, 42, 0.45)` en `#0f172a73`, y la regex veía
los primeros seis dígitos y pasaba. Salió al revertir. Ahora exige seis dígitos y
**un lookahead negativo de otro dígito hexadecimal**, que es lo que distingue un
color opaco de uno con alfa; más un rechazo explícito de la forma de ocho
dígitos.

### EL CURSOR DEL MAPA

La hoja de Leaflet pone `cursor: grab`, así que sobre el suelo el puntero era una
mano abierta. El motivo que dio el operador es el que manda: una mano no muestra
dónde se hace el clic. En un mapa cuya labor es poner un punto en una coordenada
exacta, el punto exacto tiene que estar bajo el cursor siempre; una cruz lo
marca, una mano lo tapa con la palma.

Es `crosshair` y no la flecha por la misma razón: la punta de la flecha está
desplazada arriba y a la izquierda, así que un vértice se colocaba a unos
píxeles de donde se apuntaba. Arrastrar sigue funcionando; solo cambia el
puntero, también mientras arrastra, porque la mano es justamente lo que se está
reemplazando. Los objetos interactivos conservan `pointer`, para que algo
 pulsable siga diciendo que se puede pulsar.

El selector lleva dos clases a propósito, para ganar contra la regla de Leaflet
esté o no sea la última hoja en emitirse.

### Verificación

**355 tests frontend en verde**, 27 archivos, contra 342. **382 Python**, 7
deseleccionadas. **675 de paridad geodésica.** Build limpio.

Guardas nuevas: 9 en `objects.spec.js`, 4 en `layout.spec.js`, 2 reescritas en
`components.spec.js`. Las de layout leen el CSS construido, que es el único sitio
donde un tamaño existe de verdad; y hay que **reconstruir antes de
correrlas** o pasan con el `dist` viejo. Cuatro se verificaron revirtiendo:
cursor a `grab` falla, menú translúcido falla, `flex: 1 1 0` falla, y el arreglo de
la traducción falla siete.

Los 17 objetos de prueba que se crearon al verificar se borraron. En la base
quedan los tres del operador: un círculo, un radial y una anotación.
---

## 0.29.2 — El mapa no se movía: había un escudo invisible encima

El operador reportó que apretar en el mapa y arrastrar no lo movía. No se
reprodujo el síntoma exacto, pero se encontró la causa, y era real.

### LA CAUSA

Detrás del menú de clic derecho había un escudo: `fixed inset-0`,
`pointer-events: auto`, `z-index: 1240`, que cerraba el menú con `@click`.

Medido en el navegador, en el mismo punto del mapa:

- menú cerrado, ahí está el canvas de Leaflet, y un arrastre mueve **16.906 m**;
- menú abierto, ahí está **`DIV.fixed.inset-0`**, y el mismo arrastre mueve **0 m**,
  y el menú sigue abierto.

O sea: con el menú abierto, el `mousedown` que empieza el desplazamiento se lo
comía el escudo, y el mapa no se enteraba.

Y por qué sobrevivía al arrastre: **un arrastre no produce `click`**. La
pulsación y la soltada caen en puntos distintos, así que el navegador no sintetiza
ningún `click`, `@click` no llegaba a dispararse, el escudo se quedaba durante
todo el gesto y hacía de tapón invisible.

### EL ARREGLO

**Se eliminó el escudo.** El cierre ahora es un listener de `mousedown` en
`document`, registrado solo mientras el menú está abierto y en fase de captura.

- **Captura** para que el menú ya esté cerrado cuando corre el manejador de
  Leaflet y arranca el desplazamiento.
- **No detiene la propagación**, a propósito: la misma pulsación cierra el menú
  **y** empieza a desplazar.

Verificado: con el menú abierto, el **primer** arrastre mueve 16.906 m y el menú
se cierra; el segundo mueve 16.867 m. Antes: 0 m y el menú abierto.

El menú sigue funcionando igual: pulsar dentro no lo cierra, y «Crear punto» crea
el objeto y lo cierra.

### LO QUE NO SE LOGRÓ REPRODUCIR

No pude reproducir «se mueve y vuelve atrás», que es como lo describió el
operador. Descarté, midiendo: nada tapando el mapa (1302 puntos de hit-test),
`dragging` habilitado, herramienta armada (con LÍNEA armada el mapa sí se mueve),
arrastre nativo de imagen (el `dragstart` se cancela), selección de texto, y mis
cambios de 0.29.0 (con el watcher de `invalidateSize` anulado, idéntico). Nada
mueve el mapa por su cuenta en 40 s.

Un arrastre real del navegador desplaza 58 km y el mapa se queda ahí.

Siguen faltando tres datos que solo tiene el operador: si el zoom con la rueda
funciona, si vuelve exactamente al origen o se detiene a mitad, y cuánto se mueve
antes de volver.

### DOS ERRORES PROPIOS, CORREGIDOS

**Un arnés de prueba que daba un diagnóstico falso.** Medí «el mapa solo se puede
desplazar una vez por carga de página» y estuve a punto de arreglarlo. Era mi
arnés: lanzaba `mousemove` sobre `document`, así que `e.target` era el propio
`document`, que no tiene `className`, y el `removeClass` de Leaflet reventaba a
mitad de `finishDrag`, dejando la bandera `Draggable._dragging` puesta. Con los
eventos apuntando al elemento correcto, cuatro arrastres seguidos funcionaron
(19.719, 19.675, 19.656 y 19.637 m).

**Una guarda que no podía fallar.** La primera versión del test del escudo
filtraba por `getBoundingClientRect()` buscando algo que cubriera la pantalla. En
jsdom **no hay layout**: todos los rectángulos valen cero, así que el filtro no
podía encontrar nada, ni siquiera al bug. Pasaba con el escudo puesto. Ahora
comprueba la estructura renderizada, que sí es comprobable.

### ARREGLO DE PASO: UN TEST QUE CADUCÓ SOLO

`test_flight_history.py` falla desde el 2026-10-01 sin que se haya tocado nada.

`NOW = 1_790_696_090` (2026-09-29) estaba fijo, con el comentario «fixed so the
windows are reproducible». Pero el endpoint ancla el **fin** de su ventana al
**reloj real**, así que la distancia entre ambos crecía un día por día.

Con `days=8` la ventana empezaba el 2026-09-23 18:02 UTC — derivado del «ahora»
real — y el vuelo más viejo del fixture está en 2026-09-22 15:34 UTC: un día
fuera de la ventana que debía probar que era alcanzable.

Un test que solo pasa los dos días siguientes a escribirse no está fijando
comportamiento, está fijando el calendario.

`NOW` ahora sale del reloj real. **No se debilitó ninguna afirmación**: las doce
del archivo están escritas en términos relativos a `NOW`, así que las distancias
entre los tres vuelos y los límites de las ventanas no cambian. El servicio de
OpenSky está simulado, así que nada toca la red ni la base.

### Verificación

**358 tests frontend en verde**, 27 archivos, contra 355. **382 Python**, 7
deseleccionadas. **675 de paridad geodésica.** Build limpio.

Guardas nuevas: 3 en `components.spec.js`, sobre el escudo, el cierre por
`mousedown` y el hecho de que la pulsación no se consuma. Verificadas revirtiendo:
con el escudo repuesto falla una; con `click` en vez de `mousedown` fallan dos.

Se borró el objeto de prueba que se creó al verificar. En la base quedan los tres
del operador.
---

## 0.29.3 — Los objetos borrados volvían a aparecer, dibujados pero sin poder seleccionarse

El operador: al borrar objetos, seguían viéndose en el mapa; ya no se podían
seleccionar para volver a borrarlos. Y aparecían objetos viejos que hacia tiempo
había borrado.

### LA CAUSA

Los objetos no se agregan directamente al mapa: se agregan a un `LayerGroup` por
categoría (`circles`, `radials`, `reference_points`…), mediante `ensureCategory()`.

`removeObject()` llamaba a `layer.remove()`, y eso **solo lo saca del mapa**: no
lo suelta del grupo que lo contiene. El grupo se queda con la referencia.

Y `LayerGroup.onAdd` vuelve a agregar **todos** sus hijos. Así que en cuanto esa
categoría se volvía a mostrar, la capa regresaba dibujada.

Medido en el navegador, sobre la aplicación corriendo, después de borrar tres
objetos:

| | store | mapa | `featureLayers` | hijos del grupo |
|---|---|---|---|---|
| tras borrar | 0 | 0 | 0 | **1, 1, 1** |

Con **un solo `restack()`** volvían los tres al mapa. Y ninguno tenía handler de
selección: de ahí exactamente lo de «visibles pero inactivos». `restack()`
corre en cada cambio de capa o de categoría, así que reaparecían solos.

Lo que lo hace difícil de ver es que **todo lo demás daba bien**: `map.hasLayer`
decía que no, y `featureLayers` estaba vacío. Los dos indicadores obvios eran
correctos mientras el bug estaba vivo.

### EL ARREGLO

`removeObject()` ahora suelta la capa del grupo antes de sacarla del mapa. El
grupo queda guardado en la capa como `_aerorfHost` al registrarla, para no tener
que buscarla entre todos.

```js
const host = layer._aerorfHost
if (host && typeof host.removeLayer === 'function') host.removeLayer(layer)
layer.remove()
```

`clearObjects()` y `destroy()` ahora pasan por `removeObject()`, en vez de tener
su propio bucle con `layer.remove()`. Que haya un solo camino de baja es lo que
evita que un segundo camino se quede atrás: los dos tenían la misma fuga.

**El mismo bug pasaba con cada actualización.** `renderObject()` empieza llamando
a `removeObject()`, así que mover un objeto o cambiarle el estado dejaba la capa
vieja en el grupo. Tres renderizados del mismo objeto dejaban tres capas:
**una sola prueba, y fallaba.**

### Verificado

En el navegador, con los objetos viniendo de la base (recarga en medio): tras
borrar los tres, store 0, mapa 0, **grupos 0, 0, 0**, `featureLayers` 0, handlers
0. Un `restack()` no devuelve nada. Quitar la categoría del mapa y volver a
ponerla tampoco.

### Pruebas

**366 en verde**, 27 archivos, contra 358. Ocho pruebas nuevas en
`canvas-hit-targets.spec.js`, que usan un `MapEngine` real sobre un mapa real de
Leaflet.

Están **afirmadas sobre los hijos del grupo**, y no sobre `map.hasLayer` ni sobre
`featureLayers`, porque esos dos eran correctos mientras el bug estaba vivo y no
podían verlo. Esa es la razón de que este bug pasara tanto tiempo: los
indicadores que se miran primero no lo detectan.

Verificadas revirtiendo: **8 de 16 fallan** al quitar el `removeLayer` del grupo.

**382 Python · 675 de paridad · build limpio.**

### Una nota sobre el estado de los datos

La base quedó con **0 objetos**: los tres del operador (círculo, radial,
anotación) y los de prueba ya estaban borrados antes de este arreglo. Cuando
vuelvas a abrir la aplicación no vas a ver ningún objeto, y eso es correcto: no
queda ninguno. Los que veías en pantalla eran justamente las capas que no se
quitaban.
---

## 0.29.4 — Trayectorias que se acumulan, el botón que no limpiaba, y diálogos propios

Tres cosas del operador en un lote.

### 1. LAS TRAYECTORIAS SE ACUMULABAN Y NO SE BORRABAN

Síntoma: al elegir un vuelo se acumulaban los trayectos, «vuelos del mismo avión
en distintos días», y al apretar «Quitar todas» quedaba todo.

**Es el mismo bug de 0.29.3, en otra clase.** `drawTrack` agrega con
`layer.addTo(this.trackGroup)`, y `removeTrack` llamaba solo a `layer.remove()`,
que saca la capa del mapa pero **no la suelta del grupo**. `LayerGroup.onAdd`
vuelve a agregar todos sus hijos.

Medido en el navegador con dos vuelos de `e02659`: el grupo tenía **2** hijos
después del primero y **3** después del segundo, y un solo `restack()` devolvía
los tres.

Y `clearTracks`, que es lo que llama «Quitar todas», tenía la misma fuga: vaciaba
su propio `Map` y dejaba cada capa en el grupo, así que el siguiente `restack()`
traía el lote entero de vuelta.

El arreglo es el mismo de 0.29.3: `removeTrack` y `clearTracks` sueltan la capa
del grupo antes de sacarla del mapa.

### 2. EL BOTÓN «LIMPIAR» NO LIMPIA

`clearSearch()` reseteaba `searchResult`, `selectedIcao24`, `track` y `error`, y
**no tocaba `query`**, que es lo que el operador ve en la caja. Cuando apretaba
«Limpiar» seguía escribiendo su ICAO24 ahí, y el botón parecía no hacer nada.

`query` es un objeto de cuatro campos, no un texto: `query.value = ''` habría
dejado el store con algo que no es esa forma y el siguiente render habría
reventado en `query.callsign`. Se resetea campo por campo.

Y deliberadamente **no** toca `tracks`: esas son las trayectorias cacheadas que
el mapa está dibujando, y «Limpiar» está al lado de la caja de búsqueda, no del
seguimiento. Lo que las limpia es «Quitar todas».

### 3. LOS DIÁLOGOS: «localhost:5199 dice…»

Los dibuja el navegador, no la aplicación: pone el origen de la página como título
y los estilo con los controles del sistema operativo. En medio de una herramienta
institucional, eso parece una página web colada. Y no se puede estilar.

Había **siete**: cuatro `confirm` (eliminar objeto desde la barra y desde el
inspector, seguir aeronave) y tres `prompt` que se usaban como respaldo del
portapapeles para mostrar un texto precargado que nunca se editaba.

**Ahora los dibuja la aplicación.** `systemStore.ask()` devuelve una promesa, así
que el lugar de la llamada se lee como una pregunta con respuesta:

```js
if (await systemStore.ask({ title: 'Eliminar objeto', message: '…', danger: true })) …
```

`systemStore.notify()` es para lo que ya pasó y no necesita respuesta, y
reemplaza los `prompt`.

`DialogHost.vue` se monta una vez en `App.vue`. El estado vive en el store porque
las preguntas vienen de tres sitios que no son ancestros entre sí, y así hay
**exactamente un diálogo en pantalla, por construcción**.

Detalles que importan:

- **«Eliminar» es rojo.** Una caja destructiva que se ve como todas las demás es
  una cosa más que hay que leer con cuidado antes de apretar.
- **Escape cancela**, y también cierra el aviso. Una confirmación que no se puede
  descartar solo se puede responder con el ratón, y la mano puede estar en el mapa.
- **El fondo se cierra con `mousedown`, no con `click`**: la misma trampa en la
  que cayó el escudo del menú de clic derecho en 0.29.2.
- **`pre-line`** en el mensaje, porque la pregunta de «seguir aeronave» necesita
  una línea en blanco entre la pregunta y la consecuencia.
- El aviso va abajo al centro, para no tapar ni la barra de herramientas ni la
  lectura de coordenadas.

**Un error mío en el camino:** primero dejé `const dialog = () => store.dialog` en
el componente. En una plantilla una función siempre es verdadera, así que
`v-if` nunca fue falso y `dialog.title` era `undefined`: la caja salía sin título,
sin mensaje y con dos botones sin etiqueta. Salió al mirarlo en el navegador.

### Pruebas

**379 en verde**, 27 archivos, contra 366.

Catorce pruebas nuevas en `components.spec.js`:

- **Una que no deja pasar ningún `window.confirm`/`alert`/`prompt`** en todo
  `src/`. Es una comprobación a nivel de fuente, a propósito: afirmar que cada uno
  de los siete lugares renderiza algo pasaría igual si mañana apareciera un
  octavo `window.confirm`. Esta falla en el momento en que alguien vuelve a buscar
  la caja del navegador, y **señala el archivo y la línea**.
- El store del diálogo: qué devuelve `ask` según la respuesta, qué pasa si llega
  una segunda pregunta con la primera abierta (la primera se responde sola con
  «no», si no su `await` queda colgado para siempre), y `notify` con su cuenta
  atrás.
- El componente: título, mensaje, los dos botones, `role="alertdialog"`, y que
  Cancelar y el fondo lo cierren.
- Las trayectorias: reemplazar en vez de apilar, y que `clearTracks` vacíe el
  grupo.

Verificadas revirtiendo: trayectorías **3 de 59 fallan**; con un `window.prompt`
de vuelta **1 falla** y nombra `ContextMenu.vue:228`; sin el reset de `query` **1
falla**.

**382 Python · 675 de paridad · build limpio.**
---

## 0.29.5 — El avión que no se iba, ocho herramientas, medir en vivo, y el inspector de aeronaves

Cuatro cosas del operador.

### 1. EL AVIÓN SE QUEDABA TRAS BORRAR TODOS LOS VUELOS

**Tercera instancia del mismo bug.** `syncMarkers` y `clear` llamaban
`marker.remove()`, que saca el marcador del mapa pero **no lo suelta del
`LayerGroup` `aircraft`**. `LayerGroup.onAdd` reagregan sus hijos.

Verificado en el navegador: dibujadas 2 aeronaves, al vaciar `liveStates` quedan
**0 en el mapa y 0 en el grupo**, y un `restack()` ya no las devuelve.

Ahora los cuatro caminos de baja pasan por un solo `_detach(layer)`, que suelta
del grupo y saca del mapa. Cuatro lugares lo hicieron mal por separado una vez
cada uno; que sea un método es lo que evita que vuelvan a divergir.

**Y un bug que encontró su propia guarda:** al refactorizar, `clear()` se quedó
con el `entry.marker.remove()` viejo — el reemplazo por script no aplicó — y la
prueba nueva lo cazó (`expected 2 to be +0`).

### 2. TRAZA Y POLÍGONO, FUERA

El operador: hacen lo mismo que línea y cobertura. Cuatro formas de dibujar dos
figuras es una de más en una barra del ancho de una mano.

**Se van de la paleta, no del sistema.** Siguen en `TOOL_META`: un objeto guardado
como `polygon` o `trace` tiene que seguir dibujándose, etiquetándose y
exportándose, y borrar el **tipo** dejaría huérfano lo que ya está en la base. La
herramienta es lo que sobraba, no el dato. Se filtran con `HIDDEN_TOOLS`, y del
menú de clic derecho también salen.

La paleta queda con **8 botones**, verificado en el navegador.

### 3. MEDIR: LECTURA EN VIVO

Medí lo que pasaba: MEDIR **sí** creaba el objeto entre dos puntos, pero
**no mostraba ninguna cifra mientras el operador se movía**. El número solo
existía después, que es justo el momento en que no sirve.

Añadido `_renderLiveDistance()`: una caja en el punto medio del segmento que el
puntero está extendiendo, con la distancia del tramo y, desde el tercer punto, el
total. Medido:

- 1 punto: nada, todavía no hay nada que medir;
- 2 puntos: `977.8 m · 0.528 NM · 0.978 km`;
- 3 puntos: `811.2 m · 0.438 NM · 0.811 km · total 1.789 km · 0.966 NM`.

**Dos cosas que estaban mal y no se veían en el código:**

Las etiquetas de medición vivían en el `<style scoped>` de `GisShell.vue`. Son
contenido de `divIcon`, y Leaflet construye ese elemento en tiempo de ejecución:
nunca recibe el `data-v-…` que necesita un selector con scope. Medidas: **10×19 px,
sin fondo, sin borde, sin color** — texto pelado. Movidas al bloque global, junto
a `.aerorf-popup`.

Y el `span` era `display: block` dentro de una caja de icono de tamaño cero, así
que tomaba el ancho 0 del padre y colapsaba a su relleno. Con `inline-block`
mide **169×19 px** con su fondo.

### 4. EL INSPECTOR AL HACER CLIC EN UN AVIÓN

El clic **siempre** puso `selectedIcao24`; nada lo mostraba. El panel seguía
diciendo «Seleccione un objeto» con el avión ya elegido: la información se pedía
y no aparecía en ninguna parte.

Ahora el clic abre el inspector, y el panel tiene una sección de aeronave:
identidad, **procedencia** (posición en vivo o última conocida, fuente y edad),
altitud, velocidad, rumbo, en tierra, posición, hora, la trayectoria con su
desglose por procedencia y su longitud, y los objetos RF cercanos.

La procedencia va **primero**, y es texto: si la posición tiene más de un minuto,
el panel dice «última posición conocida» en vez de dar a entender que el avión
sigue ahí.

**La nota de causalidad se mantiene**, junto a los objetos RF: proximidad
geométrica, y que eso no dice que haya interferido con la aeronave.

**Un error mío, grave.** Añadí el bloque de aeronave con `v-if`, y eso **le robó
el `v-else` al panel del objeto**: `v-else` se empareja con el condicional
hermano *inmediatamente anterior*. Con nada seleccionado se renderizaban los dos, y
el del objeto leía `object.color` sobre un `object` nulo. **Eso tumbaba el shell
del mapa entero**: el mapa no se dibujaba. Lo encontré porque el navegador dejó de
arrastrar y `engine` era `null`, y lo confirmaron ocho pruebas que ya estaban en
verde. Ahora es `v-else-if`, y hay una prueba que monta el panel con objeto **y**
aeronave a la vez.

### Pruebas

**386 en verde**, 27 archivos, contra 379.

Siete pruebas nuevas: la paleta con 8 botones y sin los dos duplicados; el
inspector de aeronave con sus campos, su procedencia y su frase de causalidad; el
objeto mandando sobre la aeronave; y los marcadores soltándose de su grupo.

Verificadas revirtiendo: `clear()` viejo y la paleta completa, **2 de 66 fallan**.
El conteo de `active-tool.spec.js` pasó de 10 a 8 botones, con el motivo anotado:
afirmar sobre el número y no sobre «más de uno» hace que una herramienta que
desaparezca tenga que ser una edición deliberada.

**382 Python · 675 de paridad · build limpio.**
---

## 0.30.0 — La paleta institucional: azul oscuro, la misma familia

El operador pidió «misma familia» que `rni-app-4.0` (2026-10-01). Esto es esa
paleta, y el motivo por el que es la correcta está en un dato.

### EL AZUL DE LA FAMILIA ES EL DEL LOGO DE ENACOM

`rni-app-4.0` lo dice en su propio archivo, y es lo que lo hace institucional y
no una preferencia:

> `--ink` es **EXACTAMENTE** el azul del logo oficial (`logoenacom.png`,
> monocromático `#0B1742`); el resto son azules derivados de ese.

`--ink` es `#0b1742` = **RGB(11, 23, 66)**, que es exactamente lo que medí del
logo cuando tuve que ponerle la ficha blanca porque sobre fondo oscuro no se veía.
No es parecido: es el mismo color.

Por eso el logo sobre la barra no es una excepción. Es el color de la familia, y
por eso va sobre una ficha blanca y nunca invertido con un filtro — un filtro haría
otro logo.

### LOS TOKENS

`src/assets/tokens.css`, copiado **por nombre** del proyecto hermano. Si allá
cambia un token, hay que cambiarlo acá: es el mismo sistema, no una paleta
parecida.

Los doce de la familia: `--ink`, `--ink-soft`, `--paper`, `--surface`, `--line`,
`--signal`, `--signal-deep`, `--signal-on-ink`, `--risk-ok`, `--risk-mid`,
`--risk-high`, `--sin-dato`. Más los derivados de texto sobre fondo oscuro
(`--on-ink`, `--on-ink-soft`, `-faint`, `-wash`).

**`--signal-on-ink` existe por una razón medida.** `--signal` sobre `--ink` da
2.52:1, por debajo del mínimo de 3:1 que WCAG pide para elementos gráficos;
`--signal-on-ink` da 6.15:1. En AeroRF el fondo oscuro está en todas partes —la
barra, el panel, el inspector—, así que usar `--signal` sobre `--ink` haría
invisible justo lo que tiene que verse: la pestaña activa, el botón apretado, el
anillo de foco.

Y los **quince propios**, porque un mapa es una superficie oscura permanente con
capas dibujadas una sobre otra, y eso necesita su propia escala de profundidad y
sus propios colores de trazo: `--fondo`, `--panel`, `--panel-alto`,
`--panel-hondo`; `--texto` en cuatro niveles; `--borde` en dos; y los de trazo
(`--trazo`, `--trazo-medido`, `--trazo-observado`, `--trazo-vuelo`,
`--trazo-borrador`, `--trazo-fin`, `--medicion`, `--seleccion`).

Medido en el navegador, después: fondo y barra `rgb(11, 23, 66)`, panel lateral
`rgb(16, 29, 77)`, pestaña activa `rgb(110, 150, 255)`.

### LEAFLET NO PUEDE LEER `var(--x)`

Es la razón de que exista `src/assets/tokens.js`: Leaflet pasa el color tal cual
al atributo `stroke` o al canvas, y ahí no hay nada que resuelva una variable.

`token(nombre, fallback)` lee la variable del `:root` y la cachea —los tokens son
constantes, no hay theming—, y `tokenConAlfa()` convierte un hex para los rellenos
que esperan `rgba(...)`. Los **27 colores que se le pasan a Leaflet** salen de ahí.

### EL PUENTE, Y LO QUE CUESTA

Las plantillas llevan **642** clases `slate-N` y **194** de otros colores: más de
800 referencias, ninguna por token. Reescribirlas a nombres semánticos es el
estado final y sigue pendiente; hacerlo en la misma pasada que el cambio de color
hubiera significado 800 ediciones sin forma de distinguir un cambio de una errata,
el mismo día que toda la interfaz cambia de color.

Así que hay un bloque de unas treinta reglas que hace que todas esas utilidades
resuelvan a la paleta nueva, sin tocar una sola plantilla.

**El costo es real y hay que decirlo: los nombres ahora mienten.** `bg-slate-900`
es azul. Un desarrollador que escriba `bg-slate-900` mañana obtiene `--panel` y no va a
saber por qué, y el nombre de Tailwind no dice nada sobre la paleta institucional.

Se escribió así —después de `@tailwind utilities`, misma especificidad, más abajo
en el archivo— en vez de redefinir la paleta `slate` de Tailwind, por dos razones
que importan más que la prolijidad: redefinir `slate` sería una mentira mayor
(la rampa es semántica, no una escala 50→900, así que habría que inventar once
pasos), y un bloque con nombre se puede **borrar**. Cuando las plantillas migren,
esta sección se va con ellas y nadie más tiene que saber que existió.

### TRES FALLOS REALES EN EL CAMINO

**El `@import` estaba en el lugar inválido y el build salió limpio igual.** El
import de `tokens.css` quedó después de las tres directivas `@tailwind`, que es
inválido: un `@import` que sigue a cualquier otra sentencia se descarta, y PostCSS
lo deja pasar. El build no se quejó —nada de lo que produce está mal, la hoja de
estilos resultante es válida—, pero en pantalla `getComputedStyle` devolvía vacío y
`body` caía a transparente sobre negro. **Nada en el código fuente dice que falta
un token: hay que preguntarle al navegador.** Eso motivó `tests/tokens.spec.js`.

**Había un segundo juego de tokens, y `--surface` significaba lo contrario.**
Existía un `:root` pequeño en `styles.css` (`--bg`, `--surface`, `--muted`, …) con
`--surface: #0f1724`, un panel **oscuro**, mientras que `--surface` en la familia es
`#ffffff`, una superficie **clara**. Dos `:root` en una hoja no pueden definir el
mismo nombre, y el que estaba después ganaba: `--on-ink`, que se construye sobre
`--surface`, iba a resolver a un azul oscuro y todo el texto sobre los fondos
oscuros iba a ser oscuro sobre oscuro. Medido antes de borrarlo: de sus ocho
nombres, **solo `--muted` se usaba**, dos veces, en ese mismo archivo.

Esto **corrige lo que dije el 2026-10-01**: afirmé que en AeroRF no había
variables de token. Había un bloque chico, casi muerto. Lo que no había —y sigue
sin haber— es un sistema que las plantillas usaran.

**Dos pruebas comparaban hex literales.** `layout.spec.js` exigía que el menú de
clic derecho tuviera `background:#xxxxxx`, y `active-tool.spec.js` que el botón
apretado tuviera fondo y borde en hex. Con los tokens, las dos fellaron contra
cosas **correctas**: un menú perfectamente opaco y un botón pintando bien. Esa es
la forma de aserción que se borra en vez de arreglarse, y por la que el defecto
original vuelve a entrar por la misma puerta. Ahora ambas **resuelven el token y
comprueban el color que llega a pantalla**, así que la opacidad se sigue
comprobando y un token inexistente sigue fallando.

### UN INCIDENTE QUE MERECE QUEDAR ESCRITO

Escribí código con backticks a través de PowerShell, que es el carácter de escape
de ese intérprete. Cada backtick se comió el carácter siguiente: `assets/` quedó
como `ssets/` y **dejó dos caracteres BEL (U+0007) dentro del archivo de pruebas**,
que dejó de parsear. Se detectó porque la corrida dio «no tests» en lugar de un
fallo.

Se reparó, y además se pasó un barrido por los 21 archivos modificados buscando
caracteres de control: **solo ese archivo tenía**, dos. La lección ya estaba en las
notas del proyecto y se incumplió igual: para cualquier cosa con acentos o
backticks, la herramienta de escritura, no PowerShell.

También rompí la aplicación a mitad de camino: reemplacé los 27 colores de Leaflet
por `token(...)` **sin importar `token`** en los cinco archivos. El build lo
detectó recién después de agregar los imports.

### Pruebas

**430 en verde**, 28 archivos, contra 386.

`tests/tokens.spec.js` es nuevo, con 44 pruebas. Las que importan:

- **El bundle tiene que contener los tokens.** Leen el CSS **construido**, no el
  fuente: el fuente puede contener un token que nunca llega. Ycomparan los
  **valores** de la familia, no solo los nombres, porque un token con el nombre
  correcto y el valor desviado es peor que uno ausente: parece deliberado.
- **El `@import` tiene que ir antes de `@tailwind`**, que es el defecto exacto que
  Provocó esta sección. Se afirma contra la regla real y no «que sea la línea 1»,
  porque el archivo también importa las fuentes web y dos `@import` seguidos son
  válidos.
- **El puente gana sobre lo que generó Tailwind.** Misma especificidad, así que
  decide la posición en el archivo: si alguien mueve el bloque arriba, todas las
  reglas siguen siendo correctas y todas pierden.
- **Cada utilidad de color que una plantilla usa está remapeada.** Así un
  `bg-slate-700` nuevo no sale gris sin que nadie lo note hasta que alguien mira la
  pantalla.
- **Solo un bloque de tokens**, para que ningún nombre pueda quedar definido dos
  veces con significados distintos.

**382 Python · 675 de paridad · build limpio.**

### Lo que queda

- **Migrar las plantillas** de `slate-N` a nombres semánticos, y borrar el puente.
  Es lo que hace que los nombres dejen de mentir.
- **Las tipografías.** `rni-app-4.0` usa Space Grotesk, IBM Plex Sans e IBM Plex
  Mono; AeroRF usa Inter y JetBrains Mono. Queda por decidir: IBM Plex Sans no
  tiene mayúsculas tan esbeltas como las del panel de 9 px, así que la barra
  lateral y la de herramientas necesitarían un peldaño más de tamaño.
---

## 0.30.1 — Buscar un vuelo pasado: el archivo propio responde antes de rendirse

El operador buscó el vuelo de ayer por su nombre de vuelo y la aplicación le dijo
que no había ninguna aeronave. Ese mensaje era técnicamente cierto y prácticamente
inútil, y por debajo había dos defectos y una imposibilidad.

### LO QUE EL OPERATOR VIO, TEXTO LITERAL

```
Invalid ICAO24 'lvkcc': expected 6 hex characters.
```

En inglés, dentro de una aplicación que debe estar toda en español, sin decir qué
hacer, y **repetido cuatro veces** en cuatro rutas distintas de
`flight_service.py`. Cuatro copias de un mensaje divergen; por eso ahora hay un
solo sitio donde se redacta: `_explicar_icao24_invalido`.

Lo que cambió es la parte que faltaba. Antes explicaba por qué falló; ahora dice
qué escribir:

> «LVKCC» no es una dirección de aeronave: un ICAO24 son seis caracteres
> hexadecimales (0-9 y a-f), y aquí hay 3 que no lo son. Si es un nombre de vuelo
> como LVKCC, escríbalo en el campo de callsign: ese campo sí funciona para
> aeronaves que están volando ahora.

**La rama del callsign sólo se abre con caracteres fuera del alfabeto
hexadecimal**, y eso corrigió un falsehood propio: la primera versión decía
«tiene letras», lo cual es **falso** para `abc` — tres letras hexadecimales
válidas, a las que sólo les falta longitud. Hay una prueba con ese caso.

### EL DEFECTO DE FONDO: RENUNCIAR DEMASIADO PRONTO

El aviso de callsign ya estaba en español y **sí se veía en el panel**. Lo que
no hacía era todo lo que la aplicación sabía.

La secuencia real: OpenSky publica sólo vectores en vivo, así que un callsign que
no está transmitiendo no aparece; sin dirección no hay forma de preguntar por el
historial; y la búsqueda se rendía ahí con un «no se encontró». Pero **la propia
aplicación guarda la dirección de cada aeronave que alguien siguió**.

Medido en la base el 2026-10-02: de 47 pistas archivadas, **45 llevan callsign, y
son 17 llamadas distintas**. Para esos casos el vuelo pasado sí se encuentra.

`search_flight` consulta el archivo **después** de los vectores en vivo —lo que
está volando manda, porque son dos aeronaves distintas— y cuando encuentra la
dirección sigue por el historial de OpenSky como si se la hubieran dado. La ruta
recibe la sesión que ya tenía y no pasaba.

Contra el backend real:

```
callsign=ARG1763  ->  e02659  via  callsign_archivo_aerorf  1 vuelo
```

### LO QUE NO SE INVENTÓ

- **La dirección sale de una fila que el sistema escribió**, no de una
  conjetura. No hay estimación en ninguna parte.
- **No se declara que la aeronave esté volando.** `states` —que son los vectores
  en vivo— queda vacío, y hay una prueba que lo exige: presentar un vuelo de ayer
  como si fuera una señal de ahora es el error que este proyecto no quiere
  cometer.
- **La procedencia es visible.** `resolved_via` distingue `callsign_live_state`
  de `callsign_archivo_aerorf`, y el panel lo dice en palabras: «vectores en vivo de
  OpenSky» frente a «archivo de vuelos de AeroRF». Eso no es pulido: es que
  «la vi transmitiendo ahora» y «la tengo guardada de hace meses» son dos clases
  de evidencia distinta, y confundirlas es precisamente lo que no hay que hacer.

### UNA AFIRMACIÓN QUE NO PODÍA SOSTENER

La primera versión devolvía una lista vacía cuando el archivo no se podía
consultar, y el mensaje afirmaba ante el operador que **no había ningún vuelo con
ese nombre en el archivo** —sin haberlo abierto—. Un sistema diciendo algo sobre sí
mismo que nadie comprobó.

Ahora `_direcciones_en_archivo` devuelve `None` para «no pude mirar» y `[]` para
«miré y no estaba», y son dos mensajes distintos. El que sí se pudo mirar incluye
además cuántas pistas hay: «47 vuelos registrados en total», que convierte un
negativo en algo con peso.

El archivo tampoco puede tirar la búsqueda: si la base falla, es un aviso, no un
500. Un backend que se cae por consultar su propio archivo no puede usarse.

### LO QUE SIGUE SIN SER POSIBLE, Y SE DICE

OpenSky no tiene búsqueda histórica por callsign, con credenciales o sin ellas.
Hay una prueba que falla si ese texto desaparece del código, porque es lo que
explica por qué un vuelo pasado necesita su dirección.

Y el mensaje viejo mandaba al operador a **`/states/all`**, que es un endpoint de
la API: nadie lo tiene abierto delante. Hay una guarda que prohibe que esa cadena
vuelva al servicio.

### Pruebas

**54 Python nuevas · 8 frontend nuevas.** 436 Python · 438 frontend · 675 de
paridad · build limpio.

Todas verificadas **revirtiendo el arreglo**, que es lo único que prueba una
guarda. Dos de ellas no fallaron la primera vez, y las dos enseñaron algo:

- Una comprobaba que el aviso contuviera la palabra «archivo» —que tienen **los
  dos** mensajes—, así que revirtiendo el `None` por `[]` pasaba en verde. Ahora
  comprueba la frase que los distingue.
- La guarda de la plantilla sólo miraba que el mapa de traducciones existiera, no
  que la plantilla lo usara: volver a la clave cruda pasaba sin fallar.

Y el arnés de reverts tuvo que reescribirse: informaba «todo verde» para dos
reverts que **nunca se habían aplicado**, porque una cadena de PowerShell con
comilla simple conserva `\n` como dos caracteres y los archivos son LF mientras
el literal era CRLF. Un revert que no entra es indistinguible de una guarda que no
funciona, y el segundo caso es el que termina en «borremos la prueba». El arnés
ahora exige que cada sustitución quede escrita antes de reportar.

### FUERA DE ALCANCE, PERO DENTRO DE LA PREGUNTA

El 400 de la ruta decía, en inglés, «Provide at least one of `callsign` or
`icao24`». El front lo interceptaba, así que nunca se veía; el endpoint directo
sí. Corregido al español que ya usaba el front.

### Queda

- **Las tipografías** (`rni-app-4.0` usa Space Grotesk / IBM Plex Sans / IBM Plex
  Mono; AeroRF usa Inter y JetBrains Mono). Sin decidir. IBM Plex Sans no tiene
  mayúsculas tan esbeltas como las del panel de 9 px, así que la barra lateral y
  la de herramientas necesitarían un peldaño más de tamaño.
- **Migrar las plantillas** de `slate-N` a nombres semánticos y borrar el puente
  de 0.30.0.
- **Rotar `OPENSKY_CLIENT_SECRET`**: está en texto plano en el historial de la
  sesión. Vive en `.env`, que está ignorado por git, y en ningún archivo
  versionado.
- **16 filas duplicadas de `aircraft_tracks`**, sin decisión del operador.
---

## 0.30.2 — La trayectoria en vivo se congelaba con la aeronave todavía volando

El operador siguió una trayectoria de un avión, siguió viendo la aeronave moverse
en vivo, y la línea dejó de crecer: se veía hasta el punto en el que había
dibujado sus objetos. Ninguna pantalla decía qué había pasado.

Había **dos** defectos, y ninguno era «la trayectoria está tapada».

### EL QUE MATABA EL CRECIMIENTO

La condición que decide si la línea sigue creciendo leía **la lista equivocada**.

El estado vivo de una aeronave llega por WebSocket a `liveStates` y se le pega a
cada fila en un `computed` llamado `watchlistWithState`. La condición leía
`watchlist` —la lista cruda— buscando un campo `.state` que **esa lista no
tiene**. La rama del feed vivo era código muerto.

Medido sobre las dos aeronaves que el operador estaba siguiendo:

```
listaCruda     e06543  state = AUSENTE
               e0b354  state = AUSENTE
listaConEstado e06543  on_ground=false  has_position=true   <-- está volando
               e0b354  sin estado
```

Con el defecto, `isAirborne` caía **siempre** a la heurística de los dos minutos:
que el final del track fuera reciente. Y ésa es una pésima señal para decidir si
un avión está volando, porque el track de OpenSky y el vector de estado del mismo
avión **son productos distintos y no se actualizan a la vez**: el track se queda
viejo antes de que la aeronave deje de volar. Bastaba un hueco de datos de un
minuto para matar el sondeo.

**Por qué el síntoma era tan confuso**: el marcador y la línea vienen de caminos
distintos. El marcador, de los vectores de estado, por WebSocket. La línea, del
sondeo cada 30 s. Congelar uno no toca el otro — y por eso se veía un avión vivo
con una línea muerta.

### EL QUE LA HACÍA PARPADECAR

El sondeo corre cada **30 s** y el caché de tracks dura **300 s**. Nueve de cada
diez sondeos recibían los mismos bytes: la línea se quedaba quieta cinco minutos
y después saltaba.

Un vuelo histórico es inmutable y su track puede cachearse cinco minutos sin
perder nada. **Un vuelo en curso no.** Así que ahora hay dos TTL: `CACHE_TTL_TRACKS_S`
(300 s, el de siempre) y `CACHE_TTL_TRACKS_LIVE_S` (30 s), que es el único que
gasta créditos de más y sólo mientras alguien sigue una aeronave en el aire.

La vía es explícita de punta a punta: `fresh` en la ruta → `ttl` en `build_track`
→ `ttl` en `get_track` → `_cached`. **Ninguna ruta lo adivina**: adivinar sería
cobrar créditos por datos que no cambian.

### UN CAMBIO MÍO ROMPIÓ DOS PRUEBAS, Y ESTO ES LO QUE PASÓ

Al pasar `ttl=` a `service.get_track`, **cuatro dobles de prueba** con la firma
vieja (`test_flight_history.py` ×3 y `test_trajectory_contract.py`)recibieron un con
`TypeError`, que `build_track` captura y convierte en «no hay track de OpenSky».
Dos pruebas pasaron a rojo con un mensaje que **apuntaba al lugar
equivocado**: no a mi cambio, sino a datos de OpenSky que sí estaban bien.

Lo comprobé contra la API viva antes de culpar a nadie: `a101c3`, 20 vuelos, y los
tres más viejos devolvieron puntos y `covered_window` correctos. Los datos
estaban; el que estaba roto era mi cambio.

**La lección que ya está anotada en este proyecto:** un `except Exception` que
convierte cualquier fallo en «el proveedor no tiene datos» no es robustez, es
ceguera. Convierte un error de programación en un diagnóstico falso.

### Pruebas

**452 Python · 438 frontend · 675 de paridad · build limpio.**

16 nuevas, **todas verificadas revirtiendo el arreglo** con un arnés que exige
que cada sustitución quede escrita antes de reportar:

| Se revierte | Falla |
|---|---|
| la condición vuelve a leer la lista cruda | `test_no_busca_state_en_la_lista_cruda` |
| el sondeo deja de pedir fresco | `test_el_sondeo_pide_fresco` |
| el store ignora `fresh` | `test_el_cliente_deja_pasar_fresh` |
| la ruta deja de acortar el caché | `test_la_ruta_tiene_fresh` |
| el servicio ignora el `ttl` | `test_get_track_recibe_el_ttl` |
| el TTL por defecto vuelve a 600 s | las dos del caché |

**La quinta no fallaba la primera vez.** Las pruebas usaban un servicio falso y
verificaban que `build_track` *pasara* el ttl, pero nadie comprobaba que
`get_track` lo *entregara* a la caché, que es donde el valor se vuelve efectivo.
Un servicio que aceptara el parámetro y lo tirara dejaba todo verde con el
defecto entero. La prueba nueva lee el código del servicio y exige que el ttl
llegue hasta `_cached`.

### Lo que encontré y NO toqué

Medido en el navegador, el orden real de dibujo del canvas compartido (por
`_leaflet_id`) es:

```
aircraft_tracks (35) → airports (141) → radials (357) → circles (358)
   → traces (364) → lines (365) → polygons (366) → user (369)
```

**La trayectoria es la segunda de abajo**: cualquier objeto con relleno se pinta
encima de ella. Confirmado con ids (`trackDebajo: true`). No es el defecto que
reportó el operador —el relleno por defecto es 15 % de opacidad, no oculta una
línea— pero es incorrecto: la trayectoria es el dato y el operador tiene que ver
dónde pasó el avión **por encima** de su propia cobertura.

También: `CATEGORY_DRAW_RANK = { circles: -1 }` pretende poner el disco de un
círculo debajo de un radial, y con `preferCanvas` **no lo consigue**: el canvas
dibuja por orden de inserción, y los ids no cambian al re-agregar un grupo. El
comentario describe un comportamiento que el mecanismo no produce.

Queda para decidir con calma, no para tocar a último momento.

### Pendiente, sin cambios

- **Las tipografías**, sin decidir desde hace tres secciones.
- **Rotar `OPENSKY_CLIENT_SECRET`**, en claro en el historial de esta sesión.
- **La pantalla de credenciales**: la parte 1 (sólo lectura + «verificar ahora»)
  sigue sin hacerse, y es lo único de aquella propuesta que no depende de entrar a
  la cuenta de OpenSky.
- Migrar las plantillas de `slate-N` y borrar el puente de 0.30.0.
- **16 filas duplicadas** de `aircraft_tracks`, sin decisión del operador.
- **Otro mensaje en inglés** en una ruta: «OpenSky does not accept future
  timestamps.», en las líneas 298 y 767 de `flights.py`.

---

## 0.30.3 - El avión por encima de cualquier cosa

**Estado:** completada · commits: pendientes de esta misma entrega

### El pedido

Por primera vez el orden de dibujo lo fija el operador con una frase, no una
preferencia nuestra: «el avión debe verse por encima de cualquier cosa», dijo
después de ver una trayectoria tapada. La investigación entera depende de eso: si
una forma con relleno pinta encima del paso del avión, el dato deja de verse.

### Por qué `CATEGORY_DRAW_RANK` no servía

Es lo primero que se probó, y **no puede** lograrlo. El mapa es `preferCanvas`:
un solo canvas y una sola lista de dibujo, ordenada por `_leaflet_id`, que se
asigna cuando la capa se **crea**. Medido en el motor: los ids del grupo eran
idénticos antes y después de un `restack()`, porque quitar y volver a añadir una
capa no la renumera. El rango decide en qué orden se re-agregan los grupos y
nada más.

Y `aircraft_tracks` se crea al montar el shell, mucho antes de que el operador
dibuje nada, así que estaba **segundo de abajo** en la lista real:

```
aircraft_tracks (35) → airports (141) → radials (357) → circles (358)
   → traces (364) → lines (365) → polygons (366) → user (369)
```

### El mecanismo: un pane propio

Los pane sí funciona, porque cada renderer es un elemento del DOM y el navegador
los apila por z-index. `MapEngine._addTrackPane()` crea `aerorfTracksPane` en
**z-index 500** — sobre el `overlayPane` (400), bajo el `markerPane` (600) — y
las trayectorias se dibujan con `L.canvas({ pane })` propio.

### El precio, y por qué es obligatorio

`pointer-events: none`. Una capa vectorial fuera del overlayPane obtiene su
propio canvas de tamaño completo, y Leaflet le pone `pointer-events: auto`; ese
canvas tapa el mapa por delante y se come todos los clics. Es exactamente el
corte que ya ocurrió con un punto central en el markerPane: nada era
seleccionable y **arreglar los manejadores no servía de nada**, porque ningún
clic llegaba a ninguno. La regla está en `assets/styles.css` y una guarda falla
si desaparece.

### El defecto que encontré al implementarlo

La primera versión movía **sólo la polilínea**. El inventario de hijos de
`drawTrack` para una pista de dos puntos:

| hijo | renderer | ¿se veía sobre las formas? |
|---|---|---|
| polilínea histórica | el nuevo | sí |
| 2 puntos de waypoint | compartido | **no** |
| extremo inicio | compartido | **no** |
| extremo fin | compartido | **no** |

O sea, tres de cinco elementos seguían debajo de cada objeto con relleno: la
línea se veía y los puntos no, que es el mismo síntoma con la mitad arreglada.

Los extremos además **no podían** pasar al pane nuevo: un path en ese pane no
recibe puntero y los tooltips «Inicio»/«Fin» se abren con el hover, así que la
etiqueta habría dejado de funcionar sin que nadie se enterara. Se convirtieron en
`L.marker` con `divIcon` (markerPane, z 600, encima de la línea) y su aspecto
redondo quedó en una regla **global** de `styles.css`, porque el contenido de un
`divIcon` se monta como cadena HTML y nunca recibe el `data-v-…` de un estilo
acotado.

### Un test que cuelga es peor que un test que falla

La primera versión de la guarda hacía, dentro de un `eachLayer`:

```js
expect(c._renderer).toBe(engine.trackRenderer)
```

Fallaba en la segunda capa —era el defecto real de arriba— y el runner **se
quedó colgado para siempre, sin ningún mensaje**. El formateador del diff con dos
renderers de Leaflet adentro no termina, y como la ejecución es síncrona ni
siquiera corre `testTimeout`: los 8 s de timeout no se dispararon. Diagnosticado
marcando el avance en disco con `appendFileSync`, porque el stdout se bufferiza y
al matar el proceso se pierde.

La regla que queda escrita en el encabezado del archivo: se recogen hechos
**planos** (números, strings, booleanos) y se espera sobre *ellos*, con el
resumen en el mensaje de error. Si falla, se ve qué capa y por qué.

### Verificación por reversión

| qué se revirtió | guarda que falló | mensaje |
|---|---|---|
| `renderer: render` de los puntos | «todas las formas se dibujan en ese renderer» | `expected 2 to be +0` |
| `L.marker` → `L.circleMarker` | «los extremos son marcadores» | `expected +0 to be 2` |
| regla `pointer-events: none` del canvas | «la regla alcanza también al canvas» | `expected false to be true` |

Cada revertido por separado, para que se vea qué guarda atrapa qué. La del
renderer se verificó **después** de restaurar los extremos: con los tres a la vez
la aserción del renderer abortaba antes, en el conteo, y no habría quedado
probada.

### Línea base

`pytest -m "not integration"` **452** · `vitest` **448 en 30 archivos** (438 + 10
nuevas) · `geo_parity` **675** · build limpio.

---

## 0.30.4 - Las filas duplicadas de `aircraft_tracks`

**Estado:** completada · decisión del operador: «borra filas»

### El número que dije no era el correcto

Vengo arrastrando «16 filas duplicadas» desde hacía varias sesiones. **No
reproduce de ninguna forma.** Ninguna agrupación que probé da 16:

| agrupación | grupos repetidos | filas sobrantes |
|---|---|---|
| geometría idéntica (sha1 del `geometry`) | 9 | **11** |
| icao24 + callsign + sesión + conteo + tiempos | 8 | 10 |
| icao24 + callsign + conteo | 9 | **11** |
| icao24 + callsign | 10 | 28 |
| icao24 | 8 | 41 |

Dos agrupaciones independientes —la geometría y la clave de identidad— coinciden
en **11**, y es lo único inequívoco: misma geometría es el mismo track guardado
dos veces. El 16 era un número mío que ya no se sostiene; aquí queda corregido.

### Se borró con respaldo y con integridad comprobada

- Copia previa: `C:\Users\lucas\AppData\Local\Temp\opencode\aerorf-antes-de-borrar.db`
  (647 168 bytes). Está en el temporal del sistema: si hace falta conservarla,
  hay que moverla; con los datos que son —pistas de OpenSky, no evidencia de un
  expediente— no justificaba meterla en el repositorio.
- Se conserva la fila de **id más alto** de cada grupo.
- `aircraft_positions.track_id` tiene `ondelete="CASCADE"` sobre
  `aircraft_tracks.id`: comprobado antes de borrar que **0 posiciones** estaban
  apoyadas en las 11 filas, así que no quedaron huérfanas.
- **53 → 42** filas; verificado contra la base después, no contra el diccionario
  en memoria: **0 grupos con geometría repetida y 0 filas sin geometría** (las
  que no son comparables habrían ocultado duplicados).
- `aerorf.db` no está trackeado por git, así que esto no aparece como cambio en
  el repositorio.

## 0.30.5 - La base en el mismo sitio, con respaldo y con versión

**Estado:** completada · auditoría de Claude, ítem **P0-06**, primero por decisión
del operador

### P0-06 no puede ir en sexto lugar

La auditoría de Claude ordena once P0 y deja P0-06 en sexto. No puede ir ahí:
P0-01 pide `nullable=False` sobre `numero_expediente` y P0-03 pide limpiar filas
ya guardadas, y **los dos necesitan lo que falta aquí** —una versión de esquema
y un respaldo previo— para no romper cada base que ya está instalada. P0-06 no
es un ítem más, es el que desbloquea a otros tres: entra primero.

### El defecto: la base seguía al directorio de trabajo

El default era `sqlite:///./aerorf.db`, una ruta **relativa**. Relativa se
resuelve contra el directorio de trabajo del proceso, así que arrancar por
`start.bat`, por `uvicorn` desde otra carpeta o desde el IDE creaba un
`aerorf.db` distinto en cada caso y lo guardado en uno no existía en el otro.
Ése es entero el síntoma que se resume en «se perdieron los expedientes»:
**no se perdió ninguna fila, la aplicación miraba a otra parte.**

`.env.example` traía esa misma línea, así que cualquiera que copiara el ejemplo
reintroducía el problema.

**Arreglado sin mover el archivo.** `RUTA_BASE_SQLITE` apunta a la raíz del
proyecto y `_anclar_sqlite` pasa por encima de cualquier `DATABASE_URL`
relativa. Elegí anclar en vez de trasladar a `data/` porque la ubicación no era
el defecto y moverlo habría añadido un riesgo —arrancar con la base vacía—
que es exactamente lo que se está arreglando.

### Lo que medí antes de tocar nada

Busqué `aerorf*.db` en todo el disco: **sólo hay una**, de 647 168 bytes. No se
había partido en dos todavía. Encontré además un `-wal` de **4 198 312 bytes**
contra un `.db` de 647 168, con marca de hora más reciente.

**Corrijo lo que dije al verlo.** Afirmé que esas 4 MB eran transacciones sin
llegar al archivo principal. No lo son: al abrir la base (que hace checkpoint
automático al cerrar) el `.db` pasó a 679 936 bytes, el WAL quedó en 0 y los
conteos eran **idénticos antes y después** — 1 expediente, 2 objetos, 42
pistas. El WAL guardaba imágenes de páginas, no filas. Nada estuvo en peligro.

Lo que un respaldo ingenuo sí pierde es lo que se escribe **con el servidor
corriendo**, que es exactamente cuando se respalda. El riesgo se sostiene; la
cifra que lo ilustraba era mía y estaba inflada.

### Un respaldo que copia el archivo no vale

Con WAL, las últimas escrituras viven en `aerorf.db-wal` hasta que un checkpoint
las mueve al `.db`. `shutil.copyfile` copia un archivo atrasado, y lo hace justo
en el peor momento: con el servidor vivo. Por eso el respaldo va por
`sqlite3.Connection.backup`, que lee a través del WAL y deja un archivo
completo y abirible por su solo cuenta.

- **Se hace en cada arranque, antes de escribir nada** (`RESPALDOS_ACTIVOS`).
- En `respaldos/` de la raíz; `*.db` ya estaba en `.gitignore`, así que no hace
  falta tocarlo.
- Rotación automática, conservando `RESPALDOS_CONSERVAR` (10 por defecto).
- Un respaldo que falla **se registra y se arranca igual**: una aplicación que
  no levanta porque no pudo hacer una copia es un resultado peor que una que
  levanta sin ella, con tal de que el fallo sea ruidoso.

### Versionado de esquema, que antes no existía

`PRAGMA user_version` valía **0** en la base instalada, y lo único que había era
`create_all`, que crea tablas que faltan y es estructuralmente incapaz de añadir
una columna o una restricción a una base existente. La primera columna nueva —
`numero_expediente` perdiendo su nulabilidad ya está en cola — habría roto cada
base en el campo.

Ahora hay `VERSION_ESQUEMA` y `MIGRACIONES`. La versión **no avanza si el paso
falla**: sentencias y sello dentro de la misma transacción, con `ROLLBACK` si
algo revienta, porque el caso peor no es una migración rota, es una migración
rota que ya dice estar hecha. Y si la base es de una AeroRF **más nueva**, no se
toca nada y se dice en español.

### Seis reverts, once guardas que mordieron

Cada arreglo se revirtió por separado y se volvió a correr la suite:

| revert | guardas que fallaron |
|---|---|
| vuelta a `sqlite:///./aerorf.db` | 2 — *«ruta relativa, seguiría al directorio de trabajo: aerorf.db»* |
| `Connection.backup` → `shutil.copyfile` | 1 — *«el respaldo no trajo la fila escrita en el WAL»* |
| no lanzar con una base más nueva | 2 — `DID NOT RAISE BaseDeDatosMasNueva` |
| el sello de versión no avanza | 2 — `assert 0 == 1` |
| la rotación deja de borrar | 2 — *«sobrevivieron los equivocados»* |
| `init_db` sin mantenimiento | 2 — *«esperaba un respaldo y hay 0»* |

La prueba del WAL **demuestra el defecto** y no sólo el arreglo: inserta una
fila, fuerza el checkpoint del esquema, escribe otra y mantiene la conexión
abierta para que la fila se quede en el WAL, y entonces compara una copia del
archivo (0 filas) con el respaldo (1 fila). Quien sustituya la API de SQLite por
un `copyfile` la pierde y la prueba revienta.

### Un número del documento que no reproducía

`AERORF_ARCHITECTURE.md` decía **357 unitarias** mientras el conjunto ya daba
452 antes de este cambio. Misma clase de caducidad que el «16 duplicados» de
0.30.4: un número que quedó escrito y dejó de corresponder. Medido ahora con
`pytest --collect-only -m "not integration"`: **466 pruebas en 15 archivos**, y
las 7 de integración siguen siendo las de `test_websocket.py`.

### Verificación

| Comprobación | Resultado |
|---|---|
| `pytest -m "not integration"` | **466 pasan**, 7 deseleccionadas (antes 452) |
| Arranque real del backend | `db.respaldo respaldo creado antes de arrancar \| archivo=aerorf-20261003-103529.db bytes=679936` |
| | `db.migracion esquema llevado a la versión 1 \| desde=0 hasta=1` |
| | `db.version esquema sin versionar adoptado como versión 1` |
| Endpoints | `/expedientes/`, `/map/layers`, `/flights/tracked`, `/map/objects/stats` → **200** |
| Frontend, paridad, build | 448 en 30 archivos · 675 · limpio |
| Estabilidad | 1 archivo de vitest falló en la primera corrida de la sesión y **no se reprodujo en las 10 siguientes**. El detalle se perdió en un filtro de la salida, así que queda sin identificar: si vuelve, capturar la salida entera la primera vez |

Los mensajes llegan en UTF-8 correcto: las bytes del `ó` en el log son `C3 B3`.
Conviene anotarlo porque el primer chequeo lo hice mal —busqué un `0x3C` de más
en el patrón y devolvió falso— y parecía un texto roto.

---

### Pendiente (lista viva)

Resueltos en esta entrega: **P0-06** de la auditoría de Claude (base anclada,
respaldo automático, versión de esquema).

Decisiones que tomó el operador al revisar la auditoría:

- **P0-02 — borrar expedientes con objetos GIS vinculados: bloquear con 409.**
  Coherente con lo que ya pasa al revés, que borrar un objeto vinculado sí está
  bloqueado. Nada se pierde en silencio.
- **Se empieza por P0-06** y de ahí se sigue con el resto de la auditoría.
- **El modelo de despliegue sigue sin decidir** — una PC por técnico o servidor
  compartido —, así que el middleware de `Origin` va acotado a los orígenes de
  CORS configurados, que sirve para los dos casos sin comprometer nada.

### Pendiente de antes

- **Migrar las plantillas** de `slate-N` a nombres semánticos y borrar el puente
  de 0.30.0. Decidido por el operador; por hacer. Es el cambio más grande que
  queda y va solo.
- **Tipografías**: adoptar Space Grotesk / IBM Plex Sans / IBM Plex Mono y subir
  el peldaño del texto de 9 px de los paneles. Decidido; por hacer.
- **Pantalla de credenciales**: el operador quiere que si falta la credencial el
  agente pueda ponerla, con **una sola clave para todas las PCs** y prioridad en
  que funcione sin trabas. Verificar antes de guardar y acotar a loopback siguen
  siendo la condición para que un error de teclado no rompa la instalación de
  todos.
- **Rotar `OPENSKY_CLIENT_SECRET`**, en claro en el historial de esta sesión.
- **Otro mensaje en inglés** en una ruta: «OpenSky does not accept future
  timestamps.», en las líneas 298 y 767 de `flights.py`.
- **`CATEGORY_DRAW_RANK`**: sigue describiendo un comportamiento que el rango no
  produce (`circles: -1`). El orden del avión ya no depende de él, pero el
  comentario de la intención sobre círculos y radiales sigue sin cumplirse.
- **`.env.example` no trae `CACHE_TTL_TRACKS_LIVE_S`** — omisión del 0.30.2, la
  mía. Está en `config.py` con default 30 y no estaba documentada.