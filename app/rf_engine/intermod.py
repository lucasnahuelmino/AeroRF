"""
rf_engine/intermod.py
─────────────────────
Intermodulation distortion (IMD) product calculator.

Theory
------
When two or more signals co-exist in a non-linear device (transmitter PA,
amplifier, receiver front-end), mixing products are generated at frequencies:

    IM_n = m·f1 ± k·f2   where  |m| + |k| = n  (order)

The odd-order products (IM3, IM5, IM7) are the most problematic in RF systems
because they fall near the fundamental frequencies and are harder to filter.

Implemented products
--------------------
IM2  (order 2): f1 + f2 ,  |f1 − f2|
IM3  (order 3): 2f1 − f2,  2f2 − f1,  2f1 + f2,  2f2 + f1
IM5  (order 5): 3f1 − 2f2, 3f2 − 2f1, 3f1 + 2f2, 3f2 + 2f1
IM7  (order 7): 4f1 − 3f2, 4f2 − 3f1  (optional, enabled via flag)
"""

from __future__ import annotations
from dataclasses import dataclass

from .tolerance import ToleranceResult, check_tolerance


@dataclass(slots=True)
class IMProduct:
    """One intermodulation product candidate."""
    order: int
    freq_a_mhz: float
    freq_b_mhz: float
    result_mhz: float
    formula: str
    tipo: str              # "IM2", "IM3", "IM5", "IM7"
    tolerance: ToleranceResult


# ─── Internal helper ──────────────────────────────────────────────────────────

def _fmt(f: float) -> str:
    """Format a frequency for display — trim unnecessary trailing zeros."""
    s = f"{f:.6f}".rstrip("0").rstrip(".")
    return s


def _product(
    result: float,
    formula: str,
    tipo: str,
    order: int,
    fa: float,
    fb: float,
    target: float,
    tol: float,
    out: list[IMProduct],
) -> None:
    """Evaluate one candidate and append to out if it matches."""
    if result <= 0:
        return
    t = check_tolerance(result, target, tol)
    if t.match:
        out.append(
            IMProduct(
                order=order,
                freq_a_mhz=fa,
                freq_b_mhz=fb,
                result_mhz=round(result, 9),
                formula=formula,
                tipo=tipo,
                tolerance=t,
            )
        )


# ─── Public API ───────────────────────────────────────────────────────────────

def calculate_im2(
    fa: float,
    fb: float,
    target_mhz: float,
    tolerance_khz: float,
) -> list[IMProduct]:
    """
    Second-order intermodulation products between ``fa`` and ``fb``.

    Formulas: fa+fb, |fa−fb|
    """
    out: list[IMProduct] = []
    a, b = _fmt(fa), _fmt(fb)
    _product(fa + fb,          f"{a} + {b}",      "IM2", 2, fa, fb, target_mhz, tolerance_khz, out)
    _product(abs(fa - fb),     f"|{a} − {b}|",    "IM2", 2, fa, fb, target_mhz, tolerance_khz, out)
    return out


def calculate_im3(
    fa: float,
    fb: float,
    target_mhz: float,
    tolerance_khz: float,
) -> list[IMProduct]:
    """
    Third-order intermodulation products between ``fa`` and ``fb``.

    Formulas: 2fa±fb, 2fb±fa
    The difference products (2fa−fb, 2fb−fa) are the classic "close-in" IM3
    that fall near the aeronautical band and are the most dangerous.
    """
    out: list[IMProduct] = []
    a, b = _fmt(fa), _fmt(fb)
    _product(2*fa - fb, f"2×{a} − {b}",  "IM3", 3, fa, fb, target_mhz, tolerance_khz, out)
    _product(2*fb - fa, f"2×{b} − {a}",  "IM3", 3, fa, fb, target_mhz, tolerance_khz, out)
    _product(2*fa + fb, f"2×{a} + {b}",  "IM3", 3, fa, fb, target_mhz, tolerance_khz, out)
    _product(2*fb + fa, f"2×{b} + {a}",  "IM3", 3, fa, fb, target_mhz, tolerance_khz, out)
    return out


def calculate_im5(
    fa: float,
    fb: float,
    target_mhz: float,
    tolerance_khz: float,
) -> list[IMProduct]:
    """
    Fifth-order intermodulation products between ``fa`` and ``fb``.

    Formulas: 3fa±2fb, 3fb±2fa
    """
    out: list[IMProduct] = []
    a, b = _fmt(fa), _fmt(fb)
    _product(3*fa - 2*fb, f"3×{a} − 2×{b}",  "IM5", 5, fa, fb, target_mhz, tolerance_khz, out)
    _product(3*fb - 2*fa, f"3×{b} − 2×{a}",  "IM5", 5, fa, fb, target_mhz, tolerance_khz, out)
    _product(3*fa + 2*fb, f"3×{a} + 2×{b}",  "IM5", 5, fa, fb, target_mhz, tolerance_khz, out)
    _product(3*fb + 2*fa, f"3×{b} + 2×{a}",  "IM5", 5, fa, fb, target_mhz, tolerance_khz, out)
    return out


def calculate_im7(
    fa: float,
    fb: float,
    target_mhz: float,
    tolerance_khz: float,
) -> list[IMProduct]:
    """
    Seventh-order intermodulation products between ``fa`` and ``fb``.

    Formulas: 4fa−3fb, 4fb−3fa (difference products only — sum products
    are too far from the aeronautical band to be useful in practice).
    """
    out: list[IMProduct] = []
    a, b = _fmt(fa), _fmt(fb)
    _product(4*fa - 3*fb, f"4×{a} − 3×{b}",  "IM7", 7, fa, fb, target_mhz, tolerance_khz, out)
    _product(4*fb - 3*fa, f"4×{b} − 3×{a}",  "IM7", 7, fa, fb, target_mhz, tolerance_khz, out)
    return out


def calculate_all_im(
    fa: float,
    fb: float,
    target_mhz: float,
    tolerance_khz: float,
    include_im7: bool = False,
) -> list[IMProduct]:
    """
    Calculate all IM products (IM2 + IM3 + IM5 + optional IM7) for a pair.
    """
    results = (
        calculate_im2(fa, fb, target_mhz, tolerance_khz)
        + calculate_im3(fa, fb, target_mhz, tolerance_khz)
        + calculate_im5(fa, fb, target_mhz, tolerance_khz)
    )
    if include_im7:
        results += calculate_im7(fa, fb, target_mhz, tolerance_khz)
    return results
