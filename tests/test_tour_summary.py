"""Walk it first, W5: the two-column summary and the "rooms to see" line in the tour request."""

import re

import pytest
from fastapi.testclient import TestClient

from snapback.agent.join import KitLookups
from snapback.api.main import create_app
from snapback.contracts import DataSource, PlaceMatch
from snapback.search import draft_tour_request
from snapback.settings import Settings
from snapback.tour import (
    STILL_ALWAYS,
    TourDirector,
    TourFact,
    TourSweep,
    WalkCoverage,
    build_tour,
    rooms_to_see,
    rooms_to_see_line,
    summarize,
)

Q = (0.0, 0.0, 0.0, 1.0)


def sweeps():
    rows = [
        ("Entryway", 0),
        ("Kitchen", 3),
        ("Bathroom", 6),
        ("Bathroom", 20),
        ("Laundry", 24),
        ("Bedroom", 28),
    ]
    return [TourSweep(f"s{i}", (float(x), 1.4, 0.0), Q, lab) for i, (lab, x) in enumerate(rows)]


def base_plan():
    return build_tour(
        property_id="fx-prop-5",
        kind="apartment",
        source=DataSource.FIXTURE,
        sweeps=sweeps(),
        has_scan=True,
    )


def mark(plan, views, **update):
    """Set ad_view on the room stops in order, as the locate-to-stops task (W1) will."""
    rooms = iter(views)
    stops = [
        s.model_copy(update={"ad_view": next(rooms)}) if s.kind == "room" else s for s in plan.stops
    ]
    return plan.model_copy(update={"stops": stops, **update})


def test_rooms_to_see_are_the_rooms_with_no_ad_photo_in_walking_order():
    p = mark(base_plan(), ["placed", "none_placed", "none_placed", "none_placed", "placed"])
    assert [s.title for s in p.stops if s.kind == "room"] == [
        "Kitchen",
        "Bathroom 1",
        "Bathroom 2",
        "Laundry",
        "Bedroom",
    ]
    assert rooms_to_see(p) == ["Bathroom 1", "Bathroom 2", "Laundry"]


def test_unknown_view_is_never_called_hidden():
    assert rooms_to_see(base_plan()) == []
    assert rooms_to_see_line(base_plan()) is None


def test_line_names_rooms_with_ordinals_and_says_the_listing_did_not_show_them():
    p = mark(base_plan(), ["placed", "none_placed", "none_placed", "none_placed", "placed"])
    line = rooms_to_see_line(p)
    titles = rooms_to_see(p)
    assert line is not None and line.startswith("I'd like to see ")
    assert line.endswith("which the listing did not show.")
    assert len(titles) == 3
    assert "the first bathroom" in line and "the second bathroom" in line and "the laundry" in line


def test_line_is_softer_when_some_photos_could_not_be_placed():
    cov = WalkCoverage(counted="rooms", total=5, with_photo=1, placed=1, unplaced=2)
    p = mark(base_plan(), ["placed", "none_placed", "placed", "placed", "placed"], coverage=cov)
    line = rooms_to_see_line(p)
    assert line is not None and line.endswith("which the photos we could place did not show.")
    assert "did not show" in line and "the listing did not show" not in line


def test_no_line_when_every_photo_was_taken_elsewhere():
    cov = WalkCoverage(counted="rooms", total=5, elsewhere=3)
    p = mark(base_plan(), ["none_placed"] * 5, coverage=cov)
    assert rooms_to_see_line(p) is None


def test_the_draft_carries_the_rooms_and_stays_a_draft():
    place = PlaceMatch(
        property_id="fx-prop-5",
        kind="apartment",
        source=DataSource.FIXTURE,
        budget_fit="within",
        availability_text="as of CoStar's last research",
        price_text="$1,500 a month, as of CoStar's last research",
        office_on_record="Fixture Property Management Co",
    )
    line = "I'd like to see the second bathroom, which the listing did not show."
    draft = draft_tour_request(place, None, rooms_line=line)
    assert line in draft.text
    assert draft.text.index(line) < draft.text.index("Please reply with times")
    assert draft.sent is False and draft.status == "draft"
    assert line not in draft_tour_request(place, None).text


def test_the_summary_has_two_columns_and_always_the_things_no_record_can_tell():
    s = summarize(base_plan())
    assert s.know and s.see
    for line in STILL_ALWAYS:
        assert line in s.see
    assert any("does not tell you who may rent it" in x for x in s.see)


def test_summary_lists_hidden_rooms_and_unconfirmed_claims_before_the_fixed_lines():
    p = mark(base_plan(), ["placed", "none_placed", "placed", "placed", "placed"])
    arrive = p.stops[0].model_copy(
        update={"claims": [TourFact(text="The ad says a 2-car garage. Not confirmed.", source="x")]}
    )
    p = p.model_copy(update={"stops": [arrive, *p.stops[1:]]})
    s = summarize(p)
    assert s.see[0].startswith("The ad did not show the")
    assert "The ad says a 2-car garage. Not confirmed." in s.see
    assert s.see.index("The ad says a 2-car garage. Not confirmed.") < s.see.index(STILL_ALWAYS[0])


def test_summary_leads_with_the_director_checks_and_caps_at_five_extras():
    p = mark(base_plan(), ["none_placed"] * 5)
    lead = ["Check the water pressure.", "Look at the lock."]
    p = p.model_copy(update={"director": TourDirector(lead_checks=lead, stamp="policy")})
    s = summarize(p)
    assert s.see[:2] == lead


def test_summary_know_column_uses_the_coverage_line_and_the_scan_kind():
    cov = WalkCoverage(
        counted="rooms",
        total=5,
        with_photo=2,
        placed=2,
        line="The ad showed 2 of the 5 rooms in this scan.",
    )
    s = summarize(mark(base_plan(), ["placed"] * 5, coverage=cov))
    assert "The ad showed 2 of the 5 rooms in this scan." in s.know
    assert any("a 3D scan in this building" in x for x in s.know)
    assert any("as of CoStar's last research" in x for x in s.know)


def test_new_summary_copy_has_no_banned_words_or_dashes():
    p = mark(base_plan(), ["none_placed"] * 5)
    s = summarize(p)
    text = " ".join([*s.know, *s.see, rooms_to_see_line(p) or ""]).lower()
    for word in ("available", "for rent", "book", "everything", "neighborhood", "school", "—", "–"):
        assert word not in text
    assert not re.search(r"\d{3}[\s.-]\d{3,4}", text)


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))


def test_the_place_tour_route_carries_the_summary(client):
    body = client.get("/places/880001/tour").json()
    assert body["summary"]["know"] and body["summary"]["see"]


def test_the_draft_route_adds_no_rooms_line_without_a_placed_photo_result(client):
    made = client.post("/cases", data={"text": "Nice 1 bed, $1,500 a month"}).json()
    url = f"/cases/{made['case_id']}/tour-draft"
    r = client.post(
        url,
        json={"property_id": "fx-prop-3", "floor_plan": "1 bed / 1 bath"},
        headers={"X-Case-Token": made["token"]},
    )
    assert r.status_code == 200
    assert "I'd like to see" not in r.json()["text"]
