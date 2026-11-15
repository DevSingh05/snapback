"""GET /cases/{id}/timeline: what the agent did, step by step, built from the case's trace.

The read token goes in a header only, the answer is never cached, the steps are in the order
they happened, and no label or result carries a phone number, an address or a rent.
"""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from snapback.agent.join import KitLookups
from snapback.agent.timeline import build_timeline
from snapback.api.main import create_app
from snapback.contracts import (
    ChoiceKind,
    DataSource,
    LocateResult,
    LocateStatus,
    ModuleEvidence,
    PhotoLocation,
    PriceResult,
    PriceStatus,
    TraceEvent,
    TraceKind,
)
from snapback.settings import Settings

PHONE = re.compile(r"\d{3}\D{0,2}\d{3}\D?\d{4}")
RENT = re.compile(r"\$\s?\d")
ADDRESS = re.compile(r"\b\d{2,6}\s+[A-Z][a-z]+\s+(St|Street|Ave|Avenue|Rd|Road|Blvd|Dr|Lane|Ln)\b")


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))


def new_case(client):
    made = client.post(
        "/cases", data={"text": "Nice 1 bed, $1,500 a month. Call 713-555-0101, 1200 Main Street"}
    )
    assert made.status_code == 201
    return made.json()


def read(case):
    return {"Authorization": f"Bearer {case['read_token']}"}


START = datetime(2026, 11, 14, 21, 0, tzinfo=UTC)


def ev(seq, ms, kind, reason="", **kw) -> TraceEvent:
    return TraceEvent(
        case_id="c1",
        seq=seq,
        at=START + timedelta(milliseconds=ms),
        kind=kind,
        reason=reason,
        source=DataSource.FIXTURE,
        **kw,
    )


def evidence(**kw) -> ModuleEvidence:
    return ModuleEvidence(case_id="c1", source=DataSource.FIXTURE, **kw)


def placed(n_in: int, n_all: int) -> LocateResult:
    photos = [
        PhotoLocation(
            photo_id=f"p{i}",
            status=LocateStatus.LOCATED_IN_CLAIMED if i < n_in else LocateStatus.NOT_LOCATED,
        )
        for i in range(n_all)
    ]
    return LocateResult(case_id="c1", photos=photos, thresholds_version="t")


# --- the route -----------------------------------------------------------------------------------


def test_timeline_needs_the_read_token_in_a_header_and_is_never_cached(client):
    case = new_case(client)
    url = f"/cases/{case['case_id']}/timeline"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer nope"}).status_code == 403
    assert client.get(f"{url}?token={case['read_token']}", headers=read(case)).status_code == 401
    r = client.get(url, headers=read(case))
    assert r.status_code == 200
    assert r.headers["cache-control"] == "private, no-store"
    body = r.json()
    assert body["case_id"] == case["case_id"]
    assert body["mode"] == "policy" and body["fell_back"] is False
    assert body["todos"] == [] and body["plan"] == []
    steps = body["steps"]
    assert steps[0]["label"] == "Read the ad"
    assert [s["step"] for s in steps] == list(range(len(steps)))
    assert {s["by"] for s in steps} <= {"agent", "code"}
    assert {s["source"] for s in steps} == {"fixture"}
    labels = [s["label"] for s in steps]
    assert any(label.startswith("Placed ") and "3D scan" in label for label in labels)


def test_timeline_route_speaks_spanish(client):
    case = new_case(client)
    r = client.get(f"/cases/{case['case_id']}/timeline?lang=es", headers=read(case))
    assert r.status_code == 200
    assert r.json()["steps"][0]["label"] == "Leyó el anuncio"


def test_timeline_route_is_404_for_an_unknown_case(client):
    r = client.get("/cases/ZZZZ/timeline", headers={"Authorization": "Bearer x"})
    assert r.status_code == 404


def test_the_routes_labels_and_results_carry_no_phone_address_or_rent(client):
    case = new_case(client)
    for lang in ("en", "es"):
        r = client.get(f"/cases/{case['case_id']}/timeline?lang={lang}", headers=read(case))
        for step in r.json()["steps"]:
            for text in (step["label"], step["result"]):
                assert not PHONE.search(text), text
                assert not RENT.search(text), text
                assert not ADDRESS.search(text), text


# --- the builder ---------------------------------------------------------------------------------


def test_steps_follow_the_trace_order_with_their_timings():
    events = [
        ev(0, 0, TraceKind.CHOICE, "Has a twin.", choice=ChoiceKind.WHICH_CHECKS, pick="x"),
        ev(1, 40, TraceKind.TOOL, "Placing 3 listing photos in the twin.", pick="locate"),
        ev(2, 340, TraceKind.CHOICE, "Only one.", choice=ChoiceKind.NEXT_CHECK, pick="home record"),
        ev(3, 900, TraceKind.CHOICE, "Plan A.", choice=ChoiceKind.WHICH_FLOOR_PLAN, pick="2 bed"),
        ev(4, 1000, TraceKind.VERDICT, "Hold.", pick="hold"),
    ]
    ev_ = evidence(
        locate=placed(3, 3),
        price=PriceResult(status=PriceStatus.WITHIN_RANGE, listed_rent=1450, n_floor_plans=37),
    )
    tl = build_timeline("c1", DataSource.FIXTURE, events, ev_)
    labels = [s.label for s in tl.steps]
    assert labels == [
        "Read the ad",
        "Chose which checks to run",
        "Placed 3 of 3 photos in its 3D scan",
        "Found the building on CoStar's record",
        "Compared the rent with 37 floor plans",
        "Matched the photos to a floor plan",
        "Code worked out the result",
    ]
    starts = [s.started_ms for s in tl.steps]
    assert starts == sorted(starts)
    locate = tl.steps[2]
    assert (locate.started_ms, locate.took_ms) == (40, 300)
    assert tl.steps[-1].by == "code" and tl.steps[-1].took_ms == 0
    assert all(s.by == "code" for s in tl.steps)  # the policy made every pick


def test_no_label_or_result_carries_a_phone_an_address_or_a_rent():
    dirty = "Call 713-555-0101 or (281) 555 0199 at 1200 Main Street, $1,450 a month"
    events = [
        ev(0, 0, TraceKind.CHOICE, dirty, choice=ChoiceKind.WHICH_CHECKS, pick=dirty),
        ev(1, 5, TraceKind.STATUS, f"Skipped listing brokerage: {dirty}", pick="listing brokerage"),
        ev(2, 9, TraceKind.TODO, "plan", options=[f"[ ] {dirty}"], chosen_by="model"),
        ev(3, 12, TraceKind.VERDICT, dirty, pick="hold"),
    ]
    tl = build_timeline("c1", DataSource.FIXTURE, events, evidence())
    texts = [t for s in tl.steps for t in (s.label, s.result)]
    texts += [t.content for t in tl.todos]
    for text in texts:
        assert not PHONE.search(text), text
        assert not RENT.search(text), text
        assert not ADDRESS.search(text), text
        assert "555" not in text and "1,450" not in text and "Main Street" not in text


def test_a_deep_agent_run_shows_its_plan_its_sub_agents_and_who_did_what():
    events = [
        ev(
            0,
            0,
            TraceKind.TODO,
            "plan",
            options=["[ ] Work the open choices", "[ ] Hand the record checks to the record"],
            chosen_by="model",
        ),
        ev(
            1,
            10,
            TraceKind.CHOICE,
            "Twin first.",
            choice=ChoiceKind.WHICH_CHECKS,
            pick="x",
            chosen_by="model",
        ),
        ev(2, 20, TraceKind.AGENT, "handed", pick="sub-agent: record", chosen_by="model"),
        ev(3, 820, TraceKind.AGENT, "back", pick="sub-agent done: record", chosen_by="model"),
        ev(
            4,
            830,
            TraceKind.TODO,
            "plan",
            options=["[x] Work the open choices", "[x] Hand the record checks to the record"],
            chosen_by="model",
        ),
        ev(5, 900, TraceKind.VERDICT, "Hold.", pick="hold"),
    ]
    tl = build_timeline("c1", DataSource.LIVE, events, evidence())
    assert tl.mode == "deepagents" and tl.fell_back is False
    assert [(t.content, t.done) for t in tl.todos] == [
        ("Work the open choices", True),
        ("Hand the record checks to the record", True),
    ]
    assert tl.plan == ["record"]
    handoff = next(s for s in tl.steps if s.label == "Handed the record checks to a sub-agent")
    assert (handoff.by, handoff.took_ms) == ("agent", 800)  # delegate to return, one step
    choice = next(s for s in tl.steps if s.label == "Chose which checks to run")
    assert choice.by == "agent"
    assert tl.steps[-1].by == "code"  # the result is always code's
    assert {s.source for s in tl.steps} == {DataSource.LIVE}


def test_a_fallback_is_shown_as_its_own_step():
    events = [
        ev(0, 0, TraceKind.TODO, "plan", options=["[ ] Work"], chosen_by="model"),
        ev(1, 3000, TraceKind.ERROR, "The agent ran out of time, so code finished the checks."),
        ev(2, 3001, TraceKind.CHOICE, "x", choice=ChoiceKind.WHICH_CHECKS, pick="x"),
        ev(3, 3002, TraceKind.VERDICT, "Hold.", pick="hold"),
    ]
    tl = build_timeline("c1", DataSource.FIXTURE, events, evidence())
    assert tl.mode == "deepagents" and tl.fell_back is True
    stop = next(s for s in tl.steps if s.label == "The agent stopped, so code finished the checks")
    assert stop.by == "code"
    assert "ran out of time" in stop.result


BARE = [
    "Check rent 1450 against the record's 1,900 floor plan",
    "1200 Post Oak, unit 4B",
    "deposit 900",
]


def test_model_written_todos_and_reasons_lose_every_bare_number():
    events = [
        ev(0, 0, TraceKind.TODO, "plan", options=[f"[ ] {t}" for t in BARE], chosen_by="model"),
        *(
            ev(
                1 + i,
                10 + i,
                TraceKind.CHOICE,
                t,
                choice=ChoiceKind.WHICH_CHECKS,
                pick="x",
                chosen_by="model",
            )
            for i, t in enumerate(BARE)
        ),
    ]
    tl = build_timeline("c1", DataSource.FIXTURE, events, evidence())
    texts = [t.content for t in tl.todos] + [s.result for s in tl.steps if s.by == "agent"]
    assert len(texts) >= 6
    for text in texts:
        assert not re.search(r"\d[\d,]{2,}", text), text
        for gone in ("1450", "1,900", "1200", "900"):
            assert gone not in text, text


def test_code_written_counts_are_kept():
    events = [
        ev(
            0,
            0,
            TraceKind.CHOICE,
            "Plan A: 457 inliers vs 9.",
            choice=ChoiceKind.WHICH_FLOOR_PLAN,
            pick="p",
        )
    ]
    tl = build_timeline("c1", DataSource.FIXTURE, events, evidence())
    assert tl.steps[1].result == "Plan A: 457 inliers vs 9."


def test_record_rent_and_phone_steps_carry_the_records_own_source():
    from snapback.contracts import AuthorityResult, AuthorityStatus, PhoneMatch

    events = [
        ev(0, 0, TraceKind.CHOICE, "x", choice=ChoiceKind.NEXT_CHECK, pick="home record"),
        ev(1, 5, TraceKind.VERDICT, "Hold.", pick="hold"),
    ]
    ev_ = evidence(
        price=PriceResult(status=PriceStatus.WITHIN_RANGE, n_floor_plans=37),
        authority=AuthorityResult(
            status=list(AuthorityStatus)[0], office_phone_match=PhoneMatch.YES
        ),
        record_source=DataSource.LIVE,
    )
    tl = build_timeline("c1", DataSource.FIXTURE, events, ev_)
    by_label = {s.label: s.source for s in tl.steps}
    assert by_label["Found the building on CoStar's record"] is DataSource.LIVE
    assert by_label["Compared the rent with 37 floor plans"] is DataSource.LIVE
    assert by_label["Checked the phone against the leasing office"] is DataSource.LIVE
    assert by_label["Read the ad"] is DataSource.FIXTURE
    assert by_label["Code worked out the result"] is DataSource.FIXTURE


def test_each_check_step_names_its_module_so_a_page_can_link_a_reason_to_it():
    events = [
        ev(0, 0, TraceKind.CHOICE, "Has a twin.", choice=ChoiceKind.WHICH_CHECKS, pick="x"),
        ev(1, 40, TraceKind.TOOL, "Placing 3 listing photos in the twin.", pick="locate"),
        ev(2, 340, TraceKind.CHOICE, "Only one.", choice=ChoiceKind.NEXT_CHECK, pick="home record"),
        ev(
            3, 500, TraceKind.CHOICE, "Owner.", choice=ChoiceKind.NEXT_CHECK, pick="owner of record"
        ),
        ev(4, 600, TraceKind.AGENT, "handed", pick="sub-agent: place", chosen_by="model"),
        ev(5, 1000, TraceKind.VERDICT, "Hold.", pick="hold"),
    ]
    ev_ = evidence(
        locate=placed(3, 3),
        price=PriceResult(status=PriceStatus.WITHIN_RANGE, listed_rent=1450, n_floor_plans=37),
    )
    tl = build_timeline("c1", DataSource.FIXTURE, events, ev_)
    kinds = [(s.kind) for s in tl.steps]
    assert kinds == [None, None, "locate", "record", "rent", "owner", "place", None]


def test_a_skipped_check_is_marked_and_a_run_check_is_not():
    events = [
        ev(
            0,
            0,
            TraceKind.STATUS,
            "Skipped owner of record: none on record.",
            pick="owner of record",
        ),
        ev(1, 50, TraceKind.CHOICE, "Only one.", choice=ChoiceKind.NEXT_CHECK, pick="home record"),
    ]
    tl = build_timeline("c1", DataSource.FIXTURE, events, evidence())
    owner = next(s for s in tl.steps if s.kind == "owner")
    record = next(s for s in tl.steps if s.kind == "record")
    assert owner.skipped is True and record.skipped is False
