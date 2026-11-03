# AERORF 2.0 — Plan de implementación

El plan se basa en [AERORF_2_AUDIT.md](./AERORF_2_AUDIT.md). Mantiene Vue 3,
FastAPI, SQLAlchemy, SQLite/PostgreSQL y Leaflet. No incluye commits, deploys,
dependencias nuevas ni borrado de datos.

## Prioridad crítica

1. **Administrador de objetos GIS — implementado**
   - Se añadió un panel accesible en la shell con listado de objetos
     persistidos, incluyendo los ocultos y los que pertenecen a capas ocultas.
   - Búsqueda por nombre/ID y filtros por tipo, capa (incluida capa ausente),
     categoría, origen, estado y visibilidad.
   - Acciones individuales y masivas; edición por el inspector existente,
     selección/centrado, visibilidad, duplicado y borrado confirmado.
   - La persistencia reutiliza `MapObject`, su store y el CRUD actual.
   - Pruebas focalizadas: 71 backend y 2 frontend pasaron.

2. **Retirada no destructiva de Expedientes — pendiente**
   - Inventario read-only realizado: una fila en `expedientes`, ninguna en sus
     tablas satélite inspeccionadas y ningún objeto GIS vinculado.
   - Desconectar navegación, vistas, stores y paneles para que el producto no
     ofrezca el módulo.
   - Retirar rutas funcionales exclusivas solo después de comprobar clientes y
     pruebas; responder de forma explícita a rutas obsoletas, no con fallbacks
     que aparenten éxito.
   - Conservar la fila existente y el esquema hasta definir su archivo o
     migración reversible. No se leyó el contenido ni se retiró la UI/API en
     esta pasada.
   - No ejecutar `DROP`, cascadas ni migraciones destructivas en esta etapa.

## Prioridad alta

3. **Consistencia de capas y edición GIS**
   - Completar administración de objetos por capa, orden y propiedades sin
     confundir ocultar capa con ocultar/eliminar objeto.
   - Validar geometrías y metadatos en el mismo camino de edición ya utilizado
     por el store/API.
   - Probar importación/exportación GeoJSON y relaciones de capa nulas.

4. **Vuelos y correlación**
   - Verificar frescura/procedencia de posiciones y trayectorias.
   - Validar selección simultánea, histórico y cálculo de distancias con datos
     de prueba contratados; distinguir histórico de vivo.
   - No presentar proximidad como causalidad.

5. **Análisis RF y espectro**
   - Verificar fórmulas del motor mediante casos numéricos y unidades.
   - Diseñar importación/visualización de espectro a partir de formatos
     existentes o definidos; implementar detección por banda con referencias
     locales y pruebas antes de optimizar.
   - No simular mediciones en vivo ni resultados no sustentados.

## Prioridad media

6. **Sistema visual y accesibilidad**
   - Extender los tokens actuales gradualmente y revisar navegación, responsive,
     contraste, teclado y etiquetas.
   - Evitar una sustitución masiva de estilos.

7. **Persistencia, trazabilidad y reportes**
   - Revisar origen, fecha, notas y evidencia asociados a los objetos GIS
     existentes; extender exportación solo cuando los datos estén estabilizados.

8. **Seguridad, rendimiento y mantenibilidad**
   - Revisar configuración sin mostrar secretos, CORS/host, validación de
     entradas, WebSocket, consultas y renderizado con pruebas medibles.
   - Resolver advertencias deprecadas en cambios relacionados, sin migración
     masiva separada.

## Secuencia segura y dependencias

1. Establecer pruebas/build de referencia (backend completo; build y suite
   frontend completos pasaron: 484 pruebas en 35 archivos).
2. Administrador sobre `MapObject` implementado y probado focalizadamente.
3. Prueba visual manual del panel pendiente.
4. Inventario read-only de base y relaciones de Expedientes completado; decidir
   cómo archivar la fila preservada.
5. Retirar la experiencia de Expedientes y los endpoints exclusivamente
   asociados, conservando el esquema hasta disponer de migración aprobada.
6. Avanzar a GIS, aeronáutica, RF/espectro, historial, seguridad y rendimiento.
7. Actualizar README, changelog y documentación con resultados ejecutados.

No se autoriza en este plan la eliminación de registros, tablas, backups ni
credenciales. Cualquier migración destructiva requiere aprobación explícita.
