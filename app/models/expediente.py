"""
models/expediente.py
────────────────────
Expediente (case) model for SIARI.

Represents a complete RF interference investigation case.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Enum
from sqlalchemy.sql import func
from app.database.database import Base
from datetime import datetime

from app.core.time import utcnow


class Expediente(Base):
    """
    Main expediente (investigation case) model.
    
    Stores all information about a single RF interference case:
    - Case number and status
    - Affected aeronautical frequency
    - Geographic location
    - Investigation notes
    - Technical severity assessment
    """

    __tablename__ = "expedientes"

    id = Column(Integer, primary_key=True, index=True)
    numero_expediente = Column(String(50), unique=True, index=True)
    
    # Affected frequency
    freq_mhz = Column(Float, index=True)
    
    # Location info
    aeropuerto = Column(String(100))
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    
    # Case metadata
    fecha_creacion = Column(DateTime, default=utcnow)
    fecha_actualizacion = Column(DateTime, default=utcnow, onupdate=utcnow)
    
    # Status and severity
    estado = Column(String(20), default="abierto")  # abierto, investigacion, resuelto, cerrado
    severidad = Column(String(20), default="media")  # baja, media, alta, crítica
    
    # Inspector info
    inspector_responsable = Column(String(100))
    
    # Notes
    observaciones = Column(Text, nullable=True)
    descripcion = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Expediente {self.numero_expediente} - {self.freq_mhz} MHz - {self.estado}>"
