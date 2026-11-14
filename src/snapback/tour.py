"""Walk it first: a room-by-room guided tour of a researched place, built by code.

The tour plan is the data behind the Tour page: arrive outside (Vexcel aerial and the outside
facts on record), the front door, one stop per labelled room in walking order, then "Now see it
in person". No model writes any line and none picks any stop.

How the walk is chosen (deterministic, nothing random):

1. The front door is the most central sweep of the rooms Matterport labelled entry, foyer,
   entryway or entrance. With none, it is the scan's start sweep (the first one the scan lists),
   labelled honestly "Start of the 3D scan".
2. Sweeps with the same room label that sit within `ROOM_LINK_M` of each other (walking
   distance, floor plane) are one room. Two separate bedrooms stay two stops.
3. Each room's stop is its most central sweep (least total distance to the others).
4. The rooms are visited nearest-first from the door, always from the last stop (nearest
   neighbour). Ties go to the sweep the scan lists first.
5. With no room labels at all the walk is evenly spaced stops along the same nearest-neighbour
   path, named "Stop 1..n", and the plan says rooms are not labelled.

Every fact carries its source line and comes only from CoStar's record (the place's floor plan
and the building record) or Vexcel (the aerial date). The lines never mention a neighbourhood, a
school or people, never say "available now" and never offer to book.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from snapback.contracts import (
    AS_OF,
    DataSource,
    LocateResult,
    LocateStatus,
    PlaceMatch,
    PropertyRecord,
)

ROOM_LINK_M = 4.0  # same-label sweeps closer than this (metres) belong to one room
MAX_ROOM_STOPS = 12
MAX_FALLBACK_STOPS = 8

SRC_RECORD = "CoStar record"
SRC_AERIAL = "Vexcel aerial"

SCAN_HOUSE = "a 3D scan of this home"
SCAN_APARTMENT = "a 3D scan in this building (it may be a model unit, not the one you'd rent)"
START_NOTE = "Start of the 3D scan"
ROOMS_NOTE = (
    "Room names are Matterport's automatic labels for each spot in the scan. "
    "They can be wrong, so look at the picture too."
)
NO_ROOMS_NOTE = "Rooms are not labelled in this scan, so the stops are numbered along its path."
NO_SCAN_NOTE = "No 3D scan is on record for this place, so there is no walkthrough to show."
NOT_CACHED_NOTE = (
    "The scan's sweeps are not loaded on this server, so the stops come from the 3D view."
)

_ENTRY_WORDS = ("entry", "foyer", "entryway", "entrance")

# What to check in person, by kind of room. Fixed text, picked by keyword on the room label.
_TIPS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("bath", "toilet", "restroom", "powder"),
        "Run the sink and shower: check the water pressure and how fast it drains.",
    ),
    (
        ("kitchen",),
        "Open the fridge, oven and dishwasher: check every appliance listed is there and works.",
    ),
    (("bed",), "Check the windows, the closet and the outlets, and your phone signal."),
    (
        ("living", "family", "great room"),
        "Turn on the AC and look at the vents; check the outlets and the outside noise.",
    ),
    (("dining",), "Check the light and the outlets; picture where your table would go."),
    (("laundry", "utility"), "Look for washer and dryer hookups, the vent, and any water stains."),
    (
        ("closet", "storage", "pantry"),
        "Open it and check the space, the shelves and any smell of damp.",
    ),
    (("garage", "carport", "parking"), "Check the space you are given, the door and the lighting."),
    (
        ("balcony", "patio", "deck", "porch", "yard"),
        "Check the railing and the door, and what you can see from here.",
    ),
    (("hall", "stair", "corridor"), "Look at the ceiling and floor for water stains or cracks."),
    (("office", "study", "den"), "Check the outlets and the phone and internet signal."),
)
_DEFAULT_TIP = "Look at the ceiling and walls for water stains, and try the light switches."
_ENTRY_TIP = "Check the lock, and that the unit number on the door matches your lease."
_START_TIP = "Check the lock, and that the unit number on the door matches your lease."


class TourFact(BaseModel):
    text: str
    source: str  # a source line, never empty


class TourPhoto(BaseModel):
    """A photo from the renter's own ad that was placed in this room of the scan. Optional on a
    stop: the design that shows "your photo, taken here" fills it from the case's locate result."""

    photo_id: str
    sweep_id: str | None = None
    position: tuple[float, float, float] | None = None
    rotation_quat: tuple[float, float, float, float] | None = None
    fov_deg: float | None = None


class WalkCoverage(BaseModel):
    """How much of the scan the ad's photos cover. Filled by the locate-to-stops task (W1);
    `counted` says whether rooms, spots or nothing were counted, and `line` is the code-written
    sentence the page shows."""

    counted: Literal["rooms", "spots", "none"] = "none"
    total: int = 0
    with_photo: int = 0
    placed: int = 0
    elsewhere: int = 0
    unplaced: int = 0
    line: str | None = None


class TourDirector(BaseModel):
    """What the tour director picked among options code wrote (W6): stops to dwell on and the
    checks that lead. `stamp` says who chose. Facts never depend on it."""

    dwell: list[str] = Field(default_factory=list)  # stop keys
    lead_checks: list[str] = Field(default_factory=list)
    stamp: Literal["model", "policy"] = "policy"
    reason: str | None = None


class TourStop(BaseModel):
    kind: Literal["arrive", "door", "room", "stop", "outro"]
    key: str
    title: str
    room_label: str | None = None  # Matterport's label for this spot, as given
    sweep_id: str | None = None
    sweep_count: int = 0  # sweeps of this room the scan holds
    sweep_ids: list[str] = Field(default_factory=list)  # every sweep of this room
    photos: list[TourPhoto] = Field(default_factory=list)  # the renter's ad photos placed here
    # Whether an ad photo was placed in this room; "unknown" until the locate result is mapped.
    ad_view: Literal["placed", "none_placed", "unknown"] = "unknown"
    claims: list[TourFact] = Field(default_factory=list)  # what the ad claimed for this room
    position: tuple[float, float, float] | None = None
    rotation_quat: tuple[float, float, float, float] | None = None  # x, y, z, w
    facts: list[TourFact] = Field(default_factory=list)
    tip: str | None = None  # "check this in person"
    note: str | None = None


class TourAerial(BaseModel):
    source: DataSource
    captured_on: date | None = None
    has_image: bool = False


class TourLinks(BaseModel):
    tour_prep: str  # the web page and API path of the tour-prep pack
    tour_prep_api: str
    tour_draft_hint: str


class TourPlan(BaseModel):
    property_id: str
    kind: Literal["apartment", "house"]
    source: DataSource
    as_of: str = AS_OF
    has_scan: bool
    scan_label: str | None = None
    rooms_labelled: bool = False
    rooms_note: str
    aerial: TourAerial | None = None
    stops: list[TourStop]
    links: TourLinks
    coverage: WalkCoverage | None = None
    director: TourDirector | None = None


class PhotoWalkFields(BaseModel):
    """What the walk knows about one ad photo, keyed by photo id. `stop_alias` is the alias (S1..)
    of the stop that holds it, or None when it is on no stop. `covers_unshown_room` is True when
    the photo's own room label names a stop that no placed photo covers (the agent's photo
    budget weighs these first)."""

    stop_alias: str | None = None
    covers_unshown_room: bool = False


class WalkResponse(BaseModel):
    """`GET /cases/{id}/walk`: the plan with the case's placed photos, and the locate result."""

    plan: TourPlan
    locate: LocateResult | None = None
    photos: dict[str, PhotoWalkFields] = Field(default_factory=dict)


@dataclass(frozen=True)
class TourSweep:
    sweep_id: str
    position: tuple[float, float, float] | None
    rotation_quat: tuple[float, float, float, float] | None
    label: str | None = None


# --- geometry ----------------------------------------------------------------------------------


def _dist(a: TourSweep, b: TourSweep) -> float:
    """Walking distance on the floor plane (x, z; y is up), inf when a position is unknown."""
    if a.position is None or b.position is None:
        return math.inf
    return math.hypot(a.position[0] - b.position[0], a.position[2] - b.position[2])


def _central(
    group: Sequence[TourSweep], order: dict[str, int], avoid: str | None = None
) -> TourSweep:
    """The sweep with the least total distance to the rest. Ties go to the one the scan lists
    first. `avoid` is skipped when another sweep is available."""
    pool = [s for s in group if s.sweep_id != avoid] or list(group)

    def cost(s: TourSweep) -> tuple[float, int]:
        total = sum(_dist(s, o) for o in group if o is not s)
        return (0.0 if math.isinf(total) else total, order[s.sweep_id])

    return min(pool, key=cost)


def _clusters(sweeps: Sequence[TourSweep], order: dict[str, int]) -> list[list[TourSweep]]:
    """Single-link groups of sweeps closer than ROOM_LINK_M; with no positions, one group."""
    parent = list(range(len(sweeps)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(sweeps):
        for j in range(i + 1, len(sweeps)):
            if _dist(a, sweeps[j]) <= ROOM_LINK_M:
                parent[find(j)] = find(i)
    out: dict[int, list[TourSweep]] = {}
    for i, s in enumerate(sweeps):
        out.setdefault(find(i), []).append(s)
    if all(s.position is None for s in sweeps):  # nothing to link by: the label is the room
        return [list(sweeps)]
    return sorted(out.values(), key=lambda g: min(order[s.sweep_id] for s in g))


def _nearest_first(
    start: TourSweep, reps: list[TourSweep], order: dict[str, int]
) -> list[TourSweep]:
    """Nearest neighbour from `start`; ties go to the sweep the scan lists first."""
    left = list(reps)
    here = start
    path: list[TourSweep] = []
    while left:
        nxt = min(left, key=lambda s: (_dist(here, s), order[s.sweep_id]))
        path.append(nxt)
        left.remove(nxt)
        here = nxt
    return path


# --- room kinds --------------------------------------------------------------------------------


def _is_entry(label: str | None) -> bool:
    low = (label or "").lower()
    return any(word in low for word in _ENTRY_WORDS)


def _kind_of(label: str | None) -> str | None:
    low = (label or "").lower()
    if _is_entry(low):
        return "entry"
    for words, _tip in _TIPS:
        if any(w in low for w in words):
            return words[0]
    return None


def tip_for(label: str | None) -> str:
    low = (label or "").lower()
    if _is_entry(low):
        return _ENTRY_TIP
    for words, tip in _TIPS:
        if any(w in low for w in words):
            return tip
    return _DEFAULT_TIP


def _plural(n: float, word: str) -> str:
    return f"{n:g} {word}{'' if n == 1 else 's'}"


def _room_facts(
    label: str | None, place: PlaceMatch | None, record: PropertyRecord | None, used: set[str]
) -> list[TourFact]:
    """Record facts that belong to this kind of room, once per kind. Only what the record holds;
    a room with no fact on record simply has none."""
    kind = _kind_of(label)
    facts: list[TourFact] = []
    if kind is None or kind in used:
        return facts
    plan = f" ({place.floor_plan})" if place and place.floor_plan else ""
    if kind == "bed" and place is not None and place.beds is not None:
        text = "A studio" if place.beds == 0 else f"{_plural(place.beds, 'bedroom')}"
        verb = "layout" if place.beds == 0 else "in this floor plan"
        facts.append(TourFact(text=f"{text} {verb}{plan}", source=f"{SRC_RECORD}, floor plan"))
    elif kind == "bath" and place is not None and place.baths is not None:
        facts.append(
            TourFact(
                text=f"{_plural(place.baths, 'bathroom')} in this floor plan{plan}",
                source=f"{SRC_RECORD}, floor plan",
            )
        )
    elif kind == "laundry" and record is not None and record.metering:
        text = (
            "Individual utility meters"
            if record.metering == "individual"
            else "One shared (master) utility meter"
        )
        facts.append(TourFact(text=text, source=SRC_RECORD))
    elif kind == "garage" and record is not None and record.parking_ratio is not None:
        facts.append(
            TourFact(text=f"{record.parking_ratio:g} parking spaces per unit", source=SRC_RECORD)
        )
    elif kind == "entry" and record is not None:
        if record.has_elevator:
            facts.append(TourFact(text="An elevator is on record", source=SRC_RECORD))
        if record.is_walkup:
            facts.append(
                TourFact(text="A walk-up building (stairs, no elevator)", source=SRC_RECORD)
            )
    if facts:
        used.add(kind)
    return facts


def outside_facts(
    place: PlaceMatch | None, record: PropertyRecord | None, aerial_on: date | None
) -> list[TourFact]:
    """Outside facts on record. Pool and yard are not in the record we hold, so they are not
    claimed; the list holds only what the record or Vexcel gives."""
    facts: list[TourFact] = []
    if record is not None:
        if record.year_built:
            facts.append(TourFact(text=f"Built in {record.year_built}", source=SRC_RECORD))
        if record.floors:
            facts.append(TourFact(text=f"{_plural(record.floors, 'floor')}", source=SRC_RECORD))
        if record.parking_ratio is not None:
            facts.append(
                TourFact(
                    text=f"{record.parking_ratio:g} parking spaces per unit", source=SRC_RECORD
                )
            )
        if record.is_walkup:
            facts.append(TourFact(text="A walk-up building", source=SRC_RECORD))
        elif record.has_elevator:
            facts.append(TourFact(text="An elevator is on record", source=SRC_RECORD))
    if aerial_on is not None:
        facts.append(
            TourFact(
                text=(
                    f"Aerial photo captured {aerial_on.strftime('%b')} "
                    f"{aerial_on.day}, {aerial_on.year}"
                ),
                source=SRC_AERIAL,
            )
        )
    return facts


# --- the walk ----------------------------------------------------------------------------------


def _stop_for(
    sweep: TourSweep,
    *,
    kind: str,
    key: str,
    title: str,
    count: int,
    label: str | None = None,
    members: Sequence[TourSweep] = (),
) -> TourStop:
    return TourStop(
        kind=kind,  # type: ignore[arg-type]
        key=key,
        title=title,
        room_label=label,
        sweep_id=sweep.sweep_id,
        sweep_count=count,
        sweep_ids=[m.sweep_id for m in members] or [sweep.sweep_id],
        position=sweep.position,
        rotation_quat=sweep.rotation_quat,
    )


def walk(
    sweeps: Sequence[TourSweep],
    place: PlaceMatch | None = None,
    record: PropertyRecord | None = None,
) -> tuple[list[TourStop], bool]:
    """The door and the room (or numbered) stops in walking order, and if rooms are labelled."""
    if not sweeps:
        return [], False
    order = {s.sweep_id: i for i, s in enumerate(sweeps)}
    labelled = [s for s in sweeps if (s.label or "").strip()]
    if not labelled:
        return _numbered(sweeps, order), False

    entry = [s for s in labelled if _is_entry(s.label)]
    used: set[str] = set()
    if entry:
        door_sweep = _central(entry, order)
        door = _stop_for(
            door_sweep,
            kind="door",
            key="door",
            title="Front door",
            count=len(entry),
            label=door_sweep.label,
            members=entry,
        )
        door.tip = _ENTRY_TIP
        door.facts = _room_facts(door_sweep.label, place, record, used)
        rest = [s for s in labelled if not _is_entry(s.label)]
    else:
        door_sweep = sweeps[0]
        door = _stop_for(door_sweep, kind="door", key="door", title="Front door", count=1)
        door.note = START_NOTE
        door.tip = _START_TIP
        rest = labelled

    groups: dict[str, list[TourSweep]] = {}
    for s in rest:
        groups.setdefault((s.label or "").strip(), []).append(s)
    rooms: list[tuple[str, list[TourSweep]]] = []
    for label in sorted(groups, key=lambda lab: min(order[s.sweep_id] for s in groups[lab])):
        rooms.extend((label, c) for c in _clusters(groups[label], order))

    reps = {id(g): _central(g, order, avoid=door_sweep.sweep_id) for _l, g in rooms}
    path = _nearest_first(door_sweep, [reps[id(g)] for _l, g in rooms], order)
    by_rep = {reps[id(g)].sweep_id: (lab, g) for lab, g in rooms}
    path = path[:MAX_ROOM_STOPS]

    totals: dict[str, int] = {}
    for lab, _g in by_rep.values():
        totals[lab] = totals.get(lab, 0) + 1
    seen: dict[str, int] = {}
    stops = [door]
    for rep in path:
        lab, group = by_rep[rep.sweep_id]
        seen[lab] = seen.get(lab, 0) + 1
        title = f"{lab} {seen[lab]}" if totals[lab] > 1 else lab
        stop = _stop_for(
            rep,
            kind="room",
            key=f"room-{len(stops)}",
            title=title,
            count=len(group),
            label=lab,
            members=group,
        )
        stop.facts = _room_facts(lab, place, record, used)
        stop.tip = tip_for(lab)
        stops.append(stop)
    return stops, True


def _numbered(sweeps: Sequence[TourSweep], order: dict[str, int]) -> list[TourStop]:
    """No labels: the door is the scan's start, then evenly spaced stops along the path."""
    start = sweeps[0]
    door = _stop_for(start, kind="door", key="door", title="Front door", count=1)
    door.note = START_NOTE
    door.tip = _START_TIP
    path = _nearest_first(start, list(sweeps[1:]), order)
    n = min(MAX_FALLBACK_STOPS, len(path))
    picks = [path[round(i * (len(path) - 1) / (n - 1))] for i in range(n)] if n > 1 else path[:n]
    stops = [door]
    for i, s in enumerate(picks, start=1):
        stop = _stop_for(s, kind="stop", key=f"stop-{i}", title=f"Stop {i}", count=1)
        stop.tip = _DEFAULT_TIP
        stops.append(stop)
    return stops


def scan_label_for(kind: str) -> str:
    return SCAN_HOUSE if kind == "house" else SCAN_APARTMENT


def build_tour(
    *,
    property_id: str,
    kind: Literal["apartment", "house"],
    source: DataSource,
    sweeps: Sequence[TourSweep],
    has_scan: bool,
    place: PlaceMatch | None = None,
    record: PropertyRecord | None = None,
    aerial_on: date | None = None,
    aerial_source: DataSource | None = None,
    aerial_image: bool = False,
    plan_key: str | None = None,
) -> TourPlan:
    """The whole tour: arrive, the door, the rooms, the outro. Pure: the same inputs give the same
    plan. `sweeps` carry the scan's own order and Matterport's room labels."""
    arrive = TourStop(
        kind="arrive",
        key="arrive",
        title="Arrive outside",
        facts=outside_facts(place, record, aerial_on),
        tip="Look at the entrance, the lighting and the parking as you walk up.",
    )
    inside, labelled = walk(sweeps, place, record) if has_scan else ([], False)
    outro = TourStop(
        kind="outro",
        key="outro",
        title="Now see it in person",
        tip="Book nothing and pay nothing until you have seen it. Take this list with you.",
    )
    if not has_scan:
        note = NO_SCAN_NOTE
    elif not inside:
        note = NOT_CACHED_NOTE
    elif labelled:
        note = ROOMS_NOTE
    else:
        note = NO_ROOMS_NOTE
    prep = f"/prep/place/{property_id}" + (f"?plan_key={plan_key}" if plan_key else "")
    return TourPlan(
        property_id=property_id,
        kind=kind,
        source=source,
        has_scan=has_scan,
        scan_label=scan_label_for(kind) if has_scan else None,
        rooms_labelled=labelled,
        rooms_note=note,
        aerial=TourAerial(
            source=aerial_source or source, captured_on=aerial_on, has_image=aerial_image
        ),
        stops=[arrive, *inside, outro],
        links=TourLinks(
            tour_prep=prep,
            tour_prep_api=f"/places/{property_id}/tour-prep",
            tour_draft_hint="Draft a tour request from the results page of your case.",
        ),
    )


def attach_photos(plan: TourPlan, photos: Sequence[TourPhoto]) -> TourPlan:
    """Put each placed ad photo on the stop whose room holds its sweep. A photo whose sweep is in
    no stop's room is left off (never forced onto a nearby room). Returns a new plan."""
    stops = []
    for stop in plan.stops:
        mine = [p for p in photos if p.sweep_id and p.sweep_id in stop.sweep_ids]
        stops.append(stop.model_copy(update={"photos": mine}) if mine else stop)
    return plan.model_copy(update={"stops": stops})


# --- where the sweeps come from ------------------------------------------------------------------

# A made-up two-bedroom flat for `fx-` model ids: sweep id, floor-plane (x, z) in metres, label.
_FIXTURE_LAYOUT: tuple[tuple[str, float, float, str | None], ...] = (
    ("fx-sweep-00", 0.0, 0.0, "Entryway"),
    ("fx-sweep-01", 3.0, 0.0, "Living room"),
    ("fx-sweep-02", 5.5, 0.5, "Living room"),
    ("fx-sweep-03", 8.0, -2.0, "Kitchen"),
    ("fx-sweep-04", 3.0, 5.0, "Bedroom"),
    ("fx-sweep-05", 9.0, 4.0, "Bedroom"),
    ("fx-sweep-06", 6.0, 6.0, "Bathroom"),
)


def fixture_sweeps(model_id: str) -> list[TourSweep]:
    """Synthetic sweeps for an `fx-` model id: no files, the same every time."""
    if not model_id.startswith("fx-"):
        return []
    return [
        TourSweep(sid, (x, 1.4, z), (0.0, 0.0, 0.0, 1.0), label)
        for sid, x, z, label in _FIXTURE_LAYOUT
    ]


def cached_sweeps(model_id: str, cache_dir=None) -> list[TourSweep]:
    """Sweeps of a live model from the local cache only (sweeps.json and rooms.json): no network,
    no key. Empty when the model is not cached. Room labels come from `cached_room_labels` once
    that exists on this branch (PR #205); until then rooms.json is read directly."""
    import json
    from pathlib import Path

    from snapback.adapters import matterport as mp

    folder = Path(cache_dir or mp.LIVE_CACHE) / mp._safe(model_id)
    try:
        sweeps = mp._read_manifest(model_id, folder)
    except (OSError, ValueError, KeyError):
        sweeps = None
    if not sweeps:
        return []
    reader = getattr(mp, "cached_room_labels", None)
    if reader is not None:
        labels = reader(model_id, Path(cache_dir or mp.LIVE_CACHE))
    else:
        try:
            labels = json.loads((folder / "rooms.json").read_text())
        except (OSError, ValueError):
            labels = {}
    if not isinstance(labels, dict):
        labels = {}
    return [
        TourSweep(s.sweep_id, s.position, s.rotation_quat, labels.get(s.sweep_id)) for s in sweeps
    ]


# --- the ad's photos on the stops (W1) -----------------------------------------------------------

WALKED = ("door", "room", "stop")  # the stop kinds that are places in the scan


def stop_aliases(plan: TourPlan) -> dict[str, str]:
    """Stop key -> alias S1..Sn over the stops inside the scan, in walking order. Aliases are
    what a model may see in place of room names and ids."""
    keys = [s.key for s in plan.stops if s.kind in WALKED]
    return {key: f"S{i}" for i, key in enumerate(keys, start=1)}


def _plural_photos(n: int) -> str:
    return f"{n} photo" if n == 1 else f"{n} photos"


def coverage_line(
    *, counted: str, total: int, with_photo: int, unplaced: int, elsewhere: int
) -> str:
    base = (
        f"The ad showed {with_photo} of the {total} rooms in this scan."
        if counted == "rooms"
        else f"The ad's photos were taken at {with_photo} of {total} spots in this scan."
    )
    if unplaced:
        base += f" {_plural_photos(unplaced)} could not be placed, so the real count may be higher."
    if elsewhere:
        was = "was" if elsewhere == 1 else "were"
        base += f" {_plural_photos(elsewhere)} {was} taken in a different building and not counted."
    return base


def map_locate(
    plan: TourPlan,
    locate: LocateResult,
    *,
    scan_plan: str | None = None,
    ad_plan: str | None = None,
) -> tuple[TourPlan, dict[str, PhotoWalkFields]]:
    """Put the ad's placed photos on the stops that hold their sweep, set each stop's `ad_view`,
    and count coverage. Only `located_in_claimed` photos ever enter a room: a photo taken in
    another building, or one that could not be placed, is counted but never put in a room.

    `ad_view` is "placed" for a stop with a photo; "none_placed" for one without only when every
    ad photo was placed in this home (so "the ad showed no photo of this room" is true); else
    "unknown". When an apartment scan's floor plan differs from the ad's, rooms are not counted.
    """
    status = {p.photo_id: p.status for p in locate.photos}
    placed_ids = [p.photo_id for p in locate.photos if p.status is LocateStatus.LOCATED_IN_CLAIMED]
    elsewhere = sum(s is LocateStatus.LOCATED_ELSEWHERE for s in status.values())
    unplaced = len(status) - len(placed_ids) - elsewhere
    all_placed = bool(status) and len(placed_ids) == len(status)

    by_stop: dict[str, list[TourPhoto]] = {}
    where: dict[str, str] = {}  # photo id -> stop key
    for photo in locate.photos:
        if photo.photo_id not in placed_ids:
            continue
        pose = locate.poses.get(photo.photo_id)
        sweep = photo.pano_id or (pose.sweep_id if pose else None)
        stop = next(
            (s for s in plan.stops if s.kind in WALKED and sweep and sweep in s.sweep_ids), None
        )
        if stop is None:
            continue  # placed, but in a sweep that is no stop: never forced onto a nearby room
        by_stop.setdefault(stop.key, []).append(
            TourPhoto(
                photo_id=photo.photo_id,
                sweep_id=sweep,
                position=tuple(pose.position) if pose else None,
                rotation_quat=tuple(pose.rotation_quat) if pose else None,
                fov_deg=pose.fov_deg if pose else None,
            )
        )
        where[photo.photo_id] = stop.key

    stops = []
    for stop in plan.stops:
        if stop.kind not in WALKED:
            stops.append(stop)
            continue
        mine = by_stop.get(stop.key, [])
        view = "placed" if mine else ("none_placed" if all_placed else "unknown")
        stops.append(stop.model_copy(update={"photos": mine, "ad_view": view}))

    walked = [s for s in stops if s.kind in WALKED]
    with_photo = sum(bool(s.photos) for s in walked)
    counted = "rooms" if plan.rooms_labelled else "spots"
    line: str | None
    if not walked:
        counted, line = "none", None
    elif scan_plan and ad_plan and scan_plan.strip().lower() != ad_plan.strip().lower():
        counted = "none"
        line = (
            f"This scan is a {scan_plan} floor plan and the ad is for a {ad_plan}, "
            "so we show the scan without counting rooms."
        )
    elif not placed_ids:
        counted = "none"
        line = (
            "None of the ad's photos could be placed in this scan, "
            "so we show it without counting rooms."
        )
    else:
        line = coverage_line(
            counted=counted,
            total=len(walked),
            with_photo=with_photo,
            unplaced=unplaced,
            elsewhere=elsewhere,
        )
    coverage = WalkCoverage(
        counted=counted,  # type: ignore[arg-type]
        total=len(walked) if counted != "none" else 0,
        with_photo=with_photo if counted != "none" else 0,
        placed=len(placed_ids),
        elsewhere=elsewhere,
        unplaced=unplaced,
        line=line,
    )

    aliases = stop_aliases(plan)
    unshown = {
        (s.room_label or "").strip().lower() for s in walked if not s.photos and s.room_label
    }
    fields: dict[str, PhotoWalkFields] = {}
    for photo in locate.photos:
        key = where.get(photo.photo_id)
        label = (photo.room_label or "").strip().lower()
        fields[photo.photo_id] = PhotoWalkFields(
            stop_alias=aliases.get(key) if key else None,
            covers_unshown_room=bool(label and label in unshown),
        )
    return plan.model_copy(update={"stops": stops, "coverage": coverage}), fields
