from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging_config import configure_logging, get_logger, request_id_var
from .routes import chat_edit, health, layout
from .settings import get_settings


def _validate_startup_config() -> None:
    """Fail-fast checks per docs/agent/design.md §12.

    - AGENT_PIPELINE_MODE must be 'mock' or 'real' (Settings literal enforces this).
    - production env may only run with mode=real.
    - real mode demands both ARK_API_KEY and DEEPSEEK_API_KEY at startup so the
      first user request doesn't blow up on credentials we could have detected
      at boot.
    """
    settings = get_settings()
    if settings.agent_env == "production" and settings.agent_pipeline_mode != "real":
        raise RuntimeError(
            "AGENT_ENV=production requires AGENT_PIPELINE_MODE=real "
            f"(got {settings.agent_pipeline_mode!r})"
        )
    if settings.agent_pipeline_mode == "real":
        missing: list[str] = []
        if not settings.ark_api_key:
            missing.append("ARK_API_KEY")
        if not settings.deepseek_api_key:
            missing.append("DEEPSEEK_API_KEY")
        if missing:
            raise RuntimeError(
                "AGENT_PIPELINE_MODE=real requires env vars: " + ", ".join(missing)
            )


settings = get_settings()
configure_logging(settings.log_level)
_validate_startup_config()
log = get_logger("agent")

app = FastAPI(title="Yujee Agent", version="1.0.0")
app.include_router(health.router)
app.include_router(layout.router)
app.include_router(chat_edit.router)


@app.middleware("http")
async def bind_request_id(request: Request, call_next):
    rid = request.headers.get("x-request-id", "-")
    token = request_id_var.set(rid)
    try:
        log.info("request.start", method=request.method, path=request.url.path)
        response = await call_next(request)
        log.info("request.end", status=response.status_code)
        return response
    finally:
        request_id_var.reset(token)


@app.exception_handler(StarletteHTTPException)
async def http_exc_handler(_: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "ok" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "error": {"code": "AGENT_INTERNAL_ERROR", "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "ok": False,
            "error": {
                "code": "AGENT_INVALID_INPUT",
                "message": str(exc.errors()[0] if exc.errors() else "invalid input"),
            },
        },
    )


log.info(
    "agent.startup",
    mode=settings.agent_pipeline_mode,
    env=settings.agent_env,
    vision_model=settings.ark_vision_model,
    planning_model=settings.deepseek_model,
)
