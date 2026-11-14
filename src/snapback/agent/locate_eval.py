"""A8 (issue #72): how well does locate place a building's own listing photos?

The sponsor kit holds listing photos of buildings we have 3D scans of. Those are the best
honest test of "these photos were taken in this building": run locate over them, and over
decoys (photos of other buildings, claimed to be this one), and count.

    photos   k of n placed in the right building, and k of n in the right floor plan
             k of n placed in ANOTHER building (target 0: that is what would turn an honest
             listing into "Don't pay")
    decoys   k of m placed in the claimed building (target 0: that is a false "taken here")
             k of m placed in another building (for a decoy that is the right answer, when
             its own building is indexed; counted beside, not against)

A photo the locator never ran on is not a pass. If the claimed building has no twin in the
index, or the time ran out, or the file could not be read, the photo is "not tested": it is
written as its own count (`photo_not_tested`, `decoy_not_tested`) and left out of the counts
whose target is 0, so "0 placed in the wrong building" can only ever mean the locator looked
and placed none there. An untested photo still counts as not placed in `right_building`.

What is written is totals only, with a Wilson 95% interval, in the same columns as
`eval/results.csv`, so the Lab panel reads it as it is. No photo, file name, building or
floor plan is written or printed: the manifest and the photos stay under `data/`.

    make eval-locate-real

The manifest is one JSON object per line, written by whoever has the kit:

    {"photo": "photos/abc.jpg", "claimed_property_id": "<our id>", "floor_plan": "2 bed / 2 bath"}
    {"photo": "photos/xyz.jpg", "claimed_property_id": "<our id>", "decoy": true}

`photo` is relative to the manifest's folder. `floor_plan` is optional. A decoy is a photo of
some other building, tested as if it were claimed to be `claimed_property_id`.

The locator is the product's own: what a live case runs (A22, `agent/locate_live.py`), which
is lane V's `Locator` over the index on this machine. So the run scores what main ships. The
bars a match has to clear are read by that locator from lane V's own config file; this
module names none of them. Two things differ from a live case, on purpose: each photo is
placed alone, and the product's saved answers are neither read nor written, so the run
measures the locator and not what an earlier run stored. The product's time budget applies
as it does in a case: a photo that is not placed in time counts as not placed.

Another locator can be named on the command line as `module:function`, called as
`function(photo_path, claimed_property_id) -> Placement`.
"""

import argparse
import importlib
import math
import sys
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from snapback.agent.locate_live import LiveLocate, LiveOutcome
from snapback.contracts import DataSource, LocateStatus, PropertyRecord
from snapback.settings import Settings

# The Lab panel's columns (fixtures/contracts/results_sample.csv). A test holds these equal to
# the ones the API checks before it serves a file.
COLUMNS = ("condition", "metric", "k", "n", "rate", "ci_low", "ci_high", "frozen_at")
CONDITION = "locate_real"
Z_95 = 1.959963984540054

DEFAULT_MANIFEST = Path("data/eval/locate_real_manifest.jsonl")
DEFAULT_OUT = Path("eval/locate_real.csv")
MAX_VERSIONS = 5  # thresholds versions named in the file's heading; one is the normal case


class ManifestRow(BaseModel):
    photo: str  # path to the image, relative to the manifest's folder
    claimed_property_id: str
    floor_plan: str | None = None  # the floor plan the photo shows, when the kit says
    decoy: bool = False  # a photo of some other building


class Placement(BaseModel):
    """What the locator says about one photo."""

    status: LocateStatus
    floor_plan: str | None = None
    thresholds_version: str | None = None  # which thresholds the locator used, when it says
    # False when the locator never ran on the photo (it ran out of time, say). "Not indexed"
    # is never tested, whatever this says.
    tested: bool = True


Locator = Callable[[Path, str], Placement]


class LocateRealResult(BaseModel):
    """Totals only. Nothing here names a photo or a building."""

    photos: int = 0  # the buildings' own photos
    right_building: int = 0
    wrong_building: int = 0  # placed, but in another building
    photos_with_floor_plan: int = 0
    right_floor_plan: int = 0  # right building and right floor plan
    decoys: int = 0
    decoy_false_placements: int = 0  # a decoy placed in the claimed building: "taken here"
    decoys_placed_elsewhere: int = 0  # a decoy placed in some other building
    photos_not_tested: int = 0  # own photos the locator never ran on
    decoys_not_tested: int = 0  # decoys the locator never ran on
    failed: int = 0  # photos the locator raised on; not tested, and counted as not placed
    thresholds_versions: list[str] = Field(default_factory=list)  # as the locator named them


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
            # One unreadable photo must not stop the run. It was not placed, and not tested.
            placement = Placement(status=LocateStatus.NOT_LOCATED, tested=False)
            result.failed += 1
        # No twin to look in, no time, or no readable file: the locator did not run on it.
        tested = placement.tested and placement.status is not LocateStatus.NOT_INDEXED

        version = placement.thresholds_version
        if version and version not in result.thresholds_versions:
            result.thresholds_versions.append(version)

        in_claimed = placement.status is LocateStatus.LOCATED_IN_CLAIMED
        elsewhere = placement.status is LocateStatus.LOCATED_ELSEWHERE
        if row.decoy:
            # A decoy read as "taken here" is the false placement. Placed in another
            # building is what locate should say about a photo of another building.
            result.decoys += 1
            result.decoys_not_tested += not tested
            result.decoy_false_placements += in_claimed
            result.decoys_placed_elsewhere += elsewhere
            continue

        result.photos += 1
        result.photos_not_tested += not tested
        result.right_building += in_claimed
        result.wrong_building += elsewhere
        if row.floor_plan is not None:
            result.photos_with_floor_plan += 1
            result.right_floor_plan += in_claimed and placement.floor_plan == row.floor_plan
    return result


def _counts(result: LocateRealResult) -> list[tuple[str, int, int]]:
    """(metric, k, n) for each count that has something under it.

    The counts whose target is 0 are over the photos the locator actually ran on. A photo it
    never ran on cannot have been placed wrongly, and must not make those counts look good.
    """
    photos_tested = result.photos - result.photos_not_tested
    decoys_tested = result.decoys - result.decoys_not_tested
    counts = [
        ("right_building", result.right_building, result.photos),
        ("right_floor_plan", result.right_floor_plan, result.photos_with_floor_plan),
        ("wrong_building", result.wrong_building, photos_tested),
        ("photo_not_tested", result.photos_not_tested, result.photos),
        ("decoy_false_placement", result.decoy_false_placements, decoys_tested),
        ("decoy_placed_elsewhere", result.decoys_placed_elsewhere, decoys_tested),
        ("decoy_not_tested", result.decoys_not_tested, result.decoys),
    ]
    return [count for count in counts if count[2] > 0]


def write_csv(result: LocateRealResult, path: Path, *, source: str, frozen_at: str) -> None:
    """Write the totals in the Lab panel's format. `source` is "live" or "fixture".

    The file is written beside its place and then renamed onto it, so a reader gets the old
    file or the new one and never half of either.
    """
    lines = [
        f"# {source.upper()}: locate over the buildings' own listing photos, and decoys.",
        "# k of n photos placed. decoy_false_placement: k of n decoys read as taken in the "
        "claimed building (target 0).",
        "# wrong_building and the decoy counts are over photos the locator ran on. "
        "photo_not_tested and decoy_not_tested: how many it never ran on.",
    ]
    if result.thresholds_versions:
        # Which bars the matches had to clear, by lane V's own name for them. Not a number.
        named = ", ".join(result.thresholds_versions[:MAX_VERSIONS])
        lines.append(f"# thresholds: {named}")
    lines.append(",".join(COLUMNS))
    for metric, k, n in _counts(result):
        low, high = wilson(k, n)
        lines.append(f"{CONDITION},{metric},{k},{n},{k / n:.4f},{low:.4f},{high:.4f},{frozen_at}")

    path.parent.mkdir(parents=True, exist_ok=True)
    beside = path.with_name(path.name + ".tmp")
    beside.write_text("\n".join(lines) + "\n")
    beside.replace(path)


# --- the product's own locator -------------------------------------------------------------


# What lane A's live locate (A22) names the thresholds of a photo it ran out of time on. A
# test runs with no time at all and holds this to what `LiveLocate` really says.
_OUT_OF_TIME = "live-budget"


class _FreshLiveLocate(LiveLocate):
    """The product's live locate (A22) with its saved answers switched off.

    A live case reads an answer saved for the same photos before it runs the model. An
    accuracy run must not: it would score what an earlier run stored. Nothing is saved
    either, so an eval never plants answers a later case would pick up.
    """

    def _read_cache(self, path: Path) -> LiveOutcome | None:
        return None

    def _write_cache(self, path: Path, outcome: LiveOutcome) -> None:
        return None


def live_for_eval(
    settings: Settings,
    *,
    records: Callable[[], Iterable[PropertyRecord]],
    **options: object,
) -> LiveLocate:
    """The locator a live case uses, from the same settings: the same index and the same time
    budget. No thresholds are passed, so lane V's `Locator` loads its own config file. The
    options are for tests (fixture faces, the numpy matcher)."""
    return _FreshLiveLocate(
        data_dir=settings.snapback_data_dir,
        records=records,
        index_name=settings.snapback_locate_index,
        budget_s=settings.snapback_locate_budget_s,
        **options,  # type: ignore[arg-type]
    )


def product_locator(live: LiveLocate) -> Locator:
    """`live`, asked about one photo at a time, as the harness's `Locator`.

    A claimed building with no twin in the index comes back "not indexed" from lane V's
    locator itself, without the model being run, exactly as in a live case.
    """

    def locate(photo: Path, claimed_property_id: str) -> Placement:
        outcome = live.locate("eval", [photo.read_bytes()], claimed_property_id)
        if outcome is None or not outcome.result.photos:
            return Placement(status=LocateStatus.NOT_INDEXED, tested=False)
        placed = outcome.result.photos[0]
        chosen = outcome.result.chosen
        in_claimed = placed.status is LocateStatus.LOCATED_IN_CLAIMED
        version = outcome.result.thresholds_version
        ran_out_of_time = version == _OUT_OF_TIME
        return Placement(
            status=placed.status,
            floor_plan=chosen.floor_plan if in_claimed and chosen is not None else None,
            thresholds_version=None if ran_out_of_time else version,
            tested=not ran_out_of_time,
        )

    return locate


def _product(settings: Settings) -> Locator | str:
    """The product's locator on this machine, or one line saying what is missing."""
    from snapback.agent.join import KitLookups

    lookups = KitLookups(settings.snapback_data_source)
    live = live_for_eval(settings, records=lambda: lookups.records().values())
    if not live.available(None, []):
        index = Path(settings.snapback_data_dir) / "index" / settings.snapback_locate_index
        return (
            f"The locator is not available here. It needs an index at {index}, the kit's "
            "records and, for a live run, the vision extra (uv sync --extra vision)."
        )
    return product_locator(live)


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
    parser.add_argument(
        "--locator",
        help="module:function to score in place of the product's own locator",
    )
    parser.add_argument("--source", choices=("live", "fixture"), default="live")
    args = parser.parse_args(argv)

    if not args.manifest.is_file():
        print(
            f"No manifest at {args.manifest}. It is written from the kit; see #72.", file=sys.stderr
        )
        return 2
    if args.locator:
        try:
            locate = _load_locator(args.locator)
        except (ImportError, AttributeError, ValueError):
            print(f"No locator at {args.locator}. Pass module:function.", file=sys.stderr)
            return 2
    else:
        settings = Settings().model_copy(update={"snapback_data_source": DataSource(args.source)})
        found = _product(settings)
        if isinstance(found, str):
            print(found, file=sys.stderr)
            return 2
        locate = found

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
    if result.photos_not_tested or result.decoys_not_tested:
        print(
            f"NOT TESTED: the locator never ran on {result.photos_not_tested} photos and "
            f"{result.decoys_not_tested} decoys (no twin in the index, out of time, or "
            "unreadable). They are not counted as passes. Fix the manifest or the index, or "
            "give it more time, before quoting this."
        )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
