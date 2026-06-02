# Proprietary services (withheld from this showcase repo)

The following modules contain the production prompts and model orchestration
and are **not included** in this public showcase repository:

- `vision.py` — Volcano doubao multi-image vision stage (prompt + parsing)
- `planning.py` — DeepSeek writing + composing stages (prompts + repair)
- `ai_client.py` — OpenAI-compatible model HTTP client / params
- the real-model paths inside `pipeline.py` and `chat_edit.py`

What **is** included and runnable here:

- the full stage scaffold and callback/progress protocol (`pipeline.py`)
- the prompt-free patch coercion / apply / clamp machinery (`chat_edit.py`)
- mock implementations (`vision_mock.py`, `planning_mock.py`) so the whole data
  flow runs end to end with `AGENT_PIPELINE_MODE=mock`
- the deterministic business-rule validator (`layout_rules.py`)
- schemas, routes, auth, structured logging with PII redaction, and tests

The architecture (stages, schemas, business rules, repair strategy, privacy
model) is fully documented in [`docs/agent/design.md`](../../../../docs/agent/design.md).

The product is live at **https://yujeeai.com**.
