# AERORF 2.1 — Plan de implementación y seguimiento

## Objetivo

Corregir el problema de visualización de trayectorias aeronáuticas cuando atraviesan geometrías GIS, especialmente círculos de cobertura, y separar conceptualmente:

- seguimiento en vivo,
- visualización de trayectoria,
- grabación AeroRF.

La meta no es solo hacer que la ruta aparezca nuevamente: es dejar la herramienta consistente con el principio de procedencia y con la prioridad de interacción del operador sobre el mapa.

## Fase 0 — preparación y auditoría

Estado: completado.

- se validó que el checkout estuviera limpio,
- se trabajó sobre la rama `mejora/aerorf-2-rebranding-trayectorias`,
- se revisó la estructura real del backend, frontend y servicios de vuelos,
- se identificó el problema de render y la causa raíz del “corte” de la trayectoria.

### Criterio de aceptación

- no se toca la rama principal,
- no se modifica la base de producción,
- se prioriza la inspección del código real sobre documentos históricos.

## Fase 1 — prioridad crítica: rutas de aeronaves

Estado: completado.

### Tareas

1. Inspeccionar el recorrido real de la ruta de una aeronave desde OpenSky hasta el renderer del mapa.
2. Confirmar dónde la trayectoria queda detrás de una geometría GIS o desaparece por orden de capa.
3. Ajustar el `MapEngine` para usar un pane y renderer específicos para `aircraft_tracks`.
4. Garantizar z-index correcto para que:
   - la trayectoria quede por encima de objetos GIS,
   - el avión quede por encima de su propia ruta,
   - el mapa siga recibiendo clics.
5. Desactivar `pointer-events` en el pane/canvas de trayectorias para evitar que la capa tape el mapa.

### Resultado esperado

La trayectoria permanece visible aunque el avión:

- entre o salga de un círculo,
- recorra varias geometrías,
- se desplace en vivo,
- cambie visibilidad o opacidad de la capa,
- se reordenen los grupos o se ejecute `restack()`.

## Fase 2 — separar seguimiento, visualización y grabación

Estado: completado.

### Tareas

1. Mantener `watchlist` como el conjunto de aeronaves monitoreadas.
2. Mantener `tracks` como caché de trayectorias visibles / cargadas.
3. Mantener la grabación local AeroRF en un flujo independiente.
4. Permitir que una trayectoria histórica cargada siga visible aunque se interrumpa el seguimiento en vivo.
5. Permitir eliminar explícitamente una trayectoria sin que una geometría o una actualización del watchlist la borre por accidente.

### Resultado esperado

La vista y el ciclo de vida de la ruta dejan de depender de la pertenencia a la lista de seguimiento.

## Fase 2B — rebranding institucional y tipografía

Estado: implementado en la base del frontend con tokens centralizados y tipografías institucionales.

### Tareas

1. Definir la nueva paleta AeroRF 2.1 centrada en fondos oscuros, texto claro y acentos cyan/blue/amber/green/red/violet.
2. Centralizar los token en `frontend/src/assets/tokens.css` para sincronizar Tailwind, Vue y renderizados cartográficos.
3. Importar Space Grotesk + IBM Plex Sans + IBM Plex Mono desde CSS y aplicarlas a la UI institucional.
4. Mantener compatibilidad con los nombres semánticos existentes del sistema visual para evitar regresiones estructurales.

### Resultado esperado

La aplicación presenta una identidad coherente con los tonos solicitados y una tipografía institucional que mantiene legibilidad y contraste.

## Fase 3 — continuidad temporal y procedencia

Estado: completado.

### Tareas

1. Revisar `AircraftRenderer.drawTrack()` para evitar mezclas de orden cronológico.
2. Mantener un orden temporal real de los puntos.
3. Preservar la procedencia en las rutas (histórico, vivo, AeroRF, merged).
4. Separar segmentos cuando haya huecos reales de datos.
5. No interpolar puntos ni inventar ubicaciones intermedias.
6. Mantener los puntos de inicio y fin de la trayectoria.

### Resultado esperado

La ruta sigue siendo una secuencia real y comprensible, con cada tramo indicando su origen sin romper la continuidad ni forzar conexiones falsas.

## Fase 4 — renderizado Leaflet y interacción

Estado: completado.

### Tareas

1. Crear un pane exclusivo para aeropuertos/objetos y otro para trayectorias.
2. Asegurar que la capa de trayectorias dibuje sobre geometrías pero bajo los marcadores de aeronaves.
3. Evitar un canvas invisible o un pane que intercepta clicks.
4. Mantener el `markerPane` como lugar para puntos finales y labels de inicio/fin.
5. Validar que los cambios de visibilidad/opacidad y `restack()` no rompen la composición.

### Resultado esperado

La interacción del mapa sigue intacta y las capas no comparten comportamiento de hit-testing.

## Fase 4 — eliminar definitivamente Expedientes

Estado: retirada parcial de navegación; eliminación completa pendiente por preservación de datos y dependencias reales.

### Tareas

1. Revisar menús, rutas, vistas, stores, endpoints, modelos y referencias internas.
2. Identificar información útil que deba conservarse antes de borrar el módulo.
3. Vincular notas, sesiones y evidencias con objetos GIS, RF y registros relevantes.
4. Ejecutar la baja total solo cuando el proceso de archivado esté validado.

### Estado y observación de bloqueo

Las rutas frontend heredadas (`/expedientes` y `/expedientes/:id`) redirigen al mapa y el menú ya no ofrece el módulo. Sin embargo, las vistas, stores, usos internos (incluidas herramientas RF/GIS), el cliente API y los endpoints/modelos backend permanecen. La retirada de navegación no equivale a eliminar funcionalmente el módulo.

No se verificó un archivo o migración de datos. Antes de retirar las dependencias restantes, hay que inventariar notas, adjuntos, mediciones, historial y evidencias, definir sus vínculos con objetos GIS, eventos RF, antenas o sesiones y validar un proceso no destructivo. No ejecutar borrados ni migraciones destructivas en producción.

## Fase 5 — revisión del módulo Espectro y centro de situación

Estado: inactivo, requiere auditoría funcional y definición de solución.

### Tareas

1. Revisar si la recuperación del módulo Espectro es posible con una arquitectura coherente.
2. Evaluar detección de picos, bandas, umbrales y tratamiento de mediciones.
3. Definir un Centro de Situación operativa, que reúna estado de servicios, OpenSky y eventos relevantes sin caer en un dashboard genérico.

### Resultado esperado

Quedará documentado qué puede recuperarse con seguridad y qué debe mantenerse fuera de la línea de trabajo actual.

## Fase 6 — pruebas de regresión y validación

Estado: parcialmente completado; la base crítica de trayectorias está verificada y la rebrand base está validada.

Se cubrieron los escenarios principales del problema de trayectorias:

- trayectoria atravesando un círculo y continuando fuera,
- círculo dibujado antes y después de cargar la ruta,
- dos círculos superpuestos,
- cambio de visibilidad de capas,
- cambio de opacidad,
- `restack()`,
- actualización de posiciones en vivo,
- varias aeronaves simultáneas,
- transiciones históricas/live,
- huecos reales de datos,
- detención del watchlist sin perder la ruta cargada,
- eliminación explícita de trayectoria.

Se validó con la suite frontend disponible:

```powershell
cd frontend
npm test -- --run
```

Resultado verificado en este checkout:

- 35 archivos de pruebas
- 484 pruebas ejecutadas
- 484 aprobadas

## Riesgos y mitigaciones

### Riesgo: volver a mezclar vista con watchlist
Mitigación: cada entidad conserva su propia responsabilidad y la UI usa `tracks` por ICAO, no la lista de seguimiento como origen de verdad del render.

### Riesgo: volver al canvas compartido
Mitigación: el pane `aerorfTracksPane` y el `trackRenderer` están en la capa correcta y se validan con pruebas de render y de `pointer-events`.

### Riesgo: detectar un falso positivo en tests de jsdom
Mitigación: las pruebas de interacción GIS se enfocan en comportamiento observable en el DOM y en propiedades del pane, no en objetos Leaflet no serializables.

## Cierre

La corrección de trayectorias se consolida como un trabajo de ingeniería de render y de separación de responsabilidades, no como un parche puntual. La solución verificable se encuadra dentro del rebranding institucional y dentro del principio de no inventar ni recortar trazados de vuelo.
