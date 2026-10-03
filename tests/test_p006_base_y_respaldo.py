"""
tests/test_p006_base_y_respaldo.py
──────────────────────────────────
P0-06: la base siempre en el mismo sitio, un respaldo que sí sirve, y una
versión de esquema que impide romper las bases ya instaladas.

Tres defectos, tres grupos de pruebas:

1. **La ruta dependía del directorio de trabajo.** El default era
   ``sqlite:///./aerorf.db``, una ruta relativa. Arrancar por `start.bat`, por
   `uvicorn` desde otra carpeta o desde el IDE creaba un `aerorf.db` distinto
   en cada caso, y los expedientes guardados en uno no existían en el otro.
   Ese es el síntoma que se resume en «se perdieron los expedientes».

2. **El respaldo tenía que salir del archivo, no del disco.** Con WAL, las
   últimas escrituras viven en ``aerorf.db-wal`` hasta que un checkpoint las
   mueve al ``.db``. Copiar sólo el ``.db`` — ``shutil.copy`` — copia una base
   atrasada, y lo hace justo en el momento en que se copia: con el servidor
   corriendo. La prueba lo demuestra con una fila que está en el WAL y no en el
   archivo, así que quien sustituya la API de SQLite por un `copyfile` la pierde
   y la prueba revienta.

3. **No había versión de esquema.** ``PRAGMA user_version`` valía ``0`` en una
   base instalada, y ``create_all`` sólo crea tablas que faltan: es
   estructuralmente incapaz de añadir una columna o una restricción a una base
   existente. La primera columna nueva — y ``numero_expediente`` ya está
   pendiente de perder su nulabilidad — habría roto cada base en el campo.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from app.core.config import ROOT_DIR, RUTA_BASE_SQLITE, Settings, _anclar_sqlite
from app.database import lifecycle
from app.database.lifecycle import (
    BaseDeDatosMasNueva,
    VERSION_ESQUEMA,
    asegurar_version,
    crear_respaldo,
    ruta_archivo_sqlite,
)


def _filas(ruta: Path, tabla: str = "eventos") -> int:
    con = sqlite3.connect(str(ruta))
    try:
        return int(con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0])
    finally:
        con.close()


def _version(ruta: Path) -> int:
    con = sqlite3.connect(str(ruta))
    try:
        return int(con.execute("PRAGMA user_version").fetchone()[0])
    finally:
        con.close()


def _url_a_ruta(url: str) -> Path:
    assert url.startswith("sqlite:///"), f"url que no es un archivo: {url}"
    return Path(url[len("sqlite:///"):])


# ─── 1. La ruta no depende de dónde se arranque ──────────────────────────────

def test_el_default_de_la_base_es_absoluto(monkeypatch, tmp_path):
    """Sin DATABASE_URL, la base queda en la raíz del proyecto.

    El `chdir` es el punto entero: con el default anterior la ruta resolvía
    contra este directorio y no contra la raíz.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)

    ruta = _url_a_ruta(Settings().database_url)

    assert ruta.is_absolute(), f"ruta relativa, seguiría al directorio de trabajo: {ruta}"
    assert ruta == RUTA_BASE_SQLITE
    assert ruta == ROOT_DIR / "aerorf.db"


def test_una_ruta_relativa_configurada_tambien_se_ancla(monkeypatch, tmp_path):
    """Un .env que diga `sqlite:///./otra.db` no vuelve a ser relativa."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./otra.db")

    ruta = _url_a_ruta(Settings().database_url)

    assert ruta.is_absolute(), f"quedó relativa: {ruta}"
    assert ruta == ROOT_DIR / "otra.db"


def test_la_memoria_y_las_rutas_absolutas_no_se_tocan(monkeypatch, tmp_path):
    """Ni la memoria de los tests ni una ruta ya absoluta cambian de significado."""
    memoria = "sqlite:///:memory:"
    assert _anclar_sqlite(memoria) == memoria

    absoluta = "sqlite:///" + (Path(tmp_path) / "base.db").as_posix()
    assert _anclar_sqlite(absoluta) == absoluta

    otro_backend = "postgresql+psycopg://usuario:clave@host/base"
    assert _anclar_sqlite(otro_backend) == otro_backend


def test_ruta_archivo_sqlite_distingue_memoria_de_archivo():
    """Lo que no es un archivo no tiene respaldo ni versión: tiene que ser None."""
    assert ruta_archivo_sqlite("sqlite:///:memory:") is None
    assert ruta_archivo_sqlite("sqlite://") is None
    assert ruta_archivo_sqlite("postgresql+psycopg://h/db") is None
    assert ruta_archivo_sqlite("sqlite:///./aerorf.db") == ROOT_DIR / "aerorf.db"


# ─── 2. El respaldo llega a lo que la base tiene de verdad ───────────────────

def test_el_respaldo_incluye_lo_que_el_wal_aun_no_llego_al_archivo(tmp_path):
    """La fila está escrita y la copia del archivo la pierde.

    Ésta es la prueba que distingue la API de SQLite de un `shutil.copyfile`:
    si alguien la sustituye por copiar el archivo, `destino` tiene 0 filas y
    esto falla. La primera aserción documenta el porqué; la segunda es la que
    defiende el arreglo.
    """
    origen = tmp_path / "origen.db"
    con = sqlite3.connect(str(origen))
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE eventos (id INTEGER PRIMARY KEY, texto TEXT)")
        con.commit()
        # El esquema se fuerza al archivo principal, para que la copia ingenua
        # al menos abra y revele lo que le falta en vez de fallar al abrir.
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("INSERT INTO eventos (texto) VALUES ('escrita y sin checkpoint')")
        con.commit()
        # La conexión queda abierta a propósito: cerrarla haría el checkpoint y
        # la fila bajaría al .db, que es exactamente lo que no queremos medir.

        copia_ingenua = tmp_path / "copia-ingenua.db"
        shutil.copyfile(origen, copia_ingenua)

        destino = crear_respaldo(origen, tmp_path / "respaldos", conservar=5)

        assert _filas(copia_ingenua) == 0, (
            "la copia del archivo ahora sí perdería la fila: cambió la situación "
            "del WAL y hay que volver a mirar el respaldo"
        )
        assert destino is not None
        assert _filas(destino) == 1, "el respaldo no trajo la fila escrita en el WAL"
    finally:
        con.close()


def test_arrancar_crea_un_respaldo_en_la_carpeta_configurada(
    tmp_path, monkeypatch
):
    """El cableado: `init_db` hace el respaldo antes de tocar el esquema."""
    import app.database.database as dbmod

    origen = tmp_path / "base.db"
    con = sqlite3.connect(str(origen))
    con.execute("CREATE TABLE t (id INTEGER)")
    con.close()

    class _Ajustes:
        respaldos_activos = True
        respaldos_conservar = 3

    monkeypatch.setattr(dbmod, "DATABASE_URL", "sqlite:///" + origen.as_posix())
    monkeypatch.setattr(dbmod, "RUTA_RESPALDOS", tmp_path / "respaldos")
    monkeypatch.setattr(dbmod, "get_settings", lambda: _Ajustes)

    dbmod.init_db(create_all=False, mantenimiento=True)

    respaldos = list((tmp_path / "respaldos").glob("aerorf-*.db"))
    assert len(respaldos) == 1, f"esperaba un respaldo y hay {len(respaldos)}"


def test_sin_base_aun_no_hay_respaldo_y_no_era_un_error(tmp_path):
    """La primera ejecución no tiene nada que copiar: devuelve None, sin excepción."""
    assert crear_respaldo(tmp_path / "no-existe.db", tmp_path / "r", conservar=5) is None
    assert not (tmp_path / "r").exists()


def test_las_copias_viejas_se_borran_y_las_nuevas_se_quedan(tmp_path):
    """Rotación: se conservan las más recientes por fecha de modificación."""
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir()
    for i in range(4):
        archivo = carpeta / f"aerorf-2026010{i}-000000.db"
        archivo.write_bytes(b"respaldo")
        # mtime creciente: el 0 es el más viejo, el 3 el más nuevo.
        os.utime(archivo, (1_600_000_000 + i, 1_600_000_000 + i))

    lifecycle._rotar(carpeta, conservar=2)

    quedan = sorted(p.name for p in carpeta.glob("aerorf-*.db"))
    assert quedan == [
        "aerorf-20260102-000000.db",
        "aerorf-20260103-000000.db",
    ], f"sobrevivieron los equivocados: {quedan}"


def test_conservar_cero_deja_todo_borrado(tmp_path):
    """`RESPALDOS_CONSERVAR=0` es una forma de decir que no se guarde ninguno."""
    carpeta = tmp_path / "respaldos"
    carpeta.mkdir()
    (carpeta / "aerorf-20260101-000000.db").write_bytes(b"x")

    lifecycle._rotar(carpeta, conservar=0)

    assert list(carpeta.glob("aerorf-*.db")) == []


# ─── 3. La versión del esquema ───────────────────────────────────────────────

def test_arrancar_deja_la_base_en_la_version_actual(tmp_path):
    ruta = tmp_path / "nueva.db"
    sqlite3.connect(str(ruta)).close()

    assert _version(ruta) == 0
    assert asegurar_version(ruta) == VERSION_ESQUEMA
    assert _version(ruta) == VERSION_ESQUEMA
    # Repetir no cuesta nada ni vuelve a tocar la base.
    assert asegurar_version(ruta) == VERSION_ESQUEMA


def test_una_base_mas_nueva_no_se_toca(tmp_path):
    """La regla inversa: si la base es de una AeroRF más nueva, no se toca."""
    ruta = tmp_path / "futura.db"
    con = sqlite3.connect(str(ruta))
    con.execute("PRAGMA user_version = 99")
    con.close()

    with pytest.raises(BaseDeDatosMasNueva) as capturado:
        asegurar_version(ruta)

    mensaje = str(capturado.value)
    assert "No se modificó nada" in mensaje, f"mensaje sin decir qué no se tocó: {mensaje}"
    assert "99" in mensaje and str(VERSION_ESQUEMA) in mensaje
    assert _version(ruta) == 99, "la versión cambió a pesar del error"


def test_arrancar_con_una_base_mas_nueva_no_arranca(tmp_path, monkeypatch):
    """El cableado: `init_db` propaga el error antes de crear nada."""
    import app.database.database as dbmod

    origen = tmp_path / "futura.db"
    con = sqlite3.connect(str(origen))
    con.execute("PRAGMA user_version = 99")
    con.close()

    monkeypatch.setattr(dbmod, "DATABASE_URL", "sqlite:///" + origen.as_posix())

    with pytest.raises(BaseDeDatosMasNueva):
        dbmod.init_db(create_all=False, mantenimiento=True)

    assert _version(origen) == 99, "init_db modificó una base más nueva que la aplicación"


def test_las_sentencias_de_migracion_se_aplican_y_suben_la_version(
    tmp_path, monkeypatch
):
    """El mecanismo tiene que servir para una migración de verdad, no sólo para el sello."""
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(str(ruta))
    con.execute("CREATE TABLE eventos (id INTEGER PRIMARY KEY)")
    con.close()

    monkeypatch.setitem(
        lifecycle.MIGRACIONES,
        VERSION_ESQUEMA,
        ["ALTER TABLE eventos ADD COLUMN texto TEXT"],
    )

    assert asegurar_version(ruta) == VERSION_ESQUEMA

    con = sqlite3.connect(str(ruta))
    try:
        columnas = [r[1] for r in con.execute("PRAGMA table_info(eventos)")]
    finally:
        con.close()
    assert "texto" in columnas, f"la migración no corrió, columnas: {columnas}"
    assert _version(ruta) == VERSION_ESQUEMA


def test_una_migracion_que_falla_no_deja_la_version_avanzada(tmp_path, monkeypatch):
    """Si el paso revienta, la versión no avanza: no se puede quedar mintiendo."""
    ruta = tmp_path / "mala.db"
    con = sqlite3.connect(str(ruta))
    con.execute("CREATE TABLE eventos (id INTEGER PRIMARY KEY)")
    con.close()

    monkeypatch.setitem(
        lifecycle.MIGRACIONES,
        VERSION_ESQUEMA,
        ["ESTO NO ES SQL VÁLIDO"],
    )

    with pytest.raises(sqlite3.Error):
        asegurar_version(ruta)

    assert _version(ruta) == 0, "la versión avanzó con la migración rota"
