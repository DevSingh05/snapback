"""X1: the walk of the building the ad's photos were taken in (copy guards, walk-plan rule 5)."""

import re

from snapback.contracts import DataSource, LocateResult, LocateStatus, PhotoLocation, Pose
from snapback.tour import (
    build_tour,
    elsewhere_property,
    fixture_sweeps,
    map_elsewhere,
)

L = LocateStatus


def photo(pid, status, pano, prop=None):
    return PhotoLocation(photo_id=pid, status=status, pano_id=pano, matched_property_id=prop)


def locate(*photos):
    poses = {
        p.photo_id: Pose(sweep_id=p.pano_id, position=(1, 1.4, 2), rotation_quat=(0, 0, 0, 1))
        for p in photos
        if p.pano_id
    }
    return LocateResult(
        case_id="c",
        photos=list(photos),
        poses=poses,
        claimed_property_id="claimed",
        thresholds_version="t",
    )


def other_plan():
    return build_tour(
        property_id="other",
        kind="apartment",
        source=DataSource.FIXTURE,
        sweeps=fixture_sweeps("fx-model-a"),
        has_scan=True,
    )


CASE_B = locate(
    photo("p1", L.LOCATED_ELSEWHERE, "fx-sweep-03", "other"),
    photo("p2", L.LOCATED_IN_CLAIMED, "fx-sweep-04", "claimed"),
    photo("p3", L.NOT_LOCATED, None),
)


def test_the_building_is_the_one_most_photos_were_verified_in_and_never_a_guess():
    assert elsewhere_property(CASE_B) == "other"
    assert elsewhere_property(locate(photo("p", L.NOT_LOCATED, None))) is None
    assert elsewhere_property(locate(photo("p", L.LOCATED_ELSEWHERE, "s", None))) is None
    two = locate(
        photo("a", L.LOCATED_ELSEWHERE, "s", "zz"),
        photo("b", L.LOCATED_ELSEWHERE, "s", "aa"),
        photo("c", L.LOCATED_ELSEWHERE, "s", "zz"),
    )
    assert elsewhere_property(two) == "zz"


def test_only_photos_verified_in_this_building_enter_its_rooms():
    plan, fields = map_elsewhere(other_plan(), CASE_B, "other", "Fixture Living LLC")
    placed = [(s.title, [p.photo_id for p in s.photos]) for s in plan.stops if s.photos]
    assert placed == [("Kitchen", ["p1"])]  # the claimed-home photo p2 is in no room here
    assert "p2" not in fields or fields["p2"].stop_alias is None
    assert plan.mode == "elsewhere"


def test_no_coverage_no_none_placed_and_the_line_names_only_the_office():
    plan, _ = map_elsewhere(other_plan(), CASE_B, "other", "Fixture Living LLC")
    assert plan.coverage.counted == "none" and plan.coverage.line is None
    assert all(s.ad_view != "none_placed" for s in plan.stops)
    assert plan.mode_line == (
        "The home in these photos is listed by Fixture Living LLC on CoStar's record. "
        "We can't tell you if it is offered, or at this price."
    )


def test_no_office_on_record_says_so():
    plan, _ = map_elsewhere(other_plan(), CASE_B, "other", None)
    assert plan.mode_line == (
        "We could not read this home's office from CoStar's record. "
        "We can't tell you if it is offered, or at this price."
    )
    assert "no leasing office" not in plan.mode_line


def test_copy_guards():
    plan, _ = map_elsewhere(other_plan(), CASE_B, "other", "Fixture Living LLC")
    text = plan.model_dump_json()
    for banned in (
        r"the real one",
        r"for rent",
        r"available",
        r"book",
        r"neighbo",
        r"school",
        r"fake",
        r"scam",
        r"everything",
    ):
        assert not re.search(banned, text.replace("Book nothing", ""), re.I), banned
    assert "—" not in text and "–" not in text


def test_elsewhere_route_needs_the_token_and_404s_when_no_photo_was_placed_elsewhere():
    import pathlib
    import tempfile

    from fastapi.testclient import TestClient

    from snapback.agent.join import KitLookups
    from snapback.api.main import create_app
    from snapback.settings import Settings

    settings = Settings(_env_file=None, snapback_data_dir=pathlib.Path(tempfile.mkdtemp()))
    client = TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))
    made = client.post("/cases", data={"text": "Nice 1 bed, $1,500 a month"}).json()
    url = f"/cases/{made['case_id']}/walk?mode=elsewhere"
    assert client.get(url).status_code == 401
    ok = client.get(url, headers={"Authorization": f"Bearer {made['read_token']}"})
    assert ok.status_code == 404
    assert client.get("/cases/fx-7Q2M/walk?mode=elsewhere").status_code == 404
    assert client.get("/cases/fx-7Q2M/walk?mode=nope").status_code == 422


def test_elsewhere_photos_keep_their_case_alias_not_a_renumbered_one():
    plan, _ = map_elsewhere(other_plan(), CASE_B, "other", None)
    kitchen = next(s for s in plan.stops if s.title == "Kitchen")
    assert [p.alias for p in kitchen.photos] == ["P1"]
    case = locate(
        photo("x", L.NOT_LOCATED, None),
        photo("y", L.LOCATED_ELSEWHERE, "fx-sweep-03", "other"),
    )
    plan, _ = map_elsewhere(other_plan(), case, "other", None)
    assert [p.alias for s in plan.stops for p in s.photos] == ["P2"]


def test_spanish_line_says_offered_not_rented_and_never_no_office():
    from snapback.tour import ELSEWHERE_LINE, ELSEWHERE_UNREAD

    assert "ofrece" in ELSEWHERE_LINE["es"] and "alquil" not in ELSEWHERE_LINE["es"]
    plan, _ = map_elsewhere(other_plan(), CASE_B, "other", None, lang="es")
    assert plan.mode_line == ELSEWHERE_UNREAD["es"]


def _client():
    import pathlib
    import tempfile

    from fastapi.testclient import TestClient

    from snapback.agent.join import KitLookups
    from snapback.api.main import create_app
    from snapback.settings import Settings

    settings = Settings(_env_file=None, snapback_data_dir=pathlib.Path(tempfile.mkdtemp()))
    return TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))


def test_a_multi_plan_building_still_names_its_office_from_any_plan(monkeypatch):
    # fx-prop-3 has several floor plans (an ambiguous place) and an office on record.
    import snapback.api.main as api

    monkeypatch.setattr(api, "elsewhere_property", lambda _l: "fx-prop-3")
    body = _client().get("/cases/fx-7Q2M/walk?mode=elsewhere").json()
    line = body["plan"]["mode_line"]
    assert "listed by Fixture Property Management Co on CoStar's record" in line
    assert "no leasing office" not in line and body["plan"]["mode"] == "elsewhere"
