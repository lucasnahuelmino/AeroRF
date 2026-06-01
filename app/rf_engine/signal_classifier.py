"""
rf_engine/signal_classifier.py
───────────────────────────────
Heuristic frequency-to-signal-type classifier.

Used when a FrequencyInput does not have an explicit signal_type, or as a
sanity-check cross-reference.  Classification is based on ITU frequency
allocations relevant to Argentina (CONATEL / ENACOM band plan).
"""

from __future__ import annotations
from dataclasses import dataclass

from app.models.rf_models import SignalType


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    signal_type: SignalType
    band_name: str
    confidence: float   # 0.0–1.0


# ─── Band table (MHz ranges → signal type) ────────────────────────────────────
# Ordered from most-specific to least-specific; first match wins.

_BANDS: list[tuple[float, float, SignalType, str]] = [
    # FM broadcast
    (87.5,   108.0,  SignalType.FM,       "FM Broadcast (87.5–108 MHz)"),
    # VHF TV Band I  (not used in AR but kept for completeness)
    (174.0,  230.0,  SignalType.TV_VHF,   "VHF TV Band III (174–230 MHz)"),
    # UHF TV
    (470.0,  862.0,  SignalType.TV_UHF,   "UHF TV (470–862 MHz)"),
    # Cellular / LTE 700 / 850
    (698.0,  960.0,  SignalType.CELLULAR, "Cellular 700/850/900 MHz"),
    # Cellular AWS / 1900 / 2100
    (1700.0, 2200.0, SignalType.CELLULAR, "Cellular 1700–2200 MHz"),
    # Cellular 2.6 GHz
    (2500.0, 2700.0, SignalType.CELLULAR, "Cellular 2600 MHz"),
    # VHF public safety / PMR / links (generic)
    (136.0,  174.0,  SignalType.VHF,      "VHF PMR/Link (136–174 MHz)"),
    (30.0,   87.5,   SignalType.VHF,      "VHF Low (30–87.5 MHz)"),
    # UHF PMR / links (generic)
    (406.0,  470.0,  SignalType.UHF,      "UHF Low (406–470 MHz)"),
    (862.0,  960.0,  SignalType.UHF,      "UHF High (862–960 MHz)"),
    # Microwave links (rough bands)
    (1300.0, 1700.0, SignalType.LINK,     "Microwave Link ~1.4 GHz"),
    (2200.0, 2500.0, SignalType.LINK,     "Microwave Link ~2.4 GHz"),
    (3400.0, 3800.0, SignalType.LINK,     "Microwave Link ~3.5 GHz"),
    (5700.0, 6000.0, SignalType.LINK,     "Microwave Link ~5.8 GHz"),
]


def classify(freq_mhz: float) -> ClassificationResult:
    """
    Classify a frequency into a SignalType based on band membership.

    Args:
        freq_mhz: Frequency in MHz.

    Returns:
        ClassificationResult with signal_type, band_name and confidence.
        Confidence is 1.0 for exact band matches, 0.5 for unknown.

    Example:
        >>> r = classify(98.7)
        >>> r.signal_type   # SignalType.FM
        >>> r.band_name     # "FM Broadcast (87.5–108 MHz)"
        >>> r.confidence    # 1.0
    """
    for lo, hi, stype, band in _BANDS:
        if lo <= freq_mhz <= hi:
            return ClassificationResult(
                signal_type=stype,
                band_name=band,
                confidence=1.0,
            )

    return ClassificationResult(
        signal_type=SignalType.UNKNOWN,
        band_name=f"Unclassified ({freq_mhz:.3f} MHz)",
        confidence=0.5,
    )


def auto_classify(freq_mhz: float, provided: SignalType) -> SignalType:
    """
    Return the provided signal type if it's not UNKNOWN; otherwise classify.
    """
    if provided != SignalType.UNKNOWN:
        return provided
    return classify(freq_mhz).signal_type
