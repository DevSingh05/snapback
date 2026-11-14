"""Retrieval index over skybox faces: which views of which sweeps look like this photo?

Step one of locate. A cube face is a 90 degree view; a phone photo is usually 60 to 70
degrees. So each face is indexed with narrower views cut from it: the centre at about 60
degrees and four views shifted towards the face's corners. A crop of a perspective image is
itself a perspective image, so these are exact narrower views, not approximations.

The top candidates go to geometric verification (V2), which decides; this only ranks.

Index files live under `data/index/<name>/` (git-ignored): embeddings are derived from
sponsor imagery. Build one from the command line (prints counts only, never ids):

    uv run python -m snapback.vision.locate.index build            # DEMO_MODEL_IDS, DINOv2
    uv run python -m snapback.vision.locate.index build <model id> ... --embedder tiny
"""

import argparse
import json
import math
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

from snapback.adapters.matterport import MatterportSettings, Sweep, get_matterport
from snapback.contracts import DataSource
from snapback.vision.embed import Embedder, TinyEmbedder, unit

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

    @property
    def embedder(self) -> Embedder | None:
        return self._embedder

    def model_ids(self) -> set[str]:
        return {entry.model_id for entry in self.entries}

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
        self,
        image: Image.Image,
        k: int = 10,
        embedder: Embedder | None = None,
        model_ids: set[str] | None = None,
        vector: np.ndarray | None = None,
    ) -> list[Hit]:
        """The k closest views, best first, at most one per (sweep, face). `model_ids` keeps
        only those twins; `vector` reuses an embedding already computed for `image`."""
        embedder = embedder or self._embedder
        if embedder is None:
            raise ValueError("pass the embedder this index was built with")
        if embedder.name != self.embedder_name:
            raise ValueError(
                f"index built with embedder {self.embedder_name!r}, queried with {embedder.name!r}"
            )
        query = unit(embedder.embed(image)) if vector is None else vector
        scores = self.vectors @ query
        hits, seen = [], set()
        for row in np.argsort(-scores):
            entry = self.entries[row]
            if model_ids is not None and entry.model_id not in model_ids:
                continue
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


def warm_features(
    index: "LocateIndex",
    sweeps: dict,
    is_cached,
    extract,
) -> dict[str, int]:
    """Extract matcher features for every face in the index that is not cached yet, so the
    first live case in a building does not spend its time budget on extraction. Each face is
    handed over with its feature key (model/sweep/face) set, as the locator does."""
    from snapback.vision.locate.verify import FEATURE_KEY

    by_id = {(m, s.sweep_id): s for m, model_sweeps in sweeps.items() for s in model_sweeps}
    faces = sorted({(e.model_id, e.sweep_id, e.face) for e in index.entries})
    extracted = missing = 0
    for model_id, sweep_id, face in faces:
        key = f"{model_id}/{sweep_id}/{face}"
        if is_cached(key):
            continue
        sweep = by_id.get((model_id, sweep_id))
        path = sweep.faces[face] if sweep is not None and face < len(sweep.faces) else None
        if path is None or not Path(path).is_file():
            missing += 1
            continue
        with Image.open(path) as opened:
            image = opened.convert("RGB")
        image.info[FEATURE_KEY] = key
        extract(image)
        extracted += 1
    return {"faces": len(faces), "extracted": extracted, "missing": missing}


def _embedder(name: str) -> Embedder:
    if name == "tiny":
        return TinyEmbedder()
    from snapback.vision.embed import Dinov2Embedder

    return Dinov2Embedder()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m snapback.vision.locate.index")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="fetch faces and build one index over the given models")
    build.add_argument("model_ids", nargs="*", help="defaults to DEMO_MODEL_IDS from .env")
    build.add_argument("--ids-file", type=Path, help="JSON list or object of more model ids")
    build.add_argument("--embedder", choices=("dinov2", "tiny"), default="dinov2")
    build.add_argument("--name", default="demo")
    build.add_argument("--out", type=Path, help="index folder (default data/index/<name>)")
    build.add_argument("--cache", type=Path, help="face cache folder (default by data source)")
    build.add_argument("--source", choices=[s.value for s in DataSource], help="override .env")
    warm = sub.add_parser("warm", help="extract DISK features for every face of an index, ahead")
    warm.add_argument("--name", default="demo")
    warm.add_argument("--index", type=Path, help="index folder (default data/index/<name>)")
    warm.add_argument("--cache", type=Path, help="face cache folder (default: the live cache)")
    args = parser.parse_args(argv)

    if args.command == "warm":  # pragma: no cover - needs torch and the local face cache
        from snapback.adapters.matterport import LIVE_CACHE, _read_manifest, _safe
        from snapback.vision.locate.verify import DiskLightGlue

        folder = args.index or INDEX_ROOT / args.name
        index = LocateIndex.load(folder, TinyEmbedder())
        cache = args.cache or LIVE_CACHE
        sweeps = {m: _read_manifest(m, cache / _safe(m)) or [] for m in index.model_ids()}
        features = folder.parent / "features"
        matcher = DiskLightGlue(feature_dir=features)
        started = time.monotonic()
        report = warm_features(
            index,
            sweeps,
            is_cached=lambda key: (features / f"{key}.npz").is_file(),
            extract=matcher._features,
        )
        print(
            f"faces {report['faces']}, extracted {report['extracted']}, missing "
            f"{report['missing']}, {time.monotonic() - started:.0f} s; features in "
            f"{features.name}/"
        )
        return 0

    settings = MatterportSettings()
    if args.source:
        settings = settings.model_copy(update={"snapback_data_source": DataSource(args.source)})
    ids = list(args.model_ids or settings.demo_ids())
    if args.ids_file:
        extra = json.loads(args.ids_file.read_text())
        ids += list(extra.values() if isinstance(extra, dict) else extra)
    ids = list(dict.fromkeys(ids))
    if not ids:
        print("no model ids: pass some, set DEMO_MODEL_IDS in .env, or use --ids-file")
        return 2

    adapter = get_matterport(settings, cache_dir=args.cache)
    started = time.monotonic()
    sweeps: list[Sweep] = []
    failed = 0
    for model_id in ids:
        try:
            sweeps += adapter.sweeps(model_id)
        except (RuntimeError, ValueError) as error:  # refused by the API, or wrong data source
            failed += 1
            print(f"skipped one model: {error}")
    if not sweeps:
        print(f"nothing to index: all {len(ids)} models were skipped")
        return 1
    fetched = time.monotonic()
    index = LocateIndex.build(args.name, sweeps, _embedder(args.embedder))
    out = args.out or INDEX_ROOT / args.name
    index.save(out)
    faces = sum(len(sweep.faces) for sweep in sweeps)
    print(
        f"models {len(ids) - failed} (skipped {failed}), sweeps {len(sweeps)}, faces {faces}, "
        f"views {len(index)}, embedder {index.embedder_name}; fetch "
        f"{fetched - started:.1f} s, embed {time.monotonic() - fetched:.1f} s; saved to {out.name}/"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
