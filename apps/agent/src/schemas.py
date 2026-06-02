"""Pydantic mirrors of the cross-service contracts in @yujee/contracts.

All schemas use `extra='forbid'` so unknown keys from either AI providers or
Web callers are rejected instead of silently propagated. Callback envelopes
use a discriminated union on `event`.
"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


# ---------- shared enums ------------------------------------------------------

PhotoOrientation = Literal["portrait", "landscape", "square"]
PhotoQuality = Literal["hero", "detail", "fill"]
Language = Literal["zh", "en"]
JobStage = Literal["vision", "writing", "composing"]
ChatRole = Literal["user", "assistant"]
PeopleCount = Literal["0", "1", "2-3", "4+"]
Scene = Literal["indoor", "outdoor", "nature", "city", "interior"]
Mood = Literal["warm", "cool", "sentimental", "energetic", "quiet"]
TimeOfDay = Literal["morning", "day", "evening", "night"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- /v1/layout request -------------------------------------------------


class PhotoIn(_Strict):
    photoId: str = Field(min_length=1)
    base64: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class LayoutRequest(_Strict):
    requestId: str = Field(min_length=1)
    prompt: str = Field(min_length=1, max_length=500)
    language: Language
    callbackUrl: HttpUrl
    photos: list[PhotoIn] = Field(min_length=1, max_length=30)


# ---------- domain ------------------------------------------------------------


class Magazine(_Strict):
    title: str = Field(min_length=1, max_length=60)
    subtitle: str | None = Field(default=None, max_length=100)
    style: str = Field(min_length=1)
    language: Language


class PhotoAnalysis(_Strict):
    """Vision output. Carries the 5 design.md §2.6 extension fields used as
    composing hints. Web-side zod (the canonical @yujee/contracts PhotoAnalysis)
    keeps only photoId/description/tags/quality/orientation and drops the rest,
    so on the chat-edit round-trip the Web sends back a layout without these
    fields. They must therefore be optional on input — vision still populates
    them on output; the contract never requires them."""

    photoId: str = Field(min_length=1)
    description: str
    tags: list[str]
    quality: PhotoQuality
    orientation: PhotoOrientation
    peopleCount: PeopleCount | None = None
    scene: Scene | None = None
    mood: Mood | None = None
    timeOfDay: TimeOfDay | None = None
    location: str | None = None


class Page(_Strict):
    pageIndex: int = Field(ge=0)
    templateId: str = Field(min_length=1)
    images: dict[str, str]
    texts: dict[str, str]


class AlbumLayoutPlan(_Strict):
    magazine: Magazine
    photos: list[PhotoAnalysis]
    pages: list[Page] = Field(min_length=1, max_length=16)


# ---------- callbacks ---------------------------------------------------------

# Web's stub /api/v1/internal/job-progress validates against the *current* TS
# CallbackUsage shape (visionTokens/planningTokens/durationMs). Layout
# completion callback emits this shape to avoid breaking Web. Chat-edit uses
# the richer Usage schema below (no Web consumer yet).
class JobUsage(_Strict):
    visionTokens: int = Field(ge=0, default=0)
    planningTokens: int = Field(ge=0, default=0)
    durationMs: int = Field(ge=0, default=0)


class JobError(_Strict):
    code: str = Field(min_length=1)
    message: str


class ProgressCallback(_Strict):
    event: Literal["progress"]
    requestId: str = Field(min_length=1)
    stage: JobStage
    progress: int = Field(ge=0, le=100)
    message: str | None = None


class CompletedCallback(_Strict):
    event: Literal["completed"]
    requestId: str = Field(min_length=1)
    layout: AlbumLayoutPlan
    usage: JobUsage
    message: str | None = None


class FailedCallback(_Strict):
    event: Literal["failed"]
    requestId: str = Field(min_length=1)
    error: JobError
    message: str | None = None


CallbackEnvelope = Annotated[
    Union[ProgressCallback, CompletedCallback, FailedCallback],
    Field(discriminator="event"),
]


# ---------- /v1/chat-edit -----------------------------------------------------


class ChatHistoryItem(_Strict):
    role: ChatRole
    content: str = Field(min_length=1, max_length=2000)


class ChatEditRequest(_Strict):
    albumId: str = Field(min_length=1)
    currentLayout: AlbumLayoutPlan
    history: list[ChatHistoryItem] = Field(default_factory=list, max_length=20)
    userMessage: str = Field(min_length=1, max_length=500)
    language: Language


class LayoutPatchEntry(_Strict):
    pageIndex: int = Field(ge=0)
    templateId: str | None = None
    images: dict[str, str] | None = None
    texts: dict[str, str] | None = None


class ChatEditUsage(_Strict):
    """Richer usage schema per design.md §10 / §13.4. Used only by chat-edit
    (no Web consumer yet, free to evolve)."""

    durationMs: int = Field(ge=0)
    planningInputTokens: int = Field(ge=0, default=0)
    planningOutputTokens: int = Field(ge=0, default=0)
    repairAttempts: int = Field(ge=0, default=0)
    model: str


class ChatEditResponse(_Strict):
    layoutPatch: list[LayoutPatchEntry] = Field(min_length=1, max_length=16)
    assistantReply: str = Field(min_length=1, max_length=500)
    usage: ChatEditUsage
