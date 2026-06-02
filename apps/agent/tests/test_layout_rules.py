import pytest

from src import templates as registry
from src.schemas import AlbumLayoutPlan, Magazine, Page, PhotoAnalysis
from src.services.layout_rules import (
    build_text_first_layout,
    clamp_page_texts,
    clamp_text,
    coerce_image_slots,
    violation,
)


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


def _good_layout() -> AlbumLayoutPlan:
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
             texts={"items": "A small page of entries kept from the trip."}),
        Page(pageIndex=2, templateId="mag-12",
             images={"imageTop": "p3", "imageBottom": "p2"},
             texts={"num1": "02", "num2": "03"}),
    ]
    return AlbumLayoutPlan(
        magazine=Magazine(title="Trip", style="warm-film", language="en"),
        photos=photos,
        pages=pages,
    )


class TestRules:
    def test_good_layout_passes(self):
        assert violation(_good_layout()) is None

    def test_unknown_template_caught(self):
        layout = _good_layout()
        layout.pages[1] = Page(pageIndex=1, templateId="does-not-exist", images={}, texts={})
        assert "TemplateRegistry" in (violation(layout) or "")

    def test_non_cover_first_page_caught(self):
        layout = _good_layout()
        layout.pages[0] = Page(pageIndex=0, templateId="mag-02", images={}, texts={"items": "x"})
        msg = violation(layout) or ""
        assert "cover" in msg

    def test_quality_mismatch_caught(self):
        # mag-16.imageTiny requires quality=['fill'] — putting a hero there fails.
        layout = _good_layout()
        layout.pages[2] = Page(
            pageIndex=2,
            templateId="mag-16",
            images={"imageTiny": "p1", "imagePerson": "p1", "imageHarbor": "p1"},
            texts={"caption1": "x" * 45, "caption2": "y" * 45,
                   "caption3": "z" * 45, "quote": "q" * 35},
        )
        msg = violation(layout) or ""
        # p1 is landscape but imageTiny requires portrait → orientation hits first
        assert "orientation" in msg or "quality" in msg

    def test_unused_photo_caught(self):
        layout = _good_layout()
        layout.pages[2] = Page(pageIndex=2, templateId="mag-02", images={},
                               texts={"items": "x"})
        assert "unused" in (violation(layout) or "")

    def test_dup_on_same_page_caught(self):
        # mag-18 has two portrait slots — give it the same photoId twice
        photos = [
            _photo("p1", quality="hero", orientation="landscape"),
            _photo("p2", quality="detail", orientation="portrait"),
        ]
        layout = AlbumLayoutPlan(
            magazine=Magazine(title="x", style="warm-film", language="en"),
            photos=photos,
            pages=[
                Page(pageIndex=0, templateId="mag-13", images={"image": "p1"},
                     texts={"title": "Trip to Tokyo", "intro": "y" * 45,
                            "issue": "YUJEE · 01", "credit": "AI ARRANGED · YUJEE"}),
                Page(pageIndex=1, templateId="mag-02", images={}, texts={"items": "x"}),
                Page(pageIndex=2, templateId="mag-18",
                     images={"imageLeft": "p2", "imageRight": "p2"},
                     texts={"numLeft": "01", "numRight": "02",
                            "captionLeft": "x" * 45, "captionRight": "y" * 45,
                            "subtitle": "z" * 35}),
            ],
        )
        msg = violation(layout) or ""
        assert "twice on same page" in msg


class TestCoerce:
    def _magazine(self) -> Magazine:
        return Magazine(title="Trip", style="warm-film", language="en")

    def test_fully_scrambled_layout_passes_after_coerce(self):
        # Every photo is mis-assigned, yet each has a compatible slot somewhere.
        # coerce must clear all violations and re-home everyone — no drops.
        photos = [
            _photo("p1", quality="hero",   orientation="landscape"),
            _photo("p2", quality="hero",   orientation="portrait"),
            _photo("p3", quality="detail", orientation="portrait"),
            _photo("p4", quality="fill",   orientation="square"),
            _photo("p5", quality="detail", orientation="landscape"),
            _photo("p6", quality="detail", orientation="square"),
        ]
        layout = AlbumLayoutPlan(
            magazine=self._magazine(),
            photos=photos,
            pages=[
                # cover slot wants landscape — gets a square/fill
                Page(pageIndex=0, templateId="mag-13", images={"image": "p4"},
                     texts={}),
                # mag-04: image1=landscape, image2=portrait, image3=square — all wrong
                Page(pageIndex=1, templateId="mag-04",
                     images={"image1": "p2", "image2": "p1", "image3": "p5"},
                     texts={}),
                # mag-12: imageTop=square, imageBottom=portrait — both wrong
                Page(pageIndex=2, templateId="mag-12",
                     images={"imageTop": "p3", "imageBottom": "p6"},
                     texts={}),
            ],
        )
        assert violation(layout) is not None  # scrambled → fails before coerce

        coerced = coerce_image_slots(layout)
        assert violation(coerced) is None
        # every photo still present and used at least once
        assert {p.photoId for p in coerced.photos} == {"p1", "p2", "p3", "p4", "p5", "p6"}

    def test_unplaceable_photo_is_dropped(self):
        # p3 (square/fill) has no compatible slot in this template set → coerce
        # drops it from photos[] so Rule 3 still holds, keeping the album shippable.
        photos = [
            _photo("p1", quality="hero", orientation="landscape"),
            _photo("p2", quality="hero", orientation="portrait"),
            _photo("p3", quality="fill", orientation="square"),
        ]
        layout = AlbumLayoutPlan(
            magazine=self._magazine(),
            photos=photos,
            pages=[
                Page(pageIndex=0, templateId="mag-13", images={"image": "p1"},
                     texts={}),
                Page(pageIndex=1, templateId="mag-08", images={"image": "p2"},
                     texts={}),
                Page(pageIndex=2, templateId="mag-02", images={}, texts={}),
            ],
        )
        # p3 is unused from the start → fails Rule 3 before coerce
        assert "unused" in (violation(layout) or "")

        coerced = coerce_image_slots(layout)
        assert violation(coerced) is None
        assert {p.photoId for p in coerced.photos} == {"p1", "p2"}

    def test_valid_placements_preserved(self):
        layout = _good_layout()
        coerced = coerce_image_slots(layout)
        assert violation(coerced) is None
        assert len(coerced.photos) == 3
        # the model's correct assignments are left untouched
        assert coerced.pages[0].images == {"image": "p1"}
        assert coerced.pages[2].images == {"imageTop": "p3", "imageBottom": "p2"}

    def test_quality_mismatch_coerced(self):
        # mag-18 imageLeft accepts only detail/fill — a hero photo there is the
        # exact prod failure (requestId 22998fe0). coerce swaps in a fitting photo.
        photos = [
            _photo("p1", quality="hero",   orientation="landscape"),
            _photo("p2", quality="detail", orientation="portrait"),
            _photo("p3", quality="fill",   orientation="portrait"),
        ]
        layout = AlbumLayoutPlan(
            magazine=self._magazine(),
            photos=photos,
            pages=[
                Page(pageIndex=0, templateId="mag-13", images={"image": "p1"},
                     texts={}),
                Page(pageIndex=1, templateId="mag-02", images={}, texts={}),
                # imageLeft/imageRight want detail|fill portraits; p1 is hero/landscape
                Page(pageIndex=2, templateId="mag-18",
                     images={"imageLeft": "p1", "imageRight": "p2"}, texts={}),
            ],
        )
        msg = violation(layout) or ""
        assert "quality" in msg or "orientation" in msg

        coerced = coerce_image_slots(layout)
        assert violation(coerced) is None


class TestFewPhotoFallback:
    """architecture §6.5 decision 6 — photo floor ≥1. The deterministic
    text-first builder must produce a §4.3-valid album for 1-2 photos of any
    orientation/quality, and every photo must appear at least once."""

    def _magazine(self) -> Magazine:
        return Magazine(title="A spring trip to Kyoto", style="warm-film", language="en")

    @pytest.mark.parametrize("orientation", ["landscape", "portrait", "square"])
    @pytest.mark.parametrize("quality", ["hero", "detail", "fill"])
    def test_single_photo_layout_is_valid(self, orientation, quality):
        photos = [_photo("p1", quality=quality, orientation=orientation)]
        layout = build_text_first_layout(self._magazine(), photos)

        assert violation(layout) is None
        assert len(layout.pages) == 3  # max(3, ceil(1/2.5))
        # the user's only photo must actually appear somewhere
        used = {pid for page in layout.pages for pid in page.images.values()}
        assert "p1" in used

    @pytest.mark.parametrize("orientation", ["landscape", "portrait", "square"])
    @pytest.mark.parametrize("quality", ["hero", "detail", "fill"])
    def test_single_photo_first_page_is_cover(self, orientation, quality):
        photos = [_photo("p1", quality=quality, orientation=orientation)]
        layout = build_text_first_layout(self._magazine(), photos)
        # violation() already enforces cover-category page 0; assert explicitly too
        assert layout.pages[0].templateId in {"mag-01", "mag-13", "mag-20", "p01"}

    def test_two_photos_both_placed(self):
        photos = [
            _photo("p1", quality="hero", orientation="square"),  # no cover fits → mag-20
            _photo("p2", quality="detail", orientation="portrait"),
        ]
        layout = build_text_first_layout(self._magazine(), photos)

        assert violation(layout) is None
        used = {pid for page in layout.pages for pid in page.images.values()}
        assert used == {"p1", "p2"}

    def test_square_photo_falls_back_to_text_only_cover(self):
        # No cover template accepts a square photo, so the cover degrades to the
        # text-only mag-20 and the photo lands on a later image page instead.
        photos = [_photo("p1", quality="hero", orientation="square")]
        layout = build_text_first_layout(self._magazine(), photos)

        assert layout.pages[0].templateId == "mag-20"
        assert layout.pages[0].images == {}
        used = {pid for page in layout.pages for pid in page.images.values()}
        assert "p1" in used

    @pytest.mark.parametrize("orientation", ["landscape", "portrait", "square"])
    @pytest.mark.parametrize("quality", ["hero", "detail", "fill"])
    @pytest.mark.parametrize("n", [1, 2])
    def test_fallback_fills_every_text_slot(self, n, quality, orientation):
        # Every web/PDF template renders a built-in placeholder ("MASASHI WAKUI",
        # "Title/Description", "11/33", …) for an unfilled text slot. The fallback
        # must leave no slot empty, or that placeholder ships into the PDF
        # (architecture review §6.5 + codex P2). Assert full coverage + non-empty.
        photos = [_photo(f"p{i}", quality=quality, orientation=orientation) for i in range(n)]
        layout = build_text_first_layout(self._magazine(), photos)
        for page in layout.pages:
            tpl = registry.get(page.templateId)
            assert tpl is not None
            for slot in tpl["textSlots"]:
                assert slot in page.texts, f"{page.templateId} slot '{slot}' missing → placeholder"
                assert page.texts[slot].strip(), f"{page.templateId} slot '{slot}' empty → placeholder"


class TestClamp:
    def test_clamp_text_trims_to_word_boundary(self):
        out = clamp_text("Snow Light Mountain Days", 20)
        assert len(out) <= 20
        assert out == "Snow Light Mountain"

    def test_clamp_text_hard_cut_when_no_boundary(self):
        assert clamp_text("supercalifragilistic", 10) == "supercalif"

    def test_clamp_text_noop_under_limit(self):
        assert clamp_text("short", 20) == "short"

    def test_clamp_page_texts_makes_over_length_title_pass(self):
        layout = _good_layout()
        # mag-13.title maxChars=30 — overshoot it (mirrors what doubao-lite does)
        layout.pages[0] = Page(
            pageIndex=0, templateId="mag-13", images={"image": "p1"},
            texts={"title": "A spring trip to Kyoto in the early cherry season",
                   "intro": "x" * 45, "issue": "YUJEE · 01",
                   "credit": "AI ARRANGED · YUJEE"},
        )
        assert "title" in (violation(layout) or "")  # fails rule 9 before clamp
        layout.pages = clamp_page_texts(layout.pages)
        assert len(layout.pages[0].texts["title"]) <= 30
        assert violation(layout) is None  # passes after clamp
