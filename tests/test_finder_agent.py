"""M9: the finder as a deep agent, driven by a scripted chat model. No network, no key.

Skipped unless the `agent` extra is installed (`uv sync --extra agent`).
"""

import re
from typing import Any

import pytest

pytest.importorskip("deepagents")

from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

from snapback.agent import finder  # noqa: E402
from snapback.agent.finder import FinderSession, load_fixture_places, run_turn  # noqa: E402
from snapback.contracts import CasePreferences, TraceKind  # noqa: E402
from test_finder import (  # noqa: E402
    BAIT_ADDRESS,
    BAIT_COMPANY,
    BAIT_PHONE,
    SCRIPT,
    new_session,
)

_n = [0]


def _call(name: str, **args: Any) -> AIMessage:
    _n[0] += 1
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": f"c{_n[0]}", "type": "tool_call"}],
    )


class FakeCrew(BaseChatModel):
    """One model for the main agent and both sub-agents, told apart by the system prompt."""

    prefs: list = []  # options the preferences sub-agent picks, in order
    leads: list = ["P1", "P2", "P3"]
    skip_todos: bool = False
    closing: str = "I lined up three places and have one thing to suggest."
    seen: list = []  # every message text the model was shown

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self) -> str:
        return "fake-crew"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.extend(str(m.content) + repr(getattr(m, "tool_calls", "")) for m in messages)
        system = str(messages[0].content)
        if "preferences checker" in system:
            reply = self._sub(
                messages, system, "read_learned", self.prefs, "prefs_choose", "option"
            )
        elif "search checker" in system:
            reply = self._sub(messages, system, "read_ranked", self.leads, "lead_pick", "alias")
        else:
            reply = self._main(messages)
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def _sub(self, messages, system, reader, picks, chooser, arg):
        path = re.search(r"path `([^`]+)`", system).group(1)
        tools = [m for m in messages if isinstance(m, ToolMessage)]
        names = [m.name for m in tools]
        if reader not in names:
            return _call(reader)
        done = names.count(chooser)
        if done < len(picks):
            return _call(chooser, **{arg: picks[done], "reason": "It fits what the renter did."})
        if "write_file" not in names:
            return _call("write_file", file_path=path, content=f"{chooser}: {', '.join(picks)}")
        return AIMessage(content="Done.")

    def _main(self, messages):
        asked = [tc for m in messages if isinstance(m, AIMessage) for tc in m.tool_calls]
        names = [tc["name"] for tc in asked]
        tasks = [tc["args"].get("subagent_type") for tc in asked if tc["name"] == "task"]
        todos = [
            {"content": "Offer what to remember", "status": "in_progress"},
            {"content": "Lead the list", "status": "pending"},
        ]
        if "write_todos" not in names and not self.skip_todos:
            return _call("write_todos", todos=todos)
        if "preferences" not in tasks:
            return _call("task", description="Offer what to remember", subagent_type="preferences")
        if "search" not in tasks:
            return _call("task", description="Lead the list", subagent_type="search")
        if names.count("write_todos") < 2 and not self.skip_todos:
            return _call("write_todos", todos=[{**t, "status": "completed"} for t in todos])
        return AIMessage(content=self.closing)


def sub(tmp_path, name):
    (tmp_path / name).mkdir()
    return tmp_path / name


def crew(**kw) -> FakeCrew:
    return FakeCrew(**({"seen": []} | kw))


ALL_FOUR = ["propose_lower_budget", "propose_prefer_scans", "propose_parking", "propose_no_walkup"]


def accept_all(s: FinderSession) -> CasePreferences:
    for p in list(s.proposals):
        s.decide(p.id, accept=True)
    return s.applied


def test_write_todos_fires_first_and_shows_in_the_trace(tmp_path):
    s = new_session(tmp_path, crew(prefs=ALL_FOUR))
    run_turn(s, SCRIPT)
    todo = [e for e in s.trace if e.kind is TraceKind.TODO]
    assert todo and todo[0].chosen_by == "model" and todo[0].options
    first_agent = next(i for i, e in enumerate(s.trace) if e.kind is TraceKind.AGENT)
    assert s.trace.index(todo[0]) < first_agent  # the plan comes before any hand-off
    assert any(e.pick == "sub-agent: preferences" for e in s.trace)
    assert any(e.kind is TraceKind.FILE for e in s.trace)
    assert any(
        e.options and e.options[0].startswith("[x]") for e in s.trace if e.kind is TraceKind.TODO
    )


def test_a_model_that_skips_the_plan_gets_nothing_done_and_code_carries_on(tmp_path):
    s = new_session(tmp_path, crew(prefs=ALL_FOUR, skip_todos=True))
    reply = run_turn(s, SCRIPT)
    assert not any(e.kind is TraceKind.TODO for e in s.trace)
    assert any(e.kind is TraceKind.ERROR and "plan" in e.reason for e in s.trace)
    assert len(reply.proposals) == 4 and all(p.chosen_by == "policy" for p in reply.proposals)
    assert all(p.chosen_by == "policy" for p in reply.picks) and reply.reply_by == "policy"


def test_policy_and_model_end_in_the_same_applied_prefs(tmp_path):
    policy = new_session(sub(tmp_path, "a"))
    run_turn(policy, SCRIPT)
    model = new_session(sub(tmp_path, "b"), crew(prefs=ALL_FOUR, leads=["P3", "P1", "P2"]))
    reply = run_turn(model, SCRIPT)
    assert [p.key for p in reply.proposals] == ALL_FOUR  # the model's order, code's content
    assert all(p.chosen_by == "model" for p in reply.proposals)
    assert reply.reply_by == "model" and reply.mode == "deepagents"
    assert model.applied == CasePreferences()  # nothing yet
    assert accept_all(policy) == accept_all(model)
    assert model.applied.max_rent == 1100
    # after the yes, the picks are code's and identical
    assert [p.pid for p in policy.picks] == [p.pid for p in model.picks]


def test_a_model_pick_off_the_list_or_a_wait_never_adds_anything(tmp_path):
    wait = new_session(sub(tmp_path, "w"), crew(prefs=["wait"]))
    assert run_turn(wait, SCRIPT).proposals == []
    assert accept_all(wait) == CasePreferences()
    off = new_session(sub(tmp_path, "o"), crew(prefs=["propose_everything", "propose_parking"]))
    reply = run_turn(off, SCRIPT)
    keys = [p.key for p in reply.proposals]
    assert "propose_everything" not in keys and "propose_parking" in keys
    assert set(keys) <= set(ALL_FOUR)
    policy = new_session(sub(tmp_path, "p"))
    run_turn(policy, SCRIPT)
    accept_all(off)
    assert off.applied != CasePreferences()
    assert off.applied == accept_all(policy)  # code fills what the model left open


def test_the_model_is_shown_nothing_it_may_not_see(tmp_path):
    m = crew(prefs=ALL_FOUR)
    s = new_session(tmp_path, m)
    text = f"no walk-ups, call {BAIT_PHONE} at {BAIT_ADDRESS}"
    run_turn(s, [*SCRIPT, *finder.read_text(text)])
    blob = "\n".join(m.seen)
    assert m.seen
    for bait in (BAIT_ADDRESS, BAIT_PHONE, BAIT_COMPANY, "fx-fnd", "call 713", "1450", "1620"):
        assert bait not in blob
    assert "P1" in blob and "passed_walkups" in blob  # it did see the allowed things


def test_a_leaky_row_in_a_live_run_never_reaches_the_model(tmp_path, monkeypatch):
    real = finder._alias_row
    monkeypatch.setattr(
        finder, "_alias_row", lambda a, p, c: real(a, p, c) | {"address": BAIT_ADDRESS}
    )
    m = crew(prefs=ALL_FOUR)
    s = new_session(tmp_path, m)
    reply = run_turn(s, SCRIPT)  # the run survives; code finishes it
    assert BAIT_ADDRESS not in "\n".join(m.seen)
    assert len(reply.picks) == 3 or reply.picks == []


def test_a_model_reason_with_a_number_or_a_claim_is_replaced_by_code(tmp_path):
    for reason in ("It is for rent at 4500 a month.", "Available now and verified."):
        s = new_session(tmp_path)
        d = s.search_desk()
        assert d.choose("P1", reason, "model")
        assert d.chosen[0][2].startswith("Leads because") and d.chosen[0][1] == "model"


def test_the_fixture_places_load_clean():
    places = load_fixture_places()
    assert len(places) == 10 and all(p.pid.startswith("fx-fnd-") for p in places)


def test_the_renters_cleaned_words_reach_the_model_as_words_and_no_contact_does(tmp_path):
    """The model reads what the renter wrote, fenced, but never a phone, email, link or street
    address. A mutant `clean_words` that lets one through fails here."""
    m = crew(prefs=ALL_FOUR)
    s = new_session(tmp_path, m)
    text = (
        f"no walk-ups, I want big windows near the park. Text {BAIT_PHONE}, write "
        f"landlord.fixture@example.com, apply at https://fixture-rentals.example.net/a, "
        f"I liked {BAIT_ADDRESS}"
    )
    reply = run_turn(s, [*SCRIPT, *finder.read_text(text)], text)
    blob = "\n".join(m.seen)
    assert "big windows near the park" in blob and "<renter_words>\n" in blob
    for bait in (
        BAIT_PHONE,
        "landlord.fixture@example.com",
        "fixture-rentals.example.net",
        BAIT_ADDRESS,
        "Fixture Boulevard",
        "1450",
        "fx-fnd",
    ):
        assert bait not in blob
    assert reply.reply_by == "model"
    # the words change nothing by themselves: code still decides what applies
    assert s.applied == CasePreferences()
    log = (tmp_path / "log.jsonl").read_text()
    assert "big windows" not in log and BAIT_PHONE not in log


def test_without_words_the_model_gets_only_the_plan_order(tmp_path):
    m = crew(prefs=ALL_FOUR)
    s = new_session(tmp_path, m)
    run_turn(s, SCRIPT)
    assert "<renter_words>\n" not in "\n".join(m.seen)
