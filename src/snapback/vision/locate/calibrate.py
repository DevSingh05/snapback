"""Locate calibration (V7 #33, learning-v2 L1b): turn a placement's evidence into how often a
placement like it is right.

- `placement_score(inliers, spread)`: one number from RANSAC inliers and how much of the photo
  they cover. More inliers spread over more of the photo is stronger evidence.
- `fit_isotonic`: pool-adjacent-violators, so P(right) never goes down as the score goes up.
- `reliability_bins`: k right out of n per confidence bin, for the Lab panel's calibration chart
  (`calibration_bin:LO-HI` rows; empty bins are left out, never drawn as 0 of 0).

Pairs come from `collect` below: for each held-out view, its best face in the twin it came from
(right) and its best face in another twin (wrong). Views are renders of the live scans, unseen
directions from the indexed scan points, not photos; every output says so.

    uv run python -m snapback.vision.locate.calibrate --index data/index/demo --n 40
"""

import argparse
import json
import math
import random
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUT = REPO_ROOT / "eval" / "locate_calibration.json"
BIN_EDGES = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def placement_score(inliers: int, spread: float) -> float:
    if inliers <= 0 or spread <= 0:
        return 0.0
    return float(math.log1p(inliers) * math.sqrt(min(1.0, spread)))


@dataclass(frozen=True)
class Calibration:
    xs: tuple[float, ...]  # score thresholds, ascending
    ps: tuple[float, ...]  # P(right) from each threshold up
    n: int = 0
    source: str = ""
    version: str = ""

    def predict(self, score: float) -> float:
        if not self.xs:
            return 0.0
        at = int(np.searchsorted(np.asarray(self.xs), score, side="right")) - 1
        return float(self.ps[max(0, at)])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "xs": list(self.xs),
                    "ps": list(self.ps),
                    "n": self.n,
                    "source": self.source,
                    "version": self.version,
                },
                indent=1,
            )
        )

    @classmethod
    def load(cls, path: Path) -> "Calibration":
        data = json.loads(Path(path).read_text())
        return cls(
            tuple(data["xs"]),
            tuple(data["ps"]),
            data.get("n", 0),
            data.get("source", ""),
            data.get("version", ""),
        )


def fit_isotonic(x: np.ndarray, y: np.ndarray) -> Calibration:
    """Non-decreasing step function of x that best fits y (pool adjacent violators)."""
    order = np.argsort(x, kind="mergesort")
    xs, ys = np.asarray(x, float)[order], np.asarray(y, float)[order]
    blocks: list[list[float]] = []  # [sum, count, first x]
    for xv, yv in zip(xs, ys, strict=True):
        blocks.append([yv, 1.0, xv])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            total, count, _ = blocks.pop()
            blocks[-1][0] += total
            blocks[-1][1] += count
    return Calibration(tuple(b[2] for b in blocks), tuple(b[0] / b[1] for b in blocks), len(xs))


@dataclass(frozen=True)
class Bin:
    low: float
    high: float
    k: int
    n: int


def reliability_bins(
    probs: np.ndarray, right: np.ndarray, edges: Sequence[float] = BIN_EDGES
) -> list[Bin]:
    probs, right = np.asarray(probs, float), np.asarray(right, int)
    out = []
    for i, (low, high) in enumerate(zip(edges[:-1], edges[1:], strict=True)):
        last = i == len(edges) - 2
        inside = (probs >= low) & ((probs <= high) if last else (probs < high))
        n = int(inside.sum())
        if n:
            out.append(Bin(round(low, 2), round(high, 2), int(right[inside].sum()), n))
    return out


# --- collecting pairs from live renders (needs the vision extra and the local scans) -----------


def collect(
    locator, sweeps: dict, n: int, seed: int
) -> list[tuple[float, int]]:  # pragma: no cover
    """(score, right) pairs: each view's best face in its own twin, and in another twin."""
    from snapback.eval.locate_gate import held_out_view
    from snapback.vision.locate.verify import verify

    rng = random.Random(seed)
    models = sorted(sweeps)
    pairs = []
    for _ in range(n):
        model = rng.choice(models)
        photo, _, _ = held_out_view(rng.choice(sweeps[model]), rng)
        hits = locator._candidates(photo, {model})
        best = {True: (0, 0.0), False: (0, 0.0)}
        for hit in hits[:12]:
            face = locator._face(hit.entry.model_id, hit.entry.sweep_id, hit.entry.face)
            check = verify(locator.matcher, photo, face, locator.thresholds.ransac_px)
            own = hit.entry.model_id == model
            if check.inliers > best[own][0]:
                best[own] = (check.inliers, check.spread)
        for own, (inliers, spread) in best.items():
            pairs.append((placement_score(inliers, spread), int(own)))
    return pairs


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - needs live scans
    from snapback.adapters.matterport import MatterportSettings, get_matterport
    from snapback.contracts import DataSource
    from snapback.vision.locate.index import LocateIndex
    from snapback.vision.locate.locate import Catalog, Locator, ModelInfo
    from snapback.vision.locate.verify import DiskLightGlue

    parser = argparse.ArgumentParser(prog="python -m snapback.vision.locate.calibrate")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--n", type=int, default=40, help="views per half (fit, then measure)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    settings = MatterportSettings().model_copy(update={"snapback_data_source": DataSource.LIVE})
    adapter = get_matterport(settings, cache_dir=args.cache)
    index = LocateIndex.load(args.index)
    if index.embedder is None:
        from snapback.vision.embed import Dinov2Embedder

        index = LocateIndex.load(args.index, Dinov2Embedder())
    models = sorted(index.model_ids())
    sweeps = {m: adapter.sweeps(m) for m in models}
    catalog = Catalog(ModelInfo(m, f"cal-prop-{m}") for m in models)
    locator = Locator(
        index, sweeps, catalog, DiskLightGlue(feature_dir=args.index.parent / "features")
    )
    started = time.monotonic()
    fit_pairs = collect(locator, sweeps, args.n, seed=100)  # dev half
    test_pairs = collect(locator, sweeps, args.n, seed=200)  # held-out half
    cal = fit_isotonic(np.array([s for s, _ in fit_pairs]), np.array([r for _, r in fit_pairs]))
    probs = np.array([cal.predict(s) for s, _ in test_pairs])
    right = np.array([r for _, r in test_pairs])
    bins = reliability_bins(probs, right)
    source = "renders: unseen directions from the indexed scan points, not photos"
    version = f"cal-{time.strftime('%Y%m%d-%H%M')}"
    out = Calibration(cal.xs, cal.ps, len(fit_pairs), source, version)
    out.save(args.out.with_name(args.out.stem + "_model.json"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "source": source,
                "version": version,
                "n_fit": len(fit_pairs),
                "n_test": len(test_pairs),
                "bins": [b.__dict__ for b in bins],
            },
            indent=1,
        )
    )
    ece = sum(b.n * abs(b.k / b.n - (b.low + b.high) / 2) for b in bins) / max(1, len(test_pairs))
    print(
        f"locate calibration ({source}); fit pairs {len(fit_pairs)}, held-out pairs "
        f"{len(test_pairs)}, {len(bins)} non-empty bins, approx ECE {ece:.3f}, "
        f"{time.monotonic() - started:.0f} s; wrote {args.out.name}"
    )
    for b in bins:
        print(f"  {b.low:.1f}-{b.high:.1f}: {b.k} right of {b.n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
