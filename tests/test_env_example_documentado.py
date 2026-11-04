"""
tests/test_env_example_documentado.py
──────────────────────────────────────
Toda variable que `Settings` **lee de la variable de entorno** tiene que
estar escrita en `.env.example`: quien copia el ejemplo para armar su
`.env` no puede enterarse de una opción existente sólo por leer el
código.

El defecto que la destapó: `CACHE_TTL_TRACKS_LIVE_S` nació en 0.30.2
(con default 30, que la ruta `fresh=true` usa para el caché corto de
tracks) y quedó sin documentar — la auditoría lo anotó como «omisión
del 0.30.2».

La guarda es **por campo, no por la lista concreta**: si mañana aparece
un settings nuevo, la prueba nueva se pone roja hasta que el ejemplo lo
diga, que era exactamente cómo falló éste.

Dos cosas que la comparación NO cubre, y por qué:

* `max_tracked_aircraft` no es una omisión: es default plano
  («hard cap from the spec, not configurable») y una línea en el
  ejemplo mentiría — no se leería nunca. Los campos sin
  `default_factory` quedan fuera del barrido justamente por eso: en
  este archivo, `default_factory` **es** la señal de que lee env
  (`_env`, `_env_int`, `_env_bool`, `_env_float`), y el nombre env es
  el campo en mayúsculas.
* `VITE_PORT` está en el ejemplo y no en `Settings`: lo lee el frente
  y `start.bat`. Por eso la comparación va de `Settings` al ejemplo y
  no al revés.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from app.core.config import Settings

_RAIZ = Path(__file__).resolve().parents[1]

#: Campos que Settings lee de la variable de entorno: en este dataclass,
#: el `default_factory` es la señal (los planos, como el tope de
#: aeronaves de la spec, no se leen de env).
_CAMPOS_DE_ENV = [
    f.name
    for f in dataclasses.fields(Settings)
    if f.default_factory is not dataclasses.MISSING
]


def _claves_del_ejemplo() -> set[str]:
    """Todas las `CLAVE=` que aparecen en `.env.example`, activas o comentadas."""
    fuente = (_RAIZ / ".env.example").read_text(encoding="utf-8")
    return set(re.findall(r"#?\s*([A-Z][A-Z0-9_]*)=", fuente))


def test_hay_campos_de_env_para_barrer():
    """Si el filtro se rompiera (Settings pasa a leer todo de otra forma), que se note."""
    assert _CAMPOS_DE_ENV, (
        "ningún campo de Settings tiene default_factory: el criterio de "
        "esta guarda dejó de describir la realidad"
    )


@pytest.mark.parametrize("campo", _CAMPOS_DE_ENV)
def test_la_variable_esta_en_el_ejemplo(campo: str):
    assert campo.upper() in _claves_del_ejemplo(), (
        f"Settings lee `{campo}` de la variable de entorno y .env.example "
        "no la documenta: quien copie el ejemplo se queda sin saber que existe"
    )
