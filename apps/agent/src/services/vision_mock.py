from ..schemas import LayoutRequest, PhotoAnalysis


_QUALITY_CYCLE = ("hero", "detail", "fill")


def _orientation(width: int, height: int) -> str:
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"


def analyze(req: LayoutRequest) -> list[PhotoAnalysis]:
    results: list[PhotoAnalysis] = []
    for idx, photo in enumerate(req.photos):
        if idx == 0:
            quality = "hero"
        else:
            quality = _QUALITY_CYCLE[1 + ((idx - 1) % 2)]
        results.append(
            PhotoAnalysis(
                photoId=photo.photoId,
                description="A moment from your story",
                tags=["family", "warm"],
                quality=quality,  # type: ignore[arg-type]
                orientation=_orientation(photo.width, photo.height),  # type: ignore[arg-type]
                peopleCount="1",
                scene="outdoor",
                mood="warm",
                timeOfDay="day",
                location=None,
            )
        )
    return results
