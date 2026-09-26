"""
core/logging.py
───────────────
Structured application logging (spec §51).

Records, per the spec:
  * OpenSky request: endpoint, duration, outcome
  * errors, and specifically 401 / 404 / 429 / 5xx
  * flight sessions (start / stop)
  * object creation and modification

Security: secrets are never written. ``SecretStr``-style masking is applied
by :func:`redact` and the OpenSky service passes tokens through
``SecretValue`` so they cannot reach a log record by accident.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.core.config import get_settings

LOGGER_NAME = "aerorf"

_configured = False

# Patterns that must never appear in a log line.
_SECRET_PATTERNS = (
    re.compile(r"(?i)(client_secret|client_id|token|authorization|password|secret)"
               r"(\"?\s*[:=]\s*\"?)([^\s\"',&}]+)"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),
)

_PLACEHOLDER = "***REDACTED***"


def redact(text: str) -> str:
    """Strip anything that looks like a credential from a string."""
    if not text:
        return text
    out = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 3:
            out = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{_PLACEHOLDER}", out)
        else:
            out = pattern.sub(_PLACEHOLDER, out)
    return out


class RedactingFilter(logging.Filter):
    """Defence in depth: scrub secrets from any formatted record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: (redact(v) if isinstance(v, str) else v)
                        for k, v in record.args.items()
                    }
                else:
                    record.args = tuple(
                        redact(a) if isinstance(a, str) else a for a in record.args
                    )
        except Exception:  # pragma: no cover - never break logging
            pass
        return True


class AeroRFLogger:
    """Adapter exposing a uniform ``extra`` payload on every call.

    ``event``/``msg``/the log level are declared **positional-only** (the
    ``/`` marker). That is deliberate: structured fields are named freely
    by callers — ``level`` for a backoff counter, ``event`` for a domain
    value — and with ordinary parameters those names would collide and
    raise ``TypeError`` from inside the logger, at the worst possible
    moment.
    """

    def __init__(self, name: str = LOGGER_NAME) -> None:
        self._log = logging.getLogger(name)

    def _emit(self, lvl: int, event: str, msg: str, /, **fields: Any) -> None:
        safe = {k: v for k, v in fields.items() if v is not None}
        self._log.log(lvl, "%s %s", event, msg, extra={"aerorf": safe})

    def debug(self, event: str, msg: str = "", /, **f: Any) -> None:
        self._emit(logging.DEBUG, event, msg, **f)

    def info(self, event: str, msg: str = "", /, **f: Any) -> None:
        self._emit(logging.INFO, event, msg, **f)

    def warning(self, event: str, msg: str = "", /, **f: Any) -> None:
        self._emit(logging.WARNING, event, msg, **f)

    def error(self, event: str, msg: str = "", /, **f: Any) -> None:
        self._emit(logging.ERROR, event, msg, **f)

    def exception(self, event: str, msg: str = "", /, **f: Any) -> None:
        self._log.error(
            "%s %s", event, msg, exc_info=True,
            extra={"aerorf": {k: v for k, v in f.items() if v is not None}},
        )


# Module-level handles. Import these instead of calling logging.getLogger.
log = AeroRFLogger("aerorf")
opensky_log = AeroRFLogger("aerorf.opensky")
object_log = AeroRFLogger("aerorf.objects")
flight_log = AeroRFLogger("aerorf.flights")


class _AeroRFFormatter(logging.Formatter):
    """Compact single-line format with an optional structured tail."""

    BASE = "%(asctime)s %(levelname)-7s %(name)-16s %(message)s"

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        payload = getattr(record, "aerorf", None)
        if payload:
            try:
                rendered = " ".join(
                    f"{k}={redact(str(v)) if isinstance(v, str) else v}"
                    for k, v in sorted(payload.items())
                )
                return f"{base} | {rendered}"
            except Exception:  # pragma: no cover
                return base
        return base


def setup_logging(
    level: str | None = None,
    log_file: str | None = None,
    force: bool = False,
) -> logging.Logger:
    """Configure the AeroRF logger. Idempotent unless ``force`` is set."""
    global _configured

    settings = get_settings()
    resolved_level = (level or settings.log_level or "INFO").upper()
    resolved_file = log_file if log_file is not None else settings.log_file

    root = logging.getLogger(LOGGER_NAME)
    if _configured and not force:
        return root

    root.setLevel(getattr(logging, resolved_level, logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:  # pragma: no cover
            pass

    formatter = _AeroRFFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    redactor = RedactingFilter()

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    stream.addFilter(redactor)
    root.addHandler(stream)

    if resolved_file:
        try:
            path = Path(resolved_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            rotating = logging.handlers.RotatingFileHandler(
                path, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
            )
            rotating.setFormatter(formatter)
            rotating.addFilter(redactor)
            root.addHandler(rotating)
        except OSError as exc:  # pragma: no cover - disk issues must not stop boot
            root.warning("logging.file_error %s", str(exc))

    # Uvicorn's own loggers are noisy and duplicate ours.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(noisy).handlers = []
        logging.getLogger(noisy).propagate = True

    _configured = True
    return root


@contextmanager
def timed(event: str, logger: AeroRFLogger = log, **fields: Any) -> Iterator[dict]:
    """Time a block and log its duration, even when it raises.

    Used for every outbound OpenSky call (spec §51: endpoint + duration).
    """
    # `event` is passed positionally to the logger, so it must not also
    # appear in the **fields expansion.
    state: dict[str, Any] = dict(fields)
    start = time.perf_counter()
    try:
        yield state
    except Exception as exc:
        state["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        state["error"] = type(exc).__name__
        logger.error("timing.failed", event, **state)
        raise
    else:
        state["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        logger.info("timing.ok", event, **state)


def log_payload(event: str, payload: Any, logger: AeroRFLogger = log) -> None:
    """Log a structured payload, redacting any string that looks secret."""
    if isinstance(payload, dict):
        safe = {k: (redact(v) if isinstance(v, str) else v) for k, v in payload.items()}
    else:
        safe = payload
    logger.info(event, "", payload=safe)
