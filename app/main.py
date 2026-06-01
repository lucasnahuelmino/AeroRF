"""
main.py
───────
SIARI — FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload --port 8000

Interactive docs:
    http://localhost:8000/docs       (Swagger UI)
    http://localhost:8000/redoc      (ReDoc)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.rf import router as rf_router
from app.api.routes.rf_expediente import router as rf_exp_router
from app.api.routes.expedientes import router as expedientes_router
from app.api.routes.flights import router as flights_router
from app.database.database import init_db

app = FastAPI(
    title="SIARI — RF Interference Analysis API",
    description=(
        "Sistema Inteligente de Análisis de Interferencias RF Aeronáuticas. "
        "Calcula armónicas, productos de intermodulación (IM2/IM3/IM5/IM7) "
        "y rankea candidatos por probabilidad de interferencia.\n\n"
        "**ENACOM — Ente Nacional de Comunicaciones de Argentina**"
    ),
    version="0.1.0",
    contact={"name": "ENACOM — Gestión del Espectro"},
    license_info={"name": "Internal use only"},
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Allow the Vue 3 dev server (and production build) to call the API.
# Tighten ALLOW_ORIGINS in production to your actual domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:4173",   # Vite preview
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(rf_router, prefix="/api/v1")
app.include_router(rf_exp_router, prefix="/api/v1")
app.include_router(expedientes_router, prefix="/api/v1")
app.include_router(flights_router, prefix="/api/v1")

# Future routers (uncomment as modules are built):
# from app.api.routes.flights     import router as flight_router
# from app.api.routes.export      import router as export_router
# app.include_router(flight_router, prefix="/api/v1")
# app.include_router(export_router, prefix="/api/v1")


# ─── Startup event ────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    """Initialize database on application startup."""
    init_db()


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health() -> dict:
    return {"status": "ok", "service": "SIARI RF Engine", "version": "0.1.0"}
