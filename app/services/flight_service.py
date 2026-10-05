"""
services/flight_service.py
──────────────────────────
Flight search, trajectory assembly, local recording and the watchlist
(spec §20–§27, §56).

The governing rule: **never invent a position.** Three distinct
provenance values flow through this module and are preserved all the way
to the API response:

* ``historical`` — a waypoint from OpenSky's track store,
* ``live``       — a current OpenSky state vector,
* ``aerorf``     — a sample AeroRF recorded itself during a session.

When a track is assembled the module reports which sources contributed how
many points, and never back-fills gaps. If OpenSky gives 12 waypoints over
a two-hour flight, the response says 12 points and explains the mean step;
it does not interpolate a 1 Hz line and present it as observed data.
"""

from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.geo import haversine_m, path_summary
from app.core.logging import flight_log, opensky_log
from app.core.time import utcnow
from app.core.units import to_metres
from app.models.constants import (
    SESSION_ERROR,
    SESSION_RECORDING,
    SESSION_STOPPED,
    TRACK_SOURCE_AERORF,
    TRACK_SOURCE_MERGED,
    TRACK_SOURCE_OPENSKY,
    PROVENANCE_HISTORICAL,
    PROVENANCE_LIVE,
)
from app.models.flight import (
    AircraftPosition,
    AircraftTrack,
    Flight,
    FlightSelection,
    FlightSession,
)
from app.models.map_object import MapObject

#: Distinct colours for the five watchlist slots (spec §25).
SLOT_COLORS = ("#22c55e", "#3b82f6", "#f97316", "#a855f7", "#eab308")

#: Hard cap from the spec.
MAX_TRACKED = 5


class FlightServiceError(RuntimeError):
    """Invalid flight operation."""


def _utc(ts: Optional[int | float]) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).replace(tzinfo=None)
    except (ValueError, OSError, OverflowError):
        return None


# ─── Search (spec §20) ───────────────────────────────────────────────────────

async def search_flight(
    service,
    callsign: Optional[str] = None,
    icao24: Optional[str] = None,
    date: Optional[str] = None,
    time_hint: Optional[str] = None,
    window_hours: int = 6,
    db: Optional[Session] = None,
) -> dict:
    """Find a flight by callsign or ICAO24.

    OpenSky has no callsign search endpoint, so a callsign lookup is
    resolved in two steps: match the callsign against current state
    vectors to learn the ICAO24, then query ``/flights/aircraft`` for the
    history. Each step is documented in the response under ``resolved_via``
    so the operator can see how the aircraft was identified.

    When the callsign is not flying, ``db`` is consulted before giving up:
    AeroRF's own archive of followed aircraft often already knows the address,
    and a flight from yesterday is a flight the operator can look for. The
    answer says which of the two routes answered, because one is OpenSky's
    live picture and the other is this installation's record, and they are
    not the same kind of evidence.
    """
    result: dict[str, Any] = {
        "query": {
            "callsign": callsign, "icao24": icao24,
            "date": date, "time_hint": time_hint, "window_hours": window_hours,
        },
        "resolved_via": None,
        "icao24": None,
        "callsign": None,
        "flights": [],
        "states": [],
        "warnings": [],
    }

    # ── Resolve ICAO24 from a callsign via live state vectors ──────────
    # Tres fuentes, en este orden, y cada una deja rastro en `resolved_via`:
    # los vectores en vivo de OpenSky, el archivo propio de AeroRF, o nada.
    if icao24 and not callsign:
        code = str(icao24).strip().lower()
        if not _valid_icao24(code):
            raise FlightServiceError(
                _explicar_icao24_invalido(icao24),
            )
        result["icao24"] = code
        result["resolved_via"] = "icao24_direct"
    elif callsign:
        wanted = callsign.strip().upper()
        if not wanted:
            raise FlightServiceError("Empty callsign.")
        live = await service.get_states()
        match = _match_callsign(live.get("states") or [], wanted)
        if match:
            result["icao24"] = match["icao24"]
            result["callsign"] = match.get("callsign")
            result["states"].append(match)
            result["resolved_via"] = "callsign_live_state"
        else:
            # OpenSky no busca por callsign en el historial, pero AeroRF sí tiene
            # un archivo propio: si alguien siguió esa aeronave, la dirección
            # está guardada y el vuelo pasado se puede consultar igual.
            candidatas = _direcciones_en_archivo(db, wanted)
            if not candidatas:
                # Dos mensajes, no uno: que no se haya encontrado y que no se
                # haya podido mirar son cosas distintas, y fundir el segundo en
                # el primero es afirmar sobre el propio sistema algo que nadie
                # comprobó.
                if candidatas is None:
                    result["warnings"].append(
                        f"No se encontró ninguna aeronave en vuelo con el callsign "
                        f"{wanted} en este momento, y no se pudo consultar el "
                        f"archivo de AeroRF para buscarlo entre los vuelos ya "
                        f"registrados. OpenSky no ofrece búsqueda por callsign "
                        f"sobre vuelos históricos: un vuelo pasado sólo se "
                        f"consulta por su dirección de aeronave, seis caracteres "
                        f"hexadecimales. Si la tiene, escríbala en el campo ICAO24."
                    )
                else:
                    registrados = _pistas_totales(db)
                    total = (
                        f" ({registrados} "
                        f"{'vuelo registrado' if registrados == 1 else 'vuelos registrados'} "
                        f"en total)"
                        if registrados
                        else ", que está vacío"
                    )
                    result["warnings"].append(
                        f"No se encontró ninguna aeronave en vuelo con el callsign "
                        f"{wanted} en este momento, ni ningún vuelo con ese nombre "
                        f"en el archivo de AeroRF{total}. OpenSky no ofrece "
                        f"búsqueda por callsign sobre vuelos históricos: un vuelo "
                        f"pasado sólo se consulta por su dirección de aeronave, "
                        f"seis caracteres hexadecimales. Si la tiene, escríbala "
                        f"en el campo ICAO24."
                    )
                return result
            elegida = candidatas[0]
            result["icao24"] = elegida["icao24"]
            result["callsign"] = elegida["callsign"]
            result["resolved_via"] = "callsign_archivo_aerorf"
            aviso = (
                f"El callsign {wanted} no está volando ahora, así que no aparece "
                f"en los vectores en vivo de OpenSky. Sí está en el archivo de "
                f"AeroRF: {elegida['vuelos']} "
                f"{'vuelo registrado' if elegida['vuelos'] == 1 else 'vuelos registrados'}, "
                f"identificado como {elegida['icao24']}. Los vuelos históricos se "
                f"piden por esa dirección."
            )
            if len(candidatas) > 1:
                otras = ", ".join(c["icao24"] for c in candidatas[1:])
                aviso += (
                    f" Ese mismo nombre de vuelo aparece además bajo {otras}: se "
                    f"usó {elegida['icao24']}, que es el registro más reciente."
                )
            result["warnings"].append(aviso)

    if not result["icao24"]:
        return result

    code = result["icao24"]

    # ── Historical flights for that aircraft ────────────────────────────
    begin, end = _window(date, time_hint, window_hours)
    try:
        flights = await service.get_flights_by_aircraft(code, begin, end)
    except Exception as exc:  # upstream failures must not kill the search
        result["warnings"].append(
            f"No se pudieron obtener los vuelos históricos: {exc}"
        )
        flights = []

    result["flights"] = [_normalise_flight(f) for f in flights] if flights else []
    if not result["flights"]:
        result["warnings"].append(
            "OpenSky no tiene registro de vuelos para este avión en la ventana "
            "consultada. Los endpoints /flights/* se procesan por lote durante la "
            "noche, por lo que el vuelo del día anterior puede no estar aún."
        )

    return result


def _match_callsign(states: Iterable[dict], wanted: str) -> Optional[dict]:
    """Exact match first, then prefix — never a fuzzy substring guess."""
    exact, prefix = None, None
    for state in states:
        cs = (state.get("callsign") or "").strip().upper()
        if not cs:
            continue
        if cs == wanted:
            exact = state
            break
        if prefix is None and cs.startswith(wanted):
            prefix = state
    return exact or prefix


def _valid_icao24(code: str) -> bool:
    return (
        len(code) == 6
        and all(c in "0123456789abcdef" for c in code)
    )


def _explicar_icao24_invalido(icao24: str) -> str:
    """
    Por qué este valor no es un ICAO24, y qué hacer en su lugar.

    **Por qué existe.** Los cuatro lugares que rechazaban un ICAO24 repetían el
    mismo texto, en inglés, diciendo que se esperaban seis caracteres hexadecimales.
    El operador lo vio tal cual en el panel de vuelos, dentro de una aplicación que
    debe estar toda en español, y sin ninguna pista de qué hacer.

    **La pista es la parte que importa.** Un ICAO24 son seis caracteres
    hexadecimales, así que cualquier otra cosa no lo es. Y hay un caso que
    merece nombrarse: algo con letras donde un hexadecimal no las tiene es,
    probablemente, un *callsign* — elFlightradar muestra "LVKCC" como vuelo, y es
    un nombre de vuelo, no una dirección de aeronave. Decirlo convierte un error
    seco en el camino correcto, y el buscador por callsign sí funciona para
    aeronaves que están transmitiendo.

    La rama de arriba solo se abre cuando hay caracteres **fuera** del alfabeto
    hexadecimal. «abc» son tres letras válidas y lo que le falta es longitud, así que
    decir «tiene letras» sería falso; «lvkcc» tiene l, v y k, que es exactamente lo
    que lo descarta como dirección y lo que delata un nombre de vuelo.

    Un mensaje, cuatro lugares: la alternativa es cuatro copias que divergen.
    """
    valor = str(icao24).strip()
    fuera_del_hex = [c for c in valor.lower() if c not in "0123456789abcdef"]
    if fuera_del_hex:
        return (
            f"«{valor}» no es una dirección de aeronave: un ICAO24 son seis "
            f"caracteres hexadecimales (0-9 y a-f), y aquí hay "
            f"{len(fuera_del_hex)} que no lo son. Si es un nombre de vuelo como "
            f"LVKCC, escríbalo en el campo de callsign: ese campo sí funciona "
            f"para aeronaves que están volando ahora."
        )
    return (
        f"«{valor}» no es una dirección de aeronave: un ICAO24 son seis "
        f"caracteres hexadecimales (0-9 y a-f). Si es un nombre de vuelo, "
        f"escríbalo en el campo de callsign."
    )


def _pistas_totales(db: Optional[Session]) -> Optional[int]:
    """Cuántos vuelos hay archivados, para poder decirlo en el aviso.

    Sin este número, «no se encontró en el archivo» y «el archivo no se pudo
    abrir» se leen casi igual desde el panel, y el operador no tiene forma de
    saber si lo que se miró estaba vacío o no se miró.

    ``None`` si tampoco esto se pudo leer: es el mismo «no comprobado» que en
    ``_direcciones_en_archivo``, y merece el mismo trato.
    """
    if db is None:
        return None
    try:
        return int(db.query(func.count(AircraftTrack.id)).scalar() or 0)
    except Exception:  # pragma: no cover - same rule: the archive never breaks a search
        return None


#: Public alias. The flight-list endpoint validates the same way, and a route
#: that has to reach through a private name is a sign the check belongs here.
valid_icao24 = _valid_icao24


def _direcciones_en_archivo(db: Optional[Session], wanted: str) -> Optional[list[dict[str, Any]]]:
    """
    Qué direcciones de aeronave tiene un callsign entre los vuelos registrados.

    **Por qué existe.** OpenSky no tiene búsqueda histórica por callsign, así que
    sin una dirección no hay forma de preguntar por un vuelo que ya pasó. La
    versión anterior de esta búsqueda se rendía ahí y le decía al operador que no
    había nada —cuando lo que probablemente quería era un vuelo suyo de ayer—,
    sin mirar lo que la propia aplicación ya tenía guardado. Medido en la base el
    2026-10-02: de 47 pistas archivadas, 45 llevan callsign, y son 17 llamadas
    distintas.

    **Qué es y qué no es.** No se estima nada. La dirección sale de una fila que
    el sistema escribió al seguir esa aeronave, así que es un dato observado, con
    su procedencia: la respuesta dice por dónde se identificó.

    **Por qué la más reciente.** Los nombres de vuelo se reasignan, y un mismo
    nombre puede llegar a designar otra aeronave con el pasar del tiempo. Cuando
    hay más de una dirección no se elige al azar: se toma la del registro más
    nuevo y se nombran las demás, para que el operador pueda corregir.

    Sin sesión no hay archivo que consultar, y una búsqueda debe responder lo mismo
    con base de datos que sin ella.

    **Por qué devuelve ``None`` y no una lista vacía.** Una lista vacía dice «lo
    miré y no estaba»; ``None`` dice «no pude mirarlo». La primera versión de este
    mensaje no distinguía los dos casos y afirmaba ante el operador que no había
    ningún vuelo con ese nombre en el archivo, sin haberlo podido abrir. Es la
    clase de afirmación que un sistema hace sobre sí mismo sin comprobarla, y lo
    que la vuelve falsa es justo el fallo.
    """
    if db is None:
        return None
    try:
        filas = (
            db.query(
                AircraftTrack.icao24,
                AircraftTrack.callsign,
                AircraftTrack.fecha_creacion,
            )
            .filter(AircraftTrack.callsign.isnot(None))
            .filter(func.upper(AircraftTrack.callsign) == wanted)
            .order_by(
                AircraftTrack.fecha_creacion.desc(),
                AircraftTrack.id.desc(),
            )
            .all()
        )
    except Exception:  # pragma: no cover - the search must not die on the archive
        opensky_log.warning("callsign_archive_lookup_failed", extra={"callsign": wanted})
        return None

    # La consulta ya viene ordenada de más reciente a más antigua, y un dict de
    # Python conserva el orden de inserción: la primera dirección que aparece es
    # la del registro más nuevo, sin tener que volver a ordenar.
    vistas: dict[str, dict[str, Any]] = {}
    for icao24, callsign, fecha in filas:
        codigo = str(icao24 or "").strip().lower()
        # Una dirección guardada que no sea válida no se propone: se respondería
        # con un 400 sobre un valor que el archivo mismo no puede sostener.
        if not _valid_icao24(codigo):
            continue
        entrada = vistas.get(codigo)
        if entrada is None:
            vistas[codigo] = {
                "icao24": codigo,
                "callsign": str(callsign or wanted).strip().upper(),
                "vuelos": 1,
                "ultima": fecha,
            }
        else:
            entrada["vuelos"] += 1
            if fecha and (entrada["ultima"] is None or fecha > entrada["ultima"]):
                entrada["ultima"] = fecha
    return list(vistas.values())


def _window(
    date: Optional[str], time_hint: Optional[str], window_hours: int
) -> tuple[int, int]:
    """Build the ``[begin, end]`` search window.

    Defaults to the last ``window_hours`` hours, which keeps the query
    inside the 2-day / 2-hour endpoint limits and minimises the number of
    day partitions — and therefore credits — that the request spans.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=window_hours)

    if date:
        try:
            base = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise FlightServiceError(
                f"Fecha inválida: {date}. Use el formato AAAA-MM-DD."
            )
        if time_hint:
            try:
                hh, mm = (int(x) for x in time_hint.split(":")[:2])
                base = base.replace(hour=hh, minute=mm)
            except (ValueError, TypeError):
                raise FlightServiceError(
                    f"Hora inválida: {time_hint}. Use el formato HH:MM."
                )
        start = base
        end = start + timedelta(hours=window_hours)
    else:
        end = now

    # Never query the future.
    if end > now:
        end = now
    # OpenSky rejects windows in the future or beyond its retention.
    begin_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    if end_ts <= begin_ts:
        end_ts = begin_ts + 3600
    return begin_ts, end_ts


def _normalise_flight(flight: dict) -> dict:
    """Normalise an OpenSky flight record, preserving nulls as nulls.

    Key casing
    ----------
    OpenSky's REST documentation renders the ``/flights/*`` fields in
    lower case, but the wire format is **camelCase**. Verified against a
    real response on 2026-09-25, which contained::

        firstSeen  lastSeen  estDepartureAirport  estArrivalAirport
        departureAirportCandidatesCount

    with **no** ``firstseen``, ``estdepartureairport`` or ``dep_lat``.
    Reading the documented lower-case names silently produced a flight
    record whose times and airports were all ``None``, so both spellings
    are accepted here.

    Also, ``dep_lat``/``arr_lat`` were never present in the observed
    payload; when OpenSky cannot resolve an airport it reports null and a
    candidates count of 0, which is surfaced rather than faked.
    """
    # Accept either casing for every field.
    first = _pick(flight, "firstSeen", "firstseen")
    last = _pick(flight, "lastSeen", "lastseen")
    departure = _pick(flight, "estDepartureAirport", "estdepartureairport")
    arrival = _pick(flight, "estArrivalAirport", "estarrivalairport")
    callsign_icao = _pick(flight, "callsign_icao", "callsignIcao")
    dep_lat = _pick(flight, "dep_lat", "depLat", "departure_lat")
    dep_lon = _pick(flight, "dep_lon", "depLon", "departure_lon")
    arr_lat = _pick(flight, "arr_lat", "arrLat", "arrival_lat")
    arr_lon = _pick(flight, "arr_lon", "arrLon", "arrival_lon")

    # How many candidate airports OpenSky considered. 0 means it could
    # not resolve one — normal, and worth reporting instead of hiding.
    dep_candidates = _pick(
        flight, "departureAirportCandidatesCount", "departure_airport_candidates_count"
    )
    arr_candidates = _pick(
        flight, "arrivalAirportCandidatesCount", "arrival_airport_candidates_count"
    )

    return {
        "icao24": (flight.get("icao24") or "").lower() or None,
        "callsign": (flight.get("callsign") or "").strip() or None,
        "first_seen": _utc(first),
        "last_seen": _utc(last),
        "first_seen_ts": first,
        "last_seen_ts": last,
        "departure": departure,
        "arrival": arrival,
        "departure_lat": dep_lat,
        "departure_lon": dep_lon,
        "arrival_lat": arr_lat,
        "arrival_lon": arr_lon,
        "callsign_icao": callsign_icao,
        "departure_candidates": dep_candidates,
        "arrival_candidates": arr_candidates,
        "duration_s": (
            last - first
            if isinstance(first, int) and isinstance(last, int) and last >= first
            else None
        ),
        "source": "opensky",
        "provenance": PROVENANCE_HISTORICAL,
    }


def _pick(source: dict, *names):
    """First present, non-null value among ``names``."""
    for name in names:
        if name in source and source[name] is not None:
            return source[name]
    return None


# ─── Trajectories (spec §21, §22, §56) ──────────────────────────────────────

async def build_track(
    service,
    db: Session,
    icao24: str,
    time_: Optional[int] = None,
    include_local: bool = True,
    ttl: Optional[float] = None,
) -> dict:
    """Assemble the full available trajectory for one aircraft.

    Combines, without inventing anything:
      * the OpenSky historical track for the flight at ``time_``,
      * AeroRF's own recorded positions, when a local session exists.

    The response states how many points came from each source and the mean
    temporal step, so the operator can judge the track's fidelity instead
    of assuming 1 Hz data.

    ``ttl`` shortens the OpenSky cache for this call. It is for the live poller
    only: a flight in progress has a route that changes every minute, and the
    300-second track cache served the frontend's 30-second poll the same answer
    nine times out of ten, so the drawn line stopped growing between jumps.
    """
    code = str(icao24).strip().lower()
    if not _valid_icao24(code):
        raise FlightServiceError(
                _explicar_icao24_invalido(icao24),
        )

    provenance: dict[str, int] = {PROVENANCE_HISTORICAL: 0, "aerorf": 0, "live": 0}
    points: list[dict] = []
    warnings: list[str] = []

    # ── OpenSky track ───────────────────────────────────────────────────
    track: dict[str, Any] = {}
    try:
        track = await service.get_track(code, time_=time_, ttl=ttl)
    except Exception as exc:
        warnings.append(f"Track de OpenSky no disponible: {exc}")
        track = {}

    for p in (track.get("points") or []):
        if p.get("latitude") is None or p.get("longitude") is None:
            continue
        points.append(
            {
                "timestamp": p.get("timestamp"),
                "latitude": p["latitude"],
                "longitude": p["longitude"],
                "altitude": p.get("altitude"),
                "heading": p.get("heading"),
                "on_ground": p.get("on_ground"),
                "provenance": (
                    PROVENANCE_LIVE if time_ == 0 else PROVENANCE_HISTORICAL
                ),
            }
        )
        provenance[
            PROVENANCE_LIVE if time_ == 0 else PROVENANCE_HISTORICAL
        ] += 1

    # ── AeroRF's own recordings ─────────────────────────────────────────
    local_points: list[dict] = []
    if include_local:
        local_points = _local_positions(db, code)
        for p in local_points:
            points.append({**p, "provenance": TRACK_SOURCE_AERORF})
            provenance[TRACK_SOURCE_AERORF] += 1

    # Merge by timestamp, dropping exact duplicates that a live sample and
    # a track waypoint may share. No interpolation, ever.
    points = _merge_points(points)

    payload: dict[str, Any] = {
        "icao24": code,
        "callsign": track.get("callsign"),
        "points": points,
        "point_count": len(points),
        "provenance_counts": provenance,
        "start_time": points[0]["timestamp"] if points else None,
        "end_time": points[-1]["timestamp"] if points else None,
        "source": _merge_source(provenance),
        "warnings": warnings,
        "requested_time": time_,
    }

    # Which flight did the returned points actually belong to?
    #
    # OpenSky's `/tracks/all` answers "the flight near this instant" when given
    # one, and the *most recent* flight when not. For an aircraft that flew
    # several times that week, a request with no instant therefore returns a
    # different flight from the one asked about, and the caller has no way to
    # tell: the points are real, the provenance is right, and the route is
    # simply the wrong one.
    #
    # So the response states the window it covers and whether the requested
    # instant falls inside it. A caller comparing routes can then refuse to
    # treat a mismatched route as the one in the report.
    if points:
        first_ts, last_ts = points[0]["timestamp"], points[-1]["timestamp"]
        payload["covered_window"] = {
            "start": first_ts,
            "end": last_ts,
            "duration_s": (last_ts - first_ts) if None not in (first_ts, last_ts) else None,
        }
        if time_ is not None and time_ != 0:
            if first_ts is not None and not (first_ts - 300 <= time_ <= last_ts + 300):
                warnings.append(
                    f"OpenSky devolvió el vuelo de "
                    f"{first_ts}–{last_ts}, no el del instante solicitado "
                    f"({time_}). Es el vuelo más reciente de esta aeronave, "
                    f"no el del reporte. Elija el vuelo en la lista."
                )
                payload["matches_request"] = False
            else:
                payload["matches_request"] = True
    else:
        payload["covered_window"] = None
        if time_ is not None and time_ != 0:
            payload["matches_request"] = None

    if points:
        summary = path_summary([[p["latitude"], p["longitude"]] for p in points])
        payload["length_m"] = summary["total_length_m"]
        payload["length_km"] = summary["total_length_km"]
        payload["length_nm"] = summary["total_length_nm"]

        times = [p["timestamp"] for p in points if p.get("timestamp") is not None]
        if len(times) >= 2:
            span = max(times) - min(times)
            steps = [b - a for a, b in zip(sorted(times), sorted(times)[1:])]
            mean = sum(steps) / len(steps)
            payload["span_s"] = span
            payload["mean_step_s"] = mean
            payload["resolution_note"] = (
                f"{len(points)} puntos en {_hms(span)} "
                f"(paso medio {_hms(mean)}). "
                "Los waypoints históricos de OpenSky no son un punto por segundo."
            )
    else:
        payload["resolution_note"] = (
            "Sin posiciones disponibles. Si el vuelo fue visto en directo por "
            "AeroRF, active «Grabar vuelo» para conservar la trayectoria propia."
        )

    # Persist for later replay and export.
    if points:
        try:
            _store_track(db, code, track.get("callsign"), points, payload)
        except Exception as exc:  # persistence failure must not break the read
            warnings.append(f"No se pudo guardar el track localmente: {exc}")

    return payload


def _merge_points(points: list[dict]) -> list[dict]:
    """Order by time and drop duplicates on (timestamp, lat, lon)."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for p in points:
        key = (p.get("timestamp"), p.get("latitude"), p.get("longitude"))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    # Points without a timestamp sort last, preserving input order.
    out.sort(key=lambda p: (p.get("timestamp") is None, p.get("timestamp") or 0))
    return out


def _merge_source(provenance: dict[str, int]) -> str:
    used = [k for k, v in provenance.items() if v > 0]
    if len(used) > 1:
        return TRACK_SOURCE_MERGED
    if used:
        return TRACK_SOURCE_OPENSKY if provenance[PROVENANCE_HISTORICAL] else used[0]
    return TRACK_SOURCE_OPENSKY


def _local_positions(db: Session, icao24: str, limit: int = 5000) -> list[dict]:
    rows = (
        db.query(AircraftPosition)
        .filter(AircraftPosition.icao24 == icao24)
        .order_by(AircraftPosition.received_at)
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        if r.latitude is None or r.longitude is None:
            continue
        out.append(
            {
                "timestamp": r.timestamp
                or int(r.received_at.replace(tzinfo=timezone.utc).timestamp()),
                "latitude": r.latitude,
                "longitude": r.longitude,
                "altitude": r.altitude,
                "heading": r.heading,
                "velocity": r.velocity,
                "on_ground": r.on_ground,
                "session_id": r.session_id,
            }
        )
    return out


def _store_track(
    db: Session,
    icao24: str,
    callsign: Optional[str],
    points: list[dict],
    payload: dict,
    session_id: Optional[int] = None,
    flight_id: Optional[int] = None,
) -> AircraftTrack:
    """Persist a trajectory as an ``aircraft_tracks`` row.

    ``session_id`` links a track produced by a recording session back to
    that session, which is what lets the replay view find it.

    Returns the row that now holds this trajectory, which is not always a row
    this call inserted. Asking twice for the same flight used to insert a
    second identical row every time, and the operator then saw every recorded
    flight two or three times in the list. Measured in the database before this
    change: 34 rows holding 8 groups of exact duplicates.

    A match is the same aerodrome, the same flight over it, and the same number
    of points. Two things are deliberately *not* treated as repeats:

    - A sparser trajectory over the same window. That is different data, not a
      repeat, and it is how a partial live recording stays visible next to the
      full one instead of being hidden by it.
    - Another flight of the same aerodrome. ``callsign`` and ``flight_id`` are
      part of the key because two flights of one aircraft can overlap in time,
      and collapsing them would file the second under the first's callsign —
      a confidently wrong label rather than a harmless duplicate.

    ``session_id`` is not part of the key: a recording session and a fetched
    trajectory can describe the same points, and that is the same trajectory.
    When they meet, the session is attached to the row that already exists, so
    the replay view still finds it.
    """
    from app.services.geojson_service import line_geometry

    started_at = _utc(payload.get("start_time"))
    ended_at = _utc(payload.get("end_time"))

    existing = (
        db.query(AircraftTrack)
        .filter(
            AircraftTrack.icao24 == icao24,
            AircraftTrack.flight_id == flight_id,
            AircraftTrack.callsign == callsign,
            AircraftTrack.started_at == started_at,
            AircraftTrack.ended_at == ended_at,
            AircraftTrack.point_count == len(points),
        )
        .order_by(AircraftTrack.id)
        .first()
    )
    if existing is not None:
        if session_id is not None and existing.session_id is None:
            existing.session_id = session_id
            db.commit()
            db.refresh(existing)
        return existing

    track = AircraftTrack(
        icao24=icao24,
        callsign=callsign,
        session_id=session_id,
        flight_id=flight_id,
        source=payload.get("source", TRACK_SOURCE_OPENSKY),
        started_at=started_at,
        ended_at=ended_at,
        point_count=len(points),
        observed_seconds=payload.get("span_s"),
        geometry=line_geometry([[p["latitude"], p["longitude"]] for p in points]),
        meta={
            "provenance_counts": payload.get("provenance_counts"),
            "mean_step_s": payload.get("mean_step_s"),
            "resolution_note": payload.get("resolution_note"),
        },
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    return track


def _hms(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {(seconds % 3600) // 60} min"


# ─── Live state (spec §23) ───────────────────────────────────────────────────

async def get_live(
    service,
    icao24: Optional[list[str]] = None,
) -> dict:
    """Current state vectors for the tracked aircraft, or for a box."""
    data = await service.get_states(icao24=icao24 or None)
    states = data.get("states") or []
    return {
        "time": data.get("time"),
        "time_utc": _utc(data.get("time")),
        "count": len(states),
        "states": states,
        "from_cache": data.get("from_cache"),
        "provenance": PROVENANCE_LIVE,
        "source": "opensky",
    }


# ─── Recording sessions (spec §24, §26) ─────────────────────────────────────

def create_session(
    db: Session,
    icao24: str,
    callsign: Optional[str] = None,
    interval_s: float = 10.0,
    description: Optional[str] = None,
    user: Optional[str] = None,
) -> FlightSession:
    """Open a recording session (spec §24)."""
    code = str(icao24).strip().lower()
    if not _valid_icao24(code):
        raise FlightServiceError(
                _explicar_icao24_invalido(icao24),
        )

    existing = (
        db.query(FlightSession)
        .filter(FlightSession.icao24 == code, FlightSession.status == SESSION_RECORDING)
        .first()
    )
    if existing:
        raise FlightServiceError(
            f"A recording session for {code} is already running (id={existing.id})."
        )

    session = FlightSession(
        icao24=code,
        callsign=callsign,
        status=SESSION_RECORDING,
        source=TRACK_SOURCE_OPENSKY,
        interval_s=interval_s,
        description=description,
        user=user,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    flight_log.info(
        "session.started", "recording session started",
        session_id=session.id, icao24=code, callsign=callsign, user=user,
    )
    return session


def record_sample(
    db: Session,
    session_id: int,
    state: dict,
) -> Optional[AircraftPosition]:
    """Append one observed position to a session.

    A state vector with no position is still recorded (it proves the
    aircraft was tracked) but carries ``latitude = None``, which the UI
    shows as "dato no disponible" rather than skipping silently.
    """
    session = db.query(FlightSession).filter(FlightSession.id == session_id).first()
    if session is None:
        raise FlightServiceError(f"Session {session_id} not found")
    if session.status != SESSION_RECORDING:
        return None

    position = AircraftPosition(
        session_id=session.id,
        timestamp=state.get("time_position"),
        latitude=state.get("latitude"),
        longitude=state.get("longitude"),
        altitude=state.get("altitude"),
        heading=state.get("heading"),
        velocity=state.get("velocity"),
        vertical_rate=state.get("vertical_rate"),
        on_ground=state.get("on_ground"),
        callsign=state.get("callsign") or session.callsign,
        icao24=state.get("icao24") or session.icao24,
        source=TRACK_SOURCE_OPENSKY,
    )
    db.add(position)
    session.sample_count = (session.sample_count or 0) + 1
    if state.get("callsign"):
        session.callsign = state["callsign"]
    db.commit()
    db.refresh(position)
    return position


def stop_session(db: Session, session_id: int, notes: Optional[str] = None) -> FlightSession:
    """Close a session and materialise its track."""
    session = db.query(FlightSession).filter(FlightSession.id == session_id).first()
    if session is None:
        raise FlightServiceError(f"Session {session_id} not found")
    if session.status != SESSION_RECORDING:
        raise FlightServiceError(
            f"Session {session_id} is already {session.status}."
        )

    session.status = SESSION_STOPPED
    session.ended_at = utcnow()
    if notes:
        session.notes = notes
    db.commit()

    positions = (
        db.query(AircraftPosition)
        .filter(AircraftPosition.session_id == session_id)
        .order_by(AircraftPosition.received_at)
        .all()
    )
    usable = [p for p in positions if p.latitude is not None]
    if usable:
        points = [
            {
                "timestamp": p.timestamp
                or int(p.received_at.replace(tzinfo=timezone.utc).timestamp()),
                "latitude": p.latitude,
                "longitude": p.longitude,
                "altitude": p.altitude,
                "heading": p.heading,
                "on_ground": p.on_ground,
            }
            for p in usable
        ]
        times = [p["timestamp"] for p in points]
        try:
            _store_track(
                db, session.icao24, session.callsign, points,
                {
                    "source": TRACK_SOURCE_AERORF,
                    "start_time": min(times), "end_time": max(times),
                    "span_s": max(times) - min(times),
                    "provenance_counts": {"aerorf": len(points)},
                },
                session_id=session.id,
            )
        except Exception as exc:
            # Track materialisation must not lose the session itself.
            flight_log.error(
                "session.track_failed", "could not build session track",
                session_id=session_id, error=str(exc),
            )

    db.refresh(session)
    flight_log.info(
        "session.stopped", "recording session stopped",
        session_id=session_id, icao24=session.icao24,
        samples=session.sample_count, with_positions=len(usable),
    )
    return session


def get_session_detail(db: Session, session_id: int) -> dict:
    """A session with its positions, ready for the replay timeline."""
    session = db.query(FlightSession).filter(FlightSession.id == session_id).first()
    if session is None:
        raise FlightServiceError(f"Session {session_id} not found")

    positions = (
        db.query(AircraftPosition)
        .filter(AircraftPosition.session_id == session_id)
        .order_by(AircraftPosition.received_at)
        .all()
    )
    # Tracks materialised when the session was stopped.
    from app.models.flight import AircraftTrack

    tracks = (
        db.query(AircraftTrack)
        .filter(AircraftTrack.session_id == session_id)
        .order_by(AircraftTrack.id)
        .all()
    )

    return {
        "session": {
            "id": session.id,
            "icao24": session.icao24,
            "callsign": session.callsign,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "status": session.status,
            "source": session.source,
            "interval_s": session.interval_s,
            "sample_count": session.sample_count,
            "description": session.description,
            "user": session.user,
            "notes": session.notes,
            "error": session.error,
        },
        "tracks": [
            {
                "id": t.id,
                "source": t.source,
                "point_count": t.point_count,
                "started_at": t.started_at,
                "ended_at": t.ended_at,
                "observed_seconds": t.observed_seconds,
                "geometry": t.geometry,
                "meta": t.meta,
            }
            for t in tracks
        ],
        "positions": [
            {
                "id": p.id,
                "timestamp": p.timestamp,
                "received_at": p.received_at,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "altitude": p.altitude,
                "heading": p.heading,
                "velocity": p.velocity,
                "on_ground": p.on_ground,
                "callsign": p.callsign,
                "icao24": p.icao24,
                "provenance": TRACK_SOURCE_AERORF,
            }
            for p in positions
        ],
    }


# ─── Watchlist (spec §25, §26) ───────────────────────────────────────────────

def list_selections(db: Session) -> list[dict]:
    rows = (
        db.query(FlightSelection).order_by(FlightSelection.slot).all()
    )
    return [
        {
            "icao24": r.icao24,
            "callsign": r.callsign,
            "slot": r.slot,
            "color": r.color or SLOT_COLORS[r.slot % len(SLOT_COLORS)],
            "show_track": r.show_track,
            "show_marker": r.show_marker,
            "selected": r.selected,
            "last_seen": r.last_seen,
            "last_position": r.last_position,
            "added_at": r.added_at,
        }
        for r in rows
    ]


def add_selection(
    db: Session,
    icao24: str,
    callsign: Optional[str] = None,
    user: Optional[str] = None,
) -> FlightSelection:
    """Add an aircraft to the watchlist, enforcing the 5-aircraft cap."""
    code = str(icao24).strip().lower()
    if not _valid_icao24(code):
        raise FlightServiceError(
                _explicar_icao24_invalido(icao24),
        )

    if db.query(FlightSelection).filter(FlightSelection.icao24 == code).first():
        raise FlightServiceError(f"Aircraft {code} is already being tracked.")

    taken = {r.slot for r in db.query(FlightSelection).all()}
    free = [s for s in range(MAX_TRACKED) if s not in taken]
    if not free:
        raise FlightServiceError(
            f"El límite es {MAX_TRACKED} aeronaves simultáneas. "
            f"Quitar una del seguimiento para agregar otra."
        )

    slot = free[0]
    row = FlightSelection(
        icao24=code,
        callsign=callsign,
        slot=slot,
        color=SLOT_COLORS[slot],
        user=user,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    flight_log.info(
        "selection.added", "aircraft tracked",
        icao24=code, callsign=callsign, slot=slot, user=user,
    )
    return row


def remove_selection(db: Session, icao24: str) -> None:
    code = str(icao24).strip().lower()
    row = db.query(FlightSelection).filter(FlightSelection.icao24 == code).first()
    if row is None:
        return
    db.delete(row)
    db.commit()
    flight_log.info("selection.removed", "aircraft untracked", icao24=code)


def update_selection(db: Session, icao24: str, patch: dict) -> FlightSelection:
    code = str(icao24).strip().lower()
    row = db.query(FlightSelection).filter(FlightSelection.icao24 == code).first()
    if row is None:
        raise FlightServiceError(f"Aircraft {code} is not being tracked.")
    allowed = {"callsign", "show_track", "show_marker", "selected", "color",
               "last_seen", "last_position"}
    for field, value in patch.items():
        if field in allowed:
            setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


def tracked_icao24s(db: Session) -> list[str]:
    return [r.icao24 for r in db.query(FlightSelection).order_by(FlightSelection.slot).all()]


# ─── Correlation (spec §35) ──────────────────────────────────────────────────

def correlate_event(
    db: Session,
    event_object_id: int,
    radii_nm: Iterable[float] = (5, 10, 20, 50),
    live_states: Optional[list[dict]] = None,
) -> dict:
    """Aircraft near an RF event, by distance band.

    This reports **spatial and temporal proximity only**. It never
    asserts that an aircraft caused an event: causation cannot be
    established from ADS-B position data plus an RF measurement, and the
    response says so explicitly.
    """
    obj = db.query(MapObject).filter(MapObject.id == event_object_id).first()
    if obj is None or obj.latitude is None or obj.longitude is None:
        raise FlightServiceError(
            f"Object {event_object_id} has no position, so it cannot be correlated."
        )

    bands: list[dict] = []
    for radius_nm in sorted(radii_nm):
        radius_m = to_metres(radius_nm, "nm")
        matches = []
        for state in live_states or []:
            lat, lon = state.get("latitude"), state.get("longitude")
            if lat is None or lon is None:
                continue
            distance = haversine_m(obj.latitude, obj.longitude, lat, lon)
            if distance <= radius_m:
                matches.append(
                    {
                        "icao24": state.get("icao24"),
                        "callsign": state.get("callsign"),
                        "distance_m": distance,
                        "distance_km": distance / 1000.0,
                        "distance_nm": distance / 1852.0,
                        "altitude": state.get("altitude"),
                        "velocity": state.get("velocity"),
                        "heading": state.get("heading"),
                        "timestamp": state.get("time_position"),
                        "timestamp_utc": _utc(state.get("time_position")),
                    }
                )
        matches.sort(key=lambda m: m["distance_m"])
        bands.append({"radius_nm": radius_nm, "count": len(matches), "aircraft": matches})

    nearest = None
    for band in bands:
        if band["count"]:
            nearest = band["aircraft"][0]
            break

    return {
        "object_id": event_object_id,
        "object_type": obj.type,
        "center": {"latitude": obj.latitude, "longitude": obj.longitude},
        "bands": bands,
        "nearest": nearest,
        "disclaimer": (
            "Correlación espacial y temporal únicamente. La cercanía entre una "
            "aeronave y un evento RF NO implica causalidad: ADS-B no registra "
            "emisiones y la posición del avión no identifica la fuente de un evento."
        ),
        "provenance": "calculated",
    }
