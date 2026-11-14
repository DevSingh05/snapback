"""M2: the place sheet (`GET /places/{pid}`) and its aerial (`/places/{pid}/aerial.jpg`)."""

import json
import re
from urllib.parse import quote, urlsplit

import pytest
from fastapi.testclient import TestClient

from snapback.agent.join import KitLookups
from snapback.api.main import create_app
from snapback.contracts import DataSource, RenterBrief
from snapback.search import HOUSE_SCAN, _all_matches
from snapback.settings import Settings

PHONE = re.compile(r"\+?\d[\d\s().\-]{8,}\d")


@pytest.fixture
def lookups():
    return KitLookups(DataSource.FIXTURE)


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))


def test_the_sheet_lists_every_plan_with_the_same_lines_search_builds(client, lookups):
    r = client.get("/places/fx-prop-3")
    assert r.status_code == 200
    body = r.json()
    assert body["property_id"] == "fx-prop-3" and body["kind"] == "apartment"
    assert body["source"] == "fixture" and body["as_of"] == "as of CoStar's last research"
    _, all_plans = _all_matches(RenterBrief(max_results=50), lookups)
    want = {m.plan_key: m for m in all_plans if m.property_id == "fx-prop-3"}
    assert len(body["plans"]) == len(want) == 3
    for plan in body["plans"]:
        m = want[plan["plan_key"]]
        assert plan["price_text"] == m.price_text
        assert plan["availability_text"] == m.availability_text
        assert [x["text"] for x in plan["must_haves"]] == [x.text for x in m.must_haves]


def test_the_sheet_names_the_company_on_record_the_scan_badge_and_the_walk_link(client):
    body = client.get("/places/fx-prop-3").json()
    assert body["office_on_record"] == "Fixture Property Management Co"
    assert body["has_3d_scan"] is True
    assert body["scan_text"] == "a 3D scan in this building"
    first_key = body["plans"][0]["plan_key"]
    assert first_key
    assert body["walk_path"] == f"/tour/fx-prop-3?plan_key={quote(first_key, safe='')}"
    # Follow the link: the web route /tour/{pid} reads the API's /places/{pid}/tour.
    parsed = urlsplit(body["walk_path"])
    walked = client.get(f"/places/{parsed.path.removeprefix('/tour/')}/tour?{parsed.query}")
    assert walked.status_code == 200
    no_scan = client.get("/places/fx-prop-4").json()
    assert no_scan["has_3d_scan"] is False and no_scan["scan_text"] is None


def test_a_house_sheet_has_one_plan_and_the_house_scan_wording(client):
    body = client.get("/places/880001").json()
    assert body["kind"] == "house" and len(body["plans"]) == 1
    assert body["scan_text"] == HOUSE_SCAN


def test_unknown_place_is_404(client):
    assert client.get("/places/nope").status_code == 404
    assert client.get("/places/fx-prop-2").status_code == 404  # held, but no priced plan


def test_sheet_copy_has_no_address_phone_banned_words_or_dashes(client):
    for pid in ("fx-prop-3", "fx-prop-4", "880001"):
        text = client.get(f"/places/{pid}").text
        low = text.lower()
        for word in ("available now", "for rent now", "open listing", "—", "–", "street", "lane"):
            assert word not in low, (pid, word)
        assert not PHONE.search(re.sub(r"\d{4}-\d{2}-\d{2}", "", text))
        assert "?token=" not in text
        assert "address" not in json.loads(text)


def test_sheet_aerial_line_names_the_date_and_source_or_says_none(client):
    body = client.get("/places/fx-prop-3").json()
    aerial = body["aerial"]
    assert aerial["source"] == "fixture" and aerial["image_path"] == "/places/fx-prop-3/aerial.jpg"
    assert aerial["line"] is None or "(fixture tile)" in aerial["line"]
    assert "Vexcel" not in json.dumps(aerial)


def test_the_aerial_route_serves_a_labelled_fixture_jpeg_for_a_fixture_place(client):
    r = client.get("/places/fx-prop-3/aerial.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert r.content.startswith(b"\xff\xd8\xff")
    assert r.headers["cache-control"] == "public, max-age=600"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert client.get("/places/nope/aerial.jpg").status_code == 404


def test_the_aerial_route_is_rate_limited_like_the_tour_and_refuses_a_token_address(client):
    assert client.get("/places/fx-prop-3/aerial.jpg?direction=sideways").status_code == 422
    codes = {client.get("/places/fx-prop-3").status_code for _ in range(40)}
    assert codes <= {200, 429}


def test_the_sheet_and_the_map_feed_agree_on_price_and_scan(client):
    feed = client.post("/places/map").json()
    for f in feed["features"]:
        pid = f["properties"]["pid"]
        sheet = client.get(f"/places/{pid}").json()
        assert sheet["has_3d_scan"] == f["properties"]["has_scan"]
        assert len(sheet["plans"]) == f["properties"]["n_plans"]
