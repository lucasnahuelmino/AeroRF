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
