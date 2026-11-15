"""The deep agent on the case path (SNAPBACK_AGENT=deepagents): it plans and orders the checks,
code sets the result, and on any error or on its time limit the trace says so and code finishes.

Skipped unless the `agent` extra is installed. No network, no key: a scripted chat model.
"""

import random
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("deepagents")

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

from snapback.agent import CaseSession, FixtureModules, Trace  # noqa: E402
from snapback.agent.graph import build_agent, run_case_with_agent  # noqa: E402
from snapback.agent.join import KitLookups  # noqa: E402
from snapback.agent.timeline import build_timeline  # noqa: E402
from snapback.api.main import create_app  # noqa: E402
from snapback.card import strings  # noqa: E402
from snapback.contracts import DataSource, TraceKind, VerdictState  # noqa: E402
from snapback.settings import Settings  # noqa: E402
from snapback.verdict import decide, to_evidence  # noqa: E402


class ScriptedChat(BaseChatModel):
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


_ids = iter(range(1, 1_000_000))


def call(name: str, **args) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": f"c{next(_ids)}", "type": "tool_call"}],
    )


TODOS = [
    {"content": "Work the open choices", "status": "in_progress"},
    {"content": "Write explanation.md", "status": "pending"},
]
RUN = [
    ("write_todos", {"todos": TODOS}),
    ("choose_option", {"option": "twin+rules+challenge", "reason": "The building has a twin."}),
    ("choose_option", {"option": "Plan A", "reason": "Plan A has far more matching points."}),
    ("draw_spot", {}),
    ("send_challenge", {}),
    ("choose_option", {"option": "accept", "reason": "Both spots matched and the code was read."}),
]


def scripted(steps=RUN) -> ScriptedChat:
    turns = [call(n, **a) for n, a in steps] + [AIMessage(content="Done.")]
    return ScriptedChat(turns=turns, calls=[])


def new_case() -> CaseSession:
    start = datetime(2026, 11, 14, 21, 0, tzinfo=UTC)
    ticks = iter(start + timedelta(seconds=n) for n in range(10_000))
    trace = Trace("fx-7Q2M", DataSource.FIXTURE, clock=lambda: next(ticks))
    return CaseSession("fx-7Q2M", FixtureModules(), trace, rng=random.Random(7))


def test_past_its_time_limit_the_agent_is_stopped_the_trace_says_so_and_code_finishes():
    case = new_case()
    model = scripted()
    now = iter([0.0] + [100.0] * 1000)  # the first step already runs past the limit
    verdict = run_case_with_agent(
        case, build_agent(case, model), lambda d: "send", deadline_s=5, clock=lambda: next(now)
    )
    assert verdict == decide(to_evidence(case.evidence))  # the result is still code's
    assert verdict.state is VerdictState.HOLD
    errors = [e.reason for e in case.trace.events if e.kind is TraceKind.ERROR]
    assert errors == [strings.text("trace.error.model_timeout")]
    assert len(model.calls) < len(RUN)  # it was stopped, not left to finish
    assert case.__dict__["agent_fell_back"] is True
    timeline = build_timeline("fx-7Q2M", DataSource.FIXTURE, case.trace.events, case.evidence)
    assert timeline.fell_back is True


def test_within_its_time_limit_the_agent_runs_to_the_end():
    case = new_case()
    verdict = run_case_with_agent(
        case, build_agent(case, scripted()), lambda d: "send", deadline_s=60
    )
    assert verdict == decide(to_evidence(case.evidence))
    assert all(e.kind is not TraceKind.ERROR for e in case.trace.events)


def app_with(tmp_path, monkeypatch, case_model=None, **settings):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Settings(
        _env_file=None,
        snapback_data_dir=tmp_path,
        snapback_agent="deepagents",
        anthropic_api_key=None,
        **settings,
    )
    return TestClient(create_app(s, lookups=KitLookups(DataSource.FIXTURE), case_model=case_model))


def start(client):
    made = client.post("/cases", data={"text": "Nice 1 bed, $1,500 a month"})
    assert made.status_code == 201
    return made.json()


def timeline(client, case):
    r = client.get(
        f"/cases/{case['case_id']}/timeline",
        headers={"Authorization": f"Bearer {case['read_token']}"},
    )
    assert r.status_code == 200
    return r.json()


def test_the_case_route_runs_the_deep_agent_and_its_plan_reaches_the_timeline(
    tmp_path, monkeypatch
):
    client = app_with(tmp_path, monkeypatch, case_model=scripted)
    case = start(client)
    events = client.app.state.store.get(case["case_id"]).events()
    assert any(e.chosen_by == "model" for e in events)
    assert all(e.kind is not TraceKind.ERROR for e in events)
    body = timeline(client, case)
    assert body["mode"] == "deepagents" and body["fell_back"] is False
    assert [t["content"] for t in body["todos"]] == [t["content"] for t in TODOS]
    picked = next(s for s in body["steps"] if s["label"] == "Chose which checks to run")
    assert picked["by"] == "agent"


def test_with_no_model_key_the_case_route_falls_back_to_the_policy_and_says_so(
    tmp_path, monkeypatch
):
    client = app_with(tmp_path, monkeypatch)
    case = start(client)
    stored = client.app.state.store.get(case["case_id"])
    events = stored.events()
    assert [e.reason for e in events if e.kind is TraceKind.ERROR] == [
        strings.text("trace.error.model_failed")
    ]
    assert {e.chosen_by for e in events} == {"policy"}
    assert stored.session.waiting_for_approval  # the policy carried the case to the renter
    body = timeline(client, case)
    assert body["fell_back"] is True
    assert any(
        s["label"] == "The agent stopped, so code finished the checks" for s in body["steps"]
    )


def test_a_model_that_breaks_on_the_route_is_finished_by_the_policy(tmp_path, monkeypatch):
    class Broken(ScriptedChat):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            raise RuntimeError("no connection")

    client = app_with(tmp_path, monkeypatch, case_model=lambda: Broken(turns=[], calls=[]))
    case = start(client)
    stored = client.app.state.store.get(case["case_id"])
    assert stored.session.waiting_for_approval
    token = {"Authorization": f"Bearer {case['token']}"}
    r = client.post(
        f"/cases/{case['case_id']}/challenge/approve", json={"decision": "send"}, headers=token
    )
    assert r.status_code == 200
    errors = [e for e in stored.events() if e.kind is TraceKind.ERROR]
    assert len(errors) == 1  # once fallen back, the case stays on the policy
    assert stored.done


def test_a_slow_model_call_is_cut_off_at_the_time_limit_and_cannot_touch_the_case_after():
    import time

    class Slow(ScriptedChat):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            time.sleep(1.5)  # one model call far longer than the agent's whole budget
            return super()._generate(messages, stop, run_manager, **kwargs)

    case = new_case()
    started = time.monotonic()
    verdict = run_case_with_agent(
        case,
        build_agent(case, Slow(turns=scripted().turns, calls=[])),
        lambda d: "send",
        deadline_s=0.3,
    )
    took = time.monotonic() - started
    assert took < 1.0, took  # bounded by the budget, not by the slow call
    assert verdict == decide(to_evidence(case.evidence))
    assert [e.reason for e in case.trace.events if e.kind is TraceKind.ERROR] == [
        strings.text("trace.error.model_timeout")
    ]
    seen = len(case.trace.events)
    time.sleep(2.0)  # the abandoned call returns a tool call; it must not land
    assert len(case.trace.events) == seen
    assert not any(e.chosen_by == "model" for e in case.trace.events)
