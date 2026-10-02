"""
tests/test_busqueda_por_archivo.py
==================================
Buscar por callsign cuando la aeronave no está volando.

El problema que esto arregla
----------------------------
El operador buscó el vuelo de ayer por su nombre de vuelo y la aplicación le
dijo que no había ninguna aeronave. El nombre no estaba volando *ahora*, que es
distinto de que no exista el vuelo: OpenSky sólo publica vectores en vivo, así que
un callsign que no está transmitiendo no aparece, y sin dirección no hay forma de
preguntar por el historial.

Pero la propia aplicación guarda la dirección de cada aeronave que alguien
siguió. Medido el 2026-10-02: 47 pistas archivadas, 45 con callsign, 17 llamadas
distintas. Para esos casos el vuelo pasado sí se puede encontrar, sin inventar
nada y sin salir de los datos que el sistema escribió.

Lo que estas pruebas fijan
--------------------------
1. Que el archivo se consulta, y sólo **después** de los vectores en vivo: la
   respuesta de OpenSky manda mientras haya respuesta.
2. Que la procedencia se dice. Un callsign resuelto por vectores en vivo y uno
   resuelto por el archivo son dos clases de evidencia distintas, y el operador
   tiene que poder distinguirlas.
3. Que una búsqueda sin base de datos responde lo mismo, en vez de romperse.
4. Que no se elige dirección al azar cuando el nombre designa más de una
   aeronave.
"""

import asyncio

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.flight import AircraftTrack
from app.services.flight_service import (
    _direcciones_en_archivo,
    search_flight,
)

#: Direcciones válidas, para no ensuciar las pruebas con filas que el propio
#: archivo no podría sostener.
ICAO_A = "e02659"
ICAO_B = "a101c3"


class ServicioFalso:
    """OpenSky sin red: los vectores en vivo son lo que el operador mire."""

    def __init__(self, estados=None):
        self._estados = estados or []
        self.llamadas = 0

    async def get_states(self):
        self.llamadas += 1
        return {"states": self._estados}

    async def get_flights_by_aircraft(self, icao24, begin, end):
        return [
            {
                "flight_id": f"{icao24}-1",
                "icao24": icao24,
                "callsign": "PRUEBA1",
                "first_seen": begin,
                "last_seen": end,
                "dep_icao": "SAEZ",
                "arr_icao": "SADF",
                "departure_airport": "AEROPORTOS DE ARGENTINA",
                "arrival_airport": "AEROPORTOS DE ARGENTINA",
                "aircraft_type": "B738",
            }
        ]


def _buscar(*args, **kwargs) -> dict:
    """Ejecuta la corrutina de la búsqueda sin plugin de asyncio.

    El proyecto no tiene `pytest-asyncio`: la convención que estableció
    `tests/test_opensky.py` es un test síncrono que llama a `asyncio.run`. Los
    argumentos se reenvían tal cual, que es lo que permite sustituir
    `await search_flight(...)` por `_buscar(...)` sin tocar el resto de la
    llamada.
    """
    return asyncio.run(search_flight(*args, **kwargs))


def _pista(db: Session, icao24: str, callsign, **extra) -> AircraftTrack:
    fila = AircraftTrack(
        icao24=icao24,
        callsign=callsign,
        source="aerorf",
        point_count=10,
        observed_seconds=60,
        **extra,
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


# ── El archivo local responde lo que los vectores en vivo no pueden ──────────


class TestElArchivoResuelveElVueloPasado:
    def test_un_callsign_archivado_se_busca_como_historia(self, db):
        # La situación del operador: el vuelo no está volando, pero existe.
        _pista(db, ICAO_A, "ARG1763")
        r = _buscar(
            ServicioFalso(), callsign="ARG1763", date="2026-09-30", db=db
        )
        assert r["icao24"] == ICAO_A, r
        assert r["callsign"] == "ARG1763"
        assert r["flights"], "el historial debería traer el vuelo"
        # La procedencia dice que vino del archivo, no de los vectores en vivo.
        assert r["resolved_via"] == "callsign_archivo_aerorf", r["resolved_via"]

    def test_el_aviso_explica_de_donde_salio_la_direccion(self, db):
        # Un número que aparece sin explicación no es provenance: es ruido. El
        # operador tiene que poder decir «esto lo saqué de tu propio archivo».
        _pista(db, ICAO_A, "ARG1763")
        r = _buscar(ServicioFalso(), callsign="ARG1763", db=db)
        joined = " ".join(r["warnings"])
        assert "archivo" in joined.lower()
        assert ICAO_A in joined

    def test_no_se_declara_que_la_aeronave_este_volviendo(self, db):
        # Lo que NO se puede hacer es presentar un vuelo de ayer como si fuera
        # una aeronave en vivo. `states` viene de los vectores de OpenSky y esta
        # aeronave no está en ellos, así que tiene que quedar vacío.
        _pista(db, ICAO_A, "ARG1763")
        r = _buscar(ServicioFalso(), callsign="ARG1763", db=db)
        assert r["states"] == [], "no hay vectores en vivo de esta aeronave"

    def test_el_callsign_se_compara_sin_importar_mayusculas(self, db):
        # El operador escribe «arg1763»; el archivo lo guardó en mayúsculas.
        _pista(db, ICAO_A, "ARG1763")
        r = _buscar(ServicioFalso(), callsign="arg1763", db=db)
        assert r["icao24"] == ICAO_A

    def test_un_callsign_que_no_existe_no_inventa_una_direccion(self, db):
        # Este es el punto en el que sería fácil fabricar algo. No: si no está en
        # vivo ni en el archivo, no hay dirección, y el resultado lo dice.
        _pista(db, ICAO_A, "ARG1763")
        r = _buscar(ServicioFalso(), callsign="LVKCC", db=db)
        assert r["icao24"] is None
        assert r["flights"] == []
        joined = " ".join(r["warnings"]).lower()
        assert "hexadecimales" in joined, joined
        # Y nombra las dos fuentes que se miraron, para que el operador sepa que
        # no fue un fallo de búsqueda.
        assert "archivo" in joined


# ── Precedencia: primero lo que está vivo ───────────────────────────────────


class TestLosVectoresEnVivoMandan:
    def test_lo_vivo_tiene_prioridad_sobre_el_archivo(self, db):
        _pista(db, ICAO_B, "TVF31HC")
        estado = {
            "icao24": ICAO_A,
            "callsign": "TVF31HC",
            "longitude": -58.5,
            "latitude": -34.6,
            "baro_altitude": 10000,
            "velocity": 220.0,
            "true_track": 90.0,
            "vertical_rate": 0.0,
            "on_ground": False,
            "last_contact": 1757000000,
            "time_position": 1757000000,
            "last_seen": 1757000000,
            "squawk": "1234",
            "spi": False,
            "position_source": 0,
        }
        r = _buscar(
            ServicioFalso([estado]), callsign="TVF31HC", db=db
        )
        # La dirección del vector en vivo, no la del archivo, aunque el archivo
        # tenga otra. Son dos aeros distintos y contestaría sobre el equivocado.
        assert r["icao24"] == ICAO_A, r
        assert r["resolved_via"] == "callsign_live_state", r["resolved_via"]

    def test_solo_se_pregunta_por_los_vectores_una_vez(self, db):
        _pista(db, ICAO_A, "ARG1763")
        servicio = ServicioFalso()
        _buscar(servicio, callsign="ARG1763", db=db)
        assert servicio.llamadas == 1, (
            "los vectores en vivo se piden una vez; repetirlos es latencia gratis"
        )


# ── Cuando el nombre designa más de una aeronave ────────────────────────────


class TestMasDeUnaDireccion:
    def test_se_toma_el_registro_mas_reciente_y_se_dicen_los_demas(self, db):
        _pista(db, ICAO_B, "REASIGNADO")
        _pista(db, ICAO_A, "REASIGNADO")
        r = _buscar(ServicioFalso(), callsign="REASIGNADO", db=db)
        # Sin decir cuál, la búsqueda contestaría sobre un avión equivocado.
        assert r["icao24"] == ICAO_A, r
        joined = " ".join(r["warnings"])
        assert ICAO_B in joined, "la otra dirección tiene que quedar a la vista"

    def test_el_orden_es_el_de_las_fechas(self, db):
        _pista(db, ICAO_B, "REASIGNADO")
        _pista(db, ICAO_A, "REASIGNADO")
        candidatas = _direcciones_en_archivo(db, "REASIGNADO")
        assert [c["icao24"] for c in candidatas] == [ICAO_A, ICAO_B]

    def test_cuenta_los_vuelos_de_cada_direccion(self, db):
        for _ in range(3):
            _pista(db, ICAO_A, "ARG1763")
        _pista(db, ICAO_B, "ARG1763")
        candidatas = _direcciones_en_archivo(db, "ARG1763")
        por_direccion = {c["icao24"]: c["vuelos"] for c in candidatas}
        assert por_direccion == {ICAO_A: 3, ICAO_B: 1}

    def test_no_devuelve_una_direccion_invalida_del_archivo(self, db):
        # Una fila con una dirección que no es un ICAO24 no se propone: la
        # búsqueda contestaría con un 400 sobre un dato que el archivo no
        # sostiene, y el operador vería un error invented por el sistema.
        db.add(
            AircraftTrack(icao24="basura", callsign="RARO1", source="aerorf")
        )
        db.commit()
        assert _direcciones_en_archivo(db, "RARO1") == []

    def test_ignora_las_filas_sin_callsign(self, db):
        _pista(db, ICAO_A, None)
        assert _direcciones_en_archivo(db, "") == []
        assert _direcciones_en_archivo(db, "NADA") == []


# ── Sin base de datos la búsqueda sigue respondiendo ────────────────────────


class TestSinBaseDeDatos:
    def test_sin_db_no_hay_excepcion_ni_direccion_inventada(self):
        r = _buscar(ServicioFalso(), callsign="ARG1763")
        assert r["icao24"] is None
        assert r["flights"] == []
        assert r["warnings"], "sin archivo hay que decirlo, no devolver vacío"

    def test_el_ayudante_distingue_no_mirar_de_mirar_y_no_encontrar(self):
        # Sin sesión no se miró nada, y eso no es lo mismo que haber mirado y no
        # haber encontrado. `None` es «no comprobado»: la primera versión
        # devolvía una lista vacía, y el mensaje ensuing le decía al operador que
        # no había ningún vuelo con ese nombre —sin haberlo comprobado—.
        assert _direcciones_en_archivo(None, "ARG1763") is None

    def test_un_error_del_archivo_no_tira_la_busqueda(self, db):
        # El archivo es una fuente secundaria: si está caída, la respuesta es un
        # aviso, no un 500. Un backend que se cae por consultar su propio archivo
        # no puede usarse.
        _pista(db, ICAO_A, "ARG1763")

        class Roto:
            def query(self, *a, **k):
                raise RuntimeError("la base no responde")

        r = _buscar(ServicioFalso(), callsign="ARG1763", db=Roto())
        assert r["icao24"] is None
        assert r["warnings"]

    def test_una_base_caida_no_se_presenta_como_un_archivo_vacio(self):
        # Esta es la distinción que faltaba, y la primera versión de la prueba no
        # la cubría: comprobaba que el aviso contuviera la palabra «archivo», y los
        # dos mensajes la tienen. Revertir el `None` por una lista vacía —que es
        # exactamente el defecto— pasaba la prueba en verde.
        #
        # Un sistema que dice «no hay ningún vuelo con ese nombre» cuando en
        # realidad no pudo mirar está afirmando algo sobre sí mismo que nadie
        # comprobó, y el operador no tiene forma de notar la diferencia.
        class Roto:
            def query(self, *a, **k):
                raise RuntimeError("la base no responde")

        r = _buscar(ServicioFalso(), callsign="ARG1763", db=Roto())
        joined = " ".join(r["warnings"]).lower()
        assert "no se pudo consultar" in joined, joined
        # Y no puede afirmar lo contrario.
        assert "ningún vuelo con ese nombre" not in joined, joined

    def test_un_archivo_vacio_si_se_puede_decir_que_no_hay_na(self, db):
        # El otro lado de la misma distinción: sí se miró, y no había nada. El
        # aviso tiene que decirlo así, y de paso decir cuántas pistas hay, para
        # que el operador sepa que lo que se miró estaba vacío y no ausente.
        r = _buscar(ServicioFalso(), callsign="ARG1763", db=db)
        joined = " ".join(r["warnings"]).lower()
        assert "en el archivo de aerorf" in joined, joined
        assert "no se pudo consultar" not in joined, joined
        assert "que está vacío" in joined, joined

    def test_el_aviso_dice_cuantas_pistas_hay_para_que_la_negativa_pes(self, db):
        # Con una pista archivada y un callsign que no está, el número convierte
        # «no encontré» en «miré esto y aquí no está».
        _pista(db, ICAO_A, "OTRO")
        r = _buscar(ServicioFalso(), callsign="ARG1763", db=db)
        joined = " ".join(r["warnings"]).lower()
        assert "1 vuelo registrado" in joined, joined

    def test_el_mensaje_ingles_no_vuelve_a_la_ruta_del_callsign(self):
        # Y el texto en inglés, que era lo que el operador vio en pantalla.
        fuente = (
            Path(__file__).resolve().parents[1]
            / "app" / "services" / "flight_service.py"
        )
        texto = fuente.read_text(encoding="utf-8")
        assert "expected 6 hex characters" not in texto
        # Y el mensaje viejo, que mandaba al operador a un endpoint de la API.
        assert "/states/all" not in texto, (
            "«/states/all» es un endpoint, no un lugar donde pueda buscar el "
            "operador; nadie lo tiene abierto delante"
        )

    def test_la_busqueda_por_icao24_no_necesita_db(self, db):
        # Un ICAO24 va derecho a OpenSky. Que ahora acepte una sesión no puede
        # haber cambiado esa ruta, y esta prueba lo comprueba.
        _pista(db, ICAO_A, "OTRO")
        r = _buscar(ServicioFalso(), icao24=ICAO_A, db=None)
        assert r["icao24"] == ICAO_A
        assert r["resolved_via"] == "icao24_direct"
        assert r["flights"]