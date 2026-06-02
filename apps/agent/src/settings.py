from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PipelineMode = Literal["mock", "real"]
AgentEnv = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # core
    agent_shared_secret: str = Field(..., min_length=1)
    web_base_url: str = "http://localhost:3000"
    background_task_timeout_seconds: int = 180
    port: int = 8001
    log_level: str = "info"

    # mode switches (see docs/agent/design.md §12)
    agent_pipeline_mode: PipelineMode = "mock"
    agent_env: AgentEnv = "development"

    # vision (火山 doubao-seed-1-6-vision)
    ark_api_key: str | None = None
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_vision_model: str = "doubao-seed-1-6-vision-250815"
    ark_timeout_seconds: int = 30
    # doubao-seed-* are reasoning models: reasoning_tokens share the max_tokens
    # budget and can truncate the JSON content (intermittent AGENT_VISION_FAILED,
    # worsening as photo count grows). Disable thinking for this structured
    # extraction. Ignored by non-doubao providers that don't accept `thinking`.
    ark_disable_thinking: bool = True

    # planning + chat-edit (DeepSeek slot; in prod points at Volcano Ark doubao)
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    # doubao-seed-2-0-lite composing runs longer than the 30s budget under real
    # prod load (full pages JSON, max_tokens=8192), tripping a per-call timeout
    # that left albums half-generated. 60s covers a slow single attempt while
    # still fitting inside background_task_timeout_seconds=180 on the happy path
    # (vision ~20s + writing ~20s + one composing call ~50s ≈ 90s).
    deepseek_timeout_seconds: int = 60
    # doubao-seed text models reject response_format=json_object (400
    # InvalidParameter); DeepSeek supports it. Default off so the configured
    # doubao planning model works; flip on only for a provider that supports it.
    deepseek_use_json_object: bool = False
    # Planning/chat-edit are combinatorial constraint satisfaction (slot
    # orientation+quality fit, photo reuse, page count): doubao's thinking
    # materially improves rule compliance here, so keep it ON by default
    # (unlike vision). Set True only for a non-reasoning planning provider.
    # NOTE: this governs the *writing* + chat-edit calls only; composing has its
    # own switch below.
    deepseek_disable_thinking: bool = False
    # Composing is the same reasoning-heavy slot, BUT it emits the full pages
    # JSON (max_tokens 8192) over a system prompt carrying the whole template
    # registry. With thinking ON, doubao-seed-2-0-lite did not return within
    # 60s on prod (verified: both internal attempts ReadTimeout at ~60s →
    # composing_failed → half-generated albums). Disable thinking here so a
    # single call lands well under the timeout; the repair loop + layout_rules
    # still catch any rule violations. Flip OFF only if a faster/abler composing
    # provider makes thinking affordable again.
    composing_disable_thinking: bool = True


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_cache() -> None:
    """Tests-only: clear the cached Settings instance so env overrides take effect."""
    global _settings
    _settings = None
