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


def test_a_reflecting_homography_is_not_a_match():
    """No real view change mirrors the photo: a reflecting homography gives no inliers."""
    import numpy as np

    from snapback.vision.locate.verify import reflects

    size = (200, 170)
    assert not reflects(np.eye(3), size)
    assert not reflects(np.array([[1.2, 0.1, 5.0], [-0.05, 0.9, 3.0], [1e-4, 0.0, 1.0]]), size)
    mirror = np.array([[-1.0, 0.0, 200.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    assert reflects(mirror, size)


def test_a_mirrored_copy_is_placed_only_through_the_flip(twins):
    """With the reflection guard, the as-sent search cannot place a mirrored copy; only the
    flipped search does, so it is always marked flipped."""
    sweeps, _, _ = twins
    off = locator(twins, flip_search=False).locate(
        "c", {"p": crop(sweeps, mirror=True)}, "fx-prop-1"
    )
    assert off.photos[0].status is LocateStatus.NOT_LOCATED
    on = locator(twins).locate("c", {"p": crop(sweeps, mirror=True)}, "fx-prop-1")
    assert on.photos[0].status is LocateStatus.LOCATED_IN_CLAIMED and on.photos[0].flipped is True


def test_a_doubtful_claimed_match_is_never_flipped_into_another_building(twins, monkeypatch):
    """Reviewer probe (#272 FIX 1): as sent, the photo has a tight but doubtful patch in the claimed
    home (the spread bar) and nothing strict elsewhere; mirrored, the claimed home is weak and a
    sister building matches strictly. A doubtful photo is never searched elsewhere (ruling 07:43,
    #28), so the flip must not run and the photo must not be placed in the other building."""
    import hashlib

    import numpy as np

    from snapback.vision.locate.verify import FEATURE_KEY, Verification

    sweeps, _, _ = twins
    photo = crop(sweeps, "fx-model-b", 1, 2)
    sent_hash = hashlib.sha256(photo.convert("RGB").tobytes()).hexdigest()

    def recorded(matcher, image, face, ransac_px):
        model = face.info[FEATURE_KEY].split("/")[0]
        if hashlib.sha256(image.tobytes()).hexdigest() == sent_hash:
            n, spread = {"fx-model-a": (70, 0.018), "fx-model-b": (119, 0.218)}.get(model, (0, 0.0))
        else:
            n, spread = {"fx-model-b": (119, 0.218)}.get(model, (0, 0.0))
        return Verification(max(n, 4), n, np.eye(3) if n else None, spread)

    monkeypatch.setattr("snapback.vision.locate.locate.verify", recorded)
    result = locator(twins).locate("c", {"p": photo}, "fx-prop-1")
    placed = result.photos[0]
    assert placed.status is not LocateStatus.LOCATED_ELSEWHERE
    assert placed.status is LocateStatus.NOT_LOCATED
    assert placed.bar_failed == "spread" and not placed.flipped


def test_a_flipped_match_below_the_strict_ratio_is_not_placed_elsewhere(twins, monkeypatch):
    """#296 composition: the flip runs under the same strict bar, 60 percent consistent included.
    Mirrored, building B clears the counts but only 43 percent of its matches agree."""
    import hashlib

    import numpy as np

    from snapback.vision.locate.verify import FEATURE_KEY, Verification

    sweeps, _, _ = twins
    photo = crop(sweeps, "fx-model-b", 1, 2)
    sent_hash = hashlib.sha256(photo.convert("RGB").tobytes()).hexdigest()

    def recorded(matcher, image, face, ransac_px):
        model = face.info[FEATURE_KEY].split("/")[0]
        if hashlib.sha256(image.tobytes()).hexdigest() == sent_hash or model != "fx-model-b":
            return Verification(4, 0, None, 0.0)
        return Verification(140, 60, np.eye(3), 0.3)

    monkeypatch.setattr("snapback.vision.locate.locate.verify", recorded)
    result = locator(twins).locate("c", {"p": photo}, "fx-prop-1")
    assert result.photos[0].status is LocateStatus.NOT_LOCATED
