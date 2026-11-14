"""Perceptual hashes: 64-bit fingerprints that survive re-encoding, resizing and copying tricks.

pHash (DCT of a 32x32 grey thumbnail) and dHash (left-right gradient of a 9x8 thumbnail) are
standard. Neither survives a crop, a screenshot or a mirror on its own, so a photo is fingerprinted
in three steps:

1. `prepare`: upright (EXIF), RGB, at most 1024 px on the long side, so a 12 MP photo costs the
   same as a small one.
2. `trim`: cut away flat borders and app UI around the largest busy region. A screenshot of a
   listing app becomes the photo inside it.
3. Hash the photo and a fixed set of crops of it (`CROPS`: square shares down to 50%, and wide
   and tall shapes), plus `probes`: the photo, its mirror, and the trimmed photo and its mirror.

Crops are always cut from the untrimmed photo. Trimming only adds probes, so a photo with a
large plain area (a white wall) that trims wrongly costs one extra comparison, nothing more.

A copy matches when one of its probes is close to one of the stored crops (it is a crop, a
screenshot or a mirror of the stored photo), or when one of its crops is close to the stored
photo itself (the stored photo appears inside it). `best_distance` does that comparison in numpy.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

HASH_SIZE = 8
MAX_SIDE = 1024
_PHASH_SIZE = 32


def prepare(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    longest = max(image.size)
    if longest > MAX_SIDE:
        scale = MAX_SIDE / longest
        image = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.Resampling.BILINEAR,
        )
    return image


def _grey(image: Image.Image, size: tuple[int, int]) -> np.ndarray:
    resized = image.convert("L").resize(size, Image.Resampling.LANCZOS)
    return np.asarray(resized, dtype=np.float64)


def _bits_to_int(bits: np.ndarray) -> int:
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return value


def _dct_matrix(n: int) -> np.ndarray:
    k = np.arange(n)[:, None]
    i = np.arange(n)[None, :]
    return np.cos(np.pi * (2 * i + 1) * k / (2 * n))


_DCT = _dct_matrix(_PHASH_SIZE)


def phash(image: Image.Image) -> int:
    pixels = _grey(image, (_PHASH_SIZE, _PHASH_SIZE))
    low = (_DCT @ pixels @ _DCT.T)[:HASH_SIZE, :HASH_SIZE]
    median = np.median(low.flatten()[1:])  # the DC term is overall brightness; leave it out
    return _bits_to_int(low > median)


def dhash(image: Image.Image) -> int:
    pixels = _grey(image, (HASH_SIZE + 1, HASH_SIZE))
    return _bits_to_int(pixels[:, 1:] > pixels[:, :-1])


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


# --- trimming -----------------------------------------------------------------------------------

_TRIM_SIDE = 256  # trimming looks at a small copy
_FLAT_STD = 6.0  # a row or column this flat (0-255 grey) is border or UI background
_MIN_SHARE = 0.15  # a busy region smaller than this share of the image is not the photo
_TRIM_GAPS = (1, 3, 6, 10)  # flat rows a photo may contain, at the 256 px trimming size


def _longest_run(busy: np.ndarray, gap: int) -> tuple[int, int] | None:
    """Longest stretch of busy entries, bridging flat gaps of at most `gap`."""
    best, start, last = None, None, None
    for i, flag in enumerate(busy):
        if not flag:
            continue
        if start is None or i - last > gap + 1:
            start = i
        last = i
        if best is None or last - start > best[1] - best[0]:
            best = (start, last)
    return best


def _busy_box(pixels: np.ndarray, gap: int) -> tuple[int, int, int, int] | None:
    height, width = pixels.shape
    # Rows first: a photo spans whole rows of a screenshot. UI text lines are short runs.
    rows = _longest_run(pixels.std(axis=1) > _FLAT_STD, gap=gap)
    if rows is None:
        return None
    band = pixels[rows[0] : rows[1] + 1]
    cols = _longest_run(band.std(axis=0) > _FLAT_STD, gap=gap)
    if cols is None:
        return None
    left, top, right, bottom = cols[0], rows[0], cols[1] + 1, rows[1] + 1
    share = (bottom - top) * (right - left) / (height * width)
    if share < _MIN_SHARE or share > 0.97:
        return None
    return left, top, right, bottom


def trims(image: Image.Image) -> list[Image.Image]:
    """Candidate photo regions inside the image (a screenshot, a photo of a screen), if any.

    How far apart a photo's busy rows may be depends on the photo (a plain ceiling is flat), so
    several gap tolerances are tried. Each distinct box is returned; most photos give none.
    """
    small = image.convert("L")
    scale = _TRIM_SIDE / max(small.size)
    small = small.resize((max(1, round(small.width * scale)), max(1, round(small.height * scale))))
    pixels = np.asarray(small, dtype=np.float64)
    boxes = []
    for gap in _TRIM_GAPS:
        box = _busy_box(pixels, gap)
        if box is not None and box not in boxes:
            boxes.append(box)
    return [image.crop(tuple(round(v / scale) for v in box)) for box in boxes]


def trim(image: Image.Image) -> Image.Image:
    """The most tolerant candidate region, or the image itself when there is none."""
    found = trims(image)
    return found[-1] if found else image


# --- crops and fingerprints --------------------------------------------------------------------

_POSITIONS = (0.0, 0.25, 0.5, 0.75, 1.0)
_EDGE_POSITIONS = (0.0, 0.5, 1.0)
_FINE_POSITIONS = tuple(i / 8 for i in range(9))

# (name, share of width, share of height, horizontal position, vertical position); positions
# run from 0 (left or top) to 1 (right or bottom). "full" comes first and is the photo itself.
CROPS: tuple[tuple[str, float, float, float, float], ...] = (
    ("full", 1.0, 1.0, 0.5, 0.5),
    *(
        (f"s{int(share * 100)}-{px:g},{py:g}", share, share, px, py)
        for share in (0.9, 0.8, 0.7, 0.6)
        for py in _POSITIONS
        for px in _POSITIONS
    ),
    *((f"s50-{px:g},{py:g}", 0.5, 0.5, px, py) for py in _EDGE_POSITIONS for px in _EDGE_POSITIONS),
    # Wide and tall shapes: nine positions along the cut side, three along the other.
    *(
        (f"w{int(sw * 100)}x{int(sh * 100)}-{px:g},{py:g}", sw, sh, px, py)
        for sw, sh in ((0.9, 0.6), (0.6, 0.9), (1.0, 0.7), (0.7, 1.0), (1.0, 0.5), (0.5, 1.0))
        for py in (_FINE_POSITIONS if sh < sw else _EDGE_POSITIONS)
        for px in (_FINE_POSITIONS if sw < sh else _EDGE_POSITIONS)
    ),
)


@dataclass(frozen=True)
class HashPair:
    variant: str
    phash: int
    dhash: int


def crop(image: Image.Image, share_w: float, share_h: float, px: float, py: float) -> Image.Image:
    width, height = image.size
    w, h = max(1, round(width * share_w)), max(1, round(height * share_h))
    left, top = round((width - w) * px), round((height - h) * py)
    return image.crop((left, top, left + w, top + h))


def _pair(name: str, image: Image.Image) -> HashPair:
    return HashPair(name, phash(image), dhash(image))


@dataclass(frozen=True)
class Fingerprint:
    crops: list[HashPair]  # the photo ("full") first, then one pair per CROPS entry
    probes: list[HashPair]  # whole-photo views a copy may be: itself, mirrored, trimmed

    def all(self) -> list[HashPair]:
        return [*self.crops, *self.probes]


def fingerprint(image: Image.Image) -> Fingerprint:
    image = prepare(image)
    crops = [
        _pair(name, image if sw == sh == 1.0 else crop(image, sw, sh, px, py))
        for name, sw, sh, px, py in CROPS
    ]
    probes = [crops[0], _pair("mirror", ImageOps.mirror(image))]
    for number, trimmed in enumerate(trims(image)):
        probes.append(_pair(f"trimmed{number}", trimmed))
        probes.append(_pair(f"trimmed{number}-mirror", ImageOps.mirror(trimmed)))
    return Fingerprint(crops, probes)


def variants(image: Image.Image) -> list[HashPair]:
    """Every hash kept for a photo: its crops, then its probes."""
    return fingerprint(image).all()


def _array(pairs: list[HashPair]) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.array([p.phash for p in pairs], dtype=np.uint64),
        np.array([p.dhash for p in pairs], dtype=np.uint64),
    )


def best_distance(
    probes: list[HashPair], targets: list[HashPair], phash_max: int, dhash_max: int
) -> int | None:
    """Smallest pHash distance over all (probe, target) pairs where both hashes are close."""
    if not probes or not targets:
        return None
    pp, pd = _array(probes)
    tp, td = _array(targets)
    p = np.bitwise_count(pp[:, None] ^ tp[None, :])
    d = np.bitwise_count(pd[:, None] ^ td[None, :])
    close = (p <= phash_max) & (d <= dhash_max)
    if not close.any():
        return None
    return int(p[close].min())
