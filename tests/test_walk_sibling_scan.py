"""#229: a photo placed in a sibling scan of the building is never mapped by position."""

from snapback.contracts import (
    DataSource,
    LocateResult,
    LocateStatus,
    PhotoLocation,
    Pose,
)
from snapback.tour import build_tour, fixture_sweeps, map_locate

L = LocateStatus
Q = (0.0, 0.0, 0.0, 1.0)


def plan_of_scan_a():
    return build_tour(
        property_id="fx-prop-1",
        kind="apartment",
        source=DataSource.FIXTURE,
        sweeps=fixture_sweeps("fx-model-a"),
        has_scan=True,
    )


def photo(pid, model, pano):
    return PhotoLocation(
        photo_id=pid,
        status=L.LOCATED_IN_CLAIMED,
        model_id=model,
        matched_model_id=model,
        pano_id=pano,
    )


def locate(*photos, at):
    poses = {
        p.photo_id: Pose(sweep_id=p.pano_id, position=at[p.photo_id], rotation_quat=Q)
        for p in photos
    }
    return LocateResult(case_id="c", photos=list(photos), poses=poses, thresholds_version="t")


def test_a_photo_from_the_sibling_scan_is_not_put_on_a_stop_by_position():
    living = next(s for s in plan_of_scan_a().stops if s.title == "Living room")
    # p2 was placed in scan B (a Bedroom there) at a position that, read in scan A's frame, is
    # exactly the Living room: the bug put it there.
    result = locate(
        photo("p1", "fx-model-a", "fx-sweep-03"),
        photo("p2", "fx-model-b", "fx-sweep-04"),
        at={"p1": (8.0, 1.4, -2.0), "p2": living.position},
    )
    plan, fields = map_locate(plan_of_scan_a(), result, model_id="fx-model-a")
    on = {s.title: [p.photo_id for p in s.photos] for s in plan.stops if s.photos}
    assert on == {"Kitchen": ["p1"]}  # nothing from scan B anywhere, least of all the Living room
    assert fields["p2"].stop_alias is None
    c = plan.coverage
    assert (c.placed, c.other_scan, c.unplaced) == (1, 1, 0)
    assert c.line == (
        "The ad showed 1 of the 6 rooms in this scan. 1 photo was placed in this home, "
        "in another scan of this building, and not shown in a room here."
    )
    # No room may claim the ad showed nothing of it while a placed photo is not on a stop.
    assert all(s.ad_view != "none_placed" for s in plan.stops)


def test_all_photos_in_the_sibling_scan_show_this_scan_without_counting():
    result = locate(
        photo("p1", "fx-model-b", "fx-sweep-03"),
        at={"p1": (8.0, 1.4, -2.0)},
    )
    plan, _ = map_locate(plan_of_scan_a(), result, model_id="fx-model-a")
    assert not any(s.photos for s in plan.stops)
    assert plan.coverage.counted == "none" and plan.coverage.other_scan == 1
    assert plan.coverage.line == (
        "The ad's photos were placed in another scan of this building, "
        "so we show this scan without counting rooms."
    )


def test_a_photo_with_no_scan_named_is_not_mapped_when_the_walks_scan_is_known():
    bare = PhotoLocation(photo_id="p1", status=L.LOCATED_IN_CLAIMED, pano_id="fx-sweep-03")
    plan, _ = map_locate(
        plan_of_scan_a(), locate(bare, at={"p1": (8.0, 1.4, -2.0)}), model_id="fx-model-a"
    )
    assert not any(s.photos for s in plan.stops) and plan.coverage.other_scan == 1


def test_without_a_walk_model_nothing_is_filtered():
    result = locate(photo("p1", "fx-model-b", "fx-sweep-03"), at={"p1": (8.0, 1.4, -2.0)})
    plan, _ = map_locate(plan_of_scan_a(), result)
    assert [s.title for s in plan.stops if s.photos] == ["Kitchen"]


def test_the_case_walk_passes_its_scan_so_a_sibling_scans_photos_are_not_mapped(monkeypatch):
    import pathlib
    import tempfile

    from fastapi.testclient import TestClient

    import snapback.api.main as api
    from snapback.agent.join import KitLookups
    from snapback.settings import Settings

    settings = Settings(_env_file=None, snapback_data_dir=pathlib.Path(tempfile.mkdtemp()))
    client = TestClient(api.create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))
    # The recorded case's photos were placed in fx-model-a; the walk is shown for fx-model-b.
    monkeypatch.setattr(api, "scan_model_of", lambda _l, _p=None: "fx-model-b")
    body = client.get("/cases/fx-7Q2M/walk").json()
    cov = body["plan"]["coverage"]
    assert cov["other_scan"] == 3 and cov["placed"] == 0 and cov["counted"] == "none"
    assert not any(s["photos"] for s in body["plan"]["stops"])
