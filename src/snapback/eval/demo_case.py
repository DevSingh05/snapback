"""A live demo case on any laptop that has the index and the scan cache (#10, Sat 17:3x).

    uv run python -m snapback.eval.demo_case --api http://localhost:8000

Picks an indexed rental building whose cached scan has room labels (or the one you name), renders
one unseen view per labelled room from the scan (renders, not photos: the label every output line
carries), posts them as a LIVE case with that building claimed, and reads back the walk and the
evidence file. It prints the case id, counts and room labels, then the browser address of the walk
and the one line to paste in the browser console so that page can read the case (tokens never go
in an address).

Nothing here is sent anywhere but the local API. It prints no record values: the building is named
only inside the local address, and the renders stay in memory.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

LABEL = "renders of the scan (unseen directions from the indexed scan points), not photos"
ROOMS = ("Kitchen", "Living Room", "Bedroom", "Bathroom")
READ_TOKEN_PREFIX = "snapback.case-read-token."  # apps/web/src/api.ts


@dataclass(frozen=True)
class Pick:
    property_id: str
    model_id: str
    room_kinds: int


def rank_scans(
    records: Iterable,
    indexed: set[str],
    rooms_for: Callable[[str], Mapping[str, str | None]],
) -> list[Pick]:
    """Indexed scans of rental buildings (multifamily with rents on record), best demo first. A
    building with ONE indexed scan comes first: with two, a view can match the sibling scan, and
    the walk (built from one scan) counts that photo but shows it on no stop. Then the most kinds
    of labelled rooms; ties go to the lower ids, so the order is stable."""
    ranked = []
    for record in records:
        if record.property_type != "multifamily" or not record.rent_median:
            continue
        scans = [m for m in record.model_ids if m in indexed]
        for model_id in scans:
            kinds = len({label for label in rooms_for(model_id).values() if label})
            if kinds:
                key = (len(scans) == 1, kinds, _desc(record.property_id), _desc(model_id))
                ranked.append((key, Pick(record.property_id, model_id, kinds)))
    return [pick for _, pick in sorted(ranked, key=lambda kp: kp[0], reverse=True)]


def pick_building(
    records: Iterable,
    indexed: set[str],
    rooms_for: Callable[[str], Mapping[str, str | None]],
) -> Pick | None:
    """The best scan to demo (`rank_scans`), or None."""
    ranked = rank_scans(records, indexed, rooms_for)
    return ranked[0] if ranked else None


def _desc(text: str) -> tuple[int, ...]:
    """Sort key that puts lower strings first when the tuple is maximised."""
    return tuple(-ord(c) for c in text)


def render_rooms(
    sweeps: Sequence,
    rooms: Mapping[str, str | None],
    wanted: Sequence[str] = ROOMS,
    seed: int = 14,
) -> list[tuple[str, bytes]]:
    """One JPEG per wanted room that the scan labels: (room, bytes), in `wanted` order."""
    from snapback.eval.locate_gate import held_out_view

    rng = random.Random(seed)
    by_id = {s.sweep_id: s for s in sweeps}
    out = []
    for room in wanted:
        ids = sorted(s for s, label in rooms.items() if label == room and s in by_id)
        if not ids:
            continue
        image, _, _ = held_out_view(by_id[rng.choice(ids)], rng)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        out.append((room, buffer.getvalue()))
    return out


@dataclass(frozen=True)
class Tried:
    case: dict
    sent: int
    on_walk: int


def first_full_walk(
    candidates: Sequence[Pick], tries: int, attempt: Callable[[Pick], Tried | None]
) -> tuple[Pick, Tried] | None:
    """Try scans best first until every sent view is on a walk stop. `attempt` returns None when
    a scan gives no view. The answer pairs each case with the building it was made for: the last
    case made when no try is full, or None when no try made a case."""
    shown: tuple[Pick, Tried] | None = None
    for pick in candidates[:tries]:
        tried = attempt(pick)
        if tried is None:
            continue
        shown = (pick, tried)
        if tried.on_walk == tried.sent:
            break
    return shown


def browser_lines(web: str, property_id: str, case_id: str, read_token: str) -> list[str]:
    key = READ_TOKEN_PREFIX + case_id.upper()
    return [
        f"Open: {web.rstrip('/')}/tour/{property_id}?case={case_id}",
        "Then, once, in that tab's console (the page reads the case token from sessionStorage):",
        f"  sessionStorage.setItem({json.dumps(key)}, {json.dumps(read_token)}); location.reload()",
    ]


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - needs the kit and the API
    import httpx

    from snapback.adapters.matterport import REPO_ROOT, cached_room_labels
    from snapback.agent.join import KitLookups, KitMissing
    from snapback.agent.locate_live import _default_sweeps
    from snapback.contracts import DataSource
    from snapback.settings import Settings

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--web", default="http://localhost:5173")
    parser.add_argument("--property-id", help="a building to claim (default: the best indexed one)")
    parser.add_argument("--rooms", default=",".join(ROOMS))
    parser.add_argument("--seed", type=int, default=14)
    parser.add_argument("--tries", type=int, default=3, help="scans to try, best first")
    args = parser.parse_args(argv)

    settings = Settings()
    data_dir = settings.snapback_data_dir
    if not data_dir.is_absolute():
        data_dir = REPO_ROOT / data_dir  # the scan cache is under REPO_ROOT/data too
    try:
        meta = json.loads(
            (data_dir / "index" / settings.snapback_locate_index / "index.json").read_text()
        )
        indexed = {entry["model_id"] for entry in meta["entries"]}
        records = KitLookups(DataSource.LIVE).records()
    except (FileNotFoundError, KeyError, KitMissing):
        print(
            "No locate index or kit under data/. "
            "Unzip the team data handoff (or build the index) first.",
            file=sys.stderr,
        )
        return 2
    if args.property_id:
        record = records.get(args.property_id)
        models = [m for m in (record.model_ids if record else []) if m in indexed]
        if not models:
            print("That building has no indexed scan here.", file=sys.stderr)
            return 2
        candidates = [Pick(args.property_id, m, 0) for m in models]
    else:
        candidates = rank_scans(records.values(), indexed, cached_room_labels)
        if not candidates:
            print("No indexed rental building with room labels here.", file=sys.stderr)
            return 2

    wanted = [r.strip() for r in args.rooms.split(",") if r.strip()]
    number = 0

    def attempt(pick: Pick) -> Tried | None:
        nonlocal number
        views = render_rooms(
            _default_sweeps(pick.model_id), cached_room_labels(pick.model_id), wanted, args.seed
        )
        if not views:
            return None
        number += 1
        files = [
            ("photos", (f"view-{i}.jpg", data, "image/jpeg"))
            for i, (_, data) in enumerate(views, 1)
        ]
        made = httpx.post(
            f"{args.api}/cases",
            data={"property_id": pick.property_id, "text": "Apartment for rent, photos attached."},
            files=files,
            timeout=300,
        )
        made.raise_for_status()
        case = made.json()
        headers = {"x-case-token": case["read_token"]}
        walk = httpx.get(f"{args.api}/cases/{case['case_id']}/walk", headers=headers, timeout=120)
        walk.raise_for_status()
        body = walk.json()
        statuses = Counter(p["status"] for p in (body.get("locate") or {}).get("photos", []))
        stops = [
            (s["room_label"], [p.get("alias") for p in s["photos"]])
            for s in body["plan"]["stops"]
            if s["photos"]
        ]
        on_walk = sum(len(aliases) for _, aliases in stops)
        print(f"try {number}: case {case['case_id']} ({case.get('source')}); photos are {LABEL}")
        print(f"  sent: {[room for room, _ in views]}")
        print(f"  placed: {dict(statuses)}")
        print(f"  on the walk: {stops}")
        if on_walk != len(views):
            print("  not every view is on a walk stop")
        return Tried(case, len(views), on_walk)

    shown = first_full_walk(candidates, args.tries, attempt)
    if shown is None:
        print("None of the scans tried labels those rooms.", file=sys.stderr)
        return 2
    pick, tried = shown
    case = tried.case
    if tried.on_walk != tried.sent:
        print("No try put every view on a walk stop; showing the last case made.")
    for line in browser_lines(args.web, pick.property_id, case["case_id"], case["read_token"]):
        print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
