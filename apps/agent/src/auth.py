from fastapi import Header, HTTPException, status

from .settings import get_settings


async def require_bearer(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    expected = f"Bearer {settings.agent_shared_secret}"
    if not authorization or authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"ok": False, "error": {"code": "AGENT_UNAUTHORIZED", "message": "invalid bearer"}},
        )
