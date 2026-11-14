"""The finder's preferences sub-agent: what the renter's picks and passes teach, offered back.

Code reads the renter's events from the bus and counts. A count that is lopsided enough becomes a
candidate: a short menu of fixed options, each already worked out in code (the key it would set,
the question for the renter, the number it rests on). The sub-agent only picks one from that menu
and says why in one sentence. The same menu runs under the code policy when no model is used.

Nothing here applies anything. A pick becomes a *proposal*; only the renter's "yes" merges it into
the applied preferences (`snapback.preferences.merge`). A renter's words never become a preference:
the facts a model may see are the counts under `FINDER_FACT_KEYS`, and `guard_facts` refuses
anything else before it can reach a model.

This module does not import deepagents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from snapback.contracts import CasePreferences, PreferencesUpdate
from snapback.events import Event, EventKind

# What the sub-agent may be told. Counts as "n of m", and one yes or no.
FINDER_FACT_KEYS = frozenset(
    {
        "passed_walkups",
        "passed_no_parking",
        "picked_with_scan",
        "picked_below_budget",
        "budget_set",
        "said_no_walkup",
        "said_parking",
    }
)
_COUNT_TEXT = re.compile(r"\d{1,3} of \d{1,3}")

WAIT = "wait"
# Priority order: the order the code policy takes them in, and the order a menu lists them.
OPTIONS = (
    "propose_no_walkup",
    "propose_parking",
    "propose_prefer_scans",
    "propose_lower_budget",
)
MIN_SIGNALS = 2  # a pattern needs at least this many of the same thing
MIN_SHARE = 0.75  # and at least this share of the places it could be seen in
BELOW_BUDGET_SHARE = 0.85  # a pick "below budget" costs at most this share of the budget
ROUND_TO = 50


class FactLeak(ValueError):
    """Something other than an allow-listed count or yes/no was about to go to a model."""


def guard_facts(facts: dict[str, object]) -> dict[str, object]:
    """The allow-list. Refuses (never trims) a key we did not plan for and a value that is not
    "n of m" or a yes/no, so a leak is a failing test, not a quiet omission."""
    for key, value in facts.items():
        if key not in FINDER_FACT_KEYS:
            raise FactLeak(f"{key} is not a fact a model may see")
        if isinstance(value, bool):
            continue
        if not (isinstance(value, str) and _COUNT_TEXT.fullmatch(value)):
            raise FactLeak(f"{key} holds a value a model may not see")
    return facts


@dataclass(frozen=True)
class Signals:
    """The counts, worked out from a session's renter events. `of` is where it could be seen."""

    walkups_passed: int = 0
    walkups_seen: int = 0
    no_parking_passed: int = 0
    parking_seen: int = 0
    scan_picked: int = 0
    picks: int = 0
    below_budget_picked: int = 0
    priced_picks: int = 0
    budget: int | None = None
    highest_pick_rent: int | None = None
    n_events: int = 0
    said_no_walkup: bool = False  # the renter's own words asked for this (read by code)
    said_parking: bool = False


def read_signals(events: list[Event], session: str) -> Signals:
    """Count one session's picks, passes and budget. Only RENTER events count: a scripted or
    pipeline event never teaches the agent anything about a person."""
    walkups_passed = walkups_seen = no_parking_passed = parking_seen = 0
    scan_picked = picks = 0
    picked_rents: list[int] = []
    budget: int | None = None
    said_no_walkup = said_parking = False
    n = 0
    for event in events:
        if event.source.value != "renter" or event.payload.get("session") != session:
            continue
        p = event.payload
        if event.kind is EventKind.BRIEF_CHANGED:
            n += 1
            if p.get("brief_field") == "budget" and isinstance(p.get("rent_max"), int):
                budget = int(p["rent_max"])  # type: ignore[arg-type]
            said_no_walkup = said_no_walkup or p.get("brief_field") == "no_walkup"
            said_parking = said_parking or p.get("brief_field") == "parking"
        elif event.kind is EventKind.PLACE_PASSED:
            n += 1
            if isinstance(p.get("walkup"), bool):
                walkups_seen += 1
                walkups_passed += 1 if p["walkup"] else 0
            if isinstance(p.get("parking"), bool):
                parking_seen += 1
                no_parking_passed += 0 if p["parking"] else 1
        elif event.kind is EventKind.PLACE_PICKED:
            n += 1
            picks += 1
            scan_picked += 1 if p.get("has_scan") is True else 0
            if isinstance(p.get("rent_from"), int):
                picked_rents.append(int(p["rent_from"]))  # type: ignore[arg-type]
    below = (
        sum(1 for r in picked_rents if budget and r <= budget * BELOW_BUDGET_SHARE) if budget else 0
    )
    return Signals(
        walkups_passed=walkups_passed,
        walkups_seen=walkups_seen,
        no_parking_passed=no_parking_passed,
        parking_seen=parking_seen,
        scan_picked=scan_picked,
        picks=picks,
        below_budget_picked=below,
        priced_picks=len(picked_rents),
        budget=budget,
        highest_pick_rent=max(picked_rents) if picked_rents else None,
        n_events=n,
        said_no_walkup=said_no_walkup,
        said_parking=said_parking,
    )


def facts_of(signals: Signals) -> dict[str, object]:
    """What a model may be told (and what the Finder tab shows as "what I've learned"). Counts
    only: no place, no price, no amount."""
    out: dict[str, object] = {"budget_set": signals.budget is not None}
    if signals.walkups_seen:
        out["passed_walkups"] = f"{signals.walkups_passed} of {signals.walkups_seen}"
    if signals.parking_seen:
        out["passed_no_parking"] = f"{signals.no_parking_passed} of {signals.parking_seen}"
    if signals.picks:
        out["picked_with_scan"] = f"{signals.scan_picked} of {signals.picks}"
    if signals.budget is not None and signals.priced_picks:
        out["picked_below_budget"] = f"{signals.below_budget_picked} of {signals.priced_picks}"
    if signals.said_no_walkup:
        out["said_no_walkup"] = True
    if signals.said_parking:
        out["said_parking"] = True
    return guard_facts(out)


def _lopsided(n: int, of: int) -> bool:
    return n >= MIN_SIGNALS and of > 0 and n / of >= MIN_SHARE


def _round_up(value: float) -> int:
    whole = int(value)
    whole += 0 if whole == value else 1
    return -(-whole // ROUND_TO) * ROUND_TO


@dataclass(frozen=True)
class Candidate:
    """One thing the agent could offer to remember. All of it is worked out in code."""

    key: str
    update: PreferencesUpdate
    text: str  # the question for the renter
    evidence: str  # what it rests on, in words
    basis: str  # the fact key it rests on, for the trace


def candidates(signals: Signals, applied: CasePreferences) -> dict[str, Candidate]:
    """The proposals the counts support and the renter has not already accepted, by key."""
    out: dict[str, Candidate] = {}
    s = signals
    walkups = _lopsided(s.walkups_passed, s.walkups_seen)
    if not applied.no_walkup and (walkups or s.said_no_walkup):
        out["propose_no_walkup"] = Candidate(
            "propose_no_walkup",
            PreferencesUpdate(no_walkup=True),
            "Skip walk-ups from now on?",
            f"you passed on {s.walkups_passed} of {s.walkups_seen} walk-ups"
            if walkups
            else "you said no walk-ups",
            "passed_walkups" if walkups else "said_no_walkup",
        )
    parking = _lopsided(s.no_parking_passed, s.parking_seen)
    if not applied.needs_parking and (parking or s.said_parking):
        out["propose_parking"] = Candidate(
            "propose_parking",
            PreferencesUpdate(needs_parking=True),
            "Only show places with parking?",
            f"you passed on {s.no_parking_passed} of {s.parking_seen} places without parking"
            if parking
            else "you asked about parking",
            "passed_no_parking" if parking else "said_parking",
        )
    if not applied.prefer_scans and _lopsided(s.scan_picked, s.picks):
        out["propose_prefer_scans"] = Candidate(
            "propose_prefer_scans",
            PreferencesUpdate(prefer_scans=True),
            "Show places with a 3D scan first?",
            f"you picked {s.scan_picked} of {s.picks} places that have a 3D scan",
            "picked_with_scan",
        )
    if s.budget and s.highest_pick_rent and _lopsided(s.below_budget_picked, s.priced_picks):
        cap = _round_up(s.highest_pick_rent * 1.10)
        if cap < s.budget and (applied.max_rent is None or cap < applied.max_rent):
            out["propose_lower_budget"] = Candidate(
                "propose_lower_budget",
                PreferencesUpdate(max_rent=cap),
                f"Lower your budget to ${cap:,} a month?",
                f"{s.below_budget_picked} of your {s.priced_picks} picks cost well under "
                "your budget",
                "picked_below_budget",
            )
    return out


@dataclass
class PrefDesk:
    """The preferences sub-agent's open decision: a menu of candidates not yet offered. A model
    (through `choose`) or the code policy (`policy_pick`) takes one at a time; the desk records
    each pick with who made it. It never applies anything."""

    pool: dict[str, Candidate]
    picked: list[tuple[Candidate, str, str]] = field(default_factory=list)  # cand, by, reason
    waited: bool = False

    def menu(self) -> list[str]:
        return [k for k in OPTIONS if k in self.pool] + ([WAIT] if self.pool else [])

    def open(self) -> bool:
        return bool(self.pool) and not self.waited

    def choose(self, option: str, reason: str, by: str) -> bool:
        """Take `option` if it is on the menu. False (and nothing changes) otherwise."""
        if not self.open() or option not in self.menu():
            return False
        if option == WAIT:
            self.waited = True
            self.picked.append((_WAIT_CANDIDATE, by, reason))
            return True
        self.picked.append((self.pool.pop(option), by, reason))
        return True

    def policy_pick(self) -> bool:
        """The code policy: the first candidate in priority order, with a code-written reason."""
        menu = [k for k in self.menu() if k != WAIT]
        if not menu:
            return False
        cand = self.pool[menu[0]]
        return self.choose(
            cand.key, f"{cand.evidence.capitalize()}, so this is worth offering.", "policy"
        )

    def settle_policy(self) -> None:
        while self.open() and self.policy_pick():
            pass


_WAIT_CANDIDATE = Candidate("wait", PreferencesUpdate(), "", "", "")
