# AeroRF — Estrategia de migraciones de base de datos

## 1. Estado actual

- AeroRF usa SQLAlchemy con `Base.metadata.create_all()` en `init_db()`.
  Las tablas nuevas se crean automáticamente al arrancar; las existentes no
  se modifican.
- No hay Alembic configurado (dependencia opcional, comentada en
  `requirements.txt`).
- Compatibilidad SQLite y PostgreSQL mantenida mediante tipos estándar.

## 2. Política

- Las migraciones deben ser **aditivas y reversibles** cuando sea posible.
- No se ejecutan migraciones destructivas ni se modifican bases reales durante
  la campaña.
- Toda modificación de esquema se prepara como código + migración, sin alterar
  datos existentes.
- La preservación histórica es prioritaria: `expedientes`, `eventos_rf`,
  `mediciones`, `registros_espectrales` y todos los objetos GIS no se tocan.

## 3. Tablas principales

- Legacy SIARI: `expedientes`, `mediciones`, `eventos_rf`,
  `registros_espectrales`.
- AeroRF GIS: `map_objects`, `layers`, `rf_sources`, `antennas`,
  `reference_points`, `rf_events`, `measurements`, `object_notes`,
  `object_history`, `annotations`.
- Vuelos: `flights`, `aircraft_tracks`, `flight_sessions`,
  `aircraft_positions`, `flight_selections`.
- AeroRF 2.6: `analisis_rf` (nueva, creada vía `create_all`).

## 4. Preparación de Alembic (futuro)

1. Instalar `alembic` y `psycopg[binary]` (opcional).
2. `alembic init alembic` en la raíz.
3. Configurar `alembic.ini` con `sqlalchemy.url` desde `DATABASE_URL`.
4. En `env.py`, importar `app.models` para poblar `Base.metadata`.
5. Generar migración inicial con `alembic revision --autogenerate -m "initial"`.
6. Revisar manualmente la migración antes de aplicarla.
7. Aplicar con `alembic upgrade head` en un entorno de prueba primero.

## 5. Consideraciones SQLite ↔ PostgreSQL

- Evitar tipos específicos de un motor (usar `String`, `Float`, `DateTime`,
  `Text`, `Integer`, `Boolean`).
- Las claves foráneas se declaran con `ForeignKey`; las políticas `ON DELETE`
  se revisan antes de agregarlas.
- Los índices se crean con `Index` explícito para ambos motores.
- Los backups automáticos (`respaldos/`) son específicos de SQLite; en
  PostgreSQL se confía en `pg_dump`.

## 6. Pendientes

- Integrar Alembic al flujo de despliegue.
- Generar y versionar la migración inicial.
- Agregar constraints de unicidad donde corresponda (p. ej.
  `aircraft_positions`).
- Documentar el procedimiento de rollback.
