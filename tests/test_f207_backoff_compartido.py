"""
tests/test_f207_backoff_compartido.py
──────────────────────────────────────
F2-07: un 429 de `/tracks` debe pausar también el feed en vivo.

La auditoría pide «un `BackoffController` para los tres pools: un 429 de
`/tracks` pausa también el feed en vivo». La estructura existía desde el
commit inicial — `OpenSkyService` crea **un** controlador y se lo pasa a
los tres `CreditAwareClient` — pero la estructura no es la garantía: la
garantía es el comportamiento. Nadie había medido el cruce entre pools.

Esta guarda lo mide en las dos direcciones, con la red mockeada y sin
gastar un crédito de verdad:

1. 429 en `/tracks/all` → la consulta de `/states/all` (lo que el feed
   en vivo hace cada 10 s) se niega **sin tocar la red**;
2. 429 en `/states/all` → la consulta de `/tracks/all` se niega igual.

Si algún día alguien le pone un controlador por pool a los tres, estas
pruebas se ponen rojas antes de que OpenSky empiece a banear a la
máquina — que es exactamente lo que el gate existe para evitar.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services.cache import RateLimitedError
from app.services.opensky_client import OpenSkyTokenManager
from app.services.opensky_service import OpenSkyService


def run(coro):
    return asyncio.run(coro)


def _service(handler) -> OpenSkyService:
    """Un servicio con red mockeada, como en `test_opensky.py`.

    El handler tiene la palabra: si contesta algo, eso manda. Si devuelve
    `None`, el wrapper responde el token con 200 (si no, todo el 401 y el
    refresh se cuelan en la prueba) y el resto con 404.
    """

    def _route(request) -> httpx.Response:
        resultado = handler(request)
        if resultado is not None:
            return resultado
        if "openid-connect/token" in str(request.url):
            return httpx.Response(
                200, json={"access_token": "t", "expires_in": 1800}
            )
        return httpx.Response(404, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(_route))
    tokens = OpenSkyTokenManager(
        client_id="cid", client_secret="csecret", http_client=client
    )
    return OpenSkyService(token_manager=tokens, http_client=client)


def _rate_limited(segundos: str) -> httpx.Response:
    return httpx.Response(
        429,
        json={"error": "quota"},
        headers={
            "X-Rate-Limit-Remaining": "0",
            "X-Rate-Limit-Retry-After-Seconds": segundos,
        },
    )


# ─── La dirección que nombra la auditoría ────────────────────────────────────

def test_429_en_tracks_pausa_al_feed_en_vivo():
    """Un tope en el pool de tracks debe frenar también `/states/all`."""
    estados: list[str] = []

    def handler(request) -> httpx.Response:
        url = str(request.url)
        if "tracks/all" in url:
            return _rate_limited("42")
        if "states/all" in url:
            estados.append(url)
            return httpx.Response(200, json={"time": 0, "states": []})
        return None

    svc = _service(handler)

    # El disparador: un 429 en el pool de tracks.
    with pytest.raises(RateLimitedError) as exc:
        run(svc.get_track("abc123"))
    assert exc.value.retry_after_s == 42
    assert svc.backoff.active is True

    # Y el feed — que consulta /states/all cada poll — queda pausado…
    with pytest.raises(RateLimitedError):
        run(svc.get_states())

    # …sin gastar crédito: ningún /states/all llegó a la red.
    assert estados == [], f"el feed siguió consultando la red: {estados}"
    assert svc.states.upstream_calls == 0


# ─── Y la inversa, para que el gate no sea de un solo sentido ───────────────

def test_429_en_states_pausa_a_las_trazas():
    """El tope del feed también frena el pool de tracks."""
    trazas: list[str] = []

    def handler(request) -> httpx.Response:
        url = str(request.url)
        if "states/all" in url:
            return _rate_limited("60")
        if "tracks/all" in url:
            trazas.append(url)
            return httpx.Response(
                200, json={"icao24": "abc123", "path": []}
            )
        return None

    svc = _service(handler)

    with pytest.raises(RateLimitedError):
        run(svc.get_states())
    assert svc.backoff.active is True

    with pytest.raises(RateLimitedError):
        run(svc.get_track("abc123"))

    assert trazas == [], f"las trazas siguieron consultándose: {trazas}"
    assert svc.tracks.upstream_calls == 0


# ─── El 429 que no pertenece a ningún pool ───────────────────────────────────

def test_429_del_token_tambien_cierra_el_gate():
    """La renovación del token también es OpenSky: un 429 ahí debe pausar.

    Antes este 429 no pasaba por el gate: `_headers` lo disfrazaba de
    `OpenSkyNotConfigured` («credenciales no configuradas», en inglés),
    el poller mandaba `not_configured` al frente y seguía renunciando
    cada 10 s contra un endpoint que nos estaba limitando. El feed no se
    pausaba y el operador quedaba informado de algo falso.
    """
    estados: list[str] = []

    def handler(request) -> httpx.Response | None:
        url = str(request.url)
        if "openid-connect/token" in url:
            return _rate_limited("42")
        if "states/all" in url:
            estados.append(url)
        return None

    svc = _service(handler)

    # Sin token válido: el primer paso es renovar, y ese 429 cierra el gate.
    with pytest.raises(RateLimitedError) as exc:
        run(svc.get_states())
    assert svc.backoff.active is True
    assert exc.value.retry_after_s >= 42  # respeta lo que pidió OpenSky

    # A partir de ahí, ninguna consulta de datos sale a la red.
    with pytest.raises(RateLimitedError):
        run(svc.get_track("abc123"))
    assert estados == [], f"el feed siguió consultando: {estados}"
