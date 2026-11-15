"""The Planner's follow-ups: after code has run every check, the deep agent reads the card's gaps
and may choose up to two more checks from a fixed menu, each with a reason tied to one gap.

The gaps are the card's own lines that are not settled (not checked, not shown, on hold) and
the card's standing "Not checked" list. The model sees each gap as a label and a status word
only (G1 "Owner: not checked"), never a line's text, so nothing from the record reaches it that
the sub-agents do not already read.

The menu is fixed in code (`MENU`). An item is on offer for a case only when the API attached
a runner for it (`case.followup_runners`, the existing lookup functions: Google Lens, the web
phrase search, the Census and RDAP lookups) and it covers at least one open gap. A pick must
name an item on offer, a gap that item covers and a reason; anything else is refused and costs
nothing. At most `MAX_PICKS` picks run per case, each within `CHECK_TIMEOUT_S` and the agent's
own time limit; a check still running at its limit is "not checked".

A result becomes an information line on the card (`ModuleEvidence.followups`) and a step in
the timeline, each naming its source. `decide()` never reads it: a follow-up cannot clear,
raise or lower a case. With no model, code makes a recorded pick instead (`run_recorded`), the
same way every time, labelled FIXTURE.

This module does not import deepagents, so it works, and is tested, without the `agent` extra.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from snapback.agent.trace import clean_reason
from snapback.card import strings
from snapback.contracts import (
    CardTone,
    ChoiceKind,
    DataSource,
    FollowUpLine,
    PublicStatus,
    TraceKind,
)

MAX_PICKS = 2
CHECK_TIMEOUT_S = 8.0
FOLLOWUP_LABEL = "label.followup"
# The tones that leave a line open: something to look at, not a finding either way.
_OPEN_TONES = (CardTone.NOT_CHECKED, CardTone.NOT_SHOWN, CardTone.HOLD)

By = Literal["model", "fixture"]


@dataclass(frozen=True)
class Outcome:
    """What one follow-up check came back with. `count` is shown when the check counts things."""

    status: PublicStatus
    source: DataSource
    count: int | None = None


Runner = Callable[[], Outcome]


@dataclass(frozen=True)
class MenuItem:
    id: str
    name: str  # plain words for the trace and the card
    source_name: str  # who answered: "Google Lens", "Web search", "Census", "RDAP"
    covers: frozenset[str]  # the card line keys (and not-checked items) it can say more about


MENU: dict[str, MenuItem] = {
    item.id: item
    for item in (
        MenuItem(
            "lens",
            "Google Lens search of the ad's photos",
            "Google Lens",
            frozenset(
                {
                    "label.here_now",
                    "label.for_sale",
                    "label.seen_before",
                    "label.matched_home",
                    "label.recently_rented",
                    "label.real",
                }
            ),
        ),
        MenuItem(
            "phrase_search",
            "web search for the ad's own words",
            "Web search",
            frozenset(
                {
                    "label.contact",
                    "label.allowed",
                    "label.office",
                    "label.license",
                    "label.seen_before",
                    "label.payment_ask",
                    "label.link",
                    "label.here_now",
                }
            ),
        ),
        MenuItem(
            "census", "Census address check, run again", "Census", frozenset({"label.address"})
        ),
        MenuItem(
            "rdap",
            "domain age lookup, run again",
            "RDAP",
            frozenset({"label.link", "label.link_domain"}),
        ),
    )
}


@dataclass(frozen=True)
class Gap:
    alias: str  # G1, G2, ...
    key: str  # the line's label key ("label.owner") or a not-checked item ("not_checked.id")
    words: str  # "Owner: not checked", code words only

    def covered_by(self, item: MenuItem) -> bool:
        return self.key in item.covers


def card_gaps(case: Any) -> list[Gap]:
    """The card's open lines, then its standing "Not checked" list, as aliased gaps."""
    from snapback.verdict import build_card

    card = build_card(case.evidence, lang=case.lang)
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in card.rows:
        for line in row.lines:
            if line.tone not in _OPEN_TONES or not line.key or line.key == FOLLOWUP_LABEL:
                continue
            if line.key in seen:
                continue
            seen.add(line.key)
            found.append(
                (line.key, f"{line.label}: {strings.tone_word(line.tone, row.kind, case.lang)}")
            )
    for item_key in ("not_checked.id", "not_checked.lease", "not_checked.ownership"):
        word = strings.text(item_key, case.lang)
        if word in card.not_checked:
            found.append((item_key, f"{strings.text('followup.not_checked', case.lang)}: {word}"))
    return [Gap(f"G{i}", key, words) for i, (key, words) in enumerate(found, start=1)]


def runners_of(case: Any) -> dict[str, Runner]:
    return dict(getattr(case, "followup_runners", None) or {})


def menu_for(case: Any, gaps: list[Gap]) -> list[MenuItem]:
    """The items on offer: a runner is attached and the item covers an open gap. Menu order."""
    runners = runners_of(case)
    return [
        item
        for item in MENU.values()
        if item.id in runners and any(g.covered_by(item) for g in gaps)
    ]


class FollowUpDesk:
    """The follow-up choices for one case: the budget, the refusals and the runs. One per case
    (`desk_of`), so the limit holds across every call the agent makes."""

    def __init__(
        self,
        case: Any,
        *,
        deadline: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        check_timeout_s: float = CHECK_TIMEOUT_S,
    ) -> None:
        self.case = case
        self.deadline = deadline
        self.clock = clock
        self.check_timeout_s = check_timeout_s
        self.picks: list[FollowUpLine] = []
        self._lock = threading.Lock()

    def picks_left(self) -> int:
        return MAX_PICKS - len(self.picks)

    def offer(self) -> dict[str, Any]:
        """What the model sees: gaps (alias and code words), the items on offer, picks left."""
        gaps = card_gaps(self.case)
        items = menu_for(self.case, gaps) if self.picks_left() > 0 else []
        chosen = {p.check for p in self.picks}
        return {
            "picks_left": self.picks_left(),
            "gaps": {g.alias: g.words for g in gaps},
            "menu": {
                item.id: {
                    "what": item.name,
                    "source": item.source_name,
                    "for_gaps": [g.alias for g in gaps if g.covered_by(item)],
                }
                for item in items
                if item.id not in chosen
            },
            "note": (
                "Pick at most the picks left, or none. A result is an information line; it never "
                "changes the result on the card."
            ),
        }

    def choose(self, check: str, gap: str, reason: str, *, by: By = "model") -> str:
        """Validate one pick, run it within its limits and keep its result. Returns the plain
        line the agent reads back: the result, or why the pick was refused."""
        with self._lock:
            if self.picks_left() <= 0:
                return f"Refused: the budget is {MAX_PICKS} follow-ups and it is spent."
            gaps = {g.alias: g for g in card_gaps(self.case)}
            item = MENU.get(str(check).strip())
            if item is None or item.id not in runners_of(self.case):
                return "Refused: that check is not on the menu for this case."
            if any(p.check == item.id for p in self.picks):
                return "Refused: that check has already run."
            target = gaps.get(str(gap).strip().upper())
            if target is None:
                return "Refused: name one of the gaps listed, such as G1."
            if not target.covered_by(item):
                return f"Refused: {item.id} cannot say anything about {target.alias}."
            said = " ".join(str(reason or "").split())
            cleaned = clean_reason(said, "")
            if not cleaned:
                return "Refused: a pick needs one plain sentence of reason tied to the gap."
            line = self._run(item, target, cleaned, by)
            self.picks.append(line)
        _keep(self.case, line, item, target)
        return result_words(line, self.case.lang)

    def _run(self, item: MenuItem, gap: Gap, reason: str, by: By) -> FollowUpLine:
        limit = self.check_timeout_s
        if self.deadline is not None:
            limit = min(limit, self.deadline - self.clock())
        outcome: list[Outcome] = []

        def work() -> None:
            try:
                outcome.append(runners_of(self.case)[item.id]())
            except Exception:  # a check that broke is a check that did not happen
                return

        if limit > 0:
            worker = threading.Thread(target=work, name=f"followup-{item.id}", daemon=True)
            worker.start()
            worker.join(limit)  # past the limit the thread is left; its answer is dropped
        got = outcome[0] if outcome and limit > 0 else None
        timed_out = got is None
        return FollowUpLine(
            check=item.id,
            gap=gap.words,
            reason=reason,
            status=PublicStatus.NOT_CHECKED if timed_out else got.status,
            count=None if timed_out else got.count,
            source_name=item.source_name,
            data_source=got.source if got is not None else self.case.trace.source,
            chosen_by=by,
        )


def desk_of(case: Any) -> FollowUpDesk:
    desk = case.__dict__.get("_followup_desk")
    if desk is None:
        desk = case.__dict__["_followup_desk"] = FollowUpDesk(
            case, deadline=case.__dict__.get("_agent_deadline")
        )
    return desk


def result_words(line: FollowUpLine, lang: str = strings.DEFAULT_LANG) -> str:
    """The result in the table's words, naming its source."""
    text = strings.text(f"followup.{line.check}.{line.status.value}", lang, count=line.count or 0)
    return strings.text("followup.result", lang, text=text, source=line.source_name)


def evidence_lock_of(case: Any) -> Any:
    """The case's own evidence lock (the API's case RLock), so a follow-up written from the
    agent's thread never erases evidence the case wrote meanwhile (an office's answer, a reply).
    A session with none gets one of its own."""
    lock = getattr(case, "evidence_lock", None)
    if lock is None:
        lock = case.__dict__.setdefault("_followup_lock", threading.RLock())
    return lock


def _keep(case: Any, line: FollowUpLine, item: MenuItem, gap: Gap) -> None:
    """The pick and its result go into the trace, the evidence (card info line) and the note.
    All under the case's evidence lock: read, copy and assign are one step."""
    with evidence_lock_of(case):
        _keep_locked(case, line, item, gap)


def _keep_locked(case: Any, line: FollowUpLine, item: MenuItem, gap: Gap) -> None:
    lang = case.lang
    reason = line.reason
    if line.chosen_by == "fixture":
        reason = strings.text("trace.followup.recorded", lang, reason=reason)
    case.trace.emit(
        TraceKind.CHOICE,
        strings.text("trace.followup.pick", lang, check=item.name, gap=gap.words, reason=reason),
        choice=ChoiceKind.FOLLOW_UP,
        options=list(MENU),
        pick=item.id,
        chosen_by="model" if line.chosen_by == "model" else "policy",
    )
    case.trace.emit(
        TraceKind.TOOL,
        strings.text("trace.followup.ran", lang, check=item.name, result=result_words(line, lang)),
        pick=f"followup:{item.id}",
        chosen_by="model" if line.chosen_by == "model" else "policy",
    )
    case.evidence = case.evidence.model_copy(update={"followups": [*case.evidence.followups, line]})
    from snapback.agent import casework

    casework.keep_note(
        case, casework.note_path(case.case_id, casework.FOLLOWUPS), note_text(case), "policy"
    )


def note_text(case: Any) -> str:
    """The follow-ups note, from code: one line per pick with its gap, reason and result."""
    lines = ["Source: follow-up checks chosen after code ran every check"]
    for line in case.evidence.followups:
        lines.append(
            f"{line.check} for {line.gap}: {line.reason} Result: {result_words(line, case.lang)}"
        )
    return "\n".join(lines)


# --- with no model: a recorded pick ---------------------------------------------------------------

RECORDED_REASON = "recorded.{check}"


def recorded_picks(case: Any) -> list[tuple[str, str]]:
    """The picks code makes with no model, the same way every time: menu order, each item once,
    for the first open gap it covers, at most `MAX_PICKS`."""
    gaps = card_gaps(case)
    picks: list[tuple[str, str]] = []
    for item in menu_for(case, gaps):
        gap = next((g for g in gaps if g.covered_by(item)), None)
        if gap is not None:
            picks.append((item.id, gap.alias))
        if len(picks) == MAX_PICKS:
            break
    return picks


def run_recorded(case: Any) -> list[FollowUpLine]:
    """Run the recorded picks (no model configured), then the recorded next step. Each is
    labelled FIXTURE in the trace."""
    desk = desk_of(case)
    for check, gap in recorded_picks(case):
        desk.choose(check, gap, strings.text(f"followup.reason.{check}", case.lang), by="fixture")
    step = recorded_next_step(case)
    if step is not None:
        choose_next_step(
            case, step[0], step[1], strings.text(f"next.reason.{step[0]}", case.lang), by="fixture"
        )
    return list(desk.picks)


# --- the next step for the renter: a draft, never sent


@dataclass(frozen=True)
class NextStep:
    id: str
    name: str
    covers: frozenset[str]


NEXT_STEPS: dict[str, NextStep] = {
    step.id: step
    for step in (
        NextStep(
            "ask_poster",
            "ask the poster for a photo at a spot in the home",
            frozenset({"label.here_now", "label.allowed", "label.contact", "label.seen_before"}),
        ),
        NextStep(
            "ask_licence",
            "ask the poster for their Texas licence number",
            frozenset({"label.license", "label.allowed", "label.contact", "label.office"}),
        ),
        NextStep(
            "call_office",
            "call the leasing office on record",
            frozenset({"label.allowed", "label.contact", "label.office", "label.payment_ask"}),
        ),
        NextStep(
            "tour_questions",
            "bring the tour questions to the viewing",
            frozenset(
                {
                    "label.here_now",
                    "label.rent_vs_record",
                    "label.rent_vs_hud",
                    "label.unit",
                    "not_checked.lease",
                    "not_checked.id",
                    "not_checked.ownership",
                }
            ),
        ),
    )
}


def next_step_draft(case: Any, step: str) -> str | None:
    """The code-written draft for one next step, or None when this case cannot offer it. The
    poster's question is the challenge code already drafted for the renter to approve."""
    if step == "ask_poster":
        pending = getattr(case, "pending_challenge", None)
        return getattr(pending, "text", None)
    if step == "call_office":
        return (
            strings.text("next.draft.call_office", case.lang) if case.evidence.authority else None
        )
    if step in NEXT_STEPS:
        return strings.text(f"next.draft.{step}", case.lang)
    return None


def next_step_offer(case: Any) -> dict[str, Any]:
    gaps = card_gaps(case)
    taken = case.__dict__.get("_next_step") is not None
    return {
        "chosen": taken,
        "gaps": {g.alias: g.words for g in gaps},
        "steps": {}
        if taken
        else {
            step.id: {
                "what": step.name,
                "for_gaps": [g.alias for g in gaps if g.key in step.covers],
            }
            for step in NEXT_STEPS.values()
            if next_step_draft(case, step.id) and any(g.key in step.covers for g in gaps)
        },
        "note": "Choose one. It is a draft for the renter; nothing is ever sent.",
    }


def choose_next_step(case: Any, step: str, gap: str, reason: str, *, by: By = "model") -> str:
    """Pick the one next step for the renter, for one gap, with a reason. Code writes the draft;
    it goes to the trace and the next-step note, and is never sent. Check and set are one step
    under the case's evidence lock, so two calls in one turn cannot both pass."""
    with evidence_lock_of(case):
        return _choose_next_step(case, step, gap, reason, by)


def _choose_next_step(case: Any, step: str, gap: str, reason: str, by: By) -> str:
    if case.__dict__.get("_next_step") is not None:
        return "Refused: the next step is already chosen."
    item = NEXT_STEPS.get(str(step).strip())
    draft = next_step_draft(case, item.id) if item is not None else None
    if item is None or not draft:
        return "Refused: that step is not on the list for this case."
    target = {g.alias: g for g in card_gaps(case)}.get(str(gap).strip().upper())
    if target is None or target.key not in item.covers:
        return "Refused: name one of the gaps listed that this step is for."
    cleaned = clean_reason(" ".join(str(reason or "").split()), "")
    if not cleaned:
        return "Refused: a pick needs one plain sentence of reason tied to the gap."
    case.__dict__["_next_step"] = (item.id, target.words, cleaned, draft)
    lang = case.lang
    shown = (
        strings.text("trace.followup.recorded", lang, reason=cleaned)
        if by == "fixture"
        else cleaned
    )
    case.trace.emit(
        TraceKind.CHOICE,
        strings.text("trace.next.pick", lang, step=item.name, gap=target.words, reason=shown),
        choice=ChoiceKind.NEXT_STEP,
        options=[target.words],  # the gap, in code words, for the timeline
        pick=item.id,
        chosen_by="model" if by == "model" else "policy",
    )
    from snapback.agent import casework

    casework.keep_note(
        case,
        casework.note_path(case.case_id, casework.NEXT_STEP),
        strings.text(
            "next.note", lang, step=item.name, gap=target.words, reason=cleaned, draft=draft
        ),
        "policy",
    )
    return strings.text("next.done", lang, draft=draft)


def recorded_next_step(case: Any) -> tuple[str, str] | None:
    """With no model: the first step on offer, for the first gap it covers."""
    offer = next_step_offer(case)
    for step_id, step in offer["steps"].items():
        if step["for_gaps"]:
            return step_id, step["for_gaps"][0]
    return None


# --- the runners: existing lookup functions, bound to one case by the API -------------------------


def build_runners(
    listing_text: str,
    source: DataSource,
    settings: Any,
    *,
    web_inputs: Any = None,
    web_ran: bool = False,
    place_check: Any = None,
    domain_check: Any = None,
) -> dict[str, Runner]:
    """The menu items this case can run, each a call to a lookup the API already has. An item
    with nothing to look at, no key, or an answer already in hand is left off. A FIXTURE case
    runs only what has a recorded answer, so nothing in it touches the network."""
    from datetime import UTC, datetime

    from snapback.public import census, fetch, lens, rdap

    text = listing_text or ""
    fetcher = fetch.fetcher_for(source)
    live = source is DataSource.LIVE
    runners: dict[str, Runner] = {}

    photos = lens.photo_urls(text)
    key = settings.serpapi_api_key.get_secret_value() if settings.serpapi_api_key else None
    if live:
        lens_ok = bool(settings.snapback_lens) and key is not None
    else:
        lens_ok = any(fetcher.get("lens", p, "", 0) is not None for p in photos)
    if photos and lens_ok:
        timeout = settings.snapback_lens_timeout_s

        def run_lens() -> Outcome:
            found = lens.check(text, fetcher, key or "recorded", timeout)
            return Outcome(PublicStatus.FOUND if found else PublicStatus.NO_MATCH, source)

        runners["lens"] = run_lens

    phrase = getattr(web_inputs, "ad_phrase", None)
    token, apify = settings.brightdata_api_token, settings.apify_token
    if live and phrase and not web_ran and (token is not None or apify is not None):

        def run_phrase() -> Outcome:
            import httpx

            from snapback.agent.web import clients
            from snapback.agent.web.facts import search_hits

            city = getattr(web_inputs, "city", None)
            query = f'"{phrase}"' + (f" {city}" if city else "")
            with httpx.Client() as http:
                if token is not None:
                    answer = clients.serp(
                        http, token, settings.brightdata_serp_zone, query, CHECK_TIMEOUT_S
                    )
                else:
                    answer = clients.apify_search(http, apify, query, CHECK_TIMEOUT_S)
            hits = search_hits(answer, getattr(web_inputs, "website_host", None))
            status = PublicStatus.FOUND if hits else PublicStatus.NO_MATCH
            return Outcome(status, source, count=len(hits))

        runners["phrase_search"] = run_phrase

    timeout = settings.snapback_public_timeout_s
    address = census.address_in(text) if settings.snapback_census_geocoder else None
    unsettled = place_check is None or place_check.status is PublicStatus.NOT_CHECKED
    if live and address and unsettled:
        runners["census"] = lambda: _public(census.check(address, fetcher, timeout), source)

    host = rdap.link_host(text) if settings.snapback_rdap else None
    unsettled = domain_check is None or domain_check.status is PublicStatus.NOT_CHECKED
    if live and host and unsettled:
        runners["rdap"] = lambda: _public(
            rdap.check(host, fetcher, today=datetime.now(UTC).date(), timeout=timeout), source
        )
    return runners


def _public(found: Any, source: DataSource) -> Outcome:
    return Outcome(found.status, getattr(found, "source", source) or source)
