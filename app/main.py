"""
app/main.py
───────────
AeroRF — plataforma GIS para investigación de interferencias
radioeléctricas aeronáuticas.

Application entry point.

    uvicorn app.main:app --reload --port 8000

Interactive docs:  /docs   (Swagger)   /redoc   (ReDoc)

What is registered here
───────────────────────
* **Legacy SIARI, untouched** — the RF calculation engine and the
  expediente CRUD that were already working: ``rf``, ``rf_expediente``,
  ``expedientes``. Their routes keep the ``/api/v1`` prefix so existing
  clients and the existing frontend views continue to work.
* **AeroRF GIS** — ``map`` (objects, layers, GeoJSON), ``rf_objects``
  (sources, antennas, events, references), ``flights`` (search, tracks,
  live, sessions, watchlist), ``correlation``, ``export``, ``system``, and
  the ``/ws/flights`` WebSocket.

There is no parallel API: one prefix, one object model, one set of
endpoints per concern.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.origin_guard import install_origin_guard
from app.core.config import get_settings
from app.core.logging import log, setup_logging
from app.database.database import init_db

# ─── Legacy SIARI routers (unchanged behaviour) ─────────────────────────────
from app.api.routes.expedientes import router as expedientes_router
from app.api.routes.rf import router as rf_router
from app.api.routes.rf_expediente import router as rf_exp_router

# ─── AeroRF GIS routers ─────────────────────────────────────────────────────
from app.api.routes.correlation import router as correlation_router
from app.api.routes.export import router as export_router
from app.api.routes.flights import router as flights_router
from app.api.routes.map import router as map_router
from app.api.routes.rf_objects import router as rf_objects_router
from app.api.routes.system import router as system_router
from app.api.routes.ws import router as ws_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown."""
    setup_logging()
    init_db()
    log.info(
        "app.startup",
        f"{settings.app_name} ready",
        environment=settings.environment,
        api_prefix=settings.api_prefix,
        database="sqlite" if settings.is_sqlite else "postgresql",
        opensky="configured" if settings.has_opensky_credentials else "not configured",
    )
    if not settings.has_opensky_credentials:
        # «Flight features disabled» era falso: en modo anónimo el
        # tráfico en vivo sí funciona (OpenSky lo sirve sin cuenta); lo
        # que se cae sin credenciales es el historial de vuelos.
        log.warning(
            "app.opensky_missing",
            "Credenciales de OpenSky ausentes: el historial de vuelos "
            "quedará deshabilitado y el tráfico en vivo dependerá de "
            "OPENSKY_ALLOW_ANONYMOUS. Ver .env.example.",
        )
    yield
    log.info("app.shutdown", "shutting down")


app = FastAPI(
    title="AeroRF — Plataforma GIS de Interferencias Aeronáuticas",
    description=(
        "Investigación espacial y temporal de interferencias radioeléctricas "
        "aeronáuticas.\n\n"
        "**Filosofía:** todo es un objeto, todo es una capa, todo ocurre "
        "sobre el mapa.\n\n"
        "* Objetos geográficos persistentes con historial completo\n"
        "* Círculos, radiales, trazas y mediciones\n"
        "* Fuentes interferentes, antenas, eventos RF y referencias\n"
        "* Vuelos: búsqueda, trayectoria, en vivo y grabación propia\n"
        "* Notas y estados que nunca se sobrescriben\n"
        "* Exportación GeoJSON / KML / CSV\n\n"
        "Los datos se distinguen siempre por procedencia: observado, "
        "histórico, en vivo, calculado o introducido por el usuario. "
        "AeroRF no inventa posiciones ni afirma causalidad."
    ),
    version="1.0.0",
    lifespan=lifespan,
    contact={"name": "AeroRF"},
    license_info={"name": "Internal use only"},
)

# ─── Errores en español (F2-05) ──────────────────────────────────────────────
# Pisa el 422 en inglés de FastAPI, atrapa la validación que las rutas con
# `body: dict` hacen dentro del handler (eso salía 500) y traduce cualquier
# IntegrityError a un 400 legible. Ver app/api/errors.py.
install_error_handlers(app)

# ─── CORS ────────────────────────────────────────────────────────────────────
# Tighten CORS_ORIGINS in production to the real domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Origin/Host (P0-07) ─────────────────────────────────────────────────────
# Acotado a los orígenes de CORS configurados: cualquier origen que
# CORSMiddleware (arriba) sirve, éste lo deja llegar — los dos leen el
# mismo .env y nunca se contradicen. CORS niega la *lectura*; el guard
# niega la *petición* (formularios, XHR de otro sitio) y cierra el hueco
# que CORS no cubre: el DNS rebinding, que no manda Origin y entra por
# el Host. Ver app/api/origin_guard.py.
install_origin_guard(app)

# ─── Routers ─────────────────────────────────────────────────────────────────
API = settings.api_prefix

# Legacy SIARI — routes and payloads unchanged.
app.include_router(rf_router, prefix=API)
app.include_router(rf_exp_router, prefix=API)
app.include_router(expedientes_router, prefix=API)

# AeroRF GIS. `flights` replaces the previous demo-flight implementation:
# the old /flights/search fabricated routes, and fabrication is exactly
# what this platform must not do.
app.include_router(map_router, prefix=API)
app.include_router(rf_objects_router, prefix=API)
app.include_router(flights_router, prefix=API)
app.include_router(correlation_router, prefix=API)
app.include_router(export_router, prefix=API)
app.include_router(system_router, prefix=API)
app.include_router(ws_router)  # /ws/flights — no version prefix


# ─── Health ──────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health() -> dict:
    """Liveness probe. Deliberately dependency-free and cheap."""
    return {
        "status": "ok",
        "service": "AeroRF",
        "version": app.version,
        "environment": settings.environment,
    }


@app.get("/", include_in_schema=False)
def root() -> dict:
    """Service banner with the API map."""
    return {
        "app": "AeroRF",
        "version": app.version,
        "description": "Plataforma GIS de interferencias radioeléctricas aeronáuticas",
        "docs": "/docs",
        "api_prefix": API,
        "endpoints": {
            "salud": "/health",
            "sistema": f"{API}/system/status",
            "objetos_mapa": f"{API}/map/objects",
            "capas": f"{API}/map/layers",
            "vocabulario": f"{API}/map/vocabulary",
            "fuentes_rf": f"{API}/rf/sources",
            "eventos_rf": f"{API}/rf/events",
            "antenas": f"{API}/antennas",
            "referencias": f"{API}/references",
            "buscar_vuelo": f"{API}/flights/search",
            "trayectoria": f"{API}/flights/{{icao24}}/track",
            "vuelo_en_vivo": f"{API}/flights/live",
            "seguimiento": f"{API}/flights/tracked",
            "sesiones": f"{API}/flights/sessions",
            "correlacion": f"{API}/correlation",
            "exportar": f"{API}/export/geojson",
            "websocket": "/ws/flights",
            # Legacy RF engine, preserved.
            "motor_rf": f"{API}/rf/calculate",
            "expedientes": f"{API}/expedientes/",
        },
    }
