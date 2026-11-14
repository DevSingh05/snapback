"""`uv run python -m snapback.eval`: score the case bank, write results.csv, run the gate.

Exit code 1 when the gate fails: an injection case changed a state, or a gated false-accept
rate rose over `--baseline`.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from snapback.eval.bank import FIXTURE_BANK, REPO_ROOT, load_bank
from snapback.eval.harness import check_injections, check_regression, evaluate
from snapback.eval.results import read_results, write_results

DEFAULT_OUT = REPO_ROOT / "data" / "eval" / "results.csv"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m snapback.eval", description=__doc__)
    parser.add_argument("--bank", type=Path, default=FIXTURE_BANK, help="case bank (.jsonl)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="results.csv to write")
    parser.add_argument(
        "--models", nargs="*", default=["v0"], help="recapture versions, oldest first"
    )
    parser.add_argument("--split", default="h0", help="split to score; 'all' for every case")
    parser.add_argument(
        "--baseline", type=Path, help="earlier results.csv the run must not lose to"
    )
    parser.add_argument("--frozen-at", help="H0 freeze tag; FIXTURE for the synthetic bank")
    args = parser.parse_args(argv)

    cases = load_bank(args.bank)
    synthetic = all(case.synthetic for case in cases)
    frozen_at = args.frozen_at or ("FIXTURE" if synthetic else "unfrozen")
    split = None if args.split == "all" else args.split

    rows = evaluate(cases, args.models, split=split, frozen_at=frozen_at)
    label = "FIXTURE: synthetic case bank, not a measurement" if synthetic else "LIVE"
    write_results(rows, args.out, comment=f"{label}. bank={args.bank.name} split={args.split}")
    print(f"wrote {len(rows)} rows to {args.out} ({len(cases)} cases in the bank)")

    failures = check_injections(cases)
    if args.baseline is not None:
        failures += check_regression(rows, read_results(args.baseline))
    for failure in failures:
        print(f"gate: FAIL {failure}")
    if failures:
        return 1
    print("gate: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
