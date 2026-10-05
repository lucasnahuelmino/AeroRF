"""
tests/test_correlacion_temporal.py
──────────────────────────────────
P1 de la auditoría: la correlación decía «espacial y temporal» pero
comparaba el evento con las posiciones **actuales** — un evento de hace
tres días «correlizaba» con el tráfico de hoy —, y cada llamada traía
el estado global de OpenSky en vez de la caja que necesita.

Tres frentes, en el orden que pide la cola:

1. **La redacción**: los disclaimer tenían que decir cómo se compara
   el tiempo (o declararse espaciales). Se verifica por el texto que
   viaja en la respuesta, que es lo que el operador lee y lo que
   exporta.
2. **`observed_at`**: cuando el objeto tiene fecha de observación, la
   coincidencia se compara contra ella con la ventana
   `CORRELACION_VENTANA_TEMPORAL_S` (600 s): dentro cuenta, fuera se
   reporta en `fuera_de_ventana` y no se cuenta. Sin `observed_at` no
   hay nada que comparar y la respuesta se declara `espacial`.
3. **Créditos**: las tres rutas que traían estados a mano piden ahora
   la caja alrededor del objeto (`get_states_in_box`); la caja de
   50 nm cabe en el tramo de 1 crédito de `estimate_states_credits`
   (área ≤ 25 sq-deg).

El control puro — las bandas siguen contando lo espacial — es
`test_control_bandas_sigue_contando_lo_espacial`, verde desde antes.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

#: El prefijo real: `main.py` monta los routers con `settings.api_prefix`.
_API = "/api/v1"

#: Ventana que las pruebas exigen (y que el código tiene que cumplir):
#: la constante del backend no se importa a propósito — si el número
#: cambia, la prueba lo dice con su propio literal.
_VENTANA_S = 600


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


class _FalsoServicio:
    """Sirve estados y anota cómo se le pidió (global vs caja)."""

    def __init__(self, estados=None):
        self.configured = True
        self.estados = estados or []
        self.llamadas: list[tuple[str, object]] = []

    async def get_states(self, **kw):
        self.llamadas.append(("global", kw))
        return {"states": self.estados}

    async def get_states_in_box(self, lat_min, lon_min, lat_max, lon_max):
        self.llamadas.append(("caja", (lat_min, lon_min, lat_max, lon_max)))
        return {"states": self.estados}


def _crear_evento(client, observed_at: datetime | None):
    cuerpo = {
        "type": "point",
        "name": "Evento de prueba",
        "latitude": -34.6,
        "longitude": -58.4,
    }
    if observed_at is not None:
        cuerpo["observed_at"] = observed_at.isoformat()
    r = client.post(f"{_API}/map/objects", json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _estado(ahora: float, con_hora=True) -> dict:
    """Estado a 0 km del evento, con el tiempo que se le pida."""
    ts = int(ahora) if con_hora else None
    return {
        "icao24": "abc123",
        "callsign": "TST1",
        "latitude": -34.6,
        "longitude": -58.4,
        "altitude": 3000.0,
        "velocity": 200.0,
        "heading": 90.0,
        "on_ground": False,
        "time_position": ts,
        "last_contact": ts,
    }


def _correlizar(client, oid, states):
    return client.post(
        f"{_API}/correlation/rf-aircraft",
        json={
            "object_id": oid,
            "radii_nm": [5, 10, 20, 50],
            "states": states,
        },
    )


def _recuento(data: dict) -> int:
    """Aeronaves distintas dentro del radio máximo pedido.

    Las bandas son acumulativas (todo lo de 5 nm también está en 10, 20
    y 50), así que el total es el conteo de la última banda, no la suma.
    """
    if not data["bands"]:
        return 0
    return data["bands"][-1]["count"]


def _assert_caja(llamada, lat0: float, lon0: float, radio_nm: float):
    """La llamada tiene que ser la caja, y la caja tiene que ser honesta."""
    metodo, args = llamada
    assert metodo == "caja", (
        f"se pidió `{metodo}`: traer el estado global es traer todo el "
        "cielo cuando sólo se necesita la caja del radio pedido"
    )
    lat_min, lon_min, lat_max, lon_max = args
    # Centrada en el objeto, simétrica.
    assert lat_min < lat0 < lat_max, llamada
    assert lon_min < lon0 < lon_max, llamada
    assert abs((lat0 - lat_min) - (lat_max - lat0)) < 1e-9, llamada
    # Cubre el radio pedido (50 nm ≈ 92,6 km)…
    medio_lat_m = (lat_max - lat_min) / 2 * 111_320
    assert medio_lat_m >= radio_nm * 1852 * 0.99, (
        f"la caja sólo alcanza {medio_lat_m:.0f} m y el radio es "
        f"{radio_nm * 1852:.0f} m: se dejaría avión fuera"
    )
    # …y sigue en el tramo de 1 crédito (área ≤ 25 sq-deg).
    area = (lat_max - lat_min) * (lon_max - lon_min)
    assert area <= 25, f"caja de {area:.1f} sq-deg: saldría del tramo de 1 crédito"


# ─── 1. observed_at: la comparación que faltaba ──────────────────────────────

def test_evento_viejo_no_se_correliza_con_el_trafico_de_hoy(client):
    """El caso de la auditoría: evento de hace 3 días vs estados de ahora."""
    hace3d = datetime.utcnow() - timedelta(days=3)
    oid = _crear_evento(client, hace3d)

    r = _correlizar(client, oid, [_estado(time.time())])
    assert r.status_code == 200, r.text
    data = r.json()

    assert data.get("comparacion") == "espacial_y_temporal", data.get("comparacion")
    assert data.get("fuera_de_ventana") == 1, data.get("fuera_de_ventana")
    assert _recuento(data) == 0, (
        f"un evento de hace 3 días no puede declarar "
        f"{_recuento(data)} aeronaves contemporáneas"
    )
    assert data["nearest"] is None, data["nearest"]


def test_evento_recien_observado_sigue_correlizando(client):
    """El flujo en vivo: evento hace 30 s, estados de ahora → cuenta."""
    recien = datetime.utcnow() - timedelta(seconds=30)
    oid = _crear_evento(client, recien)

    r = _correlizar(client, oid, [_estado(time.time())])
    assert r.status_code == 200, r.text
    data = r.json()

    assert data.get("comparacion") == "espacial_y_temporal"
    assert data.get("fuera_de_ventana") == 0, data.get("fuera_de_ventana")
    assert _recuento(data) == 1, data["bands"]
    delta = data["bands"][0]["aircraft"][0].get("delta_t_s")
    assert delta is not None, "la coincidencia no declara su delta temporal"
    assert abs(delta) <= _VENTANA_S, delta
    assert data["nearest"] is not None, data["nearest"]


def test_control_bandas_sigue_contando_lo_espacial(client):
    """CONTROL (verde antes y después): sin fecha no se rompe lo espacial."""
    oid = _crear_evento(client, None)

    r = _correlizar(client, oid, [_estado(time.time())])
    assert r.status_code == 200, r.text
    data = r.json()

    assert _recuento(data) == 1, data["bands"]
    assert data["nearest"] is not None, data["nearest"]


def test_objeto_sin_fecha_se_declara_espacial(client):
    """Sin `observed_at` no hay nada que comparar, y la respuesta lo dice."""
    oid = _crear_evento(client, None)

    r = _correlizar(client, oid, [_estado(time.time())])
    assert r.status_code == 200, r.text
    data = r.json()

    assert data.get("comparacion") == "espacial", data.get("comparacion")
    assert data.get("ventana_temporal_s") is None, data.get("ventana_temporal_s")
    assert data.get("fuera_de_ventana") is None, data.get("fuera_de_ventana")
    assert data.get("observado_en") is None, data.get("observado_en")
    delta = data["bands"][0]["aircraft"][0].get("delta_t_s")
    assert delta is None, delta


def test_estados_sin_hora_no_prueban_nada_temporalmente(client):
    """Estado sin `last_contact` ni `time_position`: no se puede afirmar
    que estuvo ahí a la hora del evento, así que no cuenta."""
    recien = datetime.utcnow() - timedelta(seconds=30)
    oid = _crear_evento(client, recien)

    r = _correlizar(client, oid, [_estado(time.time(), con_hora=False)])
    assert r.status_code == 200, r.text
    data = r.json()

    assert data.get("fuera_de_ventana") == 1, data.get("fuera_de_ventana")
    assert _recuento(data) == 0, data["bands"]


# ─── 2. La redacción ─────────────────────────────────────────────────────────

def test_disclaimer_declara_como_compara_el_tiempo(client):
    """El disclaimer viaja en cada respuesta y en cada export."""
    recien = datetime.utcnow() - timedelta(seconds=30)
    oid = _crear_evento(client, recien)

    r = _correlizar(client, oid, [_estado(time.time())])
    assert r.status_code == 200, r.text
    discl = r.json()["disclaimer"]

    assert "observed_at" in discl, discl
    assert "delta_t_s" in discl, discl
    assert "NO implica causalidad" in discl, discl


def test_disclaimer_de_la_vista_por_aeronave_es_espacial(client, monkeypatch):
    """Esa vista no compara momentos: la lista es por cercanía, y el
    texto no puede prometer una comparación que no existe."""
    fake = _FalsoServicio(estados=[_estado(time.time())])
    monkeypatch.setattr(
        "app.api.routes.correlation.get_opensky_service", lambda: fake
    )

    r = client.get(f"{_API}/correlation/aircraft/abc123")
    assert r.status_code == 200, r.text
    discl = r.json()["disclaimer"]

    assert "sin comparación de momentos" in discl, discl
    assert "NO implica causalidad" in discl, discl


# ─── 3. La caja en vez del mundo ─────────────────────────────────────────────

def test_rf_aircraft_pide_la_caja_no_el_mundo(client, monkeypatch):
    oid = _crear_evento(client, None)
    fake = _FalsoServicio(estados=[_estado(time.time())])
    monkeypatch.setattr(
        "app.api.routes.correlation.get_opensky_service", lambda: fake
    )

    r = client.post(
        f"{_API}/correlation/rf-aircraft",
        json={"object_id": oid, "radii_nm": [5, 10, 20, 50]},
    )
    assert r.status_code == 200, r.text
    assert len(fake.llamadas) == 1, fake.llamadas
    _assert_caja(fake.llamadas[0], -34.6, -58.4, 50)


def test_object_get_pide_la_caja(client, monkeypatch):
    oid = _crear_evento(client, None)
    fake = _FalsoServicio(estados=[_estado(time.time())])
    monkeypatch.setattr(
        "app.api.routes.correlation.get_opensky_service", lambda: fake
    )

    r = client.get(f"{_API}/correlation/object/{oid}?radii_nm=5,10,20,50")
    assert r.status_code == 200, r.text
    assert len(fake.llamadas) == 1, fake.llamadas
    _assert_caja(fake.llamadas[0], -34.6, -58.4, 50)


def test_flights_correlate_pide_la_caja(client, monkeypatch):
    oid = _crear_evento(client, None)
    fake = _FalsoServicio(estados=[_estado(time.time())])
    monkeypatch.setattr(
        "app.api.routes.flights.get_opensky_service", lambda: fake
    )

    r = client.get(f"{_API}/flights/correlate/{oid}?radii_nm=5,10,20,50")
    assert r.status_code == 200, r.text
    assert len(fake.llamadas) == 1, fake.llamadas
    _assert_caja(fake.llamadas[0], -34.6, -58.4, 50)


def test_flights_correlate_evento_viejo_sin_coincidencias(client, monkeypatch):
    """La misma regla temporal en la ruta hermana de `/flights/correlate`."""
    hace3d = datetime.utcnow() - timedelta(days=3)
    oid = _crear_evento(client, hace3d)
    fake = _FalsoServicio(estados=[_estado(time.time())])
    monkeypatch.setattr(
        "app.api.routes.flights.get_opensky_service", lambda: fake
    )

    r = client.get(f"{_API}/flights/correlate/{oid}?radii_nm=5,10,20,50")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data.get("comparacion") == "espacial_y_temporal", data.get("comparacion")
    assert data.get("fuera_de_ventana") == 1, data.get("fuera_de_ventana")
    assert _recuento(data) == 0, data["bands"]
