"""Walk it first: the tour plan (ordering, labels, facts), its routes and its auth."""

import re

import pytest
from fastapi.testclient import TestClient

from snapback.agent.join import KitLookups
from snapback.api.main import create_app
from snapback.contracts import DataSource, PlaceMatch, PropertyRecord, RenterBrief
from snapback.search import search
from snapback.settings import Settings
from snapback.tour import (
    SCAN_APARTMENT,
    SCAN_HOUSE,
    START_NOTE,
    TourPhoto,
    TourSweep,
    attach_photos,
    build_tour,
    cached_sweeps,
    fixture_sweeps,
)

Q = (0.0, 0.0, 0.0, 1.0)


def sw(i, x, z, label):
    return TourSweep(f"s{i:02d}", (x, 1.4, z), Q, label)


def plan(sweeps, **kw):
    args = dict(
        property_id="fx-prop-3",
        kind="apartment",
        source=DataSource.FIXTURE,
        sweeps=sweeps,
        has_scan=True,
    )
    args.update(kw)
    return build_tour(**args)


def titles(p):
    return [s.title for s in p.stops]


def test_entrance_first_rooms_grouped_and_path_in_walking_order():
    # Listed out of order on purpose; the entryway is the door, then nearest first.
    sweeps = [
        sw(0, 0, 0, "Kitchen"),
        sw(1, 12, 0, "Entryway"),
        sw(2, 9, 0, "Hallway"),
        sw(3, 0, 1, "Kitchen"),
        sw(4, 5, 0, "Bedroom"),
    ]
    p = plan(sweeps)
    assert titles(p) == [
        "Arrive outside",
        "Front door",
        "Hallway",
        "Bedroom",
        "Kitchen",
        "Now see it in person",
    ]
    door = p.stops[1]
    assert door.sweep_id == "s01" and door.note is None and door.room_label == "Entryway"
    kitchen = p.stops[4]
    assert sorted(kitchen.sweep_ids) == ["s00", "s03"] and kitchen.sweep_count == 2


def test_same_label_far_apart_is_two_rooms_numbered_in_walking_order():
    p = plan([sw(0, 0, 0, "Entryway"), sw(1, 3, 0, "Bedroom"), sw(2, 30, 0, "Bedroom")])
    assert [s.title for s in p.stops if s.kind == "room"] == ["Bedroom 1", "Bedroom 2"]
    assert p.stops[2].sweep_id == "s01"


def test_most_central_sweep_represents_the_room():
    sweeps = [sw(0, 0, 0, "Entryway")] + [
        sw(i, x, 0, "Living room") for i, x in ((1, 2), (2, 4), (3, 6))
    ]
    room = [s for s in plan(sweeps).stops if s.kind == "room"][0]
    assert room.sweep_id == "s02"


def test_order_is_deterministic_and_the_entryway_leads_whatever_the_input_order():
    base = list(fixture_sweeps("fx-model-a"))
    a = plan(base)
    assert plan(base) == a and plan(list(base)) == a
    # Reversed input may move ties (the scan's own order breaks them); the door never moves.
    b = plan(list(reversed(base)))
    assert a.stops[1].sweep_id == b.stops[1].sweep_id == "fx-sweep-00"


def test_no_entry_label_uses_the_scan_start_honestly():
    p = plan([sw(0, 0, 0, "Kitchen"), sw(1, 3, 0, "Bedroom")])
    door = p.stops[1]
    assert door.kind == "door" and door.sweep_id == "s00" and door.note == START_NOTE
    assert door.room_label is None


def test_no_labels_falls_back_to_numbered_stops_and_says_so():
    sweeps = [sw(i, i * 2.0, 0, None) for i in range(20)]
    p = plan(sweeps)
    assert not p.rooms_labelled and "not labelled" in p.rooms_note
    mid = [s for s in p.stops if s.kind == "stop"]
    assert [s.title for s in mid] == [f"Stop {i}" for i in range(1, 9)]
    ids = [s.sweep_id for s in mid]
    assert ids == sorted(ids) and ids[-1] == "s19"  # evenly spaced along the path to its end
    assert p.stops[1].note == START_NOTE


def test_no_scan_or_uncached_scan_has_no_walkthrough_but_still_arrives_and_ends():
    none = plan([], has_scan=False)
    assert titles(none) == ["Arrive outside", "Now see it in person"] and none.scan_label is None
    uncached = plan([], has_scan=True)
    assert titles(uncached) == ["Arrive outside", "Now see it in person"]
    assert "not loaded" in uncached.rooms_note


def test_scan_labels_are_exact_for_houses_and_apartments():
    assert plan([sw(0, 0, 0, "Entryway")]).scan_label == SCAN_APARTMENT
    assert (
        SCAN_APARTMENT
        == "a 3D scan in this building (it may be a model unit, not the one you'd rent)"
    )
    house = plan([sw(0, 0, 0, "Entryway")], kind="house")
    assert house.scan_label == SCAN_HOUSE == "a 3D scan of this home"


def _place(**kw):
    base = dict(
        property_id="fx-prop-3",
        kind="apartment",
        floor_plan="2 bed / 2 bath",
        plan_key="k",
        beds=2,
        baths=2.0,
        budget_fit="no_budget",
        price_text="x",
        availability_text="y",
        has_3d_scan=True,
        source=DataSource.FIXTURE,
    )
    base.update(kw)
    return PlaceMatch(**base)


RECORD = PropertyRecord(
    property_id="fx-prop-3",
    source=DataSource.FIXTURE,
    floors=12,
    year_built=1998,
    parking_ratio=1.5,
    has_elevator=True,
    metering="individual",
)


def test_every_fact_has_a_source_and_only_record_facts_appear():
    from datetime import date

    p = plan(
        fixture_sweeps("fx-model-a") + [sw(9, 20, 20, "Laundry room")],
        place=_place(),
        record=RECORD,
        aerial_on=date(2025, 3, 2),
    )
    facts = [f for s in p.stops for f in s.facts]
    assert facts and all(f.source.strip() for f in facts)
    texts = " | ".join(f.text for f in facts)
    assert "Built in 1998" in texts and "12 floors" in texts and "Mar 2, 2025" in texts
    assert "2 bedrooms" in texts and "2 bathrooms" in texts and "Individual utility meters" in texts
    # Pool and yard are not in the record: never claimed.
    assert not re.search(r"pool|yard", texts, re.I)
    # A room with no fact on record has none, but still has its tip.
    kitchen = next(s for s in p.stops if s.room_label == "Kitchen")
    assert kitchen.facts == [] and "appliance" in (kitchen.tip or "")
    bath = next(s for s in p.stops if s.room_label == "Bathroom")
    assert "water pressure" in (bath.tip or "")


def test_facts_without_a_record_are_absent_not_invented():
    p = plan(fixture_sweeps("fx-model-a"))
    assert [f for s in p.stops for f in s.facts] == []


FORBIDDEN = re.compile(r"neighbo|school|available now|book now|schedule|spanish|crime|people", re.I)


def test_wording_never_strays_into_fair_housing_or_booking():
    p = plan(fixture_sweeps("fx-model-a"), place=_place(), record=RECORD)
    text = p.model_dump_json()
    assert not FORBIDDEN.search(text.replace("Book nothing", ""))


def test_attach_photos_lands_on_the_room_that_holds_the_sweep_and_drops_strays():
    p = plan(fixture_sweeps("fx-model-a"))
    out = attach_photos(
        p,
        [
            TourPhoto(photo_id="p1", sweep_id="fx-sweep-03"),
            TourPhoto(photo_id="p2", sweep_id="nope"),
        ],
    )
    kitchen = next(s for s in out.stops if s.room_label == "Kitchen")
    assert [x.photo_id for x in kitchen.photos] == ["p1"]
    assert sum(len(s.photos) for s in out.stops) == 1
    assert all(not s.photos for s in p.stops)  # the original is untouched


def test_cached_sweeps_reads_the_cache_only_and_is_empty_when_missing(tmp_path):
    assert cached_sweeps("mdl", tmp_path) == []


# --- routes ------------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))


def plan_key_of(pid):
    lookups = KitLookups(DataSource.FIXTURE)
    return next(
        m.plan_key
        for m in search(RenterBrief(max_results=50), lookups).matches
        if m.property_id == pid
    )


def test_place_tour_route_is_fixture_labelled_and_walks_the_scan(client):
    r = client.get("/places/fx-prop-5/tour", params={"plan_key": plan_key_of("fx-prop-5")})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "fixture" and body["has_scan"] and body["rooms_labelled"]
    assert body["scan_label"] == SCAN_APARTMENT
    kinds = [s["kind"] for s in body["stops"]]
    assert kinds[:2] == ["arrive", "door"] and kinds[-1] == "outro"
    assert "model_id" not in r.text and "fx-model" not in r.text  # no scan id leaves the server
    assert body["links"]["tour_prep"].startswith("/prep/place/fx-prop-5")
    again = client.get("/places/fx-prop-5/tour", params={"plan_key": plan_key_of("fx-prop-5")})
    assert again.json() == body  # deterministic


def test_place_tour_route_house_label_unknown_place_and_ambiguous_plan(client):
    house = client.get("/places/880001/tour").json()
    assert house["kind"] == "house" and house["scan_label"] == SCAN_HOUSE
    assert client.get("/places/nope/tour").status_code == 404
    assert client.get("/places/fx-prop-3/tour").status_code == 422
    ok = client.get("/places/fx-prop-3/tour", params={"plan_key": plan_key_of("fx-prop-3")})
    assert ok.status_code == 200


def test_place_without_a_scan_says_so(client):
    body = client.get(
        "/places/fx-prop-4/tour", params={"plan_key": plan_key_of("fx-prop-4")}
    ).json()
    assert not body["has_scan"] and body["scan_label"] is None
    assert [s["kind"] for s in body["stops"]] == ["arrive", "outro"]


def test_case_tour_route_needs_the_read_token_in_a_header(client):
    made = client.post("/cases", data={"text": "Nice 1 bed, $1,500 a month"}).json()
    url = f"/cases/{made['case_id']}/tour"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer nope"}).status_code == 403
    assert client.get(f"{url}?token={made['read_token']}").status_code == 401
    ok = client.get(url, headers={"Authorization": f"Bearer {made['read_token']}"})
    assert ok.status_code in (200, 404)  # 404 only if the case names no building
    assert client.get("/cases/NOPE/tour").status_code == 404
