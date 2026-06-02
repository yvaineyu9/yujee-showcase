from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import require_bearer
from ..logging_config import get_logger
from ..schemas import ChatEditRequest
from ..services.chat_edit import ChatEditError, run as run_chat_edit

router = APIRouter()
log = get_logger("chat_edit_route")


@router.post("/v1/chat-edit", dependencies=[Depends(require_bearer)])
async def chat_edit(req: ChatEditRequest) -> dict:
    log.info(
        "chat_edit.accepted",
        album_id=req.albumId,
        history_len=len(req.history),
        language=req.language,
    )
    try:
        response = await run_chat_edit(req)
    except ChatEditError as exc:
        log.warning("chat_edit.failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "ok": False,
                "error": {"code": "AGENT_CHAT_FAILED", "message": str(exc)[:300]},
            },
        ) from exc
    except Exception as exc:  # noqa: BLE001 — must still answer in contract shape
        log.exception("chat_edit.unhandled", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "ok": False,
                "error": {"code": "AGENT_INTERNAL_ERROR", "message": str(exc)[:300]},
            },
        ) from exc
    return {"ok": True, "data": response.model_dump(exclude_none=True, mode="json")}
