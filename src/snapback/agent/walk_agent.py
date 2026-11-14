"""The walk sub-agent's desk: the tour director's two picks, taken through deepagents tools.

`snapback.tour.walk_offers(plan)` writes the options (D3 dwell rooms, D4 lead checks); a menu of
one is not offered. The walk sub-agent picks from what `WalkDesk.offer()` shows, and at the end
`choose_walk` is run with a chooser that replays those picks, so the director field is produced
by the same code whether a model or the policy chose. A kind the sub-agent did not pick, or an
off-list pick, gets the code policy, and every step is stamped model or policy.

`snapback.tour` is imported inside functions: this module loads without it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal

from snapback.agent.trace import clean_reason
from snapback.contracts import ChoiceKind

KINDS = {"dwell": ChoiceKind.DWELL_ROOMS, "lead": ChoiceKind.LEAD_CHECKS}


class _Replay:
    """A chooser that answers with the picks the sub-agent made, and with nothing otherwise."""

    chosen_by: Literal["model", "policy"] = "model"

    def __init__(self, picks: dict[str, tuple[str, str]]) -> None:
        self._picks = picks

    def choose(self, offer: Any) -> tuple[str, str]:
        return self._picks[offer.kind]  # KeyError: not picked, so the policy decides


class WalkDesk:
    def __init__(
        self,
        plan_fn: Callable[[], Any],
        must_have_kinds: Sequence[str] = (),
    ) -> None:
        self.plan = plan_fn()
        self.must_have_kinds = list(must_have_kinds)
        self.picks: dict[str, tuple[str, str]] = {}  # kind -> (label, reason)

    def _offers(self) -> dict[str, Any]:
        from snapback.tour import walk_offers

        return {o.kind: o for o in walk_offers(self.plan, self.must_have_kinds)}

    def offer(self) -> Any | None:
        """The next walk decision, as the chooser-safe offer. None when nothing is left."""
        offers = self._offers()
        for kind in ("dwell", "lead"):
            if kind in offers and kind not in self.picks:
                return offers[kind].for_chooser()
        return None

    def choose(self, option: str, reason: str) -> tuple[ChoiceKind, tuple[str, ...], str] | None:
        """Record a pick for the open offer. Off-list picks are refused (None): the policy will
        decide that kind at the end."""
        offer = self.offer()
        if offer is None:
            return None
        label = offer.resolve(option)
        if label is None:
            return None
        self.picks[offer.kind] = (label, clean_reason(reason, offer.default_reason))
        return KINDS[offer.kind], offer.options, label

    def director(self) -> Any:
        """The plan's director from the recorded picks, the rest by policy."""
        from snapback.tour import choose_walk

        return choose_walk(self.plan, _Replay(self.picks), self.must_have_kinds).director

    def policy_director(self) -> Any:
        from snapback.tour import policy_director

        return policy_director(self.plan, self.must_have_kinds)

    def text(self, director: Any) -> str:
        """The walk note's facts: what was picked, as stop aliases (S1..), and by whom."""
        from snapback.tour import stop_aliases

        alias = stop_aliases(self.plan)
        names = lambda keys: ", ".join(alias.get(k, "?") for k in keys) or "none"  # noqa: E731
        return "\n".join(
            [
                "Source: the walk through the home's 3D scan (stop aliases only)",
                f"Stops: {len(alias)}",
                f"Rooms to dwell on: {names(director.dwell)}",
                f"Checks that lead: {names(director.lead_checks)}",
                f"Chosen by: {director.stamp}",
            ]
        )
