"""
tests/test_trayectoria_viva.py
==============================
Por qué una trayectoria en vivo se congelaba con la aeronave todavía en el mapa.

El síntoma reportado
-------------------
El operador seguía una trayectoria de un avión. La aeronave siguió su recorrido
y se veía moverse en vivo, pero la línea dejó de crecer: se veía hasta el punto
en el que había dibujado sus objetos y de ahí en adelante no avanzaba. Ninguna
pantalla decía qué había pasado.

Había dos defectos, y ninguno de los dos era «la trayectoria está tapada».

**1. La condición que decide si la línea sigue creciendo leía la lista
equivocada.** El estado vivo de una aeronave llega por WebSocket a
``liveStates`` y se le pega a cada fila en un ``computed`` llamado
``watchlistWithState``. La condición leía ``watchlist`` —la lista cruda— buscando
un campo ``.state`` que esa lista no tiene. Medido sobre las dos aeronaves que
el operador estaba siguiendo: ``state`` era ``undefined`` en las dos, así que la
rama del feed vivo **no se ejecutaba nunca**.

**2. El sondeo pedía dato fresco y recibía el mismo.** El sondeo corre cada 30 s
y el caché de tracks dura 300 s, así que nueve de cada diez sondeos recibían los
mismos bytes: la línea se quedaba quieta durante cinco minutos y después saltaba.

**Por qué el síntoma era tan confuso.** El marcador del avión y la trayectoria
vienen de caminos distintos: el marcador de los vectores de estado, que llegan
por WebSocket; la línea, del sondeo. Congelar uno no toca el otro, y por eso se
veía una aeronave viva con una línea muerta y ninguna explicación.
"""

import pytest

from app.core.config import get_settings
from app.services.flight_service import build_track


class ServicioFalso:
    """OpenSky sin red, que anota cómo lo llamaron."""

    def __init__(self):
        self.llamadas = []

    async def get_track(self, icao24, time_=None, ttl=None):
        self.llamadas.append({"icao24": icao24, "time": time_, "ttl": ttl})
        return {
            "icao24": icao24,
            "points": [
                {"timestamp": 1790962000, "latitude": -34.6, "longitude": -58.4},
                {"timestamp": 1790962060, "latitude": -34.7, "longitude": -58.3},
            ],
            "point_count": 2,
        }


def correr(*args, **kwargs):
    import asyncio

    return asyncio.run(build_track(*args, **kwargs))


class TestElSondeoPideDatoFresco:
    def test_un_ttl_llega_hasta_opensky(self, db):
        # La vía completa: la ruta acorta el caché, build_track lo pasa, y el
        # servicio lo entrega. Si se pierde en un salto, el sondeo vuelve a leer
        # los mismos bytes y la línea se congela de nuevo sin que nada lo diga.
        servicio = ServicioFalso()
        correr(servicio, db, "e02659", ttl=30)
        assert servicio.llamadas[0]["ttl"] == 30

    def test_sin_ttl_no_se_toca_el_cache(self, db):
        # Un vuelo histórico es inmutable y su track puede cachearse cinco
        # minutos sin que nada se pierda. Pedir fresco siempre cobraría créditos
        # de más por datos que no cambian.
        servicio = ServicioFalso()
        correr(servicio, db, "e02659")
        assert servicio.llamadas[0]["ttl"] is None

    def test_el_poll_y_el_uso_normal_no_se_confunden(self, db):
        # Dos pedidos seguidos del mismo avión: uno del sondeo y otro de una
        # consulta normal. El segundo no debe arrastrar el ttl del primero.
        servicio = ServicioFalso()
        correr(servicio, db, "e02659", ttl=30)
        correr(servicio, db, "e02659")
        assert [c["ttl"] for c in servicio.llamadas] == [30, None]


class TestElServicioEntregaElTtlAlCache:
    """El último eslabón, que era el que nadie comprobaba.

    Las pruebas de arriba usan un servicio falso, así que verifican que
    `build_track` **pasa** el ttl a `service.get_track`. No verifican que
    `get_track` lo **entregue** a la caché, que es donde el valor se vuelve
    efectivo: un servicio que aceptara el parámetro y lo tirara dejaría las
    pruebas en verde con el defecto entero.
    """

    def test_get_track_recibe_el_ttl(self):
        from pathlib import Path

        fuente = (
            Path(__file__).resolve().parents[1]
            / "app" / "services" / "opensky_service.py"
        ).read_text(encoding="utf-8")
        cuerpo = fuente.split("async def get_track(")[1].split("\n    async def")[0]
        assert "ttl" in cuerpo.split("params = ")[0], "get_track tiene que aceptar ttl"
        assert ", ttl" in cuerpo, (
            "el ttl tiene que llegar a `_cached`; aceptarlo y no usarlo deja "
            "todo verde y el defecto vivo"
        )

    def test_el_cache_acepta_un_ttl_por_llamada(self):
        # La infraestructura tiene que admitirlo, o el ajuste de arriba sería
        # un argumento que nadie recibe.
        from pathlib import Path

        cache = (
            Path(__file__).resolve().parents[1] / "app" / "services" / "cache.py"
        ).read_text(encoding="utf-8")
        assert "ttl: Optional[float] = None" in cache

        servicio = (
            Path(__file__).resolve().parents[1]
            / "app" / "services" / "opensky_service.py"
        ).read_text(encoding="utf-8")
        cuerpo = servicio.split("async def _cached(")[1].split("\n    # ")[0]
        assert "ttl" in cuerpo


class TestElCachePorDefectoEsMasCortoQueElSondeo:
    def test_el_intervalo_de_sondeo_esta_dentro_del_ttl(self):
        # La relación que hacía el síntoma posible: el sondeo es más rápido que
        # el caché. Si alguna vez el ttl por defecto vuelve a ser menor que el
        # sondeo, el sondeo gasta créditos para recibir lo mismo.
        #
        # El valor del sondeo vive en el frontend (`TRACK_REFRESH_MS = 30000`),
        # así que se lee de ahí en vez de duplicarlo: una constante copiada deja
        # de ser cierta en silencio la primera vez que alguien cambia una.
        import re
        from pathlib import Path

        panel = (
            Path(__file__).resolve().parents[1]
            / "frontend" / "src" / "components" / "gis" / "FlightPanel.vue"
        ).read_text(encoding="utf-8")
        m = re.search(r"TRACK_REFRESH_MS\s*=\s*(\d+)", panel)
        assert m, "no se encuentra TRACK_REFRESH_MS en FlightPanel.vue"
        sondeo_ms = int(m.group(1))
        ttl = get_settings().cache_ttl_tracks_live_s
        assert ttl <= sondeo_ms / 1000, (
            f"el ttl de track en vivo ({ttl} s) dura más que el sondeo "
            f"({sondeo_ms / 1000} s): el sondeo pediría lo mismo "
            f"{int((ttl * 1000) / sondeo_ms) - 1} veces de cada {int((ttl * 1000) / sondeo_ms)}"
        )

    def test_el_ttl_por_defecto_no_es_el_de_track(self):
        # Los dos caché son de pools distintos: el de una ruta terminada puede
        # durar cinco minutos, el de una ruta que se está formando no.
        settings = get_settings()
        assert settings.cache_ttl_tracks_live_s < settings.cache_ttl_tracks_s, (
            "una trayectoria en vivo no puede cachearse más que una histórica: "
            "es la única que cambia mientras se mira"
        )


class TestLaRutaExponeElParametro:
    def test_la_ruta_tiene_fresh(self):
        # El contrato entre las dos puntas. Si el nombre cambia en un lado y no
        # en el otro, `fresh=true` se ignora en silencio y nadie se entera: el
        # síntoma es una línea congelada, no un error.
        from pathlib import Path

        ruta = (
            Path(__file__).resolve().parents[1]
            / "app" / "api" / "routes" / "flights.py"
        ).read_text(encoding="utf-8")
        assert "fresh: bool = Query(" in ruta
        # Se comprueban las dos mitades del condicional, no la línea entera: el
        # espaciado de un `=` no es el contrato, pero **qué pasa cuando `fresh`
        # es falso** sí lo es. Un `else` que devolviera el ttl largo haría que
        # cada consulta normal costara créditos de más sin avisar.
        assert "cache_ttl_tracks_live_s if fresh else None" in ruta

    def test_el_cliente_deja_pasar_fresh(self):
        from pathlib import Path

        store = (
            Path(__file__).resolve().parents[1]
            / "frontend" / "src" / "stores" / "flights.js"
        ).read_text(encoding="utf-8")
        assert "params.fresh = true" in store, (
            "el store tiene que poder pedir dato fresco; sin esto el sondeo "
            "vuelve a leer caché"
        )

    def test_el_sondeo_pide_fresco(self):
        from pathlib import Path

        panel = (
            Path(__file__).resolve().parents[1]
            / "frontend" / "src" / "components" / "gis" / "FlightPanel.vue"
        ).read_text(encoding="utf-8")
        assert "loadTrack(liveTrackIcao24, { fresh: true })" in panel


class TestLaCondicionDeVueloLeeElFeedVivo:
    """El defecto que mataba el sondeo."""

    def _panel(self):
        from pathlib import Path

        return (
            Path(__file__).resolve().parents[1]
            / "frontend" / "src" / "components" / "gis" / "FlightPanel.vue"
        ).read_text(encoding="utf-8")

    def test_no_busca_state_en_la_lista_cruda(self):
        # La lista cruda no tiene `state`: quien se lo pega es el computed
        # `watchlistWithState`. Leer la lista cruda hace que la rama del feed
        # vivo sea código muerto, y la condición cae siempre a la heurística.
        panel = self._panel()
        assert "watchlist.find((s) => s.icao24 === track?.icao24)?.state" not in panel, (
            "la lista cruda no lleva `state`; hay que leer watchlistWithState o "
            "liveStates"
        )

    def test_consulta_las_fuentes_que_si_lo_llevan(self):
        panel = self._panel()
        assert "watchlistWithState" in panel
        assert "liveStates" in panel

    def test_la_heuristica_queda_como_ultimo_recurso(self):
        # El final del track se sigue usando, pero sólo cuando no hay vector de
        # estado. Es un dato de otro producto y más lento: usarlo como respuesta
        # principal hace que un hueco de datos de un minuto mate el sondeo.
        panel = self._panel()
        cuerpo = panel.split("function isAirborne(track)")[1].split("\n}")[0]
        assert cuerpo.index("liveStates") < cuerpo.index("end_time"), (
            "el feed vivo tiene que comprobarse antes del final del track"
        )


@pytest.mark.parametrize("codigo", ["e02659", "e06543", "e0b354"])
def test_la_comparacion_de_direcciones_no_depende_de_las_mayusculas(codigo):
    """El mismo criterio que `untrackAircraft` ya tuvo que corregir una vez.

    `untrackAircraft` compara en minúsculas porque, como dice su comentario, la
    API normaliza el código y un argumento en mayúsculas dejaba la fila viva.
    La condición de vuelo comparaba con `===` y con el valor crudo, o sea con
    el mismo error en el mismo store, en la línea de al lado.
    """
    from pathlib import Path

    panel = (
        Path(__file__).resolve().parents[1]
        / "frontend" / "src" / "components" / "gis" / "FlightPanel.vue"
    ).read_text(encoding="utf-8")
    cuerpo = panel.split("function isAirborne(track)")[1].split("\n}")[0]
    assert "toLowerCase()" in cuerpo, (
        "comparar la dirección sin normalizar es el error que untrackAircraft "
        "ya tuvo que corregir"
    )