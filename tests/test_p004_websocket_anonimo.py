"""
tests/test_p004_websocket_anonimo.py
────────────────────────────────────
P0-04: en modo anónimo el WebSocket se rendía y la ruta REST no.

Reproducido en vivo antes de tocar nada, con dos instancias a la vez sobre la
misma base:

* Instancia con credenciales reales: el WebSocket consulta con
  ``auth=oauth2`` y el feed anda.
* Instancia con ``OPENSKY_CLIENT_ID`` y ``OPENSKY_CLIENT_SECRET`` en blanco y
  ``OPENSKY_ALLOW_ANONYMOUS=true`` —que es como sale el proyecto, porque
  `.env.example` viene sin credenciales—: ``GET /flights/live`` respondió
  **200** con ``auth=anonymous`` y una sola petición saliente, mientras que
  ``/ws/flights`` mandó ``not_configured`` y **no hizo ninguna**.

La cuenta de la petición es la prueba, no la impresión: en el log de la
instancia anónima hay **0** líneas ``auth=oauth2`` y exactamente **una**
petición a ``states/all``, la de la ruta REST.

La causa es una sola línea con el predicado equivocado. La ruta REST decide en
``flights.py::_service_or_503`` con ``configured or can_query_states``; el
WebSocket miraba sólo ``configured``, que responde «¿hay credenciales?» cuando
lo que hace falta saber es «¿puedo consultar estados?» — y OpenSky sirve
``/states/all`` a llamadas anónimas desde una bolsa de 400 créditos diarios.

Estas pruebas no abren servidor ni gastan crédito: llaman a ``Hub._tick``
directamente con un servicio falso y un WebSocket falso, así que lo que se
mide es la decisión, sin tiempo de por medio.
"""

from __future__ import annotations

import asyncio

from app.api.routes.ws import FlightSubscription, Hub


# ─── Dobles ──────────────────────────────────────────────────────────────────

class _WSFalsa:
    """Registra lo que el servidor le habría mandado al navegador."""

    def __init__(self) -> None:
        self.mensajes: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.mensajes.append(payload)


class _Servicio:
    """El mínimo que `_tick` toca de OpenSky.

    `configured` y `can_query_states` se ponen a mano en cada prueba porque
    son exactamente los dos predicados en disputa: el primero pregunta si hay
    credenciales, el segundo si se puede consultar.
    """

    def __init__(self, *, configurado: bool, consultable: bool) -> None:
        self.configured = configurado
        self.can_query_states = consultable
        self.consultas = 0

    async def get_states(self, icao24=None) -> dict:
        self.consultas += 1
        # Nada que devolver: lo que se mide es si fue a preguntar.
        return {"states": [], "time": 0, "from_cache": False}


def _tick_con(servicio, monkeypatch, tracked=("abc123",)):
    """Corre un tick de verdad con el servicio y la lista de seguimiento dados."""
    from app.api.routes import ws as ws_mod

    monkeypatch.setattr(ws_mod, "tracked_icao24s", lambda db: list(tracked))

    ws_falso = _WSFalsa()
    sub = FlightSubscription(ws_falso)
    hub = Hub()
    hub.clients.add(sub)

    asyncio.run(hub._tick(servicio))
    return ws_falso.mensajes


def _estados(mensajes: list[dict]) -> list[str]:
    """Los `opensky` de los mensajes de estado: un hecho plano, sin estructuras."""
    return [m["opensky"] for m in mensajes if m.get("type") == "status"]


def _consulto(mensajes: list[dict]) -> bool:
    """Si hubo indicios de que la petición se hizo: `lost` o `states`.

    `_tick` sólo puede emitir esos dos si llegó hasta `get_states`. El estado
    `not_configured` lo manda antes y hace return, así que su ausencia y la
    presencia de uno de estos dos dicen lo mismo por dos caminos distintos.
    """
    return any(m.get("type") in ("lost", "states") for m in mensajes)


# ─── Las pruebas ─────────────────────────────────────────────────────────────

def test_en_anonimo_el_websocket_consulta_en_vez_de_rendirse(monkeypatch):
    """Sin credenciales y con el anónimo activo, el feed tiene que ir a OpenSky.

    Ésta es la que muerde: si vuelve el `if not service.configured` de antes,
    la consulta no se hace y ninguno de los dos hechos se cumple.
    """
    servicio = _Servicio(configurado=False, consultable=True)

    mensajes = _tick_con(servicio, monkeypatch)

    assert servicio.consultas == 1, (
        "el WebSocket no consultó OpenSky en modo anónimo: "
        f"estados de salida {_estados(mensajes)}"
    )
    assert "not_configured" not in _estados(mensajes), (
        "declaró OpenSky no configurado pudiendo consultar sin credenciales"
    )
    assert _consulto(mensajes), f"nada indicó que la petición se hiciera: {mensajes}"


def test_con_credenciales_sigue_consultando(monkeypatch):
    """El caso que ya funcionaba no se rompe al cambiar el predicado."""
    servicio = _Servicio(configurado=True, consultable=True)

    mensajes = _tick_con(servicio, monkeypatch)

    assert servicio.consultas == 1
    assert "not_configured" not in _estados(mensajes)


def test_sin_credenciales_y_sin_anonimo_si_se_rinde(monkeypatch):
    """La compuerta sigue cerrada cuando de verdad no hay forma de consultar.

    Sin esto, la lectura obvia del arreglo sería «borrar el chequeo», que
    convertiría un aviso claro en un feed mudo.
    """
    servicio = _Servicio(configurado=False, consultable=False)

    mensajes = _tick_con(servicio, monkeypatch)

    assert servicio.consultas == 0, "consultó sin tener forma de hacerlo"
    assert "not_configured" in _estados(mensajes), (
        f"no avisó de que no había forma de consultar: {mensajes}"
    )


def test_nada_se_pregunta_si_no_hay_aeronaves_en_seguimiento(monkeypatch):
    """El orden de las compuertas: la lista vacía sigue ganando.

    Preguntar con la lista vacía convierte la llamada en una consulta global
    que cuesta 4 créditos para datos que nadie pidió, así que este chequeo va
    antes que el de las credenciales y no debe moverse.
    """
    servicio = _Servicio(configurado=False, consultable=True)

    mensajes = _tick_con(servicio, monkeypatch, tracked=())

    assert servicio.consultas == 0, "consultó con la lista de seguimiento vacía"
    assert _estados(mensajes) == ["idle"], mensajes


def test_el_mensaje_de_sin_acceso_esta_en_espanol(monkeypatch):
    """Lo que ve el operador no puede llegar en inglés.

    En 0.30.1 ya se corrigió un mensaje en inglés en una ruta; este es el
    mismo defecto en el canal de WebSocket.
    """
    servicio = _Servicio(configurado=False, consultable=False)

    mensajes = _tick_con(servicio, monkeypatch)

    avisos = [m.get("message", "") for m in mensajes if m.get("type") == "status"]
    assert avisos, "no hubo ningún aviso que leer"
    for texto in avisos:
        assert "configured" not in texto, f"mensaje en inglés: {texto}"
        assert "credential" not in texto.lower(), f"mensaje en inglés: {texto}"
        assert "Defina" in texto or "anonimo" in texto.lower() or "anónimo" in texto, (
            f"el aviso no dice qué hacer: {texto}"
        )
