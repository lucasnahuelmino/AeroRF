"""
tests/test_f202_historial_tipado.py
────────────────────────────────────
F2-02: el historial de auditoría escribe filas falsas al editar atributos
tipados.

La causa, en una línea: `svc._record_history(db, db_obj, {"rf.power_dbm": 40})`
hace `getattr(obj, "rf.power_dbm")` sobre el **MapObject**, y ese atributo no
existe → `None`. Entonces, para cada campo con valor del satélite, el historial
afirma que pasó a `None`.

Repro de la auditoría (cambiar sólo `power_dbm` de 40 a 41): se generan 6
filas, entre ellas `rf.id '1' → None`, `rf.object_id '3' → None`,
`rf.kind 'FM' → None`, `rf.frequency_mhz '98.1' → None` y
`rf.power_dbm '40.0' → None`. O sea: dice que se borraron la frecuencia y el
tipo, y el cambio real (40 → 41) **no aparece en ninguna parte**.

Lo que tiene que pasar, según el criterio de aceptación: *«el historial
registra sólo cambios reales, con valor anterior y nuevo, para todos los
tipos»*.

Y un caso que la auditoría no vió, encontrado al leer `update_reference`:
`db_obj.radius` y `db_obj.azimuth` se escriben ahí mismo y **no pasan por
ningún diff** — el objeto cambia sin que el historial se entere.
"""

from __future__ import annotations

import pytest

from app.models.rf import Antenna, RFEvent, RFSource, ReferencePoint

_API = "/api/v1"

#: endpoint, modelo, prefijo del historial, payload de alta, edición de un
#: solo campo, campo, valor viejo, valor nuevo.
VISTAS = [
    ("fuente", "rf/sources", RFSource, "rf",
     {"name": "Fuente interferente #01", "latitude": -34.61,
      "longitude": -58.40, "kind": "FM", "frequency_mhz": 98.1,
      "power_dbm": 40, "status": "Activo"},
     {"power_dbm": 41}, "power_dbm", 40.0, 41.0),
    ("antena", "antennas", Antenna, "antenna",
     {"name": "Antena EZE", "latitude": -34.82, "longitude": -58.53,
      "kind": "Direccional", "frequency_mhz": 118.3, "gain_dbi": 12,
      "azimuth_deg": 90},
     {"gain_dbi": 15}, "gain_dbi", 12.0, 15.0),
    ("evento", "rf/events", RFEvent, "event",
     {"name": "Evento RF 118.300", "latitude": -34.55,
      "longitude": -58.44, "frequency_mhz": 118.3, "level_dbm": -62,
      "classification": "Interferencia aeronaútica"},
     {"level_dbm": -50}, "level_dbm", -62.0, -50.0),
    ("referencia", "references", ReferencePoint, "reference",
     {"name": "Referencia EZE", "latitude": -34.80, "longitude": -58.46,
      "kind": "NDB", "code": "EZE", "radius": 10, "radius_unit": "nm"},
     {"radius": 25}, "radius", 10.0, 25.0),
]


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _crear(client, endpoint, payload):
    r = client.post(f"{_API}/{endpoint}", json=payload)
    assert r.status_code == 201, f"alta falló: {r.status_code} {r.text}"
    return r.json()["id"]


def _historial(client, object_id):
    r = client.get(f"{_API}/map/objects/{object_id}/history")
    assert r.status_code == 200, r.text
    return r.json()


def _del_prefijo(filas, prefijo):
    p = f"{prefijo}."
    return [f for f in filas if f["field"].startswith(p)]


@pytest.mark.parametrize(
    "nombre, endpoint, modelo, prefijo, payload, edit, campo, viejo, nuevo",
    VISTAS, ids=[v[0] for v in VISTAS],
)
def test_un_campo_cambiado_produce_exactamente_una_fila(
    client, nombre, endpoint, modelo, prefijo, payload, edit, campo, viejo, nuevo
):
    """El criterio de aceptación: sólo cambios reales, con los dos valores."""
    object_id = _crear(client, endpoint, payload)

    r = client.put(f"{_API}/{endpoint}/{object_id}", json=edit)
    assert r.status_code == 200, f"{nombre}: {r.status_code} {r.text}"

    filas = _del_prefijo(_historial(client, object_id), prefijo)

    assert len(filas) == 1, (
        f"{nombre}: esperaba 1 fila de historial, vinieron {len(filas)}: "
        f"{[(f['field'], f['old_value'], f['new_value']) for f in filas]}"
    )
    fila = filas[0]
    assert fila["field"] == f"{prefijo}.{campo}", fila["field"]
    # Se comparan como número y no como texto a propósito: el `PUT` arma el
    # satélite con el cuerpo crudo (sin pasar por Pydantic — es F2-05), así
    # que `41` llega como entero y la base lo guarda como `41`, mientras que
    # el valor viejo salió de la creación, que sí valida y quedó `40.0`. El
    # historial tiene que decir la verdad numérica, no el formato.
    assert float(fila["old_value"]) == viejo, (
        f"{nombre}: valor viejo {fila['old_value']!r}, esperaba {viejo!r}"
    )
    assert float(fila["new_value"]) == nuevo, (
        f"{nombre}: valor nuevo {fila['new_value']!r}, esperaba {nuevo!r}"
    )


def test_no_afirma_que_se_borro_lo_que_sigue_ahi(client):
    """El síntoma de la auditoría: filas que dicen `→ None`."""
    object_id = _crear(client, "rf/sources", dict(VISTAS[0][4]))

    r = client.put(f"{_API}/rf/sources/{object_id}", json={"power_dbm": 41})
    assert r.status_code == 200, r.text

    filas = _del_prefijo(_historial(client, object_id), "rf")
    borrados = [f for f in filas if f["new_value"] is None]

    assert not borrados, (
        "el historial dice que se borraron campos que siguen ahí: "
        f"{[(f['field'], f['old_value']) for f in borrados]}"
    )


def test_el_cambio_real_aparece_con_los_dos_valores(client):
    """El repro exacto: 40 → 41, una sola vez, ni una fila de relleno."""
    object_id = _crear(client, "rf/sources", dict(VISTAS[0][4]))

    r = client.put(f"{_API}/rf/sources/{object_id}", json={"power_dbm": 41})
    assert r.status_code == 200, r.text

    filas = _historial(client, object_id)
    poder = [f for f in filas if f["field"] == "rf.power_dbm"]

    assert len(poder) == 1, [(f["field"], f["old_value"], f["new_value"]) for f in filas]
    assert float(poder[0]["old_value"]) == 40.0, poder[0]
    assert float(poder[0]["new_value"]) == 41.0, poder[0]


def test_el_cambio_del_objeto_padre_tambien_aparece(client):
    """`update_antenna` copia `azimuth_deg` al objeto sin pasar por diff."""
    payload = dict(VISTAS[1][4])
    object_id = _crear(client, "antennas", payload)

    r = client.put(f"{_API}/antennas/{object_id}", json={"azimuth_deg": 120})
    assert r.status_code == 200, r.text

    filas = _historial(client, object_id)
    satelite = [f for f in filas if f["field"] == "antenna.azimuth_deg"]
    objeto = [f for f in filas if f["field"] == "azimuth"]

    assert len(satelite) == 1, [(f["field"], f["old_value"], f["new_value"]) for f in filas]
    assert float(satelite[0]["old_value"]) == 90.0, satelite[0]
    assert float(satelite[0]["new_value"]) == 120.0, satelite[0]

    assert len(objeto) == 1, (
        "el azimuth del objeto cambió sin quedar en el historial: "
        f"{[(f['field'], f['old_value'], f['new_value']) for f in filas]}"
    )
    assert float(objeto[0]["old_value"]) == 90.0, objeto[0]
    assert float(objeto[0]["new_value"]) == 120.0, objeto[0]


def test_reenviar_el_mismo_numero_como_entero_no_inventa_un_cambio(client):
    """`25.0` y `25` son el mismo número: no es un cambio.

    El `PUT` arma el satélite con el cuerpo crudo (sin Pydantic), así que un
    entero llega como entero y la base lo guarda como `25`. Si el historial
    comparara los textos renderizados, reenviar la misma medida generaría
    otra fila falsa: diría que la altura pasó de `25.0` a `25` cuando no se
    movió.
    """
    payload = {**VISTAS[0][4], "height_m": 25}
    object_id = _crear(client, "rf/sources", payload)

    r = client.put(f"{_API}/rf/sources/{object_id}", json={"height_m": 25})
    assert r.status_code == 200, r.text

    filas = _del_prefijo(_historial(client, object_id), "rf")

    assert filas == [], [
        (f["field"], f["old_value"], f["new_value"]) for f in filas
    ]
