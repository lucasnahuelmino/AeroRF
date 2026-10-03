"""
database/lifecycle.py
─────────────────────
What runs against the database before the application starts using it: an
automatic backup, and a schema version.

Two defects this exists to close.

**The backup has to go through SQLite, not through the filesystem.** The
database runs in WAL mode — that is what lets the WebSocket recorder write
while the API reads — and in WAL mode the most recent commits live in
``aerorf.db-wal`` until a checkpoint moves them into ``aerorf.db``. Copying the
``.db`` file with ``shutil.copy`` therefore copies a database that is behind by
however much has been written since the last checkpoint, which is precisely the
state it is in while the server is running: the moment anyone would take a
backup. ``sqlite3.Connection.backup`` reads through the WAL and produces a file
that is complete and openable on its own.

Measured on this machine before the code existed: a ``-wal`` of 4 198 312 bytes
next to a ``.db`` of 647 168 bytes. The row counts turned out to be identical
with and without it — the WAL held page images, not records — so nothing had
actually been stranded *there*; the risk is not about that particular file, it
is about every backup taken while the server is live.

**There was no schema version at all.** ``PRAGMA user_version`` was ``0`` on an
installed database, and the only mechanism in the project is
``create_all``, which creates *missing* tables and is structurally incapable of
adding a column or a constraint to an existing one. So the first time a column
is added — ``numero_expediente`` losing its nullability is already queued up —
every database already in the field would break. The version is what makes that
step possible instead of destructive.

The rule when the stored version is *ahead* of this build: touch nothing and
say so in Spanish. A newer database is not a database to fix up.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.core.config import ROOT_DIR, get_settings
from app.core.logging import log

#: Current shape of the schema. Bump it when a table, column or constraint
#: changes, and append the statements that upgrade the *previous* version to
#: this one to `MIGRACIONES`.
#:
#: Version 1 is the baseline: it describes the schema as it already existed
#: when versioning was introduced, which is why there is no migration into it.
#: Existing databases are adopted into it by setting `user_version` alone —
#: `create_all` has already created whatever table they were missing.
VERSION_ESQUEMA = 1

#: ``version`` -> statements applied to a database sitting at ``version - 1``.
#:
#: Each element must be a **single** statement: they run through
#: ``cursor.execute``, which rejects anything else. One entry per element, in
#: order, and the version is bumped only after the whole step commits.
MIGRACIONES: dict[int, list[str]] = {}


class BaseDeDatosMasNueva(RuntimeError):
    """The stored schema is ahead of what this build understands.

    Raised before anything is created, migrated or backed up over, so the only
    thing that ever happens to such a database is a message.
    """

    def __init__(self, ruta: Path, encontrada: int, esperada: int) -> None:
        self.ruta = ruta
        self.encontrada = encontrada
        self.esperada = esperada
        super().__init__(
            f"La base «{ruta}» está en la versión {encontrada} del esquema y "
            f"esta aplicación de AeroRF sólo entiende la {esperada}. "
            "No se modificó nada: instale una versión más reciente de AeroRF "
            "o restaure un respaldo compatible."
        )


def ruta_archivo_sqlite(url: str) -> Path | None:
    """The filesystem path behind a SQLite URL, or `None` if there isn't one.

    `None` covers the two cases where a backup or a version has no meaning:
    an in-memory database, and a non-SQLite backend. A relative path is still
    resolved against the repository root — `_anclar_sqlite` normally makes that
    unnecessary, but a URL assembled by hand should not silently become
    working-directory dependent again.
    """
    if not url.startswith("sqlite:///"):
        return None
    resto = url[len("sqlite:///"):]
    if not resto or resto == ":memory:":
        return None
    ruta = Path(resto)
    return ruta if ruta.is_absolute() else (ROOT_DIR / ruta).resolve()


def crear_respaldo(
    ruta_origen: Path,
    destino_dir: Path,
    conservar: int,
) -> Path | None:
    """Copy the database into `destino_dir` and keep only the newest copies.

    Goes through SQLite's own backup API rather than the filesystem, so the
    result includes everything currently in the WAL (module docstring).

    Returns the path written, or `None` when there was nothing to copy — a
    database that does not exist yet is not a failed backup, it is the first
    run.
    """
    if not ruta_origen.exists():
        return None

    destino_dir.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = destino_dir / f"aerorf-{sello}.db"
    # Two starts inside the same second must not overwrite each other.
    salto = 1
    while destino.exists():
        destino = destino_dir / f"aerorf-{sello}-{salto}.db"
        salto += 1

    origen = sqlite3.connect(str(ruta_origen), timeout=30)
    copia = sqlite3.connect(str(destino), timeout=30)
    try:
        origen.backup(copia)
    finally:
        copia.close()
        origen.close()

    _rotar(destino_dir, conservar)
    return destino


def _rotar(destino_dir: Path, conservar: int) -> None:
    """Delete the oldest backups beyond `conservar`, newest first by mtime.

    ``conservar <= 0`` means keep none, so everything goes. To keep no backups
    at all in the first place the switch is ``RESPALDOS_ACTIVOS=0``; this is
    the narrower statement "keep no *history*", which is why it still creates
    the current one.

    A failure to delete is a warning, never an exception: refusing to start
    because a stale backup could not be removed would trade a working
    application for a tidier folder.
    """
    try:
        respaldos = sorted(
            destino_dir.glob("aerorf-*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError as exc:  # pragma: no cover - unreadable directory
        log.warning("db.respaldo_rotar", "no se pudo listar la carpeta de respaldos",
                    error=str(exc))
        return
    for viejo in respaldos[max(conservar, 0):]:
        try:
            viejo.unlink()
        except OSError as exc:  # pragma: no cover - locked file
            log.warning("db.respaldo_rotar", "no se pudo borrar un respaldo viejo",
                        archivo=viejo.name, error=str(exc))


def asegurar_version(ruta: Path) -> int:
    """Bring `ruta` up to `VERSION_ESQUEMA`, or refuse to touch it.

    Idempotent: a database already at the current version costs a single
    `PRAGMA user_version` read. A database **newer** than this build raises
    `BaseDeDatosMasNueva` before any statement runs.
    """
    con = sqlite3.connect(str(ruta), timeout=5)
    # No implicit transactions: the statements and the version bump have to
    # commit as one thing, otherwise a crash between them leaves a database
    # half-migrated and already claiming to be migrated.
    con.isolation_level = None
    try:
        encontrada = int(con.execute("PRAGMA user_version").fetchone()[0])

        if encontrada > VERSION_ESQUEMA:
            raise BaseDeDatosMasNueva(ruta, encontrada, VERSION_ESQUEMA)

        if encontrada == VERSION_ESQUEMA:
            return VERSION_ESQUEMA

        for paso in range(encontrada + 1, VERSION_ESQUEMA + 1):
            con.execute("BEGIN")
            try:
                for sentencia in MIGRACIONES.get(paso, []):
                    con.execute(sentencia)
                con.execute(f"PRAGMA user_version = {paso}")
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            log.info(
                "db.migracion",
                f"esquema llevado a la versión {paso}",
                desde=encontrada,
                hasta=paso,
            )

        # A database at 0 is one created before versioning existed. Its shape
        # already matches, so it is adopted rather than migrated — and saying
        # so matters, because "0 -> 1" with an empty step is easy to misread as
        # a migration that did nothing by accident.
        log.info(
            "db.version",
            "esquema sin versionar adoptado como versión 1"
            if encontrada == 0
            else f"esquema actualizado a la versión {VERSION_ESQUEMA}",
            version=VERSION_ESQUEMA,
            ruta=str(ruta),
        )
        return VERSION_ESQUEMA
    finally:
        con.close()
