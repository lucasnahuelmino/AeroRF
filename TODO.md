# TODO — AeroRF

Estado al cierre de la Fase 13. Lo hecho está en `AERORF_CHANGELOG.md`;
las decisiones y su motivo, en `AERORF_ARCHITECTURE.md`.

---

## Resuelto en esta round

- [x] Auditoría completa del repositorio (`AERORF_AUDIT.md`)
- [x] Motor de vuelos que fabricaba datos — **eliminado por completo**
- [x] Tres implementaciones de mapa — **consolidadas en una**
- [x] `localStorage` como sistema de verdad — **eliminado**; todo va a SQL
- [x] OpenSky OAuth2 con `OpenSkyTokenManager` y renovación anticipada
- [x] Caché por pool de créditos con backoff ante 429
- [x] 19 tablas (las 16 del objetivo + 3 heredadas de SIARI)
- [x] `MapObject` como raíz de todo objeto geográfico
- [x] Notas append-only + historial de cambios por campo
- [x] GeoJSON bidireccional, KML 2.2, CSV
- [x] Coordenadas del cursor permanentes (era el punto P5 de la auditoría)
- [x] 10 herramientas GIS con preview, ESC y confirmación
- [x] Inspector dinámico con notas e historial
- [x] LayerManager con 15 capas
- [x] Menú contextual
- [x] WebSocket `/ws/flights` sin inundar al cliente
- [x] Grabación local de vuelos
- [x] Seguimiento de hasta 5 aeronaves
- [x] Correlación espacial con advertencia de no-causalidad
- [x] Timeline y replay
- [x] Bundle inicial: 5 058 kB → ~436 kB
- [x] **Se quemaban 24 créditos/hora consultando el mundo entero sin nada en seguimiento**
- [x] Suite de pruebas: 373 unitarias + 615 de paridad + 78 E2E + 6 WebSocket + 43 recorrido real
- [x] **Validado contra OpenSky real con credenciales**: OAuth2, tracks, flights, recorrido §57 completo

## Bugs reales encontrados al verificar

- [x] Un objeto bloqueado no se podía desbloquear (trampa de ida y vuelta)
- [x] `midpoint()` degeneraba a `atan2(0,0)` en trayectorias ecuatorianas
- [x] `timed()` y `_emit()` del logger colisionaban con campos `event`/`level`
- [x] `_store_track()` no fijaba `session_id` — las pistas quedaban huérfanas
- [x] `_coerce()` movía el `kind` de una antena al bloque RF (500)
- [x] `get_or_set` sobrecontaba llamadas upstream (contabilidad de créditos)
- [x] `estimate_states_credits` multiplicaba el área por 4
- [x] `this._toMetres()` no existía en `draw.js`
- [x] uvicorn sin soporte WebSocket → **todo el feed en vivo daba 404**
- [x] **`parse_state_vector` exigía 18 campos; la respuesta real tiene 17** → las 13 369 aeronaves rechazadas en silencio
- [x] **`/flights/*` usa camelCase y no tiene `dep_lat`** → los tiempos de vuelo salían `None`
- [x] **Altitudes imposibles en tracks reales** (−304 m, 0 m) → ahora se marcan, no se grafican
- [x] **La resolución de los waypoints no es uniforme** → se informa la mediana y el rango, no solo la media
- [x] `status` repetido cada 10 s en el WebSocket (spec §48)
- [x] Test roto del motor RF (`tolerance_khz` duplicado)

---

## Pendiente

### Antes de_multiusuario

- [ ] **Autenticación.** Hoy `object_notes.user` y `object_history.user`
      están en el esquema pero sin respaldo. La vista ya los escribe.
- [ ] **Alembic.** El esquema se crea con `create_all`. Hace falta antes de
      la primera migración real de datos.

### Opcional, por valor

- [ ] **PostGIS.** La migración está documentada
      (`ARCHITECTURE.md` §3.4) y es un `ALTER TABLE` + `ST_GeomFromGeoJSON`,
      sin cambios de código. Solo tiene sentido con volúmenes grandes o
      consultas espaciales complejas.
- [ ] **Caché compartida.** La caché es en proceso, correcto para un
      operador. Con varias instancias, Redis.
- [ ] **PDF.** El spec §46 lo deja «para después». GeoJSON, KML y CSV ya
      cubren la exportación.
- [ ] **Importar DXF/shapefile.** `POST /map/objects/from-geojson` ya acepta
      FeatureCollection; falta el lector de otros formatos.
- [ ] **Reemplazar `Chart.vue`.** Plotly está aislado en un chunk de 4,6 MB
      que solo carga la vista de la calculadora. Un SVG lo eliminaría.
- [ ] **Tests de componentes Vue.** No hay runner de tests de frontend
      (vitest no está instalado). La lógica pura sí está cubierta:
      `map/geo.js` se verifica contra Python con 615 comprobaciones.

### Descartado deliberadamente

- [ ] ADS-B Exchange, OpenAIP, mapas de calor, cobertura RF avanzada.

  Añadidas ahora, abrirían la superficie de créditos y distraerían antes de
  que el núcleo sea sólido. Ver el razonamiento en el encargo.

---

## Regla para continuar

> Si un dato no existe, mostrar «dato no disponible».
> Si OpenSky no tiene datos, decirlo. No fabricar.
> No afirmar causalidad entre una aeronave y una interferencia.
> Antes de cerrar cada fase: backend arriba, frontend arriba, pruebas
> verdes, consola limpia, y documentación actualizada.
