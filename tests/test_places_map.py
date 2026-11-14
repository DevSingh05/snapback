"""M1: the places map feed. One GeoJSON Feature per researched place, a fixed set of keys."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.agent.join import KitLookups
from snapback.api.main import create_app
from snapback.contracts import DataSource, RentalHouse, RenterBrief
from snapback.places_map import PROP_KEYS, PlacesIndex, build_places_map
from snapback.search import _all_matches
from snapback.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "map" / "places-map.fixture.geojson"
BANNED_KEYS = {
    "address",
    "office",
    "office_on_record",
    "name",
    "manager",
    "manager_company",
    "phone",
}


@pytest.fixture
def lookups():
    return KitLookups(DataSource.FIXTURE)


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))


def test_the_posted_fixture_follows_the_contract_exactly():
    doc = json.loads(FIXTURE.read_text())
    assert doc["type"] == "FeatureCollection" and doc["source"] == "fixture"
    assert doc["n_places"] == len(doc["features"]) and doc["n_fit"] <= doc["n_places"]
    for f in doc["features"]:
        assert set(f["properties"]) == set(PROP_KEYS)
        lon, lat = f["geometry"]["coordinates"]
        assert f["geometry"]["type"] == "Point" and -180 <= lon <= 180 and -90 <= lat <= 90
        assert f["properties"]["source"] == "fixture"
        assert f["properties"]["as_of"] == "as of CoStar's last research"


def test_features_carry_only_the_allow_listed_keys_and_no_address_office_or_name(lookups):
    doc = build_places_map(None, lookups).model_dump(mode="json")
    assert doc["features"], "the FIXTURE kit has located places"
    text = json.dumps(doc).lower()
    for f in doc["features"]:
        assert set(f["properties"]) == set(PROP_KEYS)
        assert not (BANNED_KEYS & set(f["properties"]))
    for word in ("fixture property management", "fixture living", "fixture walkup"):
        assert word not in text  # no company name anywhere


def test_one_feature_per_place_with_counts_and_a_printed_n(lookups):
    doc = build_places_map(None, lookups).model_dump(mode="json")
    pids = [f["properties"]["pid"] for f in doc["features"]]
    assert len(pids) == len(set(pids)) == doc["n_places"]
    # fx-prop-3 has three priced plans; the feed says so.
    by = {f["properties"]["pid"]: f["properties"] for f in doc["features"]}
    assert by["fx-prop-3"]["n_plans"] == 3 and by["fx-prop-3"]["kind"] == "apartment"
    assert by["fx-prop-3"]["has_scan"] is True
    # Places with no coordinates are counted, not drawn.
    assert doc["n_unlocated"] >= 1  # fx-prop-5 has no lat/lon in the fixture


def test_a_house_with_coordinates_is_a_place_and_says_no_units(lookups):
    doc = build_places_map(None, lookups).model_dump(mode="json")
    houses = [f["properties"] for f in doc["features"] if f["properties"]["kind"] == "house"]
    assert houses and all(h["units_reported"] is None and h["n_plans"] == 1 for h in houses)
    assert RentalHouse.model_fields["lat"].default is None


def test_fits_brief_is_the_same_set_search_would_match_not_cut_by_max_results(lookups):
    brief = RenterBrief(max_rent_month=1600, beds_min=1, max_results=1)
    doc = build_places_map(brief, lookups).model_dump(mode="json")
    fits = {f["properties"]["pid"] for f in doc["features"] if f["properties"]["fits_brief"]}
    _, matches = _all_matches(brief, lookups)
    expected = {m.property_id for m in matches}
    located = {f["properties"]["pid"] for f in doc["features"]}
    assert fits == expected & located
    assert len(expected) > 1  # max_results=1 did not cut the flags
    assert doc["n_fit"] == len(fits)


def test_no_brief_means_every_place_fits(lookups):
    doc = build_places_map(None, lookups).model_dump(mode="json")
    assert all(f["properties"]["fits_brief"] for f in doc["features"])


def test_rent_from_is_the_lowest_asking_price_and_units_sum_only_what_is_on_record(lookups):
    doc = build_places_map(None, lookups).model_dump(mode="json")
    by = {f["properties"]["pid"]: f["properties"] for f in doc["features"]}
    raws = [r for r in __import__("snapback.search", fromlist=["_supply"])._supply(lookups)]
    lows = [
        min(p for p in (r.rent_min, r.rent_max) if p is not None)
        for r in raws
        if r.property_id == "fx-prop-3"
    ]
    assert by["fx-prop-3"]["rent_from"] == min(lows)


def test_the_index_is_built_once_and_reused(lookups, monkeypatch):
    index = PlacesIndex(lookups)
    first = index.places()
    assert index.places() is first


def test_route_serves_the_feed_for_no_brief_and_for_a_brief(client):
    r = client.post("/places/map")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection" and body["source"] == "fixture"
    assert body["as_of"] == "as of CoStar's last research"
    narrowed = client.post("/places/map", json={"max_rent_month": 1000}).json()
    assert narrowed["n_places"] == body["n_places"] and narrowed["n_fit"] < body["n_fit"]


def test_route_validates_the_brief_and_has_a_rate_limit(client):
    assert client.post("/places/map", json={"max_rent_month": -5}).status_code == 422
    codes = {client.post("/places/map").status_code for _ in range(40)}
    assert codes <= {200, 429}


def test_no_banned_words_in_the_feed_copy(client):
    text = client.post("/places/map").text.lower()
    for word in ("available now", "for rent now", "open listing", "—", "–"):
        assert word not in text
