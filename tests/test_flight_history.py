"""The flight list an interference report is worked from.

Why this exists
---------------
An operator receives a report naming a flight that has already landed,
sometimes days earlier, and needs the route it flew. Asking for "the track"
of an aircraft with no instant returns whichever flight that aircraft flew
most recently, which is frequently a different one. Verified against the live
API: one aircraft, asked for its track without an instant, returned 120 points
covering 09-29 13:14-15:43, while the flight in the report (AAL3139, 09-28
10:10) had 308 points and 812 km.

The points in both answers are real and correctly labelled. Nothing looks
wrong. It is simply the wrong flight, and it cannot be detected downstream.

So the candidate flights are the data, and the trajectory is fetched for
whichever one is chosen. These tests pin that behaviour and the honesty of the
mismatch report.
"""

from __future__ import annotations

import httpx
import pytest

ICAO = "a101c3"
NOW = 1_790_696_090  # 2026-09-29, fixed so the windows are reproducible


def _flight(first: int, last: int, callsign: str, dep: str | None, arr: str | None):
    """One row shaped like OpenSky's, camelCase as it really sends it."""
    return {
        "icao24": ICAO,
        "callsign": callsign,
        "firstSeen": first,
        "lastSeen": last,
        "estDepartureAirport": dep,
        "estArrivalAirport": arr,
        "departureAirportCandidatesCount": 2 if dep else None,
        "arrivalAirportCandidatesCount": 2 if arr else None,
        "estDepartureAirportHorizDistance": 1200.0,
        "estArrivalAirportHorizDistance": 800.0,
    }


#: Two flights a day apart, and one from a week earlier.
FLIGHTS = [
    _flight(NOW - 3_600, NOW - 900, "AAL1107 ", "KBOI", ""),
    _flight(NOW - 86_400, NOW - 86_400 + 4_000, "AAL3139 ", "KPHL", "KCLT"),
    _flight(NOW - 7 * 86_400, NOW - 7 * 86_400 + 5_000, "AAL532  ", "KORD", "KPHL"),
]


@pytest.fixture
def windows(monkeypatch):
    """
    Records every window the endpoint asks OpenSky for, and answers from
    FLIGHTS only for the window that contains the flight.

    This is the point of the test: a request must not reach outside the range
    it declares, and the split must cover the whole declared range.
    """
    from app.api.routes import flights as flights_routes

    seen: list[tuple[int, int]] = []

    class _Service:
        configured = True

        async def get_flights_by_aircraft(self, icao24, begin, end):
            seen.append((int(begin), int(end)))
            # Return flights whose window overlaps, which is what a real
            # windowed query does.
            return [f for f in FLIGHTS
                    if f["firstSeen"] >= begin - 86_400 and f["lastSeen"] <= end + 86_400]

        async def get_track(self, icao24, time_=None):
            chosen = None
            if time_ is not None:
                for f in FLIGHTS:
                    if f["firstSeen"] == int(time_):
                        chosen = f
                        break
            chosen = chosen or FLIGHTS[0]
            return {
                "icao24": icao24,
                "callsign": chosen["callsign"],
                "points": [
                    {"timestamp": chosen["firstSeen"] + i * 60,
                     "latitude": -26.0 - i * 0.05, "longitude": -54.6,
                     "altitude": 3900.0, "heading": 90.0, "on_ground": False}
                    for i in range(20)
                ],
            }

    monkeypatch.setattr(flights_routes, "get_opensky_service", lambda: _Service())
    return seen


@pytest.fixture
def client(windows):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_the_list_carries_what_identifies_a_flight(client):
    """
    An operator recognises a flight by when it flew and where it went, not by
    OpenSky's distance-to-candidate fields.
    """
    body = client.get(f"/api/v1/flights/{ICAO}/flights", params={"days": 2}).json()

    assert body["icao24"] == ICAO
    assert body["count"] == len(body["flights"])
    assert body["history_limit_days"] == 30

    first = body["flights"][0]
    for key in ("callsign", "start_time", "end_time", "duration_s",
                "departure_airport", "arrival_airport", "track_time"):
        assert key in first, f"falta {key}"
    # The instant to request the trajectory for is inside the flight.
    assert first["track_time"] == first["start_time"]
    assert first["start_time"] <= first["track_time"] <= first["end_time"]
    assert first["duration_s"] == first["end_time"] - first["start_time"]


def test_the_list_is_newest_first(client):
    """
    Reports are worked from the most recent event, and the newest flight is
    the one an operator reaches for first.
    """
    flights = client.get(f"/api/v1/flights/{ICAO}/flights", params={"days": 8}).json()["flights"]
    starts = [f["start_time"] for f in flights]
    assert starts == sorted(starts, reverse=True)


def test_a_wider_search_actually_looks_further_back(client, windows):
    """
    The bug this catches: `days=8` reported eight windows queried and returned
    the same eight flights that `days=2` returned, because the range was
    hard-coded to two days regardless of the parameter. The number of windows
    said one thing and the flights said another.
    """
    two = client.get(f"/api/v1/flights/{ICAO}/flights", params={"days": 2}).json()
    windows.clear()
    eight = client.get(f"/api/v1/flights/{ICAO}/flights", params={"days": 8}).json()

    assert len(eight["windows_queried"]) > len(two["windows_queried"])
    # The older flight is now reachable, and was not in the two-day list.
    assert all(f["start_time"] > NOW - 2 * 86_400 for f in two["flights"])
    assert any(f["start_time"] <= NOW - 7 * 86_400 for f in eight["flights"])


def test_every_window_is_inside_the_declared_range(client, windows):
    """
    No request may reach outside the range the caller asked for, and the
    windows must cover it with no gaps: a gap is a flight nobody ever saw.
    """
    body = client.get(
        f"/api/v1/flights/{ICAO}/flights",
        params={"begin": NOW - 4 * 86_400, "end": NOW},
    ).json()

    assert body["begin"] == NOW - 4 * 86_400
    assert body["end"] == NOW
    for w in body["windows_queried"]:
        assert w["begin"] >= body["begin"], "una ventana empieza antes de lo pedido"
        assert w["end"] <= body["end"], "una ventana termina despues de lo pedido"

    ordered = sorted((w["begin"], w["end"]) for w in body["windows_queried"])
    assert ordered[0][0] == body["begin"], "la primera ventana no empieza en `begin`"
    assert ordered[-1][1] == body["end"], "la ultima ventana no termina en `end`"
    for (_, prev_end), (next_begin, _) in zip(ordered, ordered[1:]):
        assert next_begin == prev_end, "hay un hueco entre ventanas"


def test_a_search_wider_than_the_budget_says_it_was_cut(client):
    """
    More than 30 windows cannot be requested. A short list is then ambiguous —
    the aircraft may simply not have flown, or the search may have stopped —
    and the two must not look the same.
    """
    body = client.get(
        f"/api/v1/flights/{ICAO}/flights",
        params={"begin": NOW - 60 * 86_400, "end": NOW},
    ).json()

    assert len(body["windows_queried"]) == 30
    assert body["search_truncated"] is True
    # What was actually covered is stated, and it is the recent end.
    assert body["searched_from"] > NOW - 31 * 86_400
    assert body["end"] == NOW

    narrow = client.get(
        f"/api/v1/flights/{ICAO}/flights",
        params={"begin": NOW - 2 * 86_400, "end": NOW},
    ).json()
    assert narrow["search_truncated"] is False


def test_the_cost_of_the_search_is_stated(client):
    """
    Each window spends OpenSky credits. A 30-day search is 30 of them, so the
    figure has to be visible before the search is run, not discovered on the
    bill.
    """
    narrow = client.get(f"/api/v1/flights/{ICAO}/flights", params={"days": 2}).json()
    wide = client.get(f"/api/v1/flights/{ICAO}/flights", params={"days": 10}).json()

    assert narrow["estimated_credits"] > 0
    assert wide["estimated_credits"] > narrow["estimated_credits"], (
        "buscar mas lejos debe costar mas"
    )


def test_a_malformed_code_is_rejected(client, windows):
    """A bad code must not be sent to a metered endpoint."""
    assert client.get("/api/v1/flights/NOT-HEX/flights").status_code == 422
    assert windows == [], "no debe haber consultado nada"


def test_an_inverted_window_is_rejected(client):
    assert client.get(
        f"/api/v1/flights/{ICAO}/flights",
        params={"begin": NOW, "end": NOW - 86_400},
    ).status_code == 400


def test_a_future_window_is_rejected(client):
    assert client.get(
        f"/api/v1/flights/{ICAO}/flights",
        params={"begin": NOW + 10 * 86_400, "end": NOW + 11 * 86_400},
    ).status_code == 400


# ─── Does the trajectory answer belong to the flight that was asked for? ────


def test_the_track_states_which_window_it_covers(client):
    """
    Every response says the span of time its points actually belong to.

    Without this there is no way to tell a correct route from a plausible
    looking wrong one, which is the whole failure.
    """
    body = client.get(f"/api/v1/flights/{ICAO}/flights", params={"days": 8}).json()
    chosen = body["flights"][-1]  # the oldest, so a wrong answer is obvious

    track = client.get(
        f"/api/v1/flights/{ICAO}/track", params={"time": chosen["track_time"]}
    ).json()

    window = track["covered_window"]
    assert window is not None
    assert window["start"] == chosen["start_time"]
    assert window["end"] <= chosen["end_time"] + 60
    assert track["matches_request"] is True
    assert not any("no el del reporte" in w for w in track["warnings"])


def test_a_mismatched_track_says_so_instead_of_looking_right(client, monkeypatch):
    """
    The case that started this: the answer is a real route for the wrong
    flight.

    The response must not present it as the requested flight. It carries a
    warning, `matches_request: false`, and the window it really covers, so the
    operator can see that the points belong to another time.
    """
    from app.api.routes import flights as flights_routes

    class _WrongFlight:
        configured = True

        async def get_flights_by_aircraft(self, icao24, begin, end):
            return FLIGHTS

        async def get_track(self, icao24, time_=None):
            # Always answers with the newest flight, whatever was asked.
            newest = FLIGHTS[0]
            return {
                "icao24": icao24,
                "callsign": newest["callsign"],
                "points": [
                    {"timestamp": newest["firstSeen"] + i * 60,
                     "latitude": -26.0, "longitude": -54.6,
                     "altitude": 3900.0, "heading": 90.0, "on_ground": False}
                    for i in range(20)
                ],
            }

    monkeypatch.setattr(flights_routes, "get_opensky_service", lambda: _WrongFlight())

    old_flight = FLIGHTS[1]
    body = client.get(
        f"/api/v1/flights/{ICAO}/track", params={"time": old_flight["firstSeen"]}
    ).json()

    assert body["point_count"] == 20, "si devuelve puntos, el fallo es otro"
    assert body["matches_request"] is False, "un vuelo ajeno no puede decir que coincide"
    assert body["covered_window"]["start"] == FLIGHTS[0]["firstSeen"]
    assert body["warnings"], "un desajuste sin aviso es indistinguible de un acierto"
    joined = " ".join(body["warnings"])
    assert "no el del reporte" in joined or "vuelo más reciente" in joined


def test_an_empty_track_declares_no_window(client, monkeypatch):
    """
    No points means there is no window to report, and no claim to make.
    """
    from app.api.routes import flights as flights_routes

    class _Nothing:
        configured = True

        async def get_flights_by_aircraft(self, icao24, begin, end):
            return FLIGHTS

        async def get_track(self, icao24, time_=None):
            return {"icao24": icao24, "callsign": None, "points": []}

    monkeypatch.setattr(flights_routes, "get_opensky_service", lambda: _Nothing())

    body = client.get(
        f"/api/v1/flights/{ICAO}/track", params={"time": FLIGHTS[1]["firstSeen"]}
    ).json()

    assert body["point_count"] == 0
    assert body["covered_window"] is None
    assert body["matches_request"] is None
