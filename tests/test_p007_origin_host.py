"""
tests/test_p007_origin_host.py
──────────────────────────────
P0-07: middleware de `Origin`/`Host`, acotado a los orígenes de CORS
configurados.

Decisión del operador: el modelo de despliegue sigue sin decidido, así
que la lista es `CORS_ORIGINS` — la misma que gobierna CORS — y sirve
tanto si cada técnico tiene su PC como si hay servidor compartido.

Por qué hacen falta las dos mitades:

* **Origin** — un sitio malicioso puede mandar un POST de formulario
  (y ahora mismo casi cualquier XHR) contra el backend: CORS le impide
  **leer** la respuesta, no **hacerla**. Con Origin fuera de la lista →
  403.
* **Host** — el DNS rebinding no manda Origin: para el browser la
  petición es same-origin (`evil.com` que resuelve a 127.0.0.1), así
  que sin validar el Host el atacante entra y **lee**. Con Host fuera
  de la lista → 403.

Y la advertencia de la auditoría, medida: si la lista no es la
configurada, la interfaz entera (Origin `5199` con el proxy de Vite)
queda rechazada **mientras los tests siguen verdes** — ellos no mandan
Origin. Por eso el guard usa exactamente `settings.cors_origin_list`:
el mismo origen que CORS sirve, el guard lo deja pasar; los dos nunca
se contradicen.
"""

from __future__ import annotations

import asyncio

import pytest

#: `/health` no toca base ni depende de nada: el blanco más limpio.
_SALUD = "/health"


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


# ─── Origin ──────────────────────────────────────────────────────────────────

def test_origin_no_configurado_se_rechaza(client):
    r = client.get(_SALUD, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403, r.text
    detalle = r.json()["detail"]
    assert "evil.example" in detalle, detalle
    assert "rigen" in detalle, detalle  # «Origen no permitido…»


def test_origin_configurado_pasa(client):
    from app.core.config import get_settings

    origen = get_settings().cors_origin_list[0]
    assert origen, "CORS_ORIGINS vino vacío"
    r = client.get(_SALUD, headers={"Origin": origen})
    assert r.status_code == 200, r.text


# ─── Host ────────────────────────────────────────────────────────────────────

def test_host_desconocido_se_rechaza(client):
    r = client.get(_SALUD, headers={"Host": "evil.example:8010"})
    assert r.status_code == 403, r.text
    detalle = r.json()["detail"]
    assert "evil.example" in detalle, detalle
    assert "ost" in detalle, detalle  # «Host no permitido…»


def test_host_local_pasa(client):
    for host in ("127.0.0.1:8010", "localhost:8010", "testserver"):
        r = client.get(_SALUD, headers={"Host": host})
        assert r.status_code == 200, (host, r.status_code, r.text)


# ─── Controles: lo que hoy hace todo el mundo ───────────────────────────────

def test_sin_origin_ni_host_raro_sigue_pasando(client):
    """El default de TestClient (Host `testserver`, sin Origin)."""
    assert client.get(_SALUD).status_code == 200


# ─── El websocket, que también trae ambas cabeceras ──────────────────────────

def test_websocket_tambien_lee_origin_y_host():
    """Si el guard no mira el scope `websocket`, el rebinding entra por
    ahí con la misma facilidad: el upgrade trae Origin y Host."""
    from app.api.origin_guard import OriginHostGuard

    enviados: list[dict] = []

    async def send(mensaje):
        enviados.append(mensaje)

    async def receive():
        raise AssertionError("una petición rechazada no llega a la app")

    guard = OriginHostGuard(
        app=None,
        allow_origins={"http://localhost:5199"},
        allow_hosts={"127.0.0.1", "localhost", "testserver"},
    )
    scope = {
        "type": "websocket",
        "headers": [
            (b"origin", b"http://evil.example"),
            (b"host", b"evil.example:8010"),
        ],
    }
    asyncio.run(guard(scope, receive, send))
    assert enviados and enviados[0]["status"] == 403, enviados
