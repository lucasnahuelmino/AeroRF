"""
tests/test_textos_espanol_backend.py
────────────────────────────────────
Los últimos textos en inglés del backend, de una. La cola de RETOMAR los
anotó pieza por pieza — ws.py, el aviso de arranque, expedientes.py,
flights.py, correlation.py, map.py — y el barrido encontró más de lo
mismo en map_service, flight_service, opensky_service y cache: unas 40
frases de una línea repartidas en 12 archivos.

Regla del proyecto: lo que el operador lee está en español. La guarda es
doble:

* **en vivo** — los endpoints de la cola, pedidos de verdad y leídos en
  español. Antes de arreglar, cada una de éstas devolvía la frase en
  inglés;
* **portero de código** — el texto viejo exacto no vuelve a aparecer en
  su archivo (el patrón de ``test_error_icao24``). Un pedido por cada
  frase sería teatro; el scan cubre además las que no tienen ruta
  propia (el frame del websocket y el aviso de arranque).

Fuera del alcance, con la razón escrita:

* ``geo.py require_latlon`` — nadie lo llama: es código muerto y su
  ``ValueError`` no llega a ninguna respuesta.
* ``rf_expediente`` y su ``except Exception → 500 str(exc)`` — otra
  clase de defecto (el 500 que F2-05 manda que no exista), no prosa.
* Lo que escriben httpx, SQLite o el propio OpenSky arriba de nosotros:
  texto de terceros, se traduce donde nace la frase nuestra.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

_API = "/api/v1"
_RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _detalle(respuesta) -> str:
    """El `detail` como texto, sea string o lista de errores de Pydantic."""
    detalle = respuesta.json()["detail"]
    if isinstance(detalle, list):
        return " ".join(str(e.get("msg", "")) for e in detalle)
    return str(detalle)


def _crear_punto(client, con_posicion: bool = True) -> int:
    cuerpo = {"type": "point", "name": "Punto de texto"}
    if con_posicion:
        cuerpo.update({"latitude": -34.6, "longitude": -58.4})
    r = client.post(f"{_API}/map/objects", json=cuerpo)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ─── En vivo: los endpoints que la cola nombró ────────────────────────────────


def test_map_404_en_espanol(client, db):
    r = client.get(f"{_API}/map/objects/9999")
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "No existe el objeto 9999."


def test_expediente_404_en_espanol(client, db):
    r = client.get(f"{_API}/expedientes/9999")
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "No existe el expediente 9999."


def test_expediente_repetido_en_espanol(client, db):
    cuerpo = {
        "numero_expediente": "EXP-TEXTOS",
        "freq_mhz": 121.5,
        "aeropuerto": "Ezeiza",
    }
    alta = client.post(f"{_API}/expedientes/", json=cuerpo)
    assert alta.status_code in (200, 201), alta.text

    r = client.post(f"{_API}/expedientes/", json=cuerpo)
    assert r.status_code == 400, r.text
    detalle = _detalle(r)
    assert "Ya existe" in detalle, detalle
    assert "already exists" not in detalle, detalle


def test_rf_expediente_404_en_espanol(client, db):
    r = client.get(f"{_API}/rf/expedientes/9999/candidates")
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "No existe el expediente 9999."


def test_correlacion_404_en_espanol(client, db):
    r = client.get(f"{_API}/correlation/object/9999")
    assert r.status_code == 404, r.text
    detalle = r.json()["detail"]
    assert "No existe el objeto" in detalle, detalle
    assert "not found" not in detalle, detalle


def test_correlacion_sin_posicion_en_espanol(client, db):
    oid = _crear_punto(client, con_posicion=False)

    r = client.get(f"{_API}/correlation/object/{oid}")

    assert r.status_code == 400, r.text
    detalle = r.json()["detail"]
    assert "no tiene posición" in detalle, detalle
    assert "has no position" not in detalle, detalle


def test_radios_invalidos_en_espanol(client, db):
    oid = _crear_punto(client)

    r = client.post(
        f"{_API}/correlation/rf-aircraft",
        json={"object_id": oid, "radii_nm": ["abc"], "states": []},
    )

    assert r.status_code == 400, r.text
    detalle = r.json()["detail"]
    assert "radii_nm debe ser una lista de números" in detalle, detalle
    assert "must be a list" not in detalle, detalle


def test_icao24_invalido_en_espanol(client, db):
    r = client.get(f"{_API}/flights/lvkcc/flights")
    assert r.status_code == 422, r.text
    detalle = _detalle(r)
    # El mensaje compartido explica el camino: un callsign escrito donde
    # iba un ICAO24, y que ese campo sí funciona.
    assert "callsign" in detalle.lower(), detalle
    assert "Invalid ICAO24" not in detalle, detalle


def test_marcas_de_tiempo_futuras_en_espanol(client, db):
    futuro = int(time.time()) + 30 * 86400
    r = client.get(
        f"{_API}/flights/abc123/flights?begin={futuro}&end={futuro + 3600}"
    )
    assert r.status_code == 400, r.text
    detalle = _detalle(r)
    assert "no acepta marcas de tiempo futuras" in detalle, detalle
    assert "does not accept" not in detalle, detalle


def test_end_mayor_que_begin_en_espanol(client, db):
    ahora = int(time.time())
    r = client.get(
        f"{_API}/flights/abc123/flights?begin={ahora + 7200}&end={ahora + 3600}"
    )
    assert r.status_code == 400, r.text
    detalle = _detalle(r)
    assert "debe ser mayor" in detalle, detalle
    assert "must be greater" not in detalle, detalle


def test_sesion_inexistente_en_espanol(client, db):
    r = client.post(f"{_API}/flights/sessions/9999/start")
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "No existe la sesión de vuelo 9999."


def test_nivel_de_registro_invalido_en_espanol(client, db):
    r = client.post(f"{_API}/system/logs/level?level=BOGUS")
    assert r.status_code == 400, r.text
    detalle = _detalle(r)
    assert "Nivel de registro inválido" in detalle, detalle
    assert "Invalid log level" not in detalle, detalle


# ─── Portero: el texto viejo exacto no reaparece en su archivo ───────────────

#: (archivo, fragmento del mensaje viejo). El fragmento es literal: los
#: mensajes son de una línea y el scan es por archivo, así que un texto
#: legítimo en otro lado no lo puede volver a poner.
TEXTOS_VIEJOS = [
    ("app/main.py", "flight features disabled"),
    ("app/api/routes/ws.py", "Unknown action: {action!r}"),
    ("app/api/routes/expedientes.py", "Expediente not found"),
    ("app/api/routes/expedientes.py", "already exists"),
    ("app/api/routes/rf_expediente.py", "Expediente not found"),
    ("app/api/routes/correlation.py", "Object {object_id} not found"),
    ("app/api/routes/correlation.py", "has no position, so it cannot be correlated"),
    ("app/api/routes/correlation.py", "has no position."),
    ("app/api/routes/correlation.py", "radii_nm must be a list of numbers"),
    ("app/api/routes/flights.py", "Invalid ICAO24 {icao24!r}"),
    ("app/api/routes/flights.py", "`end` must be greater than `begin`"),
    ("app/api/routes/flights.py", "OpenSky does not accept future timestamps"),
    ("app/api/routes/flights.py", "At most "),
    ("app/api/routes/flights.py", "per query."),
    ("app/api/routes/flights.py", "bbox must be"),
    ("app/api/routes/flights.py", "Session {session_id} not found"),
    ("app/api/routes/flights.py", "Stop the session before deleting it."),
    ("app/api/routes/system.py", "Invalid log level"),
    ("app/api/routes/map.py", "Object {object_id} not found"),
    ("app/services/map_service.py", "Unknown object type {object_type!r}"),
    ("app/services/map_service.py", "Unknown status {status!r}"),
    ("app/services/map_service.py", "Unknown field(s):"),
    ("app/services/map_service.py", "Invalid WGS84 coordinate:"),
    ("app/services/map_service.py", "A note cannot be empty."),
    ("app/services/map_service.py", "Object {object_id} not found"),
    ("app/services/flight_service.py", "Invalid date {date!r}"),
    ("app/services/flight_service.py", "Invalid time {time_hint!r}"),
    ("app/services/flight_service.py", "has no position, so it cannot be correlated"),
    ("app/services/opensky_service.py", "OpenSky did not respond within"),
    ("app/services/opensky_service.py", "Could not reach OpenSky"),
    ("app/services/opensky_service.py", "rejected the access token twice"),
    ("app/services/opensky_service.py", "credit limit reached"),
    ("app/services/opensky_service.py", "rejected the request parameters"),
    ("app/services/opensky_service.py", "server error ({status}) on {path}"),
    ("app/services/opensky_service.py", "returned HTTP {status}"),
    ("app/services/opensky_service.py", "failed after retry."),
    ("app/services/opensky_service.py", "non-JSON response"),
    ("app/services/cache.py", "rate limit active for the"),
]


@pytest.mark.parametrize(
    "archivo,frase",
    TEXTOS_VIEJOS,
    ids=[f"{a}::{f[:28]}" for a, f in TEXTOS_VIEJOS],
)
def test_el_texto_viejo_no_vuelve(archivo: str, frase: str):
    fuente = (_RAIZ / archivo).read_text(encoding="utf-8")
    assert frase not in fuente, f"{archivo} volvió a escribir: {frase!r}"
