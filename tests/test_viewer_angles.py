"""The walk player turns the 3D viewer to each ad photo's matched view (#10, Sat 16:3x). The scan
cache is z-up while the cube faces and the viewer are y-up, so the viewer angles come from the
locator, which knows the pano's rotation."""

import math
import random

import numpy as np
import pytest

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
