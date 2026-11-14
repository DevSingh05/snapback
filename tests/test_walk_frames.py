"""Review FIX: the floor plane comes from the data (z-up caches); offices are found by id."""

from snapback.contracts import (
    DataSource,
    FloorPlanRent,
    LocateResult,
    LocateStatus,
    PhotoLocation,
    Pose,
    PropertyRecord,
    RentalHouse,
)
from snapback.tour import (
    TourSweep,
    build_tour,
    count_line,
    fixture_sweeps,
    floor_xy,
    map_locate,
    office_on_record,
    up_axis_for,
)

Q = (0.0, 0.0, 0.0, 1.0)


def zup(i, x, y, label, h=1.4):
    """Matterport's cache is z-up: (x, y, height)."""
    return TourSweep(f"z{i}", (x, y, h), Q, label)


def zup_plan():
    # Kitchen and Bedroom share an x but are 20 m apart in y. Read as y-up (x, z) they would
    # look 0 m apart, so the wrong frame mixes the rooms up.
    sweeps = [
        zup(0, 0.0, 0.0, "Entryway"),
        zup(1, 5.0, 0.0, "Kitchen"),
        zup(2, 5.0, 2.0, "Kitchen"),
        zup(3, 5.0, 20.0, "Bedroom"),
        zup(4, 5.0, 22.0, "Bedroom"),
    ]
    return build_tour(
        property_id="p", kind="apartment", source=DataSource.LIVE, sweeps=sweeps, has_scan=True
    )


def locate_at(x, y, h, sweep="off"):
    photo = PhotoLocation(photo_id="p1", status=LocateStatus.LOCATED_IN_CLAIMED, pano_id=sweep)
    pose = Pose(sweep_id=sweep, position=(x, y, h), rotation_quat=Q)
    return LocateResult(case_id="c", photos=[photo], poses={"p1": pose}, thresholds_version="t")


def test_the_up_axis_follows_the_data_source_not_a_guess_from_the_numbers():
    assert up_axis_for(DataSource.FIXTURE) == "y" and up_axis_for(DataSource.LIVE) == "z"
    assert floor_xy((1, 2, 3), "y") == (1, 3) and floor_xy((1, 2, 3), "z") == (1, 2)
    fixture = build_tour(
        property_id="p",
        kind="apartment",
        source=DataSource.FIXTURE,
        sweeps=fixture_sweeps("fx-model-a"),
        has_scan=True,
    )
    assert fixture.up_axis == "y"


def test_a_z_up_scan_is_walked_and_grouped_by_the_real_floor_plane():
    plan = zup_plan()
    assert plan.up_axis == "z"
    titles = [s.title for s in plan.stops if s.kind == "room"]
    assert titles == ["Kitchen", "Bedroom"]  # nearest first from the door, two separate rooms
    kitchen = next(s for s in plan.stops if s.title == "Kitchen")
    assert sorted(kitchen.sweep_ids) == ["z1", "z2"]


def test_a_photo_off_every_stop_goes_to_the_room_it_is_in_not_one_20_m_away():
    plan = zup_plan()
    # 0.7 m from the Kitchen sweep in the floor plane; the bedroom is 20 m away in y.
    out, fields = map_locate(plan, locate_at(5.7, 0.0, 1.4))
    where = {s.title: [p.photo_id for p in s.photos] for s in out.stops if s.photos}
    assert where == {"Kitchen": ["p1"]}
    # Far from every stop in the floor plane: on no room.
    far, f2 = map_locate(plan, locate_at(5.0, 11.0, 1.4))
    assert not any(s.photos for s in far.stops) and f2["p1"].stop_alias is None


def test_count_line_names_the_kind_not_the_room_label():
    line = count_line("Bedroom", "3", 2, "bedroom")
    assert line.startswith("The ad says 3 bedrooms. This scan has 2 rooms labelled Bedroom.")


class _Lookups:
    source = DataSource.FIXTURE

    def __init__(self, records, houses):
        self._records, self._houses = records, houses

    def records(self):
        return self._records

    def rentals(self):
        return self._houses

    def record(self, pid):
        return self._records.get(pid)


def _building(pid, rent, office):
    return PropertyRecord(
        property_id=pid,
        source=DataSource.FIXTURE,
        manager_company=office,
        floor_plan_rents=[
            FloorPlanRent(name="1 bed / 1 bath", beds=1, baths=1, rent_min=rent, rent_max=rent)
        ],
    )


def test_office_is_looked_up_by_id_even_with_more_than_50_cheaper_places():
    records = {
        f"cheap-{i:03d}": _building(f"cheap-{i:03d}", 500 + i, f"Cheap Co {i}") for i in range(60)
    }
    records["pricey"] = _building("pricey", 9000, "Pricey Management")
    house = RentalHouse(
        property_id="house-1",
        source=DataSource.FIXTURE,
        beds=3,
        baths=2.0,
        rent_min=9900,
        rent_max=9900,
        office="House Realty Inc",
        has_scan=True,
    )
    lookups = _Lookups(records, [house])
    assert office_on_record(lookups, "pricey") == "Pricey Management"  # beyond a top-50 page
    assert office_on_record(lookups, "house-1") == "House Realty Inc"  # houses too
    assert office_on_record(lookups, "unknown") is None


def test_one_label_split_by_10_m_in_y_is_two_rooms_in_a_z_up_scan():
    sweeps = [
        zup(0, 0.0, 0.0, "Entryway"),
        zup(1, 5.0, 0.0, "Bathroom"),
        zup(2, 5.0, 10.0, "Bathroom"),  # same x and height, 10 m away across the floor
    ]
    plan = build_tour(
        property_id="p", kind="apartment", source=DataSource.LIVE, sweeps=sweeps, has_scan=True
    )
    assert plan.up_axis == "z"
    assert [s.title for s in plan.stops if s.kind == "room"] == ["Bathroom 1", "Bathroom 2"]


def test_count_line_in_a_walk_names_the_kind_even_for_a_primary_bedroom_label():
    from snapback.contracts import AdNote
    from snapback.tour import attach_claims

    sweeps = [
        zup(0, 0.0, 0.0, "Entryway"),
        zup(1, 5.0, 0.0, "Primary Bedroom"),
        zup(2, 5.0, 10.0, "Primary Bedroom"),
    ]
    plan = build_tour(
        property_id="p", kind="apartment", source=DataSource.LIVE, sweeps=sweeps, has_scan=True
    )
    out = attach_claims(
        plan, [AdNote(key="beds_differ", claim="beds", ad_value="3", record_value="2")]
    )
    lines = [c.text for s in out.stops for c in s.claims if "labelled" in c.text]
    assert lines == [
        "The ad says 3 bedrooms. This scan has 2 rooms labelled Bedroom. "
        "Labels can be wrong, so count them in person."
    ]
