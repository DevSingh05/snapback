"""The search agent: code finds the places, the model chooses what to check and what to ask.

`agentic_search` and `agentic_alternatives` run the code search, then `plan_search` puts three
choices (each among options code wrote) to a chooser: which top places get the deep check, which
one trade-off question to ask, and whether to ask it before a tour request is drafted. Whatever
the chooser says, code applies only a listed pick, builds every per-place result line itself, and
never calls the verdict: a search reports facts about places, not a verdict on an ad.

The chooser is `PolicyChooser` unless the runner setting is `deepagents` and a model can be
built; a model that is missing, down or off the list gets the code policy (see `_decide`).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from snapback.agent.planner import SearchOffer, plan_search, tradeoffs_for
from snapback.agent.runner import PolicyChooser
from snapback.agent.trace import clean_reason
from snapback.contracts import (
    AlternativesResponse,
    CasePreferences,
    PlaceMatch,
    RenterBrief,
    SearchDecision,
    SearchResponse,
)
from snapback.preferences import apply_to_brief, facts_of, keys_of
from snapback.search import (
    _all_matches,
    _source_of,
    alternatives_brief,
    alternatives_for,
    apply_deep_checks,
)

log = logging.getLogger("snapback.search_agent")

SYSTEM = (
    "You help a renter search for a home. You are shown ONE decision with its options and a few "
    "yes/no or count facts. Pick exactly one option and give one plain sentence of reason that "
    'rests on those facts. Reply with JSON only: {"option": "<option label or alias>", '
    '"reason": "<one sentence>"}. You never see a listing, an address, an id or a company name, '
    "and nothing you say changes what the records show."
)


class ModelSearchChooser:
    """A language model behind the `Chooser` protocol for search offers. It is shown the option
    labels (written by code) and allow-listed facts only; its JSON answer is parsed here and
    then checked against the list by `_decide`."""

    chosen_by: Literal["model", "policy"] = "model"

    def __init__(self, model: Any) -> None:
        self._model = model

    def choose(self, offer: SearchOffer) -> tuple[str, str]:
        shown = {
            "decision": offer.kind,
            "options": [
                {"alias": a, "label": o} for a, o in zip(offer.aliases, offer.options, strict=True)
            ],
            "facts": offer.facts,
        }
        reply = self._model.invoke([("system", SYSTEM), ("user", json.dumps(shown))])
        text = getattr(reply, "content", reply)
        if isinstance(text, list):  # content blocks
            text = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in text)
        start, end = str(text).find("{"), str(text).rfind("}")
        data = json.loads(str(text)[start : end + 1])
        return str(data["option"]), str(data.get("reason", ""))


def search_chooser_for(agent_setting: str) -> Any:
    """`PolicyChooser` by default; with `snapback_agent=deepagents`, a model chooser built from
    the same model the case graph uses. No extra, no key or any build error: the policy."""
    if agent_setting != "deepagents":
        return PolicyChooser()
    try:
        from langchain_anthropic import ChatAnthropic

        from snapback.agent.graph import DEFAULT_MODEL

        return ModelSearchChooser(ChatAnthropic(model=DEFAULT_MODEL, max_tokens=300))
    except Exception:
        log.warning("search model unavailable; the code policy chooses")
        return PolicyChooser()


def _decisions(plan: Any) -> list[SearchDecision]:
    return [
        SearchDecision(
            kind=step.kind,  # type: ignore[arg-type]
            options=list(step.options),
            pick=step.pick,
            reason=clean_reason(step.reason, "Chosen by code."),
            chosen_by=step.chosen_by,
        )
        for step in plan.steps
    ]


def agentic_search(
    brief: RenterBrief,
    lookups: Any,
    chooser: Any,
    prefs: CasePreferences | None = None,
) -> SearchResponse:
    """`POST /search`: code search with the renter's remembered preferences, then the plan."""
    effective = apply_to_brief(brief, prefs)
    avoided = set(prefs.avoid_property_ids) if prefs else set()
    considered, found = _all_matches(effective, lookups)
    found = [m for m in found if m.property_id not in avoided]
    matches = found[: effective.max_results]
    tradeoffs = _without_rejected(tradeoffs_for(effective, lookups, matches), prefs)
    plan = plan_search(matches, tradeoffs, chooser, facts_of(prefs))
    return SearchResponse(
        source=_source_of(lookups),
        n_considered=considered,
        n_matches=len(found),
        matches=apply_deep_checks(matches, plan.deep_check, lookups),
        decisions=_decisions(plan),
        question=plan.question,
        ask_first=plan.ask_first,
        remembered=keys_of(prefs),
    )


def agentic_alternatives(
    case: Any,
    lookups: Any,
    chooser: Any,
    n: int,
    prefs: CasePreferences | None,
    source: Any,
) -> AlternativesResponse:
    """`GET /cases/{id}/alternatives`: the same plan over places near the checked ad."""
    brief = apply_to_brief(RenterBrief(), prefs)
    avoided = list(prefs.avoid_property_ids) if prefs else []
    matches: list[PlaceMatch] = alternatives_for(case, brief, lookups, n, exclude=avoided)
    anchor = alternatives_brief(case, brief)
    tradeoffs = _without_rejected(tradeoffs_for(anchor, lookups, matches), prefs) if anchor else []
    plan = plan_search(matches, tradeoffs, chooser, facts_of(prefs))
    return AlternativesResponse(
        case_id=case.case_id,
        source=source,
        matches=apply_deep_checks(matches, plan.deep_check, lookups),
        decisions=_decisions(plan),
        question=plan.question,
        ask_first=plan.ask_first,
        remembered=keys_of(prefs),
    )


def _without_rejected(options: list, prefs: CasePreferences | None) -> list:
    """Never ask again what the renter already answered: a rejected walk-up, a fixed budget."""
    if prefs is None:
        return options
    gone = set()
    if prefs.no_walkup:
        gone.add("walkup")
    if prefs.max_rent is not None:
        gone.add("budget")
    return [t for t in options if t.key not in gone]
