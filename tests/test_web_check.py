"""W1 (#11, Vidyut 20:05): the web sub-agent's three checks, on recorded pages and searches only.

No network in CI: every test reads a recorded fixture through `RecordedFetcher`, or a fake.
"""

import json
import time
from pathlib import Path

from snapback.agent.rules.contact import phone_hash
from snapback.agent.web_check import (
    RecordedFetcher,
    WebInputs,
    run_web_checks,
    web_facts_text,
)

SALT = "fx-salt"
OFFICE = "713-555-0100"  # a 555 number: never real
FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "web" / "recorded.json"


def inputs(**over) -> WebInputs:
    base = dict(
        website_host="oakcourt.example",
        site_phone_hash=phone_hash(OFFICE, SALT),
        salt=SALT,
        building_name="Oak Court",
        ad_hosts=["oakcourrt.example"],
        ad_text=(
            "Spacious 2 bed 2 bath at Oak Court with a balcony and a pool. "
            "Send the deposit by Zelle before the tour. $1,150 a month."
        ),
        ad_rent=1150,
        ad_beds=2,
    )
    base.update(over)
    return WebInputs(**base)


def by_check(report):
    return {line.check: line for line in report.lines}


# --- 1. the building's own site -----------------------------------------------------------------


def test_the_building_site_lists_the_plan_and_the_office_phone():
    report = run_web_checks(inputs(), RecordedFetcher(FIXTURE))
    site = by_check(report)["building_site"]
    assert site.status == "matches"
    assert "2 bed" in site.text
    assert "office number on record: yes" in site.text
    assert site.source == "live"


def test_the_office_phone_is_yes_or_no_only_and_its_digits_never_appear():
    other = inputs(site_phone_hash=phone_hash("713-555-0199", SALT))
    report = run_web_checks(other, RecordedFetcher(FIXTURE))
    text = " ".join(line.text for line in report.lines)
    assert "office number on record: no" in by_check(report)["building_site"].text
    assert "555" not in text and "0100" not in text


def test_no_website_on_record_is_not_checked():
    site = by_check(run_web_checks(inputs(website_host=None), RecordedFetcher(FIXTURE)))
    assert site["building_site"].status == "not_checked"


# --- 2. the ad's link --------------------------------------------------------------------------


def test_a_lookalike_link_using_the_building_name_is_caught():
    link = by_check(run_web_checks(inputs(), RecordedFetcher(FIXTURE)))["ad_link"]
    assert link.status == "doesnt_match"
    assert "oakcourrt.example" in link.text
    assert "different site" in link.text


def test_the_buildings_own_link_matches():
    own = inputs(ad_hosts=["oakcourt.example"])
    assert by_check(run_web_checks(own, RecordedFetcher(FIXTURE)))["ad_link"].status == "matches"


def test_facebook_marketplace_is_never_opened():
    seen: list[str] = []

    class Spy(RecordedFetcher):
        def page(self, url: str) -> str | None:
            seen.append(url)
            return super().page(url)

    fb = inputs(ad_hosts=["facebook.com", "www.facebook.com", "m.facebook.com"])
    link = by_check(run_web_checks(fb, Spy(FIXTURE)))["ad_link"]
    assert not [u for u in seen if "facebook" in u]
    assert link.status == "not_checked"


# --- 3. the same home elsewhere -------------------------------------------------------------------


def test_the_same_wording_elsewhere_is_counted_never_named():
    report = run_web_checks(inputs(), RecordedFetcher(FIXTURE))
    elsewhere = by_check(report)["elsewhere"]
    assert elsewhere.status == "doesnt_match"
    assert "3 other listings" in elsewhere.text
    assert "2 at a different price" in elsewhere.text
    # counts only: no host, poster, title or link from the results
    recorded = json.loads(FIXTURE.read_text())
    for results in recorded["searches"].values():
        for hit in results:
            assert hit["url"] not in elsewhere.text
            assert hit["title"] not in elsewhere.text


def test_no_copies_found_reads_as_such():
    quiet = inputs(ad_text="A quiet 1 bed with a garden view and parking near the park.")
    elsewhere = by_check(run_web_checks(quiet, RecordedFetcher(FIXTURE)))["elsewhere"]
    assert elsewhere.status == "matches"
    assert "No other listing" in elsewhere.text


# --- the rules ---------------------------------------------------------------------------------


def test_a_slow_web_never_holds_the_case_past_the_time_limit():
    class Slow(RecordedFetcher):
        def page(self, url: str) -> str | None:
            time.sleep(2)
            return super().page(url)

    start = time.monotonic()
    report = run_web_checks(inputs(), Slow(FIXTURE), budget_s=0.3)
    assert time.monotonic() - start < 1.5
    assert by_check(report)["building_site"].status == "not_checked"
    assert "time limit" in by_check(report)["building_site"].text


def test_a_broken_fetch_is_not_checked_never_an_error():
    class Broken(RecordedFetcher):
        def page(self, url: str) -> str | None:
            raise ConnectionError("down")

        def search(self, query: str) -> list[dict]:
            raise ConnectionError("down")

    report = run_web_checks(inputs(), Broken(FIXTURE))
    assert {line.status for line in report.lines} == {"not_checked"}


def test_the_lines_reach_the_trace_as_they_finish():
    seen: list[str] = []
    run_web_checks(inputs(), RecordedFetcher(FIXTURE), on_line=lambda line: seen.append(line.check))
    assert sorted(seen) == ["ad_link", "building_site", "elsewhere"]


def test_the_sub_agent_reads_one_text_block_of_facts_with_their_source():
    text = web_facts_text(run_web_checks(inputs(), RecordedFetcher(FIXTURE)))
    assert text.count("(LIVE, web)") == 3
    assert "555" not in text


# --- wiring: the sub-agent, the trace and the API ----------------------------------------------


def test_the_web_sub_agent_exists_only_when_a_web_key_is_set():
    import pytest

    pytest.importorskip("deepagents")
    import random

    from snapback.agent.graph import build_subagents
    from snapback.agent.modules import FixtureModules
    from snapback.agent.session import CaseSession
    from snapback.agent.trace import Trace
    from snapback.contracts import DataSource

    case = CaseSession(
        "fx-W1", FixtureModules(), Trace("fx-W1", DataSource.FIXTURE), rng=random.Random(1)
    )
    assert "web" not in {s["name"] for s in build_subagents(case)}
    case.web_facts = lambda: "building_site: matches: fx (LIVE, web)"
    spec = next(s for s in build_subagents(case) if s["name"] == "web")
    assert [t.name for t in spec["tools"]] == ["read_web_facts"]
    assert spec["tools"][0].invoke({}) == "building_site: matches: fx (LIVE, web)"
    # it may write only its own note
    assert any("/case/fx-W1/web.md" in p.paths for p in spec["permissions"])


def test_the_api_starts_no_web_job_without_a_key(monkeypatch):
    from snapback.agent.web_check import BrightDataFetcher

    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    assert BrightDataFetcher().configured is False


def test_a_web_job_puts_each_line_in_the_trace_and_the_sub_agent_reads_them():
    import random

    from snapback.agent.modules import FixtureModules
    from snapback.agent.session import CaseSession
    from snapback.agent.trace import Trace
    from snapback.agent.web_check import WebJob
    from snapback.contracts import DataSource, TraceKind

    session = CaseSession(
        "fx-W2", FixtureModules(), Trace("fx-W2", DataSource.FIXTURE), rng=random.Random(1)
    )
    job = WebJob(
        inputs(),
        RecordedFetcher(FIXTURE),
        on_line=lambda line: session.trace.emit(TraceKind.TOOL, line.text, pick="web"),
    )
    text = job.start().text()
    web = [e for e in session.trace.events if e.pick == "web"]
    assert len(web) == 3
    assert text.count("(LIVE, web)") == 3
    assert "555" not in " ".join(e.reason for e in web)
