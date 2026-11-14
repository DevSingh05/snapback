"""A22 (issue #141): place the renter's listing photos in the indexed twins, in a live case.

`LiveLocate` builds lane V's `Locator` once, lazily, from the index under `data/index/<name>`,
the faces already in the Matterport cache (no network here) and a catalog made from the kit's
records. It is used in a live case only. When the vision extra or the index is missing it says
so (`available` is False) and the join falls back to "not indexed", as before.

Rules this module keeps:

- One time budget per case. A photo that is not finished when the budget runs out is
  NOT_LOCATED, never an error and never "located elsewhere". Nothing is cached after that.
- Claimed home first (the Locator does that). With no claimed home the Locator is called once
  with every photo and decides whether they identify a building (`identified_by_scan`); this
  module only reads its answer. Identification alone is never DON'T PAY.
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
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
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
    key: str  # what a cached answer depends on: index, thresholds, matcher


def _default_sweeps(model_id: str):
    """Faces from the Matterport cache only: no network, no key."""
    from snapback.adapters.matterport import LIVE_CACHE, _read_manifest, _safe

    return _read_manifest(model_id, LIVE_CACHE / _safe(model_id)) or []


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
        matcher_factory: Callable[[], object] | None = None,
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
        self._pool: ThreadPoolExecutor | None = None
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
                locator = Locator(index, sweeps, catalog, self._make_matcher(), self._thresholds)
            except Exception as error:  # noqa: BLE001 - extra missing, kit missing, bad files
                log.warning("live locate unavailable (%s)", type(error).__name__)
                return None
            matcher = locator.matcher
            version = getattr(matcher, "version", matcher.name)
            index_hash = hashlib.sha256((self._index_dir / "index.json").read_bytes()).hexdigest()
            key = f"{self._index_name}|{index_hash}|{locator.thresholds!r}|{version}"
            self._ready = _Ready(locator, model_ids, key)
            return self._ready

    def _make_matcher(self):
        if self._matcher_factory is not None:
            return self._matcher_factory()
        # pragma: no cover - needs torch, kornia and the weights
        from snapback.vision.locate.verify import DiskLightGlue

        return DiskLightGlue(feature_dir=self._data_dir / "index" / "features")

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

    def _cache_path(self, ready: _Ready, photos: list[bytes], claimed: str | None) -> Path:
        digest = hashlib.sha256()
        digest.update(f"{ready.key}|{claimed or '-'}".encode())
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
        path = self._cache_path(ready, photos, claimed_property_id)
        cached = self._read_cache(path)
        if cached is not None:
            return LiveOutcome(
                cached.result.model_copy(update={"case_id": case_id}),
                cached.identified_property_id,
                from_cache=True,
            )

        deadline = time.monotonic() + self.budget_s
        blobs = {f"l{number}": blob for number, blob in enumerate(photos, start=1)}

        if claimed_property_id is None:
            # No home claimed: ONE call with every photo, so lane V's identification rules
            # apply (strict bar, two photos must agree, tangled twins identify nothing). A
            # timeout leaves every photo not located.
            def finished(result: LocateResult) -> LiveOutcome:
                found = result.claimed_property_id if result.identified_by_scan else None
                return LiveOutcome(result, found)

            def late(result: LocateResult) -> None:
                # Too late for this case, but a COMPLETE answer: keep it for the next one.
                self._write_cache(path, finished(result))

            whole = self._run(
                ready, case_id, blobs, None, deadline - time.monotonic(), on_late=late
            )
            if whole is None:
                return LiveOutcome(self._not_located(case_id, blobs))
            outcome = finished(whole)
            self._write_cache(path, outcome)
            return outcome

        found_photos: dict[str, PhotoLocation] = {}
        poses: dict[str, Pose] = {}
        versions: list[str] = []
        complete = True
        for photo_id, blob in blobs.items():
            one = self._run(
                ready, case_id, {photo_id: blob}, claimed_property_id, deadline - time.monotonic()
            )
            if one is None:
                complete = False
                found_photos[photo_id] = PhotoLocation(
                    photo_id=photo_id, status=LocateStatus.NOT_LOCATED
                )
                continue
            found_photos[photo_id] = one.photos[0]
            poses.update(one.poses)
            versions.append(one.thresholds_version)

        outcome = LiveOutcome(
            self._merge(
                ready,
                case_id,
                list(found_photos.values()),
                poses,
                claimed_property_id,
                versions[0] if versions else "live-budget",
            )
        )
        if complete:
            self._write_cache(path, outcome)
        return outcome

    def _executor(self) -> ThreadPoolExecutor:
        """One worker for every locate: a timed-out locate cannot pile threads up or race the
        matcher's feature cache. A new locate waits its turn inside its own budget."""
        with self._lock:
            if self._pool is None:
                self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="locate")
            return self._pool

    def _run(
        self,
        ready: _Ready,
        case_id: str,
        blobs: dict[str, bytes],
        claimed: str | None,
        remaining: float,
        on_late: Callable[[LocateResult], None] | None = None,
    ) -> LocateResult | None:
        """The locator on the shared worker, or None if it ran out of time, a photo could not
        be read, or it broke. A run still going at the deadline is left to finish; if it
        completes, `on_late` gets the answer (it is never used for the case that timed out)."""
        if remaining <= 0:
            return None

        def job() -> LocateResult:
            from PIL import Image

            images = {}
            for photo_id, blob in blobs.items():
                with Image.open(io.BytesIO(blob)) as opened:
                    images[photo_id] = opened.convert("RGB")
            return ready.locator.locate(case_id, images, claimed)  # type: ignore[attr-defined]

        future = self._executor().submit(job)
        try:
            return future.result(timeout=remaining)
        except FutureTimeout:
            if not future.cancel() and on_late is not None:
                future.add_done_callback(lambda done: self._late(done, on_late))
            return None
        except Exception as error:  # noqa: BLE001 - a bad photo or a broken matcher
            log.warning("photos could not be placed (%s)", type(error).__name__)
            return None

    @staticmethod
    def _late(done: Future, on_late: Callable[[LocateResult], None]) -> None:
        if done.cancelled() or done.exception() is not None:
            return
        try:
            on_late(done.result())
        except Exception as error:  # noqa: BLE001 - a cache write must never break the worker
            log.warning("late locate result not kept (%s)", type(error).__name__)

    @staticmethod
    def _not_located(case_id: str, blobs: dict[str, bytes]) -> LocateResult:
        return LocateResult(
            case_id=case_id,
            photos=[PhotoLocation(photo_id=p, status=LocateStatus.NOT_LOCATED) for p in blobs],
            thresholds_version="live-budget",
        )

    def _merge(
        self,
        ready: _Ready,
        case_id: str,
        photos: list[PhotoLocation],
        poses: Mapping[str, Pose],
        claimed: str,
        version: str,
    ) -> LocateResult:
        """Per-photo results for a claimed home, joined into one case result."""
        catalog = ready.locator.catalog  # type: ignore[attr-defined]
        candidates = []
        for model_id in sorted(catalog.models_of(claimed) & ready.model_ids):
            mine = [
                p
                for p in photos
                if p.status is LocateStatus.LOCATED_IN_CLAIMED and p.matched_model_id == model_id
            ]
            candidates.append(
                FloorPlanCandidate(
                    property_id=claimed,
                    model_id=model_id,
                    floor_plan=catalog.models[model_id].floor_plan,
                    photos_located=len(mine),
                    total_inliers=sum(p.inliers or 0 for p in mine),
                )
            )
        candidates.sort(key=lambda c: (-c.photos_located, -c.total_inliers, c.model_id))
        chosen = candidates[0] if candidates and candidates[0].photos_located else None
        return LocateResult(
            case_id=case_id,
            photos=photos,
            claimed_property_id=claimed,
            chosen=chosen,
            alternatives=[c for c in candidates if c is not chosen],
            poses=dict(poses),
            thresholds_version=version,
        )
