"""E5: the walk sub-agent picks the tour director's two decisions through its tools; the
director field is what `choose_walk` produces from those picks. Needs the walk builder's
`snapback.tour` (t/walk-it-first) and its test helper; skipped where they are absent."""

import json
import re

import pytest

pytest.importorskip("deepagents")
pytest.importorskip("snapback.tour")
walk_helpers = pytest.importorskip("test_walk_director")

from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from snapback.tour import choose_walk, policy_director  # noqa: E402

from snapback.agent import casework  # noqa: E402
from snapback.agent.graph import build_agent, build_subagents, run_case_with_agent  # noqa: E402
from snapback.agent.walk_agent import WalkDesk  # noqa: E402
from snapback.contracts import ChoiceKind, TraceKind  # noqa: E402
from test_agent_subagents import FakeCrew, _call, demo_session  # noqa: E402


class WalkCrew(FakeCrew):
    """The usual crew, plus a walk sub-agent that picks the LAST option of each decision."""

    pick_last: bool = True

    def _sub(self, messages, system):
        if "walk checker" not in system:
            return super()._sub(messages, system)
        path = re.search(r"path `([^`]+)`", system).group(1)
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        opened = [m for m in tool_msgs if m.name in ("walk_open_choice", "walk_choose_option")]
        if not opened:
            return _call("walk_open_choice")
        state = json.loads(str(opened[-1].content).split("code will decide it. ")[-1])
        if state.get("open_choice"):
            options = state["options"]
            return _call(
                "walk_choose_option",
                option=options[-1] if self.pick_last else options[0],
                reason="The count of hidden rooms is what matters here.",
            )
        if not any(m.name == "write_file" for m in tool_msgs):
            return _call("write_file", file_path=path, content="Rooms to dwell on: S1")
        return AIMessage(content="Note written.")


def walk_session():
    session = demo_session("a")
    session.walk_plan = walk_helpers.walk_plan
    return session


def test_the_walk_sub_agent_exists_only_when_the_case_has_a_walk_plan():
    assert "walk" not in {s["name"] for s in build_subagents(demo_session("a"))}
    spec = next(s for s in build_subagents(walk_session()) if s["name"] == "walk")
    assert [t.name for t in spec["tools"]] == ["walk_open_choice", "walk_choose_option"]


def test_the_desk_refuses_an_off_list_pick_and_the_policy_fills_the_kind():
    desk = WalkDesk(walk_helpers.walk_plan)
    assert desk.choose("dwell on everything", "x") is None
    assert desk.director().stamp == "policy"
    assert desk.director().dwell == policy_director(desk.plan).dwell


def test_a_desk_pick_equals_the_director_choose_walk_makes():
    desk = WalkDesk(walk_helpers.walk_plan)
    offer = desk.offer()
    assert offer is not None and len(offer.options) >= 2
    kind, options, label = desk.choose(offer.options[-1], "because")
    assert kind in (ChoiceKind.DWELL_ROOMS, ChoiceKind.LEAD_CHECKS) and label == offer.options[-1]
    direct = choose_walk(desk.plan, walk_helpers.Pick(len(offer.options) - 1, by="model")).director
    # the first decision, picked the same way, lands on the same stops
    assert getattr(desk.director(), offer.kind if offer.kind == "dwell" else "lead_checks") == (
        direct.dwell if offer.kind == "dwell" else direct.lead_checks
    )


def test_the_walk_chooser_sees_only_counts_and_aliases():
    from snapback.tour import WALK_FACT_KEYS

    offer = WalkDesk(walk_helpers.walk_plan).offer()
    assert set(offer.facts) <= WALK_FACT_KEYS
    blob = json.dumps({"o": offer.options, "a": offer.aliases, "f": offer.facts})
    assert "fx-" not in blob and "sweep" not in blob


def test_a_run_through_the_harness_stamps_the_walk_picks_and_writes_the_note():
    session = walk_session()
    agent = build_agent(
        session, WalkCrew(case=session, agents=[*FakeCrew.model_fields["agents"].default, "walk"])
    )
    verdict = run_case_with_agent(session, agent, lambda d: "send")
    assert verdict is not None
    picks = [
        e
        for e in session.trace.events
        if e.choice in (ChoiceKind.DWELL_ROOMS, ChoiceKind.LEAD_CHECKS)
    ]
    assert picks and all(e.chosen_by == "model" and len(e.options) >= 2 for e in picks)
    assert session.walk_director.stamp == "model"
    assert "walk" in session.notes and session.notes["walk"].by == "model"
    file_events = [
        e for e in session.trace.events if e.kind is TraceKind.FILE and "walk.md" in e.pick
    ]
    assert file_events


def test_a_case_with_a_walk_plan_and_no_model_gets_a_policy_director_and_a_code_note():
    from snapback.agent import PolicyChooser, run_case

    session = walk_session()
    run_case(session, PolicyChooser(), lambda d: "send")
    casework.refresh_policy_notes(session)
    assert session.walk_director.stamp == "policy"
    assert (
        session.notes["walk"].by == "policy" and "Chosen by: policy" in session.notes["walk"].text
    )
