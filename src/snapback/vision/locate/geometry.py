"""Plane-to-plane geometry in numpy: RANSAC homography, rotation from a homography, quaternions.

A listing photo and a skybox view of the same room are related by a homography when the two
cameras share a centre (a pure rotation) and approximately when they do not but the matches lie
on a dominant plane (a wall). Either way the inlier count is the evidence, and the rotation
read off the homography is the photo's viewing direction.
"""

import math

import numpy as np


def _normalise(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    centre = points.mean(axis=0)
    spread = np.sqrt(((points - centre) ** 2).sum(axis=1)).mean() or 1.0
    scale = math.sqrt(2) / spread
    t = np.array([[scale, 0, -scale * centre[0]], [0, scale, -scale * centre[1]], [0, 0, 1]])
    homogeneous = np.c_[points, np.ones(len(points))]
    return (t @ homogeneous.T).T, t


def homography_dlt(src: np.ndarray, dst: np.ndarray) -> np.ndarray | None:
    """H with dst ~ H src, from 4 or more point pairs (normalised DLT)."""
    if len(src) < 4:
        return None
    a, ta = _normalise(src)
    b, tb = _normalise(dst)
    rows = []
    for (x, y, _), (u, v, _) in zip(a, b, strict=True):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, _, vt = np.linalg.svd(np.asarray(rows))
    h = vt[-1].reshape(3, 3)
    h = np.linalg.inv(tb) @ h @ ta
    if abs(h[2, 2]) < 1e-12:
        return None
    return h / h[2, 2]


def project(h: np.ndarray, points: np.ndarray) -> np.ndarray:
    homogeneous = np.c_[points, np.ones(len(points))] @ h.T
    with np.errstate(divide="ignore", invalid="ignore"):
        return homogeneous[:, :2] / homogeneous[:, 2:3]


def ransac_homography(
    src: np.ndarray,
    dst: np.ndarray,
    threshold_px: float,
    iterations: int = 1000,
    seed: int = 0,
) -> tuple[np.ndarray | None, np.ndarray]:
    """Best homography and its inlier mask. Deterministic for a given seed."""
    n = len(src)
    mask = np.zeros(n, dtype=bool)
    if n < 4:
        return None, mask
    rng = np.random.default_rng(seed)
    best_h, best_count = None, 0
    for _ in range(iterations):
        pick = rng.choice(n, 4, replace=False)
        h = homography_dlt(src[pick], dst[pick])
        if h is None:
            continue
        errors = np.linalg.norm(project(h, src) - dst, axis=1)
        inliers = np.nan_to_num(errors, nan=np.inf) < threshold_px
        count = int(inliers.sum())
        if count > best_count:
            best_h, best_count, mask = h, count, inliers
            if count > 0.9 * n:
                break
    if best_h is not None and best_count >= 4:
        refined = homography_dlt(src[mask], dst[mask])
        if refined is not None:
            errors = np.linalg.norm(project(refined, src) - dst, axis=1)
            refined_mask = np.nan_to_num(errors, nan=np.inf) < threshold_px
            if refined_mask.sum() >= best_count:
                best_h, mask = refined, refined_mask
    return best_h, mask


def nearest_rotation(m: np.ndarray) -> np.ndarray:
    u, _, vt = np.linalg.svd(m)
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    return r


def rotation_from_homography(h: np.ndarray, k_src: np.ndarray, k_dst: np.ndarray) -> np.ndarray:
    """R with dst-camera rays = R src-camera rays, for a homography between two cameras that
    share a centre: H ~ K_dst R K_src^-1. Off-centre photos give an approximation."""
    m = np.linalg.inv(k_dst) @ h @ k_src
    m = m / np.cbrt(np.linalg.det(m)) if np.linalg.det(m) > 0 else -m / np.cbrt(-np.linalg.det(m))
    return nearest_rotation(m)


def quaternion_from_matrix(r: np.ndarray) -> tuple[float, float, float, float]:
    """(x, y, z, w) for a proper rotation matrix."""
    trace = r[0, 0] + r[1, 1] + r[2, 2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        w, x = 0.25 * s, (r[2, 1] - r[1, 2]) / s
        y, z = (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        w, x = (r[2, 1] - r[1, 2]) / s, 0.25 * s
        y, z = (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s
    elif r[1, 1] > r[2, 2]:
        s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        w, x = (r[0, 2] - r[2, 0]) / s, (r[0, 1] + r[1, 0]) / s
        y, z = 0.25 * s, (r[1, 2] + r[2, 1]) / s
    else:
        s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        w, x = (r[1, 0] - r[0, 1]) / s, (r[0, 2] + r[2, 0]) / s
        y, z = (r[1, 2] + r[2, 1]) / s, 0.25 * s
    return (float(x), float(y), float(z), float(w))


def matrix_from_quaternion(q: tuple[float, float, float, float]) -> np.ndarray:
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


# OpenCV camera axes (x right, y down, z forward) to three.js camera axes (x right, y up,
# looking down -z): flip y and z.
CV_TO_GL = np.diag([1.0, -1.0, -1.0])


def camera_quaternion(camera_to_world_cv: np.ndarray) -> tuple[float, float, float, float]:
    """The three.js camera quaternion for a camera given as OpenCV-axes camera-to-world."""
    return quaternion_from_matrix(camera_to_world_cv @ CV_TO_GL)
