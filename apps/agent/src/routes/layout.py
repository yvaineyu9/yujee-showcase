import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends

from ..auth import require_bearer
from ..logging_config import get_logger, request_id_var
from ..schemas import LayoutRequest
from ..services import pipeline
from ..settings import get_settings

router = APIRouter()
log = get_logger("layout")


async def _run_pipeline_with_timeout(req: LayoutRequest) -> None:
    settings = get_settings()
    token = request_id_var.set(req.requestId)
    try:
        try:
            await asyncio.wait_for(pipeline.run(req), timeout=settings.background_task_timeout_seconds)
        except asyncio.TimeoutError:
            log.error("pipeline.timeout")
            await pipeline.emit_failure(req, code="AGENT_TIMEOUT", message="background task exceeded timeout")
        except Exception as exc:
            log.exception("pipeline.unhandled", error=str(exc))
            await pipeline.emit_failure(req, code="AGENT_INTERNAL_ERROR", message=str(exc))
    finally:
        request_id_var.reset(token)


@router.post("/v1/layout", status_code=202, dependencies=[Depends(require_bearer)])
async def submit_layout(req: LayoutRequest, background_tasks: BackgroundTasks) -> dict:
    log.info("layout.accepted", photo_count=len(req.photos), language=req.language)
    background_tasks.add_task(_run_pipeline_with_timeout, req)
    return {"ok": True, "data": {"requestId": req.requestId, "accepted": True}}
