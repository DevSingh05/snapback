"""W1: the ad's photos on the stops, coverage wording, stop aliases (walk-plan section 5)."""

from snapback.contracts import DataSource, LocateResult, LocateStatus, PhotoLocation, Pose
from snapback.tour import TourSweep, build_tour, fixture_sweeps, map_locate

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


def locate(*photos, at=(1.0, 1.4, 2.0)):
    poses = {
        p.photo_id: Pose(sweep_id=p.pano_id, position=at, rotation_quat=(0, 0, 0, 1))
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
        "This scan is a 2-bed floor plan and the ad is for a 1-bed, "
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
        base_plan(),
        locate(photo("p1", L.LOCATED_IN_CLAIMED, "no-such-sweep"), at=(300.0, 1.4, 300.0)),
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


def test_a_photo_on_no_stop_never_lets_an_empty_room_say_the_ad_showed_none():
    # Unlabelled scan: only some sweeps become stops, so a placed photo can sit off every stop.
    sweeps = [TourSweep(f"s{i}", (i * 2.0, 1.4, 0.0), (0, 0, 0, 1), None) for i in range(30)]
    plan = base_plan(sweeps)
    stop_sweeps = {s.sweep_id for s in plan.stops if s.sweep_id}
    off = next(f"s{i}" for i in range(30) if f"s{i}" not in stop_sweeps)
    out, fields = map_locate(
        plan, locate(photo("p1", L.LOCATED_IN_CLAIMED, off), at=(500.0, 1.4, 500.0))
    )
    assert fields["p1"].stop_alias is None and out.coverage.placed == 1
    assert all(s.ad_view != "none_placed" for s in out.stops)
    assert all(s.ad_view == "unknown" for s in out.stops if s.kind in ("door", "stop"))


def test_a_photo_07_m_from_the_kitchen_sweep_is_in_the_kitchen():
    kitchen = next(s for s in base_plan().stops if s.title == "Kitchen")
    x, y, z = kitchen.position
    plan, fields = map_locate(
        base_plan(),
        locate(photo("p1", L.LOCATED_IN_CLAIMED, "off-sweep"), at=(x + 0.7, y, z)),
    )
    assert [p.photo_id for p in next(s for s in plan.stops if s.title == "Kitchen").photos] == [
        "p1"
    ]
    assert fields["p1"].stop_alias is not None


def test_the_start_sweep_door_gives_its_photo_to_the_room_and_stays_out_of_the_total():
    sweeps = [
        TourSweep("a", (0.0, 1.4, 0.0), (0, 0, 0, 1), "Kitchen"),
        TourSweep("b", (2.0, 1.4, 0.0), (0, 0, 0, 1), "Kitchen"),
        TourSweep("c", (30.0, 1.4, 0.0), (0, 0, 0, 1), "Bedroom"),
    ]
    plan = base_plan(sweeps)
    door = next(s for s in plan.stops if s.kind == "door")
    assert door.note == "Start of the 3D scan" and door.sweep_id == "a"
    out, _ = map_locate(plan, locate(photo("p1", L.LOCATED_IN_CLAIMED, "a")))
    assert [p.photo_id for p in next(s for s in out.stops if s.title == "Kitchen").photos] == ["p1"]
    assert not next(s for s in out.stops if s.kind == "door").photos
    assert out.coverage.total == 2  # Kitchen and Bedroom; the start door is no room
    assert out.coverage.line == "The ad showed 1 of the 2 rooms in this scan."


def test_the_case_walk_uses_the_scan_the_photos_were_placed_in(monkeypatch):
    import snapback.api.main as api
    from snapback.tour import fixture_sweeps as real

    asked = []

    def spy(model_id):
        asked.append(model_id)
        return real(model_id)

    monkeypatch.setattr(api, "fixture_sweeps", spy)
    from fastapi.testclient import TestClient  # noqa: F401

    client = _walk_client()
    body = client.get("/cases/fx-7Q2M/walk").json()
    assert body["model_id"] == "fx-model-a"  # the chosen floor plan's scan
    assert asked[0] == "fx-model-a"
    # A building with two scans: the second one is used when the photos were placed in it.
    asked.clear()
    monkeypatch.setattr(api, "scan_model_of", lambda _l, _p=None: "fx-model-b")
    body = client.get("/cases/fx-7Q2M/walk").json()
    assert body["model_id"] == "fx-model-b" and asked[0] == "fx-model-b"


def test_the_case_walk_derives_the_ad_floor_plan_so_a_mismatch_is_not_counted(monkeypatch):
    import snapback.api.main as api

    monkeypatch.setattr(api, "ad_beds_of", lambda _case: 1)  # the ad says 1 bed
    body = _walk_client().get("/cases/fx-7Q2M/walk").json()  # the scan is 2 bed / 2 bath
    cov = body["plan"]["coverage"]
    assert cov["plan_mismatch"] is True and cov["counted"] == "none"
    assert cov["line"] == (
        "This scan is a 2-bed floor plan and the ad is for a 1-bed, "
        "so we show the scan without counting rooms."
    )


def _walk_client():
    import pathlib
    import tempfile

    from fastapi.testclient import TestClient

    from snapback.agent.join import KitLookups
    from snapback.api.main import create_app
    from snapback.settings import Settings

    settings = Settings(_env_file=None, snapback_data_dir=pathlib.Path(tempfile.mkdtemp()))
    return TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))


def test_recorded_case_has_photos_off_every_stop_so_no_room_says_none_placed():
    # fx-7Q2M: three placed photos, two of them in sweeps this scan does not have.
    body = _walk_client().get("/cases/fx-7Q2M/walk").json()
    assert body["plan"]["coverage"]["placed"] == 3
    assert all(s["ad_view"] != "none_placed" for s in body["plan"]["stops"])


class _NoHomeNamed:
    """A case whose ad named no home (as a pasted ad with no address is): the recorded case's
    evidence, with the building known only through what the photos did or did not identify."""

    def __init__(self, inner, identified: bool) -> None:
        self._inner = inner
        self.property_id = None
        locate = inner.evidence.locate.model_copy(update={"identified_by_scan": identified})
        self.evidence = inner.evidence.model_copy(update={"locate": locate})

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _no_home_named(monkeypatch, client, identified: bool, case_id="fx-7Q2M"):
    store = client.app.state.store
    case = _NoHomeNamed(store.get(case_id), identified)
    real = store.get
    monkeypatch.setattr(store, "get", lambda cid: case if cid == case_id else real(cid))


def test_a_case_whose_home_the_photos_identified_still_has_a_walk(monkeypatch):
    client = _walk_client()
    named = client.get("/cases/fx-7Q2M/walk").json()
    _no_home_named(monkeypatch, client, identified=True)
    res = client.get("/cases/fx-7Q2M/walk")
    assert res.status_code == 200
    body = res.json()
    assert body["model_id"] == named["model_id"]
    assert [s["kind"] for s in body["plan"]["stops"]] == [s["kind"] for s in named["plan"]["stops"]]
    assert body["plan"]["coverage"]["placed"] == named["plan"]["coverage"]["placed"]


def test_a_case_with_no_home_named_or_identified_has_no_walk(monkeypatch):
    client = _walk_client()
    _no_home_named(monkeypatch, client, identified=False)
    res = client.get("/cases/fx-7Q2M/walk")
    assert res.status_code == 404
    assert res.json()["detail"] == "This case has no building on record."
