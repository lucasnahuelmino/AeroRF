"""
api/routes/rf_analisis.py
──────────────────────────
Historial propio de análisis de la calculadora RF (AeroRF 2.6, Bloque 1).

La calculadora ya no guarda en Expedientes: guarda acá. Un análisis tiene
identidad propia, se compone de los parámetros que se mandaron al motor y de
la respuesta que el motor devolvió, y se puede consultar después sin ningún
expediente.

Endpoints
─────────
POST   /rf/analisis        — Guardar una corrida de la calculadora
GET    /rf/analisis        — Listar análisis guardados (los más recientes)
GET    /rf/analisis/{id}   — Consultar un análisis con sus resultados
DELETE /rf/analisis/{id}   — Eliminar un análisis guardado por el usuario

La asociación a un objeto GIS (fuente RF, evento RF o antena) es opcional vía
`objeto_id`: se admite cuando corresponde y nunca se exige (spec 3.5).
"""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.analisis_rf import AnalisisRF
from app.models.constants import TYPE_ANTENNA, TYPE_RF_EVENT, TYPE_RF_SOURCE
from app.models.map_object import MapObject
from app.models.rf_models import AnalisisRFCreate, AnalisisRFResponse

router = APIRouter(prefix="/rf", tags=["RF Analysis"])

# Un análisis se puede asociar sólo a objetos que tengan identidad RF propia:
# fuentes, eventos y antenas. Las geometrías de dibujo no son evidencia RF.
TIPOS_ASOCIABLES = (TYPE_RF_SOURCE, TYPE_RF_EVENT, TYPE_ANTENNA)


def _fila_a_response(row: AnalisisRF) -> dict:
    """Filas guardadas → payload de respuesta, con los conteos calculados.

    Los JSON se guardan crudos y se devuelven por los contratos que ya
    validaba `POST /rf/calculate`; los conteos rápidos se derivan acá para no
    duplicarlos en la tabla.
    """
    parametros = json.loads(row.parametros)
    resultados = json.loads(row.resultados)
    return {
        "id": row.id,
        "created_at": row.created_at,
        "modo": row.modo,
        "frecuencia_referencia_mhz": row.frecuencia_referencia_mhz,
        "tolerancia_khz": row.tolerancia_khz,
        "n_emisoras": len(parametros.get("frequencies") or []),
        "n_productos": len(resultados.get("matches") or []),
        "objeto_id": row.objeto_id,
        "parametros": parametros,
        "resultados": resultados,
    }


@router.post(
    "/analisis",
    response_model=AnalisisRFResponse,
    status_code=201,
    summary="Guardar un análisis de la calculadora RF",
    description=(
        "Persiste una corrida de la calculadora con sus parámetros y sus "
        "resultados completos. No depende de Expedientes: el análisis tiene "
        "identidad propia y puede asociarse opcionalmente a una fuente RF, "
        "un evento RF o una antena mediante `objeto_id`."
    ),
)
def guardar_analisis(payload: AnalisisRFCreate, db: Session = Depends(get_db)):
    if payload.objeto_id is not None:
        obj = db.get(MapObject, payload.objeto_id)
        if obj is None:
            raise HTTPException(
                404, f"No existe el objeto GIS {payload.objeto_id}."
            )
        if obj.type not in TIPOS_ASOCIABLES:
            raise HTTPException(
                400,
                "Sólo se puede asociar un análisis a una fuente RF, un evento "
                "RF o una antena.",
            )

    row = AnalisisRF(
        modo=payload.modo.value,
        frecuencia_referencia_mhz=payload.parametros.target_mhz,
        tolerancia_khz=payload.parametros.tolerance_khz,
        parametros=payload.parametros.model_dump_json(),
        resultados=payload.resultados.model_dump_json(),
        objeto_id=payload.objeto_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _fila_a_response(row)


@router.get(
    "/analisis",
    response_model=List[AnalisisRFResponse],
    summary="Listar análisis guardados",
    description="Los más recientes primero. Cada fila trae parámetros y resultados.",
)
def listar_analisis(
    limit: int = Query(50, ge=1, le=200, description="Máximo de análisis a devolver"),
    objeto_id: Optional[int] = Query(
        None, ge=1, description="Filtrar por objeto GIS asociado"
    ),
    db: Session = Depends(get_db),
):
    q = db.query(AnalisisRF)
    if objeto_id is not None:
        q = q.filter(AnalisisRF.objeto_id == objeto_id)
    rows = q.order_by(AnalisisRF.created_at.desc(), AnalisisRF.id.desc()).limit(limit).all()
    return [_fila_a_response(r) for r in rows]


@router.get(
    "/analisis/{analisis_id}",
    response_model=AnalisisRFResponse,
    summary="Consultar un análisis guardado",
)
def obtener_analisis(analisis_id: int, db: Session = Depends(get_db)):
    row = db.get(AnalisisRF, analisis_id)
    if row is None:
        raise HTTPException(404, f"No existe el análisis {analisis_id}.")
    return _fila_a_response(row)


@router.delete(
    "/analisis/{analisis_id}",
    status_code=204,
    summary="Eliminar un análisis guardado",
)
def eliminar_analisis(analisis_id: int, db: Session = Depends(get_db)):
    row = db.get(AnalisisRF, analisis_id)
    if row is None:
        raise HTTPException(404, f"No existe el análisis {analisis_id}.")
    db.delete(row)
    db.commit()
