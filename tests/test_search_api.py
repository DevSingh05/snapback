"""POST /search, GET /cases/{id}/alternatives, POST /cases/{id}/tour-draft (council 4 core)."""

import re

import pytest
from fastapi.testclient import TestClient

from snapback.agent.join import KitLookups
from snapback.api.main import create_app
from snapback.contracts import DataSource
from snapback.settings import Settings

PHONE = re.compile(r"\+?\d[\d\s().\-]{8,}\d")


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))


def new_case(client):
    made = client.post("/cases", data={"text": "Nice 1 bed, $1,500 a month, pets ok"})
    assert made.status_code == 201
    return made.json()


def test_search_returns_labelled_matches_and_counts(client):
    response = client.post("/search", json={"max_rent_month": 1800, "beds_min": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fixture" and body["as_of"] == "as of CoStar's last research"
    assert body["n_considered"] >= body["n_matches"] >= len(body["matches"]) > 0
    assert {m["source"] for m in body["matches"]} == {"fixture"}
    assert all(m["price_text"].endswith("as of CoStar's last research") for m in body["matches"])
    assert all("available now" not in m["availability_text"].lower() for m in body["matches"])


def test_search_is_deterministic_and_validates_the_brief(client):
    first = client.post("/search", json={"max_rent_month": 1800}).json()
    assert client.post("/search", json={"max_rent_month": 1800}).json() == first
    assert client.post("/search", json={"max_rent_month": -5}).status_code == 422
    assert client.post("/search", json={"max_results": 500}).status_code == 422
    assert client.post("/search", json={}).status_code == 200


def test_alternatives_need_the_read_token_in_a_header_and_refuse_one_in_the_address(client):
    case = new_case(client)
    url = f"/cases/{case['case_id']}/alternatives"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer nope"}).status_code == 403
    assert client.get(f"{url}?token={case['read_token']}").status_code == 401
    ok = client.get(url, headers={"Authorization": f"Bearer {case['read_token']}"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["source"] == "fixture" and body["case_id"] == case["case_id"]
    assert len(body["matches"]) <= 3


def test_tour_draft_needs_the_write_token_and_the_read_token_cannot_write(client):
    case = new_case(client)
    url = f"/cases/{case['case_id']}/tour-draft"
    body = {"property_id": "fx-prop-3", "floor_plan": "1 bed / 1 bath"}
    assert client.post(url, json=body).status_code == 401
    read_only = {"Authorization": f"Bearer {case['read_token']}"}
    assert client.post(url, json=body, headers=read_only).status_code == 403


def test_tour_draft_is_a_draft_to_the_office_on_record_and_never_sent(client):
    case = new_case(client)
    url = f"/cases/{case['case_id']}/tour-draft"
    headers = {"X-Case-Token": case["token"]}
    response = client.post(
        url, json={"property_id": "fx-prop-3", "floor_plan": "1 bed / 1 bath"}, headers=headers
    )
    assert response.status_code == 200
    draft = response.json()
    assert draft["status"] == "draft" and draft["sent"] is False
    assert draft["addressee"] == "Fixture Property Management Co"
    assert draft["text"].startswith("To: Fixture Property Management Co")
    assert "application fee" in draft["text"] and not PHONE.search(draft["text"])
    # There is no route that sends it.
    assert client.post(f"{url}/send", json={}, headers=headers).status_code in (404, 405)


def test_tour_draft_errors_are_plain(client):
    case = new_case(client)
    url = f"/cases/{case['case_id']}/tour-draft"
    headers = {"X-Case-Token": case["token"]}
    unknown = client.post(url, json={"property_id": "fx-nope"}, headers=headers)
    assert unknown.status_code == 404
    no_office = client.post(url, json={"property_id": "880002"}, headers=headers)
    assert no_office.status_code == 422 and "no leasing office" in no_office.json()["detail"]
    assert client.post(url, json={}, headers=headers).status_code == 422


def test_tour_draft_quotes_the_picked_plan_by_plan_key(client):
    case = new_case(client)
    found = client.post("/search", json={"max_rent_month": 5000, "max_results": 50}).json()
    plans = [m for m in found["matches"] if m["property_id"] == "fx-prop-3"]
    assert len(plans) >= 2 and len({m["plan_key"] for m in plans}) == len(plans)
    url = f"/cases/{case['case_id']}/tour-draft"
    headers = {"X-Case-Token": case["token"]}
    for m in plans:
        body = {"property_id": m["property_id"], "plan_key": m["plan_key"]}
        draft = client.post(url, json=body, headers=headers).json()
        assert m["price_text"].split(" a month")[0] in draft["text"]


def test_search_has_a_body_cap_and_a_per_address_rate_limit(client):
    big = client.post("/search", content=b" " * 5000, headers={"Content-Type": "application/json"})
    assert big.status_code == 413
    codes = [client.post("/search", json={}).status_code for _ in range(40)]
    assert codes[:30] == [200] * 30 and 429 in codes[30:]
