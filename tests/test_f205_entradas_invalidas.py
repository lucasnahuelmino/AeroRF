"""
tests/test_f205_entradas_invalidas.py
─────────────────────────────────────
F2-05: entradas inválidas que estallan en 500.

Las rutas con `body: dict` (y las que validan dentro del handler) no
llegan al middleware de validación de FastAPI: el `ValidationError` de
Pydantic se lanza **dentro** de la vista, nada lo atrapa, y el cliente se
queda con un 500 «Internal Server Error». Casos de la auditoría:

* `visible: null` en el alta — la columna es `Boolean NOT NULL`;
* `layer_id` inexistente — violación de FK al insertar;
* `kind` inválido — el validador de `RFSourcePayload`.

Y el ojo que anota la auditoría: si se arregla pasando a Pydantic, el 500
se convierte en **422 de FastAPI, en inglés** («Input should be a valid
boolean…»), que `describeError` del frontend pinta tal cual. Así que el
traductor va **en el mismo commit**: 422 con `msg` en español, nunca 500.
"""

from __future__ import annotations

import pytest

#: El prefijo real: `main.py` monta los routers con `settings.api_prefix`.
_API = "/api/v1"

#: Lo que jamás debe llegar al operador (ni en `msg`, ni en el cuerpo).
MARCAS_EN_INGLES = (
    "input should be",
    "value is not a valid",
    "internal server error",
    "unable to parse",
    "not a valid",
    "must be one of",
    "must be 'single'",
    "string_type",
    "int_parsing",
    "bool_parsing",
    "float_parsing",
    "greater_than",
    "less_than",
    "missing",
    "value_error",
)


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _detalle(respuesta) -> str:
    """El texto que el operador ve: `describeError` une `loc: msg`."""
    data = respuesta.json()
    detalle = data.get("detail") if isinstance(data, dict) else None
    if isinstance(detalle, list):
        return " | ".join(
            f"{item.get('loc')} {item.get('msg')}"
            for item in detalle
            if isinstance(item, dict)
        )
    return str(detalle)


def _en_espanol(texto: str) -> bool:
    bajo = texto.lower()
    return not any(marca in bajo for marca in MARCAS_EN_INGLES)


def _crear_punto(client, **extra):
    cuerpo = {
        "type": "point",
        "name": "Punto de prueba",
        "latitude": -34.6,
        "longitude": -58.4,
    }
    cuerpo.update(extra)
    return client.post(f"{_API}/map/objects", json=cuerpo)


# ─── Los tres 500 de la auditoría ────────────────────────────────────────────

def test_visible_nulo_no_es_500(client):
    r = _crear_punto(client, visible=None)
    assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"
    assert _en_espanol(_detalle(r)), _detalle(r)


def test_layer_inexistente_no_es_500(client):
    r = _crear_punto(client, layer_id=999999)
    assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"
    assert _en_espanol(_detalle(r)), _detalle(r)
    # El mensaje tiene que decir cuál falta: genérico «violó una
    # restricción» no le sirve a nadie.
    assert "999999" in _detalle(r), _detalle(r)


def test_expediente_inexistente_no_es_500(client):
    r = _crear_punto(client, expediente_id=999999)
    assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"
    assert _en_espanol(_detalle(r)), _detalle(r)
    assert "expediente" in _detalle(r).lower(), _detalle(r)
    assert "999999" in _detalle(r), _detalle(r)


def test_kind_invalido_no_es_500(client):
    r = client.post(
        f"{_API}/rf/sources",
        json={"name": "Fuente rara", "latitude": -34.6, "longitude": -58.4,
              "kind": "Basura", "frequency_mhz": 98.1},
    )
    assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"
    assert _en_espanol(_detalle(r)), _detalle(r)


# ─── Las otras vías al mismo hueco ───────────────────────────────────────────

def test_visible_nulo_en_update_no_es_500(client):
    creado = _crear_punto(client)
    assert creado.status_code == 201, creado.text
    oid = creado.json()["id"]

    r = client.put(f"{_API}/map/objects/{oid}", json={"visible": None})
    assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"
    assert _en_espanol(_detalle(r)), _detalle(r)
    # Tiene que nombrar el campo: «violó una restricción» no dice nada.
    assert "visible" in _detalle(r).lower(), _detalle(r)
    # Y el objeto sigue como estaba.
    assert client.get(f"{_API}/map/objects/{oid}").json()["visible"] is True


def test_type_invalido_no_es_500(client):
    r = client.post(
        f"{_API}/map/objects",
        json={"type": "banana", "latitude": -34.6, "longitude": -58.4},
    )
    assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"
    assert _en_espanol(_detalle(r)), _detalle(r)


def test_latitud_fuera_de_rango_no_es_500(client):
    r = _crear_punto(client, latitude=999)
    assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"
    assert _en_espanol(_detalle(r)), _detalle(r)


def test_capa_con_opacidad_no_numerica_no_es_500(client):
    """`create_layer` hace `float(payload["opacity"])` con el cuerpo crudo."""
    r = client.post(
        f"{_API}/map/layers",
        json={"key": "capa_opaca", "name": "Capa opaca", "opacity": "media"},
    )
    assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"
    assert _en_espanol(_detalle(r)), _detalle(r)
    assert "opacity" in _detalle(r).lower(), _detalle(r)


def test_correlacion_con_id_no_numerico_no_es_500(client):
    """`rf-aircraft` hace `int(object_id)` con el valor crudo del cuerpo."""
    r = client.post(
        f"{_API}/correlation/rf-aircraft", json={"object_id": "no-numero"}
    )
    assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"
    assert _en_espanol(_detalle(r)), _detalle(r)
    assert "object_id" in _detalle(r), _detalle(r)


# ─── Guardas: lo válido sigue funcionando ────────────────────────────────────

def test_entrada_valida_sigue_creando(client):
    r = _crear_punto(client, visible=True)
    assert r.status_code == 201, r.text
    assert r.json()["visible"] is True


def test_el_422_de_un_campo_con_ocasion_sigue_siendo_422(client):
    """El traductor no cambia el contrato de status: 422 sigue siendo 422."""
    r = client.post(
        f"{_API}/map/objects",
        json={"type": "point", "latitude": "no-numero", "longitude": -58.4},
    )
    assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"
    assert _en_espanol(_detalle(r)), _detalle(r)
