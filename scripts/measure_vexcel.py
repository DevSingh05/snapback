#!/usr/bin/env python3
"""One command for the Vexcel measurement.

    uv run python scripts/measure_vexcel.py   # LIVE if a Vexcel key is configured, else FIXTURE
    uv run python scripts/measure_vexcel.py --mode live
    uv run python scripts/measure_vexcel.py --mode fixture

Cases: data/vexcel_eval/cases.json if present; else built from the local CoStar kit
(residential listings, Houston) and saved there (git-ignored); else the committed synthetic set
eval/vexcel/cases.fixture.json. Prints n, hits, misses and pass/fail against the 18-of-20 bar,
and writes eval/vexcel/results.json (counts and case ids only). Only a LIVE pass lets
SNAPBACK_VEXCEL_IN_VERDICT be turned on. No key value is ever read or printed here: only whether
one is configured.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from snapback.contracts import DataSource  # noqa: E402
from snapback.eval import vexcel_set  # noqa: E402
from snapback.settings import get_settings  # noqa: E402

FIXTURE_CASES = REPO / "eval" / "vexcel" / "cases.fixture.json"
RESULTS = REPO / "eval" / "vexcel" / "results.json"
KIT_LISTINGS = "residential-listings.jsonl"


def key_configured() -> bool:
    return get_settings().vexcel_api_key is not None


def kit_rows(data_dir: Path) -> list[dict]:
    path = next((data_dir / "raw" / "costar").rglob(KIT_LISTINGS), None)
    if path is None:
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        addr = (obj.get("property") or {}).get("address") or {}
        if addr.get("city") == "Houston":
            rows.append(
                {
                    "propertyId": obj.get("propertyId"),
                    "address": addr.get("fullStreetAddress"),
                    "lat": addr.get("latitude"),
                    "lon": addr.get("longitude"),
                }
            )
    return rows


def load_cases(cases: Path | None, data_dir: Path) -> tuple[dict, str]:
    local = data_dir / "vexcel_eval" / "cases.json"
    if cases:
        return json.loads(cases.read_text(encoding="utf-8")), cases.name  # no local path
    if local.is_file():
        return json.loads(local.read_text(encoding="utf-8")), "local kit set"
    rows = kit_rows(data_dir)
    if rows:
        doc = vexcel_set.build_cases(rows)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        return doc, "local kit set (built now)"
    return json.loads(FIXTURE_CASES.read_text(encoding="utf-8")), "committed synthetic set"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mode", choices=["auto", "fixture", "live"], default="auto")
    ap.add_argument("--cases", type=Path, default=None)
    ap.add_argument("--data-dir", type=Path, default=REPO / "data")
    ap.add_argument("--out", type=Path, default=None, help="results file (default results.json)")
    args = ap.parse_args(argv)

    have_key = key_configured()
    print(f"Vexcel key configured: {have_key}")
    live = args.mode == "live" or (args.mode == "auto" and have_key)
    if live and not have_key:
        print("LIVE needs a Vexcel key in the environment; none is configured.")
        return 2
    doc, where = load_cases(args.cases, args.data_dir)
    source = DataSource.LIVE if live else DataSource.FIXTURE
    cpu0, wall0 = time.process_time(), time.perf_counter()
    result = vexcel_set.run_cases(doc, source=source)
    per_pair = {
        "cpu_ms": round((time.process_time() - cpu0) * 1000 / max(result["n"], 1)),
        "wall_ms": round((time.perf_counter() - wall0) * 1000 / max(result["n"], 1)),
    }
    result["per_pair"] = per_pair
    result["cases_from"] = where
    vexcel_set.write_results(result, args.out or RESULTS)

    print(f"mode: {result['mode'].upper()}  cases: {where}")
    print(f"n={result['n']}  wrong-building cases={result['wrong_building_cases']}")
    print(f"hits={result['hits']}  misses={result['misses']}")
    print(f"right={result['right_cases']}  next-door={result['next_door']}")
    print(f"by kind: {result['by_kind']}")
    print(f"thresholds in use: {result['thresholds']}")
    print(f"inlier ranges: {result['inlier_range']}")
    print(f"offset ranges (m): {result['offset_m_range']}")
    print(f"v1 hash-diff ranges, for comparison: {result['hash_diff_range']}")
    print(f"per pair (tiles cached, includes the v1 hash): {per_pair}")
    if result["split"]:
        sp = result["split"]
        print(f"split: tuned on half -> {sp['tuned']}")
        print(f"  tune half: {sp['tune']}")
        print(f"  HELD-OUT:  {sp['held_out']}")
        print(f"  all n with tuned thresholds: {sp['all_with_tuned']}")
    passed = result["bar_met"] and result["next_door_ok"]
    print(f"bar {result['bar']}: {'PASS' if passed else 'FAIL'}")
    print(f"gate ({result['gate']}): {'MET' if result['gate_met'] else 'NOT MET'}")
    if result["mode"] == "fixture":
        print("FIXTURE measures the geometry only; it does not open the verdict gate.")
    elif result["gate_open"]:
        print("LIVE pass: SNAPBACK_VEXCEL_IN_VERDICT may be turned on.")
    print(f"wrote {args.out or RESULTS.relative_to(REPO)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
