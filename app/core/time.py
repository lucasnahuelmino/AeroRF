"""
core/time.py
────────────
Shared UTC clock helper.

``datetime.utcnow()`` is deprecated from Python 3.12 onwards. Every model
needs the same "naive UTC now" default, so it lives here once instead of
being repeated — and deprecated — in twelve model files.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-naive UTC timestamp.

    Naive on purpose: the database columns are naive UTC throughout, which
    keeps SQLite and PostgreSQL comparisons identical. Converting to
    ``timestamp with time zone`` is part of the documented PostgreSQL
    migration.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc(value: datetime | None) -> datetime | None:
    """Normalise an aware datetime to naive UTC; leave naive values alone."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def from_unix(ts: int | float | None) -> datetime | None:
    """Unix seconds to naive UTC datetime, or ``None``."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).replace(tzinfo=None)
    except (ValueError, OSError, OverflowError):
        return None


def to_unix(value: datetime | None) -> int | None:
    """Naive-UTC datetime to Unix seconds, or ``None``."""
    if value is None:
        return None
    try:
        return int(value.replace(tzinfo=timezone.utc).timestamp())
    except (ValueError, OSError, OverflowError):
        return None
