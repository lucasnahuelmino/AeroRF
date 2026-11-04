# AERORF 2.0 — Cambios

## 2026-11-03 — Primera iteración

### Implementado

- Se creó [AERORF_2_AUDIT.md](./AERORF_2_AUDIT.md) y
  [AERORF_2_IMPLEMENTATION_PLAN.md](./AERORF_2_IMPLEMENTATION_PLAN.md) a partir
  del código, las pruebas ejecutadas y un inventario SQLite read-only.
- Se agregó el panel **Objetos GIS** a la barra lateral del mapa.
- El panel lista desde el backend con paginación y filtros por nombre/ID, tipo,
  capa (incluida la falta de capa), categoría, origen, estado y visibilidad.
- Los objetos ocultos no se excluyen del administrador. Se puede seleccionar,
  centrar, abrir el inspector para editar, cambiar visibilidad, duplicar,
  eliminar con confirmación y realizar operaciones masivas de visibilidad y
  eliminación.
- Se amplió la respuesta GIS con categoría, procedencia e información de capa;
  el listado incluye `total` sin cambiar el significado existente de `count`.
- Se agregaron filtros de categoría, origen, falta de capa y búsqueda exacta por
  ID a la consulta compartida de listado/conteo.
- Se agregaron pruebas de persistencia/consulta/edición/borrado de objetos
  ocultos y pruebas frontend del panel.
- Se reemplazó el panel lateral GIS de Expedientes por Objetos y se retiró su
  carga inicial del shell; la navegación superior y las vistas/API heredadas
  siguen presentes hasta definir el archivo seguro del registro existente.

### Preservación y pendiente

- No se modificó ni eliminó dato alguno de Expedientes. La inspección read-only
  encontró una fila de Expedientes, sin mediciones/eventos ni vínculos
  `expediente_id`; no se leyó el contenido de esa fila.
- Expedientes sigue presente en navegación superior, vistas y API. Su retirada
  y la migración/archivo de la fila existente quedan pendientes para no dejar
  datos útiles inaccesibles ni romper dependencias.
- Pendiente la implementación de las etapas GIS avanzadas, aeronáuticas,
  espectro/RF, historial/reportes, seguridad y optimización del plan.

### Validación

- Backend no integración: **699 pasaron, 7 excluidas**.
- Pruebas focalizadas del administrador: **71 backend y 2 frontend pasaron**.
- Build de producción: **pasó**; advirtió que Plotly produce un chunk
  minificado de ~1.1 MB y que Browserslist necesita actualización.
- Suite frontend completa: **484 pasaron en 35 archivos**. Se ampliaron a 20
  segundos los timeouts de dos pruebas sensibles a la carga del entorno.
- Lint no disponible porque no hay configuración ESLint en el repositorio.
