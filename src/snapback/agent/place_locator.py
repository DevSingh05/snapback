"""`LocatorSearcher`: the live `PlaceSearcher`, over lane V's `Locator.search` (#223).

It does three things and decides nothing: it fetches the photo for a photo id, passes the option
as the Locator names it (`focus_scan` carries the scan's model id, and every call carries a
`deadline_s`), and maps the Locator's result into a `SearchOutcome`. The desk then re-checks the
result against the bars before it counts, so a wrong status from here cannot place a photo or
call it "elsewhere".

The Locator is lane V's (#223): `Locator.search(photo, option, claimed_property_id, *,
scan_model_id=None, deadline_s=None, photo_id="p") -> SearchResult`, where `SearchResult` has
`location` (a full `PhotoLocation`, or None for "stop"), `pose`, `points` (`EvidencePoints`),
`seconds` and `timed_out`. Anything with that shape works; the real class is not imported.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from snapback.agent.place import SearchOption, SearchOutcome
from snapback.contracts import LocateStatus, PhotoLocation
from snapback.vision.locate.thresholds import Thresholds


class LocatorSearcher:
    def __init__(self, locator: Any, photo_for: Callable[[str], Any]) -> None:
        self._locator = locator
        self._photo_for = photo_for  # photo id -> the image; the bytes never leave this process

    def search(
        self,
        photo_id: str,
        option: SearchOption,
        claimed_property_id: str | None,
        thresholds: Thresholds,
        deadline_s: float,
    ) -> SearchOutcome:
        started = time.monotonic()
        # The Locator derives the retrieval breadth from the option itself (it owns
        # `search_thresholds`); `thresholds` is for the desk's own record and its checks.
        result = self._locator.search(
            self._photo_for(photo_id),
            option.kind,
            claimed_property_id,
            scan_model_id=option.scan_model_id,
            deadline_s=deadline_s,
            photo_id=photo_id,
        )
        location = getattr(result, "location", None)
        if location is None:  # a stop, or nothing came back: a miss, not an error
            location = PhotoLocation(photo_id=photo_id, status=LocateStatus.NOT_LOCATED)
        else:
            location = location.model_copy(update={"photo_id": photo_id})
        seconds = getattr(result, "seconds", None)
        return SearchOutcome(
            location,
            pose=getattr(result, "pose", None),
            points=getattr(result, "points", None),
            seconds=float(seconds) if seconds is not None else time.monotonic() - started,
        )
