"""
tests/test_f201_candado_rf.py
──────────────────────────────
F2-01: los endpoints tipados saltean el candado y dejan escrituras parciales.

Reproducido en la auditoría y confirmado leyendo las cuatro rutas: en
`update_source`, `update_antenna`, `update_event` y `update_reference` los
campos del satélite se escriben y hacen `commit` **antes** de llamar a
`svc.update_object`, y el único que chequea el candado es `update_object`
(`map_service.py:506`). De ahí los dos síntomas:

* con la fuente bloqueada, `PUT /rf/sources/{id} {"frequency_mhz": 200}`
  devuelve 200 y cambia la frecuencia de 98.1 a 200 — pasa la evidencia
  bloqueada por una vía que el borrado individual sí protege.
* con `{"frequency_mhz": 201, "name": "otro"}` la respuesta es 400 (el
  candado manda, en `update_object`) pero la frecuencia **201 ya quedó
  guardada**: escritura parcial, con la ventana de commit abierta entre los
  dos pasos.

`update_reference` la auditoría la dejó como «no lo leída»: tiene el mismo
esqueleto (`:478` y `:489` hacen commit antes del candado de `:495`), igual
que `update_event` (`:385`, `:395` antes de `:401`) y `update_antenna`
(`:258`, `:266` antes de `:278`).

Estas pruebas leen el satélite **de la base**, no de la respuesta: así el
aserto prueba que no se persistió, y no que la serialización no lo muestre.
"""

from __future__ import annotations

import pytest

from app.models.rf import Antenna, RFEvent, RFSource, ReferencePoint

#: El prefijo real: `main.py` monta los routers con `settings.api_prefix`.
_API = "/api/v1"


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


#: Cuatro casos, uno por vista tipada: endpoint, modelo, payload de alta,
#: edit que debe rechazarse y valor que debe seguir intacto.
VISTAS = [
    (
        "fuente", "rf/sources", RFSource, "properties.rf",
        {"name": "Fuente interferente #01", "latitude": -34.61,
         "longitude": -58.40, "kind": "FM", "frequency_mhz": 98.1,
         "power_dbm": -55, "status": "Activo", "locked": True},
        {"frequency_mhz": 200.0},
        ("frequency_mhz", 98.1),
    ),
    (
        "antena", "antennas", Antenna, "properties.antenna",
        {"name": "Antena EZE", "latitude": -34.82, "longitude": -58.53,
         "kind": "Direccional", "frequency_mhz": 118.3, "azimuth_deg": 90,
         "locked": True},
        {"frequency_mhz": 130.0},
        ("frequency_mhz", 118.3),
    ),
    (
        "evento", "rf/events", RFEvent, "properties.event",
        {"name": "Evento RF 118.300", "latitude": -34.55,
         "longitude": -58.44, "frequency_mhz": 118.3, "level_dbm": -62,
         "classification": "Interferencia aeronaútica", "locked": True},
        {"frequency_mhz": 130.0},
        ("frequency_mhz", 118.3),
    ),
    (
        "referencia", "references", ReferencePoint, "properties.reference",
        {"name": "Referencia EZE", "latitude": -34.80, "longitude": -58.46,
         "kind": "NDB", "code": "EZE", "radius": 10, "radius_unit": "nm",
         "locked": True},
        {"radius": 25.0},
        ("radius", 10.0),
    ),
]


def _crear(client, endpoint, payload):
    r = client.post(f"{_API}/{endpoint}", json=payload)
    assert r.status_code == 201, f"alta falló: {r.status_code} {r.text}"
    return r.json()["id"]


def _satelite(db, modelo, object_id):
    """El satélite tal como quedó en la base, no tal como se serializa."""
    db.expire_all()
    return db.query(modelo).filter(modelo.object_id == object_id).first()


@pytest.mark.parametrize(
    "nombre, endpoint, modelo, _prop, payload, edit, intacto",
    VISTAS,
    ids=[v[0] for v in VISTAS],
)
def test_bloqueado_no_acepta_el_atributo_tipado(
    db, client, nombre, endpoint, modelo, _prop, payload, edit, intacto
):
    """Un objeto bloqueado no cambia ni si el cuerpo trae sólo campos RF."""
    object_id = _crear(client, endpoint, payload)
    campo, esperado = intacto

    r = client.put(f"{_API}/{endpoint}/{object_id}", json=edit)

    assert r.status_code == 400, (
        f"{nombre}: el candado no se aplicó, respondió {r.status_code} {r.text}"
    )
    fila = _satelite(db, modelo, object_id)
    assert getattr(fila, campo) == esperado, (
        f"{nombre}: quedó {getattr(fila, campo)!r} y debía {esperado!r}"
    )


def test_bloqueado_no_deja_escritura_parcial(db, client):
    """El repro de la auditoría: 400 por candado, pero el 201 ya estaba."""
    payload = dict(VISTAS[0][4])
    object_id = _crear(client, "rf/sources", payload)

    r = client.put(
        f"{_API}/rf/sources/{object_id}",
        json={"frequency_mhz": 201, "name": "otro"},
    )

    assert r.status_code == 400, f"esperaba 400, vino {r.status_code} {r.text}"

    fila = _satelite(db, RFSource, object_id)
    assert fila.frequency_mhz == 98.1, (
        f"escritura parcial: la frecuencia pasó a {fila.frequency_mhz!r}"
    )

    obj = client.get(f"{_API}/rf/sources/{object_id}").json()
    assert obj["name"] == "Fuente interferente #01", (
        f"escritura parcial: el nombre pasó a {obj['name']!r}"
    )


def test_desbloqueado_sigue_editandose(client):
    """Control: el candado no se volvió un muro para todo el mundo."""
    payload = {**VISTAS[0][4], "locked": False}
    object_id = _crear(client, "rf/sources", payload)

    r = client.put(f"{_API}/rf/sources/{object_id}", json={"frequency_mhz": 200.0})

    assert r.status_code == 200, f"esperaba 200, vino {r.status_code} {r.text}"


def test_bloqueado_aun_puede_desbloquearse(client):
    """La excepción del propio código: si no, el candado sería trampa."""
    object_id = _crear(client, "rf/sources", dict(VISTAS[0][4]))

    r = client.put(f"{_API}/rf/sources/{object_id}", json={"locked": False})

    assert r.status_code == 200, f"esperaba 200, vino {r.status_code} {r.text}"
    assert client.get(f"{_API}/rf/sources/{object_id}").json()["locked"] is False
