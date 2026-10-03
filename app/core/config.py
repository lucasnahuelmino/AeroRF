"""
core/config.py
──────────────
Application settings, loaded from environment variables and an optional
``.env`` file.

Security rules (spec §50):
  * OpenSky credentials live ONLY in the backend ``.env``.
  * They are never returned by any API endpoint.
  * They are never logged. ``__repr__`` masks them.

No third-party settings library is used: ``python-dotenv`` is already a
declared dependency and a frozen dataclass is enough for this surface.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Repository root = <root>/app/core/config.py -> parents[2]
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"

# Where the SQLite database lives, and where its backups go.
#
# Both are anchored to the repository root **on purpose**, because the previous
# default was `sqlite:///./aerorf.db`: a relative path, resolved against the
# working directory of whatever process happened to start the server. Starting
# through `start.bat`, through `uvicorn` from another folder, or through the IDE
# created a *different* `aerorf.db` in each case, and the expedientes saved in
# one did not exist in the other. That is the whole of the symptom usually
# reported as «se perdieron los expedientes»: no row was ever lost, the
# application was simply looking somewhere else.
#
# A relative path still wins if one is explicitly configured — it is resolved
# against here too, by `_anclar_sqlite` — so an existing `.env` that says
# `sqlite:///./aerorf.db` keeps pointing at the same file it pointed at before,
# no matter which directory the server is started from.
RUTA_BASE_SQLITE = ROOT_DIR / "aerorf.db"
RUTA_RESPALDOS = ROOT_DIR / "respaldos"

# Load .env without clobbering variables already present in the real
# environment, so container/system env always wins over the file.
load_dotenv(ENV_FILE, override=False)


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _anclar_sqlite(url: str) -> str:
    """Resolve a relative SQLite path against the repository root.

    `:memory:`, an absolute path, and anything that is not SQLite pass through
    untouched, so the test suite and an explicit `DATABASE_URL` keep behaving
    exactly as they did before. Only the case that was broken — a relative path
    that silently followed the working directory — changes.

    Returns a URL rather than a filesystem path, because that is what the
    settings field holds.
    """
    if not url.startswith("sqlite:///"):
        return url
    resto = url[len("sqlite:///"):]
    if not resto or resto == ":memory:":
        return url
    ruta = Path(resto)
    if ruta.is_absolute():
        return url
    return "sqlite:///" + (ROOT_DIR / ruta).resolve().as_posix()


@dataclass(frozen=True)
class Settings:
    """Immutable application configuration."""

    # ─── Application ──────────────────────────────────────────────────────
    app_name: str = field(default_factory=lambda: _env("APP_NAME", "AeroRF"))
    environment: str = field(default_factory=lambda: _env("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: _env_bool("DEBUG", False))
    api_prefix: str = field(default_factory=lambda: _env("API_PREFIX", "/api/v1"))

    # ─── Server ───────────────────────────────────────────────────────────
    host: str = field(default_factory=lambda: _env("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))

    # ─── Database ─────────────────────────────────────────────────────────
    # SQLite by default, always at the repository root. Set
    # DATABASE_URL=postgresql://... for PostgreSQL.
    #
    # `_anclar_sqlite` runs over whatever is configured: a relative path is
    # resolved against the root and never against the working directory, which
    # is what made two different ways of starting the server create two
    # different databases.
    database_url: str = field(
        default_factory=lambda: _anclar_sqlite(
            _env("DATABASE_URL", "sqlite:///" + RUTA_BASE_SQLITE.as_posix())
        )
    )
    sql_echo: bool = field(default_factory=lambda: _env_bool("SQL_ECHO", False))

    # ─── Startup maintenance ──────────────────────────────────────────────
    # A backup of the database is taken on every start, before anything is
    # written. Off only for the test suite, where the database is a temporary
    # file rebuilt per run and a backup would be pure noise.
    respaldos_activos: bool = field(
        default_factory=lambda: _env_bool("RESPALDOS_ACTIVOS", True)
    )
    #: How many backups to keep. Rotation deletes the oldest beyond this.
    respaldos_conservar: int = field(
        default_factory=lambda: _env_int("RESPALDOS_CONSERVAR", 10)
    )

    # ─── OpenSky Network (never exposed to the frontend) ──────────────────
    opensky_base_url: str = field(
        default_factory=lambda: _env("OPENSKY_BASE_URL", "https://opensky-network.org")
    )
    opensky_client_id: str = field(
        default_factory=lambda: _env("OPENSKY_CLIENT_ID", "")
    )
    opensky_client_secret: str = field(
        default_factory=lambda: _env("OPENSKY_CLIENT_SECRET", "")
    )
    # Renew the token this many seconds before it actually expires.
    opensky_token_margin_s: int = field(
        default_factory=lambda: _env_int("OPENSKY_TOKEN_MARGIN_S", 60)
    )
    opensky_timeout_s: float = field(
        default_factory=lambda: _env_float("OPENSKY_TIMEOUT_S", 30.0)
    )
    # OpenSky serves /states/all to anonymous callers from a 400-credit
    # daily pool, bucketed by IP. Verified live on 2026-09-25.
    # Turning this off makes every flight call require credentials.
    opensky_allow_anonymous: bool = field(
        default_factory=lambda: _env_bool("OPENSKY_ALLOW_ANONYMOUS", True)
    )

    # ─── Cache / credit control (spec §49) ───────────────────────────────
    # Each credit pool (states / tracks / flights) gets its own TTL so a
    # track lookup never serves a stale states answer or vice versa.
    cache_ttl_states_s: int = field(
        default_factory=lambda: _env_int("CACHE_TTL_STATES_S", 10)
    )
    cache_ttl_tracks_s: int = field(
        default_factory=lambda: _env_int("CACHE_TTL_TRACKS_S", 300)
    )
    #: The same cache, shortened for the poller that watches an airborne
    #: aircraft. A flight in progress has a route that changes every minute, so a
    #: five-minute cache makes the drawn line look frozen between jumps. This
    #: only spends credits while someone is following a flight that is in the air.
    cache_ttl_tracks_live_s: int = field(
        default_factory=lambda: _env_int("CACHE_TTL_TRACKS_LIVE_S", 30)
    )
    cache_ttl_flights_s: int = field(
        default_factory=lambda: _env_int("CACHE_TTL_FLIGHTS_S", 300)
    )
    # When OpenSky answers 429 we stop calling for a while.
    opensky_backoff_base_s: int = field(
        default_factory=lambda: _env_int("OPENSKY_BACKOFF_BASE_S", 30)
    )
    opensky_backoff_max_s: int = field(
        default_factory=lambda: _env_int("OPENSKY_BACKOFF_MAX_S", 900)
    )

    # ─── Live tracking ────────────────────────────────────────────────────
    live_poll_interval_s: int = field(
        default_factory=lambda: _env_int("LIVE_POLL_INTERVAL_S", 10)
    )
    # Hard cap from the spec (§25). Not configurable above 5.
    max_tracked_aircraft: int = 5

    # ─── Logging ──────────────────────────────────────────────────────────
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    log_file: str = field(default_factory=lambda: _env("LOG_FILE", ""))

    # ─── CORS ─────────────────────────────────────────────────────────────
    cors_origins: str = field(
        default_factory=lambda: _env(
            "CORS_ORIGINS",
            "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173",
        )
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_opensky_credentials(self) -> bool:
        """True when OAuth2 client credentials are configured."""
        return bool(self.opensky_client_id and self.opensky_client_secret)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"Settings(app={self.app_name!r}, env={self.environment!r}, "
            f"db={'sqlite' if self.is_sqlite else 'postgresql'}, "
            f"opensky={'configured' if self.has_opensky_credentials else 'NOT configured'})"
        )

    def masked(self) -> dict[str, object]:
        """Serialisable view safe to log or return from /api/system/config."""
        return {
            "app_name": self.app_name,
            "environment": self.environment,
            "api_prefix": self.api_prefix,
            "database": "sqlite" if self.is_sqlite else "postgresql",
            "opensky_configured": self.has_opensky_credentials,
            "opensky_allow_anonymous": self.opensky_allow_anonymous,
            "opensky_base_url": self.opensky_base_url,
            "max_tracked_aircraft": self.max_tracked_aircraft,
            "live_poll_interval_s": self.live_poll_interval_s,
            "cache_ttl_states_s": self.cache_ttl_states_s,
            "cache_ttl_tracks_s": self.cache_ttl_tracks_s,
            "cache_ttl_tracks_live_s": self.cache_ttl_tracks_live_s,
            "cache_ttl_flights_s": self.cache_ttl_flights_s,
        }


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Force a re-read of the environment. Intended for tests."""
    global _settings
    _settings = Settings()
    return _settings


# Module-level convenience, mirroring the usual `from ... import settings`.
settings = get_settings()
