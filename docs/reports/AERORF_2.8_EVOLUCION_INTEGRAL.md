# AeroRF 2.8 — Evolución integral

## 1. Resumen ejecutivo

Campaña de evolución integral ejecutada. Se completaron los pendientes de
hardening (deduplicación persistente con migración Alembic, gestión de
`SESSION_ERROR`, recuperación de sesiones, política completa de retry/backoff
OpenSky, validación visual con Playwright) y se consolidó la plataforma. Frontend
537/537, backend 730/7, integración 7/7, build y lint limpios.

## 2. Arquitectura final

- Vue 3 + Vite + Pinia + Leaflet (frontend).
- FastAPI + SQLAlchemy + Pydantic (backend).
- SQLite (dev) / PostgreSQL (prod), con Alembic para migraciones versionadas.
- OpenSky con OAuth2, caché, backoff y retry.
- WebSocket con reconexión y backoff exponencial.

## 3. Nuevos módulos

- `analisis_rf`: historial propio de análisis RF (AeroRF 2.6).
- `AircraftPosition` dedup: índice único parcial (AeroRF 2.8).
- Migración Alembic: esquema inicial + índice de deduplicación.
- Validación visual: Playwright (3 tests de humo).

## 4. Modelos y relaciones

- `AircraftPosition` con índice único parcial `uq_positions_session_icao_ts`.
- `AnalisisRF` con `objeto_id` opcional (FK a `map_objects`).
- Tablas históricas (`expedientes`, `eventos_rf`, …) conservadas.

## 5. Endpoints nuevos o modificados

- `POST /rf/analisis`, `GET /rf/analisis`, `GET /rf/analisis/{id}`,
  `PATCH /rf/analisis/{id}`, `DELETE /rf/analisis/{id}`.
- `GET /flights/history` (consulta paginada de posiciones).
- `POST /correlation/rf-aircraft`, `GET /correlation/object/{id}`,
  `GET /correlation/aircraft/{icao24}`.

## 6. Migraciones

- `03721bb97a16_initial_schema.py` (esquema completo).
- `6002fa5e1497_add_unique_index_on_aircraft_positions.py` (índice de dedup).
- Probadas en base temporal (upgrade head, 21 tablas).

## 7. Algoritmos de análisis

- Correlación espacial (Haversine) + temporal (ventana configurable).
- RF: armónicos (`f_n = f_0 × n`), intermodulación (IM2/IM3/IM5/IM7).
- Estadísticas de vuelo (posiciones, duración, altitud, velocidad).

## 8. Metodología de correlación

- Distancia geodésica (Haversine), diferencia de altitud, distancia 3D
  aproximada.
- Ventana temporal configurable (`CORRELACION_VENTANA_TEMPORAL_S = 600 s`).
- Disclaimer de no causalidad en toda respuesta.

## 9. Consultas históricas

- `GET /flights/history` con filtros: icao24, session_id, begin/end, altitud,
  velocidad, paginación.

## 10. Exportaciones

- PNG: sonda CORS, recursos validados, fallos explícitos.
- CSV/JSON: calculadora RF e importación CSV robusta.
- GeoJSON/KML: exportación del mapa.

## 11. Resultados exactos de pruebas

- Frontend Vitest: **537 passed / 39 files**.
- Backend pytest (default): **730 passed, 7 deselected**.
- Backend pytest (integración): **7 passed** (puerto 8011).
- Playwright: **3 passed** (1366×768).
- Lint: 0 errores.
- Build: OK.
- `git diff --check`: sin errores.

## 12. Validación visual

- Playwright: 3 tests de humo pasando (mapa, calculadora vacía, exportación PNG).
- 1920×1080 e intermedias: no ejecutadas (limitación del entorno).

## 13. Limitaciones

- PostgreSQL no disponible para prueba de migración.
- Validación visual en 1920×1080 e intermedias pendiente.
- Playwright sólo smoke tests (no flujos completos).

## 14. Instrucciones de instalación y arranque

### Backend
```bash
cd AeroRF
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

### Frontend
```bash
cd frontend
npm install
npm run dev  # puerto 5199
```

### Variables de entorno (.env)
- `DATABASE_URL` (default: sqlite:///aerorf.db)
- `OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET` (opcional)
- `VITE_API_TARGET` (default: http://127.0.0.1:8010)

## 15. Pendientes reales

- Rehidratación segura de `activeSessions`.
- Deduplicación a nivel DB de `AircraftPosition` (índice ya agregado).
- Validación visual en 1920×1080 e intermedias.
- Generación/versionado de migración inicial (ya incluida).
- Asociación análisis/objeto GIS desde UI (implementada, validación visual pendiente).

## 16. Commits

- `298acaf` — feat: AeroRF 2.8 (dedup migration, session recovery, OpenSky retry)
- `699f9e7` — docs: fix final SHA in 2.7.3 closure report (campaña anterior)

## 17. SHA final y estado de GitHub

- Rama: `main`.
- `HEAD == origin/main == 298acaf` (tras este commit).
- Árbol limpio salvo los dos archivos locales preservados.

## 18. Validación manual del usuario

1. Inicio de la aplicación: verificar que el mapa carga y no hay errores en consola.
2. Mapa GIS: crear punto, línea, círculo, radial; verificar persistencia.
3. Vuelos y seguimiento: buscar aeronave, agregar a seguimiento, grabar sesión.
4. Consulta histórica: filtrar por ICAO24, fechas, altitud.
5. Reconstrucción de trayectorias: visualizar trayectoria, usar control temporal.
6. Comparación: comparar dos trayectorias.
7. Correlación RF-Aeronáutica: seleccionar aeronave, ver distancias a objetos RF.
8. Análisis: ejecutar correlación con ventana temporal.
9. Informes: generar informe CSV/JSON.
10. Exportaciones: exportar mapa PNG, verificar iconos y atribución.
11. Recuperación de sesiones: reiniciar backend, verificar que las sesiones se marcan como error.
12. Responsive y visualización: probar en 1366×768 y 1920×1080.
