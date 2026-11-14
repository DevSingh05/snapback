"""Drive a case to its verdict, asking a chooser for each open choice.

The chooser is whatever makes the model's three choices: a language model behind an adapter,
or `PolicyChooser`, which is the code policy and needs no key or network. The loop is the same
either way, and a chooser that fails or answers off the list never stalls or steers a case.
"""

from collections.abc import Callable
from typing import Literal, Protocol

from snapback.agent.session import CaseSession, ChallengeDraft, Offer, Step
from snapback.contracts import Verdict

Approver = Callable[[ChallengeDraft], str]


class Chooser(Protocol):
    def choose(self, offer: Offer) -> tuple[str, str]:
        """Return (pick, reason). The pick may be an option label or its alias."""
        ...


class PolicyChooser:
    """The code policy: always the default pick, with its code-written reason."""

    chosen_by: Literal["model", "policy"] = "policy"

    def choose(self, offer: Offer) -> tuple[str, str]:
        return offer.default, offer.default_reason


def run_case(
    case: CaseSession, chooser: Chooser, approver: Approver | None = None
) -> Verdict | None:
    """Run `case` until it has a verdict, or until it needs the renter and nobody can answer.

    Returns None when the case is paused for approval and `approver` is None. Record the
    answer with `case.approve(...)` and call this again to carry on. It also returns None
    while the poster's reply is awaited; give it to `case.reply(...)` and call this again.
    """
    while not case.done:
        if case.step is Step.REPLY:
            return None
        if case.step is Step.SPOT:
            case.draw_spot()
        elif case.step is Step.APPROVAL:
            if case.waiting_for_approval:
                if approver is None:
                    case.note_waiting()
                    return None
                case.approve(approver(case.pending_challenge))
            case.send_challenge()
        else:
            case.settle()
            offer = case.offer()
            if offer is None:
                continue  # settling moved the case on (or finished it)
            try:
                pick, reason = chooser.choose(offer)
            except Exception:
                # A model that is down, refuses or times out must not stall a renter's case.
                case.choose_default(failed=True)
            else:
                case.choose(pick, reason, by=getattr(chooser, "chosen_by", "policy"))
    return case.verdict
