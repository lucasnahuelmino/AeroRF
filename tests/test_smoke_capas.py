"""
tests/test_smoke_capas.py
─────────────────────────
El chequeo de capas del smoke y los defaults que se siembran tienen que
ser el mismo número.

El 26/09 entraron `lines` y `polygons` en `DEFAULT_LAYERS` (15 → 17) y
`smoke_e2e.py` siguió esperando 15: desde entonces el smoke reporta
77/78 **en base limpia**, o sea que su único rojo era una expectativa
vieja y no una regresión (RETOMAR lo anotó como tal). El smoke es un
script HTTP puro — sin imports de `app`, por diseño: habla con el
servidor como lo haría el frente — así que no puede comparar contra el
origen él solo. La guarda vive acá: lee el número del script y lo pisa
con `len(DEFAULT_LAYERS)`.

Si alguien agrega una capa por defecto, esta guarda queda roja hasta
que el smoke diga el número nuevo; si se pone roja **sin** que los
defaults se hayan tocado, es el smoke el que se movió solo.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.constants import DEFAULT_LAYERS

_RAIZ = Path(__file__).resolve().parents[1]
_SMOKE = _RAIZ / "tests" / "smoke_e2e.py"

#: `check("17 default layers", s == 200 and layers.get("count") == 17, ...)`
_PATRON = re.compile(
    r'check\("(\d+) default layers",\s*'
    r's == 200 and layers\.get\("count"\) == (\d+)'
)


def _chequeo() -> tuple[str, str]:
    """(etiqueta, valor) del chequeo de capas, tal como está escrito."""
    fuente = _SMOKE.read_text(encoding="utf-8")
    coincidencia = _PATRON.search(fuente)
    if coincidencia is None:
        return ("", "")
    return coincidencia.group(1), coincidencia.group(2)


def test_el_chequeo_de_capas_existe_y_se_puede_leer():
    """El smoke sigue teniendo el chequeo, con la forma que la guarda espera."""
    etiqueta, valor = _chequeo()
    assert etiqueta and valor, (
        "el chequeo de capas de smoke_e2e.py no se encontró con la forma "
        'esperada: check("N default layers", s == 200 and '
        'layers.get("count") == N, ...)'
    )


def test_el_valor_del_chequeo_son_los_defaults_que_se_siembran():
    etiqueta, valor = _chequeo()
    reales = len(DEFAULT_LAYERS)
    assert valor == str(reales), (
        f"smoke_e2e espera {valor} capas y DEFAULT_LAYERS siembra {reales}: "
        "en base limpia el smoke falla con esa diferencia"
    )


def test_la_etiqueta_dice_el_mismo_numero_que_el_valor():
    etiqueta, valor = _chequeo()
    assert etiqueta == valor, (
        f"la etiqueta dice «{etiqueta} default layers» y el valor chequea "
        f"== {valor}: el rótulo del informe quedó desfasado del chequeo"
    )
