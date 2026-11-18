# AeroRF — Hardening operativo

## 1. Resumen ejecutivo

Campaña de robustez y confiabilidad completada. Se implementó deduplicación
persistente de posiciones de aeronaves, gestión de `SESSION_ERROR`, recuperación
de sesiones interrumpidas, política completa de retry/backoff para OpenSky
(incluyendo 429 con `Retry-After` y jitter), y validación visual con Playwright
(3 tests pasando en 1366×768). Frontend 537/537, backend 730/7, build y lint
limpios.

## 2. Problemas encontrados y soluciones

- **Deduplicación:** `record_sample` ya deduplicaba en código; se agregó índice
  único parcial en `AircraftPosition` (session_id, icao24, timestamp) con
  condición `timestamp IS NOT NULL`, compatible SQLite/PostgreSQL.
- **Sesiones interrumpidas:** `recover_interrupted_sessions` marca como `error`
  las sesiones en `recording` al arrancar, conservando posiciones.
- **OpenSky 429:** se respeta `Retry-After` (trip del backoff) y se reintenta
  sólo si la espera es ≤ 5 s; si no, se propaga el `RateLimitedError`.
- **Retry 5xx/timeout/red:** 3 intentos con backoff corto (0.1–1.0 s) + jitter.
- **Validación visual:** Playwright instalado con Chromium; 3 tests de humo
  (mapa, calculadora vacía, exportación PNG) pasando.

## 3. Deduplicación y estrategia de índices

- Índice único parcial: `uq_positions_session_icao_ts` sobre
  `(session_id, icao24, timestamp)` con `WHERE timestamp IS NOT NULL`.
- Manejo de `IntegrityError` en `record_sample` (retorna el existente).
- No se eliminan duplicados históricos automáticamente.

## 4. Recuperación de sesiones

- `recover_interrupted_sessions(db)` ejecutado en `lifespan` (best-effort).
- Rehidratación del frontend sólo cuando `activeSessions` está vacío.
- Estados: `recording` → `stopped` (normal) o `error` (interrupción).

## 5. Política de reintentos OpenSky

- 429: respeta `Retry-After`, reintenta sólo si ≤ 5 s.
- 5xx/timeout/red: 3 intentos, backoff 0.1–1.0 s + jitter.
- 401: un replay tras invalidar token.
- 403/400/404: sin reintento (errores definitivos).
- Límite máximo de 3 intentos.

## 6. Pruebas Playwright

- 3 tests de humo pasando en 1366×768:
  - Mapa carga y muestra `.leaflet-container`.
  - Calculadora RF carga vacía con mensaje guía.
  - Exportación PNG disponible.
- Capturas no generadas (entorno headless).

## 7. Resultados exactos de pruebas

- Frontend Vitest: **537 passed / 39 files**.
- Backend pytest (default): **730 passed, 7 deselected**.
- Backend pytest (integración, puerto 8011): **7 passed**.
- Lint: 0 errores.
- Build: OK.
- `git diff --check`: sin errores.

## 8. Limitaciones del entorno

- Validación visual en 1920×1080 e intermedias no ejecutada (sólo 1366×768).
- PostgreSQL no disponible para prueba de migración.
- Puerto 8010 ocupado (se usó 8011).

## 9. Compatibilidad de bases de datos

- SQLite: probado (índice parcial, migración Alembic).
- PostgreSQL: compatible por construcción (tipos estándar, `postgresql_where`).

## 10. Pendientes reales

- Rehidratación segura de `activeSessions` (rediseño pendiente).
- Deduplicación a nivel DB de `AircraftPosition` (índice ya agregado; migración Alembic pendiente).
- Validación visual en 1920×1080 e intermedias.
- Generación/versionado de migración inicial con el nuevo índice.

## 11. Commits generados

- `ec3984d` — feat: hardening operativo (dedup persistente, OpenSky retry/backoff, Playwright)

## 12. Estado final de sincronización con GitHub

- Rama: `main`.
- `HEAD == origin/main == ec3984d` (tras este commit).
- Árbol limpio salvo los dos archivos locales preservados.

## 13. Confirmación de preservación de datos

- Bases de datos, historiales, backups y archivos locales preservados.
- No se modificaron bases reales.
- `AERORF_2.6_ESTABILIZACION.md` y `docs/archive/implementacion.md` sin trackear.
