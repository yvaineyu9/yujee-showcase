from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
