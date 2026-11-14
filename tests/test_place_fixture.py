"""The fixture place searcher: scripted, synthetic and labelled; case a shows a retry that places
a near miss and an honest stop. Opt-in, so the default demo cases are unchanged."""

import json

import pytest

from snapback.agent import PolicyChooser, run_case
from snapback.agent.demo import DEMO_DIR, demo_place_searcher, load_demo_case, run_demo_case
from snapback.agent.place_fixture import FixturePlaceSearcher
from snapback.contracts import LocateStatus, TraceKind


def test_the_script_says_it_is_synthetic_and_refuses_to_load_otherwise():
    script = json.loads((DEMO_DIR / "a" / "place_retry.json").read_text())
    assert script["synthetic"] is True and "Not measured" in script["label"]
    assert FixturePlaceSearcher(script).synthetic
    with pytest.raises(ValueError):
        FixturePlaceSearcher({**script, "synthetic": False})


def test_only_the_cases_with_a_script_have_a_searcher():
    assert demo_place_searcher(load_demo_case("a")) is not None
    assert demo_place_searcher(load_demo_case("b")) is None


def test_case_a_without_the_opt_in_has_no_place_step_at_all():
    from snapback.agent.demo import demo_modules, read_listing
    from snapback.agent.session import CaseSession
    from snapback.agent.trace import Trace
    from snapback.contracts import ChoiceKind, DataSource

    case = load_demo_case("a")
    session = CaseSession(
        "fx-demo-a",
        demo_modules(case, read_listing(case.listing_text)),
        Trace("fx-demo-a", DataSource.FIXTURE),
    )
    run_case(session, PolicyChooser(), lambda draft: "send")
    assert session.place_desk is None and session.place_searcher is None
    assert not [e for e in session.trace.events if e.choice == ChoiceKind.NEXT_SEARCH]
    assert not [e for e in session.trace.events if e.kind is TraceKind.UNSURE]
    assert [p.photo_id for p in session.evidence.locate.photos] == ["l1", "l2", "l3"]


def test_case_a_with_retry_places_the_near_miss_and_stops_honestly():
    from snapback.agent.demo import DemoCase  # noqa: F401  (the demo loader is what we exercise)

    plain, _ = run_demo_case("a")
    verdict, _ = run_demo_case("a", with_retry=True)
    assert verdict.state == plain.state  # the retry adds evidence; the copied reply still decides


def test_the_trace_shows_the_near_miss_the_search_and_who_chose_it():
    from snapback.agent.demo import demo_modules, read_listing
    from snapback.agent.session import CaseSession
    from snapback.agent.trace import Trace
    from snapback.contracts import DataSource

    case = load_demo_case("a")
    session = CaseSession(
        "fx-demo-a",
        demo_modules(case, read_listing(case.listing_text), with_retry=True),
        Trace("fx-demo-a", DataSource.FIXTURE),
    )
    searcher = demo_place_searcher(case)
    session.place_searcher, session.place_scans = searcher, searcher.scans
    run_case(session, PolicyChooser(), lambda draft: "send")

    events = session.trace.events
    unsure = [e for e in events if e.kind is TraceKind.UNSURE]
    assert [e.pick for e in unsure] == ["P4", "P5"]
    assert "24 matched points" in unsure[0].reason
    searches = [e for e in events if (e.pick or "").startswith("search: ")]
    # the placed photos matched in S1, so the policy tries S2 first; once S2 has placed a photo,
    # every scan has been used and the next photo gets the first scan in order
    assert [e.pick for e in searches] == ["search: focus_scan:S2", "search: focus_scan:S1"]
    assert all(e.chosen_by == "policy" for e in searches)
    status = {p.photo_id: p.status for p in session.evidence.locate.photos}
    assert status["l4"] is LocateStatus.LOCATED_IN_CLAIMED  # the near miss placed on retry
    assert status["l5"] is LocateStatus.NOT_LOCATED  # the honest stop: no scripted retry places it
    # the budget was two searches and the desk is closed
    assert session.place_desk.searches_used == 2 and session.place_desk.offer() is None
    # the evidence file keeps the story for the drawer
    file = session.place_desk.evidence_file("fx-demo-a", DataSource.FIXTURE)
    p4 = next(p for p in file.photos if p.alias == "P4")
    assert [(s.option, s.result) for s in p4.searches] == [
        ("base", "not_placed"),
        ("focus_scan:S2", "placed"),
    ]
