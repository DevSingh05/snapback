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
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum

from snapback.agent.modules import ChallengeOutcome, Modules
from snapback.agent.scope import ListingScope
from snapback.agent.trace import Trace, clean_reason
from snapback.card import strings
from snapback.contracts import (
    ChoiceKind,
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
DECISIONS = (SEND, EDIT, CANCEL)


class Step(StrEnum):
    CHECKS = "checks"
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
    ) -> None:
        self.case_id = case_id
        self.modules = modules
        self.trace = trace
        self.lang = lang
        # SystemRandom by default: the draw must not be predictable from outside.
        self._rng = rng or random.SystemRandom()

        self.step = Step.CHECKS
        self.evidence = ModuleEvidence(case_id=case_id, source=trace.source)
        self.retries = 0
        self.verdict: Verdict | None = None
        self.pending_challenge: ChallengeDraft | None = None

        self._candidates: list[FloorPlanCandidate] = []
        self._model_id: str | None = None
        self._spot: SpotCandidate | None = None
        self._used_spots: set[str] = set()
        self._decision: tuple[str, str | None] | None = None
        self._said_waiting = False
        self._skipped_spot: str | None = None

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
    def recorded_decision(self) -> str | None:
        """The renter's answer, once given and before `send_challenge` has acted on it."""
        return self._decision[0] if self._decision else None

    def _say(self, key: str, **values: object) -> str:
        return strings.text(key, self.lang, **values)

    def offer(self) -> Offer | None:
        """The choice that is open now, or None when the next step is not a choice to make."""
        if self.step is Step.CHECKS:
            return self._checks_offer()
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
        if pick == STATE_ONLY:
            self._finish()
            return

        update: dict[str, object] = {
            "rules": self.modules.rules(self.case_id),
            "price": self.modules.price(self.case_id),
            "authority": self.modules.authority(self.case_id),
            "for_sale": self.modules.for_sale(self.case_id),
        }
        if pick == TWIN_RULES_CHALLENGE:
            self.trace.emit(
                TraceKind.TOOL,
                self._say("trace.tool.locate", count=self.modules.photo_count(self.case_id)),
                pick="locate",
            )
            located = self.modules.locate(self.case_id)
            update["locate"] = located
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

        if pick == RULES_ONLY:
            self._finish()
        elif self._candidates:
            self.step = Step.FLOOR_PLAN
        elif self._model_id:
            self.step = Step.SPOT  # photos were placed but no floor plans were ranked
        else:
            self._finish()  # nothing to challenge against

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

        An outcome that is still `awaiting_reply` (the photo came too late to count, say)
        leaves the case waiting.
        """
        if self.step is not Step.REPLY:
            raise RuntimeError("no reply is awaited now")
        self._take(outcome)
        if not outcome.awaiting_reply:
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

        # Proof of a forgery is never retried away, and the cap is enforced here, not asked for.
        can_retry = not forged and self.retries < MAX_RETRIES and bool(self._spots()[0])
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
                "retries_used": self.retries,
                "retries_left": MAX_RETRIES - self.retries,
            },
            default=default,
            default_reason=reason,
        )

    def _apply_retry(self, pick: str) -> None:
        if pick == RETRY:
            self.retries += 1
            self.step = Step.SPOT
        else:
            self._finish()

    # --- making a choice -------------------------------------------------------------------

    def choose(self, pick: object, reason: object = None) -> str:
        """Take a pick for the open choice. Returns the label that was applied.

        A pick that is not on the list is not an error to raise: the default is applied and the
        trace says so. Whatever is passed as the reason is reduced to one plain line.
        """
        offer = self.offer()
        if offer is None:
            raise RuntimeError(f"no choice is open at step {self.step.value!r}")

        label = offer.resolve(pick)
        if label is None:
            self.trace.emit(TraceKind.ERROR, self._say("trace.error.bad_pick"))
            label, reason = offer.default, offer.default_reason
        self.trace.emit(
            TraceKind.CHOICE,
            clean_reason(reason, offer.default_reason),
            choice=offer.kind,
            options=offer.options,
            pick=label,
        )

        if offer.kind is ChoiceKind.WHICH_CHECKS:
            self._apply_checks(label)
        elif offer.kind is ChoiceKind.WHICH_FLOOR_PLAN:
            self._apply_floor_plan(label)
        else:
            self._apply_retry(label)
        return label

    def choose_default(self, *, failed: bool = False) -> str:
        """Apply the code policy's pick, noting in the trace if a model failed to answer."""
        offer = self.offer()
        if offer is None:
            raise RuntimeError(f"no choice is open at step {self.step.value!r}")
        if failed:
            self.trace.emit(TraceKind.ERROR, self._say("trace.error.model_failed"))
        return self.choose(offer.default, offer.default_reason)

    # --- the end ---------------------------------------------------------------------------

    def _finish(self) -> None:
        """Decide on the evidence gathered. This is the only way a case gets a state."""
        self.verdict = decide(to_evidence(self.evidence, self.lang), self.lang)
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
        self.step = Step.DONE
