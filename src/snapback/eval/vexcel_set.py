"""The Vexcel labelled set: does the aerial of the claimed address show the ad's building?

A case is a claimed address, the building the ad is really for, and a label: "right" (the same
building) or "wrong" (an ad claiming a nearby address). `aerial_match` is the check; `run_cases`
scores it against the labels. The bar is 18 of 20 (90 percent, at least 20 cases). LIVE runs also
tune the matcher thresholds on one half of the cases and score the other half; the
SNAPBACK_VEXCEL_IN_VERDICT setting may be turned on only when that held-out half meets GATE_RATES.
A FIXTURE run measures the geometry only, so it never opens the gate.

Case files that hold real CoStar addresses live under data/ (git-ignored, never committed).
`results.json` holds counts and case ids only, never an address or a property id.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from snapback.adapters import vexcel, vexcel_match
from snapback.contracts import AerialResult, AerialStatus, DataSource, PropertyRecord

SAME_BUILDING_M = 12.0  # two points this close are one building (right cases are offset 8 m)
HASH_MAX_DIFF = 8  # of 64 bits; reported only, for comparison (v1 matcher; it cannot separate)
NEXT_DOOR_MIN_M, NEXT_DOOR_MAX_M = 15.0, 50.0  # the nearest other building, same block
WRONG_MIN_M, WRONG_MAX_M = 50.0, 500.0  # a nearby address on the street area
RIGHT_OFFSET_M = 8.0  # the right case's second tile is centred this far from the first
BAR_MIN_N = 20
BAR_RATE = 0.9  # 18 of 20
NEXT_DOOR_MIN_N = 6
# The verdict gate, on the held-out half (thresholds tuned on the other half): right and next-door
# at least 90 percent each, other wrong 100 percent.
GATE_RATES = {"right": 0.9, "next_door": 0.9, "wrong": 1.0}

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

    FIXTURE: the points are within SAME_BUILDING_M. LIVE: matcher v2 (vexcel_match) finds the
    claimed tile's middle inside the ad's tile, with enough RANSAC inliers, within MAX_OFFSET_M of
    its centre. A missing tile, key, coordinate or opencv says nothing (NOT_CHECKED)."""
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
        geo = vexcel_match.geo_match(tiles[0].path, tiles[1].path)
        if geo is None:
            return AerialResult(distance_m=round(dist, 1))
        a, b = (_dhash(t.path) for t in tiles)
        diff = bin(a ^ b).count("1") if a is not None and b is not None else None
        return AerialResult(
            status=_status(vexcel_match.same_building(geo)),
            distance_m=round(dist, 1),
            hash_diff=diff,
            inliers=geo.inliers,
            offset_m=geo.offset_m,
        )
    return AerialResult(status=_status(same), distance_m=round(dist, 1), hash_diff=diff)


def _status(same: bool) -> AerialStatus:
    return AerialStatus.RIGHT_BUILDING if same else AerialStatus.WRONG_BUILDING


def _record(pid: str, prop: dict[str, Any], source: DataSource) -> PropertyRecord:
    return PropertyRecord(property_id=pid, source=source, lat=prop.get("lat"), lon=prop.get("lon"))


def _shifted(record: PropertyRecord, metres: float) -> PropertyRecord:
    """The same building with the tile centre moved north by `metres`, under its own cache key."""
    return record.model_copy(
        update={
            "property_id": f"{record.property_id}~off{metres:g}",
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
    inliers: dict[str, list[int]] = {}
    offsets: dict[str, list[float]] = {}
    rows: list[dict[str, Any]] = []
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
        if found.inliers is not None:
            inliers.setdefault(kind, []).append(found.inliers)
            rows.append(
                {
                    "case_id": case["case_id"],
                    "kind": kind,
                    "label": case["label"],
                    "inliers": found.inliers,
                    "offset_m": found.offset_m,
                }
            )
        if found.offset_m is not None:
            offsets.setdefault(kind, []).append(found.offset_m)
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
    split = _split_report(rows) if len(rows) == n and n else None
    held_ok = split is not None and gate_met(split["held_out"])
    return {
        "mode": mode,
        "matcher": "v2: SIFT + ratio test + RANSAC similarity, centre offset in metres",
        "n": n,
        "right_cases": kinds.get("right", {"n": 0})["n"],
        "wrong_building_cases": wrong_n,
        "hits": hits,
        "misses": misses,
        "next_door": nd,
        "by_kind": kinds,
        "thresholds": {
            "min_inliers": vexcel_match.MIN_INLIERS,
            "max_offset_m": vexcel_match.MAX_OFFSET_M,
        },
        "inlier_range": {k: _range(v) for k, v in inliers.items()},
        "offset_m_range": {k: _range(v) for k, v in offsets.items()},
        "hash_diff_range": {k: _range(v) for k, v in diffs.items()},
        "hash_threshold": HASH_MAX_DIFF,
        "split": split,
        "bar": "18 of 20 (at least 20 cases, 90 percent), and 6+ next-door cases at 90 percent",
        "bar_met": bar_met,
        "next_door_ok": next_door_ok,
        "gate": "held-out half: right >= 90%, next-door >= 90%, other wrong 100%, LIVE only",
        "gate_met": held_ok,
        # Only a LIVE run whose held-out half meets GATE_RATES (and the all-n bar) opens the gate.
        "gate_open": held_ok and bar_met and next_door_ok and mode == "live",
        "synthetic_cases": bool(doc.get("synthetic")),
    }


def split_ids(rows: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """(tune, held_out): within each kind, by case id, alternate cases. Deterministic."""
    tune: set[str] = set()
    held: set[str] = set()
    for kind in sorted({r["kind"] for r in rows}):
        ids = sorted(r["case_id"] for r in rows if r["kind"] == kind)
        tune.update(ids[0::2])
        held.update(ids[1::2])
    return tune, held


def score(
    rows: list[dict[str, Any]], ids: set[str], min_inliers: int, max_offset_m: float
) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        if r["case_id"] not in ids:
            continue
        same = vexcel_match.same_building(
            vexcel_match.GeoMatch(inliers=r["inliers"], matches=0, offset_m=r["offset_m"]),
            min_inliers=min_inliers,
            max_offset_m=max_offset_m,
        )
        tally = out.setdefault(r["kind"], {"n": 0, "hits": 0})
        tally["n"] += 1
        tally["hits"] += same == (r["label"] == "right")
    return out


def _objective(by_kind: dict[str, dict[str, int]]) -> tuple[float, float]:
    rates = [t["hits"] / t["n"] for t in by_kind.values() if t["n"]]
    return (min(rates, default=0.0), sum(rates))


def tune_thresholds(rows: list[dict[str, Any]], ids: set[str]) -> tuple[int, float]:
    """(min_inliers, max_offset_m) that best separate the classes on `ids` only: the best worst
    class rate, then the best total. Among ties, the middle of the tied range: on a log scale for
    inliers (counts grow by factors: another place has a handful, the same scene hundreds), on a
    linear scale for the offset in metres."""
    inlier_grid = list(range(5, 305, 5))
    offset_grid = [x / 2 for x in range(10, 81)]  # 5.0 .. 40.0 m
    best: tuple[float, float] | None = None
    tied: list[tuple[int, float]] = []
    for mi in inlier_grid:
        for mo in offset_grid:
            obj = _objective(score(rows, ids, mi, mo))
            if best is None or obj > best:
                best, tied = obj, [(mi, mo)]
            elif obj == best:
                tied.append((mi, mo))
    inl = sorted({t[0] for t in tied})
    mid = math.sqrt(inl[0] * inl[-1])
    pick = min(inl, key=lambda v: (abs(v - mid), v))
    off = sorted({t[1] for t in tied if t[0] == pick})
    return pick, off[len(off) // 2]


def gate_met(held_out: dict[str, dict[str, int]]) -> bool:
    for kind, rate in GATE_RATES.items():
        t = held_out.get(kind, {"n": 0, "hits": 0})
        if not t["n"] or t["hits"] / t["n"] < rate:
            return False
    return True


def _split_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tune, held = split_ids(rows)
    mi, mo = tune_thresholds(rows, tune)
    return {
        "tuned_on": sorted(tune),
        "held_out_ids": sorted(held),
        "tuned": {"min_inliers": mi, "max_offset_m": mo},
        "tune": score(rows, tune, mi, mo),
        "held_out": score(rows, held, mi, mo),
        "all_with_tuned": score(rows, tune | held, mi, mo),
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


def _props_from_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    props: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda r: str(r["propertyId"])):
        if row.get("lat") is None or row.get("lon") is None or not row.get("address"):
            continue
        props.setdefault(
            str(row["propertyId"]),
            {"address": row["address"], "lat": row["lat"], "lon": row["lon"]},
        )
    return props


def build_cases(
    rows: list[dict[str, Any]], *, n_right: int = 12, n_next_door: int = 8, n_wrong: int = 8
) -> dict[str, Any]:
    """Cases from listing rows {propertyId, address, lat, lon}, deterministically.

    right: the ad and the claimed address are one property, and the second tile is centred
    RIGHT_OFFSET_M away, so it is not the same picture. next_door: the ad is for one property and
    claims the address of its nearest neighbour, 15 to 50 m away (same block). wrong: the same,
    but the nearest neighbour is 50 to 500 m away."""
    props = _props_from_rows(rows)
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


EXTRA_RIGHT_OFFSETS_M = (8.0, 10.0, 12.0, 15.0)  # added right cases cycle through these


def extend_cases(
    doc: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    add_right: int = 0,
    add_next_door: int = 0,
    add_wrong: int = 0,
) -> dict[str, Any]:
    """`doc` plus new cases from properties it does not use yet, deterministically.

    Existing case ids and properties are kept as they are, so a measured set only grows. New right
    cases cycle the tile offset through EXTRA_RIGHT_OFFSETS_M (8 to 15 m); new next-door and wrong
    cases follow the same rules as `build_cases`. Ids continue each kind's numbering."""
    props = _props_from_rows(rows)
    taken = {c["claimed_property_id"] for c in doc["cases"]} | {
        c["expected_property_id"] for c in doc["cases"]
    }
    ids = [p for p in props if p not in taken]
    used: set[str] = set()

    def take(pairs: list[tuple[str, str, float]], count: int) -> list[tuple[str, str, float]]:
        chosen = []
        for pair in pairs:
            if len(chosen) == count:
                break
            if pair[0] in used or pair[1] in used:
                continue
            chosen.append(pair)
            used.update(pair[:2])
        return chosen

    nd = take(_nearest(props, ids, NEXT_DOOR_MIN_M, NEXT_DOOR_MAX_M), add_next_door)
    wr = take(_nearest(props, ids, WRONG_MIN_M, WRONG_MAX_M), add_wrong)
    free = [p for p in ids if p not in used]
    step = max(1, len(free) // max(add_right, 1))
    right = free[::step][:add_right]

    def next_id(prefix: str) -> int:
        nums = [int(c["case_id"][4:]) for c in doc["cases"] if c["case_id"][3] == prefix]
        return max(nums, default=0) + 1

    new: list[dict[str, Any]] = []
    start = next_id("r")
    for i, p in enumerate(right):
        new.append(
            {
                "case_id": f"vx-r{start + i:02d}",
                "kind": "right",
                "claimed_address": props[p]["address"],
                "claimed_property_id": p,
                "expected_property_id": p,
                "expected_offset_m": EXTRA_RIGHT_OFFSETS_M[i % len(EXTRA_RIGHT_OFFSETS_M)],
                "label": "right",
            }
        )
    for prefix, kind, chosen in (("n", "next_door", nd), ("w", "wrong", wr)):
        start = next_id(prefix)
        for i, (e, c, d) in enumerate(chosen):
            new.append(
                {
                    "case_id": f"vx-{prefix}{start + i:02d}",
                    "kind": kind,
                    "claimed_address": props[c]["address"],
                    "claimed_property_id": c,
                    "expected_property_id": e,
                    "label": "wrong",
                    "distance_m": d,
                }
            )
    keep = {c["claimed_property_id"] for c in new} | {c["expected_property_id"] for c in new}
    return {
        "properties": {**doc["properties"], **{p: props[p] for p in keep}},
        "cases": doc["cases"] + new,
    }
