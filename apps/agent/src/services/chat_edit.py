"""Synchronous chat-edit pipeline (docs/agent/design.md §13).

[NOTE — public showcase repo] The production chat-edit path (the DeepSeek
system prompt, the model call, and the repair loop) is proprietary and withheld
from this repository. What remains here is the deterministic, prompt-free
machinery — patch coercion, patch application, per-template text clamping, and a
runnable MOCK path — so the Web → Agent → apply → re-validate seam stays
testable in AGENT_PIPELINE_MODE=mock without any model key. The full design is
documented in docs/agent/design.md §13.

Single DeepSeek call → LayoutPatch entries → apply to currentLayout → validate
the resulting layout against AlbumLayoutPlan schema + 9 business rules. One
repair attempt; on second failure raise ChatEditError (route maps to 502
AGENT_CHAT_FAILED)."""

import time
from typing import Any

from pydantic import ValidationError

from ..logging_config import get_logger
from ..schemas import (
    AlbumLayoutPlan,
    ChatEditRequest,
    ChatEditResponse,
    ChatEditUsage,
    LayoutPatchEntry,
    Page,
)
from ..settings import get_settings
from . import layout_rules

log = get_logger("chat_edit")


class ChatEditError(Exception):
    """Maps to AGENT_CHAT_FAILED (HTTP 502)."""


def _coerce_patch(parsed: Any) -> tuple[str, list[LayoutPatchEntry]]:
    if not isinstance(parsed, dict):
        raise ChatEditError(f"chat response not an object (got {type(parsed).__name__})")
    reply = str(parsed.get("assistantReply") or "").strip()
    patch_raw = parsed.get("layoutPatch")
    if not reply:
        raise ChatEditError("chat response missing assistantReply")
    if not isinstance(patch_raw, list) or not patch_raw:
        raise ChatEditError("chat response missing layoutPatch[]")

    entries: list[LayoutPatchEntry] = []
    for idx, item in enumerate(patch_raw):
        if not isinstance(item, dict):
            raise ChatEditError(f"layoutPatch[{idx}] not an object")
        try:
            entries.append(
                LayoutPatchEntry(
                    pageIndex=int(item["pageIndex"]),
                    templateId=item.get("templateId"),
                    images=item.get("images"),
                    texts=item.get("texts"),
                )
            )
        except (KeyError, ValidationError, ValueError, TypeError) as exc:
            raise ChatEditError(f"layoutPatch[{idx}] failed schema: {exc}") from exc

    return reply[:500], entries


def _apply_patch(
    current: AlbumLayoutPlan,
    patch: list[LayoutPatchEntry],
) -> AlbumLayoutPlan:
    by_index: dict[int, Page] = {p.pageIndex: p for p in current.pages}
    next_pages: list[Page] = [p.model_copy(deep=True) for p in current.pages]
    next_by_index = {p.pageIndex: p for p in next_pages}

    for entry in patch:
        if entry.pageIndex not in by_index:
            raise ChatEditError(
                f"patch targets pageIndex {entry.pageIndex} which does not exist"
            )
        original = next_by_index[entry.pageIndex]

        if entry.templateId and entry.templateId != original.templateId:
            # Template change: require full images+texts replacement
            if entry.images is None or entry.texts is None:
                raise ChatEditError(
                    f"page {entry.pageIndex}: templateId change requires both images and texts"
                )
            new_page = Page(
                pageIndex=entry.pageIndex,
                templateId=entry.templateId,
                images=dict(entry.images),
                texts=dict(entry.texts),
            )
        else:
            new_images = dict(original.images)
            new_texts = dict(original.texts)
            if entry.images is not None:
                # Replace whole image map when provided (slot keys may differ).
                new_images = dict(entry.images)
            if entry.texts is not None:
                new_texts.update(entry.texts)
            new_page = Page(
                pageIndex=entry.pageIndex,
                templateId=original.templateId,
                images=new_images,
                texts=new_texts,
            )

        # Replace in place
        for i, p in enumerate(next_pages):
            if p.pageIndex == entry.pageIndex:
                next_pages[i] = new_page
                break

    try:
        return AlbumLayoutPlan(
            magazine=current.magazine,
            photos=current.photos,
            pages=next_pages,
        )
    except ValidationError as exc:
        raise ChatEditError(f"patched layout schema failed: {exc.errors()[:1]}") from exc


def _clamp_patch(
    current: AlbumLayoutPlan,
    patch: list[LayoutPatchEntry],
) -> list[LayoutPatchEntry]:
    """Trim each patch entry's texts to the effective template's maxChars so the
    returned patch matches the validated layout. The effective template is the
    entry's templateId if it changes one, else the current page's template."""
    by_index = {p.pageIndex: p for p in current.pages}
    out: list[LayoutPatchEntry] = []
    for entry in patch:
        if not entry.texts:
            out.append(entry)
            continue
        current_page = by_index.get(entry.pageIndex)
        template_id = entry.templateId or (current_page.templateId if current_page else None)
        if not template_id:
            out.append(entry)
            continue
        clamped = layout_rules.clamp_texts_for_template(template_id, entry.texts)
        out.append(entry.model_copy(update={"texts": clamped}) if clamped != entry.texts else entry)
    return out


def _mock_chat_edit(req: ChatEditRequest, started: float) -> ChatEditResponse:
    """Deterministic, rules-safe stub used when AGENT_PIPELINE_MODE=mock, so the
    chat round-trip (Web → Agent → apply → persist → re-validate) is testable
    without a DeepSeek key — mirroring vision_mock / planning_mock for layout.
    It echoes the first page's existing texts as a no-op patch; it does NOT do
    real editing, which needs the live model (verified at deploy).

    Business rules (layout_rules) are intentionally NOT enforced here: mock
    layouts from planning_mock are smoke fixtures that don't satisfy every rule
    (e.g. unused photos, over-length text), so enforcing them would make the
    seam untestable. _apply_patch still guarantees a structurally valid layout
    (AlbumLayoutPlan); the real chat-edit path keeps full rule enforcement."""
    if not req.currentLayout.pages:
        raise ChatEditError("mock chat-edit: layout has no pages")
    target = req.currentLayout.pages[0]
    patch = [LayoutPatchEntry(pageIndex=target.pageIndex, texts=dict(target.texts))]
    _apply_patch(req.currentLayout, patch)  # structural validation only
    duration_ms = int((time.monotonic() - started) * 1000)
    log.info("chat_edit.mock.ok", album_id=req.albumId, patch_size=len(patch))
    return ChatEditResponse(
        layoutPatch=patch,
        assistantReply=(
            f'(mock) Got it — "{req.userMessage[:120]}". '
            "Real edits apply once the model is connected."
        ),
        usage=ChatEditUsage(durationMs=duration_ms, model="mock-chat-edit"),
    )


async def run(req: ChatEditRequest) -> ChatEditResponse:
    settings = get_settings()
    started = time.monotonic()

    if settings.agent_pipeline_mode == "mock":
        return _mock_chat_edit(req, started)

    # The production chat-edit path (DeepSeek system prompt + model call + repair
    # loop) is proprietary and withheld from this public showcase repo.
    raise ChatEditError(
        "Real chat-edit pipeline is proprietary and withheld from this showcase "
        "repo. Run with AGENT_PIPELINE_MODE=mock. See docs/agent/design.md §13."
    )
