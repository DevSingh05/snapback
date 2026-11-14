"""`LocatorSearcher`: the live `PlaceSearcher`, over lane V's `Locator.search` (#223).

It does three things and decides nothing: it fetches the photo for a photo id, passes the option
as the Locator names it (`focus_scan` carries the scan's model id, and every call carries a
`deadline_s`), and maps the Locator's result into a `SearchOutcome`. The desk then re-checks the
result against the bars before it counts, so a wrong status from here cannot place a photo or
call it "elsewhere".

The Locator is duck-typed: anything with
`search(photo, option, claimed_property_id, *, scan_model_id=None, deadline_s=None)` returning an
object with `status`, `inliers`, `inlier_ratio`, `spread`, `rival_ratio`, `bar_failed`,
`model_id`, `matched_model_id`, `matched_property_id`, `room_label`, `pose`, `points` and
`seconds` (any may be missing) works. `points` is a list of (ax, ay, bx, by) pairs normalised to
0..1; at most 48 are kept.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from snapback.agent.place import SearchOption, SearchOutcome
from snapback.contracts import EvidencePoints, LocateStatus, PhotoLocation
from snapback.vision.locate.thresholds import Thresholds

MAX_POINTS = 48


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
        )
        status = getattr(result, "status", None) or LocateStatus.NOT_LOCATED
        location = PhotoLocation(
            photo_id=photo_id,
            status=status,
            model_id=getattr(result, "model_id", None),
            pano_id=getattr(result, "sweep_id", None),
            inliers=getattr(result, "inliers", None),
            inlier_ratio=getattr(result, "inlier_ratio", None),
            matched_model_id=getattr(result, "matched_model_id", None),
            matched_property_id=getattr(result, "matched_property_id", None),
            room_label=getattr(result, "room_label", None),
            spread=getattr(result, "spread", None),
            rival_ratio=getattr(result, "rival_ratio", None),
            bar_failed=getattr(result, "bar_failed", None),
        )
        seconds = getattr(result, "seconds", None)
        return SearchOutcome(
            location,
            pose=getattr(result, "pose", None),
            points=_points(getattr(result, "points", None), getattr(result, "n_points", None)),
            seconds=float(seconds) if seconds is not None else time.monotonic() - started,
        )


def _points(raw: Any, n_total: int | None = None) -> EvidencePoints | None:
    if not raw:
        return None
    pairs = [tuple(float(v) for v in p) for p in raw if len(p) == 4]
    return EvidencePoints(
        n_total=max(n_total or 0, len(pairs)),
        sampled=pairs[:MAX_POINTS],  # type: ignore[arg-type]
    )
