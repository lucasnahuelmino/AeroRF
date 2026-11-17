"""
models/analisis_rf.py
──────────────────────
AnalisisRF — historial propio de análisis de la calculadora RF (AeroRF 2.6).

La calculadora dejó de guardar resultados en Expedientes (Bloque 1, AeroRF
2.6): un análisis pasa a tener identidad propia. La fila guarda exactamente
lo que se mandó al motor (``parametros``) y lo que el motor devolvió
(``resultados``), serializados como JSON, más el modo de la pestaña con el
que se guardó. No se copian campos sueltos del cálculo: el request y la
response son la fuente de verdad, así este almacenamiento no duplica al de
``POST /rf/calculate``.

``objeto_id`` es la relación opcional con un objeto GIS de la que habla la
spec 3.5 (fuente RF, evento RF o antena). Es opcional y nunca exigido: un
análisis es válido y consultable sin ninguna asociación, y la asociación no
pasa por Expedientes.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.core.time import utcnow
from app.database.database import Base


class AnalisisRF(Base):
    """Un guardado de la calculadora RF, consultable sin expediente."""

    __tablename__ = "analisis_rf"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)

    # Pestaña con la que se guardó: 'armonicos' | 'intermodulacion'.
    modo = Column(String(20), nullable=False)

    # Copia de consulta rápida de `parametros.target_mhz` /
    # `parametros.tolerance_khz`, para listar y filtrar sin parsear JSON.
    frecuencia_referencia_mhz = Column(Float, nullable=True)
    tolerancia_khz = Column(Float, nullable=True)

    # JSON: `RFCalculationRequest` enviado y `RFCalculationResponse` recibido.
    parametros = Column(Text, nullable=False)
    resultados = Column(Text, nullable=False)

    # Asociación opcional a un objeto GIS (fuente RF / evento RF / antena).
    # Nunca exigida: la preserva el historial y no crea módulo burocrático.
    objeto_id = Column(Integer, ForeignKey("map_objects.id"), nullable=True, index=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<AnalisisRF {self.id} modo={self.modo} "
            f"ref={self.frecuencia_referencia_mhz} MHz>"
        )
