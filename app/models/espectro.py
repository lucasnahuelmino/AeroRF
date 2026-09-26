"""
models/espectro.py
──────────────────
RegistroEspectral (spectral data) model.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, LargeBinary, ForeignKey
from sqlalchemy.sql import func
from app.database.database import Base
from datetime import datetime

from app.core.time import utcnow


class RegistroEspectral(Base):
    """
    Spectral measurement record.
    
    Stores:
    - Spectrum screenshots/images
    - CSV data
    - IQ samples (future)
    - Waterfall data (future)
    - Annotations
    """

    __tablename__ = "registros_espectrales"

    id = Column(Integer, primary_key=True, index=True)
    expediente_id = Column(Integer, ForeignKey("expedientes.id"))
    
    # File references
    archivo_path = Column(String(255))
    tipo_archivo = Column(String(20))  # imagen, csv, iq, waterfall
    nombre_archivo = Column(String(100))
    
    # Metadata
    timestamp = Column(DateTime, default=utcnow)
    frecuencia_centro_mhz = Column(Float, nullable=True)
    ancho_vista_khz = Column(Float, nullable=True)
    
    # Annotations
    anotaciones = Column(Text, nullable=True)
    descripcion = Column(Text, nullable=True)
    
    # Processing status
    procesado = Column(String(1), default='N')  # S/N
    resultado_procesamiento = Column(Text, nullable=True)

    def __repr__(self):
        return f"<RegistroEspectral {self.nombre_archivo} - {self.tipo_archivo}>"
