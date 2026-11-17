"""
tests/test_rf_analisis.py
─────────────────────────
AeroRF 2.6 · Bloque 1: la calculadora guarda sus análisis sin Expedientes.

La calculadora se quedó sin destino propio — sólo sabía guardar «en un
expediente» — y esa era la dependencia que había que retirar. El reemplazo es
`POST /rf/analisis`: una corrida se persiste con su request y su response
completos y adquiere identidad propia.

Estas pruebas cubren el criterio de aceptación del bloque:

* guardar, listar, consultar y eliminar análisis con **cero expedientes** en
  la base (ninguna operación normal requiere Expedientes);
* que la respuesta no arrastra ningún campo de expediente;
* que la asociación opcional a un objeto GIS funciona y valida (404 para un
  objeto inexistente, 400 para tipos que no son evidencia RF);
* que un body inválido se rechaza antes de escribir nada.

El body de `parametros`/`resultados` no está escrito a mano: sale de una
corrida real contra `POST /rf/calculate`, así el contrato del historial queda
atado al contrato del motor.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models.expediente import Expediente


@pytest.fixture
def client(db):
    from app.main import app

    with TestClient(app) as c:
        yield c


# Lo que la calculadora manda al motor (modo B, una emisora FM).
CALCULO = {
    "target_mhz": 177.0,
    "tolerance_khz": 10.0,
    "frequencies": [
        {"freq_mhz": 88.5, "label": "FM Radio", "signal_type": "FM"},
    ],
}


def _guardar(client, **extra):
    """Corrida real al motor + guardado del historial con esa corrida."""
    corrida = client.post("/api/v1/rf/calculate", json=CALCULO)
    assert corrida.status_code == 200, corrida.text
    body = {
        "modo": "intermodulacion",
        "parametros": CALCULO,
        "resultados": corrida.json(),
    }
    body.update(extra)
    return client.post("/api/v1/rf/analisis", json=body)


# ─── Guardar y consultar sin expedientes ─────────────────────────────────────

class TestGuardarSinExpedientes:
    def test_guardar_listar_consultar_y_borrar(self, client, db):
        assert db.query(Expediente).count() == 0, "el test arranca con expedientes"

        guardado = _guardar(client)
        assert guardado.status_code == 201, guardado.text
        datos = guardado.json()

        # El análisis no depende de ningún expediente ni arrastra sus campos.
        assert "expediente_id" not in datos
        assert "expediente" not in datos
        assert datos["id"] > 0
        assert datos["modo"] == "intermodulacion"
        assert datos["frecuencia_referencia_mhz"] == pytest.approx(177.0)
        assert datos["tolerancia_khz"] == pytest.approx(10.0)
        assert datos["n_emisoras"] == 1
        assert datos["n_productos"] >= 1
        assert datos["objeto_id"] is None
        assert datos["parametros"]["frequencies"][0]["freq_mhz"] == pytest.approx(88.5)

        # Siguen sin haber expedientes: nada de esto los necesitó.
        assert db.query(Expediente).count() == 0

        detalle = client.get(f"/api/v1/rf/analisis/{datos['id']}")
        assert detalle.status_code == 200
        assert detalle.json()["resultados"]["matches"] == datos["resultados"]["matches"]

        lista = client.get("/api/v1/rf/analisis")
        assert lista.status_code == 200
        ids = [a["id"] for a in lista.json()]
        assert datos["id"] in ids

    def test_resultados_conservan_la_respuesta_del_motor(self, client):
        corrida = client.post("/api/v1/rf/calculate", json=CALCULO).json()
        guardado = _guardar(client).json()
        assert guardado["resultados"] == corrida
        # `parametros` se guarda con los defaults del contrato ya aplicados
        # (max_results, power_dbm, etc.): lo que se pide es que lo enviado
        # esté contenido, no que el motor devuelva nuestro body crudo.
        assert guardado["parametros"]["target_mhz"] == CALCULO["target_mhz"]
        assert guardado["parametros"]["tolerance_khz"] == CALCULO["tolerance_khz"]
        assert guardado["parametros"]["frequencies"][0]["freq_mhz"] == 88.5

    def test_eliminar_un_analisis(self, client):
        guardado = _guardar(client).json()
        analisis_id = guardado["id"]

        borrado = client.delete(f"/api/v1/rf/analisis/{analisis_id}")
        assert borrado.status_code == 204

        detalle = client.get(f"/api/v1/rf/analisis/{analisis_id}")
        assert detalle.status_code == 404
        assert "No existe el análisis" in detalle.json()["detail"]

    def test_consultar_un_analisis_inexistente(self, client):
        r = client.get("/api/v1/rf/analisis/999999")
        assert r.status_code == 404


# ─── Validación de la escritura ──────────────────────────────────────────────

class TestValidacion:
    def test_modo_invalido_se_rechaza(self, client):
        r = _guardar(client, modo="probabilidad")
        assert r.status_code == 422

    def test_resultados_obligatorios(self, client):
        r = client.post(
            "/api/v1/rf/analisis",
            json={"modo": "armonicos", "parametros": CALCULO},
        )
        assert r.status_code == 422

    def test_parametros_fuera_de_rango_del_motor(self, client):
        corrida = client.post("/api/v1/rf/calculate", json=CALCULO).json()
        malo = dict(CALCULO, target_mhz=0)  # el motor exige gt=0
        r = client.post(
            "/api/v1/rf/analisis",
            json={"modo": "armonicos", "parametros": malo, "resultados": corrida},
        )
        assert r.status_code == 422


# ─── Asociación opcional a objetos GIS (spec 3.5) ───────────────────────────

class TestAsociacionAObjetoGIS:
    def test_asociar_a_una_fuente_rf(self, client, db):
        from app.services import map_service as svc

        fuente = svc.create_object(
            db, "rf_source", name="FM señal", latitude=-34.82, longitude=-58.53
        )
        db.commit()

        guardado = _guardar(client, objeto_id=fuente.id)
        assert guardado.status_code == 201, guardado.text
        assert guardado.json()["objeto_id"] == fuente.id

        por_objeto = client.get(f"/api/v1/rf/analisis?objeto_id={fuente.id}")
        assert por_objeto.status_code == 200
        assert [a["id"] for a in por_objeto.json()] == [guardado.json()["id"]]

    def test_objeto_inexistente(self, client):
        r = _guardar(client, objeto_id=999999)
        assert r.status_code == 404
        assert "No existe el objeto GIS" in r.json()["detail"]

    def test_tipo_no_asociable(self, client, db):
        from app.services import map_service as svc

        punto = svc.create_object(
            db, "point", name="Punto de dibujo", latitude=-34.82, longitude=-58.53
        )
        db.commit()

        r = _guardar(client, objeto_id=punto.id)
        assert r.status_code == 400
        assert "fuente RF" in r.json()["detail"]

        # Nada quedó escrito con la asociación inválida.
        lista = client.get("/api/v1/rf/analisis").json()
        assert all(a["objeto_id"] != punto.id for a in lista)


# ─── El legacy sigue intacto ─────────────────────────────────────────────────

class TestLegacyIntacto:
    def test_expedientes_sigue_disponible_para_clientes_historicos(self, client, db):
        """Los endpoints de Expedientes son legado: no se tocaron, y siguen
        respondiendo para los clientes históricos aunque la calculadora ya
        no los use."""
        exp = Expediente(numero_expediente="E-LEGACY", freq_mhz=118.3, aeropuerto="EZE")
        db.add(exp)
        db.commit()

        r = client.get(f"/api/v1/expedientes/{exp.id}/eventos")
        assert r.status_code == 200
        assert r.json() == []
