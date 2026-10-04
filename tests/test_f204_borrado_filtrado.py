"""
tests/test_f204_borrado_filtrado.py
───────────────────────────────────
F2-04: `clear_layer` borraba todo de un saque.

El `DELETE` masivo iba filtrado sólo por `layer_id`: no miraba `locked` ni
`expediente_id`, y los `ON DELETE CASCADE` de `ObjectNote`, `ObjectHistory`
y `Annotation` se llevaban por delante notas e historial de cada objeto
borrado. `delete_object`, que sí bloquea expedientes e hijos, **no**
chequeaba el candado: un objeto cerrado se podía borrar sin más.

Decisión del operador en esta fase: **borrado físico con los filtros** (no
baja lógica con `deleted_at`). Lo libre se borra; lo protegido no se toca.

Y hay un segundo efecto, en la misma ruta: `DELETE /map/layers/{id}` borra
la capa **después** de limpiarla, y `Layer.objects` no tiene `cascade`, así
que SQLAlchemy pondría `layer_id = NULL` en los objetos que sobrevivieron
al limpiado y los dejaría huérfanos. Por eso, si después de limpiar queda
algo, la capa **no se borra** y la ruta responde 409 con el detalle.
"""

from __future__ import annotations

import pytest

from app.models.expediente import Expediente
from app.models.map_object import MapObject

#: El prefijo real: `main.py` monta los routers con `settings.api_prefix`.
_API = "/api/v1"


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def expediente(db):
    exp = Expediente(numero_expediente="E-F204", freq_mhz=118.3, aeropuerto="EZE")
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def _capa(client, nombre: str) -> int:
    r = client.post(
        f"{_API}/map/layers",
        json={"key": f"capa_{nombre}", "name": f"Capa {nombre}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _crear(client, layer_id: int, nombre: str, **extra) -> dict:
    cuerpo = {
        "type": "point",
        "name": nombre,
        "latitude": -34.6,
        "longitude": -58.4,
        "layer_id": layer_id,
    }
    cuerpo.update(extra)
    r = client.post(f"{_API}/map/objects", json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


def _ids_de_capas(client) -> set[int]:
    r = client.get(f"{_API}/map/layers")
    assert r.status_code == 200, r.text
    return {c["id"] for c in r.json()["layers"]}


def _en_espanol(texto: str) -> bool:
    """Sin ningún marcador de error en inglés (regla del proyecto)."""
    bajo = texto.lower()
    return not any(
        marca in bajo
        for marca in ("cannot", "pass cascade", "not found", "must be", "layer ")
    )


# ─── El limpiado masivo ──────────────────────────────────────────────────────

def test_clear_borra_lo_libre_y_conserva_lo_protegido(client, expediente):
    capa = _capa(client, "mixta")
    libre = _crear(client, capa, "Libre")
    bloqueado = _crear(client, capa, "Cerrado", locked=True)
    vinculado = _crear(client, capa, "Del expediente",
                       expediente_id=expediente.id)

    r = client.delete(f"{_API}/map/layers/{capa}?clear=true")
    assert r.status_code == 409, r.text
    detalle = r.json()["detail"]
    assert _en_espanol(detalle), detalle
    # El criterio de la auditoría: el protegido sigue de pie.
    assert client.get(f"{_API}/map/objects/{bloqueado['id']}").status_code == 200
    assert client.get(f"{_API}/map/objects/{vinculado['id']}").status_code == 200
    # Y lo libre sí se fue (no es all-or-nothing: era la opción elegida).
    assert client.get(f"{_API}/map/objects/{libre['id']}").status_code == 404
    # La capa no se borra con protegidos adentro: los huérfanos quedarían
    # con `layer_id = NULL`.
    assert capa in _ids_de_capas(client)


def test_clear_con_todo_libre_borra_objetos_y_capa(client):
    capa = _capa(client, "limpia")
    obj = _crear(client, capa, "Libre")

    r = client.delete(f"{_API}/map/layers/{capa}?clear=true")
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == capa

    assert client.get(f"{_API}/map/objects/{obj['id']}").status_code == 404
    assert capa not in _ids_de_capas(client)


def test_clear_no_divide_un_grupo(client, db):
    """Un hijo no se va solo: si sobrevive, su padre también.

    `parent_id` no lo escribe ninguna ruta hoy (sólo existen la columna y
    el bloqueo de `delete_object`), pero si alguna fila lo trae, borrar el
    padre dejaría al hijo con `parent_id = NULL` por el `ON DELETE SET NULL`.
    """
    capa = _capa(client, "grupo")
    padre = _crear(client, capa, "Padre")
    hijo = _crear(client, capa, "Hijo")
    fila = db.get(MapObject, hijo["id"])
    fila.parent_id = padre["id"]
    db.commit()

    r = client.delete(f"{_API}/map/layers/{capa}?clear=true")
    assert r.status_code == 409, r.text

    assert client.get(f"{_API}/map/objects/{padre['id']}").status_code == 200
    assert client.get(f"{_API}/map/objects/{hijo['id']}").status_code == 200
    assert capa in _ids_de_capas(client)


# ─── El borrado individual ───────────────────────────────────────────────────

def test_borrado_individual_respeta_el_candado(client):
    capa = _capa(client, "cerrado")
    obj = _crear(client, capa, "Cerrado", locked=True)

    r = client.delete(f"{_API}/map/objects/{obj['id']}")
    assert r.status_code == 400, r.text
    detalle = r.json()["detail"]
    assert "bloqueado" in detalle.lower(), detalle
    assert _en_espanol(detalle), detalle
    assert client.get(f"{_API}/map/objects/{obj['id']}").status_code == 200

    # `cascade=true` sigue siendo la fuerza explícita, objeto por objeto.
    r2 = client.delete(f"{_API}/map/objects/{obj['id']}?cascade=true")
    assert r2.status_code == 200, r2.text
    assert client.get(f"{_API}/map/objects/{obj['id']}").status_code == 404


def test_borrado_individual_sigue_bloqueando_por_expediente(client, expediente):
    capa = _capa(client, "vinculado")
    obj = _crear(client, capa, "Del expediente", expediente_id=expediente.id)

    r = client.delete(f"{_API}/map/objects/{obj['id']}")
    assert r.status_code == 400, r.text
    detalle = r.json()["detail"]
    assert str(expediente.id) in detalle
    assert _en_espanol(detalle), detalle
    assert client.get(f"{_API}/map/objects/{obj['id']}").status_code == 200


def test_clear_sin_cascada_no_borra_nada(client, db):
    """El precontrato de `clear_layer` no cambia: sin cascade, ni una fila."""
    from app.services import map_service as svc

    capa = _capa(client, "sin_cascade")
    obj = _crear(client, capa, "Libre")

    with pytest.raises(svc.MapServiceError):
        svc.clear_layer(db, capa)

    assert client.get(f"{_API}/map/objects/{obj['id']}").status_code == 200
