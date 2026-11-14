"""Photo memory (V5): perceptual hashes of every listing and reply photo, never pixels.

`PhotoMemory.check` answers with a `MemoryResult`: a reply copying this case's own listing
photo, a photo seen in another check (a date only), or nothing. SQLite under `data/memory/`,
7-day TTL. Embedding lookup is optional: pass any `Embedder` (DINOv2 in V1).
"""

from snapback.vision.memory.hashes import dhash, hamming, phash, variants
from snapback.vision.memory.store import (
    DEFAULT_DB,
    THRESHOLDS_VERSION,
    TTL,
    Embedder,
    PhotoMemory,
    PhotoRole,
)

__all__ = [
    "DEFAULT_DB",
    "THRESHOLDS_VERSION",
    "TTL",
    "Embedder",
    "PhotoMemory",
    "PhotoRole",
    "dhash",
    "hamming",
    "phash",
    "variants",
]
