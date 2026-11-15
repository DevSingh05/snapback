"""The trace cards: what each member of the deep agent was asked, the tools it called in order,
what it said back, how long it took and how many model calls it made, on GET /cases/{id}/timeline.

Read from the real deepagents graph through its callbacks, on a scripted model. Everything a
model wrote is cleaned: no phone number, address, rent figure or result word reaches a card.
With the policy no model runs, so there are no member cards at all.
"""

import json
import re
import time

import pytest

pytest.importorskip("deepagents")

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from snapback.agent import worklog  # noqa: E402
from snapback.agent.join import KitLookups  # noqa: E402
from snapback.agent.worklog import AgentWork, member_traces  # noqa: E402
from snapback.api.main import create_app  # noqa: E402
from snapback.contracts import DataSource  # noqa: E402
from snapback.settings import Settings  # noqa: E402
from test_agent_live import FAMILIES, Crew, make_client, read, start  # noqa: E402

PHONE = re.compile(r"\d{3}\D{0,2}\d{3}\D?\d{4}")
MONEY = re.compile(r"\$\s?\d")
DIGITS = re.compile(r"\d{3,}")


def finished(client, case) -> dict:
    for _ in range(150):
        timeline = read(client, case)
        if not timeline["running"]:
            return timeline
        time.sleep(0.1)
    raise AssertionError("the agent did not finish")


def policy_client(tmp_path, **settings) -> TestClient:
    s = Settings(_env_file=None, snapback_data_dir=tmp_path, anthropic_api_key=None, **settings)
    return TestClient(create_app(s, lookups=KitLookups(DataSource.FIXTURE)))


def by_kind(timeline: dict) -> dict[str, dict]:
    return {m["kind"]: m for m in timeline["members"]}


def test_each_member_has_a_card_with_what_it_was_asked_did_and_said(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch, lambda: Crew())
    timeline = finished(client, start(client))
    assert timeline["mode"] == "deepagents"
    kinds = [m["kind"] for m in timeline["members"]]
    assert kinds[0] == "planner"
    assert set(kinds[1:]) == set(FAMILIES)
    cards = by_kind(timeline)

    record = cards["record"]
    assert record["model"] == "Claude Haiku"  # the background agent's sub-agents: the small one
    assert record["asked"] == "Write the record note."
    assert [t["tool"] for t in record["tools"]] == ["read_record_facts", "write_file"]
    assert all(t["label"] and t["result"] for t in record["tools"])
    assert "CoStar" in record["tools"][0]["label"]
    assert record["said"] == "Note written."
    assert record["model_calls"] == 3  # read the facts, write the note, reply
    assert record["took_ms"] is not None and record["took_ms"] >= 0

    planner = cards["planner"]
    assert planner["model"] == "Claude Sonnet"
    assert planner["asked"] is None
    tools = [t["tool"] for t in planner["tools"]]
    assert tools[0] == "write_todos"
    assert tools.count("task") == len(FAMILIES)
    assert tools.count("write_file") == 2
    assert planner["model_calls"] == 5
    # A hand-off reads as a hand-off, naming the member.
    handed = [t["label"] for t in planner["tools"] if t["tool"] == "task"]
    assert "Handed work to: Record agent" in handed
    assert "Handed work to: Phone and office agent" in handed


class Loose(Crew):
    """A model that writes a phone number, a rent, an address and a result word into its text."""

    def _main(self, messages):
        reply = super()._main(messages)
        for tc in reply.tool_calls:
            if tc["name"] == "task":
                tc["args"]["description"] = (
                    f"Check {tc['args']['subagent_type']}: call 713-555-0142 about the "
                    "$1,500 unit at 1200 Main Street, rent 1500."
                )
        return reply

    def _sub(self, messages, system):
        reply = super()._sub(messages, system)
        if not reply.tool_calls:
            return AIMessage(
                content=(
                    "Done. Do not pay 713-555-0142; rent is $1,500 at 1200 Main Street, id 1234567."
                )
            )
        return reply


def test_nothing_a_model_wrote_leaks_a_phone_a_rent_an_address_or_a_result(
    tmp_path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch, lambda: Loose())
    timeline = finished(client, start(client))
    text = json.dumps(timeline["members"], ensure_ascii=False)
    assert len(timeline["members"]) == 1 + len(FAMILIES)
    assert not PHONE.search(text), text
    assert not MONEY.search(text)
    assert not DIGITS.search(text), DIGITS.search(text).string[DIGITS.search(text).start() - 80 :][
        :160
    ]
    assert "Main Street" not in text
    assert "do not pay" not in text.lower()
    # The card still says something plain in its place.
    assert by_kind(timeline)["owner"]["said"]
    assert by_kind(timeline)["owner"]["asked"]


def test_with_the_policy_there_are_no_member_cards(tmp_path, monkeypatch) -> None:
    client = policy_client(tmp_path)
    timeline = read(client, start(client))
    assert timeline["mode"] == "policy"
    assert timeline["members"] == []
    assert timeline["trace_url"] is None


def test_the_langsmith_link_shows_only_for_an_agent_run_and_never_carries_a_token(
    tmp_path, monkeypatch
) -> None:
    url = "https://smith.langchain.com/o/team/projects/p/snapback"
    client = make_client(tmp_path, monkeypatch, lambda: Crew(), snapback_langsmith_url=url)
    assert finished(client, start(client))["trace_url"] == url
    policy = policy_client(tmp_path, snapback_langsmith_url=url)
    assert read(policy, start(policy))["trace_url"] is None
    for bad in (
        "https://smith.langchain.com/o/team?api_key=lsv2_abc",
        "https://smith.langchain.com/o/team#token=abc",
        "http://smith.langchain.com/o/team",
        "https://example.com/o/team",
        "https://user:pass@smith.langchain.com/o/team",
    ):
        assert Settings(_env_file=None, snapback_langsmith_url=bad).snapback_langsmith_url is None


def test_the_work_log_counts_and_orders_what_it_sees() -> None:
    work = AgentWork()
    work.model_call(None)
    work.tool_start("r1", None, "task", {"subagent_type": "record", "description": "Read it."})
    work.model_call("record")
    work.tool_start("r2", "record", "read_record_facts", {})
    work.tool_end("r2", "Source: CoStar record (fixture)\nRent check: not_checked\nPer bed: False")
    work.model_call("record")
    work.tool_end("r1", "The record is in.")
    cards = member_traces(work, {"planner": "Claude Sonnet", "sub": "Claude Haiku", "code": "code"})
    assert [c.kind for c in cards] == ["planner", "record"]
    assert cards[1].asked == "Read it."
    assert cards[1].said == "The record is in."
    assert cards[1].model_calls == 2
    # The source line is the label's, and code's statuses read as words.
    assert cards[1].tools[0].result == "Rent check: not checked; Per bed: no"
    assert cards[0].tools[0].tool == "task"
    # A tool nobody named still reads as plain words, never as a function name alone.
    assert worklog.tool_label("some_new_tool", {}, "en") != "some_new_tool"
    assert member_traces(AgentWork(), {"planner": "x", "sub": "y", "code": "code"}) == []
