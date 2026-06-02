"""Smoke tests for the mock pipeline branch — exercises the orchestrator
without hitting any upstream AI."""

import asyncio
import json
from typing import Any

import pytest

from src.schemas import LayoutRequest, PhotoIn
from src.services import callback as cb_mod
from src.services import pipeline


@pytest.fixture
def captured_callbacks(monkeypatch):
    received: list[dict[str, Any]] = []

    async def fake_post(callback_url: str, envelope: Any) -> bool:
        received.append(envelope.model_dump(exclude_none=True, mode="json"))
        return True

    monkeypatch.setattr(cb_mod, "post", fake_post)
    return received


def _req(prompt: str = "A spring day in Kyoto") -> LayoutRequest:
    return LayoutRequest(
        requestId="req_test",
        prompt=prompt,
        language="en",
        callbackUrl="http://example.com/cb",
        photos=[
            PhotoIn(photoId="p1", base64="data:image/jpeg;base64,AAA", width=800, height=600),
            PhotoIn(photoId="p2", base64="data:image/jpeg;base64,BBB", width=600, height=800),
            PhotoIn(photoId="p3", base64="data:image/jpeg;base64,CCC", width=800, height=800),
        ],
    )


def test_mock_pipeline_emits_progress_and_completed(captured_callbacks):
    asyncio.run(pipeline.run(_req()))

    events = [c["event"] for c in captured_callbacks]
    assert events.count("progress") >= 9, events
    assert events.count("completed") == 1
    assert events.count("failed") == 0

    # Progress order: each stage hits 0 before 100
    by_stage: dict[str, list[int]] = {}
    for env in captured_callbacks:
        if env["event"] != "progress":
            continue
        by_stage.setdefault(env["stage"], []).append(env["progress"])
    for stage, ticks in by_stage.items():
        assert ticks[0] == 0, (stage, ticks)
        assert ticks[-1] == 100, (stage, ticks)

    completed = next(c for c in captured_callbacks if c["event"] == "completed")
    assert completed["layout"]["magazine"]["language"] == "en"
    assert len(completed["layout"]["pages"]) == 3
    assert "usage" in completed and "durationMs" in completed["usage"]


def test_forced_failure_emits_progress_before_failed(captured_callbacks):
    asyncio.run(pipeline.run(_req(prompt="FAIL_TEST")))

    events = [c["event"] for c in captured_callbacks]
    # Must see a progress on vision before the failed envelope.
    assert events[0] == "progress"
    assert captured_callbacks[0]["stage"] == "vision"
    assert events.count("failed") == 1
    failed = next(c for c in captured_callbacks if c["event"] == "failed")
    assert failed["error"]["code"] == "AGENT_VISION_FAILED"


def test_completed_layout_serializable(captured_callbacks):
    asyncio.run(pipeline.run(_req()))
    completed = next(c for c in captured_callbacks if c["event"] == "completed")
    # Round-trip must produce valid JSON (no exotic types from Pydantic).
    json.dumps(completed)


def _req_single(prompt: str = "A quiet afternoon") -> LayoutRequest:
    """architecture §6.5 decision 6 — a single-photo request must run end to end."""
    return LayoutRequest(
        requestId="req_single",
        prompt=prompt,
        language="en",
        callbackUrl="http://example.com/cb",
        photos=[
            PhotoIn(photoId="p1", base64="data:image/jpeg;base64,AAA", width=800, height=600),
        ],
    )


def test_single_photo_pipeline_completes_with_valid_layout(captured_callbacks):
    from src.schemas import AlbumLayoutPlan
    from src.services import layout_rules

    asyncio.run(pipeline.run(_req_single()))

    events = [c["event"] for c in captured_callbacks]
    assert events.count("completed") == 1
    assert events.count("failed") == 0

    completed = next(c for c in captured_callbacks if c["event"] == "completed")
    layout = AlbumLayoutPlan.model_validate(completed["layout"])
    assert layout_rules.violation(layout) is None
    # the user's only photo must appear in the album
    used = {pid for page in layout.pages for pid in page.images.values()}
    assert "p1" in used
