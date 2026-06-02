"""Deterministic mock planner. Picks real templates from the registry so the
mock layout still parses on the Web side (single source of truth for templateIds
lives in packages/contracts/src/templates.ts). Not guaranteed to satisfy every
business rule — it's a CI smoke surface, not a generation guarantee."""

from ..schemas import AlbumLayoutPlan, LayoutRequest, Magazine, Page, PhotoAnalysis


_TEXT_ONLY_SPREAD = "mag-02"


def _cover_for(orientation: str) -> tuple[str, str]:
    """Returns (templateId, slotName) for a cover that matches the orientation.
    Falls back to text-only cover (mag-20) if nothing fits."""
    if orientation == "landscape":
        return "mag-13", "image"
    if orientation == "portrait":
        return "p01", "image"
    return "mag-20", ""  # text-only cover


def _title_from_prompt(prompt: str) -> str:
    trimmed = prompt.strip() or "Untitled"
    return trimmed[:60]


def plan(req: LayoutRequest, photos: list[PhotoAnalysis]) -> AlbumLayoutPlan:
    title = _title_from_prompt(req.prompt)
    subtitle = "A memoir"
    magazine = Magazine(
        title=title,
        subtitle=subtitle,
        style="warm-film",
        language=req.language,
    )

    pages: list[Page] = []

    cover_photo = photos[0]
    cover_id, cover_slot = _cover_for(cover_photo.orientation)
    cover_texts: dict[str, str] = {}
    if cover_id == "mag-13":
        cover_texts = {
            "title": title,
            "intro": "A memoir made from quiet moments worth keeping.",
            "issue": "YUJEE · 01",
            "credit": "AI ARRANGED · YUJEE",
        }
    elif cover_id == "p01":
        cover_texts = {
            "title": title,
            "body": "A collection of moments worth coming back to.",
            "category": "MEMOIR · YUJEE",
            "vol": "01",
            "date": "2026",
        }
    else:  # mag-20 text-only
        cover_texts = {
            "title": title,
            "boxText": "These photos quietly become a story to revisit.",
            "plate": "PORTFOLIO · YUJEE",
        }
    cover_images = {cover_slot: cover_photo.photoId} if cover_slot else {}
    pages.append(Page(pageIndex=0, templateId=cover_id, images=cover_images, texts=cover_texts))

    # Page 1: text-only spread so we don't have to find a slot match for every
    # photo orientation combo. mag-02's `items` is type=array; we satisfy the
    # str-dict schema by stringifying the list — the mock is a smoke fixture.
    pages.append(
        Page(
            pageIndex=1,
            templateId=_TEXT_ONLY_SPREAD,
            images={},
            texts={"items": "A page of small entries kept from the trip."},
        )
    )

    # Page 2: try to use 1-2 remaining photos with a spread that matches.
    remaining = [p for p in photos if p.photoId != cover_photo.photoId]
    page_two_images: dict[str, str] = {}
    page_two_template = _TEXT_ONLY_SPREAD
    if remaining:
        # mag-12: imageTop square+detail|fill, imageBottom portrait+hero|detail
        square = next((p for p in remaining if p.orientation == "square"), None)
        portrait = next((p for p in remaining if p.orientation == "portrait"), None)
        if square and portrait:
            page_two_template = "mag-12"
            page_two_images = {"imageTop": square.photoId, "imageBottom": portrait.photoId}
            page_two_texts = {"num1": "02", "num2": "03"}
        else:
            page_two_texts = {"items": "Another page kept from the album."}
    else:
        page_two_texts = {"items": "Another page kept from the album."}

    pages.append(
        Page(
            pageIndex=2,
            templateId=page_two_template,
            images=page_two_images,
            texts=page_two_texts,
        )
    )

    return AlbumLayoutPlan(magazine=magazine, photos=photos, pages=pages)
