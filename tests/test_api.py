"""The HTTP routes the web app and the iMessage sidecar call."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.api.main import app, create_app
from snapback.contracts import Card, DataSource, TraceEvent, TraceKind, VerdictState
from snapback.settings import Settings

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
FIXTURE_CARD = Card.model_validate_json((FIXTURES / "card_hold.json").read_text())
FIXTURE_TRACE = [
    TraceEvent.model_validate(json.loads(line))
    for line in (FIXTURES / "trace_events.jsonl").read_text().strip().splitlines()
]


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(create_app(settings))


def read_sse(response) -> list[dict]:
    """Parse a finished event stream into a list of {id, event, data} blocks."""
    events, block = [], {}
    for line in response.iter_lines():
        if not line:
            if block:
                events.append(block)
            block = {}
        elif not line.startswith(":"):
            field, _, value = line.partition(":")
            block[field] = value.removeprefix(" ")
    if block:
        events.append(block)
    return events


def stream_trace(client: TestClient, case_id: str, last_event_id: str | None = None):
    headers = {"Last-Event-ID": last_event_id} if last_event_id is not None else {}
    with client.stream("GET", f"/cases/{case_id}/trace", headers=headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        return read_sse(response)


def create(client: TestClient, **form) -> dict:
    response = client.post("/cases", data={"listing_text": "Two bed near the park.", **form})
    assert response.status_code == 201, response.text
    return response.json()


# --- what was already there ----------------------------------------------------------------


def test_healthz_reports_the_data_source():
    body = TestClient(app).get("/healthz").json()
    assert body["status"] == "ok"
    assert body["data_source"] in {"live", "fixture"}


def test_verdict_endpoint_round_trips_the_contract():
    payload = {
        "case_id": "case-1",
        "source": "fixture",
        "photos": [{"photo_id": "p1", "status": "located_in_claimed"}],
    }
    response = TestClient(app).post("/verdict", json=payload)
    assert response.status_code == 200
    assert response.json()["state"] == "hold"


# --- the tests named in the task -----------------------------------------------------------


@pytest.mark.parametrize("case_id", ["7Q2M", "fx-7Q2M", "7q2m"])
def test_card_route_returns_card_contract(client, case_id):
    response = client.get(f"/cases/{case_id}/card")
    assert response.status_code == 200
    assert Card.model_validate(response.json()) == FIXTURE_CARD


def test_trace_route_streams_fixture_events_in_order(client):
    events = stream_trace(client, "fx-7Q2M")
    assert [event["event"] for event in events] == ["trace"] * 7
    assert [event["id"] for event in events] == [str(n) for n in range(7)]
    assert [TraceEvent.model_validate_json(event["data"]) for event in events] == FIXTURE_TRACE


def test_trace_resumes_from_last_event_id(client):
    events = stream_trace(client, "fx-7Q2M", last_event_id="3")
    assert [event["id"] for event in events] == ["4", "5", "6"]
    assert stream_trace(client, "fx-7Q2M", last_event_id="6") == []
    # Anything that is not a sequence number means "from the start".
    assert len(stream_trace(client, "fx-7Q2M", last_event_id="not-a-number")) == 7


def test_create_case_rejects_more_than_daily_limit(client):
    for _ in range(3):
        create(client, renter_id="renter-a")
    refused = client.post("/cases", data={"listing_text": "x", "renter_id": "renter-a"})
    assert refused.status_code == 429
    assert "3" in refused.json()["detail"]
    # Someone else's limit is their own.
    create(client, renter_id="renter-b")


# --- a case from start to finish, in fixture mode ------------------------------------------


def test_a_new_case_pauses_for_the_renters_approval(client):
    case = create(client)
    assert case["source"] == "fixture"
    assert case["status"] == "waiting_for_approval"
    assert case["state"] is None
    challenge = case["challenge"]
    assert challenge["code"] in challenge["text"]
    assert challenge["spot_label"] in challenge["text"]

    again = client.get(f"/cases/{case['case_id']}").json()
    assert again == case


def test_approving_sends_the_challenge_and_finishes_the_case(client):
    case_id = create(client)["case_id"]
    done = client.post(f"/cases/{case_id}/challenge/approve", json={"decision": "send"})
    assert done.status_code == 200
    body = done.json()
    assert body["status"] == "done"
    assert body["state"] == "hold"
    assert body["challenge"] is None

    card = Card.model_validate(client.get(f"/cases/{case_id}/card").json())
    assert card.state is VerdictState.HOLD
    assert card.case_id == case_id
    assert card.source is DataSource.FIXTURE
    assert card.verify_url == f"http://localhost:5173/c/{case_id}"

    events = [TraceEvent.model_validate_json(e["data"]) for e in stream_trace(client, case_id)]
    assert [e.seq for e in events] == list(range(len(events)))
    assert events[-1].kind is TraceKind.VERDICT
    assert any(e.kind is TraceKind.HITL and e.pick == "send" for e in events)


def test_cancel_finishes_the_case_without_a_challenge(client):
    case_id = create(client)["case_id"]
    body = client.post(f"/cases/{case_id}/challenge/approve", json={"decision": "cancel"}).json()
    assert body["status"] == "done"
    card = Card.model_validate(client.get(f"/cases/{case_id}/card").json())
    here_now = card.rows[1].lines[0]
    assert here_now.tone == "not_checked"


def test_edit_carries_the_renters_own_wording(client):
    case_id = create(client)["case_id"]
    response = client.post(
        f"/cases/{case_id}/challenge/approve",
        json={"decision": "edit", "text": "Please send the closet door with the code on paper."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "done"


def test_the_card_is_available_before_the_case_is_done(client):
    case_id = create(client)["case_id"]
    card = Card.model_validate(client.get(f"/cases/{case_id}/card").json())
    assert card.rows[0].lines[0].tone == "ok"  # the photos were placed
    assert card.rows[1].lines[0].tone == "not_checked"  # nobody has been asked yet


@pytest.mark.parametrize(
    "listing_text",
    ["Cozy studio, $120 per night: https://www.airbnb.com/rooms/1", "Office space for lease, NNN."],
)
def test_a_short_term_or_commercial_listing_is_not_checked(client, listing_text):
    case = create(client, listing_text=listing_text)
    assert case["status"] == "done"
    assert case["state"] == "unverified"
    assert case["challenge"] is None
    kinds = [json.loads(e["data"])["kind"] for e in stream_trace(client, case["case_id"])]
    assert kinds == ["choice", "verdict"]


def test_case_ids_are_short_and_differ(client):
    ids = {create(client, renter_id=f"renter-{n}")["case_id"] for n in range(5)}
    assert len(ids) == 5
    assert all(len(case_id) == 4 and case_id.isalnum() for case_id in ids)


def test_photos_are_counted(client):
    files = [("photos", (f"p{n}.jpg", b"\xff\xd8\xff fake jpeg", "image/jpeg")) for n in range(3)]
    response = client.post("/cases", data={"listing_text": "x"}, files=files)
    assert response.status_code == 201
    assert response.json()["photos"] == 3


def test_too_many_photos_are_refused(client):
    files = [("photos", (f"p{n}.jpg", b"x", "image/jpeg")) for n in range(21)]
    response = client.post("/cases", data={"listing_text": "x"}, files=files)
    assert response.status_code == 413


# --- errors --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/cases/ZZZZ"),
        ("GET", "/cases/ZZZZ/card"),
        ("GET", "/cases/ZZZZ/trace"),
        ("POST", "/cases/ZZZZ/challenge/approve"),
    ],
)
def test_an_unknown_case_is_404(client, method, path):
    response = client.request(method, path, json={"decision": "send"})
    assert response.status_code == 404


def test_approving_when_nothing_is_waiting_is_409(client):
    case_id = create(client)["case_id"]
    client.post(f"/cases/{case_id}/challenge/approve", json={"decision": "send"})
    again = client.post(f"/cases/{case_id}/challenge/approve", json={"decision": "send"})
    assert again.status_code == 409
    # The recorded fixture case is finished too.
    recorded = client.post("/cases/fx-7Q2M/challenge/approve", json={"decision": "send"})
    assert recorded.status_code == 409


@pytest.mark.parametrize("decision", ["approve", "yes", "", "mark verified"])
def test_only_send_edit_or_cancel_are_accepted(client, decision):
    case_id = create(client)["case_id"]
    response = client.post(f"/cases/{case_id}/challenge/approve", json={"decision": decision})
    assert response.status_code == 422
    assert client.get(f"/cases/{case_id}").json()["status"] == "waiting_for_approval"


def test_live_mode_says_plainly_that_the_modules_are_not_wired(tmp_path):
    settings = Settings(_env_file=None, snapback_data_source="live", snapback_data_dir=tmp_path)
    live = TestClient(create_app(settings))
    assert live.get("/healthz").json()["data_source"] == "live"
    response = live.post("/cases", data={"listing_text": "x"})
    assert response.status_code == 503
    # Fixture cases are not served as if they were live.
    assert live.get("/cases/fx-7Q2M/card").status_code == 404


def test_the_route_list_is_what_the_other_lanes_were_told():
    paths = {
        (method, route.path) for route in app.routes for method in getattr(route, "methods", [])
    }
    for expected in [
        ("POST", "/cases"),
        ("GET", "/cases/{case_id}"),
        ("GET", "/cases/{case_id}/card"),
        ("GET", "/cases/{case_id}/trace"),
        ("POST", "/cases/{case_id}/challenge/approve"),
        ("GET", "/healthz"),
    ]:
        assert expected in paths
