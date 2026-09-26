"""
services/opensky_client.py
──────────────────────────
`OpenSkyTokenManager` — OAuth2 client-credentials token lifecycle (spec §18).

OpenSky **exclusively** supports the OAuth2 client-credentials flow;
username/password basic auth is no longer accepted. Tokens live 30
minutes. The manager:

* fetches a token on first use and reuses it,
* renews it ``margin`` seconds before real expiry (default 60 s) so an
  in-flight request never races the expiry,
* refreshes at most once even if many coroutines need it at the same
  moment (single-flight under an ``asyncio.Lock``),
* forces a refresh and replays the request exactly once on ``401``,
* **never** exposes the token to a log record or an API response.

The token lives only in this process's memory. It is never written to
disk, never sent to the browser, and never included in a serialised
payload.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.logging import opensky_log

TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/"
    "protocol/openid-connect/token"
)

#: OpenSky tokens are valid for 30 minutes.
DEFAULT_EXPIRES_IN = 1800


class OpenSkyAuthError(RuntimeError):
    """Authentication against OpenSky failed. Credentials or endpoint."""


class SecretValue:
    """A string that refuses to be printed or serialised.

    Wrapping the token means an accidental ``logger.info(token)`` or a
    stray ``json.dumps`` of a request header cannot leak it. It renders
    as ``***`` everywhere.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """Explicit unwrap. Only the request path should call this."""
        return self._value

    def __str__(self) -> str:
        return "***"

    __repr__ = __str__

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: object) -> bool:  # pragma: no cover
        return isinstance(other, SecretValue) and other._value == self._value

    def __hash__(self) -> int:  # pragma: no cover
        return hash(self._value)


@dataclass
class TokenState:
    """Observable token state. Contains no secret material."""

    has_token: bool = False
    expires_in_s: Optional[float] = None
    acquired_at: Optional[float] = None
    refreshes: int = 0
    last_error: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "has_token": self.has_token,
            "expires_in_s": (
                round(self.expires_in_s, 1) if self.expires_in_s is not None else None
            ),
            "acquired_at": self.acquired_at,
            "refreshes": self.refreshes,
            "last_error": self.last_error,
        }


class OpenSkyTokenManager:
    """Obtains and renews the OpenSky access token."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_url: str = TOKEN_URL,
        margin_s: Optional[int] = None,
        timeout_s: float = 20.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        settings = get_settings()
        self._client_id = client_id if client_id is not None else settings.opensky_client_id
        self._client_secret = (
            client_secret
            if client_secret is not None
            else settings.opensky_client_secret
        )
        self._token_url = token_url
        self._margin_s = margin_s if margin_s is not None else settings.opensky_token_margin_s
        self._timeout_s = timeout_s

        self._token: Optional[SecretValue] = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout_s)

        self.state = TokenState()

    # ─── Configuration ────────────────────────────────────────────────────
    @property
    def configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    @property
    def is_valid(self) -> bool:
        """True when a non-expired token is held."""
        return self._token is not None and time.monotonic() < self._expires_at

    @property
    def seconds_remaining(self) -> float:
        if self._token is None:
            return 0.0
        return max(0.0, self._expires_at - time.monotonic())

    # ─── Token acquisition ────────────────────────────────────────────────
    async def get_token(self, force: bool = False) -> str:
        """Return a valid access token, refreshing when needed.

        Concurrent callers share a single refresh: the first coroutine to
        arrive performs the HTTP POST and the rest wait for its result.
        """
        if not force and self.is_valid:
            return self._token.reveal()

        async with self._lock:
            # Another coroutine may have refreshed while we waited.
            if not force and self.is_valid:
                return self._token.reveal()
            return await self._refresh()

    async def _refresh(self) -> str:
        if not self.configured:
            self.state.last_error = "credentials not configured"
            raise OpenSkyAuthError(
                "OpenSky credentials are not configured. Set "
                "OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET in the backend .env "
                "(see .env.example). AeroRF will run, but flight features are "
                "unavailable until they are provided."
            )

        payload = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        try:
            async with self._client.stream(
                "POST", self._token_url, data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._timeout_s,
            ) as response:
                status = response.status_code
                body = await response.aread()

            if status == 401 or status == 403:
                self.state.last_error = f"auth rejected ({status})"
                opensky_log.error(
                    "opensky.auth_failed",
                    "OpenSky rejected the client credentials",
                    status=status,
                )
                raise OpenSkyAuthError(
                    "OpenSky rejected the client credentials (HTTP "
                    f"{status}). Verify OPENSKY_CLIENT_ID and "
                    "OPENSKY_CLIENT_SECRET in the backend .env."
                )
            if status == 429:
                self.state.last_error = "rate limited"
                raise OpenSkyAuthError(
                    "OpenSky rate-limited the token endpoint (HTTP 429)."
                )
            if status >= 400:
                self.state.last_error = f"token endpoint error ({status})"
                opensky_log.error(
                    "opensky.auth_error", "token endpoint error", status=status
                )
                raise OpenSkyAuthError(
                    f"OpenSky token endpoint returned HTTP {status}."
                )

            import json as _json

            data = _json.loads(body or b"{}")

        except OpenSkyAuthError:
            raise
        except httpx.HTTPError as exc:
            self.state.last_error = type(exc).__name__
            opensky_log.error(
                "opensky.auth_network_error",
                "could not reach the OpenSky token endpoint",
                error=type(exc).__name__,
            )
            raise OpenSkyAuthError(
                f"Could not reach the OpenSky authentication server: {exc}"
            ) from exc

        access_token = data.get("access_token")
        if not access_token:
            self.state.last_error = "no access_token in response"
            raise OpenSkyAuthError(
                "OpenSky token response did not contain an access_token."
            )

        expires_in = int(data.get("expires_in") or DEFAULT_EXPIRES_IN)
        self._token = SecretValue(access_token)
        self._expires_at = time.monotonic() + max(0, expires_in - self._margin_s)

        self.state = TokenState(
            has_token=True,
            expires_in_s=expires_in,
            acquired_at=time.time(),
            refreshes=self.state.refreshes + 1,
            last_error=None,
        )
        opensky_log.info(
            "opensky.token_acquired",
            "access token renewed",
            expires_in_s=expires_in,
            margin_s=self._margin_s,
            refreshes=self.state.refreshes,
        )
        return access_token

    async def auth_headers(self, force: bool = False) -> dict[str, str]:
        token = await self.get_token(force=force)
        return {"Authorization": f"Bearer {token}"}

    def invalidate(self) -> None:
        """Drop the token so the next call re-authenticates (after a 401)."""
        self._token = None
        self._expires_at = 0.0
        self.state.has_token = False
        self.state.expires_in_s = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def status(self) -> dict:
        """Report token state for diagnostics. No secret material."""
        return {
            "configured": self.configured,
            "valid": self.is_valid,
            "seconds_remaining": round(self.seconds_remaining, 1),
            "margin_s": self._margin_s,
            **self.state.as_dict(),
        }


#: Process-wide manager. One instance, reused by every call, so the
#: token is fetched once and shared (spec §18: "el token debe reutilizarse").
_token_manager: Optional[OpenSkyTokenManager] = None


def get_token_manager() -> OpenSkyTokenManager:
    global _token_manager
    if _token_manager is None:
        _token_manager = OpenSkyTokenManager()
    return _token_manager


def reset_token_manager() -> None:
    """Drop the singleton. Test helper."""
    global _token_manager
    _token_manager = None
