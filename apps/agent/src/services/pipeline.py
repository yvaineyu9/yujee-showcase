"""Three-stage layout pipeline orchestrator.

[NOTE — public showcase repo] The production pipeline (Volcano doubao vision +
DeepSeek writing/composing, including all prompts and model orchestration) is
proprietary and withheld from this repository. This file keeps the orchestration
scaffold and the MOCK pipeline, so the full data flow (progress callbacks, stage
boundaries, completed/failed envelopes) is runnable in AGENT_PIPELINE_MODE=mock.
The architecture is documented in docs/agent/design.md.

Each stage emits progress=0 on entry and progress=100 on success. On failure,
we emit one final `progress` callback for the failing stage (so the bar doesn't
jump straight from a stale value to failed) before the `failed` envelope, per
docs/agent/design.md §6 P0-7."""

import asyncio
import time
from dataclasses import dataclass

from ..logging_config import get_logger
from ..schemas import (
    AlbumLayoutPlan,
    CompletedCallback,
    FailedCallback,
    JobError,
    JobUsage,
    LayoutRequest,
    PhotoAnalysis,
    ProgressCallback,
)
from ..settings import get_settings
from . import callback, planning_mock, vision_mock

log = get_logger("pipeline")


_MOCK_STEP_SECONDS = 0.4


@dataclass
class _StageError(Exception):
    stage: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.stage}] {self.code}: {self.message}"


# ---------- callback helpers --------------------------------------------------


async def _emit_progress(req: LayoutRequest, stage: str, progress: int) -> None:
    envelope = ProgressCallback(
        event="progress",
        requestId=req.requestId,
        stage=stage,  # type: ignore[arg-type]
        progress=progress,
    )
    await callback.post(str(req.callbackUrl), envelope)


async def emit_failure(req: LayoutRequest, *, code: str, message: str, stage: str | None = None) -> None:
    if stage is not None:
        # Surface a progress=0 on the failing stage first so the UI bar resets,
        # then fail. Best-effort: don't crash failure path if this throws.
        try:
            await _emit_progress(req, stage, 0)
        except Exception as exc:  # noqa: BLE001
            log.warning("pipeline.pre_fail_progress_error", error=str(exc))

    envelope = FailedCallback(
        event="failed",
        requestId=req.requestId,
        error=JobError(code=code, message=message[:500]),
    )
    await callback.post(str(req.callbackUrl), envelope)


# ---------- mock branch -------------------------------------------------------


async def _run_mock(req: LayoutRequest) -> tuple[AlbumLayoutPlan, int]:
    photos: list[PhotoAnalysis] = []
    for stage in ("vision", "writing", "composing"):
        await _emit_progress(req, stage, 0)
        await asyncio.sleep(_MOCK_STEP_SECONDS)
        await _emit_progress(req, stage, 50)
        await asyncio.sleep(_MOCK_STEP_SECONDS)
        if stage == "vision":
            photos = vision_mock.analyze(req)
        await _emit_progress(req, stage, 100)

    layout = planning_mock.plan(req, photos)
    return layout, 0


# ---------- real branch (proprietary — withheld from showcase repo) -----------


async def _run_real(req: LayoutRequest) -> tuple[AlbumLayoutPlan, dict[str, int]]:
    # The production pipeline (doubao vision + DeepSeek writing/composing with the
    # real prompts) is proprietary and not part of this public showcase repo.
    # Run with AGENT_PIPELINE_MODE=mock to exercise the full data flow end to end.
    raise NotImplementedError(
        "Real pipeline is proprietary and withheld from this showcase repo. "
        "See docs/agent/design.md."
    )


# ---------- entry -------------------------------------------------------------


async def run(req: LayoutRequest) -> None:
    settings = get_settings()
    started = time.monotonic()

    if req.prompt == "FAIL_TEST":
        log.info("pipeline.forced_failure")
        await emit_failure(
            req,
            code="AGENT_VISION_FAILED",
            message="forced failure for test",
            stage="vision",
        )
        return

    log.info(
        "pipeline.start",
        photo_count=len(req.photos),
        mode=settings.agent_pipeline_mode,
        language=req.language,
    )

    try:
        if settings.agent_pipeline_mode == "mock":
            layout, vision_tokens = await _run_mock(req)
            planning_tokens = 0
        else:
            layout, usage_counters = await _run_real(req)
            vision_tokens = usage_counters["vision_tokens"]
            planning_tokens = usage_counters["planning_tokens"]
    except _StageError as stage_err:
        await emit_failure(
            req,
            code=stage_err.code,
            message=stage_err.message,
            stage=stage_err.stage,
        )
        return

    duration_ms = int((time.monotonic() - started) * 1000)
    envelope = CompletedCallback(
        event="completed",
        requestId=req.requestId,
        layout=layout,
        usage=JobUsage(
            visionTokens=vision_tokens,
            planningTokens=planning_tokens,
            durationMs=duration_ms,
        ),
    )
    await callback.post(str(req.callbackUrl), envelope)
    log.info("pipeline.completed", duration_ms=duration_ms, pages=len(layout.pages))
