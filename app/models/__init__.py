"""
models/__init__.py
──────────────────
SQLAlchemy models for AeroRF.

Two generations live side by side on purpose:

* **Legacy SIARI** — ``Expediente``, ``Medicion``, ``EventoRF``,
  ``RegistroEspectral``. Unmodified. They carry the RF calculation results
  and the case file, and they are already referenced by the working
  expedientes API. Untouched.

* **AeroRF GIS** — ``MapObject`` and its satellites (``Layer``,
  ``RFSource``, ``Antenna``, ``ReferencePoint``, ``RFEvent``,
  ``Measurement``), the traceability tables (``ObjectNote``,
  ``ObjectHistory``, ``Annotation``) and the flight tables
  (``Flight``, ``AircraftTrack``, ``FlightSession``,
  ``AircraftPosition``, ``FlightSelection``).

Importing this package registers every model on ``Base.metadata``,
which is what ``init_db()`` relies on.
"""

# ─── Legacy SIARI models ─────────────────────────────────────────────────────
from app.models.espectro import RegistroEspectral
from app.models.evento_rf import EventoRF
from app.models.expediente import Expediente
from app.models.medicion import Medicion

# ─── AeroRF GIS models ───────────────────────────────────────────────────────
from app.models.flight import (
    AircraftPosition,
    AircraftTrack,
    Flight,
    FlightSelection,
    FlightSession,
)
from app.models.layer import Layer
from app.models.map_object import MapObject
from app.models.measurement import Measurement
from app.models.rf import RFEvent, RFSource, Antenna, ReferencePoint
from app.models.tracking import Annotation, ObjectHistory, ObjectNote

__all__ = [
    # Legacy
    "Expediente",
    "Medicion",
    "RegistroEspectral",
    "EventoRF",
    # GIS
    "MapObject",
    "Layer",
    "Measurement",
    # RF
    "RFSource",
    "Antenna",
    "ReferencePoint",
    "RFEvent",
    # Traceability
    "ObjectNote",
    "ObjectHistory",
    "Annotation",
    # Flights
    "Flight",
    "AircraftTrack",
    "FlightSession",
    "AircraftPosition",
    "FlightSelection",
]
