"""The live adapter, built against lane V's `SearchResult` (#223 @ 5b58080). When that class is
importable (once #223 is on this branch) the test uses it; until then a stub with the same field
names stands in. The real `Locator.search` is never imported here."""

from dataclasses import dataclass

import pytest

from snapback.agent.place import PlaceDesk, SearchOption
from snapback.agent.place_locator import LocatorSearcher
from snapback.contracts import EvidencePoints, LocateResult, LocateStatus, PhotoLocation, Pose
from snapback.vision.locate.thresholds import load_thresholds

BASE = load_thresholds()
L = LocateStatus


@dataclass(frozen=True)
class StubResult:
    """Same field names as `locate.SearchResult` in #223 (5b58080)."""

    option: str
    location: PhotoLocation | None = None
    pose: Pose | None = None
    points: EvidencePoints | None = None
    identified_property_id: str | None = None
    verified: int = 0
    seconds: float = 0.0
    timed_out: bool = False


try:  # the real class, when #223 is on this branch
    from snapback.vision.locate.locate import SearchResult as Result
except ImportError:
    Result = StubResult


class StubLocator:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def search(
        self,
        photo,
        option,
        claimed_property_id,
        *,
        scan_model_id=None,
        deadline_s=None,
        photo_id="p",
    ):
        self.calls.append((photo, option, claimed_property_id, scan_model_id, deadline_s, photo_id))
        return self.result


def adapter(locator):
    return LocatorSearcher(locator, photo_for=lambda pid: f"image-of-{pid}")


def test_the_stub_has_the_real_result_class_s_field_names():
    if Result is StubResult:
        pytest.skip("lane V's SearchResult is not on this branch yet")
    assert set(StubResult.__dataclass_fields__) <= set(Result.__dataclass_fields__)


def test_the_adapter_passes_image_option_scan_deadline_and_photo_id_by_the_real_names():
    locator = StubLocator(Result(option="focus_scan", seconds=1.5))
    out = adapter(locator).search(
        "l2", SearchOption("focus_scan", "S2", "m2"), "fx-prop-1", BASE, 7.5
    )
    assert locator.calls == [("image-of-l2", "focus_scan", "fx-prop-1", "m2", 7.5, "l2")]
    assert out.location.status is L.NOT_LOCATED and out.seconds == 1.5  # location None: a miss


def test_the_location_pose_and_points_come_through_unchanged():
    points = EvidencePoints(n_total=90, sampled=[(i / 100, 0.5, i / 100, 0.5) for i in range(48)])
    pose = Pose(sweep_id="sw1", position=(0, 0, 0), rotation_quat=(0, 0, 0, 1))
    found = PhotoLocation(
        photo_id="p",
        status=L.LOCATED_IN_CLAIMED,
        model_id="m2",
        pano_id="sw1",
        inliers=88,
        inlier_ratio=0.41,
        spread=0.31,
        rival_ratio=0.05,
        matched_model_id="m2",
        matched_property_id="p1",
        room_label="Kitchen",
    )
    result = Result(option="wider_index", location=found, pose=pose, points=points, seconds=2.1)
    out = adapter(StubLocator(result)).search("l4", SearchOption("wider_index"), "p1", BASE, 10.0)
    assert out.location == found.model_copy(update={"photo_id": "l4"})  # keyed by OUR photo id
    assert out.pose == pose and out.points == points and out.points.n_total == 90


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


class Policy:
    chosen_by = "policy"

    def choose(self, offer):
        return offer.default, "r"


def drive(desk):
    while desk.offer() is not None:
        desk.choose(Policy())


def test_the_desk_gives_each_search_the_time_left_and_the_case_cap():
    locator = StubLocator(Result(option="x", seconds=3.0))
    desk = PlaceDesk(
        located(),
        adapter(locator),
        scans={"S1": "m1", "S2": "m2"},
        thresholds=BASE,
        max_searches=5,
        case_seconds_left=8.0,
    )
    drive(desk)
    deadlines = [c[4] for c in locator.calls]
    assert deadlines[0] == 8.0 and all(
        b < a for a, b in zip(deadlines, deadlines[1:], strict=False)
    )


def test_even_a_wrong_status_from_the_locator_cannot_place_or_condemn_a_photo():
    thin = PhotoLocation(
        photo_id="p",
        status=L.LOCATED_ELSEWHERE,
        model_id="m9",
        inliers=31,
        inlier_ratio=0.3,
        spread=0.06,
        matched_property_id="p-other",
    )
    locator = StubLocator(Result(option="x", location=thin, seconds=1.0))
    desk = PlaceDesk(
        located(),
        adapter(locator),
        scans={"S1": "m1", "S2": "m2"},
        thresholds=BASE,
        max_searches=3,
    )
    drive(desk)
    assert desk.located().photos[1].status is L.NOT_LOCATED


def test_our_search_thresholds_match_lane_vs_values_until_theirs_is_imported():
    from snapback.agent.place import search_thresholds

    assert search_thresholds(BASE, SearchOption("wider_index")).top_k == 2 * BASE.top_k == 12
    assert search_thresholds(BASE, SearchOption("deeper_claimed")).top_k_claimed == 96
    assert search_thresholds(BASE, SearchOption("focus_scan", "S2", "m2")) == BASE
