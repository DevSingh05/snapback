"""One case, as a bounded sequence of choices.

The agent has five kinds of choice and nothing else: which checks to run, which floor plan,
which spot, retry or stop, and asking the renter. This class owns the option set for each one,
so whoever is choosing (a language model, or the code policy) can only pick from a list that
code wrote. Three of them are never the model's:

- the spot is a random draw, so a poster cannot predict it and a model cannot bias it;
- only the renter approves a message before it is sent;
- the state at the end is `decide()` on the evidence gathered. A choice can change how much
  evidence there is. It cannot change what the evidence says.

What a model is shown for a choice is the `Offer`: aliases instead of labels where a label came
from a record, and derived facts (counts and yes/no), never sponsor images or records.
"""

import random
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Literal

from snapback.agent.casework import Note
from snapback.agent.modules import ChallengeOutcome, Modules
from snapback.agent.place import PlaceDesk, PlaceSearcher, write_evidence_file
from snapback.agent.planner import ASK_FIELDS, Plan, PlanKind
from snapback.agent.scope import ListingScope
from snapback.agent.trace import Trace, clean_reason
from snapback.card import strings
from snapback.contracts import (
    ChoiceKind,
    EvidenceFile,
    FloorPlanCandidate,
    LocateStatus,
    ModuleEvidence,
    PresenceStatus,
    SpotCandidate,
    TraceKind,
    Verdict,
)
from snapback.verdict import decide, presence_of, to_evidence

MAX_RETRIES = 2
MAX_LATE_ASKS = 1  # a reply that came too late (and is not a copy) is asked for again once
TOP_SPOTS = 5

TWIN_RULES_CHALLENGE = "twin+rules+challenge"
RULES_CHALLENGE = "rules+challenge"
RULES_ONLY = "rules only"
STATE_ONLY = "state only"

ACCEPT = "accept"
RETRY = "retry at a new spot"
STOP = "stop at hold"

SEND = "send"
EDIT = "edit"
CANCEL = "cancel"
UPDATED = "updated"  # a STATUS event's pick: the state moved after more checks
DECISIONS = (SEND, EDIT, CANCEL)


class Step(StrEnum):
    CHECKS = "checks"
    PLACE = "place"  # E1: the short retry budget for photos the base search could not place
    PLAN = "plan"  # A24: which evidence-gated check runs next (order only)
    ASK = "ask"  # A24 stretch: the renter was asked for the license number; waiting for them
    FLOOR_PLAN = "floor_plan"
    SPOT = "spot"
    APPROVAL = "approval"
    REPLY = "reply"  # the challenge was sent; waiting for the poster's reply photo (A14)
    RETRY = "retry"
    DONE = "done"


@dataclass(frozen=True)
class Offer:
    """One open choice, as shown to whoever picks."""

    kind: ChoiceKind
    options: tuple[str, ...]  # labels, as they appear in the trace
    aliases: tuple[str, ...]  # what a model sees, in the same order
    facts: Mapping[str, bool | int | str]  # derived facts only
    default: str  # the code policy's pick (a label)
    default_reason: str

    def resolve(self, pick: object) -> str | None:
        """The label for a pick given as a label or an alias; None if it is neither."""
        wanted = str(pick or "").strip().casefold()
        for label, alias in zip(self.options, self.aliases, strict=True):
            if wanted in (label.casefold(), alias.casefold()):
                return label
        return None


@dataclass(frozen=True)
class ChallengeDraft:
    """The message the renter is asked to approve. Nothing is sent before they do."""

    spot_id: str
    spot_label: str
    code: str
    text: str


class CaseSession:
    def __init__(
        self,
        case_id: str,
        modules: Modules,
        trace: Trace,
        *,
        rng: random.Random | None = None,
        lang: str = strings.DEFAULT_LANG,
        ask_enabled: bool = False,
    ) -> None:
        self.case_id = case_id
        self.ask_enabled = ask_enabled  # may the agent ask the renter for the license number?
        self.modules = modules
        self.trace = trace
        self.lang = lang
        # SystemRandom by default: the draw must not be predictable from outside.
        self._rng = rng or random.SystemRandom()

        self.step = Step.CHECKS
        self._checks_pick = TWIN_RULES_CHALLENGE
        self.evidence = ModuleEvidence(case_id=case_id, source=trace.source)
        self.retries = 0
        self.late_replies = 0  # replies that came after the deadline and were not copies
        self._late = False  # the reply being weighed now is one of those
        self._replied = False  # a real reply was checked at least once (A14)
        self.verdict: Verdict | None = None
        # Taken by `add_evidence`. The API swaps in the case's own lock, so evidence added from a
        # background thread cannot race the policy.
        self.evidence_lock: Any = threading.RLock()
        self.pending_challenge: ChallengeDraft | None = None

        self._candidates: list[FloorPlanCandidate] = []
        self._model_id: str | None = None
        self._spot: SpotCandidate | None = None
        self._used_spots: set[str] = set()
        self._decision: tuple[str, str | None] | None = None
        self._said_waiting = False
        self._skipped_spot: str | None = None
        self._plan: Plan | None = None
        self._after_plan: Step | None = None  # where the case goes when the plan is done
        self.question: str | None = None  # the code-written question the renter is asked
        # Working notes per check family (casework.py): derived text only, never read by decide().
        self.notes: dict[str, Note] = {}
        # Set by the API: researched places near the ad, as text. `search_places()` uses the code
        # policy (code notes); `search_places(use_model=True)` is the search sub-agent's call.
        self.search_places: Callable[..., str] | None = None
        # E1: a retry search for unplaced photos. None (the default) means no retry: the base
        # search stands. `place_scans` maps a scan alias (S1) to its model id, searcher-side only.
        self.place_searcher: PlaceSearcher | None = None
        self.place_scans: Mapping[str, str] | None = None
        self.place_covers_unshown: Mapping[str, bool] | None = None
        self.place_case_seconds_left: float | None = None  # what is left of the case's 25 s
        self.place_desk: PlaceDesk | None = None
        # E5: the walk. `walk_plan()` returns the case's TourPlan (set by whoever builds the
        # tour); `walk_desk` and `walk_director` are filled by the walk sub-agent or the policy.
        self.walk_plan: Callable[[], Any] | None = None
        self.walk_desk: Any = None
        self.walk_director: Any = None

    # --- reading the state -----------------------------------------------------------------

    @property
    def done(self) -> bool:
        return self.step is Step.DONE

    @property
    def waiting_for_approval(self) -> bool:
        return self.step is Step.APPROVAL and self._decision is None

    @property
    def waiting_for_reply(self) -> bool:
        """The challenge was sent and the poster's reply photo has not been checked yet."""
        return self.step is Step.REPLY

    @property
    def waiting_for_answer(self) -> bool:
        """The renter was asked for the license number and has not answered yet."""
        return self.step is Step.ASK

    @property
    def recorded_decision(self) -> str | None:
        """The renter's answer, once given and before `send_challenge` has acted on it."""
        return self._decision[0] if self._decision else None

    def _say(self, key: str, **values: object) -> str:
        return strings.text(key, self.lang, **values)

    def offer(self) -> Offer | None:
        """The choice that is open now, or None when the next step is not a choice to make."""
        if self.step is Step.CHECKS:
            return self._checks_offer()
        if self.step is Step.PLACE:
            return self._place_offer()
        if self.step is Step.PLAN:
            return self._plan_offer()
        if self.step is Step.FLOOR_PLAN:
            return self._floor_plan_offer()
        if self.step is Step.RETRY:
            return self._retry_offer()
        return None

    # --- choice 1: which checks ------------------------------------------------------------

    def _checks_offer(self) -> Offer:
        has_twin = self.modules.has_twin(self.case_id)
        if has_twin:
            options: tuple[str, ...] = (TWIN_RULES_CHALLENGE, RULES_CHALLENGE)
            default, reason = TWIN_RULES_CHALLENGE, self._say("trace.checks.twin")
        else:
            options = (RULES_ONLY,)
            default, reason = RULES_ONLY, self._say("trace.checks.no_twin")

        # "state only" runs nothing, so it is on the list only for a kind of listing this check
        # does not cover. On an ordinary rental it would be a way to skip a payment warning or
        # to turn a forged reply into "could not check". Every other option reads the text.
        scope = self.modules.listing_scope(self.case_id)
        out_of_scope = scope is not ListingScope.RENTAL
        if out_of_scope:
            options = (*options, STATE_ONLY)
            default, reason = STATE_ONLY, self._say(f"trace.checks.{scope.value}")

        return Offer(
            kind=ChoiceKind.WHICH_CHECKS,
            options=options,
            aliases=options,
            facts={
                "building_has_a_3d_twin": has_twin,
                "listing_photos": self.modules.photo_count(self.case_id),
                "short_term_or_commercial_listing": out_of_scope,
            },
            default=default,
            default_reason=reason,
        )

    def _apply_checks(self, pick: str) -> None:
        self._checks_pick = pick
        if pick == STATE_ONLY:
            self._finish()
            return

        update: dict[str, object] = {
            "rules": self.modules.rules(self.case_id),
            "record_source": self.modules.record_source(self.case_id),
            "property_type": self.modules.property_type(self.case_id),
        }
        if pick == TWIN_RULES_CHALLENGE:
            self.trace.emit(
                TraceKind.TOOL,
                self._say("trace.tool.locate", count=self.modules.photo_count(self.case_id)),
                pick="locate",
            )
            located = self.modules.locate(self.case_id)
            update["locate"] = located
            office_of = getattr(self.modules, "matched_office", None)
            if office_of is not None and located is not None:
                update["matched_office"] = office_of(self.case_id, located)
            if located is not None:
                self._candidates = [c for c in (located.chosen, *located.alternatives) if c]
                placed = [p for p in located.photos if p.status is LocateStatus.LOCATED_IN_CLAIMED]
                self._model_id = placed[0].model_id if placed else None
        elif pick == RULES_CHALLENGE:
            self._candidates = self.modules.floor_plans(self.case_id)
        else:
            # No twin to place photos in. If photos were sent, keep that they could not be
            # checked, so the card does not say none were sent.
            unplaced = self.modules.locate(self.case_id)
            photos = unplaced.photos if unplaced is not None else []
            if photos and all(photo.status is LocateStatus.NOT_INDEXED for photo in photos):
                update["locate"] = unplaced
        self.evidence = self.evidence.model_copy(update=update)
        if self._begin_place():
            return  # the retry budget is a choice of its own; `_end_place` carries on
        self._after_locate(pick)

    def _after_locate(self, pick: str) -> None:
        if pick == RULES_ONLY:
            self._after_plan = None
        elif self._candidates:
            self._after_plan = Step.FLOOR_PLAN
        elif self._model_id:
            self._after_plan = Step.SPOT  # photos were placed but no floor plans were ranked
        else:
            self._after_plan = None  # nothing to challenge against
        self._begin_plan()

    # --- choice 1a: the short retry budget for unplaced photos (E1) -------------------------

    def _begin_place(self) -> bool:
        located = self.evidence.locate
        if self.place_searcher is None or located is None:
            return False
        desk = PlaceDesk(
            located,
            self.place_searcher,
            scans=self.place_scans,
            covers_unshown=self.place_covers_unshown,
            case_seconds_left=self.place_case_seconds_left,
            points=self._live_points(),
        )
        for alias, bar in desk.unsure_lines():
            self.trace.emit(
                TraceKind.UNSURE,
                self._say(
                    f"trace.unsure.{bar}",
                    photo=alias,
                    n=desk.rows[desk.photo_of[alias]].location.inliers or 0,
                    bar=desk.bar_of(alias),
                ),
                pick=alias,
            )
        if not desk.is_open():
            self.place_desk = desk if desk.unplaced() else None
            return False
        self.place_desk = desk
        self.step = Step.PLACE
        return True

    def _place_offer(self) -> Offer | None:
        assert self.place_desk is not None
        offer = self.place_desk.offer()
        if offer is None:
            self._end_place()
            return self.offer()
        return Offer(
            kind=ChoiceKind(offer.kind),
            options=offer.options,
            aliases=offer.aliases,
            facts=offer.for_chooser().facts,  # only what a model may see
            default=offer.default,
            default_reason=offer.default_reason,
        )

    def _apply_place(self, kind: ChoiceKind, label: str, by: Literal["model", "policy"]) -> None:
        assert self.place_desk is not None
        desk = self.place_desk
        before = {pid: len(row.steps) for pid, row in desk.rows.items()}
        desk.apply(kind.value, label, by)
        for pid, row in desk.rows.items():
            for step in row.steps[before[pid] :]:
                if step.option not in ("stop",):
                    self.trace.emit(
                        TraceKind.TOOL,
                        self._say(
                            "trace.place.searched",
                            photo=desk.alias_of[pid],
                            option=self._say(f"place.option.{step.option.split(':')[0]}"),
                            seconds=step.seconds or 0,
                            result=self._say(f"place.result.{step.result}"),
                        ),
                        pick=f"search: {step.option}",
                        chosen_by=by,
                    )
        if not desk.is_open():
            self._end_place()

    def _live_points(self) -> dict:
        """The base search's matched pairs, when the modules have them (live cases only)."""
        reader = getattr(self.modules, "live_points", None)
        return dict(reader(self.case_id)) if reader is not None else {}

    def evidence_file(self) -> EvidenceFile | None:
        """The evidence file for the "How we know" drawer, with each photo's matched pairs, or
        None before any photo was placed or checked. Built by code from the evidence; the pairs
        go here and nowhere else (not the chooser, the trace or a log)."""
        located = self.evidence.locate
        if located is None or not located.photos:
            return None
        if self.place_desk is not None:
            return self.place_desk.evidence_file(self.case_id, self.trace.source)
        return write_evidence_file(
            self.case_id, self.trace.source, located, points=self._live_points()
        )

    def _end_place(self) -> None:
        """The budget is spent or nothing is left to try: keep what the retries found."""
        assert self.place_desk is not None
        located = self.place_desk.located()
        update: dict[str, object] = {"locate": located}
        self._candidates = [c for c in (located.chosen, *located.alternatives) if c]
        placed = [p for p in located.photos if p.status is LocateStatus.LOCATED_IN_CLAIMED]
        self._model_id = placed[0].model_id if placed else None
        self.evidence = self.evidence.model_copy(update=update)
        self._after_locate(self._checks_pick)

    # --- choice 1b: which check next (A24) -------------------------------------------------

    def _begin_plan(self) -> None:
        self._plan = Plan(self.modules, self.case_id, ask_enabled=self.ask_enabled)
        self.evidence = self.evidence.model_copy(update=self._plan.unclaimed_evidence())
        for skipped in self._plan.skipped():
            self.trace.emit(
                TraceKind.STATUS,
                self._say(
                    "plan.skipped", option=skipped.kind.value, reason=self._say(skipped.reason)
                ),
                pick=skipped.kind.value,
            )
        self.step = Step.PLAN
        self._advance_plan()

    def _advance_plan(self) -> None:
        """Leave the plan when no option can run any more."""
        assert self._plan is not None
        if self._plan.open_options():
            return
        if self._after_plan is None:
            self._finish()
        else:
            self.step = self._after_plan

    def _plan_offer(self) -> Offer:
        assert self._plan is not None
        kinds = self._plan.open_options()
        labels = tuple(kind.value for kind in kinds)
        return Offer(
            kind=ChoiceKind.NEXT_CHECK,
            options=labels,
            aliases=labels,
            facts=self._plan.facts(),
            default=labels[0],
            default_reason=self._say(self._plan.pick_key(kinds[0])),
        )

    def _apply_plan(self, pick: str) -> None:
        assert self._plan is not None
        if PlanKind(pick) is PlanKind.ASK:
            # The question is a code string. The case now waits for the renter, like REPLY.
            self.question = self._say("plan.ask.question")
            self.trace.emit(TraceKind.STATUS, self.question)
            self.step = Step.ASK
            return
        update = self._plan.run(PlanKind(pick))
        self.evidence = self.evidence.model_copy(update=update)
        self._advance_plan()

    def answer(self, text: str | None) -> None:
        """Take the renter's answer to the license question (blank or no number: no change).

        Only the checks `UNLOCKS` names for the field re-run. The raw text is read for a
        number by code and goes nowhere else: not to a model, not to the trace.
        """
        if self.step is not Step.ASK or self._plan is None:
            raise RuntimeError("no question is waiting for an answer")
        update = self._plan.answer(ASK_FIELDS[0], text)
        self.question = None
        if self._plan.looked_up:
            self.trace.emit(TraceKind.TOOL, self._say("plan.ask.looked_up"), pick="license")
        elif self._plan.number_given:
            # a number came but no lookup answered (none is wired, it broke, or it timed out)
            self.trace.emit(TraceKind.STATUS, self._say("plan.ask.not_looked_up"))
        else:
            self.trace.emit(TraceKind.STATUS, self._say("plan.ask.no_number"))
        self.evidence = self.evidence.model_copy(update=update)
        self.step = Step.PLAN
        self._advance_plan()

    # --- choice 2: which floor plan --------------------------------------------------------

    def _floor_plan_labels(self) -> tuple[str, ...]:
        labels: list[str] = []
        for number, candidate in enumerate(self._candidates, start=1):
            label = candidate.floor_plan or f"floor plan {number}"
            if label in labels:
                label = f"{label} ({number})"
            labels.append(label)
        return tuple(labels)

    def _floor_plan_offer(self) -> Offer:
        labels = self._floor_plan_labels()
        aliases = tuple(f"Plan {chr(ord('A') + index)}" for index in range(len(labels)))
        facts: dict[str, bool | int | str] = {}
        for alias, candidate in zip(aliases, self._candidates, strict=True):
            facts[f"{alias} inliers"] = candidate.total_inliers
            facts[f"{alias} photos placed"] = candidate.photos_located

        ranked = sorted(
            range(len(labels)), key=lambda i: self._candidates[i].total_inliers, reverse=True
        )
        best = ranked[0]
        if len(labels) == 1:
            reason = self._say("trace.floor_plan.only")
        elif self._candidates[best].total_inliers == 0:
            reason = self._say("trace.floor_plan.unranked")
        else:
            reason = self._say(
                "trace.floor_plan.best",
                alias=aliases[best],
                best=self._candidates[best].total_inliers,
                next=self._candidates[ranked[1]].total_inliers,
            )
        return Offer(
            kind=ChoiceKind.WHICH_FLOOR_PLAN,
            options=labels,
            aliases=aliases,
            facts=facts,
            default=labels[best],
            default_reason=reason,
        )

    def _apply_floor_plan(self, pick: str) -> None:
        index = self._floor_plan_labels().index(pick)
        chosen = self._candidates[index]
        self._model_id = chosen.model_id
        if self.evidence.locate is not None:
            others = [c for i, c in enumerate(self._candidates) if i != index]
            located = self.evidence.locate.model_copy(
                update={"chosen": chosen, "alternatives": others}
            )
            self.evidence = self.evidence.model_copy(update={"locate": located})
        self.step = Step.SPOT

    # --- choice 3: which spot (a random draw, never a pick) --------------------------------

    def _spots(self) -> tuple[list[SpotCandidate], int]:
        """Spots still open to a draw (best first, at most TOP_SPOTS), and how many overlap."""
        ranking = self.modules.spot_ranking(self.case_id, self._model_id)
        if ranking is None:
            return [], 0
        drawable = [
            spot
            for spot in ranking.spots
            if not spot.overlaps_listing_photo and spot.spot_id not in self._used_spots
        ]
        skipped = [spot for spot in ranking.spots if spot.overlaps_listing_photo]
        self._skipped_spot = skipped[0].spot_id if len(skipped) == 1 else None
        return drawable[:TOP_SPOTS], len(skipped)

    def draw_spot(self) -> None:
        if self.step is not Step.SPOT:
            raise RuntimeError("no spot is due to be drawn now")
        drawable, skipped = self._spots()
        if not drawable:
            self._finish()
            return

        spot = self._rng.choice(drawable)
        if skipped == 1:
            reason = self._say(
                "trace.spot.draw_skipped_one", count=len(drawable), skipped=self._skipped_spot
            )
        elif skipped:
            reason = self._say("trace.spot.draw_skipped_many", count=len(drawable), skipped=skipped)
        else:
            reason = self._say("trace.spot.draw", count=len(drawable))
        self.trace.emit(
            TraceKind.CHOICE,
            reason,
            choice=ChoiceKind.WHICH_SPOT,
            options=[candidate.spot_id for candidate in drawable],
            pick=spot.spot_id,
        )

        self._spot = spot
        self._used_spots.add(spot.spot_id)
        code = self.modules.new_code(self.case_id)
        self.pending_challenge = ChallengeDraft(
            spot_id=spot.spot_id,
            spot_label=spot.label,
            code=code,
            text=self._say("challenge.text", spot=spot.label, code=code),
        )
        self._decision = None
        self._said_waiting = False
        self.step = Step.APPROVAL

    # --- choice 4: ask the renter (only a person answers this one) -------------------------

    def note_waiting(self) -> None:
        """Say once, in the trace, that the case is paused for the renter."""
        if self.waiting_for_approval and not self._said_waiting:
            self.trace.emit(TraceKind.STATUS, self._say("trace.hitl.waiting"))
            self._said_waiting = True

    def approve(self, decision: str, text: str | None = None) -> None:
        """Record the renter's answer. `send_challenge` acts on it."""
        if self.step is not Step.APPROVAL or self.pending_challenge is None:
            raise RuntimeError("nothing is waiting for approval")
        if decision not in DECISIONS:
            raise ValueError("decision must be send, edit or cancel")
        self._decision = (decision, text)

    def send_challenge(self) -> None:
        """Act on the recorded approval: send the challenge, or drop it on cancel."""
        if self.step is not Step.APPROVAL or self._decision is None:
            raise RuntimeError("the renter has not approved anything yet")
        decision, text = self._decision
        self._decision = None
        self.trace.emit(
            TraceKind.HITL,
            self._say(f"trace.hitl.{decision}"),
            choice=ChoiceKind.ASK_HUMAN,
            options=DECISIONS,
            pick=decision,
        )

        draft = self.pending_challenge
        self.pending_challenge = None
        if decision == CANCEL or draft is None or self._spot is None:
            self._finish()
            return
        if decision == EDIT and text:
            draft = replace(draft, text=text)

        # The text handed over is the one the renter approved: the draft, or their edit of it.
        outcome = self.modules.challenge(
            self.case_id, self._spot, draft.code, draft.text, self.retries
        )
        self._take(outcome)
        if outcome.awaiting_reply:
            # Nothing to judge yet. The case waits here: no reply is HOLD, never a failure.
            self.trace.emit(TraceKind.STATUS, self._say("trace.reply.waiting"))
            self.step = Step.REPLY
        else:
            self.step = Step.RETRY

    def _take(self, outcome: ChallengeOutcome) -> None:
        self.evidence = self.evidence.model_copy(
            update={
                "challenge": outcome.challenge,
                "recapture": outcome.recapture,
                "memory": outcome.memory,
            }
        )

    def reply(self, outcome: ChallengeOutcome) -> None:
        """Take the poster's reply, already checked. The retry-or-stop choice comes next.

        A reply that came too late to count and is not a copy (`outcome.late`) is not judged;
        the choice that follows asks again once (decision 4, Sat 02:45). A copy is proof
        whenever it arrives. Only an outcome that is still `awaiting_reply` leaves the case
        waiting, and no check returns one today.
        """
        if self.step is not Step.REPLY:
            raise RuntimeError("no reply is awaited now")
        self._take(outcome)
        if outcome.awaiting_reply:
            return
        self._replied = True
        self._late = outcome.late
        if outcome.late:
            # Too late to count and not a copy (a copy is proof whenever it comes). Nothing
            # on it was judged; whether to ask again is the next choice.
            self.late_replies += 1
            self.trace.emit(TraceKind.STATUS, self._say("trace.reply.late"))
        else:
            self.trace.emit(TraceKind.TOOL, self._say("trace.tool.reply"), pick="reply")
        self.step = Step.RETRY

    # --- choice 5: retry or stop -----------------------------------------------------------

    def _retry_offer(self) -> Offer:
        presence = presence_of(self.evidence)
        challenge = self.evidence.challenge
        spots = challenge.spots if challenge else []
        matched = sum(bool(spot.located and spot.code_read) for spot in spots)
        forged = presence.status is PresenceStatus.FORGED
        proven = presence.status is PresenceStatus.PROVEN

        # Decision 4 (Sat 02:45): a reply that came too late and is not a copy is asked for
        # again once. A second late one is not: the case holds, and nobody is accused.
        late = self._late and not forged
        late_asks_used_up = late and self.late_replies > MAX_LATE_ASKS

        # Proof of a forgery is never retried away, and the cap is enforced here, not asked for.
        can_retry = (
            not forged
            and not late_asks_used_up
            and self.retries < MAX_RETRIES
            and bool(self._spots()[0])
        )
        options = (ACCEPT, RETRY, STOP) if can_retry else (ACCEPT, STOP)

        # A14: the reply showed the code, and nothing has checked that it was taken at the
        # spot (that needs locate). Asking again cannot change that, so the case stops here,
        # not confirmed.
        last = spots[-1] if spots else None
        code_only = (
            not forged
            and not proven
            and last is not None
            and last.replied_at is not None
            and last.code_read is True
            and last.located is None
        )

        if forged:
            default, reason = ACCEPT, self._say("trace.retry.forged")
        elif code_only:
            default, reason = STOP, self._say("trace.retry.code_only")
        elif proven and matched == len(spots) == 2:
            default, reason = ACCEPT, self._say("trace.retry.accept_both")
        elif proven:
            default = ACCEPT
            reason = self._say("trace.retry.accept", matched=matched, total=len(spots))
        elif late and can_retry:
            default, reason = RETRY, self._say("trace.retry.late")
        elif can_retry:
            default, reason = RETRY, self._say("trace.retry.again")
        else:
            default, reason = STOP, self._say("trace.retry.stop")

        return Offer(
            kind=ChoiceKind.RETRY_OR_STOP,
            options=options,
            aliases=options,
            facts={
                "spots_matched": matched,
                "spots_asked": len(spots),
                "code_read_on_every_reply": bool(spots) and all(s.code_read for s in spots),
                "recapture_flag": any(result.blocks_pass for result in self.evidence.recapture),
                "reply_copies_a_listing_photo": presence.copies_listing_photo,
                "reply_came_too_late_to_count": late,
                "retries_used": self.retries,
                "retries_left": MAX_RETRIES - self.retries,
            },
            default=default,
            default_reason=reason,
        )

    def _apply_retry(self, pick: str) -> None:
        if pick == RETRY:
            self.retries += 1
            self._late = False
            self.step = Step.SPOT
        else:
            self._finish()

    # --- making a choice -------------------------------------------------------------------

    def choose(
        self,
        pick: object,
        reason: object = None,
        *,
        by: Literal["model", "policy"] = "policy",
    ) -> str:
        """Take a pick for the open choice. Returns the label that was applied.

        A pick that is not on the list is not an error to raise: the default is applied and the
        trace says so. Whatever is passed as the reason is reduced to one plain line.
        """
        offer = self.offer()
        if offer is None:
            raise RuntimeError(f"no choice is open at step {self.step.value!r}")

        label = offer.resolve(pick)
        if len(offer.options) == 1:
            # Nothing was chosen: a menu of one. Say so, and never credit a model for it.
            label, reason, by = offer.options[0], self._say("plan.only_option"), "policy"
        elif label is None:
            self.trace.emit(TraceKind.ERROR, self._say("trace.error.bad_pick"))
            label, reason, by = offer.default, offer.default_reason, "policy"
        self.trace.emit(
            TraceKind.CHOICE,
            clean_reason(reason, offer.default_reason),
            choice=offer.kind,
            options=offer.options,
            pick=label,
            chosen_by=by,
        )

        if offer.kind in (ChoiceKind.NEXT_SEARCH, ChoiceKind.WHICH_PHOTO):
            self._apply_place(offer.kind, label, by)
        elif offer.kind is ChoiceKind.WHICH_CHECKS:
            self._apply_checks(label)
        elif offer.kind is ChoiceKind.NEXT_CHECK:
            self._apply_plan(label)
        elif offer.kind is ChoiceKind.WHICH_FLOOR_PLAN:
            self._apply_floor_plan(label)
        else:
            self._apply_retry(label)
        return label

    def settle(self) -> None:
        """Apply every open choice that has a single option. No chooser is asked about these."""
        while (offer := self.offer()) is not None and len(offer.options) == 1:
            self.choose(offer.default, offer.default_reason)

    def choose_default(self, *, failed: bool = False) -> str:
        """Apply the code policy's pick, noting in the trace if a model failed to answer."""
        offer = self.offer()
        if offer is None:
            raise RuntimeError(f"no choice is open at step {self.step.value!r}")
        if failed:
            self.trace.emit(TraceKind.ERROR, self._say("trace.error.model_failed"))
        return self.choose(offer.default, offer.default_reason)

    # --- the end ---------------------------------------------------------------------------

    def confirm_office(self, domain: str) -> None:
        """Record that someone at the office's own website domain on record confirmed this case.

        A "not ours" is sticky: a confirmation never clears it (a poster could say "email jane@
        instead"), so the case stays on HOLD with both lines on the card. A finished case is
        decided again on the evidence it now has, by `decide` and nowhere else, and the trace
        gets a new verdict event so it matches the card. A case still running carries the
        answer into its eventual decision."""
        self._office_answer({"office_confirmed_domain": domain})

    def decline_office(self, domain: str) -> None:
        """The office at the domain on record said the ad is not theirs (holds the case).

        It may clear an earlier confirmation; nothing clears it."""
        self._office_answer({"office_confirmed_domain": None, "office_declined_domain": domain})

    def _office_answer(self, update: dict[str, str | None]) -> None:
        self.evidence = self.evidence.model_copy(update=update)
        if self.verdict is not None:
            self.verdict = decide(to_evidence(self.evidence, self.lang), self.lang)
            self._emit_verdict()

    def add_evidence(self, update: Mapping[str, Any]) -> bool:
        """More evidence from outside the choice flow, e.g. an extra check the deep agent ran
        after the case was answered. Returns True when the state changed.

        The state is decided again by `decide` and nowhere else. When it moves, the trace gets
        an "updated after more checks" step with the first reason, then a new verdict event, so
        the trace matches the card. A case still running carries the evidence into its eventual
        decision. Nothing here lets a model pick a state: it can only supply evidence fields,
        and the fields are validated as `ModuleEvidence` fields."""
        with self.evidence_lock:
            self.evidence = ModuleEvidence.model_validate(
                {**dict(self.evidence), **{k: v for k, v in update.items()}}
            )
            if self.verdict is None:
                return False
            before = self.verdict.state
            self.verdict = decide(to_evidence(self.evidence, self.lang), self.lang)
            if self.verdict.state is before:
                return False
            reason = self.verdict.reasons[0] if self.verdict.reasons else ""
            self.trace.emit(
                TraceKind.STATUS,
                clean_reason(
                    self._say(
                        "trace.updated",
                        old=self._say(f"state.{before.value}"),
                        new=self._say(f"state.{self.verdict.state.value}"),
                        reason=reason,
                    ),
                    self._say("trace.updated.short"),
                ),
                pick=UPDATED,
            )
            self._emit_verdict()
            return True

    def _finish(self) -> None:
        """Decide on the evidence gathered. This is the only way a case gets a state."""
        if self._replied and presence_of(self.evidence).status is PresenceStatus.WAITING:
            # A reply came, it could not be accepted, and nothing more will be asked. The
            # card must stop telling the renter to ask for a photo. This changes no state.
            self.evidence = self.evidence.model_copy(update={"no_retry_left": True})
        self.verdict = decide(to_evidence(self.evidence, self.lang), self.lang)
        self._emit_verdict()
        self.step = Step.DONE

    def _emit_verdict(self) -> None:
        assert self.verdict is not None
        reasons: list[str] = []
        for reason in self.verdict.reasons:
            if reasons and len(" ".join([*reasons, reason])) > 200:
                break
            reasons.append(reason)
        self.trace.emit(
            TraceKind.VERDICT,
            clean_reason(" ".join(reasons), self.verdict.state.value),
            pick=self.verdict.state.value,
        )
