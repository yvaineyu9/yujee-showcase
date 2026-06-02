"""Python mirror of packages/contracts/src/templates.ts.

Single source of truth lives in TypeScript; this file is a hand-mirrored copy
used by the composing prompt and Agent-side validation. If the TS registry
changes, regenerate this file (the structures are flat enough that a manual
diff is sufficient for the 21-template registry).
"""

from typing import Literal, TypedDict


TemplateCategory = Literal["cover", "spread", "single", "grid", "closing"]


class ImageSlot(TypedDict):
    orientation: list[str]  # subset of portrait / landscape / square
    quality: list[str]      # subset of hero / detail / fill


class TextSlot(TypedDict, total=False):
    type: str               # array / caption / heading / label / meta / paragraph / quote
    minChars: int
    maxChars: int


class TemplateDef(TypedDict):
    id: str
    category: TemplateCategory
    imageSlots: dict[str, ImageSlot]
    textSlots: dict[str, TextSlot]


def _t(category: TemplateCategory,
       image_slots: dict[str, ImageSlot],
       text_slots: dict[str, TextSlot]) -> TemplateDef:
    return {"id": "", "category": category, "imageSlots": image_slots, "textSlots": text_slots}


TEMPLATES: dict[str, TemplateDef] = {
    "mag-01": _t("cover",
        {"image": {"orientation": ["landscape"], "quality": ["hero", "detail"]}},
        {
            "heading":  {"type": "heading", "minChars": 4,  "maxChars": 12},
            "sideText": {"type": "label",   "minChars": 15, "maxChars": 30},
            "caption1": {"type": "caption", "minChars": 40, "maxChars": 80},
            "caption2": {"type": "caption", "minChars": 40, "maxChars": 80},
            "folio":    {"type": "meta",    "minChars": 2,  "maxChars": 2},
        }),
    "mag-02": _t("spread",
        {},
        {
            "items":  {"type": "array", "maxChars": 240},
            "folio":  {"type": "meta",  "minChars": 2, "maxChars": 2},
        }),
    "mag-03": _t("single",
        {"image": {"orientation": ["portrait"], "quality": ["hero", "detail"]}},
        {
            "category": {"type": "label",   "minChars": 5,  "maxChars": 15},
            "location": {"type": "label",   "minChars": 10, "maxChars": 20},
            "caption":  {"type": "caption", "minChars": 0,  "maxChars": 60},
            "folio":    {"type": "meta",    "minChars": 2,  "maxChars": 2},
        }),
    "mag-04": _t("spread",
        {
            "image1": {"orientation": ["landscape"], "quality": ["hero", "detail"]},
            "image2": {"orientation": ["portrait"],  "quality": ["detail", "fill"]},
            "image3": {"orientation": ["square"],    "quality": ["detail", "fill"]},
        },
        {
            "caption1": {"type": "caption", "minChars": 40, "maxChars": 80},
            "caption2": {"type": "caption", "minChars": 40, "maxChars": 80},
            "dateNum":  {"type": "meta",    "minChars": 5,  "maxChars": 5},
            "folio":    {"type": "meta",    "minChars": 2,  "maxChars": 2},
        }),
    "mag-05": _t("single",
        {"image": {"orientation": ["landscape"], "quality": ["hero", "detail"]}},
        {
            "title":    {"type": "heading",   "minChars": 10, "maxChars": 25},
            "topRight": {"type": "label",     "minChars": 10, "maxChars": 20},
            "caption":  {"type": "paragraph", "minChars": 60, "maxChars": 120},
            "folio":    {"type": "meta",      "minChars": 2,  "maxChars": 2},
        }),
    "mag-06": _t("single",
        {"image": {"orientation": ["portrait"], "quality": ["hero", "detail"]}},
        {
            "category": {"type": "label", "minChars": 5, "maxChars": 15},
            "folio":    {"type": "meta",  "minChars": 2, "maxChars": 2},
        }),
    "mag-07": _t("spread",
        {
            "imageTop":  {"orientation": ["landscape"], "quality": ["detail", "fill"]},
            "imageMain": {"orientation": ["portrait"],  "quality": ["hero", "detail"]},
        },
        {
            "caption1": {"type": "caption", "minChars": 40, "maxChars": 80},
            "caption2": {"type": "caption", "minChars": 40, "maxChars": 80},
            "caption3": {"type": "caption", "minChars": 40, "maxChars": 80},
            "title":    {"type": "heading", "minChars": 6,  "maxChars": 16},
            "folio":    {"type": "meta",    "minChars": 2,  "maxChars": 2},
        }),
    "mag-08": _t("single",
        {"image": {"orientation": ["portrait"], "quality": ["hero", "detail"]}},
        {
            "dateNum":  {"type": "meta",    "minChars": 5,  "maxChars": 5},
            "caption1": {"type": "caption", "minChars": 40, "maxChars": 80},
            "caption2": {"type": "caption", "minChars": 40, "maxChars": 80},
            "title":    {"type": "heading", "minChars": 4,  "maxChars": 10},
            "subtitle": {"type": "label",   "minChars": 10, "maxChars": 25},
            "folio":    {"type": "meta",    "minChars": 2,  "maxChars": 2},
        }),
    "mag-09": _t("spread",
        {
            "imageTop":  {"orientation": ["landscape"], "quality": ["detail", "fill"]},
            "imageMain": {"orientation": ["square"],    "quality": ["hero", "detail"]},
        },
        {
            "quote":    {"type": "quote",   "minChars": 30, "maxChars": 60},
            "caption1": {"type": "caption", "minChars": 40, "maxChars": 80},
            "title":    {"type": "heading", "minChars": 6,  "maxChars": 16},
            "caption2": {"type": "caption", "minChars": 40, "maxChars": 80},
            "caption3": {"type": "caption", "minChars": 40, "maxChars": 80},
            "folio":    {"type": "meta",    "minChars": 2,  "maxChars": 2},
        }),
    "mag-10": _t("grid",
        {
            "cells[0].image": {"orientation": ["square"], "quality": ["detail", "fill"]},
            "cells[1].image": {"orientation": ["square"], "quality": ["detail", "fill"]},
            "cells[2].image": {"orientation": ["square"], "quality": ["detail", "fill"]},
            "cells[3].image": {"orientation": ["square"], "quality": ["detail", "fill"]},
        },
        {
            "cells": {"type": "array", "maxChars": 160},
            "folio": {"type": "meta",  "minChars": 2, "maxChars": 2},
        }),
    "mag-11": _t("single",
        {"image": {"orientation": ["portrait"], "quality": ["hero", "detail"]}},
        {
            "title":    {"type": "heading", "minChars": 6,  "maxChars": 16},
            "plate":    {"type": "label",   "minChars": 10, "maxChars": 20},
            "caption2": {"type": "caption", "minChars": 40, "maxChars": 80},
            "folio":    {"type": "meta",    "minChars": 2,  "maxChars": 2},
        }),
    "mag-12": _t("spread",
        {
            "imageTop":    {"orientation": ["square"],   "quality": ["detail", "fill"]},
            "imageBottom": {"orientation": ["portrait"], "quality": ["hero", "detail"]},
        },
        {
            "num1":  {"type": "meta", "minChars": 2, "maxChars": 2},
            "num2":  {"type": "meta", "minChars": 2, "maxChars": 2},
            "folio": {"type": "meta", "minChars": 2, "maxChars": 2},
        }),
    "mag-13": _t("cover",
        {"image": {"orientation": ["landscape"], "quality": ["hero", "detail"]}},
        {
            "title":    {"type": "heading",   "minChars": 10, "maxChars": 30},
            "intro":    {"type": "paragraph", "minChars": 40, "maxChars": 80},
            "caption1": {"type": "caption",   "minChars": 40, "maxChars": 80},
            "caption2": {"type": "caption",   "minChars": 40, "maxChars": 80},
            "issue":    {"type": "label",     "minChars": 10, "maxChars": 15},
            "credit":   {"type": "label",     "minChars": 15, "maxChars": 30},
            "folio":    {"type": "meta",      "minChars": 2,  "maxChars": 2},
        }),
    "mag-14": _t("spread",
        {},
        {
            "bigNum":        {"type": "meta",      "minChars": 2,  "maxChars": 2},
            "bigNumTotal":   {"type": "meta",      "minChars": 2,  "maxChars": 2},
            "body":          {"type": "paragraph", "minChars": 40, "maxChars": 80},
            "subtitleQuote": {"type": "quote",     "minChars": 20, "maxChars": 50},
            "bracketQuote":  {"type": "quote",     "minChars": 40, "maxChars": 80},
            "footnote":      {"type": "caption",   "minChars": 30, "maxChars": 60},
            "folio":         {"type": "meta",      "minChars": 2,  "maxChars": 2},
        }),
    "mag-15": _t("spread",
        {
            "imagePerson": {"orientation": ["portrait"],  "quality": ["hero", "detail"]},
            "imageRoad":   {"orientation": ["landscape"], "quality": ["detail", "fill"]},
        },
        {
            "body":  {"type": "paragraph", "minChars": 30, "maxChars": 60},
            "title": {"type": "heading",   "minChars": 6,  "maxChars": 16},
            "date":  {"type": "label",     "minChars": 10, "maxChars": 20},
            "folio": {"type": "meta",      "minChars": 2,  "maxChars": 2},
        }),
    "mag-16": _t("spread",
        {
            "imageTiny":   {"orientation": ["portrait"],  "quality": ["fill"]},
            "imagePerson": {"orientation": ["landscape"], "quality": ["hero", "detail"]},
            "imageHarbor": {"orientation": ["landscape"], "quality": ["detail", "fill"]},
        },
        {
            "caption1": {"type": "caption", "minChars": 40, "maxChars": 80},
            "caption2": {"type": "caption", "minChars": 40, "maxChars": 80},
            "caption3": {"type": "caption", "minChars": 40, "maxChars": 80},
            "quote":    {"type": "quote",   "minChars": 30, "maxChars": 60},
            "folio":    {"type": "meta",    "minChars": 2,  "maxChars": 2},
        }),
    "mag-17": _t("closing",
        {"image": {"orientation": ["portrait"], "quality": ["hero", "detail"]}},
        {
            "name1": {"type": "label", "minChars": 8, "maxChars": 20},
            "name2": {"type": "label", "minChars": 8, "maxChars": 20},
            "folio": {"type": "meta",  "minChars": 2, "maxChars": 2},
        }),
    "mag-18": _t("spread",
        {
            "imageLeft":  {"orientation": ["portrait"], "quality": ["detail", "fill"]},
            "imageRight": {"orientation": ["portrait"], "quality": ["detail", "fill"]},
        },
        {
            "numLeft":      {"type": "meta",    "minChars": 2,  "maxChars": 2},
            "numRight":     {"type": "meta",    "minChars": 2,  "maxChars": 2},
            "captionLeft":  {"type": "caption", "minChars": 40, "maxChars": 80},
            "captionRight": {"type": "caption", "minChars": 40, "maxChars": 80},
            "subtitle":     {"type": "quote",   "minChars": 30, "maxChars": 60},
            "folio":        {"type": "meta",    "minChars": 2,  "maxChars": 2},
        }),
    "mag-19": _t("single",
        {"image": {"orientation": ["landscape"], "quality": ["hero", "detail"]}},
        {
            "intro":        {"type": "paragraph", "minChars": 40, "maxChars": 80},
            "captionLeft":  {"type": "caption",   "minChars": 40, "maxChars": 80},
            "captionRight": {"type": "caption",   "minChars": 40, "maxChars": 80},
            "quote":        {"type": "quote",     "minChars": 30, "maxChars": 60},
            "folio":        {"type": "meta",      "minChars": 2,  "maxChars": 2},
        }),
    "mag-20": _t("cover",
        {},
        {
            "boxText": {"type": "paragraph", "minChars": 15, "maxChars": 40},
            "title":   {"type": "heading",   "minChars": 10, "maxChars": 30},
            "plate":   {"type": "label",     "minChars": 10, "maxChars": 25},
            "folio":   {"type": "meta",      "minChars": 2,  "maxChars": 2},
        }),
    "p01": _t("cover",
        {"image": {"orientation": ["portrait"], "quality": ["hero", "detail"]}},
        {
            "title":    {"type": "heading",   "minChars": 8,  "maxChars": 20},
            "body":     {"type": "paragraph", "minChars": 40, "maxChars": 80},
            "category": {"type": "label",     "minChars": 10, "maxChars": 20},
            "vol":      {"type": "meta",      "minChars": 2,  "maxChars": 4},
            "date":     {"type": "meta",      "minChars": 5,  "maxChars": 10},
        }),
}

# Fill in id field
for _tid, _tpl in TEMPLATES.items():
    _tpl["id"] = _tid


COVER_TEMPLATE_IDS = sorted(tid for tid, t in TEMPLATES.items() if t["category"] == "cover")
TEMPLATE_IDS = sorted(TEMPLATES.keys())


def is_known(template_id: str) -> bool:
    return template_id in TEMPLATES


def get(template_id: str) -> TemplateDef | None:
    return TEMPLATES.get(template_id)


def summarize_for_prompt() -> str:
    """Compact human-readable registry dump for composing/chat-edit system prompt."""
    lines = []
    for tid in TEMPLATE_IDS:
        tpl = TEMPLATES[tid]
        if tpl["imageSlots"]:
            img = "; ".join(
                f"{k}(orient={'|'.join(v['orientation'])},quality={'|'.join(v['quality'])})"
                for k, v in tpl["imageSlots"].items()
            )
        else:
            img = "(text-only)"
        txt = ", ".join(
            f"{k}<={v.get('maxChars','?')}c"
            for k, v in tpl["textSlots"].items()
            if v.get("type") != "meta"
        )
        lines.append(f"- {tid} [{tpl['category']}] images: {img} | texts: {txt}")
    return "\n".join(lines)
