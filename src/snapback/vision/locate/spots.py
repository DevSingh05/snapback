"""Rank challenge spots for one twin: `SpotRanking`, which challenge/ (lane D) draws from.

A spot is one view a person standing in the unit can photograph: a side face of one sweep (a
90 degree view along front, right, back or left). Spots rank by how many distinctive points the
view has, because the reply photo has to be verified against it. At most one spot per room
(the room's best view), so the renter's instruction can name the room.

A spot is excluded from the draw (`overlaps_listing_photo`) when a listing photo was placed in
the same room looking within `overlap_deg` of the spot's direction: the poster could answer
with the listing photo itself. Excluded spots stay in the list, flagged, so the draw can say
how many it skipped.
"""

from collections.abc import Callable, Mapping, Sequence

import numpy as np
from PIL import Image

from snapback.adapters.matterport import Sweep
from snapback.contracts import Pose, SpotCandidate, SpotRanking
from snapback.vision.locate.cube import FACE_NAMES, SIDE_FACES, angle_between, face_basis
from snapback.vision.locate.geometry import camera_quaternion, matrix_from_quaternion
from snapback.vision.locate.thresholds import Thresholds, load_thresholds


def _forward(rotation_quat: tuple[float, float, float, float]) -> np.ndarray:
    """World viewing direction of a three.js camera quaternion (it looks down its -Z)."""
    camera_to_world_gl = matrix_from_quaternion(rotation_quat)
    return camera_to_world_gl @ np.array([0.0, 0.0, -1.0])


def _spot_pose(sweep: Sweep, face: int) -> Pose:
    pano = matrix_from_quaternion(sweep.rotation_quat) if sweep.rotation_quat else np.eye(3)
    return Pose(
        sweep_id=sweep.sweep_id,
        position=sweep.position or (0.0, 0.0, 0.0),
        rotation_quat=camera_quaternion(pano @ face_basis(face)),
        fov_deg=90.0,
    )


def _label(room: str | None, number: int, face: int, repeats: int) -> str:
    if room:
        name = room.lower() if repeats < 2 else f"{room.lower()} {number}"
        return f"the {name}, a wide photo showing its walls and fixed fittings"
    return f"the room at scan point {number}, facing its {FACE_NAMES[face]} side"


def rank_spots(
    case_id: str,
    model_id: str,
    sweeps: Sequence[Sweep],
    rooms: Mapping[str, str | None],
    count_features: Callable[[Image.Image], int],
    listing_poses: Sequence[Pose] = (),
    floor_plan: str | None = None,
    thresholds: Thresholds | None = None,
) -> SpotRanking:
    t = thresholds or load_thresholds()
    listing = [(pose.sweep_id, _forward(pose.rotation_quat)) for pose in listing_poses]
    sweep_room = {s.sweep_id: rooms.get(s.sweep_id) for s in sweeps}

    scored = []
    for number, sweep in enumerate(sweeps, start=1):
        room = sweep_room[sweep.sweep_id]
        for face in SIDE_FACES:
            with Image.open(sweep.faces[face]) as opened:
                features = count_features(opened.convert("RGB"))
            pose = _spot_pose(sweep, face)
            forward = _forward(pose.rotation_quat)
            overlaps = any(
                (sweep_room.get(sweep_id) == room if room else sweep_id == sweep.sweep_id)
                and angle_between(forward, direction) < t.spots_overlap_deg
                for sweep_id, direction in listing
                if sweep_id in sweep_room
            )
            scored.append((features, number, sweep, face, room, pose, overlaps))

    # One spot per room (or per sweep when rooms are unknown): its best drawable view, and
    # separately its best excluded view, so the draw can say how many it skipped.
    best: dict[tuple, tuple] = {}
    for item in scored:
        features, number, sweep, face, room, pose, overlaps = item
        key = (room or f"sweep:{sweep.sweep_id}", overlaps)
        if key not in best or features > best[key][0]:
            best[key] = item
    spots = []
    for features, number, sweep, face, room, pose, overlaps in sorted(
        best.values(), key=lambda item: -item[0]
    ):
        spots.append(
            SpotCandidate(
                spot_id=f"{sweep.sweep_id}-{FACE_NAMES[face]}",
                model_id=model_id,
                label=_label(room, number, face, sum(1 for r in sweep_room.values() if r == room)),
                pose=pose,
                inliers=int(features),
                overlaps_listing_photo=overlaps,
            )
        )
    drawable = [s for s in spots if not s.overlaps_listing_photo][: t.spots_top_n]
    excluded = [s for s in spots if s.overlaps_listing_photo]
    return SpotRanking(
        case_id=case_id, model_id=model_id, floor_plan=floor_plan, spots=[*drawable, *excluded]
    )


__all__ = ["rank_spots"]
