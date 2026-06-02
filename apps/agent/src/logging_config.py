import logging
import re
from contextvars import ContextVar
from typing import Any

import structlog


request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


_REDACTED = "<redacted>"

# Keys in the structlog event_dict whose values must never leave the process,
# per docs/agent/design.md §9. Matching is case-insensitive on the key name.
#
# Exact-match keys: short, ambiguous names where a substring rule would catch
# benign fields. E.g. "prompt" must NOT redact "prompt_tokens" / "promptLength"
# (both are allowed numeric fields in §9).
_REDACT_KEY_EXACT = frozenset(
    {
        "prompt",
        "user_prompt",
        "userprompt",
        "system_prompt",
        "systemprompt",
        "history_content",
        "content",
    }
)

# Substring keys: distinctive enough that any key containing them is sensitive.
_REDACT_KEY_SUBSTRINGS = (
    "base64",
    "raw_response",
    "raw_content",
    "rawresponse",
    "rawcontent",
    "api_key",
    "apikey",
    "secret",
    "authorization",
    "bearer",
    "email",
    "user_id",
    "userid",
)

# Inside string values, scrub data URLs and bearer tokens even when the key
# itself isn't suspicious (e.g. a logged dict that happens to contain a photo).
_DATA_URL_RE = re.compile(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE)


def _scrub_string(value: str) -> str:
    value = _DATA_URL_RE.sub("data:image/<redacted>", value)
    value = _BEARER_RE.sub("Bearer <redacted>", value)
    return value


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    return value


def _should_redact_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _REDACT_KEY_EXACT:
        return True
    return any(token in lowered for token in _REDACT_KEY_SUBSTRINGS)


def _redact_processor(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        if _should_redact_key(key):
            event_dict[key] = _REDACTED
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict


def _inject_request_id(_, __, event_dict):
    event_dict["requestId"] = request_id_var.get()
    return event_dict


def configure_logging(level: str = "info") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _inject_request_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
