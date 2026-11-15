"""W1: the `web` sub-agent and its note. Code runs the checks; the sub-agent reads what they
found through one tool and may write only its own note. decide() never reads any of it."""

import random
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("deepagents")

from snapback.agent import CaseSession, FixtureModules, PolicyChooser, Trace, casework, run_case  # noqa: E402
from snapback.agent.graph import build_subagents  # noqa: E402
from snapback.agent.web.facts import (  # noqa: E402
    CheckStatus,
    ElsewhereCheck,
    LinkCheck,
    SiteCheck,
    WebFacts,
    WebInputs,
)
from snapback.agent.web.run import start_web_checks  # noqa: E402
from snapback.contracts import DataSource, TraceKind  # noqa: E402
from snapback.settings import Settings  # noqa: E402

FOUND = WebFacts(
    source=DataSource.FIXTURE,
    site=SiteCheck(
        status=CheckStatus.DONE,
        host="oakcourt.example",
        lists_unit=True,
        phone_matches=False,
        ms=900,
    ),
    link=LinkCheck(status=CheckStatus.TIMED_OUT, ms=15000),
    elsewhere=ElsewhereCheck(
        status=CheckStatus.DONE,
        postings=1,
        poster_differs=True,
        nearby=2,
        by_source={"zillow": 2},
        rent_low=1500,
        rent_high=1725,
        ms=4200,
    ),
)


def make_case(case_id: str = "fx-7Q2M") -> CaseSession:
    start = datetime(2026, 11, 13, 21, 41, tzinfo=UTC)
    ticks = iter(start + timedelta(seconds=n) for n in range(10_000))
    trace = Trace(case_id, DataSource.FIXTURE, clock=lambda: next(ticks))
    return CaseSession(case_id, FixtureModules(), trace, rng=random.Random(7))


def test_no_web_checks_means_no_web_sub_agent_and_no_note():
    case = make_case()
    assert "web" not in {s["name"] for s in build_subagents(case)}
    casework.refresh_policy_notes(case)
    assert casework.WEB not in case.notes


def test_the_web_sub_agent_has_one_reading_tool_and_may_write_only_its_note():
    case = make_case()
    case.web_facts = lambda: FOUND
    spec = next(s for s in build_subagents(case) if s["name"] == "web")
    assert [t.name for t in spec["tools"]] == ["read_web_facts"]
    allow, deny = spec["permissions"]
    assert allow.paths == [casework.note_path(case.case_id, casework.WEB)] and allow.mode == "allow"
    assert deny.paths == ["/**"] and deny.mode == "deny"
    text = spec["tools"][0].invoke({})
    assert "lists the ad's plan or unit: yes" in text
    assert "shows the office phone on record: no" in text
    assert "The ad's link (Browser Use): timed_out" in text
    assert (
        "posted elsewhere (Bright Data search): 1 found; one shows a different phone: yes" in text
    )
    assert "Rentals this size nearby (Apify, not the same home): 2, asked rent 1500 to 1725" in text


def test_the_code_note_says_still_running_until_the_checks_finish():
    case = make_case()
    case.web_facts = lambda: None
    casework.refresh_policy_notes(case)
    assert case.notes[casework.WEB].text.endswith("Status: still running")
    case.web_facts = lambda: FOUND
    casework.refresh_policy_notes(case)
    note = case.notes[casework.WEB]
    assert note.by == "policy" and "oakcourt.example" in note.text
    assert "web" in {n.stem for n in casework.notes_view(case).notes}


def test_web_facts_do_not_change_the_verdict():
    plain = make_case()
    run_case(plain, PolicyChooser(), lambda draft: "send")
    with_web = make_case()
    with_web.web_facts = lambda: FOUND
    run_case(with_web, PolicyChooser(), lambda draft: "send")
    assert plain.verdict is not None and with_web.verdict is not None
    assert with_web.verdict.state == plain.verdict.state
    assert with_web.verdict.reasons == plain.verdict.reasons
    assert with_web.evidence == plain.evidence


def test_the_background_job_returns_at_once_and_puts_one_trace_step_per_check():
    trace = Trace("fx-7Q2M", DataSource.FIXTURE)
    conf = Settings(
        _env_file=None, brightdata_api_token=None, apify_token=None, browser_use_api_key=None
    )
    job = start_web_checks(WebInputs(), conf, salt="s", trace=trace, source=DataSource.FIXTURE)
    facts = job.wait(5)
    assert facts is not None and facts.site.status is CheckStatus.NOT_CHECKED
    steps = [
        e for e in trace.events if e.kind is TraceKind.TOOL and (e.pick or "").startswith("web.")
    ]
    assert [e.pick for e in steps] == ["web.site", "web.link", "web.elsewhere"]
    assert all("not checked" in e.reason for e in steps)
