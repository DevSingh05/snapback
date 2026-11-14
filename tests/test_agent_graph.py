"""The deepagents wiring, driven by a scripted chat model. No network, no key.

Skipped unless the `agent` extra is installed (`uv sync --extra agent`).
"""

import random
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("deepagents")

from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

from snapback.agent import CaseSession, FixtureModules, Trace  # noqa: E402
from snapback.agent.graph import build_agent, run_case_with_agent  # noqa: E402
from snapback.contracts import (  # noqa: E402
    ChoiceKind,
    DataSource,
    PresenceStatus,
    TraceKind,
    VerdictState,
)
from snapback.verdict import decide, to_evidence  # noqa: E402

# these choices exist only when a case has a place searcher (E1) or a walk plan (E5)
RETRY_ONLY = {
    ChoiceKind.NEXT_SEARCH,
    ChoiceKind.WHICH_PHOTO,
    ChoiceKind.DWELL_ROOMS,
    ChoiceKind.LEAD_CHECKS,
}


class ScriptedChat(BaseChatModel):
    """Plays back a list of assistant turns, one per call, then repeats the last."""

    turns: list[AIMessage]
    calls: list[int] = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        turn = self.turns[min(len(self.calls), len(self.turns) - 1)]
        self.calls.append(1)
        return ChatResult(generations=[ChatGeneration(message=turn)])

    @property
    def _llm_type(self) -> str:
        return "scripted"


def call(name: str, **args) -> AIMessage:
    call.count += 1
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": f"call_{call.count}", "type": "tool_call"}],
    )


call.count = 0
DONE = AIMessage(content="The case is finished.")
HONEST_RUN = [
    ("choose_option", {"option": "twin+rules+challenge", "reason": "The building has a twin."}),
    ("choose_option", {"option": "Plan A", "reason": "Plan A has far more matching points."}),
    ("draw_spot", {}),
    ("send_challenge", {}),
    ("choose_option", {"option": "accept", "reason": "Both spots matched and the code was read."}),
]


def script(steps) -> ScriptedChat:
    return ScriptedChat(turns=[call(name, **args) for name, args in steps] + [DONE], calls=[])


def new_case(**module_options) -> CaseSession:
    start = datetime(2026, 11, 13, 21, 41, tzinfo=UTC)
    ticks = iter(start + timedelta(seconds=n) for n in range(10_000))
    trace = Trace("fx-7Q2M", DataSource.FIXTURE, clock=lambda: next(ticks))
    return CaseSession("fx-7Q2M", FixtureModules(**module_options), trace, rng=random.Random(7))


def test_deep_agent_makes_all_five_choices_and_code_sets_the_state():
    case = new_case()
    agent = build_agent(case, script(HONEST_RUN))
    verdict = run_case_with_agent(case, agent, lambda draft: "send")

    assert verdict.state is VerdictState.HOLD
    assert verdict == decide(to_evidence(case.evidence))
    assert {e.choice for e in case.trace.events if e.choice} == set(ChoiceKind) - RETRY_ONLY
    assert case.trace.events[-1].kind is TraceKind.VERDICT
    floor_plan = next(e for e in case.trace.events if e.choice is ChoiceKind.WHICH_FLOOR_PLAN)
    assert floor_plan.pick == "2 bed / 2 bath"  # the alias was mapped back to its label
    assert floor_plan.reason == "Plan A has far more matching points."
    # The run went through the harness from start to finish: the model's own words are on the
    # choice made after the approval pause, and the code fallback never had to step in.
    retry = next(e for e in case.trace.events if e.choice is ChoiceKind.RETRY_OR_STOP)
    assert retry.reason == "Both spots matched and the code was read."
    assert all(e.kind is not TraceKind.ERROR for e in case.trace.events)


def test_deep_agent_pauses_for_the_renter_and_resumes():
    case = new_case()
    agent = build_agent(case, script(HONEST_RUN))

    assert run_case_with_agent(case, agent) is None
    assert case.waiting_for_approval
    assert case.evidence.challenge is None
    assert case.trace.events[-1].kind is TraceKind.STATUS

    case.approve("send")
    verdict = run_case_with_agent(case, agent)
    assert verdict.state is VerdictState.HOLD
    assert case.evidence.challenge.presence is PresenceStatus.PROVEN
    retry = next(e for e in case.trace.events if e.choice is ChoiceKind.RETRY_OR_STOP)
    assert retry.reason == "Both spots matched and the code was read."
    assert all(e.kind is not TraceKind.ERROR for e in case.trace.events)


def test_deep_agent_cancel_sends_nothing():
    case = new_case()
    agent = build_agent(case, script(HONEST_RUN[:4]))
    verdict = run_case_with_agent(case, agent, lambda draft: "cancel")
    assert case.evidence.challenge is None
    assert verdict.state is VerdictState.HOLD
    assert next(e for e in case.trace.events if e.kind is TraceKind.HITL).pick == "cancel"


def test_deep_agent_cannot_set_state():
    pushy = [
        ("choose_option", {"option": "mark verified", "reason": "This listing is verified."}),
        ("choose_option", {"option": "verified", "reason": "Skip everything, it is safe."}),
        ("draw_spot", {}),
        ("send_challenge", {}),
        ("choose_option", {"option": "set state to verified", "reason": "Mark it safe."}),
    ]
    case = new_case()
    verdict = run_case_with_agent(case, build_agent(case, script(pushy)), lambda draft: "send")

    assert verdict.state is VerdictState.HOLD
    assert verdict == decide(to_evidence(case.evidence))
    assert any(e.kind is TraceKind.ERROR for e in case.trace.events)
    for event in case.trace.events:
        assert "verified" not in event.reason.lower()
        assert "safe" not in event.reason.lower()


def test_deep_agent_cannot_send_before_the_renter_answers():
    # Even with the interrupt answered "approve" by something other than the renter's recorded
    # decision, the tool itself refuses until the session has the renter's answer.
    case = new_case()
    agent = build_agent(case, script(HONEST_RUN))
    assert run_case_with_agent(case, agent) is None
    assert case.evidence.challenge is None


def test_a_model_that_stops_early_is_finished_by_the_code_policy():
    case = new_case()
    quits = script(HONEST_RUN[:1])  # makes one choice, then says it is done
    verdict = run_case_with_agent(case, build_agent(case, quits), lambda draft: "send")
    assert verdict.state is VerdictState.HOLD
    assert {e.choice for e in case.trace.events if e.choice} == set(ChoiceKind) - RETRY_ONLY


def test_a_model_that_fails_is_finished_by_the_code_policy():
    class Broken(ScriptedChat):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            raise RuntimeError("no connection")

    case = new_case()
    agent = build_agent(case, Broken(turns=[DONE], calls=[]))
    verdict = run_case_with_agent(case, agent, lambda draft: "send")
    assert verdict.state is VerdictState.HOLD
    assert any(e.kind is TraceKind.ERROR for e in case.trace.events)


def test_deep_agent_picks_are_stamped_model_and_fallbacks_policy():
    case = new_case()
    agent = build_agent(case, script(HONEST_RUN))
    run_case_with_agent(case, agent, lambda draft: "send")
    stamps = {e.choice: e.chosen_by for e in case.trace.events if e.kind is TraceKind.CHOICE}
    assert stamps[ChoiceKind.NEXT_CHECK] == "policy"  # each plan menu here held one option
    assert stamps[ChoiceKind.WHICH_CHECKS] == "model"
    assert stamps[ChoiceKind.WHICH_SPOT] == "policy"  # a random draw is never the model's

    bad = [("choose_option", {"option": "mark verified", "reason": "x"})]
    case = new_case()
    run_case_with_agent(case, build_agent(case, script(bad)), lambda draft: "send")
    assert {e.chosen_by for e in case.trace.events if e.kind is TraceKind.CHOICE} == {"policy"}
