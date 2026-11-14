"""The live adapter, with a stub Locator in the shape lane V's #223 describes. The real
`Locator.search` is not imported here; it plugs in once #223 lands."""

import dataclasses
from types import SimpleNamespace

from snapback.agent.place import PlaceDesk, SearchOption
from snapback.agent.place_locator import MAX_POINTS, LocatorSearcher
from snapback.contracts import LocateResult, LocateStatus, PhotoLocation
from snapback.vision.locate.thresholds import load_thresholds

BASE = load_thresholds()
L = LocateStatus


class StubLocator:
    def __init__(self, **result):
        self.result = SimpleNamespace(**result)
        self.calls = []

    def search(self, photo, option, claimed_property_id, *, scan_model_id=None, deadline_s=None):
        self.calls.append((photo, option, claimed_property_id, scan_model_id, deadline_s))
        return self.result


def adapter(locator):
    return LocatorSearcher(locator, photo_for=lambda pid: f"image-of-{pid}")


def test_the_adapter_passes_the_image_the_option_the_scan_and_the_deadline():
    locator = StubLocator(status=L.NOT_LOCATED, seconds=1.5)
    out = adapter(locator).search(
        "l2", SearchOption("focus_scan", "S2", "m2"), "fx-prop-1", BASE, 7.5
    )
    assert locator.calls == [("image-of-l2", "focus_scan", "fx-prop-1", "m2", 7.5)]
    assert out.location.status is L.NOT_LOCATED and out.seconds == 1.5


def test_the_result_maps_into_a_photo_location_with_a_capped_point_sample():
    pairs = [(i / 100, 0.5, i / 100, 0.5) for i in range(90)]
    locator = StubLocator(
        status=L.LOCATED_IN_CLAIMED,
        model_id="m2",
        sweep_id="sw1",
        inliers=88,
        inlier_ratio=0.41,
        spread=0.31,
        rival_ratio=0.05,
        bar_failed=None,
        matched_model_id="m2",
        matched_property_id="p1",
        room_label="Kitchen",
        points=pairs,
        n_points=88 + 2,
        seconds=2.1,
    )
    out = adapter(locator).search("l4", SearchOption("wider_index"), "p1", BASE, 10.0)
    loc = out.location
    assert (loc.photo_id, loc.status, loc.model_id, loc.inliers) == (
        "l4",
        L.LOCATED_IN_CLAIMED,
        "m2",
        88,
    )
    assert (loc.inlier_ratio, loc.spread, loc.rival_ratio) == (0.41, 0.31, 0.05)
    assert (loc.room_label, loc.matched_property_id) == ("Kitchen", "p1")
    assert len(out.points.sampled) == MAX_POINTS and out.points.n_total == 90


def test_a_stop_or_an_empty_result_is_a_miss_not_an_error():
    out = adapter(StubLocator(status=None)).search("l2", SearchOption("wider_index"), None, BASE, 5)
    assert out.location.status is L.NOT_LOCATED and out.points is None


def located() -> LocateResult:
    photos = [
        PhotoLocation(photo_id="l1", status=L.LOCATED_IN_CLAIMED, model_id="m1", inliers=142),
        PhotoLocation(
            photo_id="l2",
            status=L.NOT_LOCATED,
            inliers=24,
            inlier_ratio=0.18,
            spread=0.03,
            bar_failed="inliers",
        ),
    ]
    return LocateResult(
        case_id="c", photos=photos, claimed_property_id="p1", thresholds_version=BASE.version
    )


def test_the_desk_gives_each_search_the_time_left_and_the_case_cap():
    locator = StubLocator(status=L.NOT_LOCATED, seconds=3.0)
    desk = PlaceDesk(
        located(),
        adapter(locator),
        scans={"S1": "m1", "S2": "m2"},
        thresholds=BASE,
        max_searches=5,
        case_seconds_left=8.0,
    )
    while desk.offer() is not None:
        desk.choose(
            type("P", (), {"chosen_by": "policy", "choose": lambda s, o: (o.default, "r")})()
        )
    deadlines = [c[4] for c in locator.calls]
    assert deadlines[0] == 8.0 and all(
        b < a for a, b in zip(deadlines, deadlines[1:], strict=False)
    )


def test_even_a_wrong_status_from_the_locator_cannot_place_or_condemn_a_photo():
    # the desk re-checks: 31 points and a thin spread is not "elsewhere", whatever the status says
    locator = StubLocator(
        status=L.LOCATED_ELSEWHERE,
        model_id="m9",
        inliers=31,
        inlier_ratio=0.3,
        spread=0.06,
        seconds=1.0,
    )
    desk = PlaceDesk(
        located(), adapter(locator), scans={"S1": "m1", "S2": "m2"}, thresholds=BASE, max_searches=3
    )
    while desk.offer() is not None:
        desk.choose(
            type("P", (), {"chosen_by": "policy", "choose": lambda s, o: (o.default, "r")})()
        )
    assert desk.located().photos[1].status is L.NOT_LOCATED


def test_the_dataclass_fields_the_adapter_reads_exist():
    assert {"inliers", "inlier_ratio", "spread", "rival_ratio", "bar_failed", "room_label"} <= {
        f for f in PhotoLocation.model_fields
    }
    assert dataclasses.is_dataclass(SearchOption)


def test_our_search_thresholds_match_lane_vs_values_until_theirs_is_imported():
    from snapback.agent.place import search_thresholds

    assert search_thresholds(BASE, SearchOption("wider_index")).top_k == 2 * BASE.top_k == 12
    assert search_thresholds(BASE, SearchOption("deeper_claimed")).top_k_claimed == 96
    assert search_thresholds(BASE, SearchOption("focus_scan", "S2", "m2")) == BASE
