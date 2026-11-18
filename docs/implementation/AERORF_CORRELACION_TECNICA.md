# AeroRF — Correlación técnica

## 1. Principio

AeroRF **no afirma causalidad**. La correlación informa proximidad espacial
y, cuando hay fecha de observación, proximidad temporal dentro de una ventana
configurable. Toda respuesta lleva un `disclaimer` que viaja con los datos.

## 2. Endpoints

- `POST /correlation/rf-aircraft` — aeronaves cerca de un objeto RF, bandeadas
  por distancia (5/10/20/50 nm por defecto).
- `GET /correlation/object/{id}` — informe completo de un objeto, usando
  estados en vivo (caja alrededor del objeto, no estado global).
- `GET /correlation/aircraft/{icao24}` — objetos RF cerca de una aeronave,
  con posición resuelta por grabación propia → caché de seguimiento →
  estado en vivo.

## 3. Correlación espacial vs. temporal

- Si el objeto tiene `observed_at`, la comparación es **espacial y temporal**:
  sólo los estados dentro de `CORRELACION_VENTANA_TEMPORAL_S` cuentan; los que
  caen en el radio pero fuera de la ventana se reportan en `fuera_de_ventana`.
  Cada coincidencia declara `delta_t_s`.
- Sin fecha, la comparación es **espacial** y la respuesta se declara
  `espacial` (sin `delta_t_s` significativo).

## 4. Datos de aeronaves

- Estados en vivo vía OpenSky (`get_states_in_box`), con caché y backoff.
- Posición de aeronave resuelta en cascada: grabación propia → caché de
  seguimiento → estado en vivo.
- Trayectorias históricas consultables vía `/flights/{icao24}/track`, con
  proveniencia (`historical`/`live`) y conteo por proveniencia.

## 5. Limitaciones documentadas

- ADS-B no lleva datos de emisión; la distancia geográfica entre una aeronave
  y un evento RF no dice cuál causó el otro.
- Sin `observed_at` no hay comparación temporal: se informa sólo espacial.
- Sin datos históricos, no se puede analizar trayectoria completa.
- No se inventan probabilidades de interferencia.

## 6. Frontend

- `FlightPanel.vue` muestra distancias aeronave → objetos RF
  (`loadAircraftDistances`) con el disclaimer.
- `flights.js` (store) gestiona la carga y el estado.
- El historial de análisis RF (calculadora) es independiente y no afirma
  causalidad.
