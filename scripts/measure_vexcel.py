#!/usr/bin/env python3
"""One command for the Vexcel measurement.

    uv run python scripts/measure_vexcel.py   # LIVE if a Vexcel key is configured, else FIXTURE
    uv run python scripts/measure_vexcel.py --mode live
    uv run python scripts/measure_vexcel.py --mode fixture
    uv run python scripts/measure_vexcel.py --ablation   # LIVE: image+footprint vs footprint-only

Cases: data/vexcel_eval/cases_v2.json (n=54, built by vexcel_set.extend_cases) or cases.json
(n=28) if present; else built from the local CoStar kit
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

from snapback.adapters import footprints  # noqa: E402
from snapback.contracts import DataSource  # noqa: E402
from snapback.eval import vexcel_set  # noqa: E402
from snapback.settings import get_settings  # noqa: E402

FIXTURE_CASES = REPO / "eval" / "vexcel" / "cases.fixture.json"
RESULTS = REPO / "eval" / "vexcel" / "results.json"
ABLATION = REPO / "eval" / "vexcel" / "ablation.json"
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
    extended = data_dir / "vexcel_eval" / "cases_v2.json"  # the n=54 set (superset of cases.json)
    if cases:
        return json.loads(cases.read_text(encoding="utf-8")), cases.name  # no local path
    if extended.is_file():
        return json.loads(extended.read_text(encoding="utf-8")), "local kit set, extended"
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
    ap.add_argument(
        "--ablation",
        action="store_true",
        help="LIVE: nadir tiles + the claimed footprint vs footprint-only (coordinates)",
    )
    args = ap.parse_args(argv)
    if args.ablation:
        return ablation(args)

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


def ablation(args: argparse.Namespace) -> int:
    """Both arms on the held-out half; the image arm must pass the gate AND beat footprint-only."""
    if not key_configured():
        print("The ablation is LIVE only and needs a Vexcel key; none is configured.")
        return 2
    doc, where = load_cases(args.cases, args.data_dir)
    cache = args.data_dir / "footprints"  # git-ignored, like every data/ path
    result = vexcel_set.run_ablation(
        doc, footprint_fn=lambda lat, lon: footprints.fetch(lat, lon, cache_dir=cache)
    )
    out = args.out or ABLATION
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"cases: {where}  n={result['n']}  held-out n={len(result['held_out_ids'])}")
    for arm in vexcel_set.ARMS:
        print(f"{arm:16} HELD-OUT {result['arms'][arm]['held_out']}")
        print(f"{'':16} all      {result['arms'][arm]['all']}")
    print(f"held-out hits: {result['held_out_hits']}")
    print(f"image+footprint meets the gate: {result['image_gate_met']}")
    print(f"beats footprint-only: {result['beats_footprint_only']}")
    closed = "gate closed: SNAPBACK_VEXCEL_IN_VERDICT stays off"
    print("GATE OPEN" if result["gate_open"] else closed)
    print(f"wrote {out}")
    return 0 if result["gate_open"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
