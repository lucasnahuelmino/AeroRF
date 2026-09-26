"""
database/database.py
───────────────────
SQLAlchemy engine, session factory and schema bootstrap for AeroRF.

SQLite in development, PostgreSQL/PostGIS in production. The two are kept
interchangeable on purpose:

* Geometry lives in a JSON column (``MapObject.geometry``), which both
  backends support, so SQLite is a first-class citizen rather than a
  degraded fallback.
* Position lives in indexed ``Float`` columns, so bounding-box and
  distance-ordering queries are plain SQL with no spatial extension.

Migrating to PostGIS therefore means adding a ``geometry(Geometry, 4326)``
column and populating it from the existing JSON with
``ST_GeomFromGeoJSON``; no application code changes.
"""

from __future__ import annotations

import logging
from typing import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.logging import log

# Standardise log format early, before any module logs.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)-16s %(message)s",
)

Base = declarative_base()

_settings = get_settings()
DATABASE_URL = _settings.database_url


def _build_engine(url: str) -> Engine:
    """Create the engine with the right pool/connect settings per backend."""
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        # StaticPool keeps a single connection alive, which is what makes
        # the in-memory database used by the test suite work across
        # sessions and threads.
        poolclass = StaticPool if ":memory:" in url or url.endswith("://") else None
        engine = create_engine(
            url,
            connect_args=connect_args,
            echo=_settings.sql_echo,
            future=True,
            **({"poolclass": poolclass} if poolclass else {}),
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover
            cursor = dbapi_connection.cursor()
            # WAL lets the WebSocket recorder write while API reads happen.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        return engine

    # PostgreSQL / PostGIS. pool_pre_ping guards against connections
    # dropped by the server or a proxy while idle.
    return create_engine(
        url,
        echo=_settings.sql_echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
        future=True,
    )


engine = _build_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Schema bootstrap ────────────────────────────────────────────────────────

def init_db(create_all: bool = True) -> None:
    """Create tables and seed the default layers.

    Safe to call repeatedly: ``create_all`` is a no-op when the schema is
    already present, and seeding only inserts missing layer keys.
    """
    from app.models import (  # noqa: F401  (populate metadata)
        map_object,
        layer,
        tracking,
        rf,
        measurement,
        flight,
        expediente,
        medicion,
        evento_rf,
        espectro,
    )
    from app.models.constants import DEFAULT_LAYERS
    from app.models.layer import Layer

    if create_all:
        Base.metadata.create_all(bind=engine)
        log.info(
            "db.init",
            "schema ready",
            backend="sqlite" if _settings.is_sqlite else "postgresql",
            tables=len(Base.metadata.tables),
        )

    _seed_layers(Layer, DEFAULT_LAYERS)


def _seed_layers(layer_model, defaults) -> None:
    """Insert any missing default layer, preserving existing state."""
    db = SessionLocal()
    try:
        existing = {row[0] for row in db.query(layer_model.key).all()}
        added = 0
        for key, name, visible, opacity, order in defaults:
            if key in existing:
                continue
            db.add(
                layer_model(
                    key=key,
                    name=name,
                    visible=visible,
                    opacity=opacity,
                    order_index=order,
                    is_system=True,
                )
            )
            added += 1
        if added:
            db.commit()
            log.info("db.layers_seeded", f"{added} layers created", count=added)
    except Exception:  # pragma: no cover
        db.rollback()
        raise
    finally:
        db.close()


def reset_db() -> None:
    """Drop and recreate every table. Test helper only."""
    from app.models import (  # noqa: F401
        map_object, layer, tracking, rf, measurement, flight,
        expediente, medicion, evento_rf, espectro,
    )

    Base.metadata.drop_all(bind=engine)
    init_db(create_all=True)


def table_names() -> list[str]:
    """Introspection helper for diagnostics and the audit trail."""
    return sorted(inspect(engine).get_table_names())


def db_health() -> dict:
    """Report connectivity and the tables actually present."""
    from app.core.config import get_settings as _gs

    info: dict = {
        "url_scheme": DATABASE_URL.split(":", 1)[0],
        "connected": False,
        "tables": [],
        "error": None,
    }
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        info["connected"] = True
        info["tables"] = table_names()
    except Exception as exc:  # pragma: no cover
        info["error"] = str(exc)
    return info
