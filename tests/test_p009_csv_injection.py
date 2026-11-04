"""
tests/test_p009_csv_injection.py
────────────────────────────────
P0-09: inyección de fórmulas en el CSV, **sólo en campos de texto libre**.

Un nombre tecleado `=HYPERLINK("http://evil.example","clic")` viajaba
tal cual y el CSV lo abría la hoja de cálculo como **fórmula**: clic en
la celda y el operador cae en el sitio del atacante; peor, los DDE
(``=cmd|'/c calc'!A0``) llegan a ejecutar comandos. La trampa obvia —
prefijar todo lo que empiece por `=` `+` `-` `@` — es la que avisa el
propio ítem: convertiría la latitud `-34.6` en **texto**.

Por eso el blindado va por el valor, no por la columna:

* sólo **strings** — las columnas numéricas (latitud, longitud,
  nivel dBm) traen números y no se tocan;
* y un string que se pueda leer como número (`"-34.6"`, `"-62.5"`)
  tampoco: prefijarlo sería el error que el ítem describe. Una lista
  blanca de columnas se pudre con la próxima columna nueva; el
  carácter peligroso, no.

La guarda mide las dos caras: la fórmula se blinda (roja antes) y el
número negativo queda idéntico (verde de arranque, que tiene que
seguirlo).
"""

from __future__ import annotations

import csv
import io

import pytest

_API = "/api/v1"


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _fila_csv(client, object_id: int, tipo: str = "point") -> dict:
    r = client.get(f"{_API}/export/csv", params={"type": tipo})
    assert r.status_code == 200, r.text
    filas = list(csv.DictReader(io.StringIO(r.text), delimiter=";"))
    fila = next((x for x in filas if x["id"] == str(object_id)), None)
    assert fila is not None, f"no aparece {object_id}; hay {len(filas)}"
    return fila


# ─── La cara peligrosa: la fórmula no llega viva ─────────────────────────────

def test_el_csv_blinda_las_formulas_en_texto_libre(client):
    nombre = '=HYPERLINK("http://evil.example","clic")'
    descripcion = "=1+1"

    r = client.post(
        f"{_API}/map/objects",
        json={
            "type": "point",
            "name": nombre,
            "description": descripcion,
            "latitude": -34.6,
            "longitude": -58.4,
        },
    )
    assert r.status_code == 201, r.text

    fila = _fila_csv(client, r.json()["id"])
    assert fila["name"] == "'" + nombre, fila["name"]
    assert fila["description"] == "'=1+1", fila["description"]


def test_track_csv_blinda_al_callsign_tambien(client):
    """El callsign viene de OpenSky — dato de un tercero, ni siquiera
    del operador."""
    from app.services import export_service as exporter

    texto = exporter.track_to_csv(
        [
            {
                "timestamp": 1_700_000_000,
                "latitude": -34.6,
                "longitude": -58.4,
                "callsign": "=1+1",
                "icao24": "abc123",
            }
        ]
    )
    filas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    encabezado, datos = filas[0], filas[1]
    assert datos[encabezado.index("callsign")] == "'=1+1"
    # …y la latitud de la misma fila sigue siendo un número.
    assert datos[encabezado.index("latitude")] == "-34.6"


# ─── La cara que no hay que romper: los números ──────────────────────────────

def test_las_latitudes_negativas_no_se_tocan(client):
    r = client.post(
        f"{_API}/map/objects",
        json={
            "type": "point",
            "name": "Coordenada de prueba",
            "latitude": -34.6,
            "longitude": -58.4,
        },
    )
    assert r.status_code == 201, r.text

    fila = _fila_csv(client, r.json()["id"])
    assert fila["latitude"] == "-34.6", fila["latitude"]
    assert fila["longitude"] == "-58.4", fila["longitude"]


def test_un_numero_en_cadena_tampoco_se_blinda():
    """La advertencia exacta del ítem, más el caso real: un dBm que
    llega como string desde el JSON de propiedades."""
    from app.services import export_service as exporter

    assert exporter._blindar("-34.6") == "-34.6"
    assert exporter._blindar("-62.5") == "-62.5"
    assert exporter._blindar("+7.5") == "+7.5"
    assert exporter._blindar(-34.6) == -34.6
    # …y lo peligroso sí.
    assert exporter._blindar("=1+1") == "'=1+1"
    assert exporter._blindar("-2+3") == "'-2+3"
    assert exporter._blindar("@SUM(A1)") == "'@SUM(A1)"
    assert exporter._blindar("hola") == "hola"
    assert exporter._blindar("") == ""
    assert exporter._blindar(None) is None
