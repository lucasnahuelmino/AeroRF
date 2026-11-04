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

## 0.30.6 - El WebSocket se rendía en modo anónimo

**Estado:** completada · auditoría de Claude, ítem **P0-04**

### Se reprodujo con dos instancias a la vez

El mismo momento, la misma base, dos servidores:

| | instancian con credenciales | instancian anónima |
|---|---|---|
| `GET /flights/live` | 200 | **200**, `auth=anonymous` |
| `/ws/flights` | consulta con `auth=oauth2` | **0 peticiones**, manda `not_configured` |

La cuenta de peticiones es la prueba, no la impresión: en el log de la
instancia anónima hay **0** líneas `auth=oauth2` y exactamente **una** petición
a `states/all`, que es la de la ruta REST. El WebSocket no hizo ninguna.

Para que la instancia saliera realmente anónima hubo que vencer un detalle de
medición: en PowerShell `$env:X = ""` **borra** la variable, así que `.env` la
rellenaba con `override=False` y la prueba salía «con credenciales» sin que se
notara. Lo que funcionó fue dejarla presente pero en blanco, que `_env` ya
trata como ausente. El `hello` lo anunciaba igualmente (`opensky_configured`),
y es por eso que se pudo descartar el falso negativo.

### La causa: un predicado que pregunta otra cosa

`ws.py` hacía `if not service.configured`. Eso responde «¿hay credenciales
OAuth2?», y lo que hace falta saber es «¿puedo consultar estados?» — que es
`can_query_states`, y que OpenSky sí responde a llamadas anónimas desde su
bolsa de 400 créditos diarios.

**La ruta REST ya lo tenía bien**, en `flights.py::_service_or_503`:
`configured or can_query_states`. El canal de WebSocket era el único que no.

Al arreglo le cambié también el mensaje: decía «defina
`OPENSKY_CLIENT_ID`…», que era inútil en un equipo donde lo que faltaba era
activar lo anónimo. Ahora dice las dos formas de salir.

### Las guardas

Cinco pruebas en `tests/test_p004_websocket_anonimo.py`. Llaman a `Hub._tick`
directamente con el servicio y el WebSocket falsos, así que miden la decisión
sin servidor, sin tiempo de por medio y sin gastar crédito.

- **Antes del arreglo**: `assert 0 == 1`, con el mensaje
  «el WebSocket no consultó OpenSky en modo anónimo: estados de salida
  `['not_configured']`».
- **Después**: 5 en verde.
- Las otras cuatro no son decorado: una comprueba que con credenciales sigue
  consultando, otra que **la compuerta sigue cerrada** cuando de verdad no hay
  forma de consultar (si no, la lectura obvia sería «borrar el chequeo» y el
  feed quedaría mudo), otra que la lista vacía sigue ganando al chequeo de
  credenciales —que es lo que evita la consulta global de 4 créditos— y la
  última que el aviso esté en español.

### Verificación en vivo

Instancia anónima reiniciada con el arreglo: `opensky_configured=False`,
**0** apariciones de `not_configured`, y el WebSocket emitió
`GET https://opensky-network.org/api/states/all?icao24=e06543&icao24=e0b354`
—con sus dos aeronaves, o sea que además usó la lista de seguimiento—.

### Tres cosas que encontré al verificar y que no toqué aquí

1. **`lost` se reenvía en cada tick, y eso cuelga al propio test.**
   `test_feed_does_not_flood` mide durante 22 s con un `while True` cuyo
   timeout es de 22 s por lectura: si llega un frame cada 10 s el bucle nunca
   expira. **Medido con vigilante: sigue corriendo a los 150 s cuando debería
   tardar ~22 s, y sin producir salida.** Un test que se cuelga es peor que uno
   que falla. La causa es del servidor, no del test: el aviso de que una
   aeronave se perdió se repite cada 10 s sin deduplicar, que es justo lo que
   la §48 prohíbe y lo que ese test existe para detectar. Requiere su propio
   commit.
2. **`test_idle_when_nothing_is_tracked` exige una lista vacía y la lista no
   está vacía**: falla en su propia precondición, `count == 0` contra `count
   == 2`, que son `ARG1646` y `LVKMT` añadidos el 02/10. El comentario del
   test asume que «el recorrido se limpia solo y ninguna otra suite la llena»;
   el operador la llenó a mano.
3. **Dos mensajes que se quedaron cortos**: `ws.py:446` manda
   `Unknown action: ...` en inglés al navegador, y el aviso de arranque dice
   «flight features disabled» cuando en modo anónimo las de vuelo **sí**
   funcionan.

Y aclaración sobre los dos rojos de integración: el backend del 8010 se
arrancó a las 10:35, **antes** de este arreglo, y sin `--reload`. Las dos
caídas y el cuelgue se produjeron contra el **código original**, así que no
hace falta ningún revert para descartarlos: nunca pasaron por mi cambio.

### Verificación

| Comprobación | Resultado |
|---|---|
| `pytest -m "not integration"` | **471 pasan**, 7 deseleccionadas (antes 466) |
| `tests/geo_parity.mjs` | 675 pasan |
| Instancia anónima con el arreglo | 0 `not_configured`, `GET states/all?icao24=e06543&icao24=e0b354` |
| Instancia anónima sin el arreglo | 0 peticiones, `not_configured`, 0 líneas `auth=oauth2` |
| Integración (sobre el código viejo) | 5 pasan, 2 caen — preexistentes, ver arriba |

---

### Pendiente (lista viva)

Resueltos hasta ahora en la auditoría: **P0-06** (base anclada, respaldo
automático, versión de esquema) y **P0-04** (el WebSocket en modo anónimo).

**Encontrado al verificar P0-04, sin tocar** — cada uno con su repro y en
espera de commit propio:

- **`lost` se reenvía cada 10 s sin deduplicar**, que es lo que la §48 prohíbe.
  `test_feed_does_not_flood` existe para detectarlo y en vez de fallar **se
  cuelga**: mide 22 s con un timeout de 22 s por lectura, y un frame cada 10 s
  hace que nunca expire. Vigilante puesto: sigue corriendo a los 150 s.
- **`test_idle_when_nothing_is_tracked` no puede pasar** con la lista llena:
  exige `count == 0` y hay 2 (`ARG1646`, `LVKMT`, del 02/10). O el test se
  adapta, o se salta cuando la lista no está vacía; **no borrarlo**.
- **`ws.py:446` manda `Unknown action: ...` en inglés** al navegador.
- **El aviso de arranque dice «flight features disabled»** cuando en modo
  anónimo las de vuelo sí funcionan.

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

---

## 0.30.7 - El botón que decía «guardado» y no guardaba

**Rama:** `auditoria/p011-guardar-en-expediente`
**Ítem:** P0-11 de la auditoría de Claude.
**Decisión del operador:** «Selector en la calculadora».

### El defecto

Texto exacto que había en `frontend/src/views/CalculadoraRFView.vue`, y no era
otra cosa:

```js
const storeResult = () => {
  alert('Resultado guardado (próximamente integrado con expediente)')
}
```

El diálogo afirmaba un guardado que no ocurría. **Medido**: las cuatro tablas
RF estaban vacías (`eventos_rf` 0, `mediciones` 0, `rf_events` 0,
`rf_sources` 0) y `client.js` llevaba `rf.createEvent` definido **sin un solo
llamador** en toda la interfaz.

### No era una decisión de diseño: eran dos arquitecturas paralelas

Al cablear a ciegas habría ido al lugar equivocado, así que primero se miró
qué había:

| | **A — `eventos_rf`** | **B — `rf_events`** |
|---|---|---|
| Campos | `formula`, `tipo_producto`, `error_khz`, `score_probabilidad`, `proximidad`, `expediente_id` | `frequency_mhz`, `classification`, `event_at`, `calculated_evento_id` |
| Escritura | **no tenía** | `POST /rf/events` → crea un `MapObject` |
| Lectura | `GET /expedientes/{id}/eventos`, **ya existía** | `GET /rf/events` |
| Coordenadas | ninguna | obligatorias (es un objeto de mapa) |

La calculadora produce exactamente lo de la **A** y no tiene coordenadas: un
resultado de armónico no es un punto del mapa. `rf.createEvent` (la **B**)
habría exigido inventarle una lat/lon. **El guardado va a la A.**

### Lo que ya existía y no se reconstruyó

- `EventoRF` en `app/models/evento_rf.py`, con todos los campos del cálculo.
- `EventoRFCreate` y `EventoRFResponse` en `app/models/schemas.py`.
- `GET /expedientes/{id}/eventos`, ordenado por probabilidad.
- El borrado en cascata al borrar el expediente (`expedientes.py`).

Lo único que faltaba era la escritura. Por eso el `GET` siempre devolvía `[]`:
no había nada que guardar nunca.

### Lo que se hizo

**Backend** — `POST /expedientes/{id}/eventos` en
`app/api/routes/expedientes.py`. La URL manda: el expediente a guardar es el
de la ruta; si el cuerpo dice otro, responde 400 en vez de adivinar. 404
«No existe el expediente {id}» si no existe, también en español. Responde
201 con `EventoRFResponse`.

**Contrato** — `expedientes.crearEvento(id, payload)` en
`frontend/src/api/client.js`, en el mismo commit que el endpoint, como exige
la regla.

**Interfaz** — `CalculadoraRFView.vue`:

- Desplegable **Expediente de destino** (la ruta `/calculadora` no recibe id y
  en la app no hay «expediente activo», así que hay que elegir).
- El botón queda inactivo hasta que haya resultado **y** destino.
- El aviso vive en la página (`role="status"`), en español, y distingue
  éxito de error. Si la carga de expedientes falla dice «No se pudieron
  cargar», no «no hay ninguno», que sería repetir el defecto.
- Al cambiar de resultado el aviso anterior se borra: no queda un «guardado»
  hablando de un resultado que ya no es el visible.

**Lectura** — `ExpedienteDetalleView.vue` muestra **«Guardados en este
expediente»**, que viene de la base, aparte de **«Resultados del último
cálculo»**, que es memoria de la sesión. Los dos títulos ahora dicen lo que
son.

**Sin truncar** — `stores/expedientes.js`: `fetchExpedientes` acepta
parámetros opcionales (sin ellos se comporta igual que antes, ningún llamador
viejo cambia). La calculadora pide `{ limit: 100 }`.

### Las guardas

Backend, `tests/test_p011_guardar_en_expediente.py`, **6 pruebas**:

1. Guardar y volver a leer por el `GET` que ya existía.
2. Que ningún campo se redondee ni trunque en el ida y vuelta.
3. Que cada guardado deje una fila y el `GET` salga ordenado.
4. Que los dos expedientes no se mezclen.
5. 404 en español para un expediente inexistente.
6. 400 si el cuerpo contradice la URL, **y que no se haya escrito nada**.

Frontend, `frontend/tests/p011-guardar.spec.js`, **5 pruebas**: botón
inactivo sin destino y sin llamada; guardado con el mapeo exacto de campos; un
error del backend se muestra como error; un fallo de carga no se disfraza de
«no hay expedientes»; y que el texto mentiroso ya no está en la vista.

**Por reversión** — backend: quitado el endpoint, **6 de 6 fallan** (405 Method
Not Allowed). Frontend: restaurada la vista original de git, **5 de 5
fallan**. Las 11 vuelven a verde con el arreglo, y las dos suites completas
pasan después.

### Verificación en vivo

Contra una base **temporal** en el puerto 8011, no contra `aerorf.db`: no hay
`DELETE` de `eventos_rf`, así que una fila de prueba en la base real no se
podría borrar sin borrar el expediente entero. Se borró la base al terminar y
no quedó ningún respaldo nuevo.

| Acción | Resultado |
|---|---|
| `POST /expedientes/` | 200 |
| `POST /expedientes/1/eventos` | **201**, con `id` y `timestamp` |
| `GET /expedientes/1/eventos` | 200, **1 fila** (antes siempre 0) |
| `POST /expedientes/999999/eventos` | **404** «No existe el expediente 999999» |
| `POST` con cuerpo que contradice la URL | **400** «El expediente del cuerpo (501) no coincide con el de la ruta (1)» |
| `GET` después del 400 | sigue en **1**: no escribió nada |

**Un falso negativo propio, anotado para no repetirlo.** El primer chequeo de
bytes lo hice en PowerShell y el `×` (U+00D7) salió como `C3 83 C2 97`, es
decir mojibake: parecía que el servidor corrompía la fórmula. Repetido el ida y
vuelta en Python, sin ninguna capa de codificación en el medio: **`32 20 C3 97
20 38 38 2E 35` idéntico en el POST y en el GET**. La culpa era mía: PowerShell
5.1 leyó mi comando como CP1252 y el `×` llegó duplicado. El endpoint estaba
bien; el instrumento no.

### Números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 471 | **477** (+6) |
| Frontend (vitest) | 448 / 30 archivos | **453 / 31 archivos** (+5) |
| Paridad geográfica | 675 | **675**, 0 fallos |
| Build | — | **`✓ built in 1m 30s`** |

### Hallazgos nuevos, sin tocar

Cada uno para su commit:

- **`GET /expedientes` corta en 10 y nadie pagina.** El parámetro es
  `limit: int = 10`, `ExpedientesView` no pagina nada y los cinco llamadores
  de `fetchExpedientes()` van sin parámetro, así que la pantalla de expedientes
  muestra a lo sumo 10 y no se nota. **Leído en el código, no reproducido:**
  con un solo expediente en la base no hay forma de verlo fallar. Por eso el
  desplegable pide 100 explícitamente.
- **`toolbar.spec.js` falló una vez al cargar** en una corrida completa
  (441 de 453, 12 pruebas sin correr). Pasó sola 12/12 y la corrida
  siguiente dio **453/453**. Es el mismo síntoma que el flake ya registrado en
  0.30.6; **no se pudo reproducir y no se pudo atribuir a este cambio**.
- **Mensajes en inglés en `expedientes.py`**: «Expediente not found» (en los
  `GET` de mediciones y eventos) y «Expediente … already exists» (en el
  `POST`). Los del endpoint nuevo sí están en español.
- **Los 422 de FastAPI siguen en inglés** («Field required»). No se mandan al
  operador: la vista los traduce a un mensaje propio, pero el texto crudo
  sigue ahí para quien mire el JSON.
- **`client.js` tenia `rf.createEvent` sin llamador** — y es de la arquitectura
  B. Cablearlo habría sido el error fácil: habría dado «guardado» en la tabla
  equivocada.

### Pendiente (lista viva)

Resueltos hasta ahora en la auditoría: **P0-06** (base anclada, respaldo
automático, versión de esquema), **P0-04** (el WebSocket en modo anónimo),
**P0-11** (el botón que decía «guardado»), en 0.30.8 el **`lost`** que se
reenviaba cada 10 s, y en **0.30.9 la precondición de `test_idle`**: la
prueba vacía la lista por la API y la restaura en un `finally`, y la
integración quedó en **7 pasan, 0 caen**.

**Encontrado al verificar P0-04 y P0-11, sin tocar** — cada uno con su repro y
en espera de commit propio:

- **Nadie lee `lost`.** El inundador se arregló en 0.30.8, pero el frontend no
  tiene manejador: el marcador de una aeronave que se fue sigue quedando en
  pantalla. O se agrega el manejo, o se quita el frame — **decisión del
  operador**, porque cambia cómo se ve el mapa.
- **`ws.py:446` manda `Unknown action: ...` en inglés** al navegador.
- **El aviso de arranque dice «flight features disabled»** cuando en modo
  anónimo las de vuelo sí funcionan.
- **`GET /expedientes` corta en 10 sin paginación** (arriba, en Hallazgos).
- **`toolbar.spec.js` flaky**, tres veces ya: un archivo que no cargó, luego
  `toolbar` y ahora 4 pruebas en 3 archivos en una corrida a 210 s — sola
  37/37 y la completa 453/453. **Sin repro, sin atribución posible.**

Decisiones que tomó el operador al revisar la auditoría:

- **P0-02 — borrar expedientes con objetos GIS vinculados: bloquear con 409.**
  Coherente con lo que ya pasa al revés, que borrar un objeto vinculado sí está
  bloqueado. Nada se pierde en silencio.
- **P0-11 — selector de expediente en la calculadora.** Se eligió esa forma
  entre las cuatro que se le presentaron (guardar desde el detalle, meter la
  calculadora en el expediente, o quitar el botón).
- **Se empieza por P0-06** y de ahí se sigue con el resto de la auditoría.
- **El modelo de despliegue sigue sin decidir** — una PC por técnico o servidor
  compartido —, así que el middleware de `Origin` va acotado a los orígenes de
  CORS configurados, que sirve para los dos casos sin comprometer nada.

---

## 0.30.8 - «lost» se mandaba cada 10 segundos y eso colgaba al test

**Estado:** completada · hallazgo propio, encontrado al verificar P0-04

### Qué estaba mal

En `app/api/routes/ws.py`, el bucle de tick hacía:

```python
for code in missing:
    for sub in list(self.clients):
        if sub.wants(code):
            await sub.send({"type": "lost", ...})
```

Sin deduplicar. Mientras una aeronave de la lista de seguimiento no
apareciera en la respuesta de OpenSky —lo normal cuando no está volando, o
está fuera de su cobertura—, el servidor le reenviaba **el mismo aviso cada
10 s, para siempre**. Es exactamente lo que la §48 prohíbe.

`send_status` ya deduplicaba desde hace tiempo (el «status repetido cada
10 s» que está en la tabla de la 0.30.0): el `lost` era **el mismo defecto
que quedó sin arreglar en el otro canal**.

### Dos hechos que salieron de mirar, y que agravan el diagnóstico

1. **El frontend no tiene ningún manejador de `lost`.** Una búsqueda amplia
   por `frontend/src` devuelve **una sola coincidencia**, y es prosa de un
   comentario de `map.js`. El frame se mandaba cada 10 s y **nadie lo leía**:
   el costo era puro ancho de banda más el cuelgue, y el beneficio, cero.
   El comentario del código dice que el aviso existe para que no quede un
   marcador viejo en pantalla — y como nadie lo lee, el marcador sigue
   quedando. **Eso va por su cuenta** (¿manejador en el cliente, o se quita
   el frame?), porque la respuesta cambia cómo se ve el mapa.
2. **Por eso el test no fallaba: se colgaba.**
   `test_feed_does_not_flood` lee hasta que hay 22 s de silencio, con un
   timeout de 22 s por lectura. Un frame cada 10 s hace que ese silencio
   nunca llegue. **Un test que se cuelga es peor que uno que falla**: no
   informa nada y traba la suite entera.

### El arreglo

Dos métodos nuevos en `FlightSubscription`, del mismo calibre que el
`send_status` que ya estaba:

- `note_missing(icao24)` devuelve `True` **la primera vez** y `False` a
  partir de ahí, hasta que la aeronave vuelva.
- `note_returned(icao24s)` hace la mitad simétrica: si la aeronave vuelve,
  borra el aviso —para que una caída posterior también se anuncie— **y borra
  la huella guardada en `last`**.

Esa segunda parte no es decorado: `last` guarda la posición del último
estado mandado. Sin borrarla, al volver con la misma posición `changed()`
daba `False` y no se mandaba nada — o sea, un cliente que hubiera hecho caso
al aviso y borrado el marcador **nunca lo recupera**. Deduplicar sin eso
deja un hueco.

### Las guardas

`tests/test_lost_sin_inundar.py`, cinco pruebas. Corren varios `_tick`
contra la misma conexión, reutilizando el doble de servicio que armó
P0-04, porque el inundador no se ve en un tick suelto: se ve en la
repetición. Sin servidor, sin reloj y sin gastar crédito.

**Escritas antes del arreglo y ejecutadas antes de tocar nada: 3 en rojo,
2 en verde.**

| Prueba | Antes del arreglo |
|---|---|
| un solo aviso por aeronave ausente en 3 ticks | **falla**: mandó 3 |
| dos ausentes en tres ticks | **falla**: mandó 6 |
| al volver se reenvía su estado aunque no cambie | **falla**: 1 `states` en 3 ticks |
| si se pierde dos veces se avisa dos | pasa (regresión) |
| el aviso está en español | pasa (regresión) |

### Verificación en vivo

El 8010 reiniciado con el arreglo, y la suite `integration` corrida entera:

| | antes | después |
|---|---|---|
| `test_feed_does_not_flood` | **se colgaba** (sin salida a los 150 s) | **PASA** |
| total | 5 passed, 2 failed | **6 passed, 1 failed** |

La corrida entera tardó **47 s**. La única que sigue fallando es
`test_idle_when_nothing_is_tracked`, que es la precondición de las 2
entradas del watchlist — otro ítem, que no toca este.

### Números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 477 | **482** (+5) |
| Integration | 5 passed / 2 failed | **6 passed / 1 failed** |

---

# 0.30.9 — La precondición de `test_idle_when_nothing_is_tracked`

**Fecha:** 2026-10-04 · **Rama:** `auditoria/test-idle-lista-vacia` ·
**Archivos:** 1 (una prueba)

## El problema

Era el último rojo de integración. La prueba exige `count == 0` en la lista de
seguimiento y en la base del operador hay 2 (`ARG1646`, `LVKMT`, del 02/10),
así que cae en `assert 2 == 0`. La precondición no se cumple tocando el
código: hay que dejar la lista vacía.

## Las tres opciones

- **Saltarla** cuando la lista no está vacía: la más barata y la peor. Sería
  la única de las 7 de integración que no corre donde importa. **Un guardia
  que nunca corre no es un guardia.**
- **Borrarla**: prohibido por las reglas de trabajo, además de irreversible.
- **Elegida: arreglar la precondición.** Fotografiar la lista, vaciarla por la
  API pública, asertar que quedó vacía, correr el aserto del `idle` y
  **restaurar en un `finally`**, con un aserto extra de que la restauración
  devolvió exactamente lo que había.

La guarda unitaria de P0-04
(`test_nada_se_pregunta_si_no_hay_aeronaves_en_seguimiento`, línea 148) ya
afirma `["idle"]` y que no se consulta nada. Esta mitad es la del transporte:
que el frame `idle` llegue **por el WebSocket de verdad**, no sólo en el
servicio.

## Lo que cuesta

**`added_at` no se puede restaurar.** `GET /flights/tracked` no lo devuelve y
`update_selection` sólo acepta `callsign, show_track, show_marker, selected,
color, last_seen, last_position`. O sea: **cada corrida mueve `added_at` a la
fecha de hoy**.

Sí se devuelve y se restaura campo por campo: `icao24`, `callsign`, `slot`,
`color`, `show_track`, `show_marker`, `selected`. `last_seen` y
`last_position` se dejan en `NULL`, como estaban (la columna es de fecha y
hora; meterle el string de la API sería mentirle al tipo).

`added_at` no se lee en ninguna parte: 0 coincidencias en `frontend/src` y en
el backend sólo se devuelve. Es el único dato que se pierde, y se pierde a la
vista:

| | antes | después de la corrida |
|---|---|---|
| filas | 2 | **2** |
| `icao24`, `callsign`, `slot`, `color` | — | **idénticos** |
| `show_track`, `show_marker`, `selected` | 1, 1, 0 | **1, 1, 0** |
| `added_at` | 02/10 18:52 | 04/10 05:18 ← el costo |

Verificado leyendo la base del operador después de la corrida, no de memoria.
Y el `added_at` original se repuso a mano al terminar
(`2026-10-02 18:52:11.055863` y `2026-10-02 18:52:44.498771`); la próxima
corrida lo vuelve a mover.

## Verificación

| | antes | después |
|---|---|---|
| `test_idle_when_nothing_is_tracked` | **falla** (`assert 2 == 0`) | **PASA** (6,3 s) |
| suite `integration` completa | 6 passed, 1 failed (47 s) | **7 passed, 0 failed (28 s)** |

No hay asertos que fallen antes de tocar nada: esto es una prueba, no un
cambio de producción. Lo que se verifica es que la precondición se arregla
sola **y que la lista vuelve como estaba**.

**Ruido registrado, sin atribuir.** En la misma ventana, una corrida de vitest
con el equipo cargado falló **4 pruebas en 3 archivos** en 210 s (lo normal son
55 s); repetido, los mismos 3 archivos dieron **37/37 en 10 s** y la corrida
completa después **453/453 en 99 s**. Tercera aparición del mismo síntoma,
distinto archivo, sin repro y sin ningún cambio de frontend de por medio.

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 482 | **482** (sin cambios: esto es una prueba) |
| Integration | 6 passed, 1 failed | **7 passed, 0 failed** |
| Frontend | 453 | **453** |

---

# 0.30.10 — F2-01: el candado se salteaba por los campos RF

**Fecha:** 2026-10-04 · **Rama:** `auditoria/f201-candado-rf` ·
**Archivos:** 4 · **Fase 2 de la auditoría, ítem 1 de 8**

## El problema, reproducido

Las cuatro rutas tipadas escribían el satélite y hacían `commit` **antes** de
llamar a `svc.update_object`, y el único punto que verificaba el candado era
`update_object` (`map_service.py`). Con la fuente bloqueada:

| repro | qué pasaba |
|---|---|
| `PUT /rf/sources/{id} {"frequency_mhz": 200}` | **200** y la frecuencia de 98.1 a 200 |
| `PUT … {"frequency_mhz": 201, "name": "otro"}` | **400** por candado, pero **201 ya quedó guardado** |

La auditoría marcaba antenas y eventos como «deducido por lectura» y dejaba
`update_reference` sin leer: las cuatro tienen el mismo esqueleto, y se
verificó una por una.

`tests/test_f201_candado_rf.py`, siete pruebas escritas y corridas **antes**
de tocar el código:

| | antes del arreglo | después |
|---|---|---|
| las 4 parametrizadas (fuente, antena, evento, referencia) | **fallan**: responden 200 | **pasan** |
| escritura parcial | **falla**: `la frecuencia pasó a 201.0` | **pasa** |
| control desbloqueado | pasa | pasa |
| desbloquear sigue permitido | pasa | pasa |

**5 en rojo, 2 en verde** → 7 en verde.

## El arreglo

- **`map_service.require_unlocked(obj, patch)`**: el chequeo, extraído de
  `update_object` y con una sola implementación para todos los caminos. Lo
  nuevo es que las cuatro rutas RF lo llaman **antes** de tocar el satélite.
- **Una sola transacción**: desaparecen los `db.commit()` intermedios del
  satélite. Si hay `patch`, el único `commit` es el de `update_object`, y el
  satélite pendiente viaja en esa misma transacción; si no lo hay, un
  `db.commit()` final. Si algo falla en el medio, **`db.rollback()`** — antes
  la ventana de escritura parcial estaba abierta entre los dos `commit`.
- **El mensaje pasó a español**: `El objeto {id} está bloqueado.
  Desbloquéalo antes de editar.` `client.js` prefiere el `detail` del
  backend, así que esa cadena es literalmente lo que ve el operador.

## Una guarda existente que hubo que actualizar

`test_map_objects.py::test_locked_object_refuses_edits` buscaba la palabra
**«locked»** en el mensaje — que al pasar a español dejó de existir. Se le
cambió la aserción a **«bloqueado»**: la prueba sigue prohibiendo la edición
y además de paso queda que el motivo esté en el idioma del operador. No se
borró ninguna prueba.

## Lo que NO se tocó, y por qué

- **El código sigue siendo 400**, no 409. Cambiarlo es decisión de contrato
  (coherencia con el 409 ya decidido en P0-02) y no está tomada; además
  `tests/smoke_e2e.py:353` fija 400. Si se cambia, `client.js` en el mismo
  commit.
- **`update_reference:483-484`** cambia `db_obj.radius` sin que eso aparezca
  en el historial: es F2-02, no éste.
- **El historial de los satélites** sigue roto (`getattr(obj, "rf.k")` da
  `None`): F2-02.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **489 pasan** (482 + 7 nuevas), 7 deseleccionadas |
| `pytest -m integration` (8010) | **7 pasan**, 0 caen |
| `npm test` (frontend) | **453 pasan**, 31 archivos |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** |
| `python tests/smoke_e2e.py` (base del operador, 8010) | 75 de 78 |

### Hallazgo al verificar: el E2E contra la base real deja rastro

La primera corrida fue contra la base del operador, como indica el propio
`ARCHITECTURE`, y **dejó basura**: 3 aviones falsos (`abc001`-`abc003`) en
la lista de seguimiento, 8 objetos de prueba en el mapa, una fuente enganchada
al expediente y un expediente `EXP-SMOKE-001`. Todo se repuso por la API
pública y se verificó contra la base: **los 2 aviones, los 2 objetos y el
expediente del operador, con el `added_at` original y `eventos_rf` en 0**.

De ahí salen tres fallas del E2E, ninguna por este cambio:

| falla | causa |
|---|---|
| `15 default layers` | el script espera **15** y hoy se siembran **17** (`lines` y `polygons`, del 26/09). **Falla también en base limpia** — expectativa vieja del script |
| `5 aircraft tracked` → `added=3` | los 2 aviones del operador llenaron la ventana de 5. En base limpia pasa |
| `geojson lon/lat order` | ambiental. En base limpia pasa |

**Corrección al método**: el E2E hay que correrlo contra una base temporal
(`DATABASE_URL` apuntando a un descartable), no contra `aerorf.db`.

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 482 | **489** (+7) |
| Integration | 7 | **7** |
| Frontend | 453 | **453** |

---

# 0.30.11 — F2-02: el historial escribía filas falsas

**Fecha:** 2026-10-04 · **Rama:** `auditoria/f202-historial-tipado` ·
**Archivos:** 3 · **Fase 2 de la auditoría, ítem 2 de 8**

## Qué pasaba

`_record_history(db, db_obj, {"rf.power_dbm": 40})` hace
`getattr(obj, "rf.power_dbm")` sobre el **MapObject** — y ese atributo no
existe, porque `obj` es el objeto y no el satélite. Devuelve `None`. Entonces,
para **cada** campo del satélite que tenga valor, el historial graba que pasó
a `None`.

El repro de la auditoría: cambiando sólo `power_dbm` de 40 a 41, se generaban
6 filas:

| fila del historial | lo que afirma |
|---|---|
| `rf.id '1' → None` | se borró la clave del satélite |
| `rf.object_id '1' → None` | se borró el enlace con el objeto |
| `rf.kind 'FM' → None` | se borró el tipo |
| `rf.frequency_mhz '98.1' → None` | **se borró la frecuencia** |
| `rf.provenance 'user' → None` | se borró la procedencia |
| `rf.power_dbm '40.0' → None` | se borró la potencia |

**Y el cambio de verdad, 40 → 41, no aparecía en ninguna parte.** El historial
era exactamente al revés de lo que había pasado: contradecía el guardado que
acababa de ocurrir y no registraba el que había ocurrido.

Las cuatro vistas tenían la misma copia del mismo error (`rf.`, `antenna.`,
`event.`, `reference.`), y la auditoría sólo había leído dos.

## La guarda

`tests/test_f202_historial_tipado.py`, ocho pruebas. Las primeras siete se
escribieron y corrieron **antes** de tocar el código: **7 en rojo**. Cada una
lee el historial **por la API** (`GET /map/objects/{id}/history`), no con la
sesión interna, para que el aserto sea sobre lo que queda guardado.

1. `test_un_campo_cambiado_produce_exactamente_una_fila` (4 parametrizadas):
   cambio un solo campo de una fuente, una antena, un evento y una referencia →
   **exactamente una** fila, con su campo, su valor viejo y su valor nuevo.
2. `test_no_afirma_que_se_borro_lo_que_sigue_ahi`: ninguna fila con
   `new_value: None`.
3. `test_el_cambio_real_aparece_con_los_dos_valores`: el repro 40 → 41.
4. `test_el_cambio_del_objeto_padre_tambien_aparece`: el caso que la
   auditoría no vio (abajo).

La octava llegó con el arreglo y se verificó **por revertida**: con la
comparación anterior (sólo texto) da
`[('rf.height_m', '25.0', '25')]` y falla; con la nueva, pasa.

## El arreglo

- **`map_service.record_typed_history(...)`** — un solo camino para las
  cuatro rutas. Compara el satélite **contra su propio snapshot** (no contra
  el objeto) y devuelve sólo los campos que cambiaron.
- **`_SATELLITE_SKIP = _HISTORY_SKIP | {"object_id"}`**: `id` y `object_id`
  son identidad, no valores editados — de ahí salían las filas «se borró la
  clave».
- **`_mismo_valor(old, new, old_s, new_s)`**: `25.0` y `25` son el mismo
  número. Sin esto, reenviar una medida como entero generaría **otra** fila
  falsa («pasó de 25.0 a 25»). Se aplica a **los dos** diffs, el del satélite
  y el del objeto.
- **El diff del objeto padre**, que era la parte que faltaba: `update_antenna`
  copia `azimuth_deg` a `db_obj.azimuth` y `update_reference` puede copiar
  `radius` **ahí mismo, sin pasar por ningún diff** — el objeto cambiaba y el
  historial no se enteraba. Las rutas ahora sacan una foto del objeto antes
  (`_snapshot`) y la pasan junto con la del satélite.

## Lo que NO se toca, y por qué

- **El formato sigue asimétrico**: el valor viejo es `40.0` (la creación sí
  pasa por Pydantic) y el nuevo es `41` (el `PUT` arma el satélite con el
  cuerpo **crudo**, `body.items()` filtrado por `.model_fields`, sin validar).
  Esa falta de validación es **F2-05**, no éste; por eso las pruebas comparan
  el valor como **número** y no como texto, y lo dicen en el comentario.
- **Las altas de satélite siguen sin dejar fila**: si el satélite no existía
  y hay que crearlo, no hay `before` que difuminar. Es registro de creación,
  no de cambio; el `__created__` del objeto ya cubre el alta.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **497 pasan** (489 + 8 nuevas), 7 deseleccionadas |
| `pytest -m integration` (8010 reiniciado) | **7 pasan**, 0 caen |
| `npm test` (frontend) | **453 pasan**, 31 archivos |
| `tests/geo_parity.mjs` | **675 pasan** |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** (igual que en 0.30.10: el chequeo viejo de capas) |

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 489 | **497** (+8) |
| Integration | 7 | **7** |
| Frontend | 453 | **453** |
---

# 0.30.12 — F2-03: el payload de `rf_events` no se serializaba

**Fecha:** 2026-10-04 · **Rama:** `auditoria/f203-evento-serializado` ·
**Archivos:** 8 · **Fase 2 de la auditoría, ítem 3 de 8** (la parte del bug)

## Qué pasaba

`object_to_feature` serializa cuatro payloads tipados — `rf`, `antenna`,
`reference`, `measurement` — y **nunca `event`**. `RFEvent` es además el
único satélite sin relación en el lado del objeto: `RFEvent.object`
(`rf.py:189`) es de una sola vía, así que no había por dónde llegar al
registro desde el `MapObject`.

Tres consumidores esperaban ese bloque y no lo recibían:

| quién | lo que esperaba | lo que salía |
|---|---|---|
| `export_service.to_csv` (líneas 224-226) | `props["event"].level_dbm` y `.classification` | columnas `event_level_dbm` y `classification` **vacías en toda exportación** |
| el Inspector (`InspectorPanel.vue:856`) | `p.frequency_mhz` en plano | nada: no había payload que leer |
| `duplicate_object` | `event=` en `create_object` (keyword que existe desde el origen, `map_service.py:260`) | el duplicado se perdía el payload completo |

El CSV es la prueba de que el bloque estaba previsto: el código que lo leía
ya estaba escrito, apuntando a una clave que ningún backend emitía.

## La guarda

`tests/test_f203_evento_serializado.py`, siete pruebas. Las cuatro primeras
se escribieron y corrieron **antes** de tocar el código: **4 en rojo**
(respuesta del mapa, GeoJSON, CSV y duplicado). Las otras tres ya daban
verde y quedan como guarda de lo que no debe romperse:

1. un evento **sin** payload no inventa un bloque;
2. una fuente sigue llevando `rf` y **no** lleva `event`;
3. borrar un evento sigue funcionando — ésta protege la relación nueva:
   con `cascade="all, delete-orphan"` ahora es el ORM el que cascadea
   (antes lo hacía sólo la base con `ondelete=CASCADE`).

En el frontend, una prueba nueva en `tests/components.spec.js` monta el
Inspector con `properties.event` anidado y exige que se muestren la
frecuencia, el nivel y la clasificación. **Verificada por revertida**: con
la lectura plana anterior da exactamente 1 fallo (`118.3 MHz` no aparece)
y con la lectura nueva, pasa.

## El arreglo

- **`MapObject.rf_event`** (`uselist=False`, `lazy="selectin"`,
  `cascade="all, delete-orphan"`) con `back_populates` en las dos
  direcciones: la única relación que faltaba entre objeto y satélite.
- **`object_to_feature` emite `props["event"]`** con las mismas 11 columnas
  que declara `RFEventPayload`, incluido `calculated_evento_id`.
- **`duplicate_object` pasa `event=_payload_dict(src.rf_event)`**, como ya
  hacía con los otros cuatro satélites.
- **`_loaders()`** agrega `selectinload(MapObject.rf_event)`, para que la
  lista de eventos no dispare una consulta por fila.
- **`InspectorPanel.vue`** pasa de `p.frequency_mhz` a
  `p.event.frequency_mhz`, igual que `p.rf.*` para las fuentes: es el único
  cambio de contrato, y va en el mismo commit.

## Lo que NO se toca, y por qué

- **`calculated_evento_id` sigue sin escribirse.** Decisión del operador:
  queda declarado hasta que exista un caso de uso real, porque nada en el
  flujo vincula un evento del mapa con un resultado de la calculadora y
  escribirlo sería inventar el vínculo.
- **No se unifican las dos arquitecturas de eventos** (recomendación del
  anexo de F2-03 en `RETOMAR.md`): dueños distintos, semánticas distintas,
  y ya están enlazadas por esa clave.
- **La fila `rf_events` no se toca**: sólo se serializa lo que ya estaba
  guardado. No hay migración de esquema.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **504 pasan** (497 + 7 nuevas), 7 deseleccionadas |
| `pytest -m integration` (8010 reiniciado) | **7 pasan**, 0 caen |
| `npm test` (frontend) | **454 pasan**, 31 archivos |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (35,9 s) |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** (la capa obsoleta, ya encolada) |

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 497 | **504** (+7) |
| Integration | 7 | **7** |
| Frontend | 453 | **454** (+1) |
| geo_parity | 675 | **675** |
| smoke_e2e (base temporal) | 77/78 | **77/78** |
---

# 0.30.13 — F2-04: el borrado masivo no miraba nada

**Fecha:** 2026-10-04 · **Rama:** `auditoria/f204-borrado-filtrado` ·
**Archivos:** 6 · **Fase 2 de la auditoría, ítem 4 de 8**

## Qué pasaba

`clear_layer` hacía `DELETE FROM map_objects WHERE layer_id = ?` y
devolvía el conteo. Ni `locked`, ni `expediente_id`, ni `parent_id`. Y como
las tres tablas de al lado (`ObjectNote`, `ObjectHistory`, `Annotation`)
tienen `ondelete="CASCADE"`, cada objeto borrado se llevaba consigo sus
notas, su historial y sus anotaciones: destrucción sin vuelta atrás en una
operación que se pide desde «borrar capa».

`delete_object`, el borrado de a uno, bloqueaba expediente e hijo pero
**no el candado**: un objeto cerrado se podía borrar sin más, aunque
editarlo estuviera vetado.

La decisión del operador, **antes** de tocar el código: **borrado físico
con los filtros**, no baja lógica con `deleted_at`. Lo libre se borra; lo
protegido no se toca.

## La guarda

`tests/test_f204_borrado_filtrado.py`, seis pruebas. Las cuatro primeras
corrieron antes del arreglo: **4 en rojo, 2 verdes**.

1. `test_clear_borra_lo_libre_y_conserva_lo_protegido` — capa con un
   libre, uno cerrado y uno vinculado: antes 200 y no quedaba nada; ahora
   409, el libre se fue, los dos protegidos siguen y la capa también.
2. `test_clear_con_todo_libre_borra_objetos_y_capa` (verde de guarda) —
   el caso simple no se rompe.
3. `test_clear_no_divide_un_grupo` — un hijo no se va solo.
4. `test_borrado_individual_respeta_el_candado` — cerrado: antes 200;
   ahora 400 con mensaje en español, y `?cascade=true` sigue siendo la
   fuerza explícita de a uno.
5. `test_borrado_individual_sigue_bloqueando_por_expediente` — roja sólo
   por el mensaje en inglés; el bloqueo ya existía.
6. `test_clear_sin_cascada_no_borra_nada` (verde de guarda) — el
   precontrato de `clear_layer` no cambia.

## El arreglo

- **`clear_layer`** selecciona los candidatos con sus tres banderas, suma
  los que son padre de otro objeto (para no partir un grupo) y borra sólo
  los libres con una sentencia por id. Devuelve cuántos borró y registra
  `removed` y `kept` en el log.
- **`delete_object`**: el candado entra en la lista de impedimentos, y el
  mensaje entero pasó a español («No se puede borrar el objeto 5: está
  bloqueado…»), igual que el de `clear_layer`.
- **`DELETE /map/layers/{id}`** limpia primero; si queda algo, **no borra
  la capa** y contesta **409** con el detalle. No es capricho:
  `Layer.objects` no tiene cascade, así que SQLAlchemy pondría
  `layer_id = NULL` en los supervivientes y los dejaría huérfanos —
  proteger dentro de `clear_layer` no serviría de nada si la capa se
  borrara igual. Los 404 y el 400 de capa de sistema de esa misma ruta
  también pasaron a español.
- **409 y no all-or-nothing**: era la opción elegida («lo libre se borra,
  lo protegido no se toca»); la opción «no se borra nada si hay
  protegidos» estaba en el menú y no se eligió.

## Lo que NO se toca, y por qué

- **El borrado individual sigue respondiendo 400** cuando se niega, como
  antes (el smoke lo tiene asentado en la línea 285). Unificar edición y
  borrado en 409 es un cambio de contrato ya comentado y sigue pendiente
  de tu palabra: hacerlo acá dejaría la edición en 400 y el borrado en 409.
- **`client.js` no necesita cambios**: el interceptor ya prefiere el
  `detail` del backend para cualquier status, así que el 409 en español
  llega a la pantalla tal cual. Todavía no hay ninguna vista que llame a
  `layers.remove`.
- **La baja lógica (`deleted_at`)** queda descartada por decisión
  explícita, no por omisión.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **510 pasan** (504 + 6 nuevas), 7 deseleccionadas |
| `pytest -m integration` (8010 reiniciado) | **7 pasan**, 0 caen |
| `npm test` (frontend) | **454 pasan**, 31 archivos |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (33,9 s) |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** (la capa obsoleta, ya encolada) |

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 504 | **510** (+6) |
| Integration | 7 | **7** |
| Frontend | 454 | **454** |
| geo_parity | 675 | **675** |
| smoke_e2e (base temporal) | 77/78 | **77/78** |
# 0.30.14 — el test del flood se colgaba: medía silencio, no tiempo

**Fecha:** 2026-10-04 · **Rama:** `tests/flood-ventana-acotada` ·
**Archivos:** 1 (sólo el test) · **reparación de un test, no del producto**

## Qué pasaba

`test_feed_does_not_flood` (spec §48) mide los frames que llegan en una
ventana de `poll * 2 + 2 = 22 s`, pero aplicaba esa ventana como **22 s de
silencio**: sólo cortaba cuando `ws.recv()` se quedaba sin nada que dar.
Con OpenSky configurado y aeronaves en la lista — estado normal de esta
máquina — el servidor emite `states` cada `LIVE_POLL_INTERVAL_S = 10 s`,
y la medición nunca terminaba: el test corría para siempre.

Demostrado, no supuesto: un registro de 40 s contra el WS del 8010 anotó
`hello`, `lost` y tres `states` a 0,9 s / 11,7 s / 22,5 s — frames cada
10,8 s, todos dentro de la ventana. Tres corridas de integración se
agotaron sin terminar (300 s, 420 s, 150 s) mientras las cinco pruebas
anteriores ya habían pasado: el colgado no falla, sólo deja el resto del
módulo sin ejecutar (`test_idle_when_nothing_is_tracked` quedaba a la
espera).

## El arreglo

La ventana pasó a ser de **tiempo total**: un `limite` con
`loop.time() + window_s`, y `wait_for(..., timeout=restante)` en cada
lectura. Si llegan frames, se acumulan hasta agotar la ventana; si no
llegan, se corta igual. Ninguna aserción cambió: siguen mandando
`len(messages) <= 6` y `len(statuses) <= 1`, que es lo que la spec §48
exige — sólo cambió cuándo deja de mirar.

Un test que se cuelga es peor que uno roto: el colgado no dice nada.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m integration` (8010 arriba) | **7 pasan en 35 s** (antes: colgado > 420 s) |
| `pytest -m "not integration"` | **510 pasan** (el test vive en la suite de integración) |
# 0.30.15 — F2-05: ninguna entrada inválida llega a 500

**Fecha:** 2026-10-04 · **Rama:** `auditoria/f205-entradas-invalidas` ·
**Fase 2 de la auditoría, ítem 5 de 8**

## Qué pasaba

Tres ejemplos de la auditoría (`null` en `visible`, `layer_id`
inexistente, `kind` inválido) y cinco vías más al mismo hueco:

| entrada | dónde estallaba | por qué |
|---|---|---|
| `layer_id` / `expediente_id` que no existe | al hacer commit | FK: `_resolve_layer_id` devolvía el id sin mirar si la capa existía |
| `visible: null` (u otra columna NOT NULL) en un update | al escribir | el patch escribía `None` en una columna que no admite `null` |
| `kind: "Basura"` en `POST /rf/sources` | dentro del handler | `_coerce` construye el modelo adentro de la vista: su `ValidationError` no lo atrapa nadie |
| `opacity: "media"` en `POST /map/layers` | dentro del handler | `float(payload[...])` sobre el cuerpo crudo |
| `object_id: "no-numero"` en `correlation/rf-aircraft` | dentro del handler | `int(...)` sobre el cuerpo crudo |

Y el ojo que anota la auditoría: si esto se arreglaba pasando a Pydantic,
los 500 se convertían en **422 en inglés** («Input should be a valid
boolean…»), que `describeError` pinta tal cual en pantalla. Por eso el
traductor va **en el mismo commit**.

## El arreglo: tres capas

1. **Antes de escribir** (`map_service`): `_existe_referencia` chequea
   capa y expediente tanto en el alta como en el update; y el patch
   completo se chequea contra la nulidad **real** de las columnas
   (`MapObject.__table__.columns[...]`) antes de tocar la fila. Así un
   `null` en NOT NULL dice «El campo visible no admite null: es
   obligatorio.» en vez de romper el commit — y el chequeo corre antes
   de cualquier `setattr`, así que no hay escritura parcial.
2. **Traductor global** (`app/api/errors.py`, nuevo; registrado desde
   `app.main`): `RequestValidationError` → **422** con `msg` en español
   (pisa el handler de FastAPI); `pydantic.ValidationError` → **422**
   igual, que es lo que cubre la validación dentro del handler;
   `IntegrityError` → **400** genérico en español con la causa real en
   el log. El 400 es un piso de seguridad para cualquier FK o NOT NULL
   que no tenga chequeo propio — los casos del operador sí lo tienen,
   con mensaje que nombra lo que falta («No existe la capa 999999.»).
3. **Los 14 validadores de `schemas_gis.py` hablan español** (`kind
   debe ser uno de: …`). No es cosmético: para `value_error` el
   traductor muestra el mensaje del validador tal cual, así que un
   validador en inglés produce un 422 en inglés.

Los dos guards de cuerpo crudo (`create_layer`, `rf_aircraft`)
convierten con `try/except` → 400 que nombra el campo.

## La guarda

`tests/test_f205_entradas_invalidas.py`, **11 pruebas escritas antes del
arreglo**. Rojo-antes registrado: contra el código original, **7 de 8**
fallaban en la primera corrida (los tres de la auditoría incluidos; la
única verde era la guarda de que lo válido sigue funcionando). Con los
handlers ya puestos y sin los chequeos del servicio quedaban **7 rojas**
— cada familia midió su propio rojo. El corte de `rf-aircraft` se
verificó aparte, **por revertida**: sin el `try/except`,
`ValueError: invalid literal for int()` vuelve a salir del TestClient.
Al final: **11 verdes**.

La guarda del contrato: un 422 sigue siendo 422 (el traductor no cambia
status, sólo el idioma), y lo válido sigue creando con 201.

## Lo que NO cambia

- **`client.js`: ningún diff.** El interceptor ya prefiere `detail` y
  `describeError` ya une `loc: msg`; el traductor devuelve exactamente
  ese formato (`{type, loc, msg}`), así que la pantalla recibe español
  sin que el frontend se entere.
- **`type` conserva el código de Pydantic** (`bool_parsing`, `missing`…):
  es un identificador para máquinas, no prosa, y no se muestra. Lo que
  se muestra es `msg`, y ése siempre sale en español.
- **No se migró ninguna ruta a `body: dict` ni al revés.** El traductor
  cubre las dos formas de validación; cambiar el estilo de las rutas
  sería otra cosa.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **521 pasan** (510 + 11 nuevas) |
| `pytest -m integration` (8010 reiniciado) | **7 pasan en 35 s** |
| `npm test` (frontend) | **454 pasan**, 31 archivos |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (39,7 s) |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** (la capa obsoleta, ya encolada) |

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 510 | **521** (+11) |
| Integration | 7 | **7** |
| Frontend | 454 | **454** |
| geo_parity | 675 | **675** |
| smoke_e2e (base temporal) | 77/78 | **77/78** |
# 0.30.16 — F2-06: el update escribía geometría sin validarla

**Fecha:** 2026-10-04 · **Rama:** `auditoria/f206-geometria-update` ·
**Fase 2 de la auditoría, ítem 6 de 8**

## Qué pasaba

`create_object` valida la geometría con `gjs.validate_geometry` antes de
escribir — el propio comentario avisa del riesgo: «one bad ring used to
be stored happily and then took down the whole listing endpoint with a
500» — y el docstring de esa misma función promete estar en «the create
and **update** paths». El update no la llamaba: `PUT /map/objects/{id}`
con `geometry` en el body pasaba por `MUTABLE_FIELDS` y escribía el
valor tal cual.

La consecuencia no era un 500 inmediato, porque la lectura ya está
blindada (`object_to_leaflet` devuelve «Objeto sin geometría derivable»
en vez de romper el listado). Era peor para el operador: el PUT
contestaba **200**, el objeto se guardaba «bien», y después
desaparecía del mapa sin ningún aviso de por qué. Un anillo roto
guardado hoy sigue roto mañana, y nadie lo señala.

## La guarda

`tests/test_f206_geometria_update.py`, 3 pruebas escritas antes del
arreglo: **1 roja** (el PUT devolvía 200 y el log confirmaba
`fields=geometry`) y 2 verdes que quedan como guarda — la geometría
válida sigue pasando, y la puerta del alta sigue cerrada. La roja se
volvió a medir **por revertida**, con el chequeo anulado: vuelve el 200.

Detalle de la aserción clave: mira la **columna**
(`db.get(MapObject, oid).geometry is None`), no la respuesta del GET —
ésta devuelve un Point derivado de `latitude`/`longitude` que taparía la
diferencia entre «no se escribió» y «se escribió otro».

## El arreglo

Un chequeo en `update_object`, **antes** de tocar la fila y junto a los
demás pre-cheques del patch que agregó F2-05: `gjs.validate_geometry`
y, ante `GeometryError`, `MapServiceError` → 400 con el mensaje en
español que la función ya trae («Un polígono necesita al menos 4
posiciones…», «El anillo del polígono no está cerrado…»).

Mismo criterio que el alta, en el mismo lugar donde ya se chequeaban
referencias y nulidad: o entra todo el patch, o no entra nada — sin
escritura parcial.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **524 pasan** (521 + 3 nuevas) |
| `pytest -m integration` (8010 reiniciado) | **7 pasan en 37 s** |
| `npm test` (frontend) | **454 pasan**, 31 archivos |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (37,5 s) |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** (la capa obsoleta, ya encolada) |

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 521 | **524** (+3) |
| Integration | 7 | **7** |
| Frontend | 454 | **454** |
| geo_parity | 675 | **675** |
| smoke_e2e (base temporal) | 77/78 | **77/78** |
# 0.30.17 — F2-07: un 429 tiene que pausar el feed, venga de donde venga

**Fecha:** 2026-10-04 · **Rama:** `auditoria/f207-backoff-compartido` ·
**Fase 2 de la auditoría, ítem 7 de 8**

## Qué pedía y qué había

La auditoría pide «un `BackoffController` para los tres pools: un 429 de
`/tracks` pausa también el feed en vivo». La estructura existía desde el
commit inicial — `OpenSkyService` crea **un** controlador y se lo pasa a
los tres `CreditAwareClient` —, pero eso no era una garantía medida: era
un comentario en el código. La guarda nueva lo mide en las dos
direcciones con la red mockeada y **pasa**: el gate ya cruzaba pools.

Lo que NO pasaba es el 429 que no pertenece a ningún pool: la
**renovación del token**. `OpenSkyTokenManager` contestaba 429 y
`_headers` lo disfrazaba de `OpenSkyNotConfigured`:

- el feed seguía renovando cada 10 s contra un endpoint que estaba
  limitando la cuenta — cada intento otro 429, y el gate quedaba abierto;
- el operador veía `not_configured` con un mensaje en inglés: apagado el
  frente e informado de algo falso. No son credenciales faltantes, es un
  tope, y un tope se levanta solo.

## El arreglo

- **`OpenSkyRateLimited(OpenSkyAuthError)`** con `retry_after_s`: el 429
  del token deja de confundirse con «no configurado».
- **`_headers` lo atrapa y hace lo mismo que un 429 de datos**:
  `backoff.trip(retry_after)` sobre el gate compartido →
  `RateLimitedError` **en español**. El poller ya sabía manejarla
  (`send_throttled` → la franja en español con los segundos), las rutas
  ya la traducen a 429 y `client.js` ya la pinta en español. El replay
  de 401 vuelve a pasar por `_headers`, así que también queda cubierto.
- **`retry_after_seconds(headers)` en `cache.py`**: los dos nombres de
  header viven una sola vez, compartidos por el camino de datos y el de
  token.

## La guarda

`tests/test_f207_backoff_compartido.py`, 3 pruebas escritas antes de
tocar nada: **2 verdes** — el cruce de pools que la auditoría nombra, en
las dos direcciones (ninguna consulta sale a la red después del tope) —
y **1 roja**: el 429-del-token esperaba `RateLimitedError` y recibía
`OpenSkyNotConfigured`. La roja se volvió a medir **por revertida**:
restaurada la conversión vieja, vuelve a fallar.

## Lo que NO cambia

- Las credenciales de verdad siguen sin estar: 401/403 siguen siendo
  `OpenSkyNotConfigured`, y su texto en inglés queda en la cola de
  traducción — igual que `TokenState.last_error = "rate limited"`,
  que es diagnóstico interno.
- Sin tocar el mensaje del 429 de datos ni el contrato de status: 429
  sigue siendo 429, ahora también cuando el tope viene del token.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **527 pasan** (524 + 3 nuevas) |
| `pytest -m integration` (8010 reiniciado) | **7 pasan en 38 s** |
| `npm test` (frontend) | **454 pasan**, 31 archivos |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (38,3 s) |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** (la capa obsoleta, ya encolada) |

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 524 | **527** (+3) |
| Integration | 7 | **7** |
| Frontend | 454 | **454** |
| geo_parity | 675 | **675** |
| smoke_e2e (base temporal) | 77/78 | **77/78** |
# 0.30.18 — F2-08: el import ya no dice que lo tecleaste tú

**Fecha:** 2026-10-04 · **Rama:** `auditoria/f208-source-importado` ·
**Fase 2 de la auditoría, ítem 8 de 8 — cierra la F2**

## Qué decía la auditoría

«`import_geojson` no pasa `source` y queda `"user"`. No necesita
migración (no hay `CheckConstraint` en ningún modelo), pero sí hay que
agregar la etiqueta en `MapEngine.js:1028` o muestra el valor crudo en
inglés.»

Un archivo importado aparecía en el Inspector como «Introducido por el
usuario» y salía así en las exportaciones: **la procedencia mentía sobre
el origen del dato**, que es justo lo que la trazabilidad existe para
impedir.

## El arreglo — las tres bocas a la vez

Arreglar solo una dejaba el dato cayéndose por otra, así que las tres:

1. **`PROVENANCE_IMPORTED = "imported"`** en `constants.py`, sumado a
   `PROVENANCE_VALUES` — el validador de `MapObjectCreate` rechaza todo
   lo que no esté en la tupla: el alta a mano con `source: "imported"`
   devolvía **422** («source debe ser uno de: observed, historical,
   live, calculated, user») — y a `PROVENANCE_LABELS_ES` con «Dato
   importado», que es lo que sirve `/map/vocabulary` y lee la leyenda de
   `LayerPanel`.
2. **`import_geojson` pasa `source=PROVENANCE_IMPORTED`** a
   `create_object`. Sin migración: la columna ya existe con su default.
3. **`MapEngine.js`: `imported: 'Importado'`** en `PROVENANCE_LABELS` —
   `provenanceLabel` tiene tabla propia y no lee el vocabulario del
   backend, así que sin esta línea el Inspector habría pintado el crudo
   «imported», en inglés.

## La guarda

`tests/test_f208_source_importado.py` (3) +
`frontend/tests/provenance-label.spec.js` (3), escritas **antes** de
tocar el código: **4 rojas** — source «user», vocabulario sin
«imported», create en 422, etiqueta cruda en inglés — y 2 verdes de
arranque que quedan como salvaguarda de los cinco valores originales y
del guion largo. La roja del import se volvió a medir **por
revertida**: quitada la línea del `source`, vuelve a decir «user».

## Lo que NO cambia

- **Las filas ya importadas en bases existentes siguen con `"user"`:**
  no hay migración y el ítem lo dice expresamente. Reetiquetar historia
  retroactiva sería inventar datos; si algún día hace falta, es una
  decisión del operador sobre sus propios datos.
- La tupla solo crece: ningún valor viejo deja de ser válido, ningún
  contrato cambia (misma ruta, mismos campos, misma respuesta).

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **530 pasan** (527 + 3 nuevas) |
| `pytest -m integration` (8010 reiniciado) | **7 pasan en 28 s** |
| `npm test` (frontend) | **457 pasan**, 32 archivos |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (33,3 s) |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** (la capa obsoleta, ya encolada) |

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 527 | **530** (+3) |
| Integration | 7 | **7** |
| Frontend | 454 (31 archivos) | **457** (32) |
| geo_parity | 675 | **675** |
| smoke_e2e (base temporal) | 77/78 | **77/78** |
# 0.30.19 — P0-02: borrar un expediente ya no se lleva a los objetos GIS

**Fecha:** 2026-10-04 · **Rama:** `auditoria/p002-delete-409` ·
**Auditoría de Claude, ítem P0-02 — decisión del operador: «bloquear con 409»**

## Qué estaba mal

`DELETE /expedientes/{id}` borraba el expediente y **se llevaba el
vínculo en silencio**. La cadena era:

- `MapObject.expediente_id` está declarado `ON DELETE SET NULL`;
- la base corre con `PRAGMA foreign_keys=ON` (lo que hizo P0-06);
- o sea: el DELETE contestaba **200**, el expediente desaparecía y los
  objetos de mapa que eran parte del caso quedaban **huérfanos de
  caso** — dibujos sueltos que nadie desvinculó ni vio.

Y lo más grueso: **el sentido inverso ya estaba bloqueado** — no se
puede borrar un objeto que pertenece a un expediente (lo niega
`delete_object` desde hace rato). Se podía destruir el caso entero
dejando sus piezas por el piso, pero no se podía tocar una pieza.
El operador lo dijo clarito: «igual que ya pasa al revés».

## El arreglo

Un pre-check en la ruta, **antes** de tocar fila alguna:

```python
if vinculados:
    raise HTTPException(409, "No se puede borrar el expediente {id}: "
        "N objetos de mapa siguen vinculados (ids ...). "
        "Desvinculalos antes de borrarlo.")
```

- **409** (no 400): es un conflicto con el estado actual de los datos,
  no un malformado — y el backend ya usa 409 en `delete_layer`, así
  que el contrato solo crece donde ya había lenguaje.
- El detalle trae **los ids** (hasta 10, y si hay más, la coma final
  con «...») para que el operador sepa exactamente qué desvincular.
- **En español**, como todo lo que ve el operador.

Y como la regla de contrato exige el cliente en el mismo commit:
`describeError` aprendió el 409 (fallback en español para un 409 sin
`detail`; con `detail`, que es el caso normal, sigue mandando el texto
del backend, que es lo que prefiere desde siempre).

## También en español, en la misma ruta

La regra de «lo que toco habla español» se aplicó a las dos líneas de
texto que quedaban en inglés **dentro de la función tocada**: el 404
(`Expediente not found` → `No existe el expediente {id}.`) y el mensaje
de éxito (`Expediente {id} deleted` → `Expediente {id} eliminado`).
Los demás 404 de este archivo siguen en la cola de traducción.

## El camino de recuperación, verificado

1. `DELETE` con vínculos → **409**, y **no se borró nada** (el
   expediente responde 200 y el objeto conserva su `expediente_id`);
2. `PUT /map/objects/{id}` con `expediente_id: null` → el parcial usa
   `exclude_none=False`, así que el `null` llega y desvincula;
3. `DELETE` de nuevo → **200**.

## La guarda

`tests/test_p002_delete_409.py` (4) +
`frontend/tests/describe-error.spec.js` (3), escritas antes de tocar:
**4 rojas de backend** (200 en vez de 409, mensaje en inglés, 404 en
inglés) y **1 roja de frontend** («Error 409» crudo). La del bloqueo se
repitió **por revertida**: sin el pre-check vuelve `200 == 409`.

## Lo que NO cambia

- **`Medicion` y `EventoRF` siguen borrándose con el expediente** —
  son registros del propio documento, ésa es la semántica de siempre.
- El sentido inverso (borrar objeto con expediente) sigue bloqueado
  **con su 400 de siempre**: la coherencia 400 ↔ 409 es el ítem de
  contrato aparte, ya encolado.
- Sin migración: no se toca esquema ni filas existentes.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **534 pasan** (530 + 4 nuevas) |
| `pytest -m integration` (8010 reiniciado) | **7 pasan en 29 s** |
| `npm test` (frontend) | **460 pasan**, 33 archivos |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (34,7 s) |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** (la capa obsoleta, ya encolada) |

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 530 | **534** (+4) |
| Integration | 7 | **7** |
| Frontend | 457 (32 archivos) | **460** (33) |
| geo_parity | 675 | **675** |
| smoke_e2e (base temporal) | 77/78 | **77/78** |
# 0.30.20 — P0-07: el middleware de Origin/Host, acotado a la lista configurada

**Fecha:** 2026-10-04 · **Rama:** `auditoria/p007-origin-host` ·
**Auditoría de Claude, ítem P0-07 — decisión del operador: acotarlo a
los orígenes de CORS configurados**

## Qué pedía y por qué así

La auditoría pide un middleware de `Origin`/`Host`. El modelo de
despliegue sigue sin decidir (una PC por técnico vs. servidor
compartido), así que la decisión fue **acotarlo a `CORS_ORIGINS`** —
el mismo `.env` — que sirve en los dos modelos: cada técnico pone sus
orígenes, el servidor compartido los suyos.

Y la advertencia, que era la parte fina: «con el proxy de Vite el
`Origin` es `5199` y el `Host` es `8010`: sin esa lista rechaza la
interfaz entera **y los tests salen verdes**» — los tests no mandan
`Origin`, así que un guard con lista inventada rompería la interfaz
sin que ninguna prueba se enterara. Medido: los 540 tests siguen
verdes **porque** el guard usa la lista configurada.

## Qué cierra cada mitad

| | `Origin` | `Host` |
|---|---|---|
| qué ataca | CSRF de sitio: formularios y XHR que **hacen** — CORS sólo niega **leer** | DNS rebinding: `evil.com` → 127.0.0.1, same-origin para el browser, y **lee** |
| por qué no basta el otro | — | el rebinding **no manda** `Origin` |
| rechazo | 403 «Origen no permitido: …» | 403 «Host no permitido: …» |

- **Una sola lista para los dos**: el guard lee
  `settings.cors_origin_list` — cualquier origen que
  `CORSMiddleware` sirve, el guard lo deja llegar; los dos leen el
  mismo `.env` y nunca se contradicen.
- **`ALLOWED_HOSTS`** (nuevo, en `.env.example`): loopback +
  `testserver` (el `Host` que manda TestClient), **más** los hostnames
  de los orígenes configurados: la lista de hosts aprende de la de
  orígenes.
- **ASGI puro**, no `BaseHTTPMiddleware`: cubre también el scope
  `websocket` — el upgrade trae `Origin` y `Host`, y si no se miran, el
  rebinding entra por ahí con la misma facilidad.
- 403 con `{"detail"}` en español: el formato que `describeError` ya
  entiende.

## La guarda

`tests/test_p007_origin_host.py`, 6 escritas **antes** de tocar: **3
rojas** — el origin evil pasaba (200), el host evil pasaba (200), y el
websocket ni siquiera tenía módulo — y 3 verdes de arranque (origin
configurado, host local, control sin cabeceras). La roja del cableado
se volvió a medir **por revertida**: sin `install_origin_guard(app)`
vuelven las dos de API.

**En vivo contra el 8010 real**: evil `Origin` → **403** ·
`Origin: http://localhost:5199` (el de `.env`) → **200** · evil
`Host` → **403** · sin cabeceras → **200**.

## Lo que NO cambia

- **Sin `Origin` la petición pasa** (curl, tests, integración): el
  guard es defensa de browser, no autenticación — la API no tiene auth
  todavía, que es otro ítem.
- El default de `ALLOWED_HOSTS` acepta `testserver`: inofensivo (un
  browser no puede mandarlo a propósito; el rebinding manda su propio
  dominio, que queda rechazado).
- Orden de middleware: guard → CORS → rutas; CORS sigue agregando sus
  cabeceras a las peticiones que el guard deja pasar.
- El default de `CORS_ORIGINS` en `config.py` (5173) no se tocó: lo
  mandan `.env`/`.env.example` (5199), como antes de este ítem.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **540 pasan** (534 + 6 nuevas) |
| `pytest -m integration` (8010 reiniciado) | **7 pasan en 36 s** |
| `npm test` (frontend) | **460 pasan**, 33 archivos |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (54,6 s) |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** (la capa obsoleta, ya encolada) |
| En vivo contra 8010 | evil origin 403 · origin configurado 200 · evil host 403 · sin cabeceras 200 |

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 534 | **540** (+6) |
| Integration | 7 | **7** |
| Frontend | 460 (33 archivos) | **460** (33) |
| geo_parity | 675 | **675** |
| smoke_e2e (base temporal) | 77/78 | **77/78** |
# 0.30.21 — P0-09: la inyección de fórmulas en el CSV, sin tocar los números

**Fecha:** 2026-10-04 · **Rama:** `auditoria/p009-csv-injection` ·
**Auditoría de Claude, ítem P0-09 — «sólo en campos de texto libre»**

## Qué estaba mal

`GET /export/csv` escribía cada celda **tal cual**. Un nombre tecleado
`=HYPERLINK("http://evil.example","clic")` viajaba entero y la hoja de
cálculo lo abría como **fórmula**: el operador hace clic en la celda y
cae en el sitio del atacante. Peor, la familia DDE
(``=cmd|'/c calc'!A0``) llega a ejecutar comandos en la máquina donde
se abre el archivo. Los disparadores: `=`, `+`, `-`, `@`, y las dos
invisibles — tabulador y retorno de carro.

## La trampa que avisa el propio ítem

«Prefijar lo que empieza con `-` convertiría las latitudes negativas en
texto.» La solución tacaña — blindar toda celda que arranque con uno de
esos caracteres — arruina `-34.6` en una columna de latitud. El ítem
pide blindar **sólo texto libre**.

## El arreglo: por valor, no por columna

```python
def _blindar(valor):
    if not isinstance(valor, str) or not valor:   # números intactos
        return valor
    if valor[0] not in ("=", "+", "-", "@", "\t", "\r"):
        return valor
    try:
        float(valor)          # "-34.6", "-62.5", "+7.5": es un número
        return valor          # …prefijarlo sería el error del ítem
    except ValueError:
        return "'" + valor    # la fórmula, prefijada
```

- **Sólo `str`**: las columnas numéricas (latitud, longitud, nivel dBm)
  traen números y no se tocan.
- **Un string legible como número tampoco se toca**: es exactamente la
  advertencia del ítem, y cubre además el caso real de un dBm que llega
  como string desde el JSON de propiedades.
- **Por qué no una lista blanca de columnas**: se pudre con la próxima
  columna nueva (la que nadie agregue al whitelist es el hueco de
  mañana); el carácter peligroso no se pudre. En la práctica el
  resultado es el que pide el ítem: los system values (`point`,
  `user`, `#ff0000`, ISOs) no arrancan con ninguno de esos caracteres
  — la blindada es no-op — y lo tecleado o venido de un tercero sí
  queda cubierto.
- **Los dos escritores**: `to_csv` (objetos del mapa) y `track_to_csv`
  (trayectorias). El `callsign` de esta última viene de **OpenSky** —
  dato de un tercero, ni siquiera del operador.
- Las notas quedan cubiertas de fábrica (la celda empieza con
  `[timestamp]`) y la blindada por valor las cubre igual por si cambia
  el formato.

## Lo que NO cambia

- **KML y GeoJSON no se tocan**: son otras clases de archivo (XML y
  JSON), no CSV — fuera del ítem.
- Los números del CSV siguen siendo números: `-34.6` se abre como
  `-34.6`, sin apóstrofo ni comillas de más.
- Sin cambio de contrato: misma ruta, mismas columnas, mismo
  delimitador `;`.

## La guarda

`tests/test_p009_csv_injection.py`, 4 escritas **antes** de tocar:
**3 rojas** — la fórmula salía viva en `name` y en `description`, la de
la trayectoria con el callsign `=1+1`, y `_blindar` ni siquiera
existía — y **1 verde de arranque**: las latitudes negativas intactas,
que es la cara que el arreglo tiene prohibida y que sigue verde
después. La roja del CSV se volvió a medir **por revertida**: sin el
blindado vuelve `=HYPERLINK(...)` a secas.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **544 pasan** (540 + 4 nuevas) |
| `pytest -m integration` (8010 reiniciado) | **7 pasan en 29 s** |
| `npm test` (frontend) | **460 pasan**, 33 archivos |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (38,1 s) |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** (la capa obsoleta, ya encolada) |

Nota de suite: la primera corrida de frontend, en paralelo con pytest,
sacó **1 roja** con el perfil documentado del flaky de
`toolbar.spec.js` (corrida lenta, >190 s); la corrida limpia inmediata
dio **460/460 en 90 s**.

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 540 | **544** (+4) |
| Integration | 7 | **7** |
| Frontend | 460 (33 archivos) | **460** (33) |
| geo_parity | 675 | **675** |
| smoke_e2e (base temporal) | 77/78 | **77/78** |
# 0.30.22 — P0-01 + P0-03: el número de expediente ya no se puede perder

**Fecha:** 2026-10-04 · **Rama:** `auditoria/p001-p003-numero-obligatorio` ·
**Auditoría de Claude, ítems P0-01 y P0-03 — «van juntos y ya se pueden»**

## Qué estaba mal, por dos frentes

**La base lo permitía.** `numero_expediente` era anulable: cualquier
escritura directa dejaba expedientes sin número, y el número ES el
identificador del caso — sin él, la fila es un documento sin firma.

**La API lo hacía sola.** `PUT /expedientes/{id}` con
`{"numero_expediente": null}` pasaba por `exclude_unset` — el `None`
vino **explicitado**, no omitido —, el route hacía `setattr(None)` y
**commiteaba**; recién después la validación de la respuesta reventaba
en 500. O sea, en ese orden: fila sucia **y** error en inglés. Ese era
el origen real de las filas que P0-03 manda a limpiar.

P0-06 (0.30.5) se hizo antes exactamente para éste: un respaldo previo
y una versión de esquema. Acá están los dos.

## P0-01: `nullable=False`

Modelo (`app/models/expediente.py`):

```python
numero_expediente = Column(String(50), nullable=False, unique=True, index=True)
```

Y **la API deja de fabricar el problema** — validadores en las schemas
(patron del proyecto, F2-05 traduce `value_error` con nuestro mensaje):

- `ExpedienteUpdate`: `null` explícito → **422** «el número de
  expediente no admite null»; vacío o en blanco → 422 «no puede quedar
  vacío». La fila guardada queda **intacta** (lo que antes se perdía).
- `ExpedienteCreate`: número en blanco → 422 con el mismo mensaje.
- Sin cambio de contrato con el frontend: el **422 en lista** era ya la
  forma que `describeError` parsea desde el POST (F2-05), así que
  `client.js` no se toca. Lo que cambia es que el PUT con `null` pasó
  de 200-con-500-detrás a 422 temprano.

## P0-03: limpiar sin borrar

SQLite **no sabe** `ALTER COLUMN`, así que la migración reconstruye la
tabla. Los pasos (versión 1 → 2):

1. `CREATE TABLE IF NOT EXISTS expedientes (forma vieja)` — los pasos
   corren **antes** de `create_all`, así que una base recién creada
   atraviesa la migración con cero filas en vez de romper con «no such
   table».
2. **La limpieza**: `UPDATE … SET numero_expediente = 'SIN-NUMERO-' || id
   WHERE numero_expediente IS NULL OR TRIM(numero_expediente) = ''`.
   - **No se borra ninguna fila**: mediciones, eventos y vínculos siguen
     enteros. Borrar un caso porque le falte el número sería tirar la
     investigación por una etiqueta.
   - `SIN-NUMERO-5` **no inventa un número de causa**: es un marcador
     de ausencia, legible, único (el `id` lo es), y el operador puede
     poner el número real después por la API de siempre.
   - Determinista: la migración es un solo paso transaccional y
     repetible.
3. `CREATE TABLE expedientes_nuevo (… NOT NULL)` + `INSERT … SELECT`
   **con lista de columnas explícita** (el orden de la tabla vieja de
   una base que nadie vio no está garantizado; el de la nueva, sí).
4. `DROP` + `RENAME` (con `foreign_keys` OFF en esta conexión, como
   siempre) y recreación de los tres índices con sus nombres de siempre.

**En la base real, en vivo**: respaldo automático previo
(`aerorf-20261004-204642.db`), `user_version: 1 → 2`, el expediente
del operador **idéntico** (`EX-2026-37478934-…`, 118.85, abierto), y
`notnull = 1` leído de `PRAGMA table_info`. Cero filas tocadas (la base
real no tenía ninguna sucia).

## Lo que tuve que adaptar al subir la versión

- `test_p006` fijaba `_version == 0` tras una migración rota: con
  `VERSION_ESQUEMA = 2` el paso 1 (sin sentencias) **sí** corre y el
  fallo del paso 2 deja la versión en 1. El aserto ahora es
  `VERSION_ESQUEMA - 1` — la intención («nunca reclamar el paso que
  revienta») queda intacta y queda más fuerte: además mide el avance
  parcial legítimo.
- El log «esquema sin versionar **adoptado como versión 1**» mintió
  apenas hubo pasos: ahora dice «llevado a la versión {VERSION}».
- El docstring de `lifecycle.py` que decía que este cambio «ya estaba
  encolado» pasó a decir que **es** la migración 2.

## La guarda

`tests/test_p001_p003_numero_obligatorio.py`, 7 escritas **antes** de
tocar: **6 rojas** (esquema anulable, PUT null, PUT vacío, POST vacío,
migración de base vieja, migración de base nueva) y **1 verde** de
arranque (crear sin número ya era 422). Repetidas **por revertida**
(`git stash` de los cuatro archivos de implementación): mismas 6 rojas.
Detalle del primer intento de revertida: la base temporal ya estaba en
v2 y la app revertida la rechazó con `BaseDeDatosMasNueva` — el
mecanismo de P0-06 haciendo su trabajo; para el rojo por aserto se
limpió la base temporal (desechable por diseño).

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **551 pasan** (544 + 7 nuevas) |
| `pytest -m integration` (8010 reiniciado, migración aplicada) | **7 pasan en 27 s** |
| `npm test` (frontend) | **460 pasan**, 33 archivos |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (1 m 19 s) |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** (la capa obsoleta, ya encolada) |
| Base real del operador (solo lectura tras el reinicio) | v2, respaldo previo, 1 expediente intacto, `notnull=1` |

Nota de suite: la primera corrida de frontend corrió **en paralelo con
el build** y sacó 448/460 con el perfil documentado del flaky; la
corrida limpia inmediata dio **460/460 en 77 s**.

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 544 | **551** (+7) |
| Integration | 7 | **7** |
| Frontend | 460 (33 archivos) | **460** (33) |
| geo_parity | 675 | **675** |
| smoke_e2e (base temporal) | 77/78 | **77/78** |
| Versión del esquema | 1 | **2** |
# 0.30.23 — Los últimos textos en inglés del backend, de una

**Fecha:** 2026-10-04 · **Rama:** `auditoria/textos-espanol-backend` ·
**Regla del proyecto: lo que el operador lee está en español**

## Cómo llegó a ser un solo ítem

La cola de RETOMAR los anotó **uno por uno** — `ws.py`, el aviso de
arranque, `expedientes.py`, «future timestamps», `correlation.py`,
`map.py` — y el barrido encontró **más de lo mismo** en
`map_service`, `flight_service`, `opensky_service` y `cache`: unas 40
frases de una línea repartidas en 12 archivos. Son la misma falta
once veces: prosa nuestra escrita en inglés donde llega un detalle
`HTTPException`, un `MapServiceError` o un frame del websocket.
Traducirlos en tandas de uno habría sido once rondas de rama y
commit para una sola regla; se cierra **como un ítem**, con una guarda
que cubre cada frase.

## Qué se tradujo

| Dónde | Qué |
|---|---|
| `map.py` | el helper `_not_found` («Object … not found») y los tres matchers `if "not found" in str(exc)` que lo buscaban — cambiados **junto con el servicio**, después de grep: la frase vivía en `map_service` |
| `correlation.py` | 404 y «has no position…» ×2, «radii_nm must be…» |
| `expedientes.py` | 4 × «Expediente not found» + «already exists» (y el comentario en inglés que tocaba, por la regla de lo que un commit toca) |
| `rf_expediente.py` | 2 × «Expediente not found» |
| `flights.py` | «Invalid ICAO24…», «`end` must be greater…» ×2, «future timestamps» ×2, «Session … not found» ×2, «Stop the session…», «At most … per query», «bbox must be…» |
| `system.py` | «Invalid log level» |
| `ws.py` | «Unknown action: …» (el frame `error` al navegador) |
| `main.py` | el aviso de arranque — **que además era falso** (abajo) |
| `map_service.py` | tipo/estado/campo desconocidos, «Invalid WGS84» ×3, «A note cannot be empty», «Object … not found» ×4 |
| `flight_service.py` | «Invalid date/time…» — las rutas las devuelven como 400 vía `_handle` |
| `opensky_service.py` | timeout, red, token rechazado, límite de créditos (¡estaba **mezclado**: la mitad en inglés y la mitad en español), parámetros, 5xx, HTTP raro, reintento, JSON ilegible |
| `cache.py` | el mensaje del gate de backoff de F2-07 (429 al operador) |

### El aviso de arranque decía una mentira

> «OpenSky credentials absent — flight features disabled»

Falso: en modo anónimo el **tráfico en vivo sí funciona** (OpenSky
sirve `/states/all` sin cuenta) y lo que se cae sin credenciales es el
**historial**. El texto nuevo lo dice así, en español, y nombra
`OPENSKY_ALLOW_ANONYMOUS`, que es la llave del otro caso.

### El quinto ICAO24

`test_error_icao24` ya existía para un mensaje que estaba **cuatro
veces** en `flight_service.py`, y fija que las cuatro pasen por
`_explicar_icao24_invalido`. La ruta `GET /{icao24}/flights` tenía su
**propia quinta copia**, en inglés, que el guardia no miraba (escanea
`flight_service.py`). Ahora la ruta usa el mismo ayudante: una sola
prosa, en español, que además dice «si escribió un callsign, ese campo
sí funciona».

## Lo que quedó fuera, con la razón

- **`geo.py require_latlon`** — nadie lo llama: es código muerto y su
  `ValueError` no llega a ninguna respuesta.
- **`rf_expediente` y su `except Exception → 500 str(exc)`** — otra
  clase de defecto (el 500 que F2-05 manda que no exista), no prosa:
  si se arregla, se arregla por el estado, no por el texto.
- **Lo que escriben httpx, SQLite o el OpenSky arriba de nosotros** —
  texto de terceros; se traduce donde nace la frase nuestra.
- **Las líneas de log por petición** — claves de diagnóstico, no prosa
  de pantalla. El aviso de arranque sí entró: es lo primero que el
  operador lee al abrir la consola.

## La guarda

`tests/test_textos_espanol_backend.py`, **49 escritas antes de tocar**:
**12 en vivo** (los endpoints de la cola pedidos de verdad: 404 de mapa,
expediente y sesión; el 400 del repetido; correlación sin posición y
radios inválidos; ICAO24, timestamps y `end > begin`; nivel de log) y
**37 portero de código** — el texto viejo literal no reaparece en su
archivo, el patrón de `test_error_icao24`. **49 rojas antes** y
**49 rojas por revertida** (`git stash` de los 13 archivos).

Colateral honesto: **2 pins adaptados** en `test_map_objects` («Unknown
object type» → «Tipo de objeto desconocido», «Unknown field» →
«campo(s) desconocido(s)») — el assert sigue midiendo que el mensaje
**nombre** el problema; cambia el idioma, no la intención.

Y una validación del portero que se corrigió a sí misma: el primer
ciclo quedó en 48/49 porque el scan encontró «already exists» en un
**comentario** en inglés sobre la línea que tocaba — traducido, como
manda la regla.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **600 pasan** (551 + 49 nuevas) |
| `pytest -m integration` (8010 reiniciado) | **7 pasan en 28 s** |
| `npm test` (frontend) | **460 pasan**, 33 archivos |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (38 s) |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **77 de 78** (la capa obsoleta, ya encolada) |

**En vivo contra el 8010**, los cuatro que la cola nombraba:

```
GET /map/objects/9999          → {"detail":"No existe el objeto 9999."}
GET /expedientes/9999          → {"detail":"No existe el expediente 9999."}
POST /flights/sessions/9999/start → {"detail":"No existe la sesión de vuelo 9999."}
GET /flights/lvkcc/flights     → 422 «…Si es un nombre de vuelo como LVKCC,
                                  escríbalo en el campo de callsign…» (¡hasta
                                  las comillas latinas del ayudante!)
```

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 551 | **600** (+49) |
| Integration | 7 | **7** |
| Frontend | 460 (33 archivos) | **460** (33) |
| geo_parity | 675 | **675** |
| smoke_e2e (base temporal) | 77/78 | **77/78** |
| Frases en inglés llegando al operador | ~40 | **0** (guarda de 37 scans) |
# 0.30.24 — El smoke esperaba 15 capas y se siembran 17

**Fecha:** 2026-10-04 · **Rama:** `auditoria/smoke-capas-17` ·
**Clase:** expectativa vieja, no regresión (RETOMAR lo anotó así)

## Qué fallaba

Desde el 26/09, cuando entraron `lines` y `polygons` en
`DEFAULT_LAYERS` (15 → 17), el chequeo de capas de `smoke_e2e.py`
reportaba FAIL en **base limpia**:

```
Failures:
  - 15 default layers :: 200
SMOKE_EXIT=1
```

Ese era el único rojo de los **77/78**: el endpoint contestaba `200`
con `count = 17`, o sea perfecto — la expectativa del script era la que
estaba vieja. No era regresión: el smoke nació con 15 y nadie lo
actualizó cuando la semilla creció.

## El arreglo

Dos números en una línea de `smoke_e2e.py` (el rótulo **y** el valor:
ambos dicen 15) pasan a **17**, con un comentario que apunta a la
guarda. El chequeo sigue siendo igual de estricto: en base recién
creada, los defaults siembrados son exactamente los de
`DEFAULT_LAYERS`, y `_seed_layers` además **backfillea** los que falten
en bases viejas (por eso el 8010 real ya servía 17).

## La guarda: que no vuelva a desfasarse

El defecto no fue el número: fue que el código creció y el script no.
`tests/test_smoke_capas.py` (**3 pruebas, la del valor roja antes**)
lee el número escrito en `smoke_e2e.py` y lo pisa con
`len(DEFAULT_LAYERS)`:

- **el chequeo existe y se puede leer** — si alguien reescribe la línea
  con otra forma, la guarda lo dice en vez de fallar mudo;
- **el valor son los defaults que se siembran** — la roja de este ítem:
  *«smoke_e2e espera 15 capas y DEFAULT_LAYERS siembra 17»*;
- **la etiqueta dice el mismo número que el valor** — el rótulo del
  informe no puede quedar desfasado del chequeo (los dos decían 15,
  pero son dos literales independientes).

El smoke es un script HTTP puro, sin imports de `app` — habla con el
servidor como lo haría el frente — así que no puede comparar contra el
origen él solo; la guarda vive en la suite de pytest, que corre siempre.

Si alguien agrega una capa por defecto, la guarda queda roja hasta que
el smoke diga el número nuevo; si se pone roja sin que los defaults se
hayan tocado, es el smoke el que se movió.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **603 pasan** (600 + 3 nuevas) |
| `pytest -m integration` (8010) | **7 pasan en 37 s** |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **78 de 78**, `SMOKE_EXIT=0` |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (30 s) |
| `npm test` (frontend) | **460 pasan**, 33 archivos |

Rojo por revertida: `git stash` del arreglo en `smoke_e2e.py` → la
guarda vuelve a decir *«espera 15 … siembra 17»*.

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 600 | **603** (+3) |
| Integration | 7 | **7** |
| smoke_e2e (base temporal) | **77/78** (la capa) | **78/78** |
| Frontend | 460 (33 archivos) | **460** (33) |
| geo_parity | 675 | **675** |
# 0.30.25 — `.env.example` por fin documenta el TTL de tracks en vivo

**Fecha:** 2026-10-04 · **Rama:** `auditoria/env-example-ttl-vivo` ·
**Clase:** documentación de configuración (omisión del 0.30.2, anotada
por la auditoría)

## Qué faltaba

`CACHE_TTL_TRACKS_LIVE_S` nació en 0.30.2 — el caché corto (30 s) que
usa la ruta `fresh=true` cuando se sigue a una aeronave en el aire,
para que el sondeo de 10 s no sea contestado con los bytes de 300 s —
y **quedó sin documentar en `.env.example`**: quien copiaba el ejemplo
para armar su `.env` no se enteraba de que existía. La auditoría lo
dejó escrito como «omisión del 0.30.2».

## La variable, y el archivo

La línea entra con su comentario **en español**, entre
`CACHE_TTL_TRACKS_S` y `CACHE_TTL_FLIGHTS_S` (el mismo orden que
`config.py`), explicando lo que hace: es el mismo caché acortado, gasta
créditos de más sólo mientras alguien sigue un vuelo que está volando.

Y como tocar `.env.example` obliga a que lo tocado hable español
(precédente: el bloque de `ALLOWED_HOSTS` que P0-07 agregó en su
momento), el resto del archivo queda como está — traducirlo entero es
otro ítem, no éste.

## La guarda: por campo, no por la lista concreta

El defecto no fue el número: fue que el settings creció y el ejemplo
no. `tests/test_env_example_documentado.py` (**28 pruebas: la de la
variable roja antes, 27 de control verdes**) recorre `Settings` y exige
que **cada campo con `default_factory`** — en este dataclass, esa es
la señal de «lee la variable de entorno» — esté escrito en
`.env.example`. Si mañana aparece un settings nuevo, hay una prueba
roja nueva esperando a que el ejemplo lo diga.

Dos exclusiones documentadas en el propio guardia:

- **`max_tracked_aircraft` no es una omisión**: es default plano
  («hard cap from the spec, not configurable»); una línea en el
  ejemplo **mentiría**, porque no se leería nunca.
- **`VITE_PORT` está en el ejemplo y no en `Settings`**: lo lee el
  frente y `start.bat`. La comparación va de `Settings` al ejemplo, no
  al revés.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **631 pasan** (603 + 28 nuevas) |
| `pytest -m integration` (8010) | **7 pasan en 36 s** |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **78 de 78**, `SMOKE_EXIT=0` |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (29 s) |
| `npm test` (frontend) | **460 pasan**, 33 archivos |

Rojo por revertida: `git stash` de la línea del ejemplo → *«Settings
lee `cache_ttl_tracks_live_s` de la variable de entorno y .env.example
no la documenta»*.

Sin cambio de comportamiento: `.env.example` no lo lee nadie en
runtime (lo que se lee es `.env`, que no se toca).

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 603 | **631** (+28) |
| Integration | 7 | **7** |
| smoke_e2e (base temporal) | 78/78 | **78/78** |
| Frontend | 460 (33 archivos) | **460** (33) |
| geo_parity | 675 | **675** |
| Variables de `Settings` documentadas en el ejemplo | 26 de 27 | **27 de 27** |
# 0.30.26 — `async def` sin nada de async: adiós al loop congelado

**Fecha:** 2026-10-04 · **Rama:** `auditoria/p1-async-def` ·
**Ítem:** P1 de la auditoría («`async def` → `def`; con SQLite hay que
mirar `check_same_thread` antes; Claude lo marca como no medido»)

## El prerrequisito, cumplido desde antes

`_build_engine` pasa `check_same_thread=False` a **toda** conexión
sqlite (`database.py`), que es lo que permite que el threadpool de
FastAPI toque la base desde distintos hilos — con `StaticPool` (los
tests en memoria) la conexión única se comparte justamente por eso.
No había que tocar nada: el ítem sólo exigía **mirarlo** antes de
convertir, y está mirado.

## Qué estaba mal, medido

Un `async def` **sin `await` ni `async with`** es trabajo síncrono
disfrazado: FastAPI lo corre **sobre el event loop de asyncio**, y
mientras dura, no giran ni el WebSocket de vuelos ni el sondeo de
OpenSky ni ninguna otra petición. El barrido con `ast` sobre `app/`
encontró **9**: los 3 handlers de `rf.py` (mat pura), la dependencia
`_service_or_503`, los dos manejadores de errores (`_validacion`,
`_integridad`), `ws.stop`, `ws._record` (escribe sesiones en la base
en cada tick) y `lifespan` — este último **exento**: `@asynccontextmanager`
exige que sea async, es elección del framework.

Lo que se congelaba por request en `POST /rf/calculate`, medido en
esta máquina con el motor real (one-off, 50–200 corridas):

| Candidatas | Mediana | Peor |
|---|---|---|
| 12 | 3,98 ms | 44,44 ms |
| 24 | 18,7 ms | 22,9 ms |
| 48 | **75,2 ms** | **115,9 ms** |

O sea: con una planilla de 48 candidatas, **~75–116 ms de loop
parado por cada consulta de interferencias** — el feed en vivo se
congelaba y ni se enteraba el operador. `harmonics` (0,014 ms) y
`validate` (0,044 ms) eran cosméticos, pero entran al mismo invariante.

## El arreglo

Las 8 funciones pasan de `async def` a **`def`** (FastAPI las manda al
threadpool y el loop sigue girando), con sus dos únicos call sites
actualizados: `service = await _service_or_503()` y
`await self._record(...)` pierden el `await` (esperar algo que no es
corrutina sería `TypeError`). `ws.stop` no tenía llamadores.

Los exception handlers síncronos los soporta Starlette de fábrica:
`starlette._exception_handler` importa `is_async_callable` y
`run_in_threadpool` justamente para eso, y los 422/400 en vivo salen
idénticos.

**Lo que queda async, y por qué:** los handlers de vuelos y
correlación **esperan OpenSky de verdad** — son async legítimos. Sus
llamadas cortas a la base entre `await` son de milisegundos; moverlas
al threadpool sería otra pieza, medida primero, no ésta.

## La guarda

`tests/test_async_sin_trabajo_sincrono.py` (**55 pruebas: las de los
8 rojas antes**) recorre `app/` con `ast` y exige, función por
función, que cada `async def` contenga `await`, `async with` o
`async for`, o que esté envuelto en `@asynccontextmanager`. El
mensaje dice qué hacer: declárala `def`, o anota por qué el framework
exige async. Un handler nuevo síncrono-en-máscara tendrá su prueba
roja esperando.

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **686 pasan** (631 + 55 nuevas) |
| `pytest -m integration` (8010 reiniciado) | **7 pasan en 35 s** |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **78 de 78**, `SMOKE_EXIT=0` |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (31 s) |
| `npm test` (frontend) | **460 pasan**, 33 archivos |

En vivo contra el 8010 con el código nuevo: `/health` ok;
`POST /rf/calculate` devuelve el IM3 (2×88.5 − 58 = 119, score 99);
un body roto cae en `_validacion` síncrono con su 422 en español;
`GET /flights/live` pasa por `_service_or_503` y contesta 200 con
tráfico real.

Rojo por revertida: `git stash` de `app/api` → las mismas 8 vuelven a
la carga.

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 631 | **686** (+55) |
| Integration | 7 | **7** |
| smoke_e2e (base temporal) | 78/78 | **78/78** |
| Frontend | 460 (33 archivos) | **460** (33) |
| geo_parity | 675 | **675** |
| `async def` sin async real en `app/` | **9** | **1** (`lifespan`, exento) |
# 0.30.27 — Correlación: la temporal de verdad, y la caja en vez del mundo

**Fecha:** 2026-10-04 · **Rama:** `auditoria/p1-correlacion-temporal` ·
**Ítem:** P1 de la auditoría («Compara el evento con las posiciones
*actuales* y la documentación dice «espacial y temporal»; eso correlaciona
un evento de hace tres días con tráfico de hoy. Primero corregir la
redacción, después comparar con `observed_at`. Y `get_states()` global en
vez de `get_states_in_box` quema créditos»)

## El defecto

Los dos payload de correlación (`routes/correlation.py` y
`services/flight_service.py`) anunciaban **«Correlación espacial y
temporal únicamente»** mientras comparaban el evento con las posiciones
**actuales** del cielo: un evento de hace tres días declaraba
contemporáneas a las aeronaves de hoy. Y las tres rutas que traían
estados a mano pedían `get_states()` **global** — todo el cielo para
correlizar una caja.

## Arreglado en el orden de la cola

**1. La redacción.** Cada respuesta ahora **declara cómo compara**:
`comparacion` (`espacial_y_temporal` cuando hay `observed_at`,
`espacial` cuando no), `observado_en`, `ventana_temporal_s` y
`fuera_de_ventana`. El disclaimer del objeto explica la comparación que
hace; la vista por aeronave (`/correlation/aircraft/{icao24}`), que sólo
lista cercanía, tiene **su propio disclaimer declarado espacial** — que
es lo que dicen el MANUAL §215, la Ficha Técnica y el propio GisShell,
coincidiendo por fin con los hechos.

**2. `observed_at`.** Cuando el objeto tiene fecha de observación, cada
estado se compara con `delta_t_s` = `last_contact − observed_at`; sólo
cuenta dentro de la ventana de **600 s**
(`CORRELACION_VENTANA_TEMPORAL_S`, en `app/core/correlacion.py`). Lo que
queda dentro del radio pero fuera de la ventana se **reporta** en
`fuera_de_ventana`, no se esconde. Un estado sin hora no prueba nada y
no cuenta. Sin `observed_at` no hay nada que comparar y la respuesta se
declara `espacial`. El flujo en vivo no cambia (evento recién observado
→ deltas de segundos → todo cuenta); el de historia usa el `states` que
el cuerpo ya permitía mandar — que ahora es el camino honesto: estados
del momento del evento, deltas ≈ 0. En la ruta de vuelos,
`correlate_event` aplica la misma regla.

**3. La caja en vez del mundo.** Las tres rutas (`rf-aircraft`,
`object/{id}`, `flights/correlate`) piden ahora
`get_states_in_box(*caja_alrededor(...))` con el radio máximo pedido
alrededor del objeto. La caja de 50 nm mide ~4 sq-deg: **tramo de 1
crédito** de `estimate_states_credits` (área ≤ 25 sq-deg), con respuesta
de decenas en vez de miles de estados. Además el handler de vuelos ya no
gasta la llamada si el objeto no existe o no tiene posición (antes
traía el cielo para que `correlate_event` rechazara después).

## Lo que queda dicho y no estaba dicho

- **Hallazgo anotado:** `estimate_states_credits` modela la rama `None`
  como «serial-only» (1 crédito) — el caso **global no está modelado**
  en el repo, así que este commit no afirma cuánto ahorra en créditos el
  cambio; afirma lo verificable: la caja cae en el tramo de 1 crédito y
  se deja de pedir el estado global. Va como pendiente aparte.
- **Contrato:** los campos nuevos son **aditivos**; `client.js` pasa los
  datos sin esquema, así que no requiere cambio (y no se tocó).
  `FlightPanel` pinta el disclaimer nuevo tal cual, sin editar Vue.
- El mensaje «Object … has no position» de `flights/correlate` era
  inglés y **llegaba al cliente** (400 vía `_handle`): traducido, y el
  portero de textos ganó el pin
  `("app/services/flight_service.py", "has no position…")` — que estaba
  rojo antes (la cadena vivía en el archivo) y verde después.
- `app/core/correlacion.py` es el **único** dueño de ventana, delta,
  caja y los dos disclaimer: la duplicación entre la ruta y el servicio
  quedó afuera.

## La guarda

`tests/test_correlacion_temporal.py` — **11 pruebas: 10 rojas antes y
una de control verde** (`test_control_bandas_sigue_contando_lo_espacial`:
las bandas siguen contando lo espacial). Cubren el caso de la auditoría
(evento de 3 días → 0 contemporáneas + `fuera_de_ventana`), el flujo en
vivo (evento de 30 s → cuenta, con su `delta_t_s`), el objeto sin fecha
(`comparacion: espacial`), el estado sin hora (no cuenta), los dos
disclaimer y las tres rutas pidiendo caja (la caja se valida por
propiedades: centrada, simétrica, cubre el radio, área ≤ 25 sq-deg — no
se copia la fórmula de implementación). **Rojo por revertida:**
`git stash push -- app` → las mismas 11 (10 + el pin del portero).

## Verificación

| Suite | Resultado |
|---|---|
| `pytest -m "not integration"` | **698 pasan** (686 + 11 + 1 pin) |
| `pytest -m integration` (8010 reiniciado) | **7 pasan en 29 s** |
| `python tests/smoke_e2e.py` (base temporal, 8011) | **78 de 78**, `SMOKE_EXIT=0` |
| `tests/geo_parity.mjs` | **675 pasan** |
| `npm run build` | compila (33 s) |
| `npm test` (frontend) | **33 de 33 archivos** |

En vivo contra el 8010 con el código nuevo: `/health` ok y las suites
de integración ejercitan las tres rutas de correlación con el servicio
real.

### Los números

| Suite | Antes | Después |
|---|---|---|
| Python sin integración | 686 | **698** (+11 temporal +1 pin) |
| Integration | 7 | **7** |
| smoke_e2e (base temporal) | 78/78 | **78/78** |
| Frontend | 460 (33 archivos) | **460** (33) |
| geo_parity | 675 | **675** |
| Disclaimers que prometían temporal sin medirlo | 2 | **0** |
## 0.30.28 — Las plantillas dejan de mentir: `slate-N` → nombres semánticos

El puente de 0.30.0 cumplió su promesa temporal con el costo que declaraba en su
propio comentario: unas 640 utilidades `slate-N` reescritas por CSS para que
`bg-slate-900` pintara `--panel` — la clase mentía y cualquier uso nuevo podía
quedar gris sin que nadie lo notara. El ítem «migrar las plantillas» era la otra
mitad, y ahora está:

- **652 reemplazos en 22 plantillas**: cada `slate-N` pasó a su nombre
  semántico (`bg-panel`, `text-texto-medio`, `border-borde`…). Tres reglas de
  rol donde la misma clase cumplía papeles distintos: los 12 inputs a
  `bg-panel-hondo` («campos, zonas hundidas»), las cajas claras dentro de
  tarjetas a `bg-on-ink-wash` (si no, sobre `panel-alto` se volvían invisibles)
  y los divisores de 1px a `bg-borde`. Los fondos de diálogo translúcidos
  conservaron su transparencia con dos tokens nuevos, `--velo` (75%) y
  `--velo-suave` (45%), en el patrón `color-mix` de los `on-ink`. Los
  placeholders muertos (sintaxis v2, sin `text-`, nunca generados) ahora son
  `placeholder:text-texto-invisible` y se pintan.
- **El puente se borró**: las 28 reglas de `styles.css` desaparecieron y en su
  lugar quedó una cabecera en español que explica de dónde sale el color. Los
  20 nombres semánticos viven una sola vez, en `tailwind.config.js`, cada uno
  `var(--token)` — la clase y el token dicen lo mismo.
- **Guardas**: nueva `sin_slate.spec.js` (cero `slate-N` en el fuente; roja
  antes con 652), `tokens.spec` adaptado (las 14 utilidades semánticas
  resuelven a token, el bundle no contiene ni una regla `slate-\d`, ningún
  ring amarra a `--signal`) y `theme.spec` con el espejo dado vuelta
  (`slate === 0` y más de 20 usos semánticos). La intención de cada test
  adaptado está escrita en el propio test.

**465 frontend (34 archivos) · 705 Python · 675 paridad · 36 geo · build ✓.**
## 0.30.29 — El círculo recién dibujado se selecciona solo

Dibujar un círculo servía para que existiera: el objeto aparecía en el mapa y el
inspector seguía diciendo «seleccione un objeto», así que detallarlo pedía
buscarlo a mano en la lista. Ahora `handleToolComplete` deja el objeto recién
creado **seleccionado** y abre el inspector si estaba cerrado — el mismo gesto
que ya hacía el clic en una aeronave. Se dibuja para escribir sobre lo que se
dibujó.

Prueba en `drawing-flow.spec.js` con el harness existente (monta el shell, dos
clics reales, `createObject` interceptado): el inspector arranca **cerrado** a
propósito y tiene que terminar abierto con el id del objeto nuevo — **roja
antes** (`selectedId: null → 7`), verde después.

**466 frontend (34 archivos) · build ✓ · backend sin cambios.**
## 0.30.30 — La capa de aeropuertos dibuja la lista del operador, con icono descargable

El composable `useAirport` que cargó el operador (116 sitios: aeropuertos,
EAVA/ACC, CCTE, aeroclubs) es ahora lo que la capa de referencia
visualiza en el mapa, **sumado** a lo publicado — nada de lo que ya estaba
se pierde:

- Un sitio que cae a ≤ 2 km de un aeropuerto publicado se dibuja **una vez**,
  con ese aeropuerto, y el popup lista todos los que caen ahí (SAAV lleva
  «SANTA FE» y «EAVA SAUCE VIEJO»). Los números de la coincidencia: 76 de
  116 emparejan; el emparejado más lejano está a 1937 m y el sitio suelto
  más cercano a 4679 m — el umbral cae en una zona sin datos.
- Los 40 sitios sin aeropuerto cerca se dibujan como círculo ámbar, con su
  grupo y su etiqueta; el popup dice «Sitio de la lista del operador, no
  medido por AeroRF»: procedencia visible, sin inventar códigos que la
  lista no tiene.
- El símbolo de aeropuerto es ahora el icono de
  `public/iconos/aeropuerto.svg` sobre un disco claro (clase nueva
  `.aerorf-airport-icon`): el mapa es oscuro y el SVG descargado viene
  negro. Las familias mayor/menor se distinguen por el tamaño del icono
  (26/18 px), ya no por el color del círculo; los helipuertos siguen en
  círculo pizarra.
- Cuatro iconos descargados de Font Awesome Free 6.7.2 (CC BY 4.0) y
  dejados en `public/iconos/` con `LEEME.txt` de procedencia:
  `aeropuerto.svg` y, para el item siguiente, `fm.svg`, `tprs.svg`,
  `otro.svg`. Cambiar un dibujo es reemplazar el archivo, mismo nombre —
  el código sólo nombra la ruta.
- El composable vive en `src/composables/useAirport.js` con la lista del
  operador textual, y su guard en `airports.spec.js` le aplica las mismas
  salvaguardas que al archivo publicado: identificadores únicos y
  coordenadas en rango.

Pruebas: 4 nuevas en `airports.spec.js` — **rojas antes** (el sitio CCTE
CABA no se dibujaba y el marcador no tenía `options.icon`), 4 adaptadas
con la intención escrita en el test (unión publicado+lista, filtro por
país y contador, familias por tamaño). **470 frontend (34 archivos) ·
build ✓ · backend sin cambios.**
## 0.30.31 - La fuente del punto: FM, TPRS u Otra, con su icono reemplazable

El punto ya no es un círculo anónimo. Al armar la herramienta **Punto**, las
opciones muestran **Fuente del punto**: Sin fuente (punto simple), FM, TPRS u
Otra fuente, y la elección viaja como campo `icon` al guardar. El campo no es
nuevo - el backend lo guarda y lo devuelve desde hace versiones; lo que
faltaba era escribirlo y dibujarlo:

- `MapEngine` dibuja `public/iconos/<valor>.svg` (clase
  `.aerorf-punto-icono`, el mismo disco claro que el avión de aeropuerto)
  cuando el objeto es un punto y su `icon` está entre `fm`/`tprs`/`otro`.
  Cualquier otro valor -el `point` por defecto, las filas viejas- sigue
  siendo el círculo de siempre: lo que el operador no pidió no cambia de
  aspecto.
- La fuente se elige al crear el punto (opciones de la herramienta) y se
  cambia después desde el inspector, sobre un punto existente, sin volver
  a dibujarlo. La creación manual por coordenadas también la lleva.
- Los tres SVG ya estaban en `public/iconos/` con su `LEEME.txt` desde
  0.30.30; cambiar un dibujo sigue siendo reemplazar el archivo, mismo
  nombre, sin tocar código.

Pruebas: 6 nuevas - **rojas antes** - repartidas en
`stored-shapes.spec.js` (el marcador con `icon: 'fm'` devolvía el
círculo; y guardas: los tres archivos existen, el `point` por defecto
sigue siendo círculo), `components.spec.js` (la sección *Fuente del
punto* sólo con la herramienta activa, y el selector del inspector que
escribe `icon` con `updateObject`) y `drawing-flow.spec.js` (el payload
del punto no llevaba la fuente elegida). Detalle del rojo: `setTool`
sin toolManager no mueve `activeTool` - lo mueve GisShell al reportar la
herramienta -, así que el test del panel lo pone directo, que es
justamente el contrato del componente.

**476 frontend (34 archivos) - build V - backend sin cambios.**
## 0.30.32 - Espectro, baja total: se fue el menú, la ruta y la vista

El operador eligió la baja total de la sección Espectro, y la baja se hizo en
los tres archivos donde la sección podía sobrevivir:

- `BrandBar.vue` ya no ofrece la sección: quedan cuatro enlaces en el menú
  (Mapa, Panel, Expedientes, Calculadora RF).
- El enrutador ya no registra `/espectro`: la dirección vieja cae en el
  redireccionamiento catch-all y vuelve al mapa, sin una pantalla rota.
- `src/views/EspectroView.vue` fue borrada del fuente.

Lo que NO se tocó, a propósito: `Chart.vue` y plotly siguen, porque la
Calculadora RF grafica con el mismo componente, y el backend de
espectrogramas queda intacto - la baja es de la pantalla, no de los datos
del operador. El comentario de `vite.config.js` que atribuía plotly sólo a
la vista de espectro quedó corregido: lo usa la calculadora, bajo demanda.
El MANUAL y el README pasan de cinco secciones a cuatro.

Pruebas: 3 guardas nuevas en `brandbar.spec.js` - **rojas antes** (el menú
ofrecía `/espectro`, el enrutador la registraba y el view existía) -, una
por archivo editado a mano, para que la sección no vuelva por una entrada
vieja; 3 adaptadas con la intención escrita en el test (la lista de
secciones esperadas y el piso de enlaces bajan de 5 a 4).

**479 frontend (34 archivos) - build V - backend sin cambios.**
## 0.30.33 - Panel, baja total: se fue el menu, la ruta y la vista

Segunda baja total que pide el operador, con el mismo patrón del 0.30.32 y en
los mismos tres archivos donde una sección puede sobrevivir sin que nada la
contradiga:

- `BrandBar.vue` ya no ofrece la sección Panel: quedan tres enlaces (Mapa,
  Expedientes, Calculadora RF).
- El enrutador ya no registra `/dashboard`: la dirección vieja cae en el
  catch-all y vuelve al mapa, sin una pantalla rota.
- `src/views/DashboardView.vue` fue borrada del fuente, y con ella
  `src/components/StatCard.vue`, que era su único consumidor (se grepeó antes
  de borrar: `DataTable` la sigue usando `ExpedientesView` y ésa queda).

Lo que NO se tocó, a propósito: el contrato de la API. `rf.summary` sigue en
`frontend/src/api/client.js` aunque se quede sin quien lo llame, porque recortar
un cliente es un cambio de contrato y no hace falta para dar de baja una
pantalla. Los datos del operador tampoco se tocan.

Pruebas: 3 guardas nuevas en `brandbar.spec.js` - **rojas antes** (el menú
ofrecía `/dashboard`, el enrutador la registraba, y el view y el StatCard
seguían en el fuente) -, una por archivo editado a mano. 5 adaptadas con la
intención escrita en el test: las que usaban `/dashboard` como «otra sección
cualquiera» (navegación, marca, lockup y pie) ahora usan `/expedientes`, y el
piso de enlaces baja de 4 a 3.

De yapa, dos guardas que el build del 0.30.32 había dejado obsoletas y que
aparecieron recién al correr la suite contra ese build:

- `theme.spec` exigía que el CSS generara `bg-sky-700`. Ese era su único uso
  en todo el fuente (un botón de `EspectroView`), así que el CSS dejó de
  generarla y la guarda estaba pidiendo una ausencia. Salió de la lista; el
  acento sky sigue cubierto por `text-sky-400` y por la cuenta de clases sky.
- `chart-loading.spec` exigía un chunk propio para `Chart.vue`. Con la baja de
  Espectro, Rollup ya no lo separa - un solo importador dinámico lo deja
  adentro del chunk de la calculadora -, así que la guarda ahora mide el peso
  del chunk que lo lleva: 16 KB, con plotly siempre en su chunk de 1000 KB. Lo
  que la guarda protegía, que el wrapper no arrastre la librería, sigue
  midiéndose igual.

El MANUAL y el README pasan de cuatro secciones a tres, con las secciones
renumeradas, y los comentarios de `App.vue` y `styles.css` que nombraban
pantallas ya borradas quedaron corregidos.

**482 frontend (34 archivos) - build V - backend sin cambios.**