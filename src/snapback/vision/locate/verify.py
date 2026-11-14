"""Geometric verification: do two images show the same surfaces, and how are they related?

A matcher returns point pairs; `verify` fits a homography with RANSAC and reports the inliers.
Retrieval only ranks candidates; this is the check that decides.

- `DiskLightGlue`: DISK features matched by LightGlue, through kornia (Apache-2.0 code; DISK
  "depth" and LightGlue-DISK weights, Apache-2.0, downloaded once from kornia's Hugging Face
  repos into ~/.cache/torch). Chosen over SuperPoint, whose weights are non-commercial. Needs
  the `vision` extra; uses Apple's GPU (MPS) when there is one.
- `PatchMatcher`: corners and normalised patches in numpy. Handles shifted crops at the same
  scale, which is what the tests need. It lets CI run the locate pipeline without torch; it is
  not the product matcher.
"""

from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from PIL import Image

from snapback.vision.locate.geometry import ransac_homography

MATCH_SIDE = 1024  # images are matched at most this large on the long side
FEATURE_KEY = "snapback_feature_key"  # Image.info key: where to keep this image's features


class Matcher(Protocol):
    name: str

    def match(self, a: Image.Image, b: Image.Image) -> tuple[np.ndarray, np.ndarray]:
        """Matched points as two (n, 2) arrays of pixel coordinates in a and in b."""
        ...

    def count_features(self, image: Image.Image) -> int:
        """How many distinctive points the image has (used to rank challenge spots)."""
        ...


@dataclass(frozen=True)
class Verification:
    matches: int
    inliers: int
    homography: np.ndarray | None  # maps a pixels to b pixels
    spread: float = 0.0  # bounding box of the inliers in a, as a fraction of a's area

    @property
    def ratio(self) -> float:
        return self.inliers / self.matches if self.matches else 0.0


def verify(matcher: Matcher, a: Image.Image, b: Image.Image, ransac_px: float) -> Verification:
    pa, pb = matcher.match(a, b)
    if len(pa) < 4:
        return Verification(len(pa), 0, None)
    h, mask = ransac_homography(pa, pb, ransac_px)
    return Verification(len(pa), int(mask.sum()), h, _spread(pa[mask], a.size))


def _spread(points: np.ndarray, size: tuple[int, int]) -> float:
    """How much of the image the inliers cover. One planar object (a poster, an appliance)
    puts all of them in a small box; a real room match spreads across the view."""
    if len(points) < 2:
        return 0.0
    width, height = points.max(axis=0) - points.min(axis=0)
    return float(width * height) / float(size[0] * size[1])


def _shrink(image: Image.Image, side: int = MATCH_SIDE) -> tuple[Image.Image, float]:
    image = image.convert("RGB")
    scale = min(1.0, side / max(image.size))
    if scale < 1.0:
        image = image.resize((round(image.width * scale), round(image.height * scale)))
    return image, scale


# --- numpy matcher (tests and CI) ---------------------------------------------------------------


class PatchMatcher:
    name = "patch"

    def __init__(self, max_corners: int = 400, patch: int = 7, side: int = 512) -> None:
        self.max_corners = max_corners
        self.half = patch // 2
        self.side = side

    def _grey(self, image: Image.Image) -> tuple[np.ndarray, float]:
        small, scale = _shrink(image, self.side)
        return np.asarray(small.convert("L"), dtype=np.float32), scale

    def _corners(self, g: np.ndarray) -> np.ndarray:
        gy, gx = np.gradient(g)

        def box(a: np.ndarray) -> np.ndarray:
            c = np.cumsum(np.cumsum(np.pad(a, ((1, 0), (1, 0))), axis=0), axis=1)
            k = 2
            out = np.zeros_like(a)
            out[k:-k, k:-k] = (
                c[2 * k + 1 :, 2 * k + 1 :]
                - c[: -2 * k - 1, 2 * k + 1 :]
                - c[2 * k + 1 :, : -2 * k - 1]
                + c[: -2 * k - 1, : -2 * k - 1]
            )
            return out

        sxx, syy, sxy = box(gx * gx), box(gy * gy), box(gx * gy)
        response = sxx * syy - sxy * sxy - 0.04 * (sxx + syy) ** 2
        m = self.half + 3
        response[:m], response[-m:], response[:, :m], response[:, -m:] = 0, 0, 0, 0
        # Non-maximum suppression on a 5x5 neighbourhood.
        padded = np.pad(response, 2, constant_values=-np.inf)
        neighbours = np.max(
            [
                padded[dy : dy + g.shape[0], dx : dx + g.shape[1]]
                for dy in range(5)
                for dx in range(5)
            ],
            axis=0,
        )
        peaks = (response >= neighbours) & (response > 1e-4 * response.max())
        ys, xs = np.nonzero(peaks)
        order = np.argsort(-response[ys, xs])[: self.max_corners]
        return np.stack([xs[order], ys[order]], axis=1)

    def _describe(self, g: np.ndarray, points: np.ndarray) -> np.ndarray:
        h = self.half
        patches = np.stack([g[y - h : y + h + 1, x - h : x + h + 1].ravel() for x, y in points])
        patches = patches - patches.mean(axis=1, keepdims=True)
        norms = np.linalg.norm(patches, axis=1, keepdims=True)
        return patches / np.maximum(norms, 1e-6)

    def match(self, a: Image.Image, b: Image.Image) -> tuple[np.ndarray, np.ndarray]:
        ga, sa = self._grey(a)
        gb, sb = self._grey(b)
        ca, cb = self._corners(ga), self._corners(gb)
        if len(ca) < 4 or len(cb) < 4:
            return np.zeros((0, 2)), np.zeros((0, 2))
        da, db = self._describe(ga, ca), self._describe(gb, cb)
        similarity = da @ db.T
        best_b = similarity.argmax(axis=1)
        best_a = similarity.argmax(axis=0)
        mutual = best_a[best_b] == np.arange(len(ca))
        good = mutual & (similarity[np.arange(len(ca)), best_b] > 0.9)
        pa = ca[good].astype(np.float64) / sa
        pb = cb[best_b[good]].astype(np.float64) / sb
        return pa, pb

    def count_features(self, image: Image.Image) -> int:
        g, _ = self._grey(image)
        return len(self._corners(g))


# --- DISK + LightGlue (the product matcher) ----------------------------------------------------


@dataclass(frozen=True)
class _Features:
    keypoints: object  # torch tensor (n, 2)
    descriptors: object  # torch tensor (n, 128)


class DiskLightGlue:  # pragma: no cover - needs torch, kornia and a one-time weight download
    name = "disk+lightglue"

    def __init__(
        self, max_keypoints: int = 2048, device: str | None = None, feature_dir=None
    ) -> None:
        import kornia.feature as kf
        import torch

        self._torch = torch
        self.device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.max_keypoints = max_keypoints
        self._disk = kf.DISK.from_pretrained("depth").to(self.device).eval()
        self._glue = kf.LightGlueMatcher("disk").to(self.device).eval()
        self._lafs = kf.laf_from_center_scale_ori
        # id(image) -> (image, features). The image is kept so its id is never reused while
        # cached; faces come back as the same objects from the locator's face cache.
        self._cache: OrderedDict[int, tuple] = OrderedDict()
        self.cache_size = 512
        # Faces carry a key in Image.info; their DISK features are kept on disk under
        # feature_dir (data/index/features, derived from sponsor imagery, deleted by purge).
        self.feature_dir = feature_dir

    def _features(self, image: Image.Image):
        key = id(image)
        if key in self._cache and self._cache[key][0] is image:
            self._cache.move_to_end(key)
            return self._cache[key][1]
        found = self._stored(image)
        self._cache[key] = (image, found)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
        return found

    def _stored(self, image: Image.Image):
        from pathlib import Path

        name = image.info.get(FEATURE_KEY)
        if self.feature_dir is None or not name:
            return self._extract(image)
        path = Path(self.feature_dir) / f"{name}.npz"
        torch = self._torch
        if path.is_file():
            data = np.load(path)
            feats = _Features(
                torch.from_numpy(data["keypoints"].astype(np.float32)).to(self.device),
                torch.from_numpy(data["descriptors"].astype(np.float32)).to(self.device),
            )
            return feats, float(data["scale"]), tuple(int(v) for v in data["size"])
        feats, scale, size = self._extract(image)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            path,
            keypoints=feats.keypoints.cpu().numpy().astype(np.float32),
            descriptors=feats.descriptors.cpu().numpy().astype(np.float16),
            scale=scale,
            size=np.array(size),
        )
        return feats, scale, size

    def _extract(self, image: Image.Image):
        small, scale = _shrink(image)
        pixels = np.asarray(small, dtype=np.float32) / 255.0
        tensor = self._torch.from_numpy(pixels.transpose(2, 0, 1).copy())[None].to(self.device)
        with self._torch.inference_mode():
            feats = self._disk(tensor, n=self.max_keypoints, pad_if_not_divisible=True)[0]
        return feats, scale, small.size

    def match(self, a: Image.Image, b: Image.Image) -> tuple[np.ndarray, np.ndarray]:
        fa, sa, size_a = self._features(a)
        fb, sb, size_b = self._features(b)
        if len(fa.keypoints) < 4 or len(fb.keypoints) < 4:
            return np.zeros((0, 2)), np.zeros((0, 2))
        torch = self._torch
        with torch.inference_mode():
            lafs_a = self._lafs(
                fa.keypoints[None],
                torch.full((1, len(fa.keypoints), 1, 1), 1.0, device=self.device),
            )
            lafs_b = self._lafs(
                fb.keypoints[None],
                torch.full((1, len(fb.keypoints), 1, 1), 1.0, device=self.device),
            )
            _, idx = self._glue(
                fa.descriptors,
                fb.descriptors,
                lafs_a,
                lafs_b,
                hw1=tuple(size_a[::-1]),
                hw2=tuple(size_b[::-1]),
            )
        idx = idx.cpu().numpy()
        if len(idx) == 0:
            return np.zeros((0, 2)), np.zeros((0, 2))
        pa = fa.keypoints.cpu().numpy()[idx[:, 0]].astype(np.float64) / sa
        pb = fb.keypoints.cpu().numpy()[idx[:, 1]].astype(np.float64) / sb
        return pa, pb

    def count_features(self, image: Image.Image) -> int:
        feats, _, _ = self._features(image)
        return int(len(feats.keypoints))
