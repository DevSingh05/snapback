"""W1: the ad's photos on the stops, coverage wording, stop aliases (walk-plan section 5)."""

from snapback.contracts import DataSource, LocateResult, LocateStatus, PhotoLocation, Pose
from snapback.tour import build_tour, fixture_sweeps, map_locate

L = LocateStatus


def base_plan(sweeps=None):
    return build_tour(
        property_id="fx-prop-3",
        kind="apartment",
        source=DataSource.FIXTURE,
        sweeps=sweeps or fixture_sweeps("fx-model-a"),
        has_scan=True,
    )


def photo(pid, status, pano=None, label=None):
    return PhotoLocation(photo_id=pid, status=status, pano_id=pano, room_label=label)


def locate(*photos):
    poses = {
        p.photo_id: Pose(sweep_id=p.pano_id, position=(1.0, 1.4, 2.0), rotation_quat=(0, 0, 0, 1))
        for p in photos
        if p.status in (L.LOCATED_IN_CLAIMED, L.LOCATED_ELSEWHERE) and p.pano_id
    }
    return LocateResult(case_id="c", photos=list(photos), poses=poses, thresholds_version="t")


def by_title(plan):
    return {s.title: s for s in plan.stops}


def test_all_placed_lands_photos_in_their_rooms_and_empty_rooms_say_none_placed():
    plan, fields = map_locate(
        base_plan(),
        locate(
            photo("p1", L.LOCATED_IN_CLAIMED, "fx-sweep-03"),
            photo("p2", L.LOCATED_IN_CLAIMED, "fx-sweep-04"),
        ),
    )
    stops = by_title(plan)
    assert [p.photo_id for p in stops["Kitchen"].photos] == ["p1"]
    assert stops["Kitchen"].ad_view == "placed"
    assert stops["Bathroom"].ad_view == "none_placed"
    assert (
        stops["Arrive outside"].ad_view == "unknown"
        and stops["Now see it in person"].ad_view == "unknown"
    )
    c = plan.coverage
    assert (c.counted, c.total, c.with_photo, c.placed) == ("rooms", 6, 2, 2)
    assert c.line == "The ad showed 2 of the 6 rooms in this scan."
    assert fields["p1"].stop_alias == "S5" or fields["p1"].stop_alias.startswith("S")


def test_stop_alias_follows_walking_order_and_skips_arrive_and_outro():
    plan, fields = map_locate(base_plan(), locate(photo("p1", L.LOCATED_IN_CLAIMED, "fx-sweep-00")))
    assert fields["p1"].stop_alias == "S1"  # the front door is the first stop in the scan


def test_any_unplaced_photo_blocks_the_no_photo_wording_and_is_named_in_the_line():
    plan, _ = map_locate(
        base_plan(),
        locate(photo("p1", L.LOCATED_IN_CLAIMED, "fx-sweep-03"), photo("p2", L.NOT_LOCATED)),
    )
    rooms = [s for s in plan.stops if s.kind in ("door", "room")]
    assert all(s.ad_view != "none_placed" for s in rooms)
    assert plan.coverage.unplaced == 1
    assert plan.coverage.line == (
        "The ad showed 1 of the 6 rooms in this scan. "
        "1 photo could not be placed, so the real count may be higher."
    )


def test_photo_taken_elsewhere_never_enters_a_room_and_is_not_counted():
    plan, fields = map_locate(
        base_plan(),
        locate(
            photo("p1", L.LOCATED_IN_CLAIMED, "fx-sweep-03"),
            photo("p2", L.LOCATED_ELSEWHERE, "fx-sweep-04"),
        ),
    )
    assert sum(len(s.photos) for s in plan.stops) == 1
    assert fields["p2"].stop_alias is None
    assert plan.coverage.elsewhere == 1 and plan.coverage.with_photo == 1
    assert plan.coverage.line.endswith("1 photo was taken in a different building and not counted.")
    assert all(s.ad_view != "none_placed" for s in plan.stops if s.kind in ("door", "room"))


def test_nothing_placed_shows_the_scan_without_counting():
    plan, _ = map_locate(
        base_plan(), locate(photo("p1", L.NOT_LOCATED), photo("p2", L.NOT_LOCATED))
    )
    assert plan.coverage.counted == "none" and plan.coverage.total == 0
    assert plan.coverage.line == (
        "None of the ad's photos could be placed in this scan, "
        "so we show it without counting rooms."
    )
    assert all(s.ad_view == "unknown" for s in plan.stops)


def test_apartment_floor_plan_mismatch_is_not_counted_and_has_no_count_line():
    plan, _ = map_locate(
        base_plan(),
        locate(photo("p1", L.LOCATED_IN_CLAIMED, "fx-sweep-03")),
        scan_plan="2 bed / 2 bath",
        ad_plan="1 bed / 1 bath",
    )
    assert plan.coverage.counted == "none"
    assert plan.coverage.line == (
        "This scan is a 2 bed / 2 bath floor plan and the ad is for a 1 bed / 1 bath, "
        "so we show the scan without counting rooms."
    )
    assert plan.coverage.total == 0 and plan.coverage.with_photo == 0


def test_no_room_labels_count_spots_not_rooms():
    from snapback.tour import TourSweep

    sweeps = [TourSweep(f"s{i}", (i * 2.0, 1.4, 0.0), (0, 0, 0, 1), None) for i in range(6)]
    plan = base_plan(sweeps)
    plan2, _ = map_locate(plan, locate(photo("p1", L.LOCATED_IN_CLAIMED, "s0")))
    assert plan2.coverage.counted == "spots"
    assert plan2.coverage.line.startswith("The ad's photos were taken at 1 of ")
    assert plan2.coverage.line.endswith("spots in this scan.")


def test_a_placed_photo_in_a_sweep_that_is_no_stop_is_not_forced_onto_a_room():
    plan, fields = map_locate(
        base_plan(), locate(photo("p1", L.LOCATED_IN_CLAIMED, "no-such-sweep"))
    )
    assert sum(len(s.photos) for s in plan.stops) == 0
    assert fields["p1"].stop_alias is None and plan.coverage.placed == 1


def test_covers_unshown_room_is_true_only_for_a_label_no_placed_photo_covers():
    plan, fields = map_locate(
        base_plan(),
        locate(
            photo("p1", L.LOCATED_IN_CLAIMED, "fx-sweep-03", "Kitchen"),
            photo("p2", L.NOT_LOCATED, None, "Bathroom"),
            photo("p3", L.NOT_LOCATED, None, "Kitchen"),
            photo("p4", L.NOT_LOCATED),
        ),
    )
    assert fields["p2"].covers_unshown_room is True  # no placed photo is in the bathroom
    assert fields["p3"].covers_unshown_room is False  # the kitchen is already shown
    assert fields["p4"].covers_unshown_room is False  # no label: nothing to claim
    assert fields["p1"].covers_unshown_room is False


def test_walk_route_for_the_recorded_case_carries_coverage_and_photo_fields():
    import pathlib
    import tempfile

    from fastapi.testclient import TestClient

    from snapback.agent.join import KitLookups
    from snapback.api.main import create_app
    from snapback.settings import Settings

    settings = Settings(_env_file=None, snapback_data_dir=pathlib.Path(tempfile.mkdtemp()))
    client = TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))
    body = client.get("/cases/fx-7Q2M/walk").json()
    assert body["plan"]["source"] == "fixture" and body["plan"]["coverage"] is not None
    assert set(body["photos"]) == {p["photo_id"] for p in body["locate"]["photos"]}


def test_each_placed_photo_carries_its_evidence_alias_in_the_case_photo_order():
    plan, _ = map_locate(
        base_plan(),
        locate(photo("a", L.NOT_LOCATED), photo("b", L.LOCATED_IN_CLAIMED, "fx-sweep-03")),
    )
    kitchen = next(s for s in plan.stops if s.title == "Kitchen")
    assert [p.alias for p in kitchen.photos] == ["P2"]  # second photo of the case
