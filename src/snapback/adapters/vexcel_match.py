"""Matcher v2 for two Vexcel tiles: where does the claimed building sit in the ad building's tile?

Each tile is centred on a point and spans GROUND_M metres. SIFT features from the middle of the
claimed tile are matched to the whole ad tile (Lowe ratio test), and a similarity transform is
fitted with RANSAC. Few geometrically consistent inliers means a different place. Enough inliers
gives the claimed tile's centre in the ad tile, so its distance from the ad tile's centre, in
metres, says whether the two points are on one building or a house apart. No training; CPU only.

opencv is imported lazily (the `vision` extra): without it every match is None ("says nothing").
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from snapback.adapters.vexcel import BUFFER_M, HALF_SIDE_M

GROUND_M = 2 * (HALF_SIDE_M + BUFFER_M)  # a tile's side on the ground, metres
MAX_SIDE_PX = 640  # tiles are downscaled to this before features (speed, under 300 ms a pair)
CENTRE_CROP = 0.5  # features from the middle half of the claimed tile: its building, not the edge
RATIO = 0.75  # Lowe ratio test
RANSAC_PX = 5.0
MIN_KEYPOINTS = 50  # fewer on either tile means it shows nothing to match (blank, cloud, error)
CV_THREADS = 2  # the demo box runs many jobs; OpenCV must not take every core
# Picked by vexcel_set.tune_thresholds on the tune half of the LIVE set (n=54, Nov 15, at
# MAX_SIDE_PX 640); the held-out half is reported in eval/vexcel/results.json. Inliers: another
# place 0 to 4, the same scene 171+. Offset: a right case's shifted centre lands 1 to 20 m away,
# the house next door 16 to 49 m, so a 15 m shift and a 16 m neighbour cannot be told apart.
MIN_INLIERS = 40
MAX_OFFSET_M = 18.0


@dataclass(frozen=True)
class GeoMatch:
    inliers: int
    matches: int  # pairs that passed the ratio test
    offset_m: float | None  # claimed centre to ad centre on the ground; None if no transform
    # With a footprint (nadir tiles): does the ad tile's centre land inside the claimed
    # building's outline, carried into the ad tile by the same transform? None: not asked.
    in_footprint: bool | None = None

    @property
    def inlier_ratio(self) -> float:
        return self.inliers / self.matches if self.matches else 0.0


def same_building(
    m: GeoMatch, *, min_inliers: int = MIN_INLIERS, max_offset_m: float = MAX_OFFSET_M
) -> bool:
    return m.inliers >= min_inliers and m.offset_m is not None and m.offset_m <= max_offset_m


def _load(cv2, path: str):
    try:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    except cv2.error:
        return None
    if img is None or img.size == 0:
        return None
    scale = MAX_SIDE_PX / max(img.shape)
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img


def _inside(poly: list[tuple[float, float]], x: float, y: float) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def geo_match(
    claimed_path: str,
    expected_path: str,
    footprint_uv: list[tuple[float, float]] | None = None,
) -> GeoMatch | None:
    """None when opencv is missing or a tile cannot be read or has nothing to match; otherwise
    the match."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    cv2.setNumThreads(CV_THREADS)
    a, b = _load(cv2, claimed_path), _load(cv2, expected_path)
    if a is None or b is None:
        return None
    ah, aw = a.shape
    x0, y0 = int(aw * (1 - CENTRE_CROP) / 2), int(ah * (1 - CENTRE_CROP) / 2)
    crop = a[y0 : ah - y0, x0 : aw - x0]
    sift = cv2.SIFT_create()
    ka, da = sift.detectAndCompute(crop, None)
    kb, db = sift.detectAndCompute(b, None)
    if da is None or db is None or min(len(ka), len(kb)) < MIN_KEYPOINTS:
        return None  # a blank, cloudy or broken tile: no evidence either way, never "wrong"
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(da, db, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < RATIO * p[1].distance]
    if len(good) < 3:
        return GeoMatch(inliers=0, matches=len(good), offset_m=None)
    src = np.float32([ka[g.queryIdx].pt for g in good]) + np.float32([x0, y0])
    dst = np.float32([kb[g.trainIdx].pt for g in good])
    model, mask = cv2.estimateAffinePartial2D(
        src, dst, method=cv2.RANSAC, ransacReprojThreshold=RANSAC_PX
    )
    if model is None or mask is None:
        return GeoMatch(inliers=0, matches=len(good), offset_m=None)
    inliers = int(mask.sum())
    cx, cy = model @ np.float32([aw / 2, ah / 2, 1.0])
    bh, bw = b.shape
    dx_m = (cx - bw / 2) * GROUND_M / bw
    dy_m = (cy - bh / 2) * GROUND_M / bh
    in_footprint = None
    if footprint_uv:
        # the claimed outline, in claimed-tile pixels, carried into the ad tile
        mapped = [tuple(model @ np.float32([u * aw, v * ah, 1.0])) for u, v in footprint_uv]
        in_footprint = _inside([(float(x), float(y)) for x, y in mapped], bw / 2, bh / 2)
    return GeoMatch(
        inliers=inliers,
        matches=len(good),
        offset_m=round(math.hypot(dx_m, dy_m), 1),
        in_footprint=in_footprint,
    )
