"""V1 (#10): a photo not placed as sent is searched once more flipped left to right. Copied ads are
often mirrored to dodge photo checks; a mirrored copy should still be placed, and say so."""

import io
from dataclasses import replace

import pytest
from PIL import Image, ImageOps

from snapback.adapters.matterport import FixtureMatterport
from snapback.contracts import LocateStatus
from snapback.vision.embed import TinyEmbedder
from snapback.vision.locate.index import LocateIndex
from snapback.vision.locate.locate import Catalog, Locator, ModelInfo
from snapback.vision.locate.thresholds import load_thresholds
from snapback.vision.locate.verify import PatchMatcher

THRESHOLDS = replace(
    load_thresholds(), min_inliers=12, stop_at_inliers=60, elsewhere_min_inliers=16
)


@pytest.fixture(scope="module")
def twins(tmp_path_factory):
    adapter = FixtureMatterport(tmp_path_factory.mktemp("faces"))
    sweeps = {m: adapter.sweeps(m) for m in ("fx-model-a", "fx-model-b")}
    index = LocateIndex.build("fx", [s for ss in sweeps.values() for s in ss], TinyEmbedder())
    catalog = Catalog(
        [
            ModelInfo("fx-model-a", "fx-prop-1", rooms={"fx-sweep-02": "Bedroom"}),
            ModelInfo("fx-model-b", "fx-prop-2"),
        ]
    )
    return sweeps, index, catalog


def crop(sweeps, model="fx-model-a", sweep=2, face=1, mirror=False) -> Image.Image:
    with Image.open(sweeps[model][sweep].faces[face]) as opened:
        image = opened.convert("RGB").crop((30, 20, 230, 190))
    if mirror:
        image = ImageOps.mirror(image)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def locator(twins, **changes):
    sweeps, index, catalog = twins
    return Locator(index, sweeps, catalog, PatchMatcher(), replace(THRESHOLDS, **changes))


def test_the_flip_switch_is_on_in_the_frozen_thresholds():
    assert load_thresholds().flip_search is True


def test_a_mirrored_copy_is_placed_and_marked_flipped(twins):
    sweeps, _, _ = twins
    result, points = locator(twins).locate_with_points(
        "c", {"p": crop(sweeps, mirror=True)}, "fx-prop-1"
    )
    photo = result.photos[0]
    assert photo.status is LocateStatus.LOCATED_IN_CLAIMED and photo.flipped is True
    assert photo.pano_id == "fx-sweep-02" and photo.room_label == "Bedroom"
    assert "p" in result.poses and "p" in points


def test_without_the_flip_the_same_mirrored_copy_is_not_placed(twins):
    sweeps, _, _ = twins
    result = locator(twins, flip_search=False).locate(
        "c", {"p": crop(sweeps, mirror=True)}, "fx-prop-1"
    )
    assert result.photos[0].status is LocateStatus.NOT_LOCATED
    assert result.photos[0].flipped is None


def test_a_photo_placed_as_sent_is_never_flipped(twins):
    sweeps, _, _ = twins
    result = locator(twins).locate("c", {"p": crop(sweeps)}, "fx-prop-1")
    photo = result.photos[0]
    assert photo.status is LocateStatus.LOCATED_IN_CLAIMED and photo.flipped is None


def test_flipped_points_are_drawn_on_the_photo_as_sent(twins):
    """A flipped placement is matched on the un-mirrored copy; its points are mapped back onto the
    mirrored photo the ad sent, so they sit at 1 - x of the same points on the unflipped photo."""
    sweeps, _, _ = twins
    result, points = locator(twins).locate_with_points(
        "c", {"p": crop(sweeps, mirror=True)}, "fx-prop-1"
    )
    assert result.photos[0].flipped is True
    _, plain = locator(twins).locate_with_points("c", {"p": crop(sweeps)}, "fx-prop-1")
    sent_x = [x for x, _, _, _ in points["p"].sampled]
    plain_x = [x for x, _, _, _ in plain["p"].sampled]
    assert all(0.0 <= x <= 1.0 for x in sent_x)
    assert sum(sent_x) / len(sent_x) == pytest.approx(1 - sum(plain_x) / len(plain_x), abs=0.05)
    # the scan side is not flipped: the same view, the same points
    scan_u = sorted(round(u, 2) for _, _, u, _ in points["p"].sampled)
    plain_u = sorted(round(u, 2) for _, _, u, _ in plain["p"].sampled)
    assert sum(scan_u) / len(scan_u) == pytest.approx(sum(plain_u) / len(plain_u), abs=0.05)


def test_the_flip_never_places_a_photo_in_another_building_on_its_own(twins):
    """A mirrored copy of building B's view, claimed as building A: still the strict bar for
    elsewhere, and still never placed in A."""
    sweeps, _, _ = twins
    result = locator(twins).locate(
        "c", {"p": crop(sweeps, "fx-model-b", 1, 2, mirror=True)}, "fx-prop-1"
    )
    photo = result.photos[0]
    assert photo.status is not LocateStatus.LOCATED_IN_CLAIMED
    if photo.status is LocateStatus.LOCATED_ELSEWHERE:
        assert photo.matched_model_id == "fx-model-b" and photo.flipped is True


def test_an_identify_case_searches_flipped_too(twins):
    sweeps, _, _ = twins
    photos = {
        "p1": crop(sweeps, mirror=True),
        "p2": crop(sweeps, "fx-model-a", 0, 3, mirror=True),
    }
    result = locator(twins).locate("c", photos, None)
    assert result.identified_by_scan and result.claimed_property_id == "fx-prop-1"
    assert all(p.flipped is True for p in result.photos)
