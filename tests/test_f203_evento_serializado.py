"""
tests/test_f203_evento_serializado.py
──────────────────────────────────────
F2-03 (parte del bug): el payload de `rf_events` no se serializa.

Comparado campo por campo con las otras cuatro arquitecturas satélite
(anexo en RETOMAR.md), `RFEvent` es la única sin relación en `MapObject`
(`RFEvent.object` es de una sola vía, rf.py:189) y la única que
`object_to_feature` no emite: hoy sale `rf`, `antenna`, `reference` y
`measurement`, pero nunca `event`.

Dos consumidores esperan ese bloque y no lo reciben:

* `export_service.to_csv` (líneas 224-226) lee `props.get("event")` para
  llenar `event_level_dbm` y `classification`: las dos columnas salen
  vacías en toda exportación.
* el Inspector del mapa lee `p.frequency_mhz` plano (InspectorPanel:856)
  porque nunca hubo payload que leer; ahora pasa a `p.event.*`, igual que
  `p.rf.*` para las fuentes.

Y `duplicate_object` no le pasa `event=` a `create_object`, keyword que
existe desde el origen (map_service.py:260): duplicar un evento perdía el
payload completo.

Nada de esto inventa datos: sólo se serializa la fila `rf_events` que ya
está en la base. `calculated_evento_id` sigue sin escribirse — decisión
del operador: queda declarado hasta que exista un caso de uso real.
"""

from __future__ import annotations

import csv
import io

import pytest

#: El prefijo real: `main.py` monta los routers con `settings.api_prefix`.
_API = "/api/v1"


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


EVENTO = {
    "name": "Evento RF 118.300",
    "latitude": -34.55,
    "longitude": -58.44,
    "frequency_mhz": 118.3,
    "level_dbm": -62.5,
    "bandwidth_khz": 25.0,
    "classification": "Interferencia aeronaútica",
    "observations": "portón de la base",
}


def _crear_evento(client, **extra):
    r = client.post(f"{_API}/rf/events", json={**EVENTO, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _bloque(payload: dict) -> dict:
    props = payload.get("properties") or {}
    bloque = props.get("event")
    assert bloque, f"properties.event ausente; hay {sorted(props)}"
    return bloque


# ─── Serialización ───────────────────────────────────────────────────────────

def test_la_respuesta_del_mapa_lleva_el_payload(client):
    ev = _crear_evento(client)
    r = client.get(f"{_API}/map/objects/{ev['id']}")
    assert r.status_code == 200, r.text

    bloque = _bloque(r.json())
    assert bloque["level_dbm"] == -62.5
    assert bloque["frequency_mhz"] == 118.3
    assert bloque["bandwidth_khz"] == 25.0
    assert bloque["classification"] == "Interferencia aeronaútica"
    assert bloque["observations"] == "portón de la base"
    # Provenance siempre visible: el campo existe en la serialización.
    assert bloque["provenance"]


def test_geojson_incluye_el_payload(client):
    ev = _crear_evento(client)
    r = client.get(f"{_API}/export/geojson", params={"type": "rf_event"})
    assert r.status_code == 200, r.text

    mios = [
        f for f in r.json()["features"]
        if f["properties"].get("id") == ev["id"]
    ]
    assert len(mios) == 1, f"features={len(mios)}"
    assert _bloque(mios[0])["level_dbm"] == -62.5


def test_csv_llena_las_columnas_del_evento(client):
    ev = _crear_evento(client)
    r = client.get(f"{_API}/export/csv", params={"type": "rf_event"})
    assert r.status_code == 200, r.text

    rows = list(csv.DictReader(io.StringIO(r.text), delimiter=";"))
    fila = next((x for x in rows if x["id"] == str(ev["id"])), None)
    assert fila is not None, f"columnas={list(rows[0]) if rows else []}"
    assert fila["event_level_dbm"] == "-62.5", fila
    assert fila["classification"] == "Interferencia aeronaútica", fila


def test_el_duplicado_conserva_el_payload(client):
    ev = _crear_evento(client)
    r = client.post(f"{_API}/map/objects/{ev['id']}/duplicate")
    assert r.status_code == 200, r.text

    copia = r.json()
    assert copia["id"] != ev["id"]
    bloque = _bloque(copia)
    assert bloque["level_dbm"] == -62.5
    assert bloque["frequency_mhz"] == 118.3
    assert bloque["classification"] == "Interferencia aeronaútica"


# ─── Guardas: no inventar, no romper lo demás ────────────────────────────────

def test_un_evento_sin_payload_no_inventa_un_bloque(client):
    r = client.post(
        f"{_API}/rf/events",
        json={"name": "Evento sin datos", "latitude": -34.6,
              "longitude": -58.4},
    )
    assert r.status_code == 201, r.text

    props = r.json().get("properties") or {}
    assert not props.get("event"), f"payload inventado: {props.get('event')}"


def test_otros_tipos_no_llevan_bloque_evento(client):
    r = client.post(
        f"{_API}/rf/sources",
        json={"name": "Fuente guardia #01", "latitude": -34.61,
              "longitude": -58.40, "kind": "FM", "frequency_mhz": 98.1},
    )
    assert r.status_code == 201, r.text

    props = r.json().get("properties") or {}
    assert props.get("rf"), f"sin bloque rf: {sorted(props)}"
    assert not props.get("event"), "la fuente no tiene evento"


def test_borrar_un_evento_no_deja_filas_huerfanas(client):
    """La relación nueva (`rf_event` con delete-orphan) debe cascadear.

    Antes de F2-03 el cascade lo hacía sólo la base (`ondelete=CASCADE`);
    con la relación en el objeto es el ORM el que borra, y si estuviera
    mal declarada esta prueba fallaría con IntegrityError.
    """
    ev = _crear_evento(client)
    r = client.delete(f"{_API}/map/objects/{ev['id']}")
    assert r.status_code == 200, r.text

    assert client.get(f"{_API}/map/objects/{ev['id']}").status_code == 404
    assert client.get(f"{_API}/rf/events/{ev['id']}").status_code == 404
