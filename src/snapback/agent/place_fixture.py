"""A fixture `PlaceSearcher` for the demo cases: scripted, synthetic, labelled.

`fixtures/demo/<case>/place_retry.json` lists extra unplaced photos and what each retry option
returns for them. Every outcome in it is written by the team to exercise the place desk; none is
measured on a real photo. Photos with no scripted outcome simply do not place, which is the
honest stop. The case runs as a FIXTURE case, so the card and trace carry that chip.
"""

from __future__ import annotations

import json
from pathlib import Path

from snapback.agent.place import SearchOption, SearchOutcome
from snapback.contracts import LocateResult, LocateStatus, PhotoLocation
from snapback.vision.locate.thresholds import Thresholds

FILE_NAME = "place_retry.json"


class FixturePlaceSearcher:
    synthetic = True  # a test and the README rely on this staying true

    def __init__(self, script: dict) -> None:
        if script.get("synthetic") is not True:
            raise ValueError("a fixture place script must say it is synthetic")
        self.label: str = script["label"]
        self.scans: dict[str, str] = dict(script.get("scans", {}))
        self.extra_photos = [
            PhotoLocation.model_validate(p) for p in script.get("extra_photos", [])
        ]
        self._outcomes = script.get("outcomes", {})
        self._default_seconds = float(script.get("default_seconds", 2.0))
        self.calls: list[tuple[str, str]] = []

    @classmethod
    def for_folder(cls, folder: Path) -> FixturePlaceSearcher | None:
        path = folder / FILE_NAME
        return cls(json.loads(path.read_text())) if path.is_file() else None

    def with_extra_photos(self, located: LocateResult | None) -> LocateResult | None:
        """The case's base locate result plus the scripted unplaced photos."""
        if located is None:
            return None
        known = {p.photo_id for p in located.photos}
        extra = [p for p in self.extra_photos if p.photo_id not in known]
        return located.model_copy(update={"photos": [*located.photos, *extra]})

    def search(
        self,
        photo_id: str,
        option: SearchOption,
        claimed_property_id: str | None,
        thresholds: Thresholds,
    ) -> SearchOutcome:
        self.calls.append((photo_id, option.label))
        scripted = self._outcomes.get(photo_id, {}).get(option.label)
        if scripted is None:
            miss = next((p for p in self.extra_photos if p.photo_id == photo_id), None)
            location = miss or PhotoLocation(photo_id=photo_id, status=LocateStatus.NOT_LOCATED)
            return SearchOutcome(location, seconds=self._default_seconds)
        return SearchOutcome(
            PhotoLocation.model_validate(scripted["location"]),
            seconds=float(scripted.get("seconds", self._default_seconds)),
        )
