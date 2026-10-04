"""
tests/test_p001_p003_numero_obligatorio.py
──────────────────────────────────────────
P0-01 + P0-03, **juntos** como manda RETOMAR: `nullable=False` sobre
`numero_expediente` y limpieza de las filas ya guardadas. P0-06 (0.30.5)
les dio el respaldo y la versión de esquema que les faltaban.

Antes de esto el identificador del expediente podía perderse de dos
formas:

* **La base lo permitía**: la columna era anulable, así que cualquier
  escritura directa dejaba expedientes sin número.
* **La API lo hacía sola**: `PUT /expedientes/{id}` con
  `{"numero_expediente": null}` pasaba por `exclude_unset` (el `None`
  vino **explicitado**, no omitido), hacía `setattr(None)` y **commiteaba**
  — y sólo después la validación de la respuesta reventaba en 500.
  O sea: fila sucia **y** error en inglés, en ese orden.

La guarda mide los tres frentes:

1. **El esquema** declara `notnull=1` (la letra de P0-01).
2. **La API** no vuelve a fabricar filas sin número: `null` y vacío se
   rechazan en español y el número guardado queda intacto.
3. **La migración** (P0-03): una base vieja con filas `NULL`/vacías
   sube de versión **conservando las filas** y con un
   `SIN-NUMERO-{id}` — un marcador de ausencia, no un número
   inventado: no se borra nada (mediciones, eventos y vínculos siguen
   enteros) y el operador puede poner el número real después.

Más el camino de base nueva (los pasos de migración se las tienen que
arreglar contra una tabla que todavía no existe) y el control de que
crear sin número sigue siendo 422.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

_API = "/api/v1"

#: El DDL tal cual lo tenía la base instalada, copiado de sqlite_master.
_DDL_VIEJO = """
CREATE TABLE expedientes (
    id INTEGER NOT NULL,
    numero_expediente VARCHAR(50),
    freq_mhz FLOAT,
    aeropuerto VARCHAR(100),
    lat FLOAT,
    lon FLOAT,
    fecha_creacion DATETIME,
    fecha_actualizacion DATETIME,
    estado VARCHAR(20),
    severidad VARCHAR(20),
    inspector_responsable VARCHAR(100),
    observaciones TEXT,
    descripcion TEXT,
    PRIMARY KEY (id)
)
"""


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _crear(client, numero: str) -> dict:
    r = client.post(
        f"{_API}/expedientes/",
        json={"numero_expediente": numero, "freq_mhz": 121.5, "aeropuerto": "Ezeiza"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def _columna(db, nombre: str) -> tuple:
    filas = db.execute(text("PRAGMA table_info(expedientes)")).mappings().all()
    return tuple(next(f for f in filas if f["name"] == nombre).values())


def _tabla_vieja(ruta: Path) -> None:
    """Una base en versión 1: una fila `NULL`, una vacía y una real."""
    con = sqlite3.connect(str(ruta))
    try:
        con.execute(_DDL_VIEJO)
        con.execute("PRAGMA user_version = 1")
        con.executemany(
            "INSERT INTO expedientes (id, numero_expediente, freq_mhz) "
            "VALUES (?, ?, ?)",
            [(1, None, 121.5), (2, "", 118.9), (3, "EXP-REAL", 109.0)],
        )
        con.commit()
    finally:
        con.close()


# ─── P0-01: la letra del ítem ────────────────────────────────────────────────

def test_el_esquema_declara_numero_no_nulo(db):
    columna = _columna(db, "numero_expediente")
    assert columna[3] == 1, f"numero_expediente sigue anulable: {columna}"


# ─── La API deja de fabricar filas sin número ────────────────────────────────

def test_pushear_numero_nulo_se_rechaza(client, db):
    exp = _crear(client, "EXP-NULO")

    r = client.put(f"{_API}/expedientes/{exp['id']}", json={"numero_expediente": None})

    assert r.status_code == 422, r.status_code
    mensajes = [str(e.get("msg", "")) for e in r.json()["detail"]]
    assert any("no admite null" in m for m in mensajes), mensajes
    # Y lo más importante: el número guardado no se perdió en el intento.
    guardado = db.execute(
        text("SELECT numero_expediente FROM expedientes WHERE id = :i"),
        {"i": exp["id"]},
    ).scalar()
    assert guardado == "EXP-NULO", guardado


def test_pushear_numero_vacio_se_rechaza(client, db):
    exp = _crear(client, "EXP-ESPACIOS")

    r = client.put(f"{_API}/expedientes/{exp['id']}", json={"numero_expediente": "   "})

    assert r.status_code == 422, r.status_code
    mensajes = [str(e.get("msg", "")) for e in r.json()["detail"]]
    assert any("vacío" in m for m in mensajes), mensajes
    guardado = db.execute(
        text("SELECT numero_expediente FROM expedientes WHERE id = :i"),
        {"i": exp["id"]},
    ).scalar()
    assert guardado == "EXP-ESPACIOS", guardado


def test_crear_con_numero_vacio_se_rechaza(client):
    r = client.post(
        f"{_API}/expedientes/",
        json={"numero_expediente": "", "freq_mhz": 121.5, "aeropuerto": "Ezeiza"},
    )
    assert r.status_code == 422, r.status_code
    mensajes = [str(e.get("msg", "")) for e in r.json()["detail"]]
    assert any("vacío" in m for m in mensajes), mensajes


# ─── P0-03: la migración limpia sin borrar ───────────────────────────────────

def test_la_migracion_llena_los_null_y_versiona(tmp_path):
    from app.database.lifecycle import asegurar_version

    ruta = tmp_path / "legacy.db"
    _tabla_vieja(ruta)

    assert asegurar_version(ruta) == 2, "el esquema no subió a la versión 2"

    con = sqlite3.connect(str(ruta))
    try:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 2
        filas = {
            f[0]: f[1]
            for f in con.execute("SELECT id, numero_expediente FROM expedientes")
        }
        # Ninguna fila se borró: marcador de ausencia, no dato inventado.
        assert len(filas) == 3, filas
        assert filas[1] == "SIN-NUMERO-1", filas
        assert filas[2] == "SIN-NUMERO-2", filas
        assert filas[3] == "EXP-REAL", filas
        # Y la columna ya no admite null, con su índice único de siempre.
        columna = next(
            r for r in con.execute("PRAGMA table_info(expedientes)")
            if r[1] == "numero_expediente"
        )
        assert columna[3] == 1, columna
        indices = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'index' AND tbl_name = 'expedientes'"
            )
        ]
        assert "ix_expedientes_numero_expediente" in indices, indices
        assert "ix_expedientes_freq_mhz" in indices, indices
    finally:
        con.close()

    # Repetir no vuelve a tocar nada.
    assert asegurar_version(ruta) == 2


def test_una_base_nueva_atravesa_la_migracion(tmp_path):
    """Los pasos corren contra una tabla que todavía no existe: el
    `CREATE TABLE IF NOT EXISTS` de forma vieja los vuelve posibles."""
    from app.database.lifecycle import asegurar_version

    ruta = tmp_path / "recien-creada.db"
    assert asegurar_version(ruta) == 2

    con = sqlite3.connect(str(ruta))
    try:
        columna = next(
            r for r in con.execute("PRAGMA table_info(expedientes)")
            if r[1] == "numero_expediente"
        )
        assert columna[3] == 1, columna
        assert con.execute("SELECT COUNT(*) FROM expedientes").fetchone()[0] == 0
    finally:
        con.close()


# ─── Control: lo que ya era verdad y tiene que seguir siéndolo ────────────────

def test_crear_sin_numero_sigue_siendo_422(client):
    r = client.post(
        f"{_API}/expedientes/", json={"freq_mhz": 121.5, "aeropuerto": "Ezeiza"}
    )
    assert r.status_code == 422, r.status_code

    r = client.post(
        f"{_API}/expedientes/",
        json={
            "numero_expediente": None,
            "freq_mhz": 121.5,
            "aeropuerto": "Ezeiza",
        },
    )
    assert r.status_code == 422, r.status_code
