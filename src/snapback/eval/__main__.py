"""`uv run python -m snapback.eval`: score the case bank, write results.csv, run the gate.

Exit code 1 when the gate fails: an injection case changed a state, a device or room in H0
is also in dev, or the run is worse than (or not comparable to) `--baseline`. Exit code 2 when
the run cannot be made (a requested model has no results); nothing is written then.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from snapback.eval.bank import FIXTURE_BANK, REPO_ROOT, bank_digest, load_bank
from snapback.eval.harness import check_holdout, check_injections, check_regression, evaluate
from snapback.eval.results import read_meta, read_results, write_results

# Git-tracked: aggregate numbers only. The API serves this file at GET /eval/results.csv.
DEFAULT_OUT = REPO_ROOT / "eval" / "results.csv"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m snapback.eval", description=__doc__)
    parser.add_argument("--bank", type=Path, default=FIXTURE_BANK, help="case bank (.jsonl)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="results.csv to write")
    parser.add_argument(
        "--models", nargs="*", default=["v0", "v1"], help="recapture versions, oldest first"
    )
    parser.add_argument("--split", default="h0", help="split to score; 'all' for every case")
    parser.add_argument(
        "--baseline", type=Path, help="earlier results.csv the run must not lose to"
    )
    parser.add_argument("--frozen-at", help="H0 freeze tag; FIXTURE for the synthetic bank")
    args = parser.parse_args(argv)

    cases = load_bank(args.bank)
    split = None if args.split == "all" else args.split
    scored = [case for case in cases if split is None or case.split == split]
    kinds = {case.synthetic for case in scored}
    if len(kinds) > 1:
        # One n would mix synthetic and real cases, and one label could not be true for both.
        print(
            f"eval: the scored cases mix synthetic ({sum(c.synthetic for c in scored)}) and real "
            f"({sum(not c.synthetic for c in scored)}) cases; score them as separate banks"
        )
        return 2
    synthetic = kinds != {False}
    frozen_at = args.frozen_at or ("FIXTURE" if synthetic else "unfrozen")

    try:
        rows = evaluate(cases, args.models, split=split, frozen_at=frozen_at)
    except ValueError as error:
        print(f"eval: {error}")
        return 2
    label = "FIXTURE: synthetic case bank, not a measurement" if synthetic else "LIVE"
    meta = {
        "split": args.split,
        "bank": args.bank.name,
        "bank_sha256": bank_digest(args.bank),
        "models": ",".join(args.models),
    }

    failures = check_injections(cases) + check_holdout(cases)
    if args.baseline is not None:
        failures += check_regression(
            rows,
            read_results(args.baseline),
            meta=meta,
            baseline_meta=read_meta(args.baseline),
        )
    for failure in failures:
        print(f"gate: FAIL {failure}")
    if failures:
        # Nothing is written: the results file the API serves stays the last one that passed.
        print(f"gate failed: {args.out} left as it was")
        return 1
    write_results(rows, args.out, comment=label, meta=meta)
    print(f"wrote {len(rows)} rows to {args.out} ({len(cases)} cases in the bank)")
    print("gate: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
