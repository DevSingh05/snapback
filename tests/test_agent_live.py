"""The deep agent in the background (SNAPBACK_AGENT=deepagents_async): the answer comes from the
policy at once, the agent follows on its own thread and its steps land in the timeline, and
`decide()` alone sets the result.

No network, no key: a scripted chat model plays the main agent and every sub-agent. Skipped
unless the `agent` extra is installed.
"""

import json
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

pytest.importorskip("deepagents")

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from pydantic import SecretStr  # noqa: E402

from snapback.agent import casework  # noqa: E402
from snapback.agent.background import BackgroundAgents  # noqa: E402
from snapback.agent.graph import run_advisory  # noqa: E402
from snapback.agent.join import KitLookups  # noqa: E402
from snapback.agent.session import UPDATED  # noqa: E402
from snapback.api.main import create_app  # noqa: E402
from snapback.card import strings  # noqa: E402
from snapback.contracts import (  # noqa: E402
    DataSource,
    LocateResult,
    LocateStatus,
    PhotoLocation,
    RuleCategory,
    RuleHit,
    TraceKind,
    VerdictState,
)
from snapback.settings import Settings  # noqa: E402

FAMILIES = ["record", "office-and-licence", "owner", "place", "search"]
_calls = iter(range(1, 1_000_000))
_lock = threading.Lock()


def call(name: str, **args: Any) -> dict:
    with _lock:
        return {"name": name, "args": args, "id": f"c{next(_calls)}", "type": "tool_call"}


class Crew(BaseChatModel):
    """The main agent and the sub-agents on one scripted model, told apart by the system prompt.
    `delay` makes every model call slow; `on_owner` runs when the owner sub-agent first acts (a
    stand-in for a check that finds something)."""

    delay: float = 0.0
    on_owner: Any = None
    broken: bool = False
    seen: Any = None  # list of models' calls, for assertions
    started: Any = None  # a list; one entry per model call that begins

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self) -> str:
        return "crew"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.started is not None:
            self.started.append(time.monotonic())
        if self.delay:
            time.sleep(self.delay)
        if self.broken:
            raise RuntimeError("no connection")
        system = str(messages[0].content)
        if self.seen is not None:
            self.seen.append("sub" if "checker for one rental case" in system else "main")
        reply = (
            self._sub(messages, system)
            if "checker for one rental case" in system
            else self._main(messages)
        )
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def _sub(self, messages, system):
        tool_name = re.search(r"tool,\s*`(\w+)`", system).group(1)
        path = re.search(r"path `([^`]+)`", system).group(1)
        done = {m.name: m for m in messages if isinstance(m, ToolMessage)}
        if tool_name not in done:
            if tool_name == "read_owner_facts" and self.on_owner is not None:
                self.on_owner()
            return AIMessage(content="", tool_calls=[call(tool_name)])
        if "write_file" not in done:
            return AIMessage(
                content="",
                tool_calls=[
                    call("write_file", file_path=path, content=str(done[tool_name].content))
                ],
            )
        return AIMessage(content="Note written.")

    def _main(self, messages):
        asked = [tc for m in messages if isinstance(m, AIMessage) for tc in m.tool_calls]
        names = [tc["name"] for tc in asked]
        case_id = re.search(r"/case/([^/\s]+)/", str(messages[0].content))
        if "write_todos" not in names:
            todos = [
                {"content": "Hand the checks to the sub-agents", "status": "in_progress"},
                {"content": "Write explanation.md", "status": "pending"},
            ]
            return AIMessage(content="", tool_calls=[call("write_todos", todos=todos)])
        if "task" not in names:
            return AIMessage(
                content="",
                tool_calls=[
                    call("task", description=f"Write the {n} note.", subagent_type=n)
                    for n in FAMILIES
                ],
            )
        if names.count("write_todos") < 2:
            todos = [
                {"content": "Hand the checks to the sub-agents", "status": "completed"},
                {"content": "Write explanation.md", "status": "completed"},
            ]
            return AIMessage(content="", tool_calls=[call("write_todos", todos=todos)])
        if "write_file" not in names:
            cid = case_id.group(1) if case_id else "x"
            files = [("explanation", "What we could confirm."), ("tour_prep", "1. Ask the office.")]
            return AIMessage(
                content="",
                tool_calls=[
                    call("write_file", file_path=f"/case/{cid}/{stem}.md", content=text)
                    for stem, text in files
                ],
            )
        return AIMessage(content="Done.")


def make_client(tmp_path, monkeypatch, crew: Callable[[], Crew], **settings):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Settings(
        _env_file=None,
        snapback_data_dir=tmp_path,
        snapback_agent="deepagents_async",
        anthropic_api_key=None,
        **settings,
    )
    return TestClient(create_app(s, lookups=KitLookups(DataSource.FIXTURE), case_model=crew))


def start(client):
    made = client.post("/cases", data={"text": "Nice 1 bed, $1,500 a month"})
    assert made.status_code == 201
    return made.json()


def read(client, case, path="timeline"):
    r = client.get(
        f"/cases/{case['case_id']}/{path}",
        headers={"Authorization": f"Bearer {case['read_token']}"},
    )
    assert r.status_code == 200
    return r.json()


def stored(client, case):
    return client.app.state.store.get(case["case_id"])


def approve(client, case):
    r = client.post(
        f"/cases/{case['case_id']}/challenge/approve",
        json={"decision": "send"},
        headers={"Authorization": f"Bearer {case['token']}"},
    )
    assert r.status_code == 200


# --- the request does not wait, the agent follows ---------------------------------------------


def test_the_post_returns_before_a_slow_agent_and_the_steps_land_in_the_timeline(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch, lambda: Crew(delay=0.4))
    started = time.monotonic()
    case = start(client)
    took = time.monotonic() - started
    assert took < 1.5, took  # the policy answered; the agent's ~10 slow calls are not in it
    live = read(client, case)
    assert live["running"] is True and live["mode"] == "deepagents"
    assert stored(client, case).session.waiting_for_approval  # the policy carried it to the renter

    client.app.state.store.wait_for_agents()
    done = read(client, case)
    assert done["running"] is False and done["fell_back"] is False
    assert [t["content"] for t in done["todos"]][0] == "Hand the checks to the sub-agents"
    delegated = [s for s in done["steps"] if s["label"].startswith("Handed the")]
    assert len(delegated) == 5 and {s["by"] for s in delegated} == {"agent"}
    assert any(s["label"] == "Wrote a working note" for s in done["steps"])


def test_the_agent_never_picks_for_the_case(tmp_path, monkeypatch):
    seen: list = []
    client = make_client(tmp_path, monkeypatch, lambda: Crew(seen=seen))
    case = start(client)
    client.app.state.store.wait_for_agents()
    session = stored(client, case).session
    # every choice on the trace was the policy's; the agent only planned and delegated
    choices = [e for e in session.trace.events if e.kind is TraceKind.CHOICE]
    assert choices and {e.chosen_by for e in choices} == {"policy"}
    assert "main" in seen and "sub" in seen


def test_a_run_that_adds_no_evidence_never_changes_the_verdict(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, lambda: Crew(delay=0.05))
    case = start(client)
    approve(client, case)
    shown = stored(client, case)
    before = shown.session.verdict
    assert before is not None
    client.app.state.store.wait_for_agents()
    assert shown.session.verdict == before
    steps = read(client, case)["steps"]
    assert all(s["label"] != "Updated after more checks" for s in steps)
    assert sum(e.kind is TraceKind.VERDICT for e in shown.events()) == 1


def test_more_evidence_runs_decide_again_and_a_state_change_is_a_timeline_step(
    tmp_path, monkeypatch
):
    go = threading.Event()
    # a photo placed in a different home: the one kind of proof that sets DONT_PAY
    elsewhere = LocateResult(
        thresholds_version="t",
        case_id="x",
        photos=[PhotoLocation(photo_id="p1", status=LocateStatus.LOCATED_ELSEWHERE)],
    )
    holder: dict = {}

    def found():
        assert go.wait(10)
        holder["session"].add_evidence({"locate": elsewhere})

    client = make_client(tmp_path, monkeypatch, lambda: Crew(on_owner=found))
    case = start(client)
    holder["session"] = stored(client, case).session
    approve(client, case)
    session = stored(client, case).session
    assert session.verdict.state is VerdictState.HOLD
    go.set()
    client.app.state.store.wait_for_agents()

    assert session.verdict.state is VerdictState.DONT_PAY  # decide() on the new evidence
    steps = read(client, case)["steps"]
    labels = [s["label"] for s in steps]
    assert "Updated after more checks" in labels
    updated = steps[labels.index("Updated after more checks")]
    assert "Hold off" in updated["result"] and updated["by"] == "code"
    # a new verdict step follows the update, so the trace matches the card
    assert labels[labels.index("Updated after more checks") + 1] == "Code worked out the result"
    assert read(client, case, "card")["state"] == "dont_pay"


def test_evidence_added_to_a_running_case_is_carried_into_its_decision(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, lambda: Crew())
    case = start(client)
    session = stored(client, case).session
    assert session.verdict is None
    flag = RuleHit(
        rule_id="payment.zelle_before_viewing",
        category=RuleCategory.PAYMENT_METHOD,
        red_flag=True,
    )
    assert session.add_evidence({"rules": [flag]}) is False  # nothing decided yet, nothing moves
    assert flag in session.evidence.rules
    assert all(e.pick != UPDATED for e in session.trace.events)


# --- limits -----------------------------------------------------------------------------------


def test_past_its_time_limit_the_background_agent_is_cut_off_and_the_timeline_says_so(
    tmp_path, monkeypatch
):
    client = make_client(
        tmp_path, monkeypatch, lambda: Crew(delay=1.0), snapback_agent_timeout_s=0.3
    )
    case = start(client)
    session = stored(client, case).session
    approve(client, case)
    before = session.verdict
    started = time.monotonic()
    client.app.state.store.wait_for_agents()
    assert time.monotonic() - started < 1.0  # bounded by the limit, not by the slow calls
    body = read(client, case)
    assert body["fell_back"] is True and body["running"] is False
    assert [e.reason for e in session.trace.events if e.kind is TraceKind.ERROR] == [
        strings.text("trace.error.model_timeout")
    ]
    assert session.verdict == before


def test_after_the_time_limit_no_model_call_starts_and_the_pool_is_free(tmp_path, monkeypatch):
    started: list = []
    client = make_client(
        tmp_path,
        monkeypatch,
        lambda: Crew(delay=0.4, started=started),
        snapback_agent_timeout_s=0.6,
        snapback_agent_max_concurrent=2,
    )
    for _ in range(3):
        start(client)
    client.app.state.store.wait_for_agents()
    returned = time.monotonic()
    after_wait = len(started)
    time.sleep(2.5)  # abandoned runs get every chance to carry on
    late = [t for t in started if t > returned]
    assert len(started) == after_wait and late == []


def test_a_model_that_breaks_leaves_the_case_and_the_answer_alone(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, lambda: Crew(broken=True))
    case = start(client)
    client.app.state.store.wait_for_agents()
    body = read(client, case)
    assert body["fell_back"] is True and body["running"] is False
    assert stored(client, case).session.waiting_for_approval
    approve(client, case)
    assert read(client, case, "card")["state"] == "hold"


def test_a_case_stuck_behind_busy_workers_ends_with_a_terminal_step_not_a_wait_forever(
    tmp_path, monkeypatch
):
    client = make_client(
        tmp_path,
        monkeypatch,
        lambda: Crew(delay=3.0),
        snapback_agent_max_concurrent=1,
        snapback_agent_queue_wait_s=0.4,
    )
    first = start(client)
    second = start(client)
    time.sleep(0.9)
    waiting = read(client, second)
    assert waiting["running"] is False and waiting["fell_back"] is True
    assert (
        "The deep agent stopped: it waited too long behind other checks; code set the verdict"
        in [s["label"] for s in waiting["steps"]]
    )
    assert read(client, first)["running"] is True  # the one that got a worker is still at work
    assert stored(client, second).session.waiting_for_approval  # code's answer stands


def test_a_run_that_cannot_even_report_its_end_still_leaves_a_terminal_step(tmp_path, monkeypatch):
    def broken(*_a, **_k):
        raise RuntimeError("the report itself broke")

    monkeypatch.setattr("snapback.agent.graph.run_advisory", broken)
    client = make_client(tmp_path, monkeypatch, lambda: Crew())
    case = start(client)
    client.app.state.store.wait_for_agents()
    body = read(client, case)
    assert body["running"] is False and body["fell_back"] is True


def test_with_no_key_and_no_factory_the_agent_is_skipped_and_the_trace_says_so(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch, None)
    case = start(client)
    client.app.state.store.wait_for_agents()
    body = read(client, case)
    assert body["fell_back"] is True and body["running"] is False
    assert "The deep agent stopped: no model key is set; code set the verdict" in [
        s["label"] for s in body["steps"]
    ]
    assert stored(client, case).session.waiting_for_approval


def test_at_most_n_background_runs_work_at_once_and_the_rest_wait():
    pool = BackgroundAgents(2)
    lock = threading.Lock()
    state = {"now": 0, "peak": 0}
    release = threading.Event()

    def job():
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        release.wait(5)
        with lock:
            state["now"] -= 1

    for i in range(5):
        assert pool.submit(f"c{i}", job) is True
    assert pool.submit("c0", job) is False  # a case runs once
    time.sleep(0.3)
    assert state["now"] == 2 and all(pool.running(f"c{i}") for i in range(5))
    release.set()
    for i in range(5):
        pool.wait(f"c{i}", 5)
    assert state["peak"] == 2 and not any(pool.running(f"c{i}") for i in range(5))
    pool.shutdown()


def test_a_case_that_gets_no_worker_in_time_is_given_up_on_and_never_starts():
    pool = BackgroundAgents(1)
    release = threading.Event()
    ran: list[str] = []
    gave_up: list[str] = []
    pool.submit("hog", lambda: release.wait(5))
    pool.submit("late", lambda: ran.append("late"), max_wait_s=0.2, on_expire=gave_up.append)
    assert pool.running("late")
    time.sleep(0.6)
    assert gave_up == ["busy"] and not pool.running("late") and pool.running("hog")
    release.set()
    pool.wait("hog", 5)
    time.sleep(0.2)
    assert ran == []  # it was dropped, not run late
    pool.shutdown()


def test_a_job_that_runs_far_past_its_limit_is_given_up_on_so_nothing_waits_on_it():
    pool = BackgroundAgents(1)
    release = threading.Event()
    gave_up: list[str] = []
    pool.submit("stuck", lambda: release.wait(5), max_run_s=0.2, on_expire=gave_up.append)
    time.sleep(0.1)
    assert pool.running("stuck")
    time.sleep(0.4)
    assert gave_up == ["stuck"] and not pool.running("stuck")
    release.set()
    pool.shutdown()


def test_a_job_that_ends_in_time_is_never_reported_as_given_up():
    pool = BackgroundAgents(1)
    gave_up: list[str] = []
    pool.submit("ok", lambda: None, max_wait_s=0.2, max_run_s=0.2, on_expire=gave_up.append)
    pool.wait("ok", 5)
    time.sleep(0.5)
    assert gave_up == []
    pool.shutdown()


def test_a_crashing_job_is_contained_and_ends():
    pool = BackgroundAgents(1)

    def bad():
        raise ValueError("boom")

    pool.submit("a", bad)
    pool.wait("a", 5)
    assert not pool.running("a")
    pool.shutdown()


# --- the stream -------------------------------------------------------------------------------


def test_the_stream_sends_each_change_until_the_agent_is_done_and_needs_the_header_token(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch, lambda: Crew(delay=0.15))
    case = start(client)
    path = f"/cases/{case['case_id']}/timeline/stream"
    assert client.get(path).status_code in (401, 403)
    assert client.get(f"{path}?token={case['read_token']}").status_code == 401  # never in the URL
    headers = {"Authorization": f"Bearer {case['read_token']}"}
    bodies = []
    with client.stream("GET", path, headers=headers) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert "private, no-store" in r.headers["cache-control"]
        text = "".join(r.iter_text())
    for block in text.split("\n\n"):
        if block.startswith("event: timeline"):
            bodies.append(json.loads(block.split("data: ", 1)[1]))
    assert len(bodies) >= 3  # it showed progress, not only the end
    assert bodies[0]["running"] is True and bodies[-1]["running"] is False
    counts = [len(b["steps"]) for b in bodies]
    assert counts == sorted(counts) and counts[0] < counts[-1]


def test_the_stream_of_a_case_with_no_agent_is_one_snapshot_then_it_ends(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Settings(_env_file=None, snapback_data_dir=tmp_path, anthropic_api_key=None)
    client = TestClient(create_app(s, lookups=KitLookups(DataSource.FIXTURE)))
    case = start(client)
    headers = {"Authorization": f"Bearer {case['read_token']}"}
    with client.stream("GET", f"/cases/{case['case_id']}/timeline/stream", headers=headers) as r:
        text = "".join(r.iter_text())
    assert text.count("event: timeline") == 1 and '"running":false' in text


# --- models and tracing -----------------------------------------------------------------------


def test_defaults_are_sonnet_for_the_agent_and_haiku_for_the_sub_agents():
    s = Settings(_env_file=None)
    assert s.snapback_agent_model == "claude-sonnet-5-5"
    assert s.snapback_subagent_model == "claude-haiku-5-5"
    assert s.snapback_agent_max_concurrent == 2


def test_the_background_agent_gets_a_longer_budget_unless_the_limit_is_set_explicitly():
    assert Settings(_env_file=None).agent_timeout_s == 25.0  # on the request path: unchanged
    assert Settings(_env_file=None, snapback_agent="deepagents").agent_timeout_s == 25.0
    assert Settings(_env_file=None, snapback_agent="deepagents_async").agent_timeout_s == 60.0
    explicit = Settings(
        _env_file=None, snapback_agent="deepagents_async", snapback_agent_timeout_s=9
    )
    assert explicit.agent_timeout_s == 9.0


def test_the_main_agent_and_the_sub_agents_get_their_own_models(tmp_path, monkeypatch):
    import snapback.agent.graph as graph

    built: list[tuple] = []

    def fake_build_model(api_key=None, name=None, timeout_s=None, max_tokens=4096, effort=None):
        built.append((name, max_tokens, effort))
        return Crew()

    monkeypatch.setattr(graph, "build_model", fake_build_model)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Settings(
        _env_file=None,
        snapback_data_dir=tmp_path,
        snapback_agent="deepagents_async",
        anthropic_api_key=SecretStr("not-a-real-key"),
    )
    client = TestClient(create_app(s, lookups=KitLookups(DataSource.FIXTURE)))
    case = start(client)
    client.app.state.store.wait_for_agents()
    assert [(n, e) for n, _, e in built] == [
        ("claude-sonnet-5-5", "low"),
        ("claude-haiku-5-5", "low"),
    ]
    assert read(client, case)["fell_back"] is False


def test_langsmith_metadata_is_the_case_id_and_the_mode_only():
    class Recorder:
        configs: list = []

        def stream(self, payload, config, stream_mode=None):
            self.configs.append(config)
            return iter(())

        def get_state(self, config):
            return type("S", (), {"values": {}})()

    from snapback.agent import CaseSession, FixtureModules, Trace

    case = CaseSession("fx-7Q2M", FixtureModules(), Trace("fx-7Q2M", DataSource.FIXTURE))
    assert run_advisory(case, Recorder(), deadline_s=5) is True
    assert Recorder.configs[0]["metadata"] == {"case_id": "fx-7Q2M", "mode": "deepagents_async"}
    assert "listing" not in json.dumps(Recorder.configs[0]["metadata"])


def test_the_advisory_agent_has_no_tool_that_can_move_the_case():
    from snapback.agent import CaseSession, FixtureModules, Trace
    from snapback.agent.graph import build_advisory_agent, build_subagents

    case = CaseSession("fx-7Q2M", FixtureModules(), Trace("fx-7Q2M", DataSource.FIXTURE))
    agent = build_advisory_agent(case, Crew())
    assert agent is not None
    names = {n for s in build_subagents(case) for t in s["tools"] for n in [t.name]}
    assert not names & {"choose_option", "draw_spot", "send_challenge", "place_choose_option"}
    assert casework.WALK not in {casework.STEMS}
