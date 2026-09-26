"""
api/routes/system.py
────────────────────
Diagnostics and metadata (spec §50, §51).

    GET /api/v1/system/status    backend, database and OpenSky health
    GET /api/v1/system/config    effective configuration (secrets masked)
    GET /api/v1/system/vocabulary closed vocabularies for the UI
    GET /api/v1/system/credits   OpenSky credit/cache statistics

``/api/v1/system/config`` reports *whether* credentials are configured but
never returns their value: there is no code path from this router to the
secret strings (spec §50).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.database.database import db_health, get_db
from app.services.cache import RateLimitedError
from app.services.opensky_service import (
    OpenSkyError,
    OpenSkyNotConfigured,
    get_opensky_service,
)

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/status")
def status(db: Session = Depends(get_db)):
    """Overall health of the backend, the database and the OpenSky link."""
    settings = get_settings()
    service = get_opensky_service()

    db_info = db_health()

    # Report the full service status in both modes: it declares which auth
    # mode is in use and, when anonymous, what that costs and what it
    # does not cover.
    opensky_info: dict = {
        "configured": service.configured,
        "auth_mode": "oauth2" if service.configured else "anonymous",
        "can_query_states": service.can_query_states,
        "detail": service.status(),
    }
    if not service.configured:
        opensky_info["message"] = (
            "Sin credenciales OAuth2. El tráfico en vivo funciona en modo "
            "anónimo (400 créditos diarios por IP, resolución 10 s). "
            "El historial de vuelos y las trayectorias requieren credenciales. "
            "Ver .env.example."
        )

    healthy = db_info["connected"]
    return {
        "status": "ok" if healthy else "degraded",
        "app": settings.app_name,
        "environment": settings.environment,
        "database": db_info,
        "opensky": opensky_info,
    }


@router.get("/config")
def config():
    """Effective configuration. Credentials are reported as booleans only."""
    return {"config": get_settings().masked()}


@router.get("/credits")
def credits():
    """OpenSky cache and credit-pool statistics.

    Lets the operator see whether the tool is actually hitting OpenSky or
    serving cached answers — the difference between a comfortable session
    and an exhausted daily quota.
    """
    service = get_opensky_service()
    if not service.configured:
        raise HTTPException(
            503, "OpenSky is not configured, so there is no credit usage to report."
        )
    return service.status()


@router.get("/vocabulary")
def vocabulary():
    """All closed vocabularies in one place, for the frontend."""
    from app.api.routes.map import get_vocabulary

    return get_vocabulary()


@router.get("/logs/recent")
def recent_logs(limit: int = 50):
    """Log levels currently in effect (full log tail is on stdout)."""
    import logging

    return {
        "root_level": logging.getLevelName(logging.getLogger("aerorf").level),
        "log_level": get_settings().log_level,
        "log_file": get_settings().log_file or None,
        "limit": limit,
        "note": "Structured logs are written to stdout; see backend.log.",
    }


@router.post("/logs/level")
def set_log_level(level: str = "INFO"):
    """Change the log level at runtime (diagnostics only)."""
    level = level.upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise HTTPException(400, "Invalid log level")
    setup_logging(level=level, force=True)
    return {"log_level": level}
