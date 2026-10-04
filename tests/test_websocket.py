"""
tests/test_websocket.py
───────────────────────
WebSocket contract (spec §48).

Verifies the connection lifecycle, client-driven subscription, and — most
importantly — that the feed does not flood: an unchanged condition must
not be re-sent on every poll.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
from urllib.parse import urlparse

import pytest
import websockets

#: These tests drive a live backend: they exercise the real ASGI server
#: rather than the application in-process. Point elsewhere with
#: ``AERORF_WS_URL`` if the backend is not on the default port.
DEFAULT_WS = "ws://127.0.0.1:8010/ws/flights"
_BASE = "http://127.0.0.1:8010/api/v1"


def _ws_url() -> str:
    return os.getenv("AERORF_WS_URL", DEFAULT_WS)


def _backend_is_up(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


#: These are integration tests. They need a live backend, and one of them
#: deliberately waits out two poll intervals to prove the feed does not
#: flood, so they are excluded from the default run:
#:
#:     pytest -m "not integration"     # fast, no backend needed
#:     pytest -m integration           # needs the backend up
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _backend_is_up(_ws_url()),
        reason=(
            "Backend not listening. Start it first:\n"
            "  python -m uvicorn app.main:app --port 8010\n"
            "or set AERORF_WS_URL to another instance."
        ),
    ),
]


def run(coro):
    return asyncio.run(coro)


#: Messages the server emits on its own schedule while a client is
#: connected. With credentials configured and aircraft on the watchlist,
#: the poll loop really does query OpenSky, so control-message
#: assertions must tolerate `states` and `lost` frames arriving between
#: them. The earlier version of this file did not, and failed whenever the
#: watchlist happened to be non-empty.


async def _recv_until(ws, wanted, timeout=12.0, skip=()):
    """Read messages until one of type ``wanted`` arrives.

    The poll loop may interleave status frames with control replies, so
    tests assert on the message they care about rather than on position.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        remaining = deadline - loop.time()
        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.5, remaining))
        payload = json.loads(raw)
        if payload.get("type") in skip:
            continue
        if payload.get("type") in wanted:
            return payload
    raise AssertionError(f"no message of type {wanted} within {timeout}s")


class TestFlightWebSocket:
    def test_handshake(self):
        async def go():
            async with websockets.connect(_ws_url(), open_timeout=10) as ws:
                return json.loads(await asyncio.wait_for(ws.recv(), timeout=10))

        hello = run(go())
        assert hello["type"] == "hello"
        # The server advertises its limits up front.
        assert hello["max_tracked"] == 5
        assert "poll_interval_s" in hello
        assert "opensky_configured" in hello

    def test_subscribe_narrows_the_feed(self):
        async def go():
            async with websockets.connect(_ws_url(), open_timeout=10) as ws:
                await _recv_until(ws, {"hello"}, skip=("status", "states", "lost"))
                await ws.send(
                    json.dumps({"action": "track", "icao24": ["abc123", "def456"]})
                )
                return await _recv_until(ws, {"subscribed"}, skip=("status", "states", "lost"))

        sub = run(go())
        assert sub["icao24"] == ["abc123", "def456"]
        assert sub["watching"] == "specific"

    def test_untrack_widens_again(self):
        async def go():
            async with websockets.connect(_ws_url(), open_timeout=10) as ws:
                await _recv_until(ws, {"hello"}, skip=("status", "states", "lost"))
                await ws.send(json.dumps({"action": "untrack"}))
                return await _recv_until(ws, {"subscribed"}, skip=("status", "states", "lost"))

        sub = run(go())
        assert sub["icao24"] == []
        assert sub["watching"] == "all"

    def test_ping_pong(self):
        async def go():
            async with websockets.connect(_ws_url(), open_timeout=10) as ws:
                await _recv_until(ws, {"hello"}, skip=("status", "states", "lost"))
                await ws.send(json.dumps({"action": "ping"}))
                return await _recv_until(ws, {"pong"}, skip=("status", "states", "lost"))

        assert run(go())["type"] == "pong"

    def test_unknown_action_reports_an_error(self):
        async def go():
            async with websockets.connect(_ws_url(), open_timeout=10) as ws:
                await _recv_until(ws, {"hello"}, skip=("status", "states", "lost"))
                await ws.send(json.dumps({"action": "nonsense"}))
                return await _recv_until(ws, {"error"}, skip=("status", "states", "lost"))

        assert "nonsense" in run(go())["message"]

    def test_feed_does_not_flood(self):
        """Spec §48: send updates only when there is something new.

        Measured over a window longer than one poll interval, the frame
        rate must stay bounded and repeated status conditions must not be
        re-sent. A parked AeroRF receiving a frame every ten seconds
        forever is exactly what the spec forbids.
        """
        poll = 10  # seconds; matches LIVE_POLL_INTERVAL_S

        async def go():
            async with websockets.connect(_ws_url(), open_timeout=10) as ws:
                received = []
                try:
                    while True:
                        raw = await asyncio.wait_for(
                            ws.recv(), timeout=poll * 2 + 2
                        )
                        received.append(json.loads(raw))
                except (asyncio.TimeoutError, websockets.ConnectionClosed):
                    pass
                return received

        messages = run(go())
        window_s = poll * 2 + 2

        # The handshake and (at most) one acknowledgement per condition.
        # Anything more than a handful of frames per poll interval means
        # the server is repeating itself.
        allowed = 6
        assert len(messages) <= allowed, (
            f"{len(messages)} frames in ~{window_s}s "
            f"(poll interval {poll}s); the feed is flooding"
        )

        # A status condition must never be repeated while it holds.
        statuses = [m for m in messages if m.get("type") == "status"]
        assert len(statuses) <= 1, (
            f"status repeated {len(statuses)} times in ~{window_s}s: "
            f"{[m.get('opensky') for m in statuses]}"
        )

    def test_idle_when_nothing_is_tracked(self):
        """With an empty watchlist the server must not query OpenSky.

        A query with no `icao24` is a *global* one, costing 4 credits.
        Polling it every 10 s with nothing tracked would burn 24 credits
        an hour for data nobody asked for.

        The premise used to be *assumed*: a comment said the watchlist was
        empty because the walkthrough cleaned after itself. The operator
        started keeping his own aircraft in there (two, since 02/10) and the
        test stopped passing its precondition on the one machine it runs on.
        A guard that never runs is no guard, and skipping here would disable
        exactly the case worth checking.

        So the premise is arranged instead: snapshot, empty through the
        public API, assert, and put everything back in `finally`. Restored
        through the same API: icao24, callsign, slot (re-added in slot
        order, so colour follows it), the three flags and last_position.
        Not restorable, because `GET /flights/tracked` does not return it
        and `update_selection` does not accept it: `added_at`. It is read
        nowhere in the codebase, and the alternative — never running —
        costs more than it saves.
        """
        import json as _json
        import urllib.request
        from urllib.parse import urlencode
        from urllib.request import Request

        def _http(path, method="GET", body=None):
            data = None
            headers = {}
            if body is not None:
                data = _json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            req = Request(
                _BASE + path, data=data, headers=headers, method=method
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                return _json.loads(r.read().decode("utf-8"))

        def _restore(rows):
            # Slot first: `add_selection` hands out the lowest free slot, so
            # re-adding in slot order puts every aircraft back where it was,
            # colour included.
            for row in sorted(rows, key=lambda r: r["slot"]):
                query = {"icao24": row["icao24"]}
                if row.get("callsign"):
                    query["callsign"] = row["callsign"]
                _http("/flights/tracked?" + urlencode(query), "POST")
                patch = {
                    "show_track": row["show_track"],
                    "show_marker": row["show_marker"],
                    "selected": row["selected"],
                }
                if row.get("last_position") is not None:
                    patch["last_position"] = row["last_position"]
                _http(
                    f"/flights/tracked/{row['icao24']}", "PATCH", patch
                )

        before = _http("/flights/tracked")["slots"]
        try:
            for row in before:
                _http(f"/flights/tracked/{row['icao24']}", "DELETE")

            restantes = _http("/flights/tracked")
            assert restantes["count"] == 0, (
                "could not empty the watchlist for this test: "
                f"{restantes['count']} entries left"
            )

            async def go():
                async with websockets.connect(_ws_url(), open_timeout=10) as ws:
                    # The idle notice should arrive on the first tick.
                    return await _recv_until(
                        ws, {"status"}, timeout=20, skip=("states", "lost")
                    )

            msg = run(go())
            assert msg.get("type") == "status"
            assert msg.get("opensky") == "idle"
            assert "créditos" in msg.get("message", "").lower()
        finally:
            _restore(before)

        # The watchlist is the operator's, not the test's: leaving it empty
        # would be worse than never running this at all.
        after = _http("/flights/tracked")["slots"]
        assert [(r["icao24"], r["slot"], r["callsign"]) for r in after] == [
            (r["icao24"], r["slot"], r["callsign"]) for r in before
        ], f"the watchlist was not restored: {after}"
