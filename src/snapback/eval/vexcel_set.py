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

SAME_BUILDING_M = 12.0  # two points this close are one building (right cases are offset 8 m)
HASH_MAX_DIFF = 8  # of 64 bits: tiles this alike show the same building
NEXT_DOOR_MIN_M, NEXT_DOOR_MAX_M = 15.0, 50.0  # the nearest other building, same block
WRONG_MIN_M, WRONG_MAX_M = 50.0, 500.0  # a nearby address on the street area
RIGHT_OFFSET_M = 8.0  # the right case's second tile is centred this far from the first
BAR_MIN_N = 20
BAR_RATE = 0.9  # 18 of 20
NEXT_DOOR_MIN_N = 6

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
        diff = None
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
        diff = bin(a ^ b).count("1")
        same = diff <= HASH_MAX_DIFF
    return AerialResult(
        status=AerialStatus.RIGHT_BUILDING if same else AerialStatus.WRONG_BUILDING,
        distance_m=round(dist, 1),
        hash_diff=diff,
    )


def _record(pid: str, prop: dict[str, Any], source: DataSource) -> PropertyRecord:
    return PropertyRecord(property_id=pid, source=source, lat=prop.get("lat"), lon=prop.get("lon"))


def _shifted(record: PropertyRecord, metres: float) -> PropertyRecord:
    """The same building with the tile centre moved north by `metres`, under its own cache key."""
    return record.model_copy(
        update={
            "property_id": f"{record.property_id}~off",
            "lat": (record.lat or 0.0) + metres / 111_320,
        }
    )


def _range(values: list[int]) -> list[int] | None:
    return [min(values), max(values)] if values else None


def run_cases(
    doc: dict[str, Any], *, source: DataSource, tile_fn: TileFn = vexcel.get_tile
) -> dict[str, Any]:
    props = doc["properties"]
    hits, misses, wrong_n = 0, [], 0
    kinds: dict[str, dict[str, int]] = {}
    diffs: dict[str, list[int]] = {}
    for case in doc["cases"]:
        wrong_n += case["label"] == "wrong"
        claimed = _record(case["claimed_property_id"], props[case["claimed_property_id"]], source)
        expected = _record(
            case["expected_property_id"], props[case["expected_property_id"]], source
        )
        if case.get("expected_offset_m"):
            expected = _shifted(expected, float(case["expected_offset_m"]))
        found = aerial_match(claimed, expected, source=source, tile_fn=tile_fn)
        want = (
            AerialStatus.RIGHT_BUILDING if case["label"] == "right" else AerialStatus.WRONG_BUILDING
        )
        kind = case.get("kind") or ("right" if case["label"] == "right" else "wrong")
        tally = kinds.setdefault(kind, {"n": 0, "hits": 0})
        tally["n"] += 1
        if found.hash_diff is not None:
            diffs.setdefault(kind, []).append(found.hash_diff)
        if found.status is want:
            hits += 1
            tally["hits"] += 1
        else:
            misses.append(case["case_id"])
    n = len(doc["cases"])
    bar_met = n >= BAR_MIN_N and hits / n >= BAR_RATE
    nd = kinds.get("next_door", {"n": 0, "hits": 0})
    next_door_ok = nd["n"] >= NEXT_DOOR_MIN_N and nd["hits"] / nd["n"] >= BAR_RATE
    mode = "live" if source == DataSource.LIVE else "fixture"
    return {
        "mode": mode,
        "n": n,
        "right_cases": kinds.get("right", {"n": 0})["n"],
        "wrong_building_cases": wrong_n,
        "hits": hits,
        "misses": misses,
        "next_door": nd,
        "by_kind": kinds,
        "hash_diff_range": {k: _range(v) for k, v in diffs.items()},
        "hash_threshold": HASH_MAX_DIFF,
        "bar": "18 of 20 (at least 20 cases, 90 percent), and 6+ next-door cases at 90 percent",
        "bar_met": bar_met,
        "next_door_ok": next_door_ok,
        # Only a LIVE pass, next-door cases included, lets SNAPBACK_VEXCEL_IN_VERDICT be on.
        "gate_open": bar_met and next_door_ok and mode == "live",
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


def _nearest(
    props: dict[str, dict[str, Any]], ids: list[str], lo: float, hi: float
) -> list[tuple[str, str, float]]:
    """(expected, claimed, metres): each property's nearest other one, if lo..hi metres away."""
    out = []
    for pid in ids:
        others = [(d, o) for o in ids if o != pid and (d := _dist(props[pid], props[o])) < hi * 4]
        if not others:
            continue
        d, other = min(others)
        if lo <= d < hi:
            out.append((pid, other, round(d, 1)))
    return out


def build_cases(
    rows: list[dict[str, Any]], *, n_right: int = 12, n_next_door: int = 8, n_wrong: int = 8
) -> dict[str, Any]:
    """Cases from listing rows {propertyId, address, lat, lon}, deterministically.

    right: the ad and the claimed address are one property, and the second tile is centred
    RIGHT_OFFSET_M away, so it is not the same picture. next_door: the ad is for one property and
    claims the address of its nearest neighbour, 15 to 50 m away (same block). wrong: the same,
    but the nearest neighbour is 50 to 500 m away."""
    props: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda r: str(r["propertyId"])):
        if row.get("lat") is None or row.get("lon") is None or not row.get("address"):
            continue
        props.setdefault(
            str(row["propertyId"]),
            {"address": row["address"], "lat": row["lat"], "lon": row["lon"]},
        )
    ids = list(props)
    used: set[str] = set()

    def take(pairs: list[tuple[str, str, float]], count: int) -> list[tuple[str, str, float]]:
        free = [p for p in pairs if p[0] not in used and p[1] not in used]
        step = max(1, len(free) // max(count, 1))
        chosen = []
        for pair in free[::step]:
            if len(chosen) == count:
                break
            if pair[0] in used or pair[1] in used:
                continue
            chosen.append(pair)
            used.update(pair[:2])
        return chosen

    next_door = take(_nearest(props, ids, NEXT_DOOR_MIN_M, NEXT_DOOR_MAX_M), n_next_door)
    wrong = take(_nearest(props, ids, WRONG_MIN_M, WRONG_MAX_M), n_wrong)
    free = [p for p in ids if p not in used]
    step = max(1, len(free) // max(n_right, 1))
    right = free[::step][:n_right]

    def wrong_case(prefix: str, kind: str, i: int, e: str, c: str, d: float) -> dict[str, Any]:
        return {
            "case_id": f"vx-{prefix}{i + 1:02d}",
            "kind": kind,
            "claimed_address": props[c]["address"],
            "claimed_property_id": c,
            "expected_property_id": e,
            "label": "wrong",
            "distance_m": d,
        }

    cases = (
        [
            {
                "case_id": f"vx-r{i + 1:02d}",
                "kind": "right",
                "claimed_address": props[p]["address"],
                "claimed_property_id": p,
                "expected_property_id": p,
                "expected_offset_m": RIGHT_OFFSET_M,
                "label": "right",
            }
            for i, p in enumerate(right)
        ]
        + [wrong_case("n", "next_door", i, *t) for i, t in enumerate(next_door)]
        + [wrong_case("w", "wrong", i, *t) for i, t in enumerate(wrong)]
    )
    keep = {c["claimed_property_id"] for c in cases} | {c["expected_property_id"] for c in cases}
    return {"properties": {p: props[p] for p in keep}, "cases": cases}
