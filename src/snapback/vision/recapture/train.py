"""Train a recapture model with a split by source photo, and report dev numbers with n.

Every attack made from a photo stays on the same side as the photo, so dev never sees a
variant of a training photo. The threshold is frozen on dev at a genuine false-reject rate of at
most 5% (learning-v2 L1a), and the dev AUROC is reported with n.

    uv run python -m snapback.vision.recapture --manifest data/recapture/manifest.csv \\
        --version v0 --out data/recapture/v0.json

The manifest is CSV with `path`, `label` (genuine, screen, print, paste) and `source` (or
lane D's `source_photo_id`), plus optional `synthetic` (1 or true). One id scheme: `source` is
the genuine photo's file stem (what lane D's generator writes), so a genuine photo's own row
must say its own stem, and every attack must name a genuine photo that is in the data. Paths are
resolved against the manifest's folder, then the working directory. Protocol for team photos:
docs/recapture-protocol.md.
"""

import argparse
import csv
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from snapback.contracts import RecaptureLabel
from snapback.vision.recapture.features import features, too_small
from snapback.vision.recapture.model import CLASSES, RecaptureModel, fit_platt, fit_softmax

MAX_GENUINE_FALSE_REJECT = 0.05


@dataclass(frozen=True)
class TrainingRow:
    image: Image.Image
    label: RecaptureLabel
    source: str
    synthetic: bool = True


@dataclass(frozen=True)
class TrainReport:
    version: str
    n_train: int
    n_dev_genuine: int
    n_dev_attack: int
    dev_auroc: float
    threshold: float
    dev_genuine_false_reject: float
    dev_attack_false_accept: float
    synthetic_only: bool
    train_sources: tuple[str, ...]
    dev_sources: tuple[str, ...]
    row_split: tuple[tuple[str, bool], ...]  # (source, is_dev) for every row, in order
    # Real attacks (team captures) and synthetic ones (lane D's generator), apart, each with n.
    n_dev_attack_real: int
    n_dev_attack_synthetic: int
    dev_auroc_real: float
    dev_auroc_synthetic: float
    dev_attack_false_accept_real: float
    dev_attack_false_accept_synthetic: float


def auroc(scores_neg: Sequence[float], scores_pos: Sequence[float]) -> float:
    """Probability a random positive outscores a random negative (ties count half)."""
    neg, pos = np.asarray(scores_neg), np.asarray(scores_pos)
    if not len(neg) or not len(pos):
        return float("nan")
    greater = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(greater / (len(pos) * len(neg)))


def _side(source: str, seed: int, dev_share: float) -> str:
    digest = hashlib.sha256(f"{seed}|{source}".encode()).digest()
    return "dev" if digest[0] / 255 < dev_share else "train"


def train(
    rows: Sequence[TrainingRow], version: str, seed: int = 0, dev_share: float = 0.3
) -> tuple[RecaptureModel, TrainReport]:
    rows = [r for r in rows if r.label in CLASSES and not too_small(r.image)]
    genuine = {r.source for r in rows if r.label is RecaptureLabel.GENUINE}
    orphans = sorted({r.source for r in rows if r.label is not RecaptureLabel.GENUINE} - genuine)
    if orphans:
        raise ValueError(
            f"{len(orphans)} attack source(s) match no genuine photo in the data (e.g. "
            f"{orphans[0]!r}); a source must be the genuine photo's file stem"
        )
    sides = {r.source: _side(r.source, seed, dev_share) for r in rows}
    # Make sure both sides have genuine photos.
    genuine_sources = sorted({r.source for r in rows if r.label is RecaptureLabel.GENUINE})
    if genuine_sources and all(sides[s] == "train" for s in genuine_sources):
        sides[genuine_sources[0]] = "dev"
    if genuine_sources and all(sides[s] == "dev" for s in genuine_sources):
        sides[genuine_sources[0]] = "train"

    vectors = np.stack([features(r.image) for r in rows])
    labels = np.array([CLASSES.index(r.label) for r in rows])
    is_dev = np.array([sides[r.source] == "dev" for r in rows])
    train_x, train_y = vectors[~is_dev], labels[~is_dev]

    mean = train_x.mean(axis=0)
    scale = train_x.std(axis=0)
    scale[scale < 1e-9] = 1.0
    weights = fit_softmax((train_x - mean) / scale, train_y, len(CLASSES))
    model = RecaptureModel(
        version, mean, scale, weights, (1.0, 0.0), 0.5, all(r.synthetic for r in rows)
    )

    # Calibrate on train (dev stays clean for the numbers), then freeze the threshold on dev.
    raw_train = np.array([model.raw(v) for v in train_x])
    model.platt = fit_platt(raw_train, (train_y != 0).astype(float))
    dev_scores = np.array([model.score_vector(v) for v in vectors[is_dev]])
    dev_genuine = dev_scores[labels[is_dev] == 0]
    dev_attack = dev_scores[labels[is_dev] != 0]
    dev_synthetic = np.array([r.synthetic for r in rows])[is_dev][labels[is_dev] != 0]
    if len(dev_genuine):
        allowed = int(np.floor(MAX_GENUINE_FALSE_REJECT * len(dev_genuine)))
        ordered = np.sort(dev_genuine)[::-1]
        model.threshold = float(min(0.999, ordered[allowed] + 1e-6))
    report = TrainReport(
        version=version,
        n_train=int((~is_dev).sum()),
        n_dev_genuine=int(len(dev_genuine)),
        n_dev_attack=int(len(dev_attack)),
        dev_auroc=auroc(dev_genuine, dev_attack),
        threshold=model.threshold,
        dev_genuine_false_reject=float((dev_genuine > model.threshold).mean())
        if len(dev_genuine)
        else float("nan"),
        dev_attack_false_accept=float((dev_attack <= model.threshold).mean())
        if len(dev_attack)
        else float("nan"),
        synthetic_only=model.synthetic_only,
        train_sources=tuple(sorted(s for s, side in sides.items() if side == "train")),
        dev_sources=tuple(sorted(s for s, side in sides.items() if side == "dev")),
        row_split=tuple((r.source, bool(d)) for r, d in zip(rows, is_dev, strict=True)),
        n_dev_attack_real=int((~dev_synthetic).sum()),
        n_dev_attack_synthetic=int(dev_synthetic.sum()),
        dev_auroc_real=auroc(dev_genuine, dev_attack[~dev_synthetic]),
        dev_auroc_synthetic=auroc(dev_genuine, dev_attack[dev_synthetic]),
        dev_attack_false_accept_real=_rate(dev_attack[~dev_synthetic] <= model.threshold),
        dev_attack_false_accept_synthetic=_rate(dev_attack[dev_synthetic] <= model.threshold),
    )
    # Real and synthetic numbers only, each with n; the mixed AUROC is never saved.
    mixed = {"dev_auroc", "dev_attack_false_accept", "row_split"}
    model.meta = {
        k: v for k, v in report.__dict__.items() if not k.endswith("_sources") and k not in mixed
    }
    return model, report


def _rate(flags: np.ndarray) -> float:
    return float(flags.mean()) if len(flags) else float("nan")


def _resolve(manifest: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    beside = manifest.parent / candidate
    return beside if beside.exists() else Path.cwd() / candidate


def read_manifest(path: Path) -> list[TrainingRow]:
    rows = []
    with path.open() as handle:
        for record in csv.DictReader(line for line in handle if not line.startswith("#")):
            label = RecaptureLabel(record["label"])
            if label not in CLASSES:
                continue
            image_path = _resolve(path, record["path"])
            with Image.open(image_path) as opened:
                image = opened.convert("RGB")
            synthetic = str(record.get("synthetic", "1")).strip().lower() in ("1", "true", "yes")
            source = record.get("source") or record.get("source_photo_id") or image_path.stem
            if label is RecaptureLabel.GENUINE and source != image_path.stem:
                raise ValueError(
                    f"{path.name}: genuine photo {image_path.name} has source {source!r}; it "
                    f"must be its file stem {image_path.stem!r} (lane D names attacks that way)"
                )
            rows.append(TrainingRow(image, label, source, synthetic))
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m snapback.vision.recapture")
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        required=True,
        help="CSV of photos; repeat to combine team captures and lane D's attacks",
    )
    parser.add_argument("--version", default="v0")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    rows = [row for manifest in args.manifest for row in read_manifest(manifest)]
    model, report = train(rows, args.version, args.seed)
    model.save(args.out)
    kind = "SYNTHETIC ONLY" if report.synthetic_only else "includes team captures"
    print(
        f"recapture {report.version} ({kind}): train n={report.n_train}; dev genuine "
        f"n={report.n_dev_genuine}; threshold {report.threshold:.3f} (dev genuine false "
        f"reject {report.dev_genuine_false_reject:.3f}); saved {args.out.name}"
    )
    print(
        f"  real attacks (team captures): n={report.n_dev_attack_real}, dev AUROC "
        f"{report.dev_auroc_real:.3f}, false accept {report.dev_attack_false_accept_real:.3f}"
    )
    print(
        f"  SYNTHETIC attacks (lane D generator): n={report.n_dev_attack_synthetic}, dev AUROC "
        f"{report.dev_auroc_synthetic:.3f}, false accept "
        f"{report.dev_attack_false_accept_synthetic:.3f}"
    )
    return 0
