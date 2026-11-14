"""Skybox cube geometry: which way each face looks, and perspective views rendered from faces.

Face order and pixel orientation were measured from seam continuity on 32 live sweeps (every
pair of adjacent faces shares an edge; issue #68): 0 up, 1 front, 2 right, 3 back, 4 left,
5 down. Directions are in the pano's own frame, Y up and front along -Z (three.js), which the
pano's rotation quaternion takes into the model frame.

A face pixel (x, y) of a W x W face looks along  f + u r + v d  with u, v in [-1, 1]:
u = (x + 0.5) / W * 2 - 1 to the right, v = (y + 0.5) / W * 2 - 1 downwards.
"""

import math
from collections.abc import Sequence

import numpy as np
from PIL import Image

# (forward, right, down) per face, in the pano frame.
FACE_AXES: tuple[tuple[tuple[float, float, float], ...], ...] = (
    ((0, 1, 0), (1, 0, 0), (0, 0, -1)),  # 0 up: its bottom edge meets the front face
    ((0, 0, -1), (1, 0, 0), (0, -1, 0)),  # 1 front
    ((1, 0, 0), (0, 0, 1), (0, -1, 0)),  # 2 right
    ((0, 0, 1), (-1, 0, 0), (0, -1, 0)),  # 3 back
    ((-1, 0, 0), (0, 0, -1), (0, -1, 0)),  # 4 left
    ((0, -1, 0), (1, 0, 0), (0, 0, 1)),  # 5 down: its top edge meets the front face
)
FACE_NAMES = ("up", "front", "right", "back", "left", "down")
SIDE_FACES = (1, 2, 3, 4)


def face_basis(face: int) -> np.ndarray:
    """3x3 matrix whose columns are the face camera's right, down and forward axes (OpenCV
    camera axes: x right, y down, z forward) in the pano frame."""
    forward, right, down = (np.array(v, dtype=np.float64) for v in FACE_AXES[face])
    return np.stack([right, down, forward], axis=1)


def intrinsics(
    width: int, height: int, hfov_deg: float, cx: float | None = None, cy: float | None = None
) -> np.ndarray:
    fx = (width / 2) / math.tan(math.radians(hfov_deg) / 2)
    return np.array(
        [
            [fx, 0, width / 2 if cx is None else cx],
            [0, fx, height / 2 if cy is None else cy],
            [0, 0, 1],
        ],
        dtype=np.float64,
    )


def face_intrinsics(size: int) -> np.ndarray:
    """A face is a 90 degree pinhole view."""
    return intrinsics(size, size, 90.0)


def look_rotation(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    """Camera-to-pano rotation (OpenCV camera axes) for a camera turned `yaw` to the right of
    front and tilted `pitch` up."""
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    forward = np.array(
        [math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch)]
    )
    right = np.array([math.cos(yaw), 0.0, math.sin(yaw)])
    down = np.cross(forward, right)
    return np.stack([right, down, forward], axis=1)


def render(
    faces: Sequence[Image.Image],
    rotation: np.ndarray,
    hfov_deg: float,
    size: tuple[int, int],
) -> Image.Image:
    """A pinhole view from the cube centre. `rotation` is camera-to-pano (OpenCV axes)."""
    width, height = size
    arrays = [np.asarray(face.convert("RGB"), dtype=np.float32) for face in faces]
    k_inv = np.linalg.inv(intrinsics(width, height, hfov_deg))
    xs, ys = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    pixels = np.stack([xs, ys, np.ones_like(xs)], axis=-1).reshape(-1, 3)
    rays = (rotation @ (k_inv @ pixels.T)).T  # pano-frame directions

    out = np.zeros((rays.shape[0], 3), dtype=np.float32)
    best = np.full(rays.shape[0], -np.inf)
    which = np.full(rays.shape[0], -1)
    for face in range(6):
        forward = np.array(FACE_AXES[face][0], dtype=np.float64)
        along = rays @ forward
        take = along > best
        best[take], which[take] = along[take], face
    for face in range(6):
        mask = which == face
        if not mask.any():
            continue
        forward, right, down = (np.array(v, dtype=np.float64) for v in FACE_AXES[face])
        ray = rays[mask]
        depth = ray @ forward
        u, v = (ray @ right) / depth, (ray @ down) / depth
        image = arrays[face]
        side = image.shape[0]
        x = np.clip((u + 1) / 2 * side - 0.5, 0, side - 1)
        y = np.clip((v + 1) / 2 * side - 0.5, 0, side - 1)
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        x1, y1 = np.minimum(x0 + 1, side - 1), np.minimum(y0 + 1, side - 1)
        wx, wy = (x - x0)[:, None], (y - y0)[:, None]
        out[mask] = (
            image[y0, x0] * (1 - wx) * (1 - wy)
            + image[y0, x1] * wx * (1 - wy)
            + image[y1, x0] * (1 - wx) * wy
            + image[y1, x1] * wx * wy
        )
    return Image.fromarray(np.clip(out.reshape(height, width, 3), 0, 255).astype(np.uint8), "RGB")


def angle_between(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    return math.degrees(math.acos(float(np.clip(np.dot(a, b), -1.0, 1.0))))
