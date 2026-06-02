import pytest
from pydantic import ValidationError

from src.schemas import (
    AlbumLayoutPlan,
    CompletedCallback,
    FailedCallback,
    JobError,
    JobUsage,
    LayoutPatchEntry,
    LayoutRequest,
    Magazine,
    Page,
    PhotoAnalysis,
    PhotoIn,
    ProgressCallback,
)


def _photo_analysis(pid: str = "p1", quality: str = "hero", orientation: str = "landscape") -> PhotoAnalysis:
    return PhotoAnalysis(
        photoId=pid,
        description="A simple test photo",
        tags=["sample"],
        quality=quality,  # type: ignore[arg-type]
        orientation=orientation,  # type: ignore[arg-type]
        peopleCount="1",
        scene="outdoor",
        mood="warm",
        timeOfDay=None,
        location=None,
    )


def _layout() -> AlbumLayoutPlan:
    return AlbumLayoutPlan(
        magazine=Magazine(title="Hi", style="warm-film", language="en"),
        photos=[_photo_analysis("p1")],
        pages=[Page(pageIndex=0, templateId="mag-13", images={"image": "p1"}, texts={})],
    )


class TestPhotoFloor:
    """architecture §6.5 decision 6 — photo floor lowered 3 → 1."""

    def test_single_photo_request_accepted(self):
        req = LayoutRequest(
            requestId="r1",
            prompt="a quiet afternoon",
            language="en",
            callbackUrl="http://example.com/cb",
            photos=[PhotoIn(photoId="p1", base64="data:image/jpeg;base64,A", width=800, height=600)],
        )
        assert len(req.photos) == 1

    def test_zero_photos_still_rejected(self):
        with pytest.raises(ValidationError):
            LayoutRequest(
                requestId="r1",
                prompt="hi",
                language="en",
                callbackUrl="http://example.com/cb",
                photos=[],
            )


class TestExtraForbid:
    def test_layout_request_rejects_unknown(self):
        with pytest.raises(ValidationError):
            LayoutRequest(
                requestId="r1",
                prompt="hi",
                language="en",
                callbackUrl="http://example.com/cb",
                photos=[
                    PhotoIn(photoId="p1", base64="data:image/jpeg;base64,A", width=10, height=10),
                    PhotoIn(photoId="p2", base64="data:image/jpeg;base64,A", width=10, height=10),
                    PhotoIn(photoId="p3", base64="data:image/jpeg;base64,A", width=10, height=10),
                ],
                unknown="x",  # type: ignore[call-arg]
            )

    def test_photo_analysis_rejects_unknown(self):
        with pytest.raises(ValidationError):
            PhotoAnalysis(
                photoId="p1",
                description="x",
                tags=[],
                quality="hero",
                orientation="landscape",
                peopleCount="1",
                scene="outdoor",
                mood="warm",
                extra="nope",  # type: ignore[call-arg]
            )

    def test_callback_envelopes_each_have_extra_forbid(self):
        with pytest.raises(ValidationError):
            ProgressCallback(
                event="progress",
                requestId="r1",
                stage="vision",
                progress=0,
                error={"code": "X", "message": "y"},  # type: ignore[call-arg]
            )

        with pytest.raises(ValidationError):
            CompletedCallback(
                event="completed",
                requestId="r1",
                layout=_layout(),
                usage=JobUsage(),
                stage="vision",  # type: ignore[call-arg]
            )

        with pytest.raises(ValidationError):
            FailedCallback(
                event="failed",
                requestId="r1",
                error=JobError(code="X", message="y"),
                layout=_layout(),  # type: ignore[call-arg]
            )


class TestLayoutPatchEntry:
    def test_partial_fields_allowed(self):
        e = LayoutPatchEntry(pageIndex=2, texts={"caption": "ok"})
        assert e.templateId is None
        assert e.images is None
        assert e.texts == {"caption": "ok"}

    def test_unknown_key_rejected(self):
        with pytest.raises(ValidationError):
            LayoutPatchEntry(pageIndex=0, foo="bar")  # type: ignore[call-arg]


class TestPagesBound:
    def test_pages_capped_at_16(self):
        with pytest.raises(ValidationError):
            AlbumLayoutPlan(
                magazine=Magazine(title="H", style="warm-film", language="en"),
                photos=[_photo_analysis("p1")],
                pages=[
                    Page(pageIndex=i, templateId="mag-13", images={"image": "p1"}, texts={})
                    for i in range(17)
                ],
            )
