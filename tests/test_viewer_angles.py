"""The walk player turns the 3D viewer to each ad photo's matched view (#10, Sat 16:3x). The scan
cache is z-up while the cube faces and the viewer are y-up, so the viewer angles come from the
locator, which knows the pano's rotation."""

import math
import random

import numpy as np
import pytest
from PIL import Image

from snapback.vision.locate.cube import face_basis, look_rotation
from snapback.vision.locate.geometry import (
    camera_quaternion,
    matrix_from_quaternion,
    viewer_yaw_pitch,
)


def about_z(deg: float) -> np.ndarray:
    a = math.radians(deg)
    return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])


def quat_yaw_pitch(q) -> tuple[float, float]:
    """The web player's old reading (twin/pose.ts quatToYawPitch): world y up, camera down -Z."""
    f = -matrix_from_quaternion(q)[:, 2]
    return math.degrees(math.atan2(-f[0], -f[2])), math.degrees(math.asin(f[1]))


@pytest.mark.parametrize("seed", range(5))
def test_the_viewer_pitch_is_the_pitch_the_view_was_taken_at(seed):
    """A view rendered at pitch p from any pano reads pitch p, whatever the pano's turn about the
    cache's z axis. The old reading of the raw quaternion fails this (it gave up to +-75)."""
    rng = random.Random(seed)
    worst_old = 0.0
    for _ in range(20):
        turn, yaw, pitch = rng.uniform(-180, 180), rng.uniform(-180, 180), rng.uniform(-15, 10)
        pano, camera = about_z(turn), look_rotation(yaw, pitch)
        _, got = viewer_yaw_pitch(pano, camera)
        assert got == pytest.approx(pitch, abs=0.01)
        _, old = quat_yaw_pitch(camera_quaternion(pano @ camera))
        worst_old = max(worst_old, abs(old - pitch))
    assert worst_old > 20  # the bug this replaces, so the test is live


def test_the_viewer_yaw_turns_with_the_pano_and_with_the_view():
    """No pano turn: the front face looks down -Z (yaw 0), the left face is +90, the right -90.
    A pano turned by t about the cache's z axis turns every yaw by the same t."""
    still = np.eye(3)
    assert viewer_yaw_pitch(still, face_basis(1)) == (0.0, 0.0)  # front
    assert viewer_yaw_pitch(still, face_basis(4))[0] == pytest.approx(90)  # left
    assert viewer_yaw_pitch(still, face_basis(2))[0] == pytest.approx(-90)  # right
    for turn in (30.0, -75.0, 150.0):
        a = viewer_yaw_pitch(about_z(turn), face_basis(1))[0]
        b = viewer_yaw_pitch(about_z(turn), face_basis(2))[0]
        assert abs(((a - b + 180) % 360) - 180) == pytest.approx(90)  # the faces keep their spacing
        assert abs(((a - 0 + 180) % 360) - 180) == pytest.approx(abs(turn))  # turned by |t|


def test_the_locator_puts_the_viewer_angles_on_the_pose_and_the_walk_carries_them():
    from snapback.contracts import Pose
    from snapback.tour import TourPhoto

    assert {"yaw_deg", "pitch_deg"} <= set(Pose.model_fields)
    assert {"yaw_deg", "pitch_deg"} <= set(TourPhoto.model_fields)


def test_the_locator_sets_the_viewer_angles_from_its_own_pose(tmp_path):
    """#244 review: drop `yaw_deg`/`pitch_deg` in Locator._pose and this fails. The angles must be
    the viewer angles of the very camera the pose's quaternion describes."""
    from dataclasses import replace

    from snapback.adapters.matterport import FixtureMatterport
    from snapback.vision.embed import TinyEmbedder
    from snapback.vision.locate.geometry import CV_TO_GL
    from snapback.vision.locate.index import LocateIndex
    from snapback.vision.locate.locate import Catalog, Locator, ModelInfo
    from snapback.vision.locate.thresholds import load_thresholds
    from snapback.vision.locate.verify import PatchMatcher

    adapter = FixtureMatterport(tmp_path / "faces")
    sweeps = {"fx-model-a": adapter.sweeps("fx-model-a")}
    index = LocateIndex.build("fx", sweeps["fx-model-a"], TinyEmbedder())
    t = replace(load_thresholds(), min_inliers=12, stop_at_inliers=60, elsewhere_min_inliers=16)
    locator = Locator(
        index, sweeps, Catalog([ModelInfo("fx-model-a", "fx-prop-1")]), PatchMatcher(), t
    )
    with Image.open(sweeps["fx-model-a"][2].faces[1]) as opened:
        crop = opened.convert("RGB").crop((30, 20, 230, 190))
    result = locator.locate("c", {"p": crop}, "fx-prop-1")
    pose = result.poses["p"]
    assert pose.yaw_deg is not None and pose.pitch_deg is not None
    sweep = next(s for s in sweeps["fx-model-a"] if s.sweep_id == pose.sweep_id)
    pano = matrix_from_quaternion(sweep.rotation_quat) if sweep.rotation_quat else np.eye(3)
    camera_to_world_cv = (
        matrix_from_quaternion(pose.rotation_quat) @ CV_TO_GL
    )  # CV_TO_GL is its own inverse
    yaw, pitch = viewer_yaw_pitch(pano, pano.T @ camera_to_world_cv)
    assert (pose.yaw_deg, pose.pitch_deg) == pytest.approx((yaw, pitch), abs=0.05)


def test_the_walk_carries_the_angles_to_each_photo_unchanged():
    """#244 review: drop them in map_locate and this fails."""
    from snapback.contracts import DataSource, LocateResult, LocateStatus, PhotoLocation, Pose
    from snapback.tour import TourSweep, build_tour, map_locate

    q = (0.0, 0.0, 0.0, 1.0)
    sweeps = [
        TourSweep("z0", (0.0, 0.0, 1.4), q, "Entryway"),
        TourSweep("z1", (5.0, 0.0, 1.4), q, "Kitchen"),
    ]
    plan = build_tour(
        property_id="p", kind="apartment", source=DataSource.LIVE, sweeps=sweeps, has_scan=True
    )
    pose = Pose(
        sweep_id="z1",
        position=(5.0, 0.0, 1.4),
        rotation_quat=q,
        fov_deg=62.0,
        yaw_deg=-175.3,
        pitch_deg=-13.2,
    )
    located = LocateResult(
        case_id="c",
        photos=[PhotoLocation(photo_id="p1", status=LocateStatus.LOCATED_IN_CLAIMED, pano_id="z1")],
        poses={"p1": pose},
        thresholds_version="t",
    )
    out, _ = map_locate(plan, located)
    placed = [p for s in out.stops for p in s.photos]
    assert len(placed) == 1
    got = placed[0]
    assert (got.sweep_id, got.yaw_deg, got.pitch_deg, got.fov_deg) == ("z1", -175.3, -13.2, 62.0)
