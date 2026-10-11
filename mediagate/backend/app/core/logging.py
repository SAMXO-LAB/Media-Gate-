"""JSON logging with secret redaction."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

_REDACT_PATTERNS = [
    # query-string style: access_token=abc
    re.compile(r"\b((?:access_token|refresh_token|client_secret|api_key|key|token|code_verifier|code)=)[^&\s\"']+", re.I),
    # Authorization: Bearer abc
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.I),
    # JSON style: "access_token": "abc"
    re.compile(r"(\"(?:access_token|refresh_token|authorization|password|client_secret)\"\s*:\s*\")[^\"]+", re.I),
]


def redact(text: str) -> str:
    for pat in _REDACT_PATTERNS:
        text = pat.sub(lambda m: m.group(1) + "[REDACTED]", text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        for key in ("request_id", "job_id", "user_id", "platform", "status", "duration_ms", "path", "method"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # httpx logs full URLs at INFO, which can include query-string credentials.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
