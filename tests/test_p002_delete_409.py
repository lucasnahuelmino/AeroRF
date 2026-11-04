"""
tests/test_p002_delete_409.py
──────────────────────────────
P0-02: borrar un expediente con objetos GIS vinculados: bloquear con 409.

Decisión del operador: «igual que ya pasa al revés, donde borrar un
objeto vinculado sí está bloqueado» — `map_service.delete_object` ya
niega borrar un objeto que pertenece a un expediente.

Lo que había: `MapObject.expediente_id` es `ON DELETE SET NULL` y la
base corre con `PRAGMA foreign_keys=ON`, así que el DELETE contestaba
**200** y se llevaba el vínculo en silencio: el expediente
desaparecía, los objetos quedaban huérfanos de caso y nadie veía nada.
El sentido inverso estaba bloqueado; este no.

La guarda mide cuatro cosas:

1. 409 con detalle en español cuando hay vínculos — y que **no borró
   nada**: el expediente y el vínculo siguen tras el intento;
2. que el borrado legítimo (sin vínculos) sigue funcionando, con el
   mensaje ya en español — el bloqueo no se come el camino bueno;
3. el camino de recuperación: desvincular por la API pública y borrar;
4. 404 en español para el expediente que no existe (el texto en
   inglés estaba justo en la función que hay que tocar).
"""

from __future__ import annotations

import pytest

_API = "/api/v1"
_DEPENDENCY_LABELS = {
    "medicion": "mediciones",
    "evento_rf": "eventos rf",
    "registro_espectral": "registros espectrales",
}


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _expediente(client, numero: str) -> dict:
    r = client.post(
        f"{_API}/expedientes/",
        json={
            "numero_expediente": numero,
            "freq_mhz": 121.5,
            "aeropuerto": "Ezeiza",
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def _objeto_vinculado(client, expediente_id: int) -> dict:
    r = client.post(
        f"{_API}/map/objects",
        json={
            "type": "point",
            "name": "Objeto del caso",
            "latitude": -34.6,
            "longitude": -58.4,
            "expediente_id": expediente_id,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _crear_dato_dependiente(kind: str, expediente_id: int) -> int:
    from app.database.database import SessionLocal
    from app.models.evento_rf import EventoRF
    from app.models.espectro import RegistroEspectral
    from app.models.medicion import Medicion

    modelos = {
        "medicion": Medicion,
        "evento_rf": EventoRF,
        "registro_espectral": RegistroEspectral,
    }
    modelo = modelos[kind]
    valores = {"expediente_id": expediente_id}
    if kind == "medicion":
        valores.update(freq_mhz=121.5, lat=-34.6, lon=-58.4)
    elif kind == "evento_rf":
        valores.update(
            frecuencia_resultado_mhz=121.5,
            tipo_producto="H2",
            formula="2 * 60.75",
            error_khz=0.0,
            score_probabilidad=90.0,
        )
    else:
        # This is database metadata only; the test does not create or modify a file.
        valores.update(
            archivo_path="evidencias/prueba.png",
            tipo_archivo="imagen",
            nombre_archivo="prueba.png",
        )

    with SessionLocal() as session:
        dato = modelo(**valores)
        session.add(dato)
        session.commit()
        return dato.id


# ─── El bloqueo nuevo ────────────────────────────────────────────────────────

def test_delete_con_objetos_gis_vinculados_da_409(client):
    exp = _expediente(client, "EXP-P002")
    obj = _objeto_vinculado(client, exp["id"])

    r = client.delete(f"{_API}/expedientes/{exp['id']}")

    assert r.status_code == 409, r.text
    detalle = r.json()["detail"]
    assert isinstance(detalle, str) and detalle, detalle
    assert "objeto" in detalle.lower() and "vincul" in detalle.lower(), detalle

    # El 409 no se comió nada: el expediente sigue vivo…
    assert client.get(f"{_API}/expedientes/{exp['id']}").status_code == 200
    # …y el vínculo también, no el «SET NULL» silencioso de antes.
    objeto = client.get(f"{_API}/map/objects/{obj['id']}").json()
    assert objeto["expediente_id"] == exp["id"], objeto.get("expediente_id")


# ─── El camino bueno, que el bloqueo no puede estorbar ───────────────────────

def test_delete_sin_vinculos_sigue_borrando(client):
    exp = _expediente(client, "EXP-P002-LIBRE")

    r = client.delete(f"{_API}/expedientes/{exp['id']}")

    assert r.status_code == 200, r.text
    assert "eliminado" in r.json()["message"], r.json()
    assert client.get(f"{_API}/expedientes/{exp['id']}").status_code == 404


def test_desvincular_y_borrar_es_el_camino_de_recuperacion(client):
    exp = _expediente(client, "EXP-P002-DESV")
    obj = _objeto_vinculado(client, exp["id"])

    assert client.delete(f"{_API}/expedientes/{exp['id']}").status_code == 409

    # Desvincular por la API pública (PUT parcial: `exclude_none=False`).
    r = client.put(
        f"{_API}/map/objects/{obj['id']}", json={"expediente_id": None}
    )
    assert r.status_code == 200, r.text
    assert r.json()["expediente_id"] is None, r.json().get("expediente_id")

    r = client.delete(f"{_API}/expedientes/{exp['id']}")
    assert r.status_code == 200, r.text
    assert client.get(f"{_API}/expedientes/{exp['id']}").status_code == 404


@pytest.mark.parametrize("kind", ["medicion", "evento_rf", "registro_espectral"])
def test_delete_con_datos_dependientes_bloquea_y_preserva_filas(client, kind):
    from app.database.database import SessionLocal
    from app.models.evento_rf import EventoRF
    from app.models.espectro import RegistroEspectral
    from app.models.medicion import Medicion

    exp = _expediente(client, f"EXP-PRESERVAR-{kind}")
    dato_id = _crear_dato_dependiente(kind, exp["id"])
    modelos = {
        "medicion": Medicion,
        "evento_rf": EventoRF,
        "registro_espectral": RegistroEspectral,
    }

    r = client.delete(f"{_API}/expedientes/{exp['id']}")

    assert r.status_code == 409, r.text
    assert "datos asociados" in r.json()["detail"].lower()
    assert _DEPENDENCY_LABELS[kind] in r.json()["detail"].lower()
    assert client.get(f"{_API}/expedientes/{exp['id']}").status_code == 200
    with SessionLocal() as session:
        assert session.get(modelos[kind], dato_id) is not None


# ─── El 404 de esta función, en español ──────────────────────────────────────

def test_delete_inexistente_da_404_en_espanol(client):
    r = client.delete(f"{_API}/expedientes/999999")
    assert r.status_code == 404, r.text
    detalle = r.json()["detail"]
    assert "not found" not in str(detalle).lower(), detalle
    assert "expediente" in str(detalle).lower(), detalle
