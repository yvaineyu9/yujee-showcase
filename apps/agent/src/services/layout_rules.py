"""The 9 business rules from docs/agent/design.md §4.3. Used both after
composing and after applying a chat-edit patch. Returns the first violation
as a human-readable string for the repair prompt, or None if all pass."""

from collections import Counter
from math import ceil

from ..logging_config import get_logger
from ..schemas import AlbumLayoutPlan, Magazine, Page, PhotoAnalysis
from .. import templates as registry

log = get_logger("layout_rules")

# Architecture §6.5 decision 6: photo floor is ≥1. With ≤2 photos the page-count
# target (3) outruns what the photos can fill, so the extra pages use text-only
# templates. Builds bottom out in build_text_first_layout when the model can't.
FEW_PHOTO_MAX = 2

# Text-only spreads used to pad a few-photo album to the page-count target.
_TEXT_ONLY_PAD = ("mag-02", "mag-14")


def _expected_page_count(photo_count: int) -> int:
    raw = ceil(photo_count / 2.5)
    return min(16, max(3, raw))


def clamp_text(text: str, max_chars: int) -> str:
    """Trim text to <= max_chars, preferring the last word boundary within the
    limit (falling back to a hard cut). Only ever shortens."""
    if len(text) <= max_chars:
        return text
    hard = text[:max_chars].rstrip()
    space = hard.rfind(" ")
    if space >= max(1, int(max_chars * 0.6)):
        hard = hard[:space].rstrip()
    return hard


def clamp_texts_for_template(template_id: str, texts: dict[str, str]) -> dict[str, str]:
    """Return a copy of `texts` with each slot trimmed to the template's
    maxChars. Unknown template / slots pass through unchanged."""
    tpl = registry.get(template_id)
    if not tpl:
        return dict(texts)
    out = dict(texts)
    for slot, text in texts.items():
        cons = tpl["textSlots"].get(slot)
        if not cons:
            continue
        max_chars = cons.get("maxChars")
        if isinstance(max_chars, int):
            out[slot] = clamp_text(text, max_chars)
    return out


def clamp_page_texts(pages: list[Page]) -> list[Page]:
    """Deterministically trim each text slot to its template's maxChars.

    Real planning models (e.g. doubao-seed-lite) routinely overshoot a slot's
    maxChars by a few characters and ignore the repair feedback, which would
    otherwise fail Rule 9 and sink the whole generation over a purely cosmetic
    limit. This only ever shortens text and layout_rules enforces no minChars,
    so it can never introduce a new violation."""
    out: list[Page] = []
    for page in pages:
        new_texts = clamp_texts_for_template(page.templateId, page.texts)
        out.append(page.model_copy(update={"texts": new_texts}) if new_texts != page.texts else page)
    return out


def _photo_fits(photo: PhotoAnalysis, constraint: dict) -> bool:
    return (
        photo.orientation in constraint["orientation"]
        and photo.quality in constraint["quality"]
    )


def coerce_image_slots(layout: AlbumLayoutPlan) -> AlbumLayoutPlan:
    """Deterministically force every image slot to satisfy its template's
    orientation/quality constraint — the photo-slot analogue of clamp_text.

    Runs ONLY after the model's repair budget is exhausted: a bottom-line, not
    a replacement for sound assignment. doubao-seed-lite reliably matches
    orientation+quality on 3 photos but mis-assigns on 7-8, and a single repair
    can't recover it, sinking the whole job over a cosmetic mismatch. This makes
    the layout pass §4.3 unconditionally so the album always ships.

    Strategy (only touches placements the model got wrong):
      1. Clear every placement that breaks a per-slot rule — bad slot key,
         dangling photoId, orientation/quality mismatch, same-page duplicate,
         or reuse beyond twice. Valid placements are left exactly as the model
         arranged them.
      2. Re-home each now-unused photo into an empty, compatible slot on a page
         that doesn't already show it (Rule 3: every photo used at least once).
      3. Last resort: a photo with no compatible slot anywhere is dropped from
         photos[] (the album omits it) — it is unused, so nothing references it,
         and a smaller photo set only lowers the Rule 1 page target.

    After coerce, violation() returns None for any structurally sound layout
    (valid page count / cover-first / sequential pageIndex / known templates) —
    the structural rules are the model's job and are left untouched here."""
    by_id: dict[str, PhotoAnalysis] = {p.photoId: p for p in layout.photos}
    page_tpls = [registry.get(page.templateId) for page in layout.pages]
    page_images: list[dict[str, str]] = [dict(page.images) for page in layout.pages]

    used: Counter[str] = Counter()
    on_page: list[set[str]] = [set() for _ in layout.pages]

    # Phase 1 — keep only placements that satisfy every per-slot rule.
    for i, (imgs, tpl) in enumerate(zip(page_images, page_tpls)):
        if tpl is None:
            continue
        for slot in list(imgs.keys()):
            pid = imgs[slot]
            cons = tpl["imageSlots"].get(slot)
            photo = by_id.get(pid)
            keep = (
                cons is not None
                and photo is not None
                and _photo_fits(photo, cons)
                and pid not in on_page[i]
                and used[pid] < 2
            )
            if keep:
                used[pid] += 1
                on_page[i].add(pid)
            else:
                del imgs[slot]

    # Phase 2 — re-home unused photos into empty, compatible slots (Rule 3).
    for pid in [p.photoId for p in layout.photos]:
        if used[pid] > 0:
            continue
        photo = by_id[pid]
        for i, (imgs, tpl) in enumerate(zip(page_images, page_tpls)):
            if tpl is None or pid in on_page[i]:
                continue
            empty = next(
                (
                    s
                    for s, c in tpl["imageSlots"].items()
                    if s not in imgs and _photo_fits(photo, c)
                ),
                None,
            )
            if empty is not None:
                imgs[empty] = pid
                used[pid] += 1
                on_page[i].add(pid)
                break

    # Phase 3 — drop photos that have no compatible slot anywhere.
    survivors = [p for p in layout.photos if used[p.photoId] > 0]
    dropped = [p.photoId for p in layout.photos if used[p.photoId] == 0]
    if dropped:
        log.warning(
            "composing.coerce.dropped_photos",
            photo_ids=dropped[:5],
            count=len(dropped),
        )

    new_pages = [
        page.model_copy(update={"images": imgs}) if imgs != page.images else page
        for page, imgs in zip(layout.pages, page_images)
    ]
    return layout.model_copy(update={"pages": new_pages, "photos": survivors})


def violation(layout: AlbumLayoutPlan) -> str | None:
    pages = layout.pages
    photos = layout.photos
    photo_ids = {p.photoId for p in photos}
    by_id: dict[str, PhotoAnalysis] = {p.photoId: p for p in photos}

    # Rule 1: page count — §4.3 requires pages.length == max(3, ceil(n/2.5))
    # (capped at 16). Strict equality, so too MANY pages is a violation too: a
    # model that pads past the target must hit fallback/repair, not slip through.
    expected = _expected_page_count(len(photos))
    if len(pages) != expected:
        return f"pages count {len(pages)} != required {expected} for {len(photos)} photos"

    # Rule 2: first page must be a cover-category template
    first_tpl = registry.get(pages[0].templateId)
    if not first_tpl:
        return f"page 0 templateId {pages[0].templateId} not in TemplateRegistry"
    if first_tpl["category"] != "cover":
        return f"page 0 templateId {pages[0].templateId} category={first_tpl['category']} (must be cover)"

    # Rule 8: pageIndex strictly 0..N-1
    for expected_idx, page in enumerate(pages):
        if page.pageIndex != expected_idx:
            return f"pageIndex {page.pageIndex} at position {expected_idx} (must be sequential)"

    used_counts: Counter[str] = Counter()
    for page in pages:
        tpl = registry.get(page.templateId)
        if not tpl:
            return f"page {page.pageIndex}: templateId {page.templateId} not in TemplateRegistry"

        # Rule 7: image slot keys subset of template
        for slot in page.images.keys():
            if slot not in tpl["imageSlots"]:
                return f"page {page.pageIndex}: image slot '{slot}' not in template {page.templateId}"
        for slot in page.texts.keys():
            if slot not in tpl["textSlots"]:
                return f"page {page.pageIndex}: text slot '{slot}' not in template {page.templateId}"

        # Rule 5/6 + 4 (single-page dup): every photoId referenced exists; no duplicate within a page
        seen_on_page: set[str] = set()
        for slot, pid in page.images.items():
            if pid not in photo_ids:
                return f"page {page.pageIndex}: photoId {pid} not in photos[]"
            if pid in seen_on_page:
                return f"page {page.pageIndex}: photoId {pid} used twice on same page"
            seen_on_page.add(pid)
            used_counts[pid] += 1

            constraint = tpl["imageSlots"][slot]
            photo = by_id[pid]
            if photo.orientation not in constraint["orientation"]:
                return (
                    f"page {page.pageIndex} slot '{slot}': "
                    f"photo {pid} orientation={photo.orientation} not in "
                    f"{constraint['orientation']}"
                )
            if photo.quality not in constraint["quality"]:
                return (
                    f"page {page.pageIndex} slot '{slot}': "
                    f"photo {pid} quality={photo.quality} not acceptable "
                    f"(slot accepts {constraint['quality']})"
                )

        # Rule 9: text length (we keep it lenient: only the explicit maxChars)
        for slot, text in page.texts.items():
            cons = tpl["textSlots"][slot]
            max_chars = cons.get("maxChars")
            if isinstance(max_chars, int) and len(text) > max_chars:
                return (
                    f"page {page.pageIndex} text '{slot}' length {len(text)} > "
                    f"maxChars {max_chars}"
                )

    # Rule 3: every photoId referenced at least once
    unused = [pid for pid in photo_ids if used_counts[pid] == 0]
    if unused:
        return f"unused photos: {unused[:3]}"

    # Rule 6: single photo reused at most twice
    overused = [pid for pid, c in used_counts.items() if c > 2]
    if overused:
        return f"photos reused more than 2 times: {overused[:3]}"

    return None


# --- few-photo deterministic fallback (architecture §6.5 decision 6) ----------


def _cover_for_photo(photo: PhotoAnalysis | None) -> tuple[str, str]:
    """Return (templateId, imageSlot) for a cover that can hold `photo`. Falls
    back to the text-only cover (mag-20, empty slot) when no image cover fits its
    orientation/quality (e.g. a square or fill-grade photo — no cover accepts
    those)."""
    if photo is not None:
        for tid in registry.COVER_TEMPLATE_IDS:
            tpl = registry.TEMPLATES[tid]
            for slot, cons in tpl["imageSlots"].items():
                if _photo_fits(photo, cons):
                    return tid, slot
    return "mag-20", ""


def _page_slot_for_photo(photo: PhotoAnalysis) -> tuple[str, str] | None:
    """First non-cover (templateId, imageSlot) whose constraint accepts `photo`.
    Across the 21-template registry every orientation×quality combo has at least
    one home, so this only returns None for a photo no template can place."""
    for tid in registry.TEMPLATE_IDS:
        tpl = registry.TEMPLATES[tid]
        if tpl["category"] == "cover":
            continue
        for slot, cons in tpl["imageSlots"].items():
            if _photo_fits(photo, cons):
                return tid, slot
    return None


def _real_texts(
    template_id: str,
    magazine: Magazine,
    page_index: int,
    total_pages: int,
    photo: PhotoAnalysis | None = None,
) -> dict[str, str]:
    """Fill every text slot of `template_id` with real, clamped copy.

    Each web/PDF template renders a built-in placeholder string for any unfilled
    text slot (mag-20's "MASASHI WAKUI", mag-02's "Title/Description", mag-14's
    "11/33", mag-03's "Portrait", …). The few-photo fallback has no model-authored
    copy, so leaving texts={} would ship those placeholders into the finished PDF
    (architecture review §6.5 + codex P2). The agent registry can't tell which
    slots default safely, so we fill them all from real data: the magazine title
    for headings, the subtitle (or title) for body copy, the photo's own
    description for captions, and the page's real folio number for numeric slots.
    """
    tpl = registry.get(template_id)
    if not tpl:
        return {}
    title = magazine.title
    body = magazine.subtitle or magazine.title
    caption = photo.description if photo and photo.description else body
    out: dict[str, str] = {}
    for slot, cons in tpl["textSlots"].items():
        max_chars = cons.get("maxChars", 60)
        s = slot.lower()
        if any(tok in s for tok in ("num", "folio", "vol", "date")):
            # decorative index/folio numbers — use the page's real position
            value = str(total_pages) if "total" in s else str(page_index + 1)
        elif "caption" in s or s in ("intro", "credit"):
            value = caption
        elif (
            any(tok in s for tok in ("title", "heading", "name", "issue", "category"))
            or s in ("plate", "topright", "sidetext")
        ):
            value = title
        else:  # body, quote, subtitle, boxText, items, cells, footnote, …
            value = body
        out[slot] = clamp_text(value, max_chars)
    return out


def build_text_first_layout(magazine: Magazine, photos: list[PhotoAnalysis]) -> AlbumLayoutPlan:
    """Deterministic, §4.3-valid album for the 1-2 photo case (architecture §6.5
    decision 6). Used as the composing fallback when the model can't arrange so
    few photos: a cover, each photo placed exactly once in a constraint-matching
    slot, then padded to the page-count target with text-only spreads. Unlike the
    coerce path, this never drops the user's photo — every photo still appears."""
    pages: list[Page] = []
    placed: set[str] = set()
    expected = _expected_page_count(len(photos))

    cover_photo = photos[0] if photos else None
    cover_id, cover_slot = _cover_for_photo(cover_photo)
    cover_images: dict[str, str] = {}
    if cover_slot and cover_photo is not None:
        cover_images = {cover_slot: cover_photo.photoId}
        placed.add(cover_photo.photoId)
    pages.append(
        Page(
            pageIndex=0,
            templateId=cover_id,
            images=cover_images,
            texts=_real_texts(cover_id, magazine, 0, expected, cover_photo),
        )
    )

    # One page per still-unplaced photo, in a slot matching its constraints.
    for photo in photos:
        if photo.photoId in placed:
            continue
        found = _page_slot_for_photo(photo)
        if found is None:
            continue  # no compatible slot anywhere — leave unused (won't happen for 21 templates)
        tid, slot = found
        pages.append(
            Page(
                pageIndex=len(pages),
                templateId=tid,
                images={slot: photo.photoId},
                texts=_real_texts(tid, magazine, len(pages), expected, photo),
            )
        )
        placed.add(photo.photoId)

    # Pad to the page-count target with text-only spreads.
    while len(pages) < expected:
        tid = _TEXT_ONLY_PAD[len(pages) % len(_TEXT_ONLY_PAD)]
        pages.append(
            Page(
                pageIndex=len(pages),
                templateId=tid,
                images={},
                texts=_real_texts(tid, magazine, len(pages), expected),
            )
        )

    return AlbumLayoutPlan(magazine=magazine, photos=photos, pages=pages)
