# AERORF 2.1 — Auditoría del rebranding institucional y corrección de trayectorias

Fecha de inspección: 2026-11-04  
Rama de trabajo: `mejora/aerorf-2-rebranding-trayectorias`  
Commit base: `f86d752` (`merge: consolidacion integral AeroRF 2.0`)  
Estado del repositorio: limpio antes de la revisión; se respetó la regla de no tocar la base de producción y no se ejecutaron mutaciones destructivas.

## Alcance

Esta revisión se centró en la corrección del problema reportado en la etapa 1 del plan: una trayectoria aérea se ocultaba o cortaba cuando cruzaba un círculo GIS, y el sistema mezclaba tres conceptos distintos que debían separarse claramente:

- seguimiento en vivo,
- visualización de trayectoria,
- grabación AeroRF.

La inspección se hizo sobre el código real del repositorio, no sobre documentos previos, y se validó con la suite de frontend disponible en el mismo checkout.

## Resumen ejecutivo

El problema real no estaba en la lógica de vuelo por sí misma sino en la composición del render GIS:

- la trayectoria se dibujaba en un grupo/capa cuyo orden de apilado quedaba por debajo de las geometrías del operador,
- el `MapEngine` no aseguraba un pane dedicado y estable para las trayectorias,
- los extremos de la línea y los path se mezclaban entre renderers y panes,
- el comportamiento del layer group no estaba desacoplado de la lista de seguimiento.

La corrección vigente en el código actual separa el diseño de la capa de trayectorias del resto del mapa, con una creación explícita de un renderer propio para `aircraft_tracks` y un pane `aerorfTracksPane` que queda por encima de las formas rellenas sin bloquear los clics del mapa.

La auditoría concluye que el repositorio ya incorpora la corrección principal de la etapa 1 y que la causa raíz se resolvió con una combinación de:

1. pane dedicado para rutas de aeronaves,
2. z-index apropiado para mantener la ruta encima de geometrías GIS y debajo del avión,
3. pointer-events desactivados en el pane/canvas para evitar que la capa “se coma” todos los clics,
4. separación lógica entre caché de trayectorias, selección de aeronaves seguidas y grabación local.

## Estado real por subsistema

### Frontend

- `frontend/src/map/MapEngine.js`: el motor de mapa define categorías, orden de dibujo y pane para recorridos. La implementación actual respeta que la trayectoria quede por encima de la geometría operatoria, pero por debajo del icono del avión.
- `frontend/src/map/aircraft.js`: `AircraftRenderer.drawTrack()` conserva por aeronave la trayectoria y distingue procedencias, sin interpolar puntos ni inventar datos. Los extremos de la ruta siguen siendo marcadores, no paths, para que los hover y tooltips sigan funcionando.
- `frontend/src/stores/flights.js`: `tracks` se guarda por ICAO24, con normalización de clave; `track` queda como el último solicitado para la UI; `watchlist` y `recording` se mantienen separados.
- `frontend/src/views/GisShell.vue`: el flujo de render y watchlist se integra con el renderer y con la lógica de visibilidad.

### Integración con OpenSky y WebSocket

- Las consultas de trayectoria y las rutas de historial se manejan por `flightsApi.track()` y `flightsApi.flightsOf()`, sin mezclar el alta a la lista de seguimiento con la consulta de la ruta.
- La contratación del socket queda desacoplada de las pruebas y no se exige una conexión real para validar la lógica de la trayectoria.

### Arquitectura GIS y rebranding

La base del repositorio mantiene la lógica de capas y objetos GIS sin convertir AeroRF en un dashboard genérico: la herramienta sigue priorizando análisis aeronautical, geográfico y radioeléctrico. La corrección de trayectorias no cambia esa intención.

## Observaciones sobre el problema reportado

### 1. Orden de dibujo y pane de trayectoria

La causa raíz era la asignación de la capa `aircraft_tracks` en un canvas compartido con las formas como círculos, radiales y objetos del operador. Eso hacía que la ruta quedara debajo del relleno de la figura cuando el mapa usaba `preferCanvas` y un único render list ordenado por `_leaflet_id`.

La solución actual crea un pane especial:

- `aerorfTracksPane`
- `trackRenderer` asociado al pane
- `pointer-events: none` en el pane y su canvas para no bloquear clics del mapa
- z-index intermedio entre `overlayPane` y `markerPane`

Esto garantiza que:

- las geometrías del operador queden por debajo de la trayectoria,
- el icono del avión quede por encima de su propia ruta,
- el mapa siga siendo interactivo.

### 2. Separación conceptual

La corrección no solo cambia el dibujo. También deja separadas tres decisiones:

- `watchlist`: aeronaves bajo seguimiento en vivo,
- `tracks`: datos de trayectoria cargada y visible,
- `recording`: grabación local de AeroRF.

Esto permite mantener una trayectoria histórica visible aunque el seguimiento en vivo se detenga, y que el operador quite la ruta explicitamente sin que una geometría o una actualización del watchlist la borre por accidente.

### 3. Continuidad y procedencia

La lógica de `drawTrack()` conserva la secuencia temporal de puntos, mantiene la procedencia en la representación y no inventa posiciones intermedias. La visualización distingue orígenes reales de datos (histórico, vivo, AeroRF, merged) sin desordenar la ruta.

## Pruebas y validación

Se ejecutó la suite frontend completa con:

```powershell
cd frontend
npm test -- --run
```

Resultado medido en este checkout:

- 35 archivos de pruebas
- 484 pruebas ejecutadas
- 484 aprobadas
- 0 fallos

Esto incluye las pruebas de regresión de trayectorias y del pane dedicado, además de las pruebas de flujo, watchlist, render y selección GIS.

## Hallazgos y estado final

### Completados

- corrección del corte visual de trayectorias al cruzar círculos GIS,
- separación entre seguimiento, trayectoria y grabación,
- ajuste de apilado para que el avión esté encima de su propia ruta,
- protección de interactividad del mapa con `pointer-events: none`,
- pruebas de regresión relevantes,
- base de rebranding institucional centralizada en `frontend/src/assets/tokens.css` con la nueva paleta AeroRF 2.1 y tipografía de marca.

### Parcialmente implementados / bloqueados por seguridad de datos

- `Expedientes` ya no aparece en la navegación activa y sus rutas frontend heredadas (`/expedientes` y `/expedientes/:id`) redirigen al mapa. Esto es una retirada parcial de la experiencia, no la eliminación definitiva del módulo: permanecen vistas, stores, consumidores internos, cliente API y endpoints/modelos backend. Antes de retirar esas estructuras hay que inventariar notas, adjuntos, mediciones, historial y evidencias y definir cómo vincularlos a objetos GIS, RF y sesiones.
- No se verificó aquí que los datos de Expedientes hayan sido archivados ni migrados. No se ejecutaron escrituras o migraciones sobre bases de datos; por lo tanto, no se afirma que la preservación de datos ya esté resuelta.
- la recuperación del módulo Espectro queda en evaluación; requiere validación real de filtros y picos antes de reintroducir un componente funcional.

### Inventario de preservación de Expedientes (solo código)

La inspección de modelos, endpoints y consumidores confirma estas estructuras:

| Información | Persistencia actual | Destino o vínculo posible en AeroRF | Estado |
|---|---|---|---|
| Identificador, estado, severidad, frecuencia, aeropuerto, coordenadas, inspector y narrativa | `expedientes` | No hay un modelo GIS de caso equivalente; no se debe convertir automáticamente el expediente entero en un objeto cartográfico ni crear un módulo sustituto | Sin destino aprobado |
| Objetos GIS vinculados | `map_objects.expediente_id` (`ON DELETE SET NULL`) | El vínculo ya existe; la API impide borrar un caso mientras haya objetos vinculados | Preservado por FK y guarda |
| Notas, historial y anotaciones de objetos | `object_notes`, `object_history`, `annotations`, relacionados con `map_objects` | Permanecen junto al objeto GIS correspondiente | Vínculo actual disponible |
| Mediciones de campo con frecuencia, nivel, ancho de banda, coordenadas, fecha y notas | `mediciones.expediente_id` | Potencialmente asociables a un objeto/medición GIS, pero falta un crosswalk que determine objeto, tipo y procedencia por fila | Sin migrar; ahora el borrado se bloquea con 409 |
| Resultados calculados RF | `eventos_rf.expediente_id` | `rf_events.calculated_evento_id` permite referenciar un resultado legacy desde un evento GIS | Sin migrar; ahora el borrado se bloquea con 409 |
| Capturas, CSV u otros archivos espectrales: tipo, nombre, centro/ancho de banda, anotaciones y estado de procesamiento | `registros_espectrales.expediente_id`; `archivo_path` referencia almacenamiento externo | Requiere resolver y verificar cada archivo en su almacenamiento antes de asociar sus metadatos a un evento, fuente o sesión | Sin inventario físico; ahora el borrado se bloquea con 409 |

El inventario es de esquema y código, no de contenido: no se abrió una base configurada ni se inspeccionó el sistema de archivos de evidencias. No hay evidencia suficiente para construir un mapeo automático sin riesgo de asignar mediciones o archivos al objeto GIS equivocado.

Como protección preventiva, `DELETE /expedientes/{id}` ya no elimina en cascada mediciones ni eventos calculados y responde 409 si hay registros dependientes: objetos GIS, mediciones, resultados RF o metadatos espectrales. El bloqueo no constituye un archivo ni una migración; conserva la información mientras se define y valida su destino.

### Centro de Situación y Espectro

- Se incorporó `/situacion` como una vista operativa de solo lectura con estado reportado de API/base, modo/configuración OpenSky, aeronaves en la lista de seguimiento, sesiones grabando, eventos RF GIS y mediciones GIS recientes. Las fuentes se consultan mediante APIs existentes o extensiones acotadas con orden temporal y límite.
- El feed de actividad general no existe como historial consultable: `/system/logs/recent` informa configuración/ruta de logs, mientras los registros técnicos salen por stdout. La vista declara esta limitación y no fabrica una lista de actividad.
- La lista de seguimiento muestra las aeronaves efectivamente marcadas por el operador y estados ya recibidos por el WebSocket; no consulta todos los vuelos globales ni llama OpenSky para llenar la pantalla. El indicador de OpenSky describe configuración/capacidad reportada, no disponibilidad real del proveedor.
- Espectro no tiene vista, ruta, API ni motor actual de análisis: `RegistroEspectral` conserva metadatos y una ruta externa a archivos; no se encontró ingestión de datos ni lógica activa de detección/filtro de picos. No se recuperó código antiguo ni se activó un análisis sin archivos/protocolo de entrada verificables.

### Sin novedad relevante

- no se encontraron secretos en `.env` ni se expusieron credenciales,
- no se consultaron ni modificaron bases de datos o archivos de evidencias,
- no se realizaron cambios de esquema ni migraciones.

## Conclusión

El repositorio ya resolvió la fase crítica de trayectorias, centralizó el rebranding institucional e incorporó un Centro de Situación limitado a fuentes reales disponibles. Expedientes fue retirado parcialmente de la navegación y su endpoint de borrado protege las filas dependientes identificadas en el esquema. La preservación/migración aún no está resuelta porque falta inspeccionar una copia autorizada de datos y el almacenamiento de evidencias, además de aprobar un crosswalk. Espectro permanece fuera de la aplicación: solo se identificaron metadatos de archivos, sin un motor de análisis comprobable.

## Addendum — AeroRF Workspace 2.2

La rama actual de trabajo es `mejora/aerorf-workspace-unificado`, basada en
`0fb57d1` (`main` integrado). Se preservaron las modificaciones locales de la
fase anterior; esta continuación no crea commits, no publica cambios y no hace
deploy.

### Cambios del workspace

- `GisShell.vue` ahora monta una sola superficie lateral. Su estado distingue
  abierto, contraído y cerrado; la sección, lado y ancho se persisten en
  `localStorage`, y el cambio de tamaño/posición vuelve a invalidar el tamaño de
  Leaflet.
- La navegación del workspace conserva paneles mediante `KeepAlive` y reúne
  herramientas, capas, objetos, vuelos, aeropuertos, inspector y línea de
  tiempo.
- La selección del mapa ya no abre automáticamente el inspector. La acción
  explícita abre el contexto de objeto o aeronave; el contexto se puede fijar y
  recuperar desde el historial reciente.
- El timeline del workspace y el dock inferior reutilizan el estado de replay
  del store de vuelos. Se quitó el intervalo local de seguimiento: el mapa
  sigue el índice compartido de replay y el shell pausa la reproducción al
  desmontarse.
- `App.vue` dejó de montar `FooterBar`; el mapa ocupa ahora el espacio restante
  bajo la cabecera institucional. El componente de footer permanece en el
  repositorio, pero no forma parte del árbol de la aplicación.
- El workspace se vuelve superpuesto en pantallas estrechas para conservar el
  área cartográfica. Se añadieron pruebas de modos, persistencia, contexto
  fijado, navegación explícita, footer ausente y estado compartido del timeline.

### Alcance que sigue pendiente

- La navegación no agrega todavía una sección de Configuración ni una vista
  independiente de Espectro: no se encontró un motor activo verificable ni un
  protocolo/muestra autorizado para análisis de picos y bandas.
- No se modificaron las APIs legacy de Expedientes más allá de la protección
  contra borrado de datos dependientes; la eliminación completa continúa
  bloqueada por falta de crosswalk aprobado y datos/evidencias autorizados.
- La implementación y sus pruebas requieren validación final de frontend,
  build, backend y paridad geográfica antes de registrar resultados de cierre.
