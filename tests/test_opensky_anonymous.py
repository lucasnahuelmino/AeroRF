"""
tests/test_opensky_anonymous.py
──────────────────────────────
AeroRF without OpenSky credentials.

OpenSky serves ``/states/all`` to anonymous callers from a 400-credit
daily pool. Probed live on 2026-09-25:

    GET /states/all                      -> 200   (4 credits, global)
    GET /states/all?icao24=<hex>         -> 200   (1 credit)
    GET /states/all?lamin=…&lamax=…      -> 200   (1–3 credits by area)
    GET /tracks/all?icao24=…&time=0      -> 200   but empty
    GET /flights/all?begin=…&end=…       -> 403   needs OAuth2
    GET /flights/aircraft?…              -> 403   needs OAuth2

So AeroRF is useful for live traffic out of the box, and says so plainly
when an endpoint genuinely needs an account.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.cache import RateLimitedError
from app.services.opensky_client import OpenSkyTokenManager
from app.services.opensky_service import (
    OpenSkyError,
    OpenSkyNotConfigured,
    OpenSkyService,
    estimate_states_credits,
)

import json
from pathlib import Path

FIXTURE = (
    Path(__file__).parent / "fixtures" / "opensky_states_contract.json"
)


@pytest.fixture
def anonymous_service():
    """An OpenSkyService with no credentials, backed by a mock transport."""
    import dataclasses

    from app.core.config import get_settings

    capture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = [item["row"] for item in capture["sample"]]
    seen_auth_headers = []

    def _route(request: httpx.Request) -> httpx.Response:
        seen_auth_headers.append(request.headers.get("Authorization"))
        return httpx.Response(
            200, json={"time": capture["time"], "states": rows}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(_route))
    tokens = OpenSkyTokenManager(
        client_id="", client_secret="", http_client=client
    )
    service = OpenSkyService(token_manager=tokens, http_client=client)
    # Settings is a frozen dataclass, so swap in a modified copy rather
    # than trying to mutate the shared singleton.
    service.settings = dataclasses.replace(
        service.settings, opensky_allow_anonymous=True
    )
    service.seen_auth_headers = seen_auth_headers
    return service


def run(coro):
    import asyncio

    return asyncio.run(coro)


# ─── Capability ──────────────────────────────────────────────────────────────

class TestAnonymousCapability:
    def test_not_configured_but_states_available(self, anonymous_service):
        assert anonymous_service.configured is False
        assert anonymous_service.can_query_states is True
        assert anonymous_service.requires_credentials is False

    def test_states_reachable(self, anonymous_service):
        assert anonymous_service._can_reach("states/all") is True

    def test_flights_not_reachable(self, anonymous_service):
        for path in ("flights/all", "flights/aircraft", "flights/arrival",
                     "flights/departure"):
            assert anonymous_service._can_reach(path) is False, path

    def test_can_be_disabled(self, anonymous_service):
        import dataclasses

        anonymous_service.settings = dataclasses.replace(
            anonymous_service.settings, opensky_allow_anonymous=False
        )
        assert anonymous_service.can_query_states is False
        assert anonymous_service._can_reach("states/all") is False


# ─── Behaviour ───────────────────────────────────────────────────────────────

class TestAnonymousRequests:
    def test_states_fetched_without_authorization_header(self, anonymous_service):
        result = run(anonymous_service.get_states(icao24=["3c6444"]))
        assert result["count"] == 24
        # The whole point: no Bearer token is sent.
        assert all(h is None for h in anonymous_service.seen_auth_headers)

    def test_result_declares_anonymous_auth(self, anonymous_service):
        result = run(anonymous_service.get_states(icao24=["3c6444"]))
        assert result["auth"] == "anonymous"
        assert "notice" in result
        assert "anónimo" in result["notice"].lower()

    def test_states_are_parsed(self, anonymous_service):
        result = run(anonymous_service.get_states(icao24=["3c6444"]))
        for state in result["states"]:
            assert state["icao24"]
            assert len(state["icao24"]) == 6
            assert "position_age_s" in state

    def test_bounding_box_fetched(self, anonymous_service):
        result = run(
            anonymous_service.get_states_in_box(-35.0, -59.0, -33.5, -57.0)
        )
        assert result["count"] == 24
        assert result["auth"] == "anonymous"

    def test_cache_prevents_a_second_credit(self, anonymous_service):
        run(anonymous_service.get_states(icao24=["3c6444"]))
        first = len(anonymous_service.seen_auth_headers)
        run(anonymous_service.get_states(icao24=["3c6444"]))
        assert len(anonymous_service.seen_auth_headers) == first

    def test_flights_refuse_before_spending_a_request(self, anonymous_service):
        with pytest.raises(OpenSkyNotConfigured) as exc:
            run(anonymous_service.get_flights_all(1785000000, 1785003600))
        assert "credenciales" in str(exc.value).lower()
        # Refused locally: no request was made at all.
        assert anonymous_service.seen_auth_headers == []

    def test_track_refuses_clearly(self, anonymous_service):
        with pytest.raises(OpenSkyNotConfigured):
            run(anonymous_service.get_track("3c6444", time_=0))


# ─── Upstream refusals ───────────────────────────────────────────────────────

class TestAnonymousUpstreamResponses:
    def _service_returning(self, status, body=None, headers=None):
        def _route(request):
            return httpx.Response(status, json=body or {}, headers=headers or {})

        client = httpx.AsyncClient(transport=httpx.MockTransport(_route))
        tokens = OpenSkyTokenManager(client_id="", client_secret="", http_client=client)
        return OpenSkyService(token_manager=tokens, http_client=client)

    def test_403_becomes_a_credentials_message(self):
        svc = self._service_returning(403, {"error": "forbidden"})
        with pytest.raises(OpenSkyNotConfigured) as exc:
            run(svc.get_states())
        assert "403" not in str(exc.value) or "credenciales" in str(exc.value)
        assert "credenciales" in str(exc.value).lower()

    def test_401_anonymous_does_not_try_to_refresh(self):
        """There is no token to refresh, so it must not loop."""
        svc = self._service_returning(401, {"error": "unauthorized"})
        with pytest.raises(OpenSkyNotConfigured):
            run(svc.get_states())
        # One attempt only: a refresh loop would be a bug.
        assert svc.tokens.state.refreshes == 0

    def test_429_still_honours_the_backoff(self):
        svc = self._service_returning(
            429, {"error": "quota"},
            headers={"X-Rate-Limit-Retry-After-Seconds": "30"},
        )
        with pytest.raises(RateLimitedError):
            run(svc.get_states())
        assert svc.backoff.active is True

    def test_404_still_means_no_data(self):
        svc = self._service_returning(404, {})
        result = run(svc.get_states())
        assert result["count"] == 0
        assert result["auth"] == "anonymous"


# ─── Status reporting ────────────────────────────────────────────────────────

class TestAnonymousStatus:
    def test_status_reports_the_mode(self, anonymous_service):
        status = anonymous_service.status()
        assert status["configured"] is False
        assert status["auth_mode"] == "anonymous"
        assert status["can_query_states"] is True
        assert "anonymous_note" in status
        assert "400" in status["anonymous_note"]

    def test_status_never_leaks_anything(self, anonymous_service):
        assert "test-client-secret" not in str(anonymous_service.status())


# ─── Credit arithmetic for the anonymous path ───────────────────────────────

class TestAnonymousCreditCost:
    def test_watchlist_query_costs_one_credit(self):
        """Five aircraft in one query is 1 credit, not five."""
        assert estimate_states_credits() == 1

    def test_global_query_costs_four(self):
        # A whole-world box is > 400 sq°.
        assert estimate_states_credits(-90, -180, 90, 180) == 4

    def test_buenos_aires_box_is_cheap(self):
        # 1.5 deg x 2 deg = 3 sq° -> 1 credit.
        assert estimate_states_credits(-35.0, -59.0, -33.5, -57.0) == 1
