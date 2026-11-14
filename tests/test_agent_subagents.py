"""Sub-agents per check family and the case notes in the deepagents file system.

A fake chat model plays the main agent (todos, choices, delegation, explanation) and each
sub-agent (read its facts, write its note). No network, no key. Skipped unless the `agent`
extra is installed.
"""

import json
import random
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

pytest.importorskip("deepagents")

from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

from snapback.agent import (  # noqa: E402
    CaseSession,
    FixtureModules,
    PolicyChooser,
    Trace,
    casework,  # noqa: E402
    run_case,
)
from snapback.agent.demo import demo_case_ids, demo_modules, load_demo_case  # noqa: E402
from snapback.agent.graph import (  # noqa: E402
    build_agent,
    build_subagents,
    enable_langsmith,
    run_case_with_agent,
)
from snapback.agent.intake import read_listing  # noqa: E402
from snapback.contracts import DataSource, TraceKind  # noqa: E402
from snapback.verdict import build_card  # noqa: E402

CHECK_AGENTS = ["record", "office-and-licence", "owner", "place", "search"]
_calls = [0]


def _call(name: str, **args: Any) -> AIMessage:
    _calls[0] += 1
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": f"c{_calls[0]}", "type": "tool_call"}],
    )


class FakeCrew(BaseChatModel):
    """One model for the main agent and every sub-agent, told apart by the system prompt."""

    case: Any
    pick_last_for_plan: bool = False
    todos: bool = True
    agents: list = CHECK_AGENTS
    delegate: bool = True

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self) -> str:
        return "fake-crew"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        system = str(messages[0].content)
        reply = (
            self._sub(messages, system)
            if "checker for one rental case" in system
            else self._main(messages)
        )
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def _sub(self, messages, system):
        if "place checker" in system:
            return self._place(messages, system)
        tool_name = re.search(r"tool,\s*`(\w+)`", system).group(1)
        path = re.search(r"path `([^`]+)`", system).group(1)
        done = {m.name: m for m in messages if isinstance(m, ToolMessage)}
        if tool_name not in done:
            return _call(tool_name)
        if "write_file" not in done:
            return _call("write_file", file_path=path, content=str(done[tool_name].content))
        return AIMessage(content="Note written.")

    def _place(self, messages, system):
        path = re.search(r"path `([^`]+)`", system).group(1)
        done = [m for m in messages if isinstance(m, ToolMessage)]
        if not done:
            return _call("read_place_facts")
        if self.case.step.value == "place":
            offer = self.case.offer()
            return _call("place_choose_option", option=offer.default, reason="Nearest miss first.")
        if not any(m.name == "write_file" for m in done):
            return _call("write_file", file_path=path, content=str(done[0].content))
        return AIMessage(content="Note written.")

    def _main(self, messages):
        asked = [tc for m in messages if isinstance(m, AIMessage) for tc in m.tool_calls]
        names = [tc["name"] for tc in asked]
        case = self.case
        if self.todos and "write_todos" not in names:
            return _call(
                "write_todos",
                todos=[
                    {"content": "Work the open choices", "status": "in_progress"},
                    {"content": "Delegate to the check sub-agents", "status": "pending"},
                    {"content": "Write the explanation", "status": "pending"},
                ],
            )
        if case.step.value == "place":
            if not any(tc["args"].get("subagent_type") == "place" for tc in asked):
                return _call(
                    "task", description="Retry the unplaced photos.", subagent_type="place"
                )
            return AIMessage(content="The place sub-agent has not finished.")
        offer = case.offer()
        if offer is not None:
            if len(offer.options) == 1:
                return _call("open_choice")
            label = offer.default
            if self.pick_last_for_plan and offer.kind.value == "next_check":
                label = offer.options[-1]
            return _call("choose_option", option=label, reason="Matches the facts shown.")
        step = case.step.value
        if step == "spot":
            sent = [tc["args"].get("subagent_type") for tc in asked if tc["name"] == "task"]
            if self.delegate:
                for name in self.agents:
                    if name not in sent:
                        return _call(
                            "task", description=f"Write the {name} note.", subagent_type=name
                        )
            return _call("draw_spot")
        if step == "approval":
            return _call("send_challenge")
        if step == "done":
            for stem, text in (
                ("explanation", "What we could confirm, in plain words."),
                ("tour_prep", "1. Ask the office for the number it has on record."),
            ):
                path = casework.note_path(case.case_id, stem)
                if not any(tc["args"].get("file_path") == path for tc in asked):
                    return _call("write_file", file_path=path, content=text)
        return AIMessage(content="The case is finished.")


def make_case(case_id: str = "fx-7Q2M", **module_options) -> CaseSession:
    start = datetime(2026, 11, 13, 21, 41, tzinfo=UTC)
    ticks = iter(start + timedelta(seconds=n) for n in range(10_000))
    trace = Trace(case_id, DataSource.FIXTURE, clock=lambda: next(ticks))
    return CaseSession(case_id, FixtureModules(**module_options), trace, rng=random.Random(7))


def demo_session(demo_id: str) -> CaseSession:
    demo = load_demo_case(demo_id)
    listing = read_listing(demo.listing_text)
    full_id = f"fx-demo-{demo_id}"
    session = CaseSession(
        full_id,
        demo_modules(demo, listing),
        Trace(full_id, DataSource.FIXTURE),
        rng=random.Random(3),
    )
    session.search_places = lambda use_model=False: (
        "Source: researched places\nPlace 1: apartment, 2 bed, $1,900"
    )
    return session


def run_with_crew(session: CaseSession, **crew):
    agent = build_agent(session, FakeCrew(case=session, **crew))
    return run_case_with_agent(session, agent, lambda draft: "send")


# --- the shape of the crew --------------------------------------------------------------------


def test_one_sub_agent_per_check_family_each_with_only_its_own_tool():
    specs = {s["name"]: s for s in build_subagents(make_case())}
    assert set(CHECK_AGENTS) <= set(specs)
    reads = {name: [t.name for t in specs[name]["tools"]] for name in CHECK_AGENTS}
    assert reads == {
        "record": ["read_record_facts"],
        "office-and-licence": ["read_office_facts"],
        "owner": ["read_owner_facts"],
        "place": ["read_place_facts"],
        "search": ["search_places"],
    }
    # nobody but the main agent has the choice tools, including the built-in general agent
    assert specs["general-purpose"]["tools"] == []


# --- what the run leaves behind ---------------------------------------------------------------


def test_main_agent_plans_delegates_and_every_note_lands_in_the_case():
    session = demo_session("a")
    verdict = run_with_crew(session)

    assert verdict is not None
    trace = session.trace.events
    todos = [e for e in trace if e.reason.startswith("The agent wrote its plan")]
    assert todos and todos[0].chosen_by == "model" and len(todos[0].options) == 3
    handed = [e.pick for e in trace if e.pick and e.pick.startswith("sub-agent: ")]
    assert handed == [f"sub-agent: {name}" for name in CHECK_AGENTS]
    written = {e.pick for e in trace if e.pick and e.pick.startswith("file: ")}
    for stem in (*casework.STEMS, *casework.MAIN_STEMS):
        assert f"file: {casework.note_path(session.case_id, stem)}" in written
    assert set(session.notes) == {*casework.STEMS, *casework.MAIN_STEMS}
    assert {n.by for n in session.notes.values()} == {"model"}
    assert all(e.kind is not TraceKind.ERROR for e in trace)


def test_notes_hold_derived_text_only():
    session = demo_session("a")
    run_with_crew(session)
    for note in session.notes.values():
        assert len(note.text) <= casework.MAX_NOTE_CHARS
        assert "data:image" not in note.text and "base64" not in note.text
    # the place note is results and counts, never a photo id or an image
    place = session.notes[casework.PLACE].text
    assert "Photos:" in place and "photo_id" not in place


def test_a_model_note_with_banned_words_or_a_wrong_path_is_cleaned_or_dropped():
    session = make_case()
    ok = casework.keep_note(
        session,
        casework.note_path(session.case_id, "record"),
        "Rent within range\nThis listing is a scam\nDon't pay anyone",
        "model",
    )
    assert ok is not None and ok.text == "Rent within range"
    assert casework.keep_note(session, "/etc/passwd", "x", "model") is None
    assert casework.keep_note(session, "/case/other/record.md", "x", "model") is None


def test_the_sub_agent_cannot_write_outside_its_own_file():
    from deepagents import FilesystemPermission  # noqa: F401  (the rule objects are what we check)

    session = make_case()
    spec = next(s for s in build_subagents(session) if s["name"] == "owner")
    allow, deny = spec["permissions"]
    assert allow.paths == [casework.note_path(session.case_id, "owner")]
    assert allow.mode == "allow" and deny.paths == ["/**"] and deny.mode == "deny"


def test_a_model_that_never_delegates_still_leaves_code_written_notes():
    session = demo_session("b")
    verdict = run_with_crew(session, delegate=False)
    assert verdict is not None
    assert set(session.notes) >= {casework.RECORD, casework.OFFICE, casework.OWNER, casework.PLACE}
    assert {session.notes[s].by for s in (casework.RECORD, casework.PLACE)} == {"policy"}


def test_a_failing_model_falls_back_to_policy_and_notes_are_still_written():
    class Broken(BaseChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        @property
        def _llm_type(self) -> str:
            return "broken"

        def _generate(self, *args, **kwargs):
            raise RuntimeError("model down")

    session = demo_session("a")
    agent = build_agent(session, Broken())
    verdict = run_case_with_agent(session, agent, lambda draft: "send")
    assert verdict is not None
    assert any(e.kind is TraceKind.ERROR for e in session.trace.events)
    assert {n.by for n in session.notes.values()} == {"policy"}


# --- verdict invariance -----------------------------------------------------------------------

CASES = [c for c in demo_case_ids()]


def _outcome(session: CaseSession, verdict):
    card = build_card(session.evidence, checked_at=datetime(2026, 11, 14, 12, 0, tzinfo=UTC))
    return verdict.state, verdict.reasons, card.model_dump(mode="json", exclude={"expires_at"})


@pytest.mark.parametrize("demo_id", CASES)
def test_deepagents_path_and_policy_give_the_same_verdict_and_rows(demo_id):
    policy = demo_session(demo_id)
    expected = _outcome(policy, run_case(policy, PolicyChooser(), lambda draft: "send"))

    agent_session = demo_session(demo_id)
    got = _outcome(agent_session, run_with_crew(agent_session))
    assert got == expected

    # choosing the plan's check order differently moves the order only, never the evidence
    reordered = demo_session(demo_id)
    assert _outcome(reordered, run_with_crew(reordered, pick_last_for_plan=True)) == expected


@pytest.mark.parametrize("demo_id", CASES)
def test_every_model_step_is_stamped(demo_id):
    session = demo_session(demo_id)
    run_with_crew(session)
    for event in session.trace.events:
        assert event.chosen_by in ("model", "policy")
        # the spot is a random draw and the approval is the renter's: both stay policy
        if event.kind is TraceKind.CHOICE and event.choice.value != "which_spot":
            # a model picks only where there are 2+ options
            assert event.chosen_by == ("model" if len(event.options) > 1 else "policy")
        if event.pick and event.pick.startswith(("sub-agent: ", "file: ")):
            assert event.chosen_by == "model"


def test_notes_do_not_change_what_decide_reads():
    a, b = demo_session("a"), demo_session("a")
    run_with_crew(a)
    b.notes.clear()
    run_case(b, PolicyChooser(), lambda draft: "send")
    assert a.evidence == b.evidence


# --- the policy path and the setting ----------------------------------------------------------


def test_policy_notes_are_written_by_code_with_no_model():
    session = demo_session("c")
    run_case(session, PolicyChooser(), lambda draft: "send")
    casework.refresh_policy_notes(session)
    assert set(session.notes) == set(casework.STEMS)
    assert {n.by for n in session.notes.values()} == {"policy"}
    view = casework.notes_view(session)
    assert [n.stem for n in view.notes] == list(casework.STEMS)
    assert view.source is DataSource.FIXTURE


def test_langsmith_turns_on_only_with_a_key(monkeypatch):
    for name in ("LANGSMITH_API_KEY", "LANGSMITH_TRACING", "LANGSMITH_PROJECT"):
        monkeypatch.setenv(name, "x")  # so undo removes whatever enable_langsmith sets
        monkeypatch.delenv(name)
    assert enable_langsmith(None) is False
    assert "LANGSMITH_TRACING" not in __import__("os").environ
    assert enable_langsmith("lsv2_test_key", "snapback") is True
    env = __import__("os").environ
    assert env["LANGSMITH_TRACING"] == "true" and env["LANGSMITH_PROJECT"] == "snapback"


# --- review round 1 (#217) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "Don’t pay anyone",  # curly apostrophe
        "Checks  passed",  # double space
        "Checks passed",  # non-breaking space
        "DONT PAY",
        "DON'T PAY. Something here doesn't match.",
        "Hold off for now",
        "No pague",
        "NO PAGUE a nadie",
        "Algo aquí no coincide",
        "Las revisiones pasaron",
        "Could not place these photos",
        "Espere por ahora",
    ],
)
def test_a_note_line_that_announces_a_result_is_dropped_however_it_is_spelt(line):
    assert casework.clean_note(f"Rent within range\n{line}") == "Rent within range"


def test_ordinary_fact_lines_survive_the_cleaner():
    text = "Rent check: within_range\nPhotos: 3 located_in_claimed\nOwner of record: a company"
    assert casework.clean_note(text) == text


def test_code_notes_do_not_call_search_again_once_a_model_wrote_places():
    session = demo_session("a")
    calls = []
    session.search_places = lambda use_model=False: calls.append(use_model) or "Source: places"
    casework.refresh_policy_notes(session)
    assert calls == [False]  # code notes use the policy, never the model
    casework.keep_note(
        session, casework.note_path(session.case_id, "places"), "From the agent", "model"
    )
    casework.refresh_policy_notes(session)
    assert calls == [False]  # skipped: the model's note is already there


def test_a_family_is_missing_until_a_model_wrote_it():
    from snapback.agent.graph import describe

    session = demo_session("a")
    session.step = type(session.step)("spot")
    casework.refresh_policy_notes(session)  # code notes exist for every family
    missing = json.loads(describe(session))["notes_missing_delegate_to"]
    assert missing == CHECK_AGENTS


class DeniedWrites(BaseChatModel):
    """Every role tries something it must not do; each role's script is by its system prompt."""

    case: Any

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self) -> str:
        return "denied-writes"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        system = str(messages[0].content)
        turn = sum(isinstance(m, AIMessage) for m in messages)
        cid = self.case.case_id
        if "owner checker" in system:
            script = [_call("write_file", file_path=casework.note_path(cid, "record"), content="x")]
        elif "has no tools" in system:  # the replaced general-purpose agent
            script = [
                _call("write_file", file_path="/gp.md", content="x"),
                _call("choose_option", option="rules only", reason="x"),
            ]
        else:
            script = [
                _call("write_file", file_path="/evil.md", content="x"),
                _call("write_file", file_path=casework.note_path(cid, "record"), content="x"),
                _call("task", description="d", subagent_type="owner"),
                _call("task", description="d", subagent_type="general-purpose"),
            ]
        reply = script[turn] if turn < len(script) else AIMessage(content="Done.")
        return ChatResult(generations=[ChatGeneration(message=reply)])


def test_permissions_hold_at_runtime_for_main_sub_agent_and_general_purpose():
    session = demo_session("a")
    agent = build_agent(session, DeniedWrites(case=session))
    config = {"configurable": {"thread_id": "perm"}, "recursion_limit": 40}
    result = agent.invoke({"messages": [("user", "go")]}, config)
    # nothing it tried to write exists
    assert not result.get("files")
    denied = [
        m.content
        for m in result["messages"]
        if isinstance(m, ToolMessage) and m.name == "write_file"
    ]
    assert len(denied) == 2 and all("permission denied" in str(c) for c in denied)


# --- E1 through the harness: the place sub-agent picks the retries -----------------------------


def test_the_place_sub_agent_spends_the_retry_budget_through_its_tools():
    from test_place_agent import StubSearcher
    from test_place_agent import make_case as make_retry_case

    session = make_retry_case(StubSearcher())
    session.search_places = lambda: "Source: researched places"
    verdict = run_with_crew(session)
    assert verdict is not None
    picks = [
        e
        for e in session.trace.events
        if e.choice and e.choice.value in ("next_search", "which_photo")
    ]
    assert picks and all(e.chosen_by == "model" for e in picks if len(e.options) > 1)
    assert session.place_desk.searches_used == 2
    assert "place" in session.notes and session.notes["place"].by == "model"
    from snapback.verdict import decide, to_evidence

    assert verdict == decide(to_evidence(session.evidence))


def test_the_main_agent_cannot_make_the_place_decision():
    from snapback.agent.graph import describe
    from test_place_agent import StubSearcher
    from test_place_agent import make_case as make_retry_case

    session = make_retry_case(StubSearcher())
    session.choose(session.offer().default)  # which checks
    assert session.step.value == "place"
    assert "place sub-agent" in describe(session)


def test_the_place_retry_prompt_and_tools_exist_only_when_the_case_can_retry():
    from test_place_agent import StubSearcher

    plain = next(x for x in build_subagents(make_case()) if x["name"] == "place")
    assert "could not be placed" not in plain["system_prompt"]
    assert [t.name for t in plain["tools"]] == ["read_place_facts"]
    case = make_case()
    case.place_searcher = StubSearcher()
    live = next(x for x in build_subagents(case) if x["name"] == "place")
    assert "could not be placed" in live["system_prompt"]
    assert [t.name for t in live["tools"]][1:] == ["place_open_choice", "place_choose_option"]


def test_a_finished_case_still_tells_the_model_to_delegate_until_the_notes_are_the_agents():
    from snapback.agent.graph import describe

    session = demo_session("a")
    run_case(session, PolicyChooser(), lambda draft: "send")
    assert session.step.value == "done"
    assert json.loads(describe(session))["notes_missing_delegate_to"] == CHECK_AGENTS
    for stem in casework.STEMS:
        casework.keep_note(session, casework.note_path(session.case_id, stem), "x", "model")
    assert json.loads(describe(session)) == {"finished": True}


# --- the opening plan (write_todos) ----------------------------------------------------------


def test_the_main_prompt_opens_with_a_write_todos_plan_with_one_todo_per_family():
    from snapback.agent.graph import KICKOFF, SYSTEM_PROMPT, plan_instruction

    text = plan_instruction(demo_session("a"))
    assert "very first action" in text and "write_todos" in text
    for name in CHECK_AGENTS:
        assert f"Hand the {name} checks to the {name} sub-agent" in text
    assert "completed" in text and "never mark a step completed before it is done" in text
    assert "write_todos" in KICKOFF
    assert "write_todos" in SYSTEM_PROMPT + text


def test_a_walk_case_gets_a_walk_todo_too_and_a_plain_case_does_not():
    from snapback.agent.graph import plan_instruction

    session = demo_session("a")
    assert "walk" not in plan_instruction(session)
    session.walk_plan = lambda: None
    assert "Hand the walk checks to the walk sub-agent" in plan_instruction(session)


def test_the_todo_event_is_stamped_as_the_agent_s_own():
    session = demo_session("a")
    run_with_crew(session)
    todos = [e for e in session.trace.events if e.kind.value == "todo"]
    assert len(todos) == 1 and todos[0].chosen_by == "model" and len(todos[0].options) == 3


def test_a_run_without_todos_and_the_policy_path_still_work():
    from snapback.agent import PolicyChooser, run_case

    plain = demo_session("a")
    verdict = run_with_crew(plain, todos=False)  # a model that skips the plan
    assert verdict is not None
    assert not [e for e in plain.trace.events if e.kind.value == "todo"]
    assert set(plain.notes) >= set(casework.STEMS)  # the case and its notes still complete
    # A crash would fall back to the policy and still pass the lines above; these would not.
    assert not [e for e in plain.trace.events if e.kind.value == "error"]
    assert all(note.by == "model" for note in plain.notes.values())

    policy = demo_session("a")
    run_case(policy, PolicyChooser(), lambda draft: "send")
    assert not [e for e in policy.trace.events if e.kind.value == "todo"]
    assert policy.verdict == verdict  # same result with or without a plan


def test_the_main_agent_really_has_a_write_todos_tool_and_it_works():
    """deepagents 0.7 adds no planner by itself. Without this the model's write_todos call hit
    'not a valid tool' and the earlier tests still passed on the call alone."""
    session = demo_session("a")
    agent = build_agent(session, FakeCrew(case=session))
    assert "write_todos" in agent.nodes["tools"].bound.tools_by_name
    config = {"configurable": {"thread_id": "todos"}, "recursion_limit": 60}
    agent.invoke({"messages": [("user", "go")]}, config)
    state = agent.get_state(config).values
    assert [t["content"] for t in state["todos"]][0] == "Work the open choices"
    replies = [
        m for m in state["messages"] if isinstance(m, ToolMessage) and m.name == "write_todos"
    ]
    assert replies and all(m.status != "error" for m in replies)
