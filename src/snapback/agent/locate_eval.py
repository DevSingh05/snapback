"""A8 (issue #72): how well does locate place a building's own listing photos?

The sponsor kit holds listing photos of buildings we have 3D scans of. Those are the best
honest test of "these photos were taken in this building": run locate over them, and over
decoys (photos of other buildings, claimed to be this one), and count.

    photos   k of n placed in the right building, and k of n in the right floor plan
    decoys   k of m placed anywhere at all; the target is 0

What is written is totals only, with a Wilson 95% interval, in the same columns as
`eval/results.csv`, so the Lab panel reads it as it is. No photo, file name, building or
floor plan is written or printed: the manifest and the photos stay under `data/`.

    make eval-locate-real

The manifest is one JSON object per line, written by whoever has the kit:

    {"photo": "photos/abc.jpg", "claimed_property_id": "<our id>", "floor_plan": "2 bed / 2 bath"}
    {"photo": "photos/xyz.jpg", "claimed_property_id": "<our id>", "decoy": true}

`photo` is relative to the manifest's folder. `floor_plan` is optional. A decoy is a photo of
some other building, tested as if it were claimed to be `claimed_property_id`.

The locator is lane V's (V2, issue #28). It is named on the command line as `module:function`
and called as `function(photo_path, claimed_property_id) -> Placement`.
"""

import argparse
import importlib
import math
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from snapback.contracts import LocateStatus

# The Lab panel's columns (fixtures/contracts/results_sample.csv). A test holds these equal to
# the ones the API checks before it serves a file.
COLUMNS = ("condition", "metric", "k", "n", "rate", "ci_low", "ci_high", "frozen_at")
CONDITION = "locate_real"
Z_95 = 1.959963984540054

DEFAULT_MANIFEST = Path("data/eval/locate_real_manifest.jsonl")
DEFAULT_OUT = Path("eval/locate_real.csv")
# Where lane V's locator is expected once V2 lands. Until then, pass --locator.
DEFAULT_LOCATOR = "snapback.vision.locate.verify:locate_photo"

_PLACED = frozenset({LocateStatus.LOCATED_IN_CLAIMED, LocateStatus.LOCATED_ELSEWHERE})


class ManifestRow(BaseModel):
    photo: str  # path to the image, relative to the manifest's folder
    claimed_property_id: str
    floor_plan: str | None = None  # the floor plan the photo shows, when the kit says
    decoy: bool = False  # a photo of some other building


class Placement(BaseModel):
    """What the locator says about one photo."""

    status: LocateStatus
    floor_plan: str | None = None


Locator = Callable[[Path, str], Placement]


class LocateRealResult(BaseModel):
    """Totals only. Nothing here names a photo or a building."""

    photos: int = 0  # the buildings' own photos
    right_building: int = 0
    wrong_building: int = 0  # placed, but in another building
    photos_with_floor_plan: int = 0
    right_floor_plan: int = 0  # right building and right floor plan
    decoys: int = 0
    decoy_false_placements: int = 0  # a decoy placed anywhere
    failed: int = 0  # photos the locator raised on; counted as not placed


def wilson(k: int, n: int) -> tuple[float, float]:
    """The Wilson 95% interval for k successes in n tries."""
    if n <= 0 or not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n and n > 0, got k={k}, n={n}")
    rate = k / n
    spread = Z_95 * Z_95 / n
    centre = (rate + spread / 2) / (1 + spread)
    half = Z_95 * math.sqrt(rate * (1 - rate) / n + spread / (4 * n)) / (1 + spread)
    return max(0.0, centre - half), min(1.0, centre + half)


def read_manifest(path: Path) -> list[tuple[Path, ManifestRow]]:
    """Each photo's path and its row. An error names the line, never what is on it."""
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = ManifestRow.model_validate_json(line)
        except ValidationError:
            raise ValueError(f"manifest line {number} is not a valid row") from None
        rows.append((path.parent / row.photo, row))
    return rows


def score(rows: Sequence[tuple[Path, ManifestRow]], locate: Locator) -> LocateRealResult:
    result = LocateRealResult()
    for photo, row in rows:
        try:
            placement = locate(photo, row.claimed_property_id)
        except Exception:
            # One unreadable photo must not stop the run. It was not placed.
            placement = Placement(status=LocateStatus.NOT_LOCATED)
            result.failed += 1

        if row.decoy:
            result.decoys += 1
            result.decoy_false_placements += placement.status in _PLACED
            continue

        result.photos += 1
        in_claimed = placement.status is LocateStatus.LOCATED_IN_CLAIMED
        result.right_building += in_claimed
        result.wrong_building += placement.status is LocateStatus.LOCATED_ELSEWHERE
        if row.floor_plan is not None:
            result.photos_with_floor_plan += 1
            result.right_floor_plan += in_claimed and placement.floor_plan == row.floor_plan
    return result


def _counts(result: LocateRealResult) -> list[tuple[str, int, int]]:
    """(metric, k, n) for each count that has something under it."""
    counts = [
        ("right_building", result.right_building, result.photos),
        ("right_floor_plan", result.right_floor_plan, result.photos_with_floor_plan),
        ("wrong_building", result.wrong_building, result.photos),
        ("decoy_false_placement", result.decoy_false_placements, result.decoys),
    ]
    return [count for count in counts if count[2] > 0]


def write_csv(result: LocateRealResult, path: Path, *, source: str, frozen_at: str) -> None:
    """Write the totals in the Lab panel's format. `source` is "live" or "fixture".

    The file is written beside its place and then renamed onto it, so a reader gets the old
    file or the new one and never half of either.
    """
    lines = [
        f"# {source.upper()}: locate over the buildings' own listing photos, and decoys.",
        "# k of n photos placed; for decoy_false_placement, k of n decoys placed (target 0).",
        ",".join(COLUMNS),
    ]
    for metric, k, n in _counts(result):
        low, high = wilson(k, n)
        lines.append(f"{CONDITION},{metric},{k},{n},{k / n:.4f},{low:.4f},{high:.4f},{frozen_at}")

    path.parent.mkdir(parents=True, exist_ok=True)
    beside = path.with_name(path.name + ".tmp")
    beside.write_text("\n".join(lines) + "\n")
    beside.replace(path)


def _load_locator(name: str) -> Locator:
    module_name, _, function_name = name.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, function_name)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m snapback.agent.locate_eval",
        description="Locate accuracy on a building's own listing photos. Writes totals only.",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--locator", default=DEFAULT_LOCATOR, help="module:function")
    parser.add_argument("--source", choices=("live", "fixture"), default="live")
    args = parser.parse_args(argv)

    if not args.manifest.is_file():
        print(
            f"No manifest at {args.manifest}. It is written from the kit; see #72.", file=sys.stderr
        )
        return 2
    try:
        locate = _load_locator(args.locator)
    except (ImportError, AttributeError, ValueError):
        print(
            f"No locator at {args.locator}. Lane V's locate (V2, #28) has to land first, "
            "or pass --locator module:function.",
            file=sys.stderr,
        )
        return 2

    result = score(read_manifest(args.manifest), locate)
    frozen_at = (
        "FIXTURE"
        if args.source == "fixture"
        else datetime.now().astimezone().isoformat(timespec="minutes")
    )
    write_csv(result, args.out, source=args.source, frozen_at=frozen_at)

    for metric, k, n in _counts(result):
        low, high = wilson(k, n)
        print(f"{metric}: {k} of {n} (95% interval {low:.2f} to {high:.2f})")
    if result.failed:
        print(f"{result.failed} photos could not be read and count as not placed")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
