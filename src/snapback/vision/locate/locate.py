"""Place listing photos in the indexed twins: retrieve, verify, pose. Output: `LocateResult`.

For each photo:

1. Retrieve the closest views over every indexed building, plus the closest views in the
   claimed property's own twins (so the claimed building is always tried).
2. Verify each candidate face with the matcher and a RANSAC homography. The claimed property's
   twins are verified first and the best face with enough inliers places the photo there. Only
   when none does, another building places it, and only on a stricter bar (more inliers,
   spread over the photo); otherwise it is not placed.
3. Status: placed in a twin of the claimed property is `located_in_claimed`; placed in any other
   building is `located_elsewhere`, with that building's ids; not placed is `not_located`, or
   `not_indexed` when the claimed property has no twin in the index.
4. Pose: the sweep's position, and the camera rotation read off the homography, in the model
   frame (three.js camera quaternion, see `cube.py` for the face frames).

The floor-plan candidates (`chosen`, `alternatives`) are the claimed property's twins, ranked
by photos placed, then inliers. Model units per floor plan: a match claims "this building, this
floor plan", never a unit number.
"""

import logging
import math
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, fields, replace
from functools import lru_cache

import numpy as np
from PIL import Image, ImageOps

from snapback.adapters.matterport import Sweep
from snapback.contracts import (
    EvidencePoints,
    FloorPlanCandidate,
    LocateResult,
    LocateStatus,
    PhotoLocation,
    Pose,
    PropertyRecord,
)
from snapback.vision.embed import unit
from snapback.vision.locate.cube import SIDE_FACES, face_basis, face_intrinsics, intrinsics
from snapback.vision.locate.geometry import (
    camera_quaternion,
    matrix_from_quaternion,
    rotation_from_homography,
    viewer_yaw_pitch,
)
from snapback.vision.locate.index import LocateIndex
from snapback.vision.locate.thresholds import Thresholds, load_thresholds
from snapback.vision.locate.verify import FEATURE_KEY, Matcher, Verification, verify

log = logging.getLogger(__name__)

_EXIF_IFD = 0x8769
_FOCAL_35MM = 0xA405


@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    property_id: str
    floor_plan: str | None = None
    rooms: Mapping[str, str | None] = field(default_factory=dict)  # sweep id -> room label


class Catalog:
    """Which property and floor plan each twin belongs to, and the room of each sweep."""

    def __init__(self, models: Iterable[ModelInfo]) -> None:
        self.models = {model.model_id: model for model in models}

    def property_of(self, model_id: str) -> str | None:
        info = self.models.get(model_id)
        return info.property_id if info else None

    def models_of(self, property_id: str | None) -> set[str]:
        return {m.model_id for m in self.models.values() if m.property_id == property_id}

    def room(self, model_id: str, sweep_id: str) -> str | None:
        info = self.models.get(model_id)
        return info.rooms.get(sweep_id) if info else None


def catalog_from_records(
    records: Iterable[PropertyRecord],
    rooms: Callable[[str], Mapping[str, str | None]] | None = None,
) -> Catalog:
    """A catalog from lane D's PropertyRecords (model ids and floor plans, in the same order)."""
    models = []
    for record in records:
        for number, model_id in enumerate(record.model_ids):
            plan = record.floor_plans[number] if number < len(record.floor_plans) else None
            models.append(
                ModelInfo(model_id, record.property_id, plan, rooms(model_id) if rooms else {})
            )
    return Catalog(models)


def photo_hfov(image: Image.Image, default: float) -> float:
    """Horizontal field of view from the 35 mm equivalent focal length in EXIF, if any."""
    try:
        focal = image.getexif().get_ifd(_EXIF_IFD).get(_FOCAL_35MM)
    except Exception:  # noqa: BLE001 - EXIF is untrusted input
        focal = None
    if not focal:
        return default
    long_side = 36.0 if image.width >= image.height else 24.0
    return math.degrees(2 * math.atan(long_side / (2 * float(focal))))


_RING = (1, 2, 3, 4)  # side faces, left to right: each meets its neighbours at a seam


def seam_neighbours(hits: list, top: int = 2) -> list:
    """For the `top` best hits on a side face, the side faces either side of it in the same
    sweep: a photo looking across a seam splits its matches between two faces."""
    from snapback.vision.locate.index import Entry, Hit

    floor = min((h.score for h in hits), default=0.0)
    out = []
    for hit in hits[:top]:
        entry = hit.entry
        if entry.face not in _RING:
            continue
        at = _RING.index(entry.face)
        for neighbour in (_RING[at - 1], _RING[(at + 1) % len(_RING)]):
            out.append(Hit(Entry(entry.model_id, entry.sweep_id, neighbour, "face"), floor - 1e-3))
    return out


# --- E2a: the place sub-agent's retry options ----------------------------------------------------

SEARCH_OPTIONS = ("focus_scan", "wider_index", "deeper_claimed", "stop")
# The only thresholds a retry may change: how many candidates are verified, never a bar.
RETRIEVAL_FIELDS = frozenset({"top_k", "top_k_claimed"})


def retrieve_only(thresholds: Thresholds, **changes) -> Thresholds:
    """A copy of the thresholds that differs in retrieval only. Any bar change is refused, so a
    retry can look at more candidates but never accept weaker evidence."""
    known = {f.name for f in fields(thresholds)}
    bad = sorted(set(changes) - RETRIEVAL_FIELDS)
    if bad:
        kind = "unknown" if set(bad) - known else "a bar"
        raise ValueError(f"a search option changes retrieval only, not {kind}: {', '.join(bad)}")
    return replace(thresholds, **changes)


def search_thresholds(base: Thresholds, option: str) -> Thresholds:
    """The thresholds a retry option runs with (the A-lane place step calls this): wider_index
    verifies twice the candidates over every building (top_k 6 -> 12), deeper_claimed twice the
    claimed building's faces (top_k_claimed 48 -> 96); focus_scan and stop keep the base."""
    if option == "wider_index":
        return retrieve_only(base, top_k=2 * base.top_k)
    if option == "deeper_claimed":
        return retrieve_only(base, top_k_claimed=2 * base.top_k_claimed)
    if option in ("focus_scan", "stop", "base"):
        return base
    raise ValueError(f"unknown search option {option!r}; use one of {SEARCH_OPTIONS}")


@dataclass(frozen=True)
class SearchResult:
    """One retry for one photo, as locate() would report it. `location` is a full PhotoLocation
    (status, inliers, ratio, spread, rival_ratio, bar_failed, matched ids, room); `pose` and
    `points` are set when the photo is placed. No pixels."""

    option: str
    location: PhotoLocation | None = None  # None for "stop": nothing was searched
    pose: Pose | None = None
    points: EvidencePoints | None = None
    identified_property_id: str | None = None  # no claimed home: the home the photo names
    verified: int = 0  # how many faces were verified
    seconds: float = 0.0
    timed_out: bool = False  # the deadline passed before every candidate was verified

    @property
    def status(self) -> LocateStatus | None:
        return self.location.status if self.location else None

    @property
    def model_id(self) -> str | None:
        return self.location.matched_model_id if self.location else None

    @property
    def sweep_id(self) -> str | None:
        return self.location.pano_id if self.location else None

    @property
    def inliers(self) -> int | None:
        return self.location.inliers if self.location else None


@dataclass(frozen=True)
class _Placement:
    model_id: str
    sweep: Sweep
    face: int
    check: Verification


# Bars that mark a doubtful match: the flip must never override them.
_NO_FLIP_BARS = frozenset({"ambiguity", "spread"})


@dataclass(frozen=True)
class _PlaceOutcome:
    placed: "_Placement | None"
    bar_failed: str | None  # "inliers", "ratio", "spread" or "ambiguity" when not placed
    rival_ratio: float | None  # best rival building's inliers over the claimed match's


def passes_strict(c: Verification, t: Thresholds) -> bool:
    """The strict bar: what naming a home from the photos alone, or placing a photo in another
    building (a route to DON'T PAY), needs. More inliers and spread than the claimed bar, and its
    own inlier ratio: a regenerated (AI-edited) photo can clear the counts with half its matches
    inconsistent, and named the wrong building that way (#10)."""
    return (
        c.inliers >= t.elsewhere_min_inliers
        and c.ratio >= max(t.min_inlier_ratio, t.elsewhere_min_ratio)
        and c.spread >= t.elsewhere_min_spread
    )


def loose(c: Verification, t: Thresholds) -> bool:
    """A near miss on the strict bar: enough inliers and spread to name a building, but fewer
    than elsewhere_min_ratio of the matches consistent (and at least the claimed ratio). The
    photo is not placed; it is reported as matching only loosely."""
    return (
        c.inliers >= t.elsewhere_min_inliers
        and c.spread >= t.elsewhere_min_spread
        and t.min_inlier_ratio <= c.ratio < t.elsewhere_min_ratio
    )


def _failed_bar(top: Verification | None, t: Thresholds) -> str:
    """Which claimed bar the strongest candidate missed (a photo that placed nowhere)."""
    if top is None or top.inliers < t.min_inliers:
        return "inliers"
    if top.ratio < t.min_inlier_ratio:
        return "ratio"
    if top.spread < t.claimed_min_spread:
        return "spread"
    return "inliers"


MAX_POINTS = 48


def evidence_points(placed: "_Placement", photo_size, face_size) -> EvidencePoints | None:
    """Up to MAX_POINTS inlier pairs, evenly sampled, each coordinate normalised to 0..1:
    (ad x, ad y, scan x, scan y). n_total is every inlier."""
    pairs = placed.check.pairs
    if pairs is None or len(pairs) == 0:
        return None
    keep = sorted({round(i) for i in np.linspace(0, len(pairs) - 1, min(MAX_POINTS, len(pairs)))})
    scale = np.array([photo_size[0], photo_size[1], face_size[0], face_size[1]], dtype=float)
    sample = np.clip(pairs[keep] / scale, 0.0, 1.0)
    return EvidencePoints(
        n_total=int(placed.check.inliers),
        sampled=[tuple(round(float(v), 4) for v in row) for row in sample],
    )


class _DeadlineExceeded(Exception):
    """A search ran out of its time budget before verifying every candidate."""


class Locator:
    def __init__(
        self,
        index: LocateIndex,
        sweeps: Mapping[str, list[Sweep]],
        catalog: Catalog,
        matcher: Matcher,
        thresholds: Thresholds | None = None,
    ) -> None:
        self._counter = threading.local()  # verify calls, per thread, for search()
        self.index = index
        self.catalog = catalog
        self.matcher = matcher
        self.thresholds = thresholds or load_thresholds()
        self._sweeps = {
            (model_id, sweep.sweep_id): sweep
            for model_id, model_sweeps in sweeps.items()
            for sweep in model_sweeps
        }
        self._face = lru_cache(maxsize=512)(self._load_face)

    def _verify(self, photo: Image.Image, face: Image.Image, t: Thresholds) -> Verification:
        deadline = getattr(self._counter, "deadline", None)
        if deadline is not None and time.monotonic() >= deadline:
            raise _DeadlineExceeded
        self._counter.calls = getattr(self._counter, "calls", 0) + 1
        return verify(self.matcher, photo, face, t.ransac_px)

    def _load_face(self, model_id: str, sweep_id: str, face: int) -> Image.Image:
        with Image.open(self._sweeps[(model_id, sweep_id)].faces[face]) as opened:
            image = opened.convert("RGB")
        image.info[FEATURE_KEY] = f"{model_id}/{sweep_id}/{face}"
        return image

    # --- one photo ---------------------------------------------------------------------------

    def _candidates(
        self,
        photo: Image.Image,
        claimed_models: set[str],
        t: Thresholds | None = None,
        extra: list | None = None,
        claimed_search: set[str] | None = None,
    ) -> list:
        """Candidates to verify: the top_k over every building, plus the claimed building's
        side faces (top_k_claimed of them), or only those of `claimed_search` when given."""
        t = t or self.thresholds
        embedder = self.index.embedder
        vector = unit(embedder.embed(photo)) if embedder is not None else None
        hits = self.index.search(photo, k=t.top_k, vector=vector)
        if claimed_models:
            # The claimed building's side faces (where listing photos look), best first.
            claimed = self.index.search(
                photo,
                k=4 * t.top_k_claimed,
                model_ids=claimed_search or claimed_models,
                vector=vector,
            )
            hits += [h for h in claimed if h.entry.face in SIDE_FACES][: t.top_k_claimed]
        hits += extra or []
        seen, out = set(), []
        for hit in sorted(hits, key=lambda h: -h.score):
            key = (hit.entry.model_id, hit.entry.sweep_id, hit.entry.face)
            if key not in seen and (hit.entry.model_id, hit.entry.sweep_id) in self._sweeps:
                seen.add(key)
                out.append(hit)
        return out

    def _best(
        self,
        photo: Image.Image,
        hits: list,
        passes: Callable[[Verification], bool],
        stop_early: bool = True,
        t: Thresholds | None = None,
    ):
        """The passing candidate with the most inliers, or None. Stops at a very strong one."""
        t = t or self.thresholds
        best = None
        for hit in hits:
            entry = hit.entry
            face = self._face(entry.model_id, entry.sweep_id, entry.face)
            check = self._verify(photo, face, t)
            if passes(check) and (best is None or check.inliers > best.check.inliers):
                best = _Placement(
                    entry.model_id,
                    self._sweeps[(entry.model_id, entry.sweep_id)],
                    entry.face,
                    check,
                )
            if stop_early and check.inliers >= t.stop_at_inliers and passes(check):
                break
        return best

    def _scan_claimed(
        self,
        photo: Image.Image,
        hits: list,
        claimed_ok: Callable[[Verification], bool],
        t: Thresholds | None = None,
    ) -> tuple[_Placement | None, bool, Verification | None]:
        """One pass over the claimed candidates, each verified once: the best that passes the
        claimed bar (stopping at a very strong one, as _best does), and whether any cleared
        inliers and ratio (a candidate that fails only the spread floor)."""
        t = t or self.thresholds
        best, doubtful, top = None, False, None
        for hit in hits:
            entry = hit.entry
            face = self._face(entry.model_id, entry.sweep_id, entry.face)
            check = self._verify(photo, face, t)
            if top is None or check.inliers > top.inliers:
                top = check
            if check.inliers >= t.min_inliers and check.ratio >= t.min_inlier_ratio:
                doubtful = True
            if claimed_ok(check) and (best is None or check.inliers > best.check.inliers):
                best = _Placement(
                    entry.model_id,
                    self._sweeps[(entry.model_id, entry.sweep_id)],
                    entry.face,
                    check,
                )
            if best is not None and check.inliers >= t.stop_at_inliers and claimed_ok(check):
                break
        return best, doubtful, top

    def _place(
        self,
        photo: Image.Image,
        claimed_models: set[str],
        t: Thresholds | None = None,
        extra: list | None = None,
    ) -> _Placement | None:
        return self._place_detail(photo, claimed_models, t, extra).placed

    def _place_detail(
        self,
        photo: Image.Image,
        claimed_models: set[str],
        t: Thresholds | None = None,
        extra: list | None = None,
        claimed_search: set[str] | None = None,
    ) -> "_PlaceOutcome":
        """Claimed twins first, always: a twin of the claimed building that passes places the
        photo there, whatever else matches and whatever order the index was built in. Another
        building places it only on the stricter elsewhere bar (it can lead to DON'T PAY). When
        the claimed match passes but another building clears the strict bar with ambiguity_ratio
        times its inliers, the photo is not placed at all."""
        t = t or self.thresholds
        hits = self._candidates(photo, claimed_models, t, extra, claimed_search)
        claimed_hits = [h for h in hits if h.entry.model_id in claimed_models]
        other_hits = [h for h in hits if h.entry.model_id not in claimed_models]
        seen = {(h.entry.model_id, h.entry.sweep_id, h.entry.face) for h in other_hits}
        other_hits += [
            h
            for h in seam_neighbours(other_hits)
            if (h.entry.model_id, h.entry.sweep_id, h.entry.face) not in seen
            and (h.entry.model_id, h.entry.sweep_id) in self._sweeps
        ]

        def strict(c: Verification) -> bool:
            return passes_strict(c, t)

        def claimed_ok(c: Verification) -> bool:
            return (
                c.inliers >= t.min_inliers
                and c.ratio >= t.min_inlier_ratio
                and c.spread >= t.claimed_min_spread
            )

        placed, doubtful, top = self._scan_claimed(photo, claimed_hits, claimed_ok, t)
        if placed is None:
            # A claimed match that clears inliers and ratio but fails only the spread floor is
            # doubtful, not absent: could not place, and never search elsewhere (no new route to
            # DON'T PAY; ruling 07:43, #28).
            if doubtful:
                return _PlaceOutcome(None, "spread", None)
            elsewhere = self._best(photo, other_hits, strict, t=t)
            if elsewhere is not None:
                return _PlaceOutcome(elsewhere, None, None)
            return _PlaceOutcome(None, _failed_bar(top, t), None)

        # Ambiguity (ruling 03:46): another building far stronger than the claimed match means
        # the photo is placed nowhere. No false pass, and no false DON'T PAY either.
        # The rival only ever blocks, never places, so it needs inliers and ratio but not the
        # strict spread (ruling (a), 09:26 on #74): a far stronger match elsewhere packed on a
        # patch still makes the claimed one doubtful. Placing elsewhere keeps the strict bar.
        def rival_ok(c: Verification) -> bool:
            return c.inliers >= t.elsewhere_min_inliers and c.ratio >= t.min_inlier_ratio

        rival = self._best(photo, other_hits, rival_ok, stop_early=False, t=t)
        if rival is not None and rival.check.inliers >= t.ambiguity_ratio * placed.check.inliers:
            # The claimed search may have stopped early at a strong face (only possible at or
            # above stop_at_inliers); compare the rival with the claimed maximum first.
            if placed.check.inliers >= t.stop_at_inliers:
                full = self._best(photo, claimed_hits, claimed_ok, stop_early=False, t=t)
                if full is not None and full.check.inliers > placed.check.inliers:
                    placed = full
            if rival.check.inliers >= t.ambiguity_ratio * placed.check.inliers:
                return _PlaceOutcome(
                    None, "ambiguity", round(rival.check.inliers / placed.check.inliers, 4)
                )
        ratio = round(rival.check.inliers / placed.check.inliers, 4) if rival else None
        return _PlaceOutcome(placed, None, ratio)

    def _identify(
        self,
        photo: Image.Image,
        t: Thresholds | None = None,
        extra: list | None = None,
        near: list[Verification] | None = None,
    ) -> tuple[_Placement | None, bool]:
        """The ad names no home. Verify EVERY candidate on the strict bar, with no early stop, so
        the answer never depends on index order. Returns (best placement, ambiguous): ambiguous
        when the photo passes in more than one property (tract twins, sister buildings)."""
        t = t or self.thresholds
        best, homes = None, set()
        for hit in self._candidates(photo, set(), t, extra):
            entry = hit.entry
            face = self._face(entry.model_id, entry.sweep_id, entry.face)
            check = self._verify(photo, face, t)
            if not passes_strict(check, t):
                if near is not None and loose(check, t):
                    near.append(check)
                continue
            homes.add(self.catalog.property_of(entry.model_id))
            if best is None or check.inliers > best.check.inliers:
                best = _Placement(
                    entry.model_id,
                    self._sweeps[(entry.model_id, entry.sweep_id)],
                    entry.face,
                    check,
                )
        return best, len(homes) > 1

    # --- E2a: retry with more candidates of one kind, same bars ---------------------------

    def _focus_models(
        self, option: str, claimed_property_id: str | None, scan_model_id: str | None
    ) -> set[str] | None:
        """focus_scan names one scan of the claimed building: only its side faces are verified
        on the claimed side (up to top_k_claimed, never faces 0 and 5)."""
        if option != "focus_scan":
            return None
        claimed = self.catalog.models_of(claimed_property_id) & self.index.model_ids()
        if scan_model_id is None or scan_model_id not in claimed:
            raise ValueError("focus_scan needs scan_model_id: an indexed scan of the claimed home")
        return {scan_model_id}

    def candidates_for(
        self,
        photo: Image.Image,
        claimed_property_id: str | None,
        option: str,
        scan_model_id: str | None = None,
    ) -> list:
        """The candidates an option would verify ("base" for the ordinary run)."""
        t = search_thresholds(self.thresholds, option)
        claimed = self.catalog.models_of(claimed_property_id) & self.index.model_ids()
        focus = self._focus_models(option, claimed_property_id, scan_model_id)
        return self._candidates(photo.convert("RGB"), claimed, t, None, focus)

    def search(
        self,
        photo: Image.Image,
        option: str,
        claimed_property_id: str | None,
        *,
        scan_model_id: str | None = None,
        deadline_s: float | None = None,
        photo_id: str = "p",
    ) -> SearchResult:
        """Re-run placement for one photo with more candidates of the kind `option` names, through
        the very routine locate() runs, so every guard holds (claimed first, the bars, the
        ambiguity rule, catalog-unknown buildings, a claimed home with no scan, identify when no
        home is claimed). Options: focus_scan (the side faces of one named scan of the claimed
        home), wider_index (top_k 6 -> 12), deeper_claimed (top_k_claimed 48 -> 96), stop.
        Only retrieval changes; a retry finds more, never accepts less. Past `deadline_s` it stops
        verifying and reports not_located (timed_out), never a guess."""
        if option not in SEARCH_OPTIONS:
            raise ValueError(f"unknown search option {option!r}; use one of {SEARCH_OPTIONS}")
        if option == "stop":
            return SearchResult(option="stop")
        t = search_thresholds(self.thresholds, option)
        focus = self._focus_models(option, claimed_property_id, scan_model_id)
        image = photo.convert("RGB")
        started = time.monotonic()
        self._counter.calls = 0
        self._counter.deadline = None if deadline_s is None else started + deadline_s
        try:
            result, points = self.locate_with_points(
                f"search-{option}",
                {photo_id: image},
                claimed_property_id,
                t=t,
                claimed_search=focus,
            )
        except _DeadlineExceeded:
            return SearchResult(
                option=option,
                location=PhotoLocation(
                    photo_id=photo_id, status=LocateStatus.NOT_LOCATED, bar_failed="inliers"
                ),
                verified=self._counter.calls,
                seconds=round(time.monotonic() - started, 3),
                timed_out=True,
            )
        finally:
            self._counter.deadline = None
        return SearchResult(
            option=option,
            location=result.photos[0],
            pose=result.poses.get(photo_id),
            points=points.get(photo_id),
            identified_property_id=(
                result.claimed_property_id if result.identified_by_scan else None
            ),
            verified=self._counter.calls,
            seconds=round(time.monotonic() - started, 3),
        )

    def _pose(self, photo: Image.Image, placed: _Placement) -> Pose | None:
        if placed.check.homography is None or placed.sweep.position is None:
            return None  # no geometry, e.g. a walkthrough video frame
        hfov = photo_hfov(photo, self.thresholds.default_hfov_deg)
        face_size = self._face(placed.model_id, placed.sweep.sweep_id, placed.face).size[0]
        photo_to_face = rotation_from_homography(
            placed.check.homography,
            intrinsics(photo.width, photo.height, hfov),
            face_intrinsics(face_size),
        )
        pano = (
            matrix_from_quaternion(placed.sweep.rotation_quat)
            if placed.sweep.rotation_quat
            else np.eye(3)
        )
        camera_to_pano = face_basis(placed.face) @ photo_to_face
        camera_to_world = pano @ camera_to_pano
        yaw, pitch = viewer_yaw_pitch(pano, camera_to_pano)
        return Pose(
            sweep_id=placed.sweep.sweep_id,
            position=placed.sweep.position or (0.0, 0.0, 0.0),
            rotation_quat=camera_quaternion(camera_to_world),
            fov_deg=round(hfov, 2),
            yaw_deg=yaw,
            pitch_deg=pitch,
        )

    # --- one case ----------------------------------------------------------------------------

    def locate(
        self,
        case_id: str,
        photos: Mapping[str, Image.Image],
        claimed_property_id: str | None,
    ) -> LocateResult:
        return self.locate_with_points(case_id, photos, claimed_property_id)[0]

    def locate_with_points(
        self,
        case_id: str,
        photos: Mapping[str, Image.Image],
        claimed_property_id: str | None,
        *,
        t: Thresholds | None = None,
        claimed_search: set[str] | None = None,
    ) -> tuple[LocateResult, dict[str, EvidencePoints]]:
        """locate(), plus up to 48 normalised matched pairs per placed photo for the evidence
        file (E2b). The pairs come back beside the result, never inside it, so they never reach
        the agent's chooser, the trace or a log. `t` and `claimed_search` are for search(): a
        retrieval-only thresholds copy and the one scan focus_scan names; every guard below
        applies to a search exactly as to a locate."""
        claimed_models = self.catalog.models_of(claimed_property_id) & self.index.model_ids()
        # Where a photo may be placed:
        #   claimed home set and indexed -> claimed first, strict bar elsewhere (can say elsewhere)
        #   claimed home set, not indexed -> nothing is placed: NOT_INDEXED, never elsewhere
        #   no claimed home -> identify: the strict bar in any building ("identified as P")
        identify = claimed_property_id is None
        locations: list[PhotoLocation] = []
        poses: dict[str, Pose] = {}
        per_model: dict[str, list[int]] = {}

        placements: dict[str, _Placement | None] = {}
        bars: dict[str, str | None] = {}  # photo id -> the bar that stopped it, if any
        rivals: dict[str, float | None] = {}  # photo id -> best rival over its claimed match
        points: dict[str, EvidencePoints] = {}
        tangled = False  # a photo passed in more than one property
        flipped: dict[str, Image.Image] = {}  # photo id -> the mirrored copy that placed it

        def attempt(img: Image.Image):
            """(placed, bar that stopped it, rival ratio, ambiguous) for one image."""
            if identify:
                near: list[Verification] = []
                found, ambiguous = self._identify(img, t, near=near)
                # "loose": enough matched points to name a building, too few of them consistent.
                # A regenerated (AI-edited) photo looks like this (#10); the card says so. Its own
                # value, never "ratio", which a claimed home's plain ratio miss also sets.
                failed = "loose" if near else "inliers"
                bar = "ambiguity" if ambiguous else (None if found else failed)
                return found, bar, None, ambiguous
            outcome = self._place_detail(img, claimed_models, t, None, claimed_search)
            return outcome.placed, outcome.bar_failed, outcome.rival_ratio, False

        flip_search = (t or self.thresholds).flip_search
        for photo_id, image in photos.items():
            if not identify and not claimed_models:
                placements[photo_id] = None
                continue
            photo = image.convert("RGB")
            placed, bar, rival, ambiguous = attempt(photo)
            if placed is None and flip_search and not ambiguous and bar not in _NO_FLIP_BARS:
                # V1 (#10): copied ads are often mirrored. Search the photo once more flipped left
                # to right, under the very same bars and guards; only a placement counts. Never
                # after a doubtful result (ambiguity or spread): a doubtful photo is not searched
                # elsewhere (ruling 07:43, #28), and a flip would do exactly that.
                mirrored = ImageOps.mirror(photo)
                m_placed, m_bar, m_rival, m_ambiguous = attempt(mirrored)
                ambiguous = ambiguous or m_ambiguous
                if m_placed is not None:
                    placed, bar, rival = m_placed, m_bar, m_rival
                    flipped[photo_id] = mirrored
            tangled = tangled or ambiguous
            bars[photo_id] = bar
            if not identify:
                rivals[photo_id] = rival
            if (
                placed is not None
                and placed.model_id not in claimed_models
                and self.catalog.property_of(placed.model_id) is None
            ):
                # Never "somewhere else" without a known other building: the catalog may just be
                # missing the claimed property's own twin. Not trustworthy enough to place.
                placed = None
                bars[photo_id] = "ambiguity"
                flipped.pop(photo_id, None)
            placements[photo_id] = placed

        identified_by_scan = conflict = False
        identified_photos = 0
        if identify:
            found = {
                self.catalog.property_of(p.model_id) for p in placements.values() if p is not None
            }
            strict_placed = sum(p is not None for p in placements.values())
            if tangled:
                log.warning("case %s: a photo matches more than one property", case_id)
                placements = dict.fromkeys(placements)
                conflict = True
            elif found and len(photos) >= 2 and strict_placed < 2:
                # One lone strict match among several photos is not enough to name a home.
                log.warning(
                    "case %s: only %d of %d photos identify a home",
                    case_id,
                    strict_placed,
                    len(photos),
                )
                placements = dict.fromkeys(placements)
                conflict = True
            elif len(found) > 1:
                # Photos from different homes: do not pick one.
                log.warning(
                    "case %s: photos identify different properties %s", case_id, sorted(found)
                )
                placements = dict.fromkeys(placements)
                conflict = True
            elif found:
                (claimed_property_id,) = found
                claimed_models = (
                    self.catalog.models_of(claimed_property_id) & self.index.model_ids()
                )
                identified_by_scan = True
                identified_photos = strict_placed

        for photo_id, placed in placements.items():
            if placed is None:
                status = (
                    LocateStatus.NOT_LOCATED
                    if claimed_models or conflict or (identify and self.index.model_ids())
                    else LocateStatus.NOT_INDEXED
                )
                locations.append(
                    PhotoLocation(
                        photo_id=photo_id,
                        status=status,
                        bar_failed=bars.get(photo_id)
                        if status is LocateStatus.NOT_LOCATED
                        else None,
                        rival_ratio=rivals.get(photo_id),
                    )
                )
                continue
            in_claimed = placed.model_id in claimed_models
            locations.append(
                PhotoLocation(
                    photo_id=photo_id,
                    status=(
                        LocateStatus.LOCATED_IN_CLAIMED
                        if in_claimed
                        else LocateStatus.LOCATED_ELSEWHERE
                    ),
                    model_id=placed.model_id,
                    pano_id=placed.sweep.sweep_id,
                    inliers=placed.check.inliers,
                    inlier_ratio=round(placed.check.ratio, 4),
                    matched_model_id=placed.model_id,
                    matched_property_id=self.catalog.property_of(placed.model_id),
                    room_label=self.catalog.room(placed.model_id, placed.sweep.sweep_id),
                    spread=round(placed.check.spread, 4),
                    rival_ratio=rivals.get(photo_id),
                    flipped=True if photo_id in flipped else None,
                    scan_face=placed.face,
                )
            )
            # A flipped placement was matched on the mirrored copy: its pose is the real view,
            # and its points are mapped back onto the photo as the ad sent it.
            used = flipped.get(photo_id) or photos[photo_id].convert("RGB")
            face_size = self._face(placed.model_id, placed.sweep.sweep_id, placed.face).size
            sample = evidence_points(placed, used.size, face_size)
            if sample is not None and photo_id in flipped:
                sample = sample.model_copy(
                    update={
                        "sampled": [(round(1 - x, 4), y, u, v) for x, y, u, v in sample.sampled]
                    }
                )
            if sample is not None:
                points[photo_id] = sample
            pose = self._pose(used, placed)
            if pose is not None:
                poses[photo_id] = pose
            if in_claimed:
                per_model.setdefault(placed.model_id, []).append(placed.check.inliers)

        candidates = sorted(
            (
                FloorPlanCandidate(
                    property_id=claimed_property_id or "",
                    model_id=model_id,
                    floor_plan=(
                        self.catalog.models.get(model_id) or ModelInfo(model_id, "")
                    ).floor_plan,
                    photos_located=len(per_model.get(model_id, [])),
                    total_inliers=sum(per_model.get(model_id, [])),
                )
                for model_id in sorted(claimed_models)
            ),
            key=lambda c: (-c.photos_located, -c.total_inliers, c.model_id),
        )
        chosen = candidates[0] if candidates and candidates[0].photos_located else None
        result = LocateResult(
            case_id=case_id,
            photos=locations,
            claimed_property_id=claimed_property_id,
            identified_by_scan=identified_by_scan,
            identified_photos=identified_photos,
            chosen=chosen,
            alternatives=[c for c in candidates if c is not chosen],
            poses=poses,
            thresholds_version=(
                f"{self.thresholds.version}+{getattr(self.matcher, 'version', self.matcher.name)}"
            ),
        )
        return result, points
