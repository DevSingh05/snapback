"""A22 (issue #141): place the renter's listing photos in the indexed twins, in a live case.

`LiveLocate` builds lane V's `Locator` once, lazily, from the index under `data/index/<name>`,
the faces already in the Matterport cache (no network here) and a catalog made from the kit's
records. It is used in a live case only. When the vision extra or the index is missing it says
so (`available` is False) and the join falls back to "not indexed", as before.

Rules this module keeps:

- One time budget per case. A photo that is not finished when the budget runs out is
  NOT_LOCATED, never an error and never "located elsewhere". Nothing is cached after that.
- Claimed home first (the Locator does that). With no claimed home, photos that all land in
  one indexed building identify it ("identified by scan"); photos that land in two different
  buildings identify nothing. Identification alone is never DON'T PAY.
- The cache under `data/locate/` is keyed on the photo hashes and the claimed id. An entry is
  read only if it says it came from live data, and is written only by a live run.

Nothing here logs an id, a hash or a value from a record.
"""

import hashlib
import io
import json
import logging
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from snapback.contracts import (
    DataSource,
    FloorPlanCandidate,
    LocateResult,
    LocateStatus,
    PhotoLocation,
    Pose,
    PropertyRecord,
)

log = logging.getLogger("snapback.locate_live")

DEFAULT_BUDGET_S = 25.0
DEFAULT_INDEX = "demo"
CACHE_LABEL = DataSource.LIVE.value


@dataclass(frozen=True)
class LiveOutcome:
    """The placed photos, the building they identify when no home was claimed, and whether
    this came from the cache."""

    result: LocateResult
    identified_property_id: str | None = None
    from_cache: bool = False


@dataclass
class _Ready:
    locator: object
    model_ids: set[str]


def _default_sweeps(model_id: str):
    """Faces from the Matterport cache only: no network, no key."""
    from snapback.adapters.matterport import LIVE_CACHE, _read_manifest, _safe

    return _read_manifest(model_id, LIVE_CACHE / _safe(model_id)) or []


def _default_matcher():  # pragma: no cover - needs torch, kornia and the weights
    from snapback.vision.locate.verify import DiskLightGlue

    return DiskLightGlue(feature_dir=Path("data") / "index" / "features")


def _default_embedder(name: str):  # pragma: no cover - needs torch
    from snapback.vision.embed import Dinov2Embedder

    return Dinov2Embedder()


class LiveLocate:
    def __init__(
        self,
        *,
        data_dir: Path,
        records: Callable[[], Iterable[PropertyRecord]],
        index_name: str = DEFAULT_INDEX,
        sweeps_for: Callable[[str], list] = _default_sweeps,
        matcher_factory: Callable[[], object] = _default_matcher,
        embedder_factory: Callable[[str], object] = _default_embedder,
        budget_s: float = DEFAULT_BUDGET_S,
        thresholds: object | None = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._records = records
        self._index_name = index_name
        self._sweeps_for = sweeps_for
        self._matcher_factory = matcher_factory
        self._embedder_factory = embedder_factory
        self.budget_s = budget_s
        self._thresholds = thresholds
        self._ready: _Ready | None = None
        self._lock = threading.Lock()

    # --- building the locator, once ---------------------------------------------------------

    @property
    def _index_dir(self) -> Path:
        return self._data_dir / "index" / self._index_name

    def _load(self) -> _Ready | None:
        """The locator, or None when the vision extra, the index or the kit is missing."""
        with self._lock:
            if self._ready is not None:
                return self._ready
            if not (self._index_dir / "index.json").is_file():
                return None
            try:
                from snapback.vision.locate.index import LocateIndex
                from snapback.vision.locate.locate import Locator, catalog_from_records

                meta = json.loads((self._index_dir / "index.json").read_text())
                embedder = (
                    None
                    if meta.get("embedder") == "tiny"
                    else self._embedder_factory(meta.get("embedder", ""))
                )
                index = LocateIndex.load(self._index_dir, embedder)
                model_ids = index.model_ids()
                if not model_ids:
                    return None
                catalog = catalog_from_records(list(self._records()))
                sweeps = {m: self._sweeps_for(m) for m in sorted(model_ids)}
                locator = Locator(index, sweeps, catalog, self._matcher_factory(), self._thresholds)
            except Exception as error:  # noqa: BLE001 - extra missing, kit missing, bad files
                log.warning("live locate unavailable (%s)", type(error).__name__)
                return None
            self._ready = _Ready(locator, model_ids)
            return self._ready

    def available(self, claimed_property_id: str | None, claimed_model_ids: list[str]) -> bool:
        """Is there a twin to place photos in? True for a claimed home that is indexed, and
        for no claimed home when the index is not empty."""
        ready = self._load()
        if ready is None:
            return False
        if claimed_property_id is None:
            return True
        return bool(set(claimed_model_ids) & ready.model_ids)

    # --- the cache ---------------------------------------------------------------------------

    def _cache_path(self, photos: list[bytes], claimed: str | None) -> Path:
        digest = hashlib.sha256()
        digest.update(f"{self._index_name}|{claimed or '-'}".encode())
        for blob in photos:
            digest.update(hashlib.sha256(blob).digest())
        return self._data_dir / "locate" / f"{digest.hexdigest()[:40]}.json"

    def _read_cache(self, path: Path) -> LiveOutcome | None:
        try:
            raw = json.loads(path.read_text())
            if raw.get("source") != CACHE_LABEL:  # only live entries are used in a live case
                return None
            return LiveOutcome(
                LocateResult.model_validate(raw["result"]),
                raw.get("identified_property_id"),
                from_cache=True,
            )
        except Exception:  # noqa: BLE001 - missing, torn or old file: just run live
            return None

    def _write_cache(self, path: Path, outcome: LiveOutcome) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            body = {
                "source": CACHE_LABEL,
                "identified_property_id": outcome.identified_property_id,
                "result": outcome.result.model_dump(mode="json"),
            }
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(body))
            temp.replace(path)
        except OSError as error:
            log.warning("locate cache not written (%s)", type(error).__name__)

    # --- one case ----------------------------------------------------------------------------

    def locate(
        self, case_id: str, photos: list[bytes], claimed_property_id: str | None
    ) -> LiveOutcome | None:
        """Place every photo, or None if there is nothing to place them in."""
        ready = self._load()
        if ready is None or not photos:
            return None
        path = self._cache_path(photos, claimed_property_id)
        cached = self._read_cache(path)
        if cached is not None:
            return LiveOutcome(
                cached.result.model_copy(update={"case_id": case_id}),
                cached.identified_property_id,
                from_cache=True,
            )

        deadline = time.monotonic() + self.budget_s
        found: dict[str, PhotoLocation] = {}
        poses: dict[str, Pose] = {}
        versions: list[str] = []
        complete = True
        for number, blob in enumerate(photos, start=1):
            photo_id = f"l{number}"
            remaining = deadline - time.monotonic()
            one = self._one(ready, case_id, photo_id, blob, claimed_property_id, remaining)
            if one is None:
                complete = False
                found[photo_id] = PhotoLocation(photo_id=photo_id, status=LocateStatus.NOT_LOCATED)
                continue
            found[photo_id] = one.photos[0]
            poses.update(one.poses)
            versions.append(one.thresholds_version)

        outcome = self._assemble(
            ready,
            case_id,
            list(found.values()),
            poses,
            claimed_property_id,
            versions[0] if versions else "live-budget",
        )
        if complete:
            self._write_cache(path, outcome)
        return outcome

    def _one(
        self,
        ready: _Ready,
        case_id: str,
        photo_id: str,
        blob: bytes,
        claimed: str | None,
        remaining: float,
    ) -> LocateResult | None:
        """One photo through the locator on a worker thread, or None if it ran out of time,
        could not be read, or broke. A worker still running at the deadline is left to finish
        by itself; its answer is dropped."""
        if remaining <= 0:
            return None
        box: list[LocateResult] = []

        def work() -> None:
            try:
                from PIL import Image

                with Image.open(io.BytesIO(blob)) as opened:
                    image = opened.convert("RGB")
                box.append(ready.locator.locate(case_id, {photo_id: image}, claimed))  # type: ignore[attr-defined]
            except Exception as error:  # noqa: BLE001 - a bad photo or a broken matcher
                log.warning("a photo could not be placed (%s)", type(error).__name__)

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        worker.join(remaining)
        if worker.is_alive() or not box:
            return None
        return box[0]

    def _assemble(
        self,
        ready: _Ready,
        case_id: str,
        photos: list[PhotoLocation],
        poses: Mapping[str, Pose],
        claimed: str | None,
        version: str,
    ) -> LiveOutcome:
        catalog = ready.locator.catalog  # type: ignore[attr-defined]
        identified: str | None = None
        if claimed is None:
            # No home was claimed, so "elsewhere" has no meaning here (ruling, Sat 03:25).
            # Photos that land in one indexed building identify it; two buildings identify
            # nothing, and a photo that landed nowhere is not located.
            placed = [
                p
                for p in photos
                if p.status in (LocateStatus.LOCATED_IN_CLAIMED, LocateStatus.LOCATED_ELSEWHERE)
                and p.matched_property_id
            ]
            owners = {p.matched_property_id for p in placed}
            if len(owners) == 1:
                identified = next(iter(owners))
            photos = [
                p.model_copy(update={"status": LocateStatus.LOCATED_IN_CLAIMED})
                if identified and p in placed
                else PhotoLocation(photo_id=p.photo_id, status=LocateStatus.NOT_LOCATED)
                for p in photos
            ]
        target = claimed or identified
        if claimed is None:
            kept = {p.photo_id for p in photos if p.status is LocateStatus.LOCATED_IN_CLAIMED}
            poses = {k: v for k, v in poses.items() if k in kept}

        candidates = []
        if target:
            for model_id in sorted(catalog.models_of(target) & ready.model_ids):
                mine = [
                    p
                    for p in photos
                    if p.status is LocateStatus.LOCATED_IN_CLAIMED
                    and p.matched_model_id == model_id
                ]
                candidates.append(
                    FloorPlanCandidate(
                        property_id=target,
                        model_id=model_id,
                        floor_plan=catalog.models[model_id].floor_plan,
                        photos_located=len(mine),
                        total_inliers=sum(p.inliers or 0 for p in mine),
                    )
                )
            candidates.sort(key=lambda c: (-c.photos_located, -c.total_inliers, c.model_id))
        chosen = candidates[0] if candidates and candidates[0].photos_located else None
        result = LocateResult(
            case_id=case_id,
            photos=photos,
            claimed_property_id=target,
            chosen=chosen,
            alternatives=[c for c in candidates if c is not chosen],
            poses=dict(poses),
            thresholds_version=version,
        )
        return LiveOutcome(result, identified)
