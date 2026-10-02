"""
tests/test_error_icao24.py
=========================
El mensaje que rechaza una dirección de aeronave inválida.

Por qué este archivo existe
---------------------------
El operador escribió ``LVKCC`` en el campo de dirección de aeronave y no encontró
nada. Lo que vio fue, textual, en inglés::

    Invalid ICAO24 'lvkcc': expected 6 hex characters.

Tres cosas mal en una línea, y las tres importan:

1. **Está en inglés**, dentro de una aplicación que debe estar toda en español.
2. **No dice qué hacer.** Explica por qué falló y nada más.
3. **Estaba repetido cuatro veces** en ``flight_service.py``, en cuatro rutas
   distintas. Cuatro copias de un mensaje divergen; es la razón por la que existe
   ``_explicar_icao24_invalido``.

Lo que ``LVKCC`` es en realidad
------------------------------
Un **callsign**: el nombre del vuelo, como lo muestra el radar de vuelo. Un ICAO24
son seis caracteres hexadecimales, y ahí hay ``l``, ``v`` y ``k``, que no lo son.
La distinción no es académica: el buscador por callsign **sí** funciona, para
aeronaves que están transmitiendo en este momento. Decirlo convierte un error
muerto en el camino correcto.

La limitación que no se puede arreglar
-------------------------------------
OpenSky no tiene búsqueda histórica por callsign, con credenciales o sin ellas. Un
vuelo de hace días sólo se encuentra si se conoce su ICAO24. Eso lo dice el propio
backend en ``warnings``; estas pruebas fijan que lo siga diciendo.
"""

from pathlib import Path

import pytest

from app.services.flight_service import (
    _explicar_icao24_invalido,
    _valid_icao24,
    valid_icao24,
)

#: Valores que el operador puede escribir en un campo de seis caracteres.
ENTRADAS = ["LVKCC", "lvkcc", "KCC", "abc", "12345", "e02659x", "", "   "]


class TestElMensajeEstaEnEspanol:
    """Un mensaje que llega al panel del operador, en el idioma del operador."""

    @pytest.mark.parametrize("valor", ENTRADAS)
    def test_no_contiene_ingles(self, valor):
        texto = _explicar_icao24_invalido(valor).lower()
        for palabra in ("invalid", "expected", "hex characters", "error", "expected 6"):
            assert palabra not in texto, f"queda texto en inglés: {palabra!r}"

    @pytest.mark.parametrize("valor", ENTRADAS)
    def test_no_usa_las_comillas_del_interprete(self, valor):
        # ``!r`` de Python produce ``'LVKCC'`` con comillas simples. Es un detalle
        # de ``repr()`` filtrado a la interfaz, y el operador no debería ver
        # comillas simples en un mensaje en español.
        assert "'" not in _explicar_icao24_invalido(valor)

    def test_el_texto_ingles_del_viejo_no_sobrevive_en_el_codigo(self):
        # La guarda de portero: recorre el archivo y falla si el texto viejo
        # reaparece. Cuatro rutas distintas lo usaban, y basta con que una vuelva
        # a escribirlo para que el operador lo lea en inglés otra vez.
        fuente = Path(__file__).resolve().parents[1] / "app" / "services" / "flight_service.py"
        texto = fuente.read_text(encoding="utf-8")
        assert "expected 6 hex characters" not in texto

    def test_las_cuatro_rutas_pasan_por_el_mismo_ayudante(self):
        # Si una de las cuatro vuelve a escribir su propio mensaje, las copias
        # divergen y el operador ve dos textos para el mismo problema.
        fuente = Path(__file__).resolve().parents[1] / "app" / "services" / "flight_service.py"
        texto = fuente.read_text(encoding="utf-8")
        usos = texto.count("_explicar_icao24_invalido(")
        assert usos == 5, f"se esperaban cuatro usos más la definición; hay {usos}"


class TestElMensajeDiceQueHacer:
    """La parte que faltaba: no sólo por qué falló, sino qué escribir."""

    def test_un_callsign_lo_dice_por_el_campo_de_callsign(self):
        texto = _explicar_icao24_invalido("LVKCC")
        assert "callsign" in texto.lower()
        # Y dice que ese campo funciona, que es lo que convierte el error en un
        # camino. Sin esto el operador lee «no sirve» y se rinde.
        assert "funciona" in texto.lower()

    def test_un_valor_sin_letras_igualmente_dice_que_use_el_callsign(self):
        texto = _explicar_icao24_invalido("12345").lower()
        assert "callsign" in texto
        assert "seis caracteres hexadecimales" in texto

    def test_explica_las_dos_cosas_que_se_necesitan(self):
        # Qué es un ICAO24, y qué es lo que se escribió. Sin las dos, el mensaje
        # obliga a otro viaje a buscar la definición.
        texto = _explicar_icao24_invalido("LVKCC").lower()
        assert "seis caracteres hexadecimales" in texto
        assert "no es una dirección de aeronave" in texto


class TestLaExplicacionNoMiente:
    """La rama del callsign tiene que abrirse sólo cuando corresponde."""

    def test_abc_no_recibe_la_explicacion_de_las_letras(self):
        # «abc» son tres letras **hexadecimales** válidas. Lo que le falta es
        # longitud, así que decir «aquí hay caracteres que no son hexadecimales»
        # sería falso. Es el caso que hace que la regla sea «fuera del alfabeto»,
        # no «tiene letras».
        texto = _explicar_icao24_invalido("abc")
        assert "no lo son" not in texto.lower()
        assert "seis caracteres hexadecimales" in texto

    def test_cuenta_cuantos_caracteres_no_son_hexadecimales(self):
        # El mensaje afirma un número. Si dice 3 y hay 5, el operador cuenta y
        # pierde la confianza en todo lo demás que dice la aplicación.
        texto = _explicar_icao24_invalido("lvkcc")
        assert "3 que no lo son" in texto

    def test_una_direccion_valida_no_pasa_por_este_mensaje(self):
        for codigo in ("e02659", "abcdef", "000000"):
            assert _valid_icao24(codigo), codigo
            # Si se le pasara, el mensaje sería absurdo para un código bueno, y
            # además nadie lo vería nunca: la ruta válida no llama a este texto.

    def test_el_validador_trabaja_sobre_la_forma_normalizada(self):
        # ``_valid_icao24`` sólo acepta minúsculas, y eso no es un defecto:
        # normalizar es trabajo de quien llama, y las nueve rutas que lo usan lo
        # hacen antes de validar (``str(x).strip().lower()``). Por eso una
        # dirección escrita en mayúsculas por el operador funciona igual.
        #
        # La primera versión de esta prueba afirmaba que ``ABCDEF`` era válida
        # para el validador, y falló. La que falla es la prueba: estaba
        # preguntando por el validador algo que depende de los llamadores.
        assert not _valid_icao24("ABCDEF")
        assert _valid_icao24("ABCDEF".lower())


class TestElBuscadorPorCallsignSigueAvisando:
    """Lo que no se puede arreglar, pero sí se puede seguir diciendo."""

    def test_el_alias_publico_sigue_disponible(self):
        # La ruta del listado de vuelos valida con el mismo criterio, y una ruta
        # que tiene que llegar a un nombre privado es señal de que el chequeo
        # debería estar acá.
        assert valid_icao24 is _valid_icao24

    def test_la_limitacion_de_opensky_sigue_documentada(self):
        # La búsqueda histórica por callsign no existe en OpenSky. Si algún día
        # existiera, este texto sería el que hay que borrar; mientras exista, es
        # lo que evita que el operador repita la búsqueda.
        #
        # Se busca media frase porque el aviso está partido entre dos literales
        # adyacentes: la primera termina en «no ofrece búsqueda por » y la segunda
        # arranca con «callsign sobre vuelos históricos». Buscar la frase entera
        # no la encontraría nunca, y una prueba que no puede pasar no es una
        # prueba.
        fuente = Path(__file__).resolve().parents[1] / "app" / "services" / "flight_service.py"
        texto = fuente.read_text(encoding="utf-8")
        assert "sobre vuelos históricos" in texto


@pytest.mark.parametrize("codigo", ["LVKCC", "lvkcc", "ARG1763", "KCC"])
def test_un_callsign_nunca_pasa_como_icao24(codigo):
    """La propiedad que importa: un nombre de vuelo no se acepta como dirección."""

    assert not _valid_icao24(codigo)


@pytest.mark.parametrize("codigo", ["e02659", "abcdef", "000000"])
def test_una_direccion_real_si_pasa(codigo):
    """Y lo contrario: una dirección de verdad no se rechaza."""

    assert _valid_icao24(codigo)