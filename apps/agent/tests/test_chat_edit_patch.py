"""Verifies the chat-edit patch application logic in isolation.

DeepSeek is not called — we feed a synthesized model response into the
internal helpers (`_coerce_patch` + `_apply_patch`) and check the result
against the business rules."""

import pytest

from src.schemas import AlbumLayoutPlan, Magazine, Page, PhotoAnalysis
from src.services import chat_edit
from src.services.layout_rules import violation


def _photo(pid: str, *, quality: str, orientation: str) -> PhotoAnalysis:
    return PhotoAnalysis(
        photoId=pid,
        description="test",
        tags=["t"],
        quality=quality,  # type: ignore[arg-type]
        orientation=orientation,  # type: ignore[arg-type]
        peopleCount="1",
        scene="outdoor",
        mood="warm",
    )


def _layout() -> AlbumLayoutPlan:
    photos = [
        _photo("p1", quality="hero", orientation="landscape"),
        _photo("p2", quality="detail", orientation="portrait"),
        _photo("p3", quality="fill", orientation="square"),
    ]
    pages = [
        Page(pageIndex=0, templateId="mag-13", images={"image": "p1"},
             texts={"title": "A spring trip to Kyoto", "intro": "x" * 45,
                    "issue": "YUJEE · 01", "credit": "AI ARRANGED · YUJEE"}),
        Page(pageIndex=1, templateId="mag-02", images={},
             texts={"items": "A page of entries."}),
        Page(pageIndex=2, templateId="mag-12",
             images={"imageTop": "p3", "imageBottom": "p2"},
             texts={"num1": "02", "num2": "03"}),
    ]
    return AlbumLayoutPlan(
        magazine=Magazine(title="Trip", style="warm-film", language="en"),
        photos=photos,
        pages=pages,
    )


class TestApplyPatch:
    def test_text_only_patch_preserves_other_pages(self):
        layout = _layout()
        _, patch = chat_edit._coerce_patch(
            {
                "assistantReply": "ok",
                "layoutPatch": [
                    {"pageIndex": 0, "texts": {"intro": "y" * 50}},
                ],
            }
        )
        patched = chat_edit._apply_patch(layout, patch)
        assert patched.pages[0].texts["intro"] == "y" * 50
        # other pages untouched
        assert patched.pages[1].templateId == "mag-02"
        assert patched.pages[2].images == {"imageTop": "p3", "imageBottom": "p2"}
        # business rules still hold
        assert violation(patched) is None

    def test_template_change_requires_full_replacement(self):
        layout = _layout()
        _, patch = chat_edit._coerce_patch(
            {
                "assistantReply": "swap template",
                "layoutPatch": [
                    {"pageIndex": 2, "templateId": "mag-15"},
                ],
            }
        )
        with pytest.raises(chat_edit.ChatEditError):
            chat_edit._apply_patch(layout, patch)

    def test_unknown_page_index_rejected(self):
        layout = _layout()
        _, patch = chat_edit._coerce_patch(
            {
                "assistantReply": "edit",
                "layoutPatch": [{"pageIndex": 99, "texts": {"items": "x"}}],
            }
        )
        with pytest.raises(chat_edit.ChatEditError):
            chat_edit._apply_patch(layout, patch)

    def test_patch_violating_business_rules_caught(self):
        # Patch removes the only reference to p3 → unused photo violation
        layout = _layout()
        _, patch = chat_edit._coerce_patch(
            {
                "assistantReply": "drop p3",
                "layoutPatch": [
                    {"pageIndex": 2, "images": {"imageBottom": "p2"}},
                ],
            }
        )
        # _apply_patch succeeds (schema OK), violation() then catches it
        patched = chat_edit._apply_patch(layout, patch)
        v = violation(patched)
        assert v is not None and ("unused" in v or "imageTop" in v or "slot" in v)


class TestClampPatch:
    def test_patch_text_clamped_to_template_maxchars(self):
        # doubao-lite overshoots maxChars; the returned patch must be clamped so
        # it equals the layout that was validated.
        layout = _layout()
        _, patch = chat_edit._coerce_patch(
            {
                "assistantReply": "longer title",
                "layoutPatch": [
                    {"pageIndex": 0,
                     "texts": {"title": "A spring trip to Kyoto in the early cherry season"}},
                ],
            }
        )
        clamped = chat_edit._clamp_patch(layout, patch)
        assert len(clamped[0].texts["title"]) <= 30  # mag-13.title cap
        patched = chat_edit._apply_patch(layout, clamped)
        assert violation(patched) is None


class TestCoercePatch:
    def test_missing_reply_rejected(self):
        with pytest.raises(chat_edit.ChatEditError):
            chat_edit._coerce_patch({"layoutPatch": [{"pageIndex": 0}]})

    def test_empty_patch_rejected(self):
        with pytest.raises(chat_edit.ChatEditError):
            chat_edit._coerce_patch({"assistantReply": "x", "layoutPatch": []})
