"""
api/origin_guard.py
────────────────────
Middleware de `Origin`/`Host` (P0-07): defensa contra el CSRF de sitio
y contra DNS rebinding, acotada a los orígenes de CORS configurados.

La lista de orígenes es la **misma** que gobierna `CORSMiddleware`
(`settings.cors_origin_list`): cualquier origen al que CORS le sirve
pasa el guard, así que los dos nunca se contradicen — si mañana cambia
`CORS_ORIGINS`, cambian los dos, en el mismo .env.

Los hosts permitidos salen de `ALLOWED_HOSTS` (default: loopback y el
`testserver` de TestClient) más los hostnames de los orígenes
configurados: una sola lista que aprende de la otra.

Responde **403** con ``{"detail": ...}`` en español — el formato que
`describeError` del frontend ya entiende — y es ASGI puro para cubrir
también el scope ``websocket``: el upgrade trae `Origin` y `Host`, y si
no se miran, el rebinding entra por ahí con la misma facilidad.
"""

from __future__ import annotations

import json
from typing import Iterable
from urllib.parse import urlparse

from fastapi import FastAPI

from app.core.config import get_settings


def _normalise(value: str) -> str:
    return value.strip().lower().rstrip("/")


def _host_name(host: str) -> str:
    """Hostname del header Host: sin puerto y sin corchetes IPv6."""
    host = host.strip().lower()
    if host.startswith("["):
        cierre = host.find("]")
        if cierre != -1:
            return host[1:cierre]
    return host.split(":", 1)[0]


class OriginHostGuard:
    """Cierra el request cuando el Origin o el Host no está permitido."""

    def __init__(
        self, app, allow_origins: Iterable[str], allow_hosts: Iterable[str]
    ) -> None:
        self.app = app
        self.allow_origins = {_normalise(o) for o in allow_origins}
        self.allow_hosts = {_normalise(h) for h in allow_hosts}

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope["headers"]
        }

        # Un Origin presente y fuera de lista: el browser no debería
        # estar hablándonos desde ahí (CORS le habría negado la lectura;
        # esto le niega además la petición).
        origin = headers.get("origin")
        if origin is not None and _normalise(origin) not in self.allow_origins:
            await _deny(send, f"Origen no permitido: {origin}.")
            return

        # Sin Origin no hay CSRF que frenar — pero el DNS rebinding
        # justamente no manda Origin: valida el Host, que es lo único
        # que delata a `evil.com` resolviendo a 127.0.0.1.
        host = headers.get("host")
        if host is not None and _host_name(host) not in self.allow_hosts:
            await _deny(send, f"Host no permitido: {host}.")
            return

        await self.app(scope, receive, send)


async def _deny(send, detalle: str) -> None:
    cuerpo = json.dumps({"detail": detalle}, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(cuerpo)).encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": cuerpo})


def install_origin_guard(app: FastAPI) -> None:
    """Monta el guard con las listas configuradas (patrón de errors.py)."""
    settings = get_settings()
    allow_hosts = list(settings.allowed_host_list)
    # Los hostnames de los orígenes configurados siempre están permitidos:
    # una interfaz que CORS sirve, el guard la deja llegar.
    for origen in settings.cors_origin_list:
        host = urlparse(origen).hostname
        if host:
            allow_hosts.append(host)
    app.add_middleware(
        OriginHostGuard,
        allow_origins=settings.cors_origin_list,
        allow_hosts=allow_hosts,
    )
