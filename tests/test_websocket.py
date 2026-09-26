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
        """
        # The watchlist is empty for this test run: the walkthrough cleans
        # up after itself and no other suite populates it.
        import json as _json
        import urllib.request

        with urllib.request.urlopen(
            _BASE + "/flights/tracked", timeout=15
        ) as r:
            watchlist = _json.loads(r.read().decode())
        assert watchlist["count"] == 0, (
            "this test needs an empty watchlist; "
            f"found {watchlist['count']} entries"
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
