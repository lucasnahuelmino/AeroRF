"""
tests/test_f206_geometria_update.py
───────────────────────────────────
F2-06: `update_object` no valida geometría; `create_object` sí.

El docstring de `gjs.validate_geometry` promete ser «Called from the
create and update paths», pero sólo la alta la llama. Un PUT con una
geometría rota se almacenaba tal cual: el objeto seguía existiendo, pero
`object_to_leaflet` lo marcaba «sin geometría derivable» y desaparecía
del mapa sin decir por qué. El comentario de `create_object` avisa del
riesgo desde el origen: «one bad ring used to be stored happily and then
took down the whole listing endpoint with a 500».

La guarda mide las dos puertas con el mismo criterio: o rechaza con
mensaje en español, o no escribe nada. Y con geometría válida, sí pasa.
"""

from __future__ import annotations

import pytest

_API = "/api/v1"

#: Lo que jamás debe llegar al operador en un rechazo de geometría.
MARCAS_EN_INGLES = (
    "geometry error",
    "internal server error",
    "expected",
    "must be",
    "not a valid",
    "invalid literal",
)

#: Tres posiciones y sin cerrar: el anillo no se repite al final.
POLIGONO_ABIERTO = {
    "type": "Polygon",
    "coordinates": [[[-58.5, -34.7], [-58.3, -34.7], [-58.3, -34.5]]],
}


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _detalle(respuesta) -> str:
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


def _crear(client) -> int:
    r = client.post(
        f"{_API}/map/objects",
        json={
            "type": "polygon",
            "name": "Polígono de prueba",
            "latitude": -34.6,
            "longitude": -58.4,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ─── La puerta que faltaba ───────────────────────────────────────────────────

def test_update_con_geometria_malformada_no_se_almacena(client, db):
    from app.models.map_object import MapObject

    oid = _crear(client)

    r = client.put(
        f"{_API}/map/objects/{oid}", json={"geometry": POLIGONO_ABIERTO}
    )
    assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"
    assert _en_espanol(_detalle(r)), _detalle(r)

    # Y sobre todo: no se escribió. La columna sigue vacía — el `geometry`
    # que devuelve GET es un Point derivado de lat/lon, no el registro.
    db.expire_all()
    fila = db.get(MapObject, oid)
    assert fila.geometry is None, fila.geometry
    guardado = client.get(f"{_API}/map/objects/{oid}").json()
    assert guardado.get("geometry") != POLIGONO_ABIERTO, guardado.get("geometry")


def test_update_con_geometria_valida_si_pasa(client):
    """Si la geometría está bien, el update sigue funcionando igual."""
    oid = _crear(client)
    valido = {
        "type": "LineString",
        "coordinates": [[-58.5, -34.7], [-58.3, -34.5]],
    }

    r = client.put(f"{_API}/map/objects/{oid}", json={"geometry": valido})
    assert r.status_code == 200, r.text

    guardado = client.get(f"{_API}/map/objects/{oid}").json()
    assert guardado.get("geometry") == valido, guardado.get("geometry")


def test_create_con_geometria_malformada_sigue_rechazada(client):
    """La puerta del alta ya existía: queda como guarda de la paridad."""
    r = client.post(
        f"{_API}/map/objects",
        json={
            "type": "polygon",
            "name": "Roto",
            "latitude": -34.6,
            "longitude": -58.4,
            "geometry": POLIGONO_ABIERTO,
        },
    )
    assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"
    assert _en_espanol(_detalle(r)), _detalle(r)
