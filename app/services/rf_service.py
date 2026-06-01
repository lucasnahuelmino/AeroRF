"""
services/rf_service.py
──────────────────────
RF analysis service integrating the RF engine with database persistence.

Handles:
- Calculation requests
- Result persistence to database
- Event ranking and storage
- Historical correlation
"""

from app.rf_engine.engine import RFEngine
from app.models.evento_rf import EventoRF
from app.models.expediente import Expediente
from sqlalchemy.orm import Session
from typing import List, Optional


class RFService:
    """RF analysis and correlation service."""

    def __init__(self):
        self.engine = RFEngine()

    def calculate_and_store(
        self,
        db: Session,
        expediente_id: int,
        target_mhz: float,
        frequencies: List[dict],
        tolerance_khz: float = 10.0,
    ) -> List[dict]:
        """
        Calculate RF interference products and store results in database.

        Args:
            db: Database session
            expediente_id: Case ID for correlation
            target_mhz: Affected aeronautical frequency
            frequencies: List of candidate frequencies
            tolerance_khz: Tolerance window

        Returns:
            List of calculated and stored events with scores
        """
        # Call existing RF engine
        from app.models.rf_models import RFCalculationRequest, FrequencyInput, SignalType

        frequency_inputs = [
            FrequencyInput(
                freq_mhz=f["freq_mhz"],
                label=f.get("label", f"Freq_{f['freq_mhz']}"),
                signal_type=f.get("signal_type", SignalType.UNKNOWN),
                power_dbm=f.get("power_dbm"),
            )
            for f in frequencies
        ]

        request = RFCalculationRequest(
            target_mhz=target_mhz,
            tolerance_khz=tolerance_khz,
            frequencies=frequency_inputs,
        )

        result = self.engine.calculate(request)

        # Store in database
        stored_events = []
        for match in result.matches:
            event = EventoRF(
                expediente_id=expediente_id,
                frecuencia_resultado_mhz=match.resultado,
                tipo_producto=match.tipo,
                formula=match.formula,
                error_khz=match.error_khz,
                score_probabilidad=match.score,
                proximidad=match.proximity,
                freq_1_mhz=match.freq_a_mhz,
                freq_2_mhz=match.freq_b_mhz if match.order > 1 else None,
                senal_type=match.signal_type,
                potencia_estimada_dbm=match.power_dbm,
            )
            db.add(event)
            db.flush()
            stored_events.append(event)

        db.commit()

        return stored_events

    def get_top_candidates(
        self,
        db: Session,
        expediente_id: int,
        limit: int = 10,
    ) -> List[EventoRF]:
        """
        Get top RF interference candidates for an expediente,
        ranked by probability score.
        """
        return (
            db.query(EventoRF)
            .filter(EventoRF.expediente_id == expediente_id)
            .order_by(EventoRF.score_probabilidad.desc())
            .limit(limit)
            .all()
        )

    def get_frequency_conflicts(
        self,
        db: Session,
        frequency_mhz: float,
        tolerance_khz: float = 50.0,
    ) -> List[EventoRF]:
        """
        Find all stored events that conflict with a given frequency.
        Useful for searching historical interference patterns.
        """
        from sqlalchemy import and_

        lo = frequency_mhz - (tolerance_khz / 1000.0)
        hi = frequency_mhz + (tolerance_khz / 1000.0)

        return (
            db.query(EventoRF)
            .filter(
                and_(
                    EventoRF.frecuencia_resultado_mhz >= lo,
                    EventoRF.frecuencia_resultado_mhz <= hi,
                )
            )
            .order_by(EventoRF.score_probabilidad.desc())
            .all()
        )
