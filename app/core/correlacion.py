"""
app/core/correlacion.py
───────────────────────
Comparación temporal de la correlación aeronave ↔ evento RF.

La auditoría (P1) encontró que la correlación se anunciaba «espacial y
temporal» pero comparaba el evento con las posiciones **actuales**: un
evento de hace tres días «correlizaba» con el tráfico de hoy. Acá vive
lo que significa «temporal», en un solo lugar para las dos rutas que
correlizan (`routes/correlation.py` y `services/flight_service.py`):

* ``CORRELACION_VENTANA_TEMPORAL_S`` — ventana alrededor de
  ``MapObject.observed_at``; dentro cuenta, fuera se reporta en
  ``fuera_de_ventana``. Sin ``observed_at`` no hay nada que comparar y
  la respuesta se declara ``espacial``.
* ``delta_t_s`` — segundos entre la fecha de observación y el último
  contacto de la aeronave; ``None`` cuando falta dato (no se puede
  afirmar contemporaneidad sin hora).
* ``caja_alrededor`` — caja WGS84 que contiene el círculo pedido, para
  pedirle a OpenSky la caja y no el estado global.
* Los dos disclaimer que viajan en las respuestas: el del objeto
  declara cómo compara el tiempo; el de la vista por aeronave se
  declara espacial, que es lo que calcula.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import cos, radians
from typing import Optional

#: Segundos de tolerancia alrededor de `observed_at`. Un evento recién
#: observado y los estados en vivo llegan con segundos de desfase; lo
#: más viejo que esto no es contemporáneo del tráfico actual.
CORRELACION_VENTANA_TEMPORAL_S = 600

#: Viaja en cada respuesta que correliza un objeto (y en cada export).
DISCLAIMER = (
    "Correlación espacial y, cuando el evento tiene fecha de observación "
    "(observed_at), también temporal: cada coincidencia declara su "
    "delta_t_s contra esa fecha y sólo dentro de la ventana se cuenta. "
    "La cercanía entre una aeronave y un evento RF NO implica causalidad. "
    "ADS-B no registra emisiones electromagnéticas, la posición del avión "
    "no identifica la fuente de un evento, y un evento de intermodulación "
    "puede originarse a kilómetros de la aeronave observada."
)

#: La vista por aeronave lista objetos por cercanía: no compara momentos.
DISCLAIMER_AERONAVE = (
    "Correlación espacial: la lista es cercanía entre la posición usada de "
    "la aeronave y los objetos, sin comparación de momentos. La cercanía "
    "entre una aeronave y un evento RF NO implica causalidad. ADS-B no "
    "registra emisiones electromagnéticas, la posición del avión no "
    "identifica la fuente de un evento, y un evento de intermodulación "
    "puede originarse a kilómetros de la aeronave observada."
)


def epoch(dt: Optional[datetime]) -> Optional[float]:
    """Epoch de un datetime; naive se toma como UTC (convenio de la base)."""
    if dt is None:
        return None
    if isinstance(dt, (int, float)):
        return float(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def delta_t_s(
    observed_at: Optional[datetime], state: dict
) -> Optional[int]:
    """Segundos entre `observed_at` del evento y el último contacto del estado.

    Negativo = el estado es anterior al evento. ``None`` = falta la fecha
    del evento o la hora del estado: sin dato no se afirma nada.
    """
    t_obj = epoch(observed_at)
    if t_obj is None:
        return None
    t_estado = state.get("last_contact") or state.get("time_position")
    if t_estado is None:
        return None
    return int(round(float(t_estado) - t_obj))


def caja_alrededor(
    lat: float, lon: float, radio_m: float
) -> tuple[float, float, float, float]:
    """Caja ``(lat_min, lon_min, lat_max, lon_max)`` que contiene el círculo.

    Margen del 10 % y metros por grado conservadores (110 km) para que la
    caja no se quede corta en el paralelo del objeto. El área de una caja
    de 50 nm queda en ~4 sq-deg: tramo de 1 crédito de
    ``estimate_states_credits`` (área ≤ 25 sq-deg).
    """
    dlat = (radio_m * 1.1) / 110_000.0
    dlon = dlat / max(cos(radians(lat)), 0.2)
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)
