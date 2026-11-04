"""
app/api/errors.py
─────────────────
Errores en español, y sin 500 de por medio (F2-05).

Tres huecos que cierra este módulo:

1. FastAPI valida con Pydantic y responde **422 en inglés**
   («Input should be a valid boolean…»). `describeError` del frontend une
   `loc: msg` y lo pinta tal cual en pantalla.
2. Las rutas con `body: dict` validan **dentro** del handler: ese
   `ValidationError` no llega al middleware de validación de FastAPI y
   salía como 500 «Internal Server Error».
3. Lo que Pydantic deja pasar y SQLite rechaza (FK que no existe, columna
   NOT NULL con `null`) también terminaba en 500.

Regla del proyecto: ninguna entrada del operador devuelve 500, y todo lo
que llega a la pantalla está en español. El campo `type` conserva el
código original de Pydantic — es un identificador para máquinas, no
prosa, y `describeError` no lo muestra — pero `msg`, que sí se muestra,
siempre sale de acá traducido.
"""

from __future__ import annotations

from typing import Any, Iterable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.logging import log

#: `type` de Pydantic → lo que lee el operador. Lo que no esté en la tabla
#: cae en `_GENERICO`: en español igual, porque un 422 en inglés es un
#: defecto. Los códigos que aparecen son los que produce este proyecto
#: (`schemas_gis.py` y las rutas con `body: dict`).
_MENSAJES: dict[str, str] = {
    "missing": "es obligatorio",
    "none_not_allowed": "no admite null",
    "string_type": "debe ser un texto",
    "string_too_long": "supera el largo máximo permitido",
    "string_pattern_mismatch": "no cumple el formato esperado",
    "int_parsing": "debe ser un número entero",
    "int_type": "debe ser un número entero",
    "int_from_float": "debe ser un número entero, sin decimales",
    "float_parsing": "debe ser un número",
    "float_type": "debe ser un número",
    "bool_parsing": "debe ser true o false",
    "bool_type": "debe ser true o false",
    "dict_type": "debe ser un objeto JSON",
    "model_attributes_type": "debe ser un objeto JSON",
    "list_type": "debe ser una lista",
    "json_invalid": "no es JSON válido",
    "json_type": "debe ser JSON",
    "greater_than": "debe ser mayor que {gt}",
    "greater_than_equal": "debe ser mayor o igual que {ge}",
    "less_than": "debe ser menor que {lt}",
    "less_than_equal": "debe ser menor o igual que {le}",
    "extra_forbidden": "no es un campo permitido",
    "enum": "no es un valor del listado permitido",
    "url_parsing": "no es una URL válida",
    "url_scheme": "no usa un esquema de URL válido",
    "datetime_parsing": "no es una fecha y hora válida",
    "date_parsing": "no es una fecha válida",
    "time_parsing": "no es una hora válida",
}

_GENERICO = "dato inválido"

#: Pydantic envuelve el `ValueError` de nuestros validadores con esto.
_PREFIJO_VALUE_ERROR = "Value error, "

_MENSAJE_INTEGRIDAD = (
    "La operación violó una restricción de la base de datos. Revisá los "
    "datos enviados: puede ser una capa o un expediente que no existe, o "
    "un campo obligatorio vacío. El detalle quedó en el log del servidor."
)


def mensaje_espanol(error: dict[str, Any]) -> str:
    """El texto humano de un error de Pydantic, siempre en español."""
    tipo = str(error.get("type", ""))
    if tipo == "value_error":
        # Lo escribió un validador nuestro (`schemas_gis.py`) y ya está en
        # español: sólo hay que quitar el envoltorio de Pydantic.
        msg = str(error.get("msg", ""))
        if msg.startswith(_PREFIJO_VALUE_ERROR):
            msg = msg[len(_PREFIJO_VALUE_ERROR):]
        return msg or _GENERICO

    plantilla = _MENSAJES.get(tipo, _GENERICO)
    if "{" not in plantilla:
        return plantilla
    try:
        return plantilla.format(**(error.get("ctx") or {}))
    except (KeyError, IndexError, ValueError):
        return _GENERICO


def detalle_espanol(errors: Iterable[Any]) -> list[dict[str, Any]]:
    """`errors()` de Pydantic → el `detail` que `describeError` renderiza.

    Sólo `type`, `loc` y `msg`: ni `input` (no tiene por qué ecoar el
    cuerpo que mandó el cliente) ni `url` (un enlace a la documentación
    en inglés que nadie va a seguir).
    """
    traducidos: list[dict[str, Any]] = []
    for error in errors:
        error = dict(error)
        traducidos.append(
            {
                "type": str(error.get("type", "")),
                "loc": list(error.get("loc", ())),
                "msg": mensaje_espanol(error),
            }
        )
    return traducidos


def _validacion(request: Request, exc: Any) -> JSONResponse:
    """422 con el `msg` traducido, sea del middleware o del handler."""
    return JSONResponse(
        status_code=422, content={"detail": detalle_espanol(exc.errors())}
    )


def _integridad(request: Request, exc: IntegrityError) -> JSONResponse:
    """La entrada pasó Pydantic y la frenó SQLite: 400, no 500.

    Red de seguridad para cualquier FK o columna NOT NULL que no tenga
    chequeo propio (los de capa y expediente sí lo tienen, con mensaje
    preciso). La causa real va al log: el operador no necesita ver SQL.
    """
    causa = str(getattr(exc, "orig", None) or exc)
    log.error(
        "db.integrity_error",
        "restricción de la base de datos violada",
        path=request.url.path,
        causa=causa,
    )
    return JSONResponse(status_code=400, content={"detail": _MENSAJE_INTEGRIDAD})


def install_error_handlers(app: FastAPI) -> None:
    """Se llama una sola vez, desde `app.main`."""
    # El de FastAPI: pisa el 422 en inglés que venía por defecto.
    app.add_exception_handler(RequestValidationError, _validacion)
    # Las rutas con `body: dict` validan dentro del handler y su
    # `ValidationError` no pasa por el middleware: sin éste, salía 500.
    app.add_exception_handler(ValidationError, _validacion)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, _integridad)
