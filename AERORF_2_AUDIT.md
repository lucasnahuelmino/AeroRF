# AERORF 2.0 — Auditoría del repositorio

Fecha de inspección: 2026-11-03  
Rama: `mejora/panel-baja`  
Commit inspeccionado: `a8c7377` (`0.30.33 Panel, baja total: se fue el menu, la ruta y la vista`)  
Estado inicial de Git: limpio.

## Alcance y método

Se inspeccionaron la estructura del frontend y backend, los modelos SQLAlchemy,
las rutas FastAPI, los servicios, stores, vistas y componentes GIS, las pruebas,
las dependencias y la documentación principal. La auditoría refleja el código
local, no las cifras históricas de documentos previos.

No se abrió ni imprimió el contenido de `.env`, no se revelaron credenciales y
no se modificó la base de datos. Para revisar Expedientes se usó una conexión
SQLite `mode=ro` que consultó únicamente conteos agregados y claves foráneas;
no se leyeron valores de las filas. El repositorio no presentaba cambios
locales antes de esta tarea.

## Arquitectura actual

- **Frontend:** Vue 3, Vite, Pinia, Vue Router, Leaflet y Tailwind. La interfaz
  GIS se concentra en `GisShell.vue`; `MapEngine` posee las capas Leaflet y el
  store de mapa coordina datos, selección y persistencia.
- **Backend:** FastAPI/Uvicorn, Pydantic y SQLAlchemy. `app/main.py` registra
  los routers GIS, RF, vuelos, exportación, sistema, WebSocket y los routers
  heredados de Expedientes.
- **Persistencia:** SQLite por configuración actual del proyecto, con soporte
  de SQLAlchemy y una arquitectura portable hacia PostgreSQL. El esquema
  declarado contiene 19 tablas. `create_all` y el sembrado de capas forman
  parte del arranque; no se encontró un flujo de migraciones Alembic activo en
  `requirements.txt`.
- **GIS:** `MapObject` centraliza identidad, geometría GeoJSON, coordenadas,
  capa, visibilidad, estado, procedencia, propiedades e historial. Los
  atributos RF tipados están en tablas satélite. La API ofrece listado
  paginado/filtrado, creación, edición, borrado, estado, movimiento,
  duplicación, notas, historial, importación GeoJSON y administración de capas.
- **Vuelos:** hay servicios y rutas OpenSky, estado en tiempo real por
  WebSocket, historial/trayectorias, selección y correlación. La existencia de
  estas rutas no sustituye pruebas de conectividad real con el proveedor.
- **RF:** existe motor Python dedicado para armónicos, intermodulación,
  tolerancias y ranking, además de rutas RF y entidades GIS para fuentes,
  antenas y eventos.
- **Espectro:** no se encontró `EspectroView.vue` ni una función `inBand` en el
  código inspeccionado. Sí permanece el modelo legado `RegistroEspectral`.
  No debe atribuirse al estado actual una interfaz de análisis de espectro que
  no está presente.

## Estado funcional por pilar

| Pilar | Estado observado | Brecha principal |
|---|---|---|
| Mapa | Shell GIS, Leaflet, dibujo/medición, selección, capas base, aeropuertos, vuelos y exportación están presentes. | La administración de capas no reemplaza un listado persistente de todos los objetos. |
| Objetos | El modelo y la API contemplan objetos ocultos, geometría, edición, borrado y persistencia. Se implementó un administrador paginado independiente del mapa. | La edición contextual reutiliza el inspector existente; faltan superficies avanzadas de estilo/metadata y validación visual en navegador. |
| Análisis RF | Motor RF, calculadora, correlación, fuentes, antenas y eventos existen en el backend. | No se verificó una experiencia integrada que cubra todos los cálculos físicos solicitados ni una auditoría de sus supuestos. |
| Espectro | Hay un modelo de datos histórico. | No hay vista `EspectroView.vue` ni `inBand`; importación, detección de picos y comparación están pendientes, no corregidas. |
| Expedientes | Persiste como módulo en navegación superior, rutas/vistas, store, endpoints y modelos; el panel del shell GIS se retiró al agregar Objetos. | No está eliminado. La fila existente obliga a definir un archivo/migración antes de retirar rutas y APIs. |

## Datos, API e integraciones

- `MapObject.visible` y `Layer.visible` son estados distintos de la existencia
  del registro. `MapObject.layer_id` permite relación nula y la capa usa
  `ON DELETE SET NULL`; el administrador muestra objetos sin capa e incluye un
  filtro dedicado para encontrarlos.
- La ruta de objetos acepta filtros por tipo, capa, capa ausente, categoría,
  origen, estado, visibilidad, búsqueda por nombre/ID y caja geográfica, con
  límite, desplazamiento y total coincidente. Por omisión, no limita el
  resultado a objetos visibles.
- Las respuestas de mapa y exportación conservan geometría GeoJSON y propiedades
  específicas. Hay historial y notas en el modelo GIS.
- La aplicación conserva configuración OpenSky en backend. La auditoría no
  inspeccionó valores de configuración ni probó llamadas externas.
- CORS y validación de origen/host tienen módulos propios. Esta lectura
  arquitectónica no es una revisión de seguridad exhaustiva ni una prueba de
  explotación.

## Calidad y pruebas: resultados medidos

- Backend: `.\.venv\Scripts\python.exe -m pytest -q -m "not integration"`:
  **699 pasaron, 7 fueron excluidas por el marcador, 19 advertencias**.
- Las advertencias incluyen APIs deprecadas de Pydantic/Starlette y uso
  obsoleto de `datetime.utcnow()` / `utcfromtimestamp()` en código de pruebas y
  producción.
- Pruebas focalizadas del administrador: **71 backend y 2 frontend pasaron**.
- `npm run build`: pasó, con advertencia de un chunk Plotly de ~1.1 MB y base
  Browserslist atrasada.
- La última ejecución completa de `npm test -- --run` pasó: **484 pruebas en
  35 archivos**. Se ajustó a 20 segundos el timeout de dos pruebas sensibles
  a la carga del entorno; no se modificó su comportamiento probado.
- `npm run lint` no se puede ejecutar: no hay configuración ESLint en el
  repositorio aunque exista el script.
- No se ejecutó el conjunto marcado como integración contra servicios reales.
- Los números de pruebas y endpoints en el README y auditorías anteriores no
  se consideran evidencia actual hasta volver a medirlos.

## Hallazgos priorizados

### Crítica

1. **Administrador GIS agregado; cobertura funcional básica probada.** El
   panel lista páginas del backend, no solo el cache del mapa, incluye objetos
   ocultos y capas ausentes, y reutiliza el CRUD existente. Falta validación
   manual/visual en navegador.
2. **Retirar Expedientes requiere preservar una fila existente.** El inventario
   encontró datos en la tabla y ningún vínculo por FK desde las entidades
   inspeccionadas; el contenido de la fila no se leyó. Retirar su interfaz o
   API sin una estrategia de archivo podría dejar esos datos inaccesibles.

### Alta

3. **La superficie de Expedientes está distribuida.** La navegación superior,
   rutas frontend, vistas, store, panel, carga inicial del shell, endpoints
   `/expedientes` y `/rf/expedientes`, modelos heredados y FK siguen activos.
   Una eliminación parcial dejaría rutas o dependencias huérfanas.
4. **No hay módulo de espectro activo ni se encontró `inBand`.** La corrección
   algorítmica pedida no puede aplicarse a una función inexistente; primero
   debe decidirse/implementar una interfaz sustentada por datos de entrada y
   probar detección por banda.
5. **No se detectó una capa de migraciones instalada/configurada.** Cambios
   estructurales deben diseñarse como migración aditiva o documentarse antes
   de alterar el esquema existente.

### Media

6. **La documentación está desfasada respecto del código.** README y
   arquitectura aún presentan Expedientes como sección vigente y declaran
   conteos de pruebas/endpoints que requieren actualización medida.
7. **Hay deuda de compatibilidad visible en advertencias.** Debe tratarse de
   forma gradual, sin mezclarla con la prioridad GIS.
8. **La evolución visual está parcialmente iniciada.** Existen tokens
   semánticos y una shell oscura, pero no se verificó una migración global de
   estilos hardcodeados ni las superficies avanzadas de estación de trabajo.

## Límites y riesgos conocidos

- La base SQLite activa contenía 1 fila en `expedientes`, 1 en `map_objects` y
  0 en `mediciones`, `eventos_rf` y `registros_espectrales`. No había filas con
  `expediente_id` no nulo en `map_objects`, `mediciones` ni `eventos_rf`. No se
  leyó el contenido del expediente; mantener la fila y el esquema hasta decidir
  cómo archivar sus campos.
- No se validaron credenciales, despliegue, límites de uso OpenSky, servicios
  de teselas ni interacción visual en navegador.
- La ausencia de `inBand` se verificó por búsqueda de código; una rama/historia
  distinta podría contener una implementación no presente en este checkout.
- No se hizo revisión de seguridad especializada ni se deducen vulnerabilidades
  de los controles existentes a partir de una inspección superficial.
