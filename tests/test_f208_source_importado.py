"""
tests/test_f208_source_importado.py
────────────────────────────────────
F2-08: `import_geojson` no pasa `source` y el objeto queda como «user».

Un archivo importado aparecía en el Inspector como «Introducido por el
usuario» y salía así en el CSV exportado: la procedencia mentía sobre el
origen del dato, que es exactamente lo que la trazabilidad existe para
impedir.

Arreglarlo bien exige las tres bocas a la vez, o el dato se cae por
otro lado:

1. **el import** tiene que pasar `source=PROVENANCE_IMPORTED`;
2. **`PROVENANCE_VALUES`** tiene que aceptar el valor — el validador de
   `MapObjectCreate` rechaza cualquier `source` fuera de la tupla;
3. **`PROVENANCE_LABELS_ES` + `MapEngine.provenanceLabel`** tienen que
   tener la etiqueta — si no, la UI pinta el valor crudo, en inglés
   («imported»), que es justo lo que avisa la auditoría.
"""

from __future__ import annotations

import pytest

#: El prefijo real: `main.py` monta los routers con `settings.api_prefix`.
_API = "/api/v1"

_FEATURE = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [-58.4, -34.6]},
    "properties": {"name": "Importado de prueba"},
}


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


# ─── La boca que miente ──────────────────────────────────────────────────────

def test_import_geojson_deja_el_source_importado(client):
    r = client.post(f"{_API}/map/objects/from-geojson", json=_FEATURE)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["count"] == 1, cuerpo

    detalle = client.get(f"{_API}/map/objects/{cuerpo['created'][0]['id']}").json()
    # Lo que ve el Inspector…
    assert detalle["provenance"] == "imported", detalle.get("provenance")
    # …y lo que sale en la exportación GeoJSON.
    assert detalle["properties"]["source"] == "imported", (
        detalle["properties"].get("source")
    )


# ─── Las otras dos bocas ─────────────────────────────────────────────────────

def test_vocabulario_sirve_importado_con_etiqueta_en_espanol(client):
    vocab = client.get(f"{_API}/map/vocabulary").json()
    assert "imported" in vocab["provenance"], vocab["provenance"]
    assert vocab["provenance_labels"].get("imported") == "Dato importado", (
        vocab["provenance_labels"].get("imported")
    )


def test_create_acepta_source_importado(client):
    """El valor nuevo tiene que pasar también por el alta a mano."""
    r = client.post(
        f"{_API}/map/objects",
        json={
            "type": "point",
            "name": "Creado con source importado",
            "latitude": -34.6,
            "longitude": -58.4,
            "source": "imported",
        },
    )
    assert r.status_code == 201, r.text
