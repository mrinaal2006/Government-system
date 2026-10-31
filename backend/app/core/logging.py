"""Structured logging with sensitive-field redaction.

Every record is emitted as one JSON object (or a readable line in console mode) and
carries the active request ID. A redaction filter masks values whose key names
suggest credentials or citizen personal data, as a defence in depth: code must still
avoid logging such data in the first place.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import LogFormat, Settings
from app.core.request_context import get_request_id

REDACTED = "[REDACTED]"
SENSITIVE_KEY_PATTERN = re.compile(
    r"(pass(word|wd)?|secret|token|authorization|cookie|session|api[_-]?key|otp|mfa|"
    r"aadhaar|aadhar|pan_?(number|no)|phone|mobile|email|address|dob|date_of_birth)",
    re.IGNORECASE,
)
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def redact(value: Any, key: str | None = None) -> Any:
    if key is not None and SENSITIVE_KEY_PATTERN.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {k: redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: redact(value, key)
        for key, value in record.__dict__.items()
        if key not in _RESERVED and not key.startswith("_")
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        payload.update(_extra_fields(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).strftime("%H:%M:%S")
        extras = " ".join(f"{k}={v}" for k, v in _extra_fields(record).items())
        rid = get_request_id()
        line = f"{ts} {record.levelname:<8} {record.name}: {record.getMessage()}"
        if rid:
            line += f" request_id={rid}"
        if extras:
            line += f" {extras}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if settings.log_format == LogFormat.JSON else ConsoleFormatter()
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)
    # Uvicorn's own access log would duplicate ours and include query strings.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error", "celery", "alembic"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
