"""Verifies docs/agent/design.md §9 — sensitive fields never leak to logs.

We re-configure structlog with `cache_logger_on_first_use=False` for these
tests via a module-scoped fixture, then capture stdout."""

import json

import pytest
import structlog

from src.logging_config import _redact_processor, request_id_var


def _run(event_dict: dict) -> dict:
    """Drive the redact processor directly — bypasses structlog plumbing
    so we can assert on the output dict without stdout games."""
    return _redact_processor(None, None, dict(event_dict))


class TestRedaction:
    def test_base64_key_value_redacted(self):
        out = _run({"event": "evt", "base64": "data:image/png;base64,SECRETBYTES"})
        assert out["base64"] == "<redacted>"

    def test_prompt_key_value_redacted(self):
        out = _run({"event": "evt", "prompt": "user's secret text here"})
        assert out["prompt"] == "<redacted>"

    def test_api_key_redacted(self):
        out = _run({"event": "evt", "api_key": "sk-real-secret"})
        assert out["api_key"] == "<redacted>"

    def test_authorization_header_key_redacted(self):
        out = _run({"event": "evt", "Authorization": "Bearer abc.def.ghi"})
        assert out["Authorization"] == "<redacted>"

    def test_bearer_inline_scrubbed_in_safe_key(self):
        out = _run({"event": "evt", "note": "failed Authorization: Bearer abc.def.ghi"})
        assert "abc.def.ghi" not in out["note"]
        assert "Bearer <redacted>" in out["note"]

    def test_data_url_inline_scrubbed_in_safe_key(self):
        out = _run({"event": "evt", "note": "raw=data:image/jpeg;base64,LEAKED"})
        assert "LEAKED" not in out["note"]
        assert "data:image/<redacted>" in out["note"]

    def test_safe_fields_passthrough(self):
        out = _run({"event": "evt", "requestId": "r1", "stage": "vision", "progress": 50})
        assert out["requestId"] == "r1"
        assert out["stage"] == "vision"
        assert out["progress"] == 50

    def test_nested_dict_values_scrubbed(self):
        out = _run(
            {
                "event": "evt",
                "payload": {
                    "headers": {"Authorization": "Bearer xyz"},
                    "snippet": "data:image/jpeg;base64,ABC",
                },
            }
        )
        # Nested values are scrubbed by string content (regex), not key match.
        assert "xyz" not in json.dumps(out["payload"])
        assert "ABC" not in json.dumps(out["payload"])

    def test_email_key_redacted(self):
        out = _run({"event": "evt", "user_email": "a@b.com"})
        assert out["user_email"] == "<redacted>"

    def test_prompt_exact_key_redacted(self):
        out = _run({"event": "evt", "prompt": "user's secret prompt"})
        assert out["prompt"] == "<redacted>"

    def test_prompt_tokens_not_redacted(self):
        # "prompt" must not substring-match the allowed numeric usage fields.
        out = _run({"event": "evt", "prompt_tokens": 1820, "completion_tokens": 142})
        assert out["prompt_tokens"] == 1820
        assert out["completion_tokens"] == 142

    def test_prompt_length_not_redacted(self):
        # promptLength is explicitly an allowed field in design.md §9.
        out = _run({"event": "evt", "promptLength": 42})
        assert out["promptLength"] == 42
