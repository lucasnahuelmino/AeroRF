"""
services/cache.py
────────────────
Time-based cache with per-credit-pool TTLs and 429 backoff (spec §49).

OpenSky charges credits separately for ``states``, ``tracks`` and
``flights``, and the cost of a track request grows with the number of
day-partitions it spans. The practical consequences this module encodes:

* **Separate TTL per pool.** A cached track answer is never served for a
  states request and vice versa, because the TTL that is safe differs by
  an order of magnitude (seconds for live states, minutes for tracks).
* **A 429 puts the whole client in backoff.** Once the server tells us we
  are over budget, the correct response is to stop calling — not to
  retry immediately. The backoff doubles from ``base`` to ``max``.
* **In-flight de-duplication.** Two concurrent requests for the same
  key await a single upstream call instead of spending two credits.

This is an in-process cache. It is deliberately simple: AeroRF is a
single-user operational tool, and a shared cache (Redis) would add an
operational dependency for no benefit at this scale.
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.core.logging import log

# Credit pools, matching the three OpenSky endpoints AeroRF uses.
POOL_STATES = "states"
POOL_TRACKS = "tracks"
POOL_FLIGHTS = "flights"
POOL_AUTH = "auth"


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    created_at: float


@dataclass
class TTLCache:
    """Thread-safe TTL cache with a single-flight guard per key."""

    default_ttl: float = 10.0
    max_entries: int = 512
    _data: dict[str, CacheEntry] = field(default_factory=dict)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _guard: threading.Lock = field(default_factory=threading.Lock)

    # ─── Basic operations ────────────────────────────────────────────────
    def get(self, key: str) -> tuple[bool, Any]:
        """Return ``(hit, value)``; expired entries count as misses."""
        with self._guard:
            entry = self._data.get(key)
            if entry is None:
                return False, None
            if entry.expires_at <= time.monotonic():
                self._data.pop(key, None)
                return False, None
            return True, entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        effective = self.default_ttl if ttl is None else float(ttl)
        now = time.monotonic()
        with self._guard:
            if len(self._data) >= self.max_entries:
                self._evict_locked(now)
            self._data[key] = CacheEntry(
                value=value, expires_at=now + effective, created_at=now
            )

    def delete(self, key: str) -> None:
        with self._guard:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._guard:
            self._data.clear()
            self._locks.clear()

    def _evict_locked(self, now: float) -> None:
        """Drop expired entries first; if still full, drop the oldest."""
        expired = [k for k, e in self._data.items() if e.expires_at <= now]
        for key in expired:
            self._data.pop(key, None)
        if len(self._data) >= self.max_entries:
            oldest = sorted(self._data.items(), key=lambda kv: kv[1].created_at)
            for key, _ in oldest[: max(1, self.max_entries // 4)]:
                self._data.pop(key, None)

    def stats(self) -> dict:
        now = time.monotonic()
        with self._guard:
            live = [e for e in self._data.values() if e.expires_at > now]
            return {
                "entries": len(self._data),
                "live_entries": len(live),
                "keys": sorted(self._data.keys())[:50],
            }

    # ─── Single-flight ───────────────────────────────────────────────────
    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        ttl: Optional[float] = None,
    ) -> tuple[Any, bool]:
        """Return ``(value, from_cache)``.

        Concurrent callers for the same key share one execution of
        ``factory``: the first one runs it, the rest await the same
        result. That is what stops a burst of five aircraft from spending
        five identical credits.
        """
        hit, value = self.get(key)
        if hit:
            return value, True

        lock = self._lock_for(key)
        async with lock:
            # Re-check: another coroutine may have filled it while we
            # waited for the lock.
            hit, value = self.get(key)
            if hit:
                return value, True
            result = await factory()
            self.set(key, result, ttl)
            return result, False

    def _lock_for(self, key: str) -> asyncio.Lock:
        with self._guard:
            return self._locks.setdefault(key, asyncio.Lock())


class BackoffController:
    """Rate-limit gate driven by OpenSky 429 responses (spec §49)."""

    def __init__(self, base_s: float = 30.0, max_s: float = 900.0) -> None:
        self.base_s = base_s
        self.max_s = max_s
        self._until: float = 0.0
        self._level: int = 0
        self._lock = threading.Lock()

    @property
    def active(self) -> bool:
        return time.monotonic() < self._until

    @property
    def retry_after_s(self) -> float:
        return max(0.0, self._until - time.monotonic())

    def trip(self, retry_after: float | None = None) -> float:
        """Record a 429 and extend the cooldown.

        Honours ``Retry-After`` when the server sends one, and never goes
        below our own exponential floor.
        """
        with self._lock:
            self._level = min(self._level + 1, 16)
            exponential = self.base_s * (2 ** (self._level - 1))
            delay = min(self.max_s, max(exponential, float(retry_after or 0)))
            self._until = time.monotonic() + delay
            log.warning(
                "opensky.backoff",
                "rate limited, pausing OpenSky calls",
                level=self._level,
                retry_after_s=round(delay, 1),
            )
            return delay

    def clear(self) -> None:
        """Reset after a successful call."""
        with self._lock:
            if self._level:
                log.info(
                    "opensky.backoff_cleared", "credit restored", level=self._level
                )
            self._level = 0
            self._until = 0.0

    def state(self) -> dict:
        return {
            "active": self.active,
            "retry_after_s": round(self.retry_after_s, 1),
            "level": self._level,
        }


class CreditAwareClient:
    """Cache + backoff + statistics around an async fetch function.

    One instance per credit pool, created by ``OpenSkyService``. Tracks
    hits, misses, upstream calls and 429s so the operator can see whether
    the tool is burning credits.
    """

    def __init__(self, pool: str, ttl: float, backoff: BackoffController) -> None:
        self.pool = pool
        self.ttl = ttl
        self.cache = TTLCache(default_ttl=ttl)
        self.backoff = backoff
        self.hits = 0
        self.misses = 0
        self.upstream_calls = 0
        self.rate_limited = 0

    async def fetch(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        ttl: Optional[float] = None,
    ) -> tuple[Any, bool]:
        if self.backoff.active:
            hit, cached = self.cache.get(key)
            if hit:
                self.hits += 1
                return cached, True
            raise RateLimitedError(
                f"OpenSky rate limit active for the {self.pool} pool; "
                f"retry in {self.backoff.retry_after_s:.0f}s",
                retry_after_s=self.backoff.retry_after_s,
                pool=self.pool,
            )

        self.misses += 1
        # Wrap the factory so `upstream_calls` counts *actual* executions.
        # Counting here instead would over-report whenever concurrent
        # callers share a single-flight, which is exactly the case that
        # matters for credit accounting.
        async def _call() -> Any:
            self.upstream_calls += 1
            return await factory()

        try:
            value, from_cache = await self.cache.get_or_set(key, _call, ttl)
        except RateLimitedError:
            self.rate_limited += 1
            self.cache.delete(key)
            raise
        if from_cache:
            self.hits += 1
        return value, from_cache

    def invalidate(self, key: str | None = None) -> None:
        if key is None:
            self.cache.clear()
        else:
            self.cache.delete(key)

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "pool": self.pool,
            "ttl_s": self.ttl,
            "hits": self.hits,
            "misses": self.misses,
            "upstream_calls": self.upstream_calls,
            "rate_limited": self.rate_limited,
            "hit_rate": round(self.hits / total, 3) if total else None,
            "backoff": self.backoff.state(),
            "cache": self.cache.stats(),
        }


class RateLimitedError(RuntimeError):
    """Raised when OpenSky signals 429 and the backoff is active."""

    def __init__(
        self, message: str, retry_after_s: float = 0.0, pool: str = ""
    ) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s
        self.pool = pool


__all__ = [
    "TTLCache",
    "BackoffController",
    "CreditAwareClient",
    "RateLimitedError",
    "POOL_STATES",
    "POOL_TRACKS",
    "POOL_FLIGHTS",
    "POOL_AUTH",
]
