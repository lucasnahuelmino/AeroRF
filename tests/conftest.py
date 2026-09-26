"""
tests/conftest.py
─────────────────
Shared pytest fixtures.

Every test runs against a real, isolated SQLite database and never
touches the network. OpenSky is exercised through ``httpx.MockTransport``
so the parsing, caching, token-renewal and error-handling paths are all
tested for real without spending a credit or needing credentials.
"""

from __future__ import annotations

import os
import tempfile

import pytest

# Point the app at a throwaway database *before* any app module reads config.
_TMP_DB = os.path.join(tempfile.gettempdir(), "aerorf_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["OPENSKY_CLIENT_ID"] = "test-client-id"
os.environ["OPENSKY_CLIENT_SECRET"] = "test-client-secret"
os.environ["ENVIRONMENT"] = "test"


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Create the schema once for the whole session."""
    from app.database.database import Base, engine, init_db
    import app.models  # noqa: F401  (registers every model)

    Base.metadata.drop_all(bind=engine)
    init_db(create_all=True)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    """A clean session: tables are truncated between tests, not dropped."""
    from app.database.database import Base, SessionLocal, engine

    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.exec_driver_sql(f'DELETE FROM "{table.name}"')

    # Re-seed the default layers that init_db inserted.
    from app.database.database import init_db

    init_db(create_all=False)

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def settings():
    from app.core.config import get_settings

    return get_settings()


# ─── OpenSky fixtures ────────────────────────────────────────────────────────

#: A real-shaped state vector. Index 17 is the last field OpenSky documents.
STATE_VECTOR = [
    "abc123",              # 0 icao24
    "ARG1234  ",           # 1 callsign (padded, as OpenSky sends it)
    "Argentina",           # 2 origin_country
    1758000000,            # 3 time_position
    1758000005,            # 4 last_contact
    -58.381592,            # 5 longitude
    -34.603722,            # 6 latitude
    10500.0,               # 7 baro_altitude
    False,                 # 8 on_ground
    240.5,                 # 9 velocity
    89.5,                  # 10 true_track
    -1.25,                 # 11 vertical_rate
    [1, 2, 3],             # 12 sensors
    10620.0,               # 13 geo_altitude
    "1234",                # 14 squawk
    False,                 # 15 spi
    0,                     # 16 position_source (ADS-B)
    3,                     # 17 category (Small)
]


@pytest.fixture
def states_payload():
    """A `/states/all` response with one aircraft."""
    return {"time": 1758000005, "states": [STATE_VECTOR]}


@pytest.fixture
def track_payload():
    """A `/tracks/all` response shaped like OpenSky's waypoint list.

    Waypoints are deliberately sparse (about 10 minutes apart) because that
    is what OpenSky actually returns — the test suite must not assume 1 Hz.
    """
    return {
        "icao24": "abc123",
        "startTime": 1758000000,
        "endTime": 1758001200,
        "callsign": "ARG1234",
        "path": [
            [1758000000, -34.603722, -58.381592, 10500.0, 89.5, False],
            [1758000600, -34.500000, -58.300000, 11000.0, 91.0, False],
            [1758001200, -34.400000, -58.200000, 11500.0, 92.5, False],
        ],
    }


@pytest.fixture
def make_service(track_payload, states_payload):
    """Build an OpenSkyService wired to a mock transport.

    ``handler`` receives the httpx.Request and returns (status, json).
    """
    import httpx

    from app.services.opensky_service import OpenSkyService, get_opensky_service
    from app.services.opensky_client import get_token_manager

    def _build(handler, token_response=None):
        calls: list[str] = []

        def _route(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if "openid-connect/token" in str(request.url):
                if token_response is not None:
                    return token_response
                return httpx.Response(
                    200,
                    json={"access_token": "test-token", "expires_in": 1800},
                )
            status, body = handler(request)
            return httpx.Response(status, json=body)

        client = httpx.AsyncClient(transport=httpx.MockTransport(_route))
        service = OpenSkyService(http_client=client)
        service.tokens._client = client
        return service, calls

    yield _build

    # Leave the process singletons untouched by the tests.
    get_token_manager()
    get_opensky_service()
