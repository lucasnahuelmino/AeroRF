"""
api/routes/expedientes.py
─────────────────────────
FastAPI router for expediente (case) management endpoints.

Endpoints
─────────
GET    /expedientes          — List all expedientes
POST   /expedientes          — Create new expediente
GET    /expedientes/{id}     — Get expediente by ID
PUT    /expedientes/{id}     — Update expediente
DELETE /expedientes/{id}     — Delete expediente
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List

from app.database.database import get_db
from app.models.expediente import Expediente
from app.models.medicion import Medicion
from app.models.evento_rf import EventoRF
from app.models.schemas import (
    ExpedienteCreate,
    ExpedienteUpdate,
    ExpedienteResponse,
    MedicionResponse,
    EventoRFResponse,
)

router = APIRouter(prefix="/expedientes", tags=["Expedientes"])


# ─── GET /expedientes ──────────────────────────────────────────────────────────

@router.get("/", response_model=List[ExpedienteResponse])
def list_expedientes(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    estado: str = Query(None),
    db: Session = Depends(get_db),
):
    """
    List all expedientes with optional filtering.
    
    Query Parameters:
    - skip: Number of records to skip (pagination)
    - limit: Maximum records to return
    - estado: Filter by status (abierto, investigacion, resuelto, cerrado)
    """
    query = db.query(Expediente).order_by(desc(Expediente.fecha_creacion))
    
    if estado:
        query = query.filter(Expediente.estado == estado)
    
    return query.offset(skip).limit(limit).all()


# ─── POST /expedientes ─────────────────────────────────────────────────────────

@router.post("/", response_model=ExpedienteResponse)
def create_expediente(
    expediente: ExpedienteCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new RF interference investigation case.
    
    Request Body:
    - numero_expediente: Case number (must be unique)
    - freq_mhz: Affected aeronautical frequency
    - aeropuerto: Airport identifier
    - And other case details
    """
    # Check if numero_expediente already exists
    existing = db.query(Expediente).filter(
        Expediente.numero_expediente == expediente.numero_expediente
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Expediente {expediente.numero_expediente} already exists"
        )
    
    db_expediente = Expediente(**expediente.dict())
    db.add(db_expediente)
    db.commit()
    db.refresh(db_expediente)
    
    return db_expediente


# ─── GET /expedientes/{id} ────────────────────────────────────────────────────

@router.get("/{id}", response_model=ExpedienteResponse)
def get_expediente(id: int, db: Session = Depends(get_db)):
    """Get a specific expediente by ID."""
    expediente = db.query(Expediente).filter(Expediente.id == id).first()
    
    if not expediente:
        raise HTTPException(status_code=404, detail="Expediente not found")
    
    return expediente


# ─── PUT /expedientes/{id} ────────────────────────────────────────────────────

@router.put("/{id}", response_model=ExpedienteResponse)
def update_expediente(
    id: int,
    expediente: ExpedienteUpdate,
    db: Session = Depends(get_db),
):
    """Update an existing expediente."""
    db_expediente = db.query(Expediente).filter(Expediente.id == id).first()
    
    if not db_expediente:
        raise HTTPException(status_code=404, detail="Expediente not found")
    
    # Update only provided fields
    for field, value in expediente.dict(exclude_unset=True).items():
        setattr(db_expediente, field, value)
    
    db.commit()
    db.refresh(db_expediente)
    
    return db_expediente


# ─── DELETE /expedientes/{id} ──────────────────────────────────────────────────

@router.delete("/{id}")
def delete_expediente(id: int, db: Session = Depends(get_db)):
    """Delete an expediente (cascade deletes related records)."""
    db_expediente = db.query(Expediente).filter(Expediente.id == id).first()
    
    if not db_expediente:
        raise HTTPException(status_code=404, detail="Expediente not found")
    
    # Delete related records
    db.query(Medicion).filter(Medicion.expediente_id == id).delete()
    db.query(EventoRF).filter(EventoRF.expediente_id == id).delete()
    
    db.delete(db_expediente)
    db.commit()
    
    return {"message": f"Expediente {id} deleted"}


# ─── GET /expedientes/{id}/mediciones ──────────────────────────────────────────

@router.get("/{id}/mediciones", response_model=List[MedicionResponse])
def get_mediciones(id: int, db: Session = Depends(get_db)):
    """Get all measurements (mediciones) for an expediente."""
    expediente = db.query(Expediente).filter(Expediente.id == id).first()
    
    if not expediente:
        raise HTTPException(status_code=404, detail="Expediente not found")
    
    return db.query(Medicion).filter(Medicion.expediente_id == id).all()


# ─── GET /expedientes/{id}/eventos ────────────────────────────────────────────

@router.get("/{id}/eventos", response_model=List[EventoRFResponse])
def get_eventos_rf(id: int, db: Session = Depends(get_db)):
    """Get all detected RF events for an expediente."""
    expediente = db.query(Expediente).filter(Expediente.id == id).first()
    
    if not expediente:
        raise HTTPException(status_code=404, detail="Expediente not found")
    
    return db.query(EventoRF).filter(EventoRF.expediente_id == id).order_by(
        desc(EventoRF.score_probabilidad)
    ).all()
