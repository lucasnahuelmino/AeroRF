"""
tests/test_async_sin_trabajo_sincrono.py
────────────────────────────────────────
P1 de la auditoría: un `async def` **sin `await` ni `async with`** es
trabajo síncrono disfrazado — y todo lo síncrono que se declare async
corre sobre el event loop de asyncio, congelando mientras tanto el
WebSocket de vuelos, el sondeo y cualquier otra request. La forma
correcta de decir «esto es síncrono» en FastAPI es `def`: el framework
lo manda al threadpool y el loop sigue girando.

El prerrequisito de SQLite que pide el ítem ya estaba cumplido y aquí
queda fijado: `_build_engine` pasa `check_same_thread=False` a **toda**
conexión sqlite (database.py), que es lo que permite que el threadpool
toque la base desde distintos hilos — con `StaticPool` (los tests en
memoria) la conexión única se comparte justamente por eso.

La guarda recorre `app/` con `ast` y exige, **función por función**,
que cada `async def` contenga `await`, `async with` o `async for`, o
bien que esté envuelto en `@asynccontextmanager` (el caso de
`lifespan`: el framework exige que sea async, punto — no es una
elección).

Lo que la guarda NO cubre, y por qué queda escrito:

* Los handlers de vuelos y correlación esperan OpenSky con `await`:
  son async de verdad y no entran en este ítem; sus llamadas cortas a
  la base entre `await` son de milisegundos (el arreglo de fondo —
  moverlas al threadpool — sería otra pieza, y medida).
* `main.py lifespan` es async porque `@asynccontextmanager` lo exige.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[1]
_APP = _RAIZ / "app"

_ES_ASYNC_DE_VERDAD = (ast.Await, ast.AsyncWith, ast.AsyncFor)


def _es_asynccontextmanager(nodo: ast.AsyncFunctionDef) -> bool:
    for dec in nodo.decorator_list:
        if isinstance(dec, ast.Name) and "asynccontextmanager" in dec.id:
            return True
        if isinstance(dec, ast.Attribute) and "asynccontextmanager" in dec.attr:
            return True
    return False


def _inventario() -> list[tuple[str, bool, int]]:
    """[(etiqueta, cumple_async_de_verdad, línea)] de cada `async def` de app/."""
    filas: list[tuple[str, bool, int]] = []
    for ruta in sorted(_APP.rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.AsyncFunctionDef):
                continue
            rel = ruta.relative_to(_RAIZ).as_posix()
            cumple = any(
                isinstance(h, _ES_ASYNC_DE_VERDAD) for h in ast.walk(nodo)
            ) or _es_asynccontextmanager(nodo)
            filas.append((f"{rel}:{nodo.lineno}::{nodo.name}", cumple, nodo.lineno))
    return filas


_INVENTARIO = _inventario()


def test_el_inventario_no_esta_vacio():
    """Si `ast` dejó de encontrar nada, la guarda no está mirando."""
    assert len(_INVENTARIO) >= 20, f"sólo {_INVENTARIO} async def en app/"


@pytest.mark.parametrize(
    "etiqueta,cumple,linea",
    _INVENTARIO,
    ids=[e for e, _, _ in _INVENTARIO],
)
def test_async_de_verdad(etiqueta: str, cumple: bool, linea: int):
    assert cumple, (
        f"{etiqueta} es `async def` sin await/async with/async for: trabajo "
        "síncrono corriendo sobre el event loop. Declárala `def` (FastAPI la "
        "manda al threadpool) o, si el framework exige async, envuélvela en "
        "@asynccontextmanager y anota por qué."
    )
