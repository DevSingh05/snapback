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

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from PIL import Image

from snapback.adapters.matterport import Sweep
from snapback.contracts import (
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
)
from snapback.vision.locate.index import LocateIndex
from snapback.vision.locate.thresholds import Thresholds, load_thresholds
from snapback.vision.locate.verify import FEATURE_KEY, Matcher, Verification, verify

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


@dataclass(frozen=True)
class _Placement:
    model_id: str
    sweep: Sweep
    face: int
    check: Verification


class Locator:
    def __init__(
        self,
        index: LocateIndex,
        sweeps: Mapping[str, list[Sweep]],
        catalog: Catalog,
        matcher: Matcher,
        thresholds: Thresholds | None = None,
    ) -> None:
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

    def _load_face(self, model_id: str, sweep_id: str, face: int) -> Image.Image:
        with Image.open(self._sweeps[(model_id, sweep_id)].faces[face]) as opened:
            image = opened.convert("RGB")
        image.info[FEATURE_KEY] = f"{model_id}/{sweep_id}/{face}"
        return image

    # --- one photo ---------------------------------------------------------------------------

    def _candidates(self, photo: Image.Image, claimed_models: set[str]) -> list:
        t = self.thresholds
        embedder = self.index.embedder
        vector = unit(embedder.embed(photo)) if embedder is not None else None
        hits = self.index.search(photo, k=t.top_k, vector=vector)
        if claimed_models:
            # The claimed building's side faces (where listing photos look), best first.
            claimed = self.index.search(
                photo, k=4 * t.top_k_claimed, model_ids=claimed_models, vector=vector
            )
            hits += [h for h in claimed if h.entry.face in SIDE_FACES][: t.top_k_claimed]
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
    ):
        """The passing candidate with the most inliers, or None. Stops at a very strong one."""
        t = self.thresholds
        best = None
        for hit in hits:
            entry = hit.entry
            face = self._face(entry.model_id, entry.sweep_id, entry.face)
            check = verify(self.matcher, photo, face, t.ransac_px)
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

    def _place(self, photo: Image.Image, claimed_models: set[str]) -> _Placement | None:
        """Claimed twins first, always: a twin of the claimed building that passes places the
        photo there, whatever else matches and whatever order the index was built in. Another
        building places it only on the stricter elsewhere bar (it can lead to DON'T PAY). When
        the claimed match passes but another building clears the strict bar with ambiguity_ratio
        times its inliers, the photo is not placed at all."""
        t = self.thresholds
        hits = self._candidates(photo, claimed_models)
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
            return (
                c.inliers >= t.elsewhere_min_inliers
                and c.ratio >= t.min_inlier_ratio
                and c.spread >= t.elsewhere_min_spread
            )

        placed = self._best(
            photo,
            claimed_hits,
            lambda c: c.inliers >= t.min_inliers and c.ratio >= t.min_inlier_ratio,
        )
        if placed is None:
            return self._best(photo, other_hits, strict)
        # Ambiguity (ruling 03:46): another building far stronger than the claimed match means
        # the photo is placed nowhere. No false pass, and no false DON'T PAY either.
        rival = self._best(photo, other_hits, strict, stop_early=False)
        if rival is not None and rival.check.inliers >= t.ambiguity_ratio * placed.check.inliers:
            return None
        return placed

    def _pose(self, photo: Image.Image, placed: _Placement) -> Pose | None:
        if placed.check.homography is None:
            return None
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
        camera_to_world = pano @ face_basis(placed.face) @ photo_to_face
        return Pose(
            sweep_id=placed.sweep.sweep_id,
            position=placed.sweep.position or (0.0, 0.0, 0.0),
            rotation_quat=camera_quaternion(camera_to_world),
            fov_deg=round(hfov, 2),
        )

    # --- one case ----------------------------------------------------------------------------

    def locate(
        self,
        case_id: str,
        photos: Mapping[str, Image.Image],
        claimed_property_id: str | None,
    ) -> LocateResult:
        claimed_models = self.catalog.models_of(claimed_property_id) & self.index.model_ids()
        locations: list[PhotoLocation] = []
        poses: dict[str, Pose] = {}
        per_model: dict[str, list[int]] = {}

        for photo_id, image in photos.items():
            photo = image.convert("RGB")
            placed = self._place(photo, claimed_models)
            if (
                placed is not None
                and placed.model_id not in claimed_models
                and self.catalog.property_of(placed.model_id) is None
            ):
                # Never "somewhere else" without a known other building: the catalog may just be
                # missing the claimed property's own twin.
                placed = None
            if placed is None:
                status = LocateStatus.NOT_LOCATED if claimed_models else LocateStatus.NOT_INDEXED
                locations.append(PhotoLocation(photo_id=photo_id, status=status))
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
                )
            )
            pose = self._pose(photo, placed)
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
        return LocateResult(
            case_id=case_id,
            photos=locations,
            claimed_property_id=claimed_property_id,
            chosen=chosen,
            alternatives=[c for c in candidates if c is not chosen],
            poses=poses,
            thresholds_version=(
                f"{self.thresholds.version}+{getattr(self.matcher, 'version', self.matcher.name)}"
            ),
        )
