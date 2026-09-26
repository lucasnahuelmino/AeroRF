"""
models/evento_rf.py
───────────────────
EventoRF (RF event) model for detected interference events.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.database.database import Base
from datetime import datetime

from app.core.time import utcnow


class EventoRF(Base):
    """
    Detected RF interference event.
    
    Stores:
    - Detection timestamp
    - Calculated interference product
    - Formula and error metrics
    - Ranking score
    """

    __tablename__ = "eventos_rf"

    id = Column(Integer, primary_key=True, index=True)
    expediente_id = Column(Integer, ForeignKey("expedientes.id"))
    
    # Event identification
    timestamp = Column(DateTime, default=utcnow)
    frecuencia_resultado_mhz = Column(Float)
    
    # RF calculation details
    tipo_producto = Column(String(10))  # H2, H3, IM2, IM3, IM5, IM7
    formula = Column(String(100))
    error_khz = Column(Float)
    
    # Scoring
    score_probabilidad = Column(Float)  # 0-99
    proximidad = Column(Float)
    
    # Source frequencies
    freq_1_mhz = Column(Float, nullable=True)
    freq_2_mhz = Column(Float, nullable=True)
    
    # Additional context
    senal_type = Column(String(20), nullable=True)  # FM, TV_VHF, TV_UHF, etc
    potencia_estimada_dbm = Column(Float, nullable=True)
    
    # Notes
    observaciones = Column(Text, nullable=True)

    def __repr__(self):
        return f"<EventoRF {self.formula} = {self.frecuencia_resultado_mhz} MHz (score: {self.score_probabilidad})>"
