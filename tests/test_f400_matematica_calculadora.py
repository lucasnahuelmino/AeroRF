"""
tests/test_f400_matematica_calculadora.py
─────────────────────────────────────────
Fase 4 (AeroRF 2.5): la aritmética que muestra la Calculadora RF.

La pantalla hace dos cuentas y éstas son las que tienen que cerrar:

  * `armónica = fundamental × orden` — sale de `GET /rf/harmonics/{freq}`
    y del motor (`calculate_harmonics`), nunca de una fórmula del frontend.
  * `diferencia (kHz) = |armónica − referencia| × 1000` — es la resta que
    la vista muestra contra lo que eligió el operador.

La construcción `90 / 60 / 45 → 180` no es un ejemplo inventado: es la
mínima donde los tres órdenes (2.ª, 3.ª y 4.ª) llegan **exactos** a la
misma referencia, así que sirve para fijar las tres columnas del modo
Armónicos de una sola vez.

Además se fija el contrato del modo Intermodulación: deduplicación por
fórmula, tolerancia inclusiva en su propio borde, y que un producto fuera
de banda vuelva vacío y con aviso en lugar de un falso positivo.
"""

import pytest
from pydantic import ValidationError

from app.models.rf_models import FrequencyInput, RFCalculationRequest, SignalType
from app.rf_engine.engine import RFEngine
from app.rf_engine.harmonics import all_harmonics_table, calculate_harmonics
from app.rf_engine.tolerance import check_tolerance
from app.api.routes.rf import harmonics


# ─── Armónicos contra la referencia ─────────────────────────────────────────

class TestArmonicosContraLaReferencia:
    def test_90_60_45_llegan_exactos_a_180(self):
        for fundamental, orden in ((90.0, 2), (60.0, 3), (45.0, 4)):
            productos = calculate_harmonics(fundamental, 180.0, 10.0, max_order=4)
            buscado = next((p for p in productos if p.order == orden), None)
            assert buscado is not None, (
                f"falta la armonica {orden}a de {fundamental} MHz contra 180 MHz"
            )
            assert buscado.result_mhz == 180.0
            assert buscado.tolerance.error_khz == 0.0
            assert buscado.tolerance.match is True
            assert buscado.formula == f"{orden} × {fundamental}"

    def test_la_tabla_del_endpoint_tambien_da_180(self):
        # El modo Armónicos de la vista consume GET /rf/harmonics/{freq}:
        # la fila de 90 MHz tiene que traer H2 = 180 MHz, sin filtrar.
        respuesta = harmonics(freq_mhz=90.0, max_order=4)
        h2 = next(h for h in respuesta.harmonics if h["order"] == 2)
        assert h2["freq_mhz"] == 180.0
        assert h2["tipo"] == "H2"
        assert [h["order"] for h in respuesta.harmonics] == [2, 3, 4]

    def test_segunda_armonica_de_88_5_es_177(self):
        productos = calculate_harmonics(88.5, 177.0, 10.0, max_order=4)
        h2 = next((p for p in productos if p.order == 2), None)
        assert h2 is not None
        assert h2.result_mhz == 177.0
        assert h2.formula == "2 × 88.5"
        assert h2.tolerance.error_khz == 0.0

    def test_diferencia_en_khz_es_abs_sobre_1000(self):
        # 90×2 = 180.000 contra referencia 180.002 → 2 kHz de diferencia.
        productos = calculate_harmonics(90.0, 180.002, 10.0, max_order=2)
        assert productos and productos[0].order == 2
        assert productos[0].tolerance.error_khz == pytest.approx(2.0, abs=1e-6)
        # La misma emisora a 11 kHz de la referencia ya no es coincidencia.
        assert calculate_harmonics(90.0, 180.011, 10.0, max_order=2) == []

    def test_tabla_y_motor_comparten_la_misma_cuenta(self):
        # La tabla (que lee la vista) y el producto del motor tienen que
        # dar el mismo número para la misma pareja fundamental/referencia.
        for fundamental in (45.0, 60.0, 88.5, 90.0, 119.0):
            tabla = all_harmonics_table(fundamental, max_order=4)
            productos = calculate_harmonics(fundamental, 180.0, 10.0, max_order=4)
            for fila in tabla:
                assert fila["freq_mhz"] == pytest.approx(
                    fila["order"] * fundamental
                )
            for p in productos:
                assert p.result_mhz == pytest.approx(p.order * fundamental)


# ─── Tolerancia ─────────────────────────────────────────────────────────────

class TestToleranciaDeLaCalculadora:
    def test_la_tolerancia_incluye_su_propio_limite(self):
        # El borde se construye con la misma expresión que usa el motor
        # (abs(result − target) × 1000) para que el aserto no dependa de la
        # representación binaria de un decimal redondo. El match compara el
        # valor crudo y el error que devuelve viene redondeado a 3 decimales
        # (0.001 kHz = 1 Hz), que es como lo muestra la pantalla.
        resultado, referencia = 180.01, 180.0
        banda = abs(resultado - referencia) * 1000
        dentro = check_tolerance(resultado, referencia, banda)
        assert dentro.match is True
        assert dentro.error_khz == pytest.approx(round(banda, 3))
        fuera = check_tolerance(resultado, referencia, banda * 0.999)
        assert fuera.match is False
        assert fuera.error_khz > banda * 0.999

    def test_frecuencia_invalida_se_rechaza(self):
        for valor in (0, -1, 6000, 10000):
            with pytest.raises(ValidationError):
                FrequencyInput(freq_mhz=valor)
        assert FrequencyInput(freq_mhz=88.5).freq_mhz == 88.5

        # El endpoint informativo también cierra la puerta, no sólo el modelo.
        with pytest.raises(Exception) as exc:
            harmonics(freq_mhz=0)
        assert getattr(exc.value, "status_code", None) == 422


# ─── Intermodulación (modo B) ───────────────────────────────────────────────

class TestIntermodulacionDelModoB:
    def test_frecuencias_duplicadas_no_duplican_productos(self):
        # Dos entradas de 88.5 MHz producen la misma fórmula "2 × 88.5":
        # la deduplicación es por fórmula, así que puede aparecer una sola vez.
        requerimiento = RFCalculationRequest(
            target_mhz=177.0,
            tolerance_khz=10.0,
            frequencies=[
                FrequencyInput(freq_mhz=88.5, label="A", signal_type=SignalType.FM),
                FrequencyInput(freq_mhz=88.5, label="B", signal_type=SignalType.FM),
            ],
        )
        respuesta = RFEngine().calculate(requerimiento)
        formulas = [m.formula for m in respuesta.matches]
        assert len(formulas) == len(set(formulas)), "formulas repetidas en la respuesta"
        assert formulas.count("2 × 88.5") == 1

    def test_producto_fuera_de_tolerancia_no_es_coincidencia(self):
        # 2×90 = 180.000 queda a 11 kHz de 180.011 con tolerancia de 10 kHz:
        # tiene que volver vacío y con aviso, nunca con un falso positivo.
        requerimiento = RFCalculationRequest(
            target_mhz=180.011,
            tolerance_khz=10.0,
            frequencies=[FrequencyInput(freq_mhz=90.0, signal_type=SignalType.FM)],
        )
        respuesta = RFEngine().calculate(requerimiento)
        assert respuesta.matches == []
        assert respuesta.total_matches == 0
        assert respuesta.warnings, "el motor debe avisar que no hubo productos"

    def test_intermod_no_depende_del_orden_maximo_de_armonicas(self):
        # Con max_harmonic_order=2 los armónicos sólo alcanzan el orden 2, y
        # ninguno de 88.5 ni de 58 cae en 119.0: si igual aparece el IM3
        # (2×88.5 − 58.0), la intermodulación corre por su propio camino.
        def tipos_con(orden: int) -> set[str]:
            requerimiento = RFCalculationRequest(
                target_mhz=119.0,
                tolerance_khz=10.0,
                frequencies=[
                    FrequencyInput(freq_mhz=88.5, signal_type=SignalType.FM),
                    FrequencyInput(freq_mhz=58.0, signal_type=SignalType.TV_UHF),
                ],
                max_harmonic_order=orden,
            )
            respuesta = RFEngine().calculate(requerimiento)
            return {m.tipo for m in respuesta.matches}

        con_orden_2 = tipos_con(2)
        assert "IM3" in con_orden_2, "el IM3 no debe depender de max_harmonic_order"
        assert con_orden_2 == tipos_con(5), (
            "la intermodulacion no debe variar cuando cambia el orden de armonicas"
        )

    def test_im3_canonico_saez_sigue_dando_119(self):
        # El caso de referencia del proyecto: 2×88.5 − 58.0 = 119.0 MHz.
        requerimiento = RFCalculationRequest(
            target_mhz=119.0,
            tolerance_khz=10.0,
            frequencies=[
                FrequencyInput(freq_mhz=88.5, signal_type=SignalType.FM),
                FrequencyInput(freq_mhz=58.0, signal_type=SignalType.TV_UHF),
            ],
        )
        respuesta = RFEngine().calculate(requerimiento)
        im3 = next((m for m in respuesta.matches if m.tipo == "IM3"), None)
        assert im3 is not None, "falta el IM3 canonico 2×88.5 − 58"
        assert im3.result_mhz == pytest.approx(119.0, abs=1e-6)
        assert im3.error_khz == pytest.approx(0.0, abs=0.1)
        assert len(im3.frequencies_involved) == 2
