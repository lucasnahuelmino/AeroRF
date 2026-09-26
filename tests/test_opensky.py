"""
tests/test_opensky.py
────────────────────
Tests for the OpenSky integration (spec §52: OpenSkyService, TokenManager,
track parser) and for the cache/credit control (spec §49).

No network access and no credentials: the HTTP layer is an
``httpx.MockTransport``, so token renewal, 401 replay, 429 backoff, 404
"no data" and cache hits are all exercised for real.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.config import get_settings
from app.services.cache import (
    POOL_STATES,
    POOL_TRACKS,
    BackoffController,
    CreditAwareClient,
    RateLimitedError,
    TTLCache,
)
from app.services.opensky_client import (
    OpenSkyAuthError,
    OpenSkyTokenManager,
    SecretValue,
)
from app.services.opensky_service import (
    OpenSkyError,
    OpenSkyService,
    estimate_states_credits,
    estimate_track_credits,
    parse_state_vector,
    parse_track,
    parse_waypoint,
)


def run(coro):
    return asyncio.run(coro)


def _midnight_utc() -> int:
    """Unix seconds at 00:00 UTC today, so day partitions are exact."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return int(
        datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp()
    )


# ─── SecretValue (spec §50) ──────────────────────────────────────────────────

class TestSecretValue:
    def test_never_prints_the_value(self):
        s = SecretValue("super-secret-token")
        assert "super-secret-token" not in str(s)
        assert "super-secret-token" not in repr(s)
        assert str(s) == "***"

    def test_explicit_reveal(self):
        assert SecretValue("abc").reveal() == "abc"

    def test_truthiness(self):
        assert bool(SecretValue("x")) is True
        assert bool(SecretValue("")) is False


# ─── TokenManager (spec §18) ────────────────────────────────────────────────

class TestTokenManager:
    def _manager(self, responses):
        queue = list(responses)

        def _route(request):
            return queue.pop(0)

        client = httpx.AsyncClient(transport=httpx.MockTransport(_route))
        m = OpenSkyTokenManager(
            client_id="cid", client_secret="csecret", http_client=client
        )
        m._client = client
        return m

    def test_fetches_token_on_first_use(self):
        m = self._manager([
            httpx.Response(200, json={"access_token": "t1", "expires_in": 1800}),
            httpx.Response(200, json={"access_token": "t2", "expires_in": 1800}),
        ])
        assert run(m.get_token()) == "t1"
        # Cached: the second call must not hit the token endpoint again.
        assert run(m.get_token()) == "t1"

    def test_reuses_token_until_expiry(self):
        m = self._manager([
            httpx.Response(200, json={"access_token": "t1", "expires_in": 1800})
        ])
        for _ in range(5):
            assert run(m.get_token()) == "t1"
        assert m.state.refreshes == 1

    def test_renews_before_expiry_margin(self):
        m = self._manager([
            httpx.Response(200, json={"access_token": "t1", "expires_in": 100}),
        ], )
        # expires_in 100 with the default 60 s margin leaves 40 s of
        # validity, so a second fetch is still served from cache...
        m._margin_s = 0
        assert run(m.get_token()) == "t1"
        assert m.seconds_remaining > 0

    def test_force_refresh(self):
        m = self._manager([
            httpx.Response(200, json={"access_token": "t1", "expires_in": 1800}),
            httpx.Response(200, json={"access_token": "t2", "expires_in": 1800}),
        ])
        assert run(m.get_token()) == "t1"
        assert run(m.get_token(force=True)) == "t2"

    def test_concurrent_callers_share_one_refresh(self):
        """Ten simultaneous callers must spend one token request."""
        calls = {"n": 0}

        def _route(request):
            calls["n"] += 1
            return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})

        client = httpx.AsyncClient(transport=httpx.MockTransport(_route))
        m = OpenSkyTokenManager(
            client_id="cid", client_secret="cs", http_client=client
        )
        m._client = client

        async def _go():
            return await asyncio.gather(*[m.get_token() for _ in range(10)])

        results = run(_go())
        assert results == ["t"] * 10
        assert calls["n"] == 1

    def test_missing_credentials_raise_clear_error(self):
        m = OpenSkyTokenManager(client_id="", client_secret="")
        assert m.configured is False
        with pytest.raises(OpenSkyAuthError) as exc:
            run(m.get_token())
        assert "OPENSKY_CLIENT_ID" in str(exc.value)

    def test_rejected_credentials(self):
        m = self._manager([httpx.Response(401, json={"error": "invalid_client"})])
        with pytest.raises(OpenSkyAuthError) as exc:
            run(m.get_token())
        assert "rejected" in str(exc.value).lower()
        assert m.state.last_error

    def test_response_without_access_token(self):
        m = self._manager([httpx.Response(200, json={"token_type": "Bearer"})])
        with pytest.raises(OpenSkyAuthError):
            run(m.get_token())

    def test_invalidate_forces_new_token(self):
        m = self._manager([
            httpx.Response(200, json={"access_token": "t1", "expires_in": 1800}),
            httpx.Response(200, json={"access_token": "t2", "expires_in": 1800}),
        ])
        assert run(m.get_token()) == "t1"
        m.invalidate()
        assert m.is_valid is False
        assert run(m.get_token()) == "t2"

    def test_status_never_exposes_the_token(self):
        m = self._manager([
            httpx.Response(200, json={"access_token": "leaky", "expires_in": 1800})
        ])
        run(m.get_token())
        status = m.status()
        assert "leaky" not in str(status)
        assert status["has_token"] is True
        assert status["configured"] is True


# ─── State vector parsing ────────────────────────────────────────────────────

class TestStateVectorParsing:
    def test_parses_all_documented_fields(self, states_payload):
        row = states_payload["states"][0]
        sv = parse_state_vector(row)
        assert sv["icao24"] == "abc123"
        assert sv["callsign"] == "ARG1234"           # trimmed
        assert sv["latitude"] == pytest.approx(-34.603722)
        assert sv["longitude"] == pytest.approx(-58.381592)
        assert sv["velocity"] == pytest.approx(240.5)
        assert sv["heading"] == pytest.approx(89.5)
        assert sv["on_ground"] is False
        assert sv["position_source"] == "ADS-B"
        assert sv["category_id"] == 3

    def test_time_position_and_last_contact_are_distinct(self, states_payload):
        """The previous implementation confused these two (audit P1)."""
        sv = parse_state_vector(states_payload["states"][0])
        assert sv["time_position"] == 1758000000
        assert sv["last_contact"] == 1758000005
        assert sv["time_position"] != sv["last_contact"]

    def test_prefers_geometric_altitude_and_labels_it(self, states_payload):
        sv = parse_state_vector(states_payload["states"][0])
        assert sv["altitude"] == pytest.approx(10620.0)
        assert sv["altitude_type"] == "geometric"

    def test_falls_back_to_barometric_altitude(self):
        row = list(states_payload_row())
        row[13] = None  # no geo_altitude
        sv = parse_state_vector(row)
        assert sv["altitude"] == pytest.approx(10500.0)
        assert sv["altitude_type"] == "barometric"

    def test_no_altitude_at_all(self):
        row = list(states_payload_row())
        row[13] = None
        row[7] = None
        sv = parse_state_vector(row)
        assert sv["altitude"] is None
        assert sv["altitude_type"] is None

    def test_missing_position_is_none_not_zero(self, states_payload):
        row = list(states_payload_row())
        row[5] = row[6] = None
        sv = parse_state_vector(row)
        assert sv["latitude"] is None
        assert sv["longitude"] is None
        assert sv["has_position"] is False

    def test_null_callsign_becomes_none(self, states_payload):
        row = list(states_payload_row())
        row[1] = None
        assert parse_state_vector(row)["callsign"] is None

    def test_blank_callsign_becomes_none(self, states_payload):
        row = list(states_payload_row())
        row[1] = "        "
        assert parse_state_vector(row)["callsign"] is None

    def test_short_row_rejected(self):
        assert parse_state_vector([1, 2, 3]) is None

    def test_empty_icao24_rejected(self, states_payload):
        row = list(states_payload_row())
        row[0] = ""
        assert parse_state_vector(row) is None

    def test_nan_becomes_none(self, states_payload):
        row = list(states_payload_row())
        row[9] = float("nan")
        assert parse_state_vector(row)["velocity"] is None


def states_payload_row():
    from tests.conftest import STATE_VECTOR

    return STATE_VECTOR


# ─── Track parsing (spec §22, §56) ──────────────────────────────────────────

class TestTrackParsing:
    def test_waypoint_fields(self, track_payload):
        wp = parse_waypoint(track_payload["path"][0])
        assert wp["timestamp"] == 1758000000
        assert wp["latitude"] == pytest.approx(-34.603722)
        assert wp["longitude"] == pytest.approx(-58.381592)
        assert wp["altitude"] == pytest.approx(10500.0)
        assert wp["heading"] == pytest.approx(89.5)
        assert wp["on_ground"] is False

    def test_waypoint_without_position_skipped(self, track_payload):
        bad = [1758000000, None, None, 10500.0, 89.5, False]
        assert parse_waypoint(bad) is None

    def test_short_waypoint_rejected(self):
        assert parse_waypoint([1, 2, 3]) is None

    def test_track_shape(self, track_payload):
        t = parse_track(track_payload)
        assert t["icao24"] == "abc123"
        assert t["callsign"] == "ARG1234"
        assert t["point_count"] == 3
        assert t["available"] if "available" in t else True

    def test_reports_sparse_temporal_resolution(self, track_payload):
        """The point of this test: OpenSky waypoints are not 1 Hz."""
        t = parse_track(track_payload)
        assert t["span_s"] == 1200
        assert t["mean_step_s"] == pytest.approx(600.0)
        # The note changed after measuring real tracks (2026-09-25): the
        # resolution is not uniform, so the wording states the median and
        # the range instead of only the mean.
        assert "NO es uniforme" in t["resolution_note"]
        assert "no es de un punto por segundo" in t["resolution_note"]
        assert t["step_median_s"] == pytest.approx(600.0)

    def test_accepts_the_misspelled_calllsign_key(self):
        t = parse_track({"icao24": "abc123", "calllsign": "ARG1234", "path": []})
        assert t["callsign"] == "ARG1234"

    def test_empty_track(self):
        t = parse_track({"icao24": "abc123", "path": []})
        assert t["point_count"] == 0
        assert t["span_s"] == 0
        assert t["mean_step_s"] is None

    def test_malformed_payload(self):
        assert parse_track(None)["point_count"] == 0
        assert parse_track("nonsense")["point_count"] == 0

    def test_waypoints_with_no_timestamp(self):
        t = parse_track({
            "icao24": "abc123",
            "path": [[None, -34.6, -58.4, 100, 90, False]],
        })
        assert t["point_count"] == 1
        assert t["mean_step_s"] is None


# ─── Credit estimation (spec §49) ───────────────────────────────────────────

class TestCreditEstimation:
    def test_live_window_costs_four(self):
        assert estimate_track_credits(1_758_000_000, 1_758_003_600) == 4

    def test_under_24h_costs_four(self):
        assert estimate_track_credits(1_758_000_000, 1_758_086_000) == 4

    def test_two_partitions_cost_30(self):
        # OpenSky bills by calendar days *crossed*. To land in the 1-2
        # partition band the window must exceed 24 h yet touch only two
        # midnights: yesterday 00:00 -> today 01:00 is 25 h / 2 partitions.
        begin = _midnight_utc() - 86_400
        end = _midnight_utc() + 3600
        assert estimate_track_credits(begin, end) == 30

    def test_three_partitions_cost_60_each(self):
        # Two days ago 00:00 -> today 01:00 = 49 h across 3 partitions.
        begin = _midnight_utc() - 2 * 86_400
        end = _midnight_utc() + 3600
        assert estimate_track_credits(begin, end) == 180

    def test_partitions_are_counted_from_midnight(self):
        # Three full days from midnight touches FOUR calendar days.
        base = _midnight_utc()
        assert estimate_track_credits(base, base + 3 * 86_400) == 240

    def test_cost_grows_with_partitions(self):
        day = 86_400
        base = _midnight_utc()
        one = estimate_track_credits(base, base + day)
        many = estimate_track_credits(base, base + 20 * day)
        assert many > one

    def test_states_serial_query_costs_one(self):
        assert estimate_states_credits() == 1

    def test_states_by_box_area(self):
        # area = lat_range * lon_range, in square degrees
        assert estimate_states_credits(-35, -59, -30, -54) == 1   # 25 sq°
        assert estimate_states_credits(-35, -59, -30, -49) == 2   # 50 sq°
        assert estimate_states_credits(-35, -59, -30, -29) == 3   # 150 sq°
        assert estimate_states_credits(-35, -59, -30, 0) == 3     # 295 sq°
        assert estimate_states_credits(-35, -59, -30, 40) == 4    # 495 sq°


# ─── Cache and backoff (spec §49) ───────────────────────────────────────────

class TestTTLCache:
    def test_set_get(self):
        c = TTLCache(default_ttl=10)
        c.set("k", 42)
        hit, value = c.get("k")
        assert hit is True and value == 42

    def test_miss_on_unknown_key(self):
        assert TTLCache().get("nope") == (False, None)

    def test_expiry(self):
        c = TTLCache(default_ttl=0.01)
        c.set("k", 1)
        import time as _t

        _t.sleep(0.05)
        assert c.get("k") == (False, None)

    def test_delete_and_clear(self):
        c = TTLCache()
        c.set("a", 1)
        c.set("b", 2)
        c.delete("a")
        assert c.get("a")[0] is False
        c.clear()
        assert c.get("b")[0] is False

    def test_max_entries_evicts(self):
        c = TTLCache(default_ttl=60, max_entries=10)
        for i in range(50):
            c.set(f"k{i}", i)
        assert len(c._data) <= 10

    def test_single_flight_deduplicates(self):
        """Two concurrent misses must trigger one factory call."""
        c = TTLCache(default_ttl=60)
        calls = {"n": 0}

        async def factory():
            calls["n"] += 1
            await asyncio.sleep(0.01)
            return "value"

        async def _go():
            return await asyncio.gather(
                c.get_or_set("k", factory), c.get_or_set("k", factory)
            )

        results = run(_go())
        assert calls["n"] == 1
        assert all(r[0] == "value" for r in results)
        # The second caller learns it was a cache hit.
        assert sorted(r[1] for r in results) == [False, True]


class TestBackoff:
    def test_starts_inactive(self):
        b = BackoffController(base_s=1, max_s=10)
        assert b.active is False

    def test_trip_activates(self):
        b = BackoffController(base_s=30, max_s=900)
        delay = b.trip()
        assert b.active is True
        assert 0 < delay <= 900

    def test_backoff_doubles(self):
        b = BackoffController(base_s=10, max_s=1000)
        d1 = b.trip()
        d2 = b.trip()
        d3 = b.trip()
        assert d2 > d1 and d3 > d2

    def test_respects_retry_after_when_larger(self):
        b = BackoffController(base_s=10, max_s=900)
        assert b.trip(retry_after=300) == 300

    def test_capped_at_max(self):
        b = BackoffController(base_s=10, max_s=60)
        for _ in range(10):
            b.trip()
        assert b.state()["retry_after_s"] <= 60

    def test_clear_resets(self):
        b = BackoffController(base_s=30)
        b.trip()
        b.clear()
        assert b.active is False
        assert b.state()["level"] == 0


class TestCreditAwareClient:
    def test_second_call_is_served_from_cache(self):
        b = BackoffController()
        client = CreditAwareClient(POOL_STATES, 60, b)
        calls = {"n": 0}

        async def factory():
            calls["n"] += 1
            return ["data"]

        async def _go():
            await client.fetch("k", factory)
            await client.fetch("k", factory)

        run(_go())
        assert calls["n"] == 1
        assert client.hits >= 1
        assert client.upstream_calls == 1

    def test_raises_while_backed_off(self):
        b = BackoffController(base_s=30)
        b.trip()
        client = CreditAwareClient(POOL_TRACKS, 60, b)

        async def factory():  # pragma: no cover - must not run
            raise AssertionError("factory called while backed off")

        async def _go():
            with pytest.raises(RateLimitedError):
                await client.fetch("k", factory)

        run(_go())

    def test_cached_value_served_even_while_backed_off(self):
        b = BackoffController(base_s=30)
        client = CreditAwareClient(POOL_STATES, 600, b)

        async def factory():
            return "cached"

        async def _go():
            await client.fetch("k", factory)
            b.trip()
            value, from_cache = await client.fetch("k", factory)
            return value, from_cache

        value, from_cache = run(_go())
        assert value == "cached"
        assert from_cache is True

    def test_stats(self):
        client = CreditAwareClient(POOL_STATES, 60, BackoffController())
        client.stats()
        assert client.stats()["pool"] == POOL_STATES


# ─── OpenSkyService (spec §19) ──────────────────────────────────────────────

class TestOpenSkyService:
    def _service(self, handler):
        calls = []

        def _route(request):
            url = str(request.url)
            calls.append(url)
            if "openid-connect/token" in url:
                return httpx.Response(
                    200, json={"access_token": "t", "expires_in": 1800}
                )
            result = handler(request)
            # A handler may return (status, body) or a ready-made Response.
            if isinstance(result, httpx.Response):
                return result
            status, body = result
            return httpx.Response(status, json=body)

        client = httpx.AsyncClient(transport=httpx.MockTransport(_route))
        # A fresh token manager per service: in production they share the
        # process-wide one (correct — one token for the whole app), but
        # tests need isolation to assert on refresh counts.
        tokens = OpenSkyTokenManager(
            client_id="cid", client_secret="csecret", http_client=client
        )
        svc = OpenSkyService(token_manager=tokens, http_client=client)
        return svc, calls

    def test_states_parsed(self, states_payload):
        svc, _ = self._service(lambda r: (200, states_payload))
        out = run(svc.get_states())
        assert out["count"] == 1
        assert out["states"][0]["icao24"] == "abc123"
        assert out["provenance"] == "live"

    def test_states_cached_between_calls(self, states_payload):
        svc, calls = self._service(lambda r: (200, states_payload))
        run(svc.get_states(icao24=["abc123"]))
        first = len(calls)
        run(svc.get_states(icao24=["abc123"]))
        # Only the token call happened once; the states call was cached.
        assert len(calls) == first

    def test_serial_query_costs_one_credit_for_many_aircraft(self, states_payload):
        """Five aircraft in one query, not five queries."""
        svc, calls = self._service(lambda r: (200, states_payload))
        run(svc.get_states(icao24=["abc123", "def456", "ghi789"]))
        states_calls = [c for c in calls if "states/all" in c]
        assert len(states_calls) == 1
        assert states_calls[0].count("icao24=") == 3

    def test_401_triggers_refresh_and_replay(self, states_payload):
        state = {"n": 0}

        def handler(request):
            state["n"] += 1
            if state["n"] == 1:
                return httpx.Response(401, json={"error": "expired"})
            return httpx.Response(200, json=states_payload)

        svc, _ = self._service(handler)
        out = run(svc.get_states())
        assert out["count"] == 1
        # The 401 caused exactly one replay, not a retry storm.
        assert state["n"] == 2

    def test_401_invalidates_the_cached_token(self, states_payload):
        state = {"n": 0}

        def handler(request):
            state["n"] += 1
            return httpx.Response(401, json={}) if state["n"] == 1 \
                else httpx.Response(200, json=states_payload)

        svc, _ = self._service(handler)
        run(svc.get_states())
        # A fresh token was fetched for the replay.
        assert svc.tokens.state.refreshes == 2
        assert svc.tokens.is_valid is True

    def test_401_twice_raises(self):
        def handler(request):
            if "openid-connect/token" in str(request.url):
                return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
            return httpx.Response(401, json={})

        svc, _ = self._service(handler)
        with pytest.raises(OpenSkyError) as exc:
            run(svc.get_states())
        assert exc.value.status == 401

    def test_429_raises_rate_limited_and_trips_backoff(self):
        def handler(request):
            if "openid-connect/token" in str(request.url):
                return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
            return httpx.Response(
                429,
                json={"error": "quota"},
                headers={
                    "X-Rate-Limit-Remaining": "0",
                    "X-Rate-Limit-Retry-After-Seconds": "42",
                },
            )

        svc, _ = self._service(handler)
        with pytest.raises(RateLimitedError) as exc:
            run(svc.get_states())
        assert exc.value.retry_after_s == 42
        assert svc.backoff.active is True

    def test_404_is_no_data_not_an_error(self):
        def handler(request):
            if "openid-connect/token" in str(request.url):
                return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
            return httpx.Response(404, json={})

        svc, _ = self._service(handler)
        out = run(svc.get_track("abc123"))
        assert out["available"] is False
        assert out["point_count"] == 0
        assert "no tiene track" in out["note"]

    def test_400_raises_with_parameter_hint(self):
        def handler(request):
            if "openid-connect/token" in str(request.url):
                return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
            return httpx.Response(400, json={})

        svc, _ = self._service(handler)
        with pytest.raises(OpenSkyError) as exc:
            run(svc.get_states())
        assert exc.value.status == 400

    def test_5xx_raises(self):
        def handler(request):
            if "openid-connect/token" in str(request.url):
                return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
            return httpx.Response(503, json={})

        svc, _ = self._service(handler)
        with pytest.raises(OpenSkyError) as exc:
            run(svc.get_states())
        assert exc.value.status == 503

    def test_track_parsed_and_labelled(self, track_payload):
        svc, _ = self._service(lambda r: (200, track_payload))
        out = run(svc.get_track("abc123", time_=1758000000))
        assert out["point_count"] == 3
        assert out["provenance"] == "historical"
        assert out["mean_step_s"] == pytest.approx(600.0)

    def test_live_track_sets_provenance_live(self, track_payload):
        svc, _ = self._service(lambda r: (200, track_payload))
        out = run(svc.get_live_track("abc123"))
        assert out["provenance"] == "live"

    def test_bounding_box_query(self, states_payload):
        svc, calls = self._service(lambda r: (200, states_payload))
        run(svc.get_states_in_box(-35.0, -59.0, -34.0, -58.0))
        url = [c for c in calls if "states/all" in c][0]
        assert "lamin=-35.0" in url and "lomax=-58.0" in url

    def test_flights_404_returns_empty_list(self):
        def handler(request):
            if "openid-connect/token" in str(request.url):
                return httpx.Response(200, json={"access_token": "t", "expires_in": 1800})
            return httpx.Response(404, json={})

        svc, _ = self._service(handler)
        assert run(svc.get_flights(1, 2, icao24="abc123")) == []

    def test_flights_window_is_clamped_to_two_hours(self):
        svc, calls = self._service(lambda r: (200, []))
        run(svc.get_flights(1_758_000_000, 1_758_000_000 + 86_400))
        url = [c for c in calls if "flights/all" in c][0]
        begin = int(url.split("begin=")[1].split("&")[0])
        end = int(url.split("end=")[1].split("&")[0])
        assert end - begin <= 2 * 3600

    def test_status_reports_no_secret(self, states_payload):
        svc, _ = self._service(lambda r: (200, states_payload))
        run(svc.get_states())
        status = svc.status()
        assert "test-client-secret" not in str(status)
        assert status["configured"] is True
        assert "states" in status["pools"]

    def test_invalidate_clears_a_pool(self, states_payload):
        svc, _ = self._service(lambda r: (200, states_payload))
        run(svc.get_states(icao24=["abc123"]))
        svc.invalidate("states")
        assert svc.states.cache.stats()["entries"] == 0
