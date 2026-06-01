"""
api/routes/rf_expediente.py
───────────────────────────
RF analysis routes integrated with expediente management.

Endpoints
─────────
POST   /rf/expedientes/{id}/calculate  — Calculate for expediente + store
GET    /rf/expedientes/{id}/candidates — Get top RF candidates
GET    /rf/frequency-conflicts          — Search historical conflicts
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.expediente import Expediente
from app.models.schemas import EventoRFResponse
from app.models.rf_models import RFCalculationRequest
from app.services.rf_service import RFService
from typing import List

router = APIRouter(prefix="/rf", tags=["RF Analysis"])
rf_service = RFService()


# ─── POST /rf/expedientes/{id}/calculate ──────────────────────────────────────

@router.post("/expedientes/{expediente_id}/calculate")
def calculate_for_expediente(
    expediente_id: int,
    request: RFCalculationRequest,
    db: Session = Depends(get_db),
):
    """
    Calculate RF interference products for an expediente,
    store results in database, and return ranked candidates.
    """
    # Verify expediente exists
    expediente = db.query(Expediente).filter(Expediente.id == expediente_id).first()
    if not expediente:
        raise HTTPException(status_code=404, detail="Expediente not found")

    try:
        # Calculate and store
        stored_events = rf_service.calculate_and_store(
            db=db,
            expediente_id=expediente_id,
            target_mhz=request.target_mhz,
            frequencies=[f.dict() for f in request.frequencies],
            tolerance_khz=request.tolerance_khz,
        )

        return {
            "expediente_id": expediente_id,
            "target_mhz": request.target_mhz,
            "tolerance_khz": request.tolerance_khz,
            "total_eventos": len(stored_events),
            "eventos": [
                {
                    "id": e.id,
                    "formula": e.formula,
                    "tipo": e.tipo_producto,
                    "resultado_mhz": e.frecuencia_resultado_mhz,
                    "error_khz": e.error_khz,
                    "score": e.score_probabilidad,
                }
                for e in stored_events[:10]  # Top 10
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── GET /rf/expedientes/{id}/candidates ──────────────────────────────────────

@router.get("/expedientes/{expediente_id}/candidates", response_model=List[EventoRFResponse])
def get_candidates(
    expediente_id: int,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """
    Get top RF interference candidates for an expediente,
    ranked by probability score.
    """
    expediente = db.query(Expediente).filter(Expediente.id == expediente_id).first()
    if not expediente:
        raise HTTPException(status_code=404, detail="Expediente not found")

    return rf_service.get_top_candidates(db, expediente_id, limit)


# ─── GET /rf/frequency-conflicts ──────────────────────────────────────────────

@router.get("/frequency-conflicts")
def search_frequency_conflicts(
    frequency_mhz: float,
    tolerance_khz: float = 50.0,
    db: Session = Depends(get_db),
):
    """
    Search historical RF events that conflict with a given frequency.
    Useful for finding interference patterns.
    """
    conflicts = rf_service.get_frequency_conflicts(
        db, frequency_mhz, tolerance_khz
    )

    return {
        "search_frequency_mhz": frequency_mhz,
        "tolerance_khz": tolerance_khz,
        "total_conflicts": len(conflicts),
        "conflicts": [
            {
                "id": c.id,
                "expediente_id": c.expediente_id,
                "formula": c.formula,
                "tipo": c.tipo_producto,
                "resultado_mhz": c.frecuencia_resultado_mhz,
                "error_khz": c.error_khz,
                "score": c.score_probabilidad,
            }
            for c in conflicts[:20]  # Top 20
        ],
    }
