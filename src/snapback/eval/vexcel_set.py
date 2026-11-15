"""The Vexcel labelled set: does the aerial of the claimed address show the ad's building?

A case is a claimed address, the building the ad is really for, and a label: "right" (the same
building) or "wrong" (an ad claiming a nearby address). `aerial_match` is the check; `run_cases`
scores it against the labels. The bar is 18 of 20 (90 percent, at least 20 cases). The
SNAPBACK_VEXCEL_IN_VERDICT setting may be turned on only when a LIVE run meets it; a FIXTURE run
measures the geometry only, so it never opens the gate.

Case files that hold real CoStar addresses live under data/ (git-ignored, never committed).
`results.json` holds counts and case ids only, never an address or a property id.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from snapback.adapters import vexcel
from snapback.contracts import AerialResult, AerialStatus, DataSource, PropertyRecord

SAME_BUILDING_M = 25.0  # two points this close are one building
HASH_MAX_DIFF = 8  # of 64 bits: tiles this alike show the same building
WRONG_MIN_M, WRONG_MAX_M = 40.0, 500.0  # a nearby address: a different building, same street area
BAR_MIN_N = 20
BAR_RATE = 0.9  # 18 of 20

TileFn = Callable[..., Any]


def _dhash(path: str) -> int | None:
    from PIL import Image

    try:
        with Image.open(path) as img:
            px = img.convert("L").resize((9, 8)).tobytes()
    except (OSError, ValueError):
        return None
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return bits


def aerial_match(
    claimed: PropertyRecord,
    expected: PropertyRecord,
    *,
    source: DataSource,
    tile_fn: TileFn = vexcel.get_tile,
) -> AerialResult:
    """Is the aerial of `claimed` the building `expected` (where the ad really is)?

    FIXTURE: the points are within SAME_BUILDING_M. LIVE: the two Vexcel tiles look alike
    (perceptual hash). A missing tile, key or coordinate says nothing (NOT_CHECKED)."""
    dist = vexcel.distance_m(claimed, expected)
    if dist is None:
        return AerialResult()
    if source == DataSource.FIXTURE:
        same = dist <= SAME_BUILDING_M
    else:
        try:
            tiles = [tile_fn(r, "north", source=DataSource.LIVE) for r in (claimed, expected)]
        except (vexcel.VexcelKeyMissingError, OSError):
            return AerialResult(distance_m=round(dist, 1))
        if any(t is None or not t.path for t in tiles):
            return AerialResult(distance_m=round(dist, 1))
        a, b = (_dhash(t.path) for t in tiles)
        if a is None or b is None:
            return AerialResult(distance_m=round(dist, 1))
        same = bin(a ^ b).count("1") <= HASH_MAX_DIFF
    return AerialResult(
        status=AerialStatus.RIGHT_BUILDING if same else AerialStatus.WRONG_BUILDING,
        distance_m=round(dist, 1),
    )


def _record(pid: str, prop: dict[str, Any], source: DataSource) -> PropertyRecord:
    return PropertyRecord(property_id=pid, source=source, lat=prop.get("lat"), lon=prop.get("lon"))


def run_cases(
    doc: dict[str, Any], *, source: DataSource, tile_fn: TileFn = vexcel.get_tile
) -> dict[str, Any]:
    props = doc["properties"]
    hits, misses, wrong_n = 0, [], 0
    for case in doc["cases"]:
        wrong_n += case["label"] == "wrong"
        claimed = _record(case["claimed_property_id"], props[case["claimed_property_id"]], source)
        expected = _record(
            case["expected_property_id"], props[case["expected_property_id"]], source
        )
        got = aerial_match(claimed, expected, source=source, tile_fn=tile_fn).status
        want = (
            AerialStatus.RIGHT_BUILDING
            if case["label"] == "right"
            else (AerialStatus.WRONG_BUILDING)
        )
        if got is want:
            hits += 1
        else:
            misses.append(case["case_id"])
    n = len(doc["cases"])
    bar_met = n >= BAR_MIN_N and hits / n >= BAR_RATE
    mode = "live" if source == DataSource.LIVE else "fixture"
    return {
        "mode": mode,
        "n": n,
        "wrong_building_cases": wrong_n,
        "hits": hits,
        "misses": misses,
        "bar": "18 of 20 (at least 20 cases, 90 percent)",
        "bar_met": bar_met,
        # Only a LIVE pass lets SNAPBACK_VEXCEL_IN_VERDICT be turned on.
        "gate_open": bar_met and mode == "live",
        "synthetic_cases": bool(doc.get("synthetic")),
    }


def write_results(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def _dist(a: dict[str, Any], b: dict[str, Any]) -> float:
    ra, rb = (
        PropertyRecord(
            property_id="x", source=DataSource.FIXTURE, **{"lat": p["lat"], "lon": p["lon"]}
        )
        for p in (a, b)
    )
    return vexcel.distance_m(ra, rb) or math.inf


def build_cases(
    rows: list[dict[str, Any]], *, n_right: int = 14, n_wrong: int = 10
) -> dict[str, Any]:
    """Cases from listing rows {propertyId, address, lat, lon}, deterministically.

    Right: the ad's building and the claimed address are the same property. Wrong: the ad is for
    one property and claims the address of the nearest other property 40 to 500 m away."""
    props: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda r: str(r["propertyId"])):
        if row.get("lat") is None or row.get("lon") is None or not row.get("address"):
            continue
        props.setdefault(
            str(row["propertyId"]),
            {"address": row["address"], "lat": row["lat"], "lon": row["lon"]},
        )
    ids = list(props)
    pairs: list[tuple[str, str, float]] = []  # (expected, claimed, metres)
    for pid in ids:
        near = [
            (other, d)
            for other in ids
            if other != pid and WRONG_MIN_M <= (d := _dist(props[pid], props[other])) <= WRONG_MAX_M
        ]
        if near:
            other, d = min(near, key=lambda t: t[1])
            pairs.append((pid, other, round(d, 1)))
    step = max(1, len(pairs) // max(n_wrong, 1))
    wrong = pairs[::step][:n_wrong]
    used = {e for e, _, _ in wrong} | {c for _, c, _ in wrong}
    free = [p for p in ids if p not in used]
    step = max(1, len(free) // max(n_right, 1))
    right = free[::step][:n_right]
    cases = [
        {
            "case_id": f"vx-r{i + 1:02d}",
            "claimed_address": props[p]["address"],
            "claimed_property_id": p,
            "expected_property_id": p,
            "label": "right",
        }
        for i, p in enumerate(right)
    ] + [
        {
            "case_id": f"vx-w{i + 1:02d}",
            "claimed_address": props[c]["address"],
            "claimed_property_id": c,
            "expected_property_id": e,
            "label": "wrong",
            "distance_m": d,
        }
        for i, (e, c, d) in enumerate(wrong)
    ]
    keep = {c["claimed_property_id"] for c in cases} | {c["expected_property_id"] for c in cases}
    return {"properties": {p: props[p] for p in keep}, "cases": cases}
