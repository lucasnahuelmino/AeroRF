"""
tests/test_lost_sin_inundar.py
──────────────────────────────
Spec §48: el marco `lost` se mandaba una vez por tick y no se deduplicaba.

El defecto, en `app/api/routes/ws.py`:

    for code in missing:
        for sub in list(self.clients):
            if sub.wants(code):
                await sub.send({"type": "lost", "icao24": code, ...})

Mientras una aeronave de la lista siga sin aparecer en la respuesta de OpenSky
—que es lo normal cuando no está volando o está fuera de su cobertura— el
servidor le reenviaba el **mismo aviso cada 10 s, para siempre**. Es exactamente
lo que la §48 prohíbe y lo que `test_feed_does_not_flood` existe para detectar.

Ese test, además, **no falla: se cuelga**. Mide hasta que cada lectura aguanta
22 s de silencio, y con un frame cada 10 s el silencio nunca llega. Por eso
éste archivo prueba la misma cosa sin servidor ni reloj: corre varios `_tick`
contra la misma conexión y cuenta los frames.

Dos hechos más que salieron de mirar el código, y que cambian el tamaño del
problema:

* El frontend **no tiene ningún manejador de `lost`** — no hay una sola
  coincidencia en `frontend/src`. El frame se mandaba y nadie lo leía.
* `send_status` ya deduplicaba desde 0.30.0 («status repetido cada 10 s»,
  contra la misma §48). El `lost` era el mismo defecto que quedó sin arreglar.

Ninguna de las dos cosas se arregla acá: éste commit sólo deja de inundar. Que
nadie lea `lost` —y por eso el marcador de una aeronave que se fue sigue
quedando en pantalla— va por su cuenta, con decisión del operador.
"""

from __future__ import annotations

import asyncio

from app.api.routes.ws import FlightSubscription, Hub


# ─── Dobles ───────────────────────────────────────────────────────────────────

class _WSFalsa:
    """Registra lo que el servidor le habría mandado al navegador."""

    def __init__(self) -> None:
        self.mensajes: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.mensajes.append(payload)


class _Servicio:
    """Devuelve las respuestas dadas, una por tick, en orden.

    `configured` y `can_query_states` van en verde: el gate de P0-04 ya está
    resuelto y lo que se mide acá pasa de largo de él.
    """

    def __init__(self, respuestas: list[list[dict]]) -> None:
        self._respuestas = list(respuestas)
        self.consultas = 0
        self.configured = True
        self.can_query_states = True

    async def get_states(self, icao24=None) -> dict:
        self.consultas += 1
        estados = self._respuestas.pop(0) if self._respuestas else []
        return {"states": estados, "time": self.consultas, "from_cache": False}


def _estado(icao24: str = "abc123", *, lat: float = -34.5, lon: float = -58.4) -> dict:
    """Una posición plana y completa: `_fingerprint` pide lat/lon con corchetes."""
    return {
        "icao24": icao24,
        "latitude": lat,
        "longitude": lon,
        "altitude": 3000,
        "heading": 90,
        "velocity": 200,
        "on_ground": False,
        "callsign": "TEST",
        "time_position": 1,
    }


def _perdidos(mensajes: list[dict]) -> list[str]:
    """Los `icao24` de los frames `lost`, en el orden en que llegaron."""
    return [m["icao24"] for m in mensajes if m.get("type") == "lost"]


def _ticks(respuestas, monkeypatch, tracked=("abc123",)) -> list[dict]:
    """Varios ticks de verdad sobre **la misma conexión**.

    Ése es el punto: el inundador no se ve en un tick suelto, se ve en la
    repetición. Se reutiliza el mismo doble de servicio que P0-04, que ya
    probó que `_tick` se puede correr sin servidor.
    """
    from app.api.routes import ws as ws_mod

    monkeypatch.setattr(ws_mod, "tracked_icao24s", lambda db: list(tracked))

    ws_falso = _WSFalsa()
    sub = FlightSubscription(ws_falso)
    hub = Hub()
    hub.clients.add(sub)

    servicio = _Servicio(respuestas)
    for _ in respuestas:
        asyncio.run(hub._tick(servicio))
    return ws_falso.mensajes


# ─── Las pruebas ─────────────────────────────────────────────────────────────

def test_una_aeronave_ausente_se_avisa_una_sola_vez(monkeypatch):
    """Tres ticks sin la aeronave y **un solo** frame `lost`.

    Ésta es la que muerde: antes del arreglo salían tres.
    """
    mensajes = _ticks([[], [], []], monkeypatch)

    assert len(_perdidos(mensajes)) == 1, (
        f"mandó {len(_perdidos(mensajes))} avisos de la misma aeronave ausente "
        f"en 3 ticks; la §48 prohíbe repetir una condición que no cambió"
    )
    assert _perdidos(mensajes) == ["abc123"], _perdidos(mensajes)


def test_cada_aeronave_ausente_se_avisa_una_vez(monkeypatch):
    """Dos ausentes en tres ticks: dos frames, no seis."""
    mensajes = _ticks(
        [[], [], []], monkeypatch, tracked=("abc123", "def456")
    )

    perdidos = _perdidos(mensajes)
    assert sorted(perdidos) == ["abc123", "def456"], (
        f"avisos de más o de menos: {perdidos}"
    )
    assert len(perdidos) == 2, f"se repitieron: {perdidos}"


def test_si_vuelve_y_vuelve_a_perderse_se_vuelve_a_avisar(monkeypatch):
    """Deduplicar no puede convertirse en callarse.

    Si el aviso se emitiera una sola vez para siempre, una aeronave que se
    pierda dos veces distintas sólo se enteraría la primera.
    """
    mensajes = _ticks([[], [_estado()], []], monkeypatch)

    assert len(_perdidos(mensajes)) == 2, (
        f"esperaba un aviso por cada caída (2) y hubo {_perdidos(mensajes)}"
    )


def test_al_volver_se_vuelve_a_mandar_su_estado_aunque_no_haya_cambiado(monkeypatch):
    """Si le dijimos al cliente que se la llevó, hay que devolvérsela.

    `FlightSubscription.last` guarda la huella del último estado mandado. Al
    ausentarse, esa huella seguía ahí: al volver con la misma posición
    `changed()` devolvía `False` y no se mandaba nada, así que un cliente que
    hubiera borrado el marcador nunca lo recupera. Éste es el reverso del
    dedupe, y sin él el arreglo dejaría un hueco.
    """
    mensajes = _ticks([[_estado()], [], [_estado()]], monkeypatch)

    frames_de_estados = [m for m in mensajes if m.get("type") == "states"]
    assert len(frames_de_estados) >= 2, (
        "la aeronave volvió y su estado no se reenvió: sólo hubo "
        f"{len(frames_de_estados)} frame de estados en 3 ticks "
        "(uno por la ida y ninguno por la vuelta)"
    )
    que_llego = [
        s["icao24"] for m in frames_de_estados for s in m["states"]
    ]
    assert "abc123" in que_llego, f"el estado que volvió no la traía: {que_llego}"


def test_el_aviso_de_aeronave_perdida_esta_en_espanol(monkeypatch):
    """Lo que ve el operador no puede llegar en inglés.

    Regresión del mismo texto que ya estaba; si alguien lo traduce al pasar
    por acá, este test lo agarra.
    """
    mensajes = _ticks([[]], monkeypatch)

    avisos = [m for m in mensajes if m.get("type") == "lost"]
    assert avisos, "no hubo ningún aviso que leer"
    for aviso in avisos:
        texto = aviso.get("message", "")
        assert texto, "el aviso vino sin texto"
        for palabra in ("not found", "no signal", "coverage is", "does not"):
            assert palabra not in texto, f"mensaje en inglés: {texto}"
        assert "OpenSky" in texto, f"el aviso no nombra la causa: {texto}"
