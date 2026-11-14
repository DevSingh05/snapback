"""The place desk: what to do about listing photos the first search could not place.

`Locator.locate` is the base search and it always runs first, on every photo, unchanged. For a
photo it could not place, the case has a short budget (2 more searches or 10 seconds, whichever
comes first) to spend on a retry. Code writes the menu of retries from what failed; a chooser
(the place sub-agent, a model behind the same list, or the code policy) picks from it:

- D1, `next_search`: `focus_scan:S2` (one other scan in this building gets the full side-face
  budget), `wider_index` (more candidates over every building), `deeper_claimed` (more side
  faces of the claimed scans), or `stop`.
- D2, `which_photo`: only when unplaced photos outnumber the searches left.

Every retry uses the SAME verification bars as the base search. `search_thresholds` changes
`[retrieve]` only, and the E6 mutant test fails if a bar ever moves. A retry never touches a
photo that is already placed. A retry may find "taken in a different building" on the strict
bar, exactly as the base search can (ruling R-E1; `retry_can_find_elsewhere`).

A model sees aliases (P1, S2), counts and bar values (`PLACE_FACT_KEYS`), never an image, a
keypoint, an id or an address. The matched points go to the evidence file for the drawer and
nowhere else.

The retry itself belongs to `Locator.search` (E2a, lane V). Until it lands this module talks to
it through the `PlaceSearcher` protocol, and tests use a stub.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Literal, Protocol

from snapback.agent.planner import SearchOffer, SearchStep, _decide
from snapback.contracts import (
    ChoiceKind,
    DataSource,
    EvidenceFile,
    EvidencePhoto,
    EvidencePoints,
    LocateResult,
    LocateStatus,
    PhotoLocation,
    PlaceStep,
    Pose,
)
from snapback.vision.locate.thresholds import Thresholds, load_thresholds

log = logging.getLogger("snapback.place")

MAX_SEARCHES = 2
MAX_SECONDS = 10.0
STOP = "stop"
WIDER_INDEX = "wider_index"
DEEPER_CLAIMED = "deeper_claimed"
FOCUS_PREFIX = "focus_scan:"

WIDER_TOP_K = 12  # the #207 setting, for this photo only
DEEPER_TOP_K_CLAIMED = 96

# What a chooser may be shown for a place decision. Anything else is dropped before it leaves.
PLACE_FACT_KEYS = frozenset(
    {
        "bar_failed",
        "best_inliers",
        "bar",
        "spread",
        "rival_ratio",
        "n_scans_in_building",
        "seconds_left",
        "searches_left",
        "covers_unshown_room",
        "est_seconds_wider_index",
        "est_seconds_deeper_claimed",
        "est_seconds_focus_scan",
        "unplaced_photos",
    }
)

_ALIASED = re.compile(r"^P\d+ ")

BAR_KEYS = {
    "inliers": "min_inliers",
    "ratio": "min_inlier_ratio",
    "spread": "claimed_min_spread",
    "ambiguity": "ambiguity_ratio",
}


@dataclass(frozen=True)
class SearchOption:
    """One retry. `scan_model_id` is for the searcher only and is never shown to a chooser."""

    kind: Literal["focus_scan", "wider_index", "deeper_claimed"]
    scan_alias: str | None = None
    scan_model_id: str | None = field(default=None, compare=False, repr=False)

    @property
    def label(self) -> str:
        return f"{FOCUS_PREFIX}{self.scan_alias}" if self.kind == "focus_scan" else self.kind


@dataclass(frozen=True)
class SearchOutcome:
    location: PhotoLocation
    pose: Pose | None = None
    points: EvidencePoints | None = None
    seconds: float | None = None


class PlaceSearcher(Protocol):
    def search(
        self,
        photo_id: str,
        option: SearchOption,
        claimed_property_id: str | None,
        thresholds: Thresholds,
        deadline_s: float,
    ) -> SearchOutcome:
        """Retry one photo with `option`. `thresholds` is `search_thresholds(base, option)`:
        the base bars with only retrieval breadth changed. `deadline_s` is the most this search
        may take: min(what is left of the 10 s retry budget, what is left of the case's time)."""
        ...


def search_thresholds(base: Thresholds, option: SearchOption) -> Thresholds:
    """(Lane V owns the real one, `locate.search_thresholds`, in #223. This copy matches it,
    wider_index top_k 12 and deeper_claimed top_k_claimed 96, and goes when #223 lands.)

    The thresholds a retry runs with: the base, with retrieval breadth changed and every
    verification bar left exactly as it is."""
    if option.kind == "wider_index":
        return replace(base, top_k=max(base.top_k, WIDER_TOP_K))
    if option.kind == "deeper_claimed":
        return replace(base, top_k_claimed=max(base.top_k_claimed, DEEPER_TOP_K_CLAIMED))
    return base  # focus_scan narrows the scope to one scan; the numbers do not move


class PlaceOffer(SearchOffer):
    """A place decision. Same shape as the search offers, so any chooser can take it, with its
    own allow-list for what a model may see."""

    def for_chooser(self) -> SearchOffer:  # type: ignore[override]
        # "P3 best_inliers" is allowed when "best_inliers" is: the alias prefix is not an id.
        facts = {
            k: v
            for k, v in self.facts.items()
            if (k.split(" ", 1)[1] if _ALIASED.match(k) else k) in PLACE_FACT_KEYS
        }
        return SearchOffer(
            self.kind, self.options, self.aliases, facts, self.default, self.default_reason
        )


@dataclass
class _Row:
    location: PhotoLocation
    steps: list[PlaceStep] = field(default_factory=list)
    points: EvidencePoints | None = None
    pose: Pose | None = None
    tried: set[str] = field(default_factory=set)


class PlaceDesk:
    def __init__(
        self,
        located: LocateResult,
        searcher: PlaceSearcher,
        *,
        scans: Mapping[str, str] | None = None,
        thresholds: Thresholds | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_searches: int = MAX_SEARCHES,
        max_seconds: float = MAX_SECONDS,
        case_seconds_left: float | None = None,
        est_seconds: Mapping[str, float] | None = None,
        covers_unshown: Mapping[str, bool] | None = None,
        retry_can_find_elsewhere: bool = True,
        points: Mapping[str, EvidencePoints] | None = None,
    ) -> None:
        self.base = located
        self.searcher = searcher
        self.thresholds = thresholds or load_thresholds()
        self._clock = clock
        self.max_searches = max_searches
        # the 10 s retry budget can never exceed what is left of the case's own time budget
        self.max_seconds = (
            max_seconds if case_seconds_left is None else min(max_seconds, case_seconds_left)
        )
        self.est_seconds = dict(est_seconds or {})
        self.covers_unshown = dict(covers_unshown or {})
        self.retry_can_find_elsewhere = retry_can_find_elsewhere
        self.searches_used = 0
        self.seconds_spent = 0.0
        self._focus: str | None = None
        self.stopped: set[str] = set()
        self.alias_of = {p.photo_id: f"P{i}" for i, p in enumerate(located.photos, start=1)}
        self.photo_of = {a: pid for pid, a in self.alias_of.items()}
        # scan alias -> model id; falls back to the scans the base search placed photos in
        if scans:
            self.scans = dict(scans)
        else:
            seen = dict.fromkeys(p.model_id for p in located.photos if p.model_id)
            self.scans = {f"S{i}": m for i, m in enumerate(seen, start=1)}
        self._scan_alias = {m: a for a, m in self.scans.items()}
        # the base search's matched pairs (E2b): a photo no retry touches keeps them
        base_points = dict(points or {})
        self.rows = {
            p.photo_id: _Row(p, points=base_points.get(p.photo_id)) for p in located.photos
        }
        for row in self.rows.values():
            row.steps.append(
                PlaceStep(option="base", chosen_by="policy", result=_result(row.location))
            )

    # --- the budget and who is left ----------------------------------------------------------

    @property
    def searches_left(self) -> int:
        return max(0, self.max_searches - self.searches_used)

    @property
    def seconds_left(self) -> float:
        return max(0.0, self.max_seconds - self.seconds_spent)

    def unplaced(self) -> list[str]:
        """Aliases of photos the base search left unplaced in an indexed claimed home, nearest
        miss first. Placed, elsewhere and not-indexed photos are never in this list."""
        out = [
            self.alias_of[pid]
            for pid, row in self.rows.items()
            if row.location.status is LocateStatus.NOT_LOCATED
            and self.alias_of[pid] not in self.stopped
        ]
        return sorted(out, key=lambda a: -(self.rows[self.photo_of[a]].location.inliers or 0))

    def _options_for(self, alias: str) -> list[SearchOption]:
        row = self.rows[self.photo_of[alias]]
        options: list[SearchOption] = []
        if len(self.scans) >= 2:
            # "Another scan": the base search spread its faces over every scan of the home, and
            # the placed photos matched in some of them. Focus on a scan none of them used; if
            # every scan was used, any other scan than the photo's own is still a new look.
            used = {
                r.location.model_id
                for r in self.rows.values()
                if r.location.status is LocateStatus.LOCATED_IN_CLAIMED
            }
            others = {a: m for a, m in self.scans.items() if m not in used} or self.scans
            for scan_alias, model_id in others.items():
                if model_id != row.location.model_id:
                    options.append(SearchOption("focus_scan", scan_alias, model_id))
        options += [SearchOption("wider_index"), SearchOption("deeper_claimed")]
        return [o for o in options if o.label not in row.tried]

    def is_open(self) -> bool:
        """Is there a decision to make? Closes the desk quietly when nothing real is left."""
        while self.searches_left > 0 and self.seconds_left > 0 and self.unplaced():
            focus = self._focus_alias()
            if self._options_for(focus):
                return True
            self._stop(focus, "policy")  # every search was tried: nothing to choose
        return False

    def _focus_alias(self) -> str:
        if self._focus is not None:
            return self._focus
        return self.unplaced()[0]

    # --- the offers --------------------------------------------------------------------------

    def offer(self) -> PlaceOffer | None:
        if not self.is_open():
            return None
        if self._focus is None and len(self.unplaced()) > self.searches_left:
            return self._photo_offer()
        return self._search_offer(self._focus_alias())

    def _photo_offer(self) -> PlaceOffer:
        aliases = tuple(self.unplaced())
        facts: dict[str, bool | int | float | str] = {
            "unplaced_photos": len(aliases),
            "searches_left": self.searches_left,
        }
        for a in aliases:
            loc = self.rows[self.photo_of[a]].location
            facts[f"{a} best_inliers"] = loc.inliers or 0
            facts[f"{a} bar_failed"] = loc.bar_failed or "unknown"
            facts[f"{a} covers_unshown_room"] = self.covers_unshown.get(a, False)
        return PlaceOffer(
            kind=ChoiceKind.WHICH_PHOTO.value,
            options=aliases,
            aliases=aliases,
            facts=facts,  # type: ignore[arg-type]
            default=aliases[0],
            default_reason="The closest near miss is the likeliest to place on a retry.",
        )

    def _search_offer(self, alias: str) -> PlaceOffer:
        row = self.rows[self.photo_of[alias]]
        loc = row.location
        options = self._options_for(alias)
        labels = tuple(o.label for o in options) + (STOP,)
        bar = getattr(self.thresholds, BAR_KEYS.get(loc.bar_failed or "", ""), None)
        facts: dict[str, bool | int | float | str] = {
            "bar_failed": loc.bar_failed or "unknown",
            "best_inliers": loc.inliers or 0,
            "n_scans_in_building": len(self.scans),
            "seconds_left": int(self.seconds_left),
            "searches_left": self.searches_left,
            "covers_unshown_room": self.covers_unshown.get(alias, False),
        }
        if bar is not None:
            facts["bar"] = bar
        if loc.spread is not None:
            facts["spread"] = round(loc.spread, 3)
        if loc.rival_ratio is not None:
            facts["rival_ratio"] = round(loc.rival_ratio, 2)
        for kind in ("wider_index", "deeper_claimed", "focus_scan"):
            if kind in self.est_seconds:
                facts[f"est_seconds_{kind}"] = self.est_seconds[kind]
        default, reason = self._policy(options, loc)
        return PlaceOffer(
            kind=ChoiceKind.NEXT_SEARCH.value,
            options=labels,
            aliases=labels,
            facts=facts,  # type: ignore[arg-type]
            default=default,
            default_reason=reason,
        )

    def _policy(self, options: list[SearchOption], loc: PhotoLocation) -> tuple[str, str]:
        by_kind = {o.kind: o for o in options}
        focus = next((o for o in options if o.kind == "focus_scan"), None)
        if focus and loc.bar_failed == "inliers":
            return focus.label, "It fell short on matched points; another scan may match it."
        if "wider_index" in by_kind and (loc.rival_ratio or 0) > 1:
            return WIDER_INDEX, "Another building matched more strongly, so look wider."
        if "deeper_claimed" in by_kind:
            return DEEPER_CLAIMED, "Look at more side faces of this home's own scans."
        if "wider_index" in by_kind:
            return WIDER_INDEX, "Look wider over every building."
        return STOP, "No search is left that could change the answer."

    # --- applying a pick ---------------------------------------------------------------------

    def choose(self, chooser: object) -> tuple[SearchStep, Literal["photo", "search"]]:
        """Ask `chooser` (anything with `.choose(offer)` and `.chosen_by`) about the open offer
        and apply the pick. A menu of one, an off-list pick or a failing chooser is policy."""
        offer = self.offer()
        if offer is None:
            raise RuntimeError("no place decision is open")
        label, step = _decide(offer, chooser)
        self.apply(offer.kind, label, step.chosen_by)
        return step, ("photo" if offer.kind == ChoiceKind.WHICH_PHOTO.value else "search")

    def apply(self, kind: str, label: str, by: Literal["model", "policy"]) -> None:
        if kind == ChoiceKind.WHICH_PHOTO.value:
            self._focus = label
            return
        alias = self._focus_alias()
        if label == STOP:
            self._stop(alias, by)
            return
        option = next(o for o in self._options_for(alias) if o.label == label)
        self._search(alias, option, by)

    def _stop(self, alias: str, by: Literal["model", "policy"]) -> None:
        self.rows[self.photo_of[alias]].steps.append(
            PlaceStep(option=STOP, chosen_by=by, result="skipped")
        )
        self.stopped.add(alias)
        self._focus = None

    def _search(self, alias: str, option: SearchOption, by: Literal["model", "policy"]) -> None:
        pid = self.photo_of[alias]
        row = self.rows[pid]
        row.tried.add(option.label)
        started = self._clock()
        try:
            outcome = self.searcher.search(
                pid,
                option,
                self.base.claimed_property_id,
                search_thresholds(self.thresholds, option),
                self.seconds_left,
            )
        except Exception as exc:
            # A broken retry costs its budget and changes nothing, but it is not silent. Only the
            # error type is logged: its message may carry ids.
            log.warning("place retry %s failed: %s", option.label, type(exc).__name__)
            outcome = None
        wall = max(0.0, self._clock() - started)
        reported = outcome.seconds if outcome and outcome.seconds is not None else 0.0
        seconds = max(wall, reported)  # a searcher cannot under-report its way past the budget
        self.searches_used += 1
        self.seconds_spent += seconds
        self._focus = None
        result: Literal["placed", "not_placed", "elsewhere", "skipped"] = "not_placed"
        if outcome is not None and row.location.status is LocateStatus.NOT_LOCATED:
            new = outcome.location
            # The searcher's word is not taken: a retry result must clear the same bars the base
            # search is held to, or it counts as not placed.
            if new.status is LocateStatus.LOCATED_IN_CLAIMED and self._clears_claimed(new):
                result = "placed"
            elif (
                new.status is LocateStatus.LOCATED_ELSEWHERE
                and self.retry_can_find_elsewhere
                and self._clears_elsewhere(new)
            ):
                result = "elsewhere"
            if result != "not_placed":
                row.location, row.points, row.pose = new, outcome.points, outcome.pose
            elif new.status is LocateStatus.NOT_LOCATED and (new.inliers or 0) >= (
                row.location.inliers or 0
            ):
                row.location, row.points = new, outcome.points  # a nearer miss, still unplaced
        row.steps.append(
            PlaceStep(option=option.label, chosen_by=by, seconds=round(seconds, 2), result=result)
        )

    def _clears_claimed(self, loc: PhotoLocation) -> bool:
        t = self.thresholds
        return (
            loc.inliers is not None
            and loc.inliers >= t.min_inliers
            and loc.inlier_ratio is not None
            and loc.inlier_ratio >= t.min_inlier_ratio
            and loc.spread is not None
            and loc.spread >= t.claimed_min_spread
            # locate()'s ambiguity rule: a rival building far stronger blocks a claimed pass
            and (loc.rival_ratio is None or loc.rival_ratio < t.ambiguity_ratio)
        )

    def _clears_elsewhere(self, loc: PhotoLocation) -> bool:
        """The strict bar for "taken in a different building", which can lead to DON'T PAY."""
        t = self.thresholds
        claimed = self.base.claimed_property_id
        return (
            # locate()'s guards: never "elsewhere" without a claimed home and a known other one
            claimed is not None
            and loc.matched_property_id is not None
            and loc.matched_property_id != claimed
            and loc.inliers is not None
            and loc.inliers >= t.elsewhere_min_inliers
            and loc.inlier_ratio is not None
            and loc.inlier_ratio >= t.min_inlier_ratio
            and loc.spread is not None
            and loc.spread >= t.elsewhere_min_spread
        )

    # --- what it leaves behind -----------------------------------------------------------------

    def located(self) -> LocateResult:
        """The base result with retried photos replaced. Placed photos are never changed."""
        poses = dict(self.base.poses)
        for pid, row in self.rows.items():
            if row.pose is not None:
                poses[pid] = row.pose
        return self.base.model_copy(
            update={
                "photos": [self.rows[p.photo_id].location for p in self.base.photos],
                "poses": poses,
            }
        )

    def evidence_file(self, case_id: str, source: DataSource) -> EvidenceFile:
        return write_evidence_file(
            case_id,
            source,
            self.located(),
            thresholds=self.thresholds,
            points={pid: row.points for pid, row in self.rows.items() if row.points is not None},
            steps={pid: row.steps for pid, row in self.rows.items()},
            scans=self.scans,
            thresholds_version=self.base.thresholds_version,
        )

    def bar_of(self, alias: str) -> int | float:
        """The bar the photo's `bar_failed` names, as a number (0 when none)."""
        loc = self.rows[self.photo_of[alias]].location
        return getattr(self.thresholds, BAR_KEYS.get(loc.bar_failed or "", ""), 0)

    def unsure_lines(self) -> list[tuple[str, str]]:
        """(alias, key) for each photo that fell short, for the code-raised UNSURE events.
        The sentences live in the string table."""
        out = []
        for a in self.unplaced():
            loc = self.rows[self.photo_of[a]].location
            if loc.bar_failed:
                out.append((a, loc.bar_failed))
        return out


def _result(loc: PhotoLocation) -> Literal["placed", "not_placed", "elsewhere", "skipped"]:
    if loc.status is LocateStatus.LOCATED_IN_CLAIMED:
        return "placed"
    if loc.status is LocateStatus.LOCATED_ELSEWHERE:
        return "elsewhere"
    return "not_placed"


def write_evidence_file(
    case_id: str,
    source: DataSource,
    located: LocateResult,
    *,
    thresholds: Thresholds | None = None,
    points: Mapping[str, EvidencePoints] | None = None,
    steps: Mapping[str, list[PlaceStep]] | None = None,
    scans: Mapping[str, str] | None = None,
    thresholds_version: str | None = None,
) -> EvidenceFile:
    """The evidence file the code writes for the "How we know" drawer: every photo's
    measurements, the bars they were held to, and its matched pairs (`points`, at most 48,
    normalised to 0..1, E2b). Used with or without a retry desk. Aliases only (P1, S1)."""
    t = thresholds or load_thresholds()
    points = points or {}
    steps = steps or {}
    if scans:
        scan_alias = {m: a for a, m in scans.items()}
    else:
        seen = dict.fromkeys(p.model_id for p in located.photos if p.model_id)
        scan_alias = {m: f"S{i}" for i, m in enumerate(seen, start=1)}
    photos = [
        EvidencePhoto(
            alias=f"P{number}",
            status=loc.status,
            inliers=loc.inliers,
            inlier_ratio=loc.inlier_ratio,
            spread=loc.spread,
            rival_ratio=loc.rival_ratio,
            bar_failed=loc.bar_failed,
            room_label=loc.room_label,
            scan_alias=scan_alias.get(loc.model_id or ""),
            searches=list(steps.get(loc.photo_id, [])),
            points=points.get(loc.photo_id),
        )
        for number, loc in enumerate(located.photos, start=1)
    ]
    return EvidenceFile(
        case_id=case_id,
        source=source,
        thresholds_version=thresholds_version or located.thresholds_version or t.version,
        bars={
            "min_inliers": t.min_inliers,
            "min_inlier_ratio": t.min_inlier_ratio,
            "claimed_min_spread": t.claimed_min_spread,
            "elsewhere_min_inliers": t.elsewhere_min_inliers,
            "elsewhere_min_spread": t.elsewhere_min_spread,
            "ambiguity_ratio": t.ambiguity_ratio,
        },
        photos=photos,
    )
