"""Perceptual hashes: 64-bit fingerprints that survive re-encoding and resizing.

pHash (DCT of a 32x32 grey thumbnail) and dHash (left-right gradient of a 9x8 thumbnail) are
standard. Neither survives a crop well on its own, so `variants` also hashes a fixed set of
crops of each photo: a reply cropped from a listing photo lands close to one of them, and a
listing photo shown inside a bigger frame (a screen, a printout) is close to one of the reply's.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

HASH_SIZE = 8
_PHASH_SIZE = 32


def _grey(image: Image.Image, size: tuple[int, int]) -> np.ndarray:
    image = ImageOps.exif_transpose(image).convert("L")
    resized = image.resize(size, Image.Resampling.LANCZOS)
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


_POSITIONS = (0.0, 0.25, 0.5, 0.75, 1.0)

# Crops as (share of width and height, horizontal position, vertical position), positions
# from 0 (left or top) to 1 (right or bottom). "full" comes first and is the photo itself.
CROPS: tuple[tuple[str, float, float, float], ...] = (
    ("full", 1.0, 0.5, 0.5),
    *(
        (f"s{int(share * 100)}-{px:g},{py:g}", share, px, py)
        for share in (0.9, 0.8, 0.7, 0.6)
        for py in _POSITIONS
        for px in _POSITIONS
    ),
)


@dataclass(frozen=True)
class HashPair:
    variant: str
    phash: int
    dhash: int


def crop(image: Image.Image, share: float, px: float, py: float) -> Image.Image:
    width, height = image.size
    w, h = max(1, round(width * share)), max(1, round(height * share))
    left, top = round((width - w) * px), round((height - h) * py)
    return image.crop((left, top, left + w, top + h))


def variants(image: Image.Image) -> list[HashPair]:
    """The photo's own hashes first, then one pair per crop in `CROPS`."""
    image = ImageOps.exif_transpose(image)
    pairs = []
    for name, share, px, py in CROPS:
        part = image if share == 1.0 else crop(image, share, px, py)
        pairs.append(HashPair(name, phash(part), dhash(part)))
    return pairs
