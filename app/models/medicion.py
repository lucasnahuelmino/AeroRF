"""
models/medicion.py
──────────────────
Medicion (measurement) model for field data points.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.database.database import Base
from datetime import datetime


class Medicion(Base):
    """
    Field measurement data point.
    
    Stores:
    - Frequency measurements
    - Signal level (dBm)
    - Location (lat/lon)
    - Timestamp
    - Analyst notes
    """

    __tablename__ = "mediciones"

    id = Column(Integer, primary_key=True, index=True)
    expediente_id = Column(Integer, ForeignKey("expedientes.id"))
    
    # Measurement data
    freq_mhz = Column(Float)
    nivel_dbm = Column(Float, nullable=True)
    ancho_banda_khz = Column(Float, nullable=True)
    
    # Location
    lat = Column(Float)
    lon = Column(Float)
    
    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow)
    fecha_medicion = Column(String(50))
    
    # Metadata
    descripcion = Column(Text, nullable=True)
    notas_tecnicas = Column(Text, nullable=True)
    ubicacion_nombre = Column(String(100), nullable=True)

    def __repr__(self):
        return f"<Medicion {self.freq_mhz} MHz @ {self.lat},{self.lon}>"
