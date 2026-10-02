"""Why this exists
------------------
The frontend's ``loadTrack`` never reached the trajectory endpoint. The API
client defined the key ``track`` twice in one object literal: once for
``GET /flights/{icao24}/track`` and again for ``POST /flights/tracked``, which
adds an aircraft to the watchlist. In a JavaScript object literal the second
definition silently replaces the first.

So asking AeroRF for a flight's route added the aircraft to the watchlist and
returned a watchlist row -- no points, no path -- and the panel said
"Trayectoria: no cargada" while the backend had the whole route ready to
return. The bug was in JavaScript, so no Python test could have found it. But
the contract it broke is a backend contract, and that is what belongs here:
these tests pin the wire format the corrected client depends on.

The stub is a real ``OpenSkyService`` behind ``httpx.MockTransport``, the same
way the other OpenSky tests do it, so the parsing path runs for real. No
credits are spent.
"""

from __future__ import annotations

import httpx
import pytest

ICAO = "e06491"
WAYPOINTS = 40


def _waypoints(icao24: str, n: int = WAYPOINTS) -> dict:
    """
    A `/tracks/all` body with `n` sparse waypoints, as OpenSky sends them.

    The timestamps are deliberately not round multiples of the recorded
    samples below: a waypoint and a recording that share an instant are
    merged, and this file has to be able to tell "merged" apart from "lost".
    """
    return {
        "icao24": icao24,
        "startTime": 1790687775,
        "endTime": 1790687775 + (n - 1) * 60,
        "callsign": "ARG1775",
        "path": [
            [
                1790687775 + i * 60,
                -26.0 - i * 0.05,
                -54.6 - i * 0.05,
                3900.0,
                90.0,
                False,
            ]
            for i in range(n)
        ],
    }


@pytest.fixture
def client(make_service, monkeypatch):
    """
    A TestClient whose OpenSky is stubbed.

    The stub is the real service over a mock transport, so token renewal,
    parsing and caching all run for real.
    """
    from fastapi.testclient import TestClient

    from app.api.routes import flights as flights_routes
    from app.main import app

    service, calls = make_service(
        lambda request: (200, _waypoints(ICAO)),
        token_response=httpx.Response(
            200, json={"access_token": "test-token", "expires_in": 1800}
        ),
    )
    monkeypatch.setattr(flights_routes, "get_opensky_service", lambda: service)
    service.calls = calls

    with TestClient(app) as c:
        yield c


class _EmptyService:
    """An OpenSky stand-in with no history for the requested aircraft."""

    configured = True

    def __init__(self):
        self.calls: list = []

    async def get_track(self, icao24, time_=None, ttl=None):
        self.calls.append((icao24, time_))
        return {"icao24": icao24, "callsign": None, "points": []}

    async def get_live_track(self, icao24):
        self.calls.append((icao24, 0))
        return {"icao24": icao24, "callsign": None, "points": []}


def test_the_two_endpoints_are_separate_resources(client):
    """
    The regression, in one test.

    The client used to send ``POST /flights/tracked`` when the operator asked
    for a trajectory, because one key stood for both. The endpoints are still
    distinct, and the frontend's rename can only be correct while they are.
    """
    assert client.get(f"/api/v1/flights/{ICAO}/track").status_code == 200
    assert client.get(f"/api/v1/flights/{ICAO}/live-track").status_code == 200

    # The watchlist is its own resource with its own verb.
    created = client.post(
        "/api/v1/flights/tracked", params={"icao24": ICAO, "callsign": "ARG1775"}
    )
    assert created.status_code == 201


def test_a_trajectory_response_carries_what_the_panel_renders(client):
    """
    The panel reads ``point_count``, ``source`` and ``provenance_counts`` off
    this response, and the map reads ``points`` with ``latitude``/``longitude``.
    It was storing a watchlist row in that slot instead, so every one of those
    reads was undefined.
    """
    body = client.get(f"/api/v1/flights/{ICAO}/track").json()

    assert body["icao24"] == ICAO
    assert body["point_count"] == WAYPOINTS
    assert body["source"] == "opensky"
    assert body["provenance_counts"]["historical"] == WAYPOINTS
    assert len(body["points"]) == WAYPOINTS

    first = body["points"][0]
    assert first["latitude"] is not None and first["longitude"] is not None
    assert first["provenance"] == "historical"

    # The frontend normalises this key to lower case to find its cache. The
    # backend has to agree, or the panel misses a trajectory it has in hand.
    assert body["icao24"] == body["icao24"].lower()

    # And the route is measured, because comparing routes is the point.
    assert body["length_km"] > 0
    assert body["mean_step_s"] and body["mean_step_s"] > 0


def test_time_zero_asks_for_the_flight_in_progress(client):
    """
    ``time=0`` is a real request, not "absent".

    The store used a truthiness check and dropped it, so the request went out
    with no time at all. The backend reads the difference: ``0`` labels the
    points as live rather than historical.
    """
    body = client.get(f"/api/v1/flights/{ICAO}/track", params={"time": 0}).json()

    assert body["provenance_counts"]["live"] == WAYPOINTS, "time=0 debe llegar al servicio"
    assert body["points"][0]["provenance"] == "live"


def test_a_finished_recording_is_part_of_the_trajectory(client, db):
    """
    Record a flight, then ask for its trajectory: the recorded samples must be
    in the answer, marked as AeroRF's own rather than OpenSky's.

    This is the operator's flow. Without the recorded points a finished
    recording looked like it had produced nothing, which is what was reported.
    """
    created = client.post(
        "/api/v1/flights/sessions",
        json={"icao24": ICAO, "callsign": "ARG1775", "interval_s": 10},
    )
    assert created.status_code == 201
    session_id = created.json()["id"]
    assert client.post(f"/api/v1/flights/sessions/{session_id}/start").status_code in (200, 201)

    from datetime import datetime, timezone

    from app.models.flight import AircraftPosition, AircraftTrack

    track = AircraftTrack(
        icao24=ICAO, callsign="ARG1775", session_id=session_id,
        source="aerorf", point_count=2,
    )
    db.add(track)
    db.flush()
    for i in range(2):
        db.add(
            AircraftPosition(
                icao24=ICAO,
                session_id=session_id,
                track_id=track.id,
                # Offset by 20 s from the waypoint grid on purpose: a merge
                # that drops near-misses would show up here as a lost sample.
                timestamp=1790687775 + i * 60 + 20,
                received_at=datetime(2026, 9, 29, 14, 38, 54 + i, tzinfo=timezone.utc),
                latitude=-26.0 + i * 0.01,
                longitude=-54.6,
                altitude=3900.0,
            )
        )
    db.commit()

    body = client.get(f"/api/v1/flights/{ICAO}/track").json()

    # Both recorded samples are in the answer, and both are labelled as ours.
    own = [p for p in body["points"] if p["provenance"] == "aerorf"]
    assert len(own) == 2, "las dos muestras grabadas deben estar en la trayectoria"
    assert all(p["session_id"] == session_id for p in own)

    assert body["point_count"] == len(body["points"])
    assert body["point_count"] == WAYPOINTS + 2
    assert body["source"] == "merged"

    # No instant is drawn twice, and none is invented.
    timestamps = [p["timestamp"] for p in body["points"]]
    assert len(timestamps) == len(set(timestamps))
    assert body["start_time"] == min(timestamps)
    assert body["end_time"] == max(timestamps)


def test_a_recording_never_overwrites_the_opensky_route(client, db):
    """
    The recorded points and OpenSky's waypoints are both kept.

    They are different observations of the same flight, so the answer holds
    both and the map draws AeroRF's as a dashed line over OpenSky's solid one.
    Collapsing them into one would erase the operator's own measurements.
    """
    from datetime import datetime, timezone

    from app.models.flight import AircraftPosition, AircraftTrack

    track = AircraftTrack(icao24=ICAO, source="aerorf", point_count=1, session_id=None)
    db.add(track)
    db.flush()
    db.add(
        AircraftPosition(
            icao24=ICAO, track_id=track.id,
            timestamp=1790687775 + 30,
            received_at=datetime(2026, 9, 29, 14, 38, 54, tzinfo=timezone.utc),
            latitude=-26.02, longitude=-54.62, altitude=3900.0,
        )
    )
    db.commit()

    body = client.get(f"/api/v1/flights/{ICAO}/track").json()

    historical = [p for p in body["points"] if p["provenance"] == "historical"]
    ours = [p for p in body["points"] if p["provenance"] == "aerorf"]
    assert len(historical) == WAYPOINTS, "la ruta de OpenSky no debe reducirse"
    assert len(ours) == 1
    assert body["source"] == "merged"


def test_an_unknown_aircraft_is_an_empty_track_not_an_error(client, monkeypatch):
    """
    A flight with no history and no recording is empty, not broken.

    The panel has to be able to say "no points", so the response is a
    well-formed empty track rather than a 404 or a 500.
    """
    from app.api.routes import flights as flights_routes

    monkeypatch.setattr(flights_routes, "get_opensky_service", lambda: _EmptyService())

    response = client.get("/api/v1/flights/abcdef/track")

    assert response.status_code == 200
    body = response.json()
    assert body["point_count"] == 0
    assert body["points"] == []
    assert body["start_time"] is None
    assert body["end_time"] is None
    # No length is claimed, because there is nothing to measure.
    assert "length_km" not in body


def test_a_malformed_code_never_reaches_opensky(client, monkeypatch):
    """
    The client is not the only thing that can get a code wrong, and a bad one
    must not be sent to a metered API.
    """
    from app.api.routes import flights as flights_routes

    empty = _EmptyService()
    monkeypatch.setattr(flights_routes, "get_opensky_service", lambda: empty)

    response = client.get("/api/v1/flights/NOT-HEX/track")

    assert response.status_code in (400, 422)
    assert empty.calls == [], "no debe consultarse OpenSky con un codigo invalido"
