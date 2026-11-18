# AeroRF — Cierre técnico (Campaña integral)

## 1. Funcionalidades implementadas

- **Retirada funcional de Expedientes (AeroRF 2.6 B1):** historial propio de
  análisis RF (`analisis_rf`), inspector sin asociación, archivos huérfanos
  eliminados, API legado conservado.
- **Importación CSV robusta (B2):** parser completo en `rfFiles.js`, revisión
  antes de confirmar.
- **Exportación PNG confiable (B3):** sonda CORS, recursos validados, fallos
  explícitos, atribución conservada.
- **Calculadora vacía al arrancar (B4):** mensaje guía, «Cargar ejemplo» con
  «DATOS DE EJEMPLO», sin probabilidades.
- **Documentación y nomenclatura (B5):** `MANUAL.md` reescrito, `siari-frontend`
  → `aerorf-frontend`, claims de probabilidad removidos del OpenAPI.
- **Campaña integral (fases A–G):**
  - Fase A: cierre ordenado del cliente HTTP de OpenSky en `lifespan`.
  - Fase B: reconexión WebSocket con backoff exponencial acotado; corrección de
    llamada duplicada a OpenSky en `/flights/all`.
  - Fase C: exportación PNG ya consolidada (B3).
  - Fase D: correlación espacial/temporal ya implementada (ver documento
    dedicado).
  - Fase E: calculadora consolidada (B4).
  - Fase F: estrategia de migraciones documentada (ver documento dedicado).
  - Fase G: referencias visuales de Expedientes eliminadas; documentación
    actualizada.

## 2. Archivos y módulos principales modificados

- Backend: `app/api/routes/flights.py`, `app/main.py`,
  `app/services/opensky_service.py` (sin cambios de lógica en esta campaña,
  excepto uso existente), `app/models/rf_models.py`, `app/models/schemas.py`,
  `app/api/routes/rf.py`, `app/api/routes/rf_analisis.py`, `app/models/analisis_rf.py`.
- Frontend: `frontend/src/stores/flights.js` (backoff WS),
  `frontend/src/map/exportMap.js`, `frontend/src/lib/rfFiles.js`,
  `frontend/src/views/CalculadoraRFView.vue`, `frontend/src/components/gis/InspectorPanel.vue`.
- Configuración: `frontend/vite.config.js` (`testTimeout`), `frontend/package.json`,
  `frontend/package-lock.json`.
- Documentación: `MANUAL.md`, `README.md`, `RETOMAR.md`,
  `AERORF_ARCHITECTURE.md`, `AERORF_CHANGELOG.md`.

## 3. Tests ejecutados y resultados reales

- Frontend: `npx vitest run` → **537 passed / 39 files**.
- Backend: `pytest -m "not integration"` → **730 passed, 7 deselected**.
- Lint (`npm run lint`, src/): **0 errores**.
- Build (`npm run build`): **OK** (CalculadoraRFView 30.82 KB).
- `git diff --check`: sin errores.

## 4. Tests no ejecutados y motivos

- `pytest -m integration` (7 tests WebSocket): no ejecutados porque el puerto 8010
  está ocupado por otra aplicación en esta máquina (ALMATE Nexo Stock) y el
  backend de AeroRF no estaba levantado. Los tests se saltan automáticamente.
  La lógica queda cubierta por los 730 tests in-process.
- Validación visual en navegador real (1366×768, 1920×1080, intermedios): no
  ejecutada; no se dispone de Playwright ni de la herramienta de navegador del
  harness en esta corrida. Cubierta parcialmente por `export-map.spec.js` (5).

## 5. Errores corregidos

- Llamada duplicada a OpenSky en `/flights/all`.
- Reconexión WebSocket fija (5 s) → backoff exponencial acotado (1 s → 30 s).
- Cierre ordenado del cliente HTTP de OpenSky en `lifespan`.
- Claims de probabilidad en OpenAPI (`RFMatch.score`, `EventoRF.score_probabilidad`).
- Calculadora con datos precargados → arranque vacío con guía.
- Dependencia de Expedientes en calculadora e inspector.

## 6. Pendientes reales

- Validación visual en navegador real y test Playwright del PNG.
- Tests de integración WebSocket (requieren backend en 8010 libre).
- Retry/backoff sobre 5xx/timeout/red en `opensky_service._request` (hoy un solo
  intento para esos casos; sólo 401 se repite). Pendiente por riesgo de romper
  tests de conteo de llamadas.
- Rehidratación de `activeSessions` tras recarga del frontend.
- Deduplicación a nivel DB de `AircraftPosition` (hoy guardada en código).
- Uso del estado `SESSION_ERROR`.
- Asociación de análisis a objeto GIS desde la UI de la calculadora.
- Alembic: esquema preparado en documentación, sin migración ejecutada.

## 7. Estado de la base de datos y preservación histórica

- Tablas históricas (`expedientes`, `eventos_rf`, `mediciones`, …) conservadas.
- Nueva tabla `analisis_rf` creada vía `create_all` (aditiva, sin migración
  destructiva, sin pérdida de datos).
- Backups automáticos en `respaldos/` (10 más recientes) intactos.
- Compatibilidad SQLite/PostgreSQL mantenida (tipos estándar SQLAlchemy).

## 8. SHA del commit final

`660838ad5f67d7644640d34cc5f6784a393b8097`.

## 9. Estado de `main` y sincronización con `origin/main`

- Rama: `main`.
- `HEAD == origin/main == 660838a` tras la publicación de esta campaña.
- Publicado en `origin/main` (commit `660838a`).
