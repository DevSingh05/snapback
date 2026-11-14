"""Retrieval index over skybox faces: which views of which sweeps look like this photo?

Step one of locate. A cube face is a 90 degree view; a phone photo is usually 60 to 70
degrees. So each face is indexed with narrower views cut from it: the centre at about 60
degrees and four views shifted towards the face's corners. A crop of a perspective image is
itself a perspective image, so these are exact narrower views, not approximations.

The top candidates go to geometric verification (V2), which decides; this only ranks.

Index files live under `data/index/<name>/` (git-ignored): embeddings are derived from
sponsor imagery.
"""

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

from snapback.adapters.matterport import Sweep
from snapback.vision.embed import Embedder, unit

REPO_ROOT = Path(__file__).resolve().parents[4]
INDEX_ROOT = REPO_ROOT / "data" / "index"

# Share of a 90 degree face that a 60 degree view covers: tan(30) / tan(45).
NARROW_SHARE = math.tan(math.radians(30))


def views(face: Image.Image) -> list[tuple[str, Image.Image]]:
    """The face, then five narrower views: centre, and shifted to each corner."""
    width, height = face.size
    w, h = round(width * NARROW_SHARE), round(height * NARROW_SHARE)
    out = [("face", face)]
    for name, px, py in (
        ("c", 0.5, 0.5),
        ("tl", 0.15, 0.15),
        ("tr", 0.85, 0.15),
        ("bl", 0.15, 0.85),
        ("br", 0.85, 0.85),
    ):
        left, top = round((width - w) * px), round((height - h) * py)
        out.append((name, face.crop((left, top, left + w, top + h))))
    return out


@dataclass(frozen=True)
class Entry:
    model_id: str
    sweep_id: str
    face: int
    view: str


@dataclass(frozen=True)
class Hit:
    entry: Entry
    score: float  # cosine similarity, higher is closer


class LocateIndex:
    def __init__(
        self,
        name: str,
        entries: list[Entry],
        vectors: np.ndarray,
        embedder_name: str,
        built_at: str,
    ) -> None:
        self.name = name
        self.entries = entries
        self.vectors = vectors.astype(np.float32)
        self.embedder_name = embedder_name
        self.built_at = built_at
        self._embedder: Embedder | None = None

    def __len__(self) -> int:
        return len(self.entries)

    @classmethod
    def build(cls, name: str, sweeps: Sequence[Sweep], embedder: Embedder) -> "LocateIndex":
        entries: list[Entry] = []
        images: list[Image.Image] = []
        for sweep in sweeps:
            for number, path in enumerate(sweep.faces):
                with Image.open(path) as opened:
                    face = opened.convert("RGB")
                for view, image in views(face):
                    entries.append(Entry(sweep.model_id, sweep.sweep_id, number, view))
                    images.append(image)
        embed_many = getattr(embedder, "embed_many", None)
        if embed_many is not None:
            vectors = np.asarray(embed_many(images), dtype=np.float32)
        else:
            vectors = np.stack([unit(embedder.embed(image)) for image in images])
        index = cls(name, entries, vectors, embedder.name, datetime.now(UTC).isoformat())
        index._embedder = embedder
        return index

    def search(
        self, image: Image.Image, k: int = 10, embedder: Embedder | None = None
    ) -> list[Hit]:
        """The k closest views, best first, at most one per (sweep, face)."""
        embedder = embedder or self._embedder
        if embedder is None:
            raise ValueError("pass the embedder this index was built with")
        if embedder.name != self.embedder_name:
            raise ValueError(
                f"index built with embedder {self.embedder_name!r}, queried with {embedder.name!r}"
            )
        scores = self.vectors @ unit(embedder.embed(image))
        hits, seen = [], set()
        for row in np.argsort(-scores):
            entry = self.entries[row]
            key = (entry.model_id, entry.sweep_id, entry.face)
            if key in seen:
                continue
            seen.add(key)
            hits.append(Hit(entry, float(scores[row])))
            if len(hits) == k:
                break
        return hits

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder / "vectors.npy", self.vectors)
        meta = {
            "name": self.name,
            "embedder": self.embedder_name,
            "built_at": self.built_at,
            "entries": [asdict(entry) for entry in self.entries],
        }
        (folder / "index.json").write_text(json.dumps(meta))

    @classmethod
    def load(cls, folder: Path, embedder: Embedder | None = None) -> "LocateIndex":
        meta = json.loads((folder / "index.json").read_text())
        index = cls(
            meta["name"],
            [Entry(**row) for row in meta["entries"]],
            np.load(folder / "vectors.npy"),
            meta["embedder"],
            meta["built_at"],
        )
        if embedder is not None:
            index._embedder = embedder
        elif meta["embedder"] == "tiny":
            from snapback.vision.embed import TinyEmbedder

            index._embedder = TinyEmbedder()
        return index
