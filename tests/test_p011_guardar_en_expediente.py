"""
tests/test_p011_guardar_en_expediente.py
────────────────────────────────────────
P0-11: el botón «Guardar en Expediente» decía «guardado» y no guardaba nada.

El código era este, y no otra cosa:

    const storeResult = () => {
      alert('Resultado guardado (próximamente integrado con expediente)')
    }

Lo que ya existía, antes de tocar nada:

* `EventoRF` con exactamente los campos que produce el cálculo
  (`frecuencia_resultado_mhz`, `tipo_producto`, `formula`, `error_khz`,
  `score_probabilidad`, `expediente_id`), en `eventos_rf`.
* `EventoRFCreate` y `EventoRFResponse` en `schemas.py`.
* `GET /expedientes/{id}/eventos`, que devuelve esos campos ordenados por
  probabilidad.

Lo que no existía era la escritura, y por eso no había nada que ver en ese
`GET`. Por eso estas pruebas fallan antes del arreglo: el método no está.

Dos arquitecturas RF conviven en el proyecto y no se mezclan:

* **A, `eventos_rf`** — la que usa la calculadora, sin coordenadas.
* **B, `rf_events`** — acompañante de `MapObject`, con lat/lon y
  `POST /rf/events` (`client.js` lo llama `rf.createEvent`).

Un resultado del armónico no tiene coordenadas, así que guardarla en la B
habría sido escribir en el stack equivocado y exigirle una lat/lon que nadie
tiene. Éste va a la A.
"""

from __future__ import annotations

import pytest

from app.models.expediente import Expediente


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def expediente(db):
    """Un expediente real, creado igual que en el resto de la suite."""
    exp = Expediente(numero_expediente="E-P011", freq_mhz=118.3, aeropuerto="EZE")
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def _payload(expediente, **extra):
    """Lo que la calculadora manda, mapeado a los campos de `EventoRF`.

    Los valores no los invento: son la respuesta real de
    `POST /rf/calculate` con objetivo 177.0 MHz contra 88.5 MHz, medida en
    vivo antes de escribir esta prueba (`tipo` llega como `"H2"`, no como
    `IMOrder.H2`, que no cabría en `String(10)`).
    """
    body = {
        "expediente_id": expediente.id,
        "frecuencia_resultado_mhz": 177.0,
        "tipo_producto": "H2",
        "formula": "2 × 88.5",
        "error_khz": 0.0,
        "score_probabilidad": 99,
        "freq_1_mhz": 88.5,
    }
    body.update(extra)
    return body


# ─── La prueba del defecto ────────────────────────────────────────────────────

def test_lo_que_el_boton_promete_se_puede_ver_despues(client, expediente):
    """Guardar y volver a leer. Antes no había nada que leer."""
    r = client.post(
        f"/api/v1/expedientes/{expediente.id}/eventos",
        json=_payload(expediente),
    )
    assert r.status_code == 201, r.text

    guardado = r.json()
    assert guardado["id"] > 0, "no devolvió el id del evento creado"
    assert guardado["expediente_id"] == expediente.id

    # El GET que ya existía tiene que devolverlo ahora.
    lista = client.get(f"/api/v1/expedientes/{expediente.id}/eventos").json()
    assert len(lista) == 1, f"el GET seguía vacío: {lista}"
    assert lista[0]["frecuencia_resultado_mhz"] == 177.0
    assert lista[0]["tipo_producto"] == "H2"
    assert lista[0]["formula"] == "2 × 88.5"
    assert lista[0]["score_probabilidad"] == 99


def test_los_valores_sobreviven_el_viaje_de_ida_y_vuelta(client, expediente):
    """Ningún campo se redondea, trunca ni se llena solo en el camino."""
    payload = _payload(
        expediente,
        error_khz=0.004,
        score_probabilidad=41,
        freq_1_mhz=88.5,
        freq_2_mhz=58.0,
        proximidad=12.5,
        senal_type="FM",
        potencia_estimada_dbm=-73.25,
        observaciones="Guardado desde la calculadora",
    )
    r = client.post(
        f"/api/v1/expedientes/{expediente.id}/eventos", json=payload
    )
    assert r.status_code == 201, r.text

    fila = client.get(f"/api/v1/expedientes/{expediente.id}/eventos").json()[0]
    for campo in (
        "error_khz",
        "score_probabilidad",
        "freq_1_mhz",
        "freq_2_mhz",
        "proximidad",
        "senal_type",
        "potencia_estimada_dbm",
        "observaciones",
    ):
        assert fila[campo] == payload[campo], f"{campo} cambió en el camino"


def test_el_expediente_recibe_todos_los_que_se_guardan(client, expediente):
    """Cada guardado deja una fila; el botón no es de un solo uso."""
    for score in (41, 99, 70):
        r = client.post(
            f"/api/v1/expedientes/{expediente.id}/eventos",
            json=_payload(expediente, score_probabilidad=score),
        )
        assert r.status_code == 201, r.text

    lista = client.get(f"/api/v1/expedientes/{expediente.id}/eventos").json()
    assert [e["score_probabilidad"] for e in lista] == [99, 70, 41], (
        "el GET no devuelve ordenado por probabilidad, que es como lo usa "
        f"la vista del expediente: {lista}"
    )


def test_los_guardados_de_un_expediente_no_aparecen_en_otro(client, expediente):
    """Los dos expedientes no se mezclan al guardar."""
    client.post("/api/v1/expedientes/", json={
        "numero_expediente": "E-OTRO",
        "freq_mhz": 121.5,
        "aeropuerto": "EZE",
    })

    r = client.post(
        f"/api/v1/expedientes/{expediente.id}/eventos",
        json=_payload(expediente),
    )
    assert r.status_code == 201, r.text

    # El otro expediente, recién creado, no puede heredar nada.
    creado = [e for e in client.get("/api/v1/expedientes/").json()
              if e["numero_expediente"] == "E-OTRO"]
    assert creado, "no se pudo crear el segundo expediente"
    ajeno = client.get(f"/api/v1/expedientes/{creado[0]['id']}/eventos").json()
    assert ajeno == [], f"se filtró un evento al otro expediente: {ajeno}"


# ─── Los errores, en español ─────────────────────────────────────────────────

def test_guardar_en_un_expediente_inexistente_no_existe(client):
    """404, y en español: «Expediente not found» era el texto de al lado."""
    r = client.post(
        "/api/v1/expedientes/999999/eventos",
        json={
            "expediente_id": 999999,
            "frecuencia_resultado_mhz": 177.0,
            "tipo_producto": "H2",
            "formula": "2 × 88.5",
            "error_khz": 0.0,
            "score_probabilidad": 99,
        },
    )
    assert r.status_code == 404, r.text
    detalle = r.json()["detail"]
    assert "not found" not in detalle.lower(), f"mensaje en inglés: {detalle}"
    assert "expediente" in detalle.lower(), (
        f"el aviso no nombra lo que falta: {detalle}"
    )


def test_si_el_cuerpo_dice_otro_expediente_no_se_escribe_nada(client, expediente):
    """La URL manda; una contradicción es un error, no un motivo para adivinar."""
    r = client.post(
        f"/api/v1/expedientes/{expediente.id}/eventos",
        json=_payload(expediente, expediente_id=expediente.id + 1),
    )
    assert r.status_code == 400, r.text
    detalle = r.json()["detail"]
    assert "no coincide" in detalle, f"mensaje en inglés o vago: {detalle}"

    # Y sobre todo: no se escribió en ningún lado.
    assert client.get(f"/api/v1/expedientes/{expediente.id}/eventos").json() == []
