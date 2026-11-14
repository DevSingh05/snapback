"""V2: verify and pose, on synthetic fixture twins with the numpy matcher (no torch needed)."""

import io
import math
import shutil
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from snapback.adapters.matterport import FixtureMatterport
from snapback.contracts import LocateResult, LocateStatus, Pose
from snapback.vision.embed import TinyEmbedder
from snapback.vision.locate.cube import (
    angle_between,
    face_basis,
    face_intrinsics,
    intrinsics,
    look_rotation,
    render,
)
from snapback.vision.locate.geometry import (
    camera_quaternion,
    matrix_from_quaternion,
    quaternion_from_matrix,
    ransac_homography,
    rotation_from_homography,
)
from snapback.vision.locate.index import LocateIndex
from snapback.vision.locate.locate import Catalog, Locator, ModelInfo, photo_hfov
from snapback.vision.locate.spots import rank_spots
from snapback.vision.locate.thresholds import load_thresholds
from snapback.vision.locate.verify import PatchMatcher, verify

# The numpy matcher finds fewer points than DISK+LightGlue, so the tests use a lower floor.
THRESHOLDS = replace(
    load_thresholds(), min_inliers=12, stop_at_inliers=60, elsewhere_min_inliers=16
)


def jpeg(image: Image.Image, quality: int = 85) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


@pytest.fixture(scope="module")
def twins(tmp_path_factory):
    cache = tmp_path_factory.mktemp("faces")
    adapter = FixtureMatterport(cache)
    sweeps = {m: adapter.sweeps(m) for m in ("fx-model-a", "fx-model-b")}
    index = LocateIndex.build("fx", [s for ss in sweeps.values() for s in ss], TinyEmbedder())
    rooms = {
        "fx-model-a": {
            "fx-sweep-00": "Kitchen",
            "fx-sweep-01": "Kitchen",
            "fx-sweep-02": "Bedroom",
            "fx-sweep-03": "Living Room",
        },
        "fx-model-b": {},
    }
    catalog = Catalog(
        [
            ModelInfo("fx-model-a", "fx-prop-1", "2 bed / 2 bath", rooms["fx-model-a"]),
            ModelInfo("fx-model-b", "fx-prop-2", "1 bed / 1 bath"),
            ModelInfo("fx-model-c", "fx-prop-3", "studio"),  # on record, not indexed
        ]
    )
    return sweeps, index, catalog


@pytest.fixture(scope="module")
def locator(twins):
    sweeps, index, catalog = twins
    return Locator(index, sweeps, catalog, PatchMatcher(), THRESHOLDS)


def listing_photo(sweeps, model: str, sweep: int, face: int) -> Image.Image:
    with Image.open(sweeps[model][sweep].faces[face]) as opened:
        face_image = opened.convert("RGB")
    return jpeg(face_image.crop((30, 20, 230, 190)))


# --- the three tests the issue names -----------------------------------------------------------


def test_locate_fixture_case_returns_located_in_claimed(twins, locator):
    sweeps, _, _ = twins
    photos = {
        "p1": listing_photo(sweeps, "fx-model-a", 2, 1),
        "p2": listing_photo(sweeps, "fx-model-a", 0, 3),
    }
    result = locator.locate("fx-case-1", photos, "fx-prop-1")

    assert isinstance(result, LocateResult)
    assert [p.status for p in result.photos] == [LocateStatus.LOCATED_IN_CLAIMED] * 2
    first = result.photos[0]
    assert first.matched_model_id == "fx-model-a" and first.matched_property_id == "fx-prop-1"
    assert first.pano_id == "fx-sweep-02" and first.room_label == "Bedroom"
    assert first.inliers >= THRESHOLDS.min_inliers
    assert result.poses["p1"].sweep_id == "fx-sweep-02"
    assert result.chosen.model_id == "fx-model-a" and result.chosen.photos_located == 2
    assert result.thresholds_version.startswith("thresholds-")


def test_photo_from_other_building_is_located_elsewhere(twins, locator):
    sweeps, _, _ = twins
    photos = {"p1": listing_photo(sweeps, "fx-model-a", 1, 2)}
    result = locator.locate("fx-case-2", photos, "fx-prop-2")

    photo = result.photos[0]
    assert photo.status is LocateStatus.LOCATED_ELSEWHERE
    assert photo.matched_model_id == "fx-model-a"
    assert photo.matched_property_id == "fx-prop-1"
    assert result.chosen is None  # nothing was placed in the claimed building


def test_spot_overlapping_listing_photo_is_excluded(twins):
    sweeps, _, catalog = twins
    model_sweeps = sweeps["fx-model-a"]
    rooms = catalog.models["fx-model-a"].rooms
    matcher = PatchMatcher()
    free = rank_spots(
        "fx-case-1",
        "fx-model-a",
        model_sweeps,
        rooms,
        matcher.count_features,
        thresholds=THRESHOLDS,
    )
    assert not any(s.overlaps_listing_photo for s in free.spots)
    kitchen = next(s for s in free.spots if "kitchen" in s.label)

    # A listing photo placed in the kitchen, looking the way the kitchen spot looks.
    listing = Pose(
        sweep_id=kitchen.pose.sweep_id,
        position=kitchen.pose.position,
        rotation_quat=kitchen.pose.rotation_quat,
        fov_deg=65.0,
    )
    ranked = rank_spots(
        "fx-case-1",
        "fx-model-a",
        model_sweeps,
        rooms,
        matcher.count_features,
        listing_poses=[listing],
        thresholds=THRESHOLDS,
    )

    flagged = [s for s in ranked.spots if s.overlaps_listing_photo]
    assert flagged and all("kitchen" in s.label for s in flagged)
    drawable = [s for s in ranked.spots if not s.overlaps_listing_photo]
    assert kitchen.spot_id not in {s.spot_id for s in drawable}
    assert len(drawable) <= THRESHOLDS.spots_top_n


# --- more locate behaviour ---------------------------------------------------------------------


def test_unrelated_photo_is_not_located(locator):
    rng = np.random.default_rng(7)
    noise = Image.fromarray(rng.integers(0, 255, (180, 220, 3), dtype=np.uint8), "RGB")
    result = locator.locate("fx-case-3", {"p1": noise}, "fx-prop-1")
    assert result.photos[0].status is LocateStatus.NOT_LOCATED
    assert result.photos[0].matched_model_id is None
    assert "p1" not in result.poses


def test_claimed_property_without_a_twin_is_not_indexed(locator):
    rng = np.random.default_rng(8)
    noise = Image.fromarray(rng.integers(0, 255, (180, 220, 3), dtype=np.uint8), "RGB")
    result = locator.locate("fx-case-4", {"p1": noise}, "fx-prop-3")
    assert result.photos[0].status is LocateStatus.NOT_INDEXED


def test_pose_points_the_way_the_photo_looks(twins, locator):
    sweeps, _, _ = twins
    result = locator.locate(
        "fx-case-5", {"p": listing_photo(sweeps, "fx-model-a", 3, 2)}, "fx-prop-1"
    )
    pose = result.poses["p"]
    sweep = sweeps["fx-model-a"][3]
    pano = matrix_from_quaternion(sweep.rotation_quat)
    face_forward = pano @ face_basis(2)[:, 2]
    looks = matrix_from_quaternion(pose.rotation_quat) @ np.array([0.0, 0.0, -1.0])
    assert angle_between(looks, face_forward) < 30
    assert pose.position == sweep.position


def test_hfov_comes_from_exif_when_present():
    image = Image.new("RGB", (400, 300))
    assert photo_hfov(image, 65.0) == 65.0
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0xA405] = 26  # a typical phone main camera
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    buffer.seek(0)
    assert photo_hfov(Image.open(buffer), 65.0) == pytest.approx(69.4, abs=0.2)


# --- geometry ----------------------------------------------------------------------------------


def test_ransac_recovers_a_known_homography_despite_outliers():
    rng = np.random.default_rng(0)
    h = np.array([[1.1, 0.05, 12.0], [-0.03, 0.95, -7.0], [1e-4, -5e-5, 1.0]])
    src = rng.uniform(0, 500, (120, 2))
    dst = np.c_[src, np.ones(120)] @ h.T
    dst = dst[:, :2] / dst[:, 2:]
    dst[:30] = rng.uniform(0, 500, (30, 2))  # a quarter are wrong matches
    found, mask = ransac_homography(src, dst, threshold_px=1.0)
    assert mask[30:].all() and mask[:30].sum() <= 2
    assert np.allclose(found / found[2, 2], h, atol=1e-3)


def test_rotation_from_a_pure_rotation_homography():
    r = look_rotation(12, -7)
    k_a, k_b = intrinsics(640, 480, 60), face_intrinsics(512)
    h = k_b @ r @ np.linalg.inv(k_a)
    assert np.allclose(rotation_from_homography(h, k_a, k_b), r, atol=1e-6)


def test_quaternion_round_trip():
    r = look_rotation(37, 11)
    assert np.allclose(matrix_from_quaternion(quaternion_from_matrix(r)), r, atol=1e-9)


def test_camera_quaternion_looks_along_the_camera_forward():
    camera_to_world = look_rotation(-40, 15)
    looks = matrix_from_quaternion(camera_quaternion(camera_to_world)) @ np.array([0, 0, -1.0])
    assert angle_between(looks, camera_to_world[:, 2]) < 1e-6


def test_render_at_a_face_reproduces_the_face(twins):
    sweeps, _, _ = twins
    faces = [Image.open(p).convert("RGB") for p in sweeps["fx-model-a"][0].faces]
    side = faces[1].size[0]
    for face, rotation in ((1, look_rotation(0, 0)), (2, look_rotation(90, 0)), (0, face_basis(0))):
        out = render(faces, rotation, 90.0, (side, side))
        error = np.abs(np.asarray(out, np.float32) - np.asarray(faces[face], np.float32)).mean()
        assert error < 1.0


def test_rendered_view_verifies_against_its_face(twins):
    sweeps, _, _ = twins
    faces = [Image.open(p).convert("RGB") for p in sweeps["fx-model-a"][1].faces]
    view = render(faces, look_rotation(0, 0), 90.0, (256, 256)).crop((20, 20, 236, 236))
    check = verify(PatchMatcher(), view, faces[1], ransac_px=3.0)
    assert check.inliers >= 12 and check.ratio > 0.5


def test_thresholds_version_changes_with_the_file(tmp_path):
    from snapback.vision.locate.thresholds import THRESHOLDS_FILE

    copy = tmp_path / "t.toml"
    copy.write_text(THRESHOLDS_FILE.read_text())
    same = load_thresholds(copy).version
    copy.write_text(THRESHOLDS_FILE.read_text().replace("min_inliers = 30", "min_inliers = 31"))
    assert load_thresholds(copy).version != same == load_thresholds().version
    assert math.isfinite(load_thresholds().ransac_px)


# --- claimed twin first, strict bar elsewhere (PR #111 FIX 1) -----------------------------------


def sister_sweeps(sweeps, tmp_path):
    """The same rooms again as another building's twin: a model with identical faces."""
    copied = []
    for sweep in sweeps["fx-model-a"]:
        faces = []
        for number, face in enumerate(sweep.faces):
            target = tmp_path / sweep.sweep_id / f"{number}{face.suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(face, target)
            faces.append(target)
        copied.append(replace(sweep, model_id="fx-model-sister", faces=tuple(faces)))
    return copied


@pytest.mark.parametrize("sister_first", [True, False])
def test_sister_twin_never_beats_the_claimed_building(twins, tmp_path, sister_first):
    sweeps, _, catalog = twins
    sister = sister_sweeps(sweeps, tmp_path)
    ordered = [sister, sweeps["fx-model-a"]] if sister_first else [sweeps["fx-model-a"], sister]
    index = LocateIndex.build("fx-sister", [s for group in ordered for s in group], TinyEmbedder())
    models = [*catalog.models.values(), ModelInfo("fx-model-sister", "fx-prop-9")]
    all_sweeps = {"fx-model-a": sweeps["fx-model-a"], "fx-model-sister": sister}
    locator = Locator(index, all_sweeps, Catalog(models), PatchMatcher(), THRESHOLDS)

    photo = listing_photo(sweeps, "fx-model-a", 2, 1)
    result = locator.locate("fx-sister", {"p": photo}, "fx-prop-1")

    assert result.photos[0].status is LocateStatus.LOCATED_IN_CLAIMED
    assert result.photos[0].matched_property_id == "fx-prop-1"
    assert result.chosen.model_id == "fx-model-a"


def test_match_elsewhere_below_the_strict_bar_is_not_located(twins):
    sweeps, index, catalog = twins
    photos = {"p1": listing_photo(sweeps, "fx-model-a", 1, 2)}  # claims prop-2, shows prop-1
    for strict in (
        replace(THRESHOLDS, elsewhere_min_inliers=40),  # too few inliers for "another building"
        replace(THRESHOLDS, elsewhere_min_spread=0.99),  # inliers packed into one small area
    ):
        locator = Locator(index, sweeps, catalog, PatchMatcher(), strict)
        photo = locator.locate("fx-strict", photos, "fx-prop-2").photos[0]
        assert photo.status is LocateStatus.NOT_LOCATED
        assert photo.matched_model_id is None


def test_verify_reports_how_far_the_inliers_spread(twins):
    sweeps, _, _ = twins
    face = Image.open(sweeps["fx-model-a"][1].faces[1]).convert("RGB")
    check = verify(PatchMatcher(), face.crop((30, 20, 230, 190)), face, ransac_px=6.0)
    assert 0.2 < check.spread <= 1.0
    assert verify(PatchMatcher(), face.crop((0, 0, 4, 4)), face, ransac_px=6.0).spread == 0.0


def test_gate_counts_claimed_views_placed_elsewhere_and_not_located(twins, locator):
    from snapback.eval.locate_gate import claimed_outcome_lines

    sweeps, _, _ = twins
    noise = Image.fromarray(
        np.random.default_rng(9).integers(0, 255, (180, 220, 3), dtype=np.uint8), "RGB"
    )
    results = [
        locator.locate("g1", {"p": listing_photo(sweeps, "fx-model-a", 2, 1)}, "fx-prop-1"),
        locator.locate("g2", {"p": listing_photo(sweeps, "fx-model-a", 0, 3)}, "fx-prop-1"),
        locator.locate("g3", {"p": listing_photo(sweeps, "fx-model-a", 1, 2)}, "fx-prop-2"),
        locator.locate("g4", {"p": noise}, "fx-prop-1"),
    ]
    lines = claimed_outcome_lines([r.photos[0].status for r in results])
    assert lines == [
        "views of the claimed building placed in another building: 1 of 4",
        "not located: 1 of 4",
    ]


def test_unmapped_twin_is_not_located_never_elsewhere(twins):
    sweeps, index, _ = twins
    catalog = Catalog([ModelInfo("fx-model-b", "fx-prop-2")])  # fx-model-a is not mapped
    locator = Locator(index, sweeps, catalog, PatchMatcher(), THRESHOLDS)
    photo = locator.locate(
        "fx-unmapped", {"p": listing_photo(sweeps, "fx-model-a", 2, 1)}, "fx-prop-1"
    ).photos[0]
    assert photo.status is not LocateStatus.LOCATED_ELSEWHERE
    assert photo.status in (LocateStatus.NOT_LOCATED, LocateStatus.NOT_INDEXED)
    assert photo.matched_property_id is None


def test_thresholds_reject_an_elsewhere_bar_below_the_placement_bar(tmp_path):
    from snapback.vision.locate.thresholds import THRESHOLDS_FILE

    copy = tmp_path / "t.toml"
    import re

    text, swapped = re.subn(
        r"elsewhere_min_inliers = \d+", "elsewhere_min_inliers = 29", THRESHOLDS_FILE.read_text()
    )
    assert swapped == 1  # the edit must land, whatever the current value is
    copy.write_text(text)
    with pytest.raises(ValueError, match="elsewhere_min_inliers"):
        load_thresholds(copy)


def test_thresholds_version_names_the_matcher(twins, locator):
    sweeps, _, _ = twins
    photo = listing_photo(sweeps, "fx-model-a", 2, 1)
    result = locator.locate("fx-case-v", {"p": photo}, "fx-prop-1")
    assert result.thresholds_version.startswith("thresholds-")
    assert result.thresholds_version.endswith("+patch")


def test_seam_neighbours_add_the_faces_either_side_of_the_top_two_hits():
    from snapback.vision.locate.index import Entry, Hit
    from snapback.vision.locate.locate import seam_neighbours

    hits = [
        Hit(Entry("m1", "s1", 1, "c"), 0.9),
        Hit(Entry("m2", "s4", 4, "face"), 0.8),
        Hit(Entry("m3", "s9", 2, "c"), 0.7),  # third hit: no neighbours added
    ]
    added = {(h.entry.model_id, h.entry.sweep_id, h.entry.face) for h in seam_neighbours(hits)}
    assert added == {("m1", "s1", 4), ("m1", "s1", 2), ("m2", "s4", 3), ("m2", "s4", 1)}
    assert all(h.score < 0.7 for h in seam_neighbours(hits))  # tried after the real hits


def test_elsewhere_bar_follows_the_ruling():
    t = load_thresholds()
    assert t.elsewhere_min_inliers == 50 and t.elsewhere_min_spread == 0.15


# --- ambiguity rule (conductor ruling 03:46 on #28) ----------------------------------------------


def _scripted_verify(inliers_by_model):
    """A verify() stand-in: every face of a model gets that model's inlier count, spread 0.5."""
    from snapback.vision.locate.verify import FEATURE_KEY, Verification

    def fake(matcher, photo, face, ransac_px):
        model = face.info[FEATURE_KEY].split("/")[0]
        n = inliers_by_model.get(model, 0)
        return Verification(max(n, 4), n, np.eye(3) if n else None, 0.5 if n else 0.0)

    return fake


@pytest.mark.parametrize(
    ("claimed_inliers", "other_inliers", "expected"),
    [
        (70, 390, LocateStatus.NOT_LOCATED),  # another building is far stronger: could not place
        (390, 70, LocateStatus.LOCATED_IN_CLAIMED),
        (100, 290, LocateStatus.LOCATED_IN_CLAIMED),  # under 3x: claimed-first still holds
        (100, 300, LocateStatus.NOT_LOCATED),  # exactly 3x counts as far stronger
        (70, 45, LocateStatus.LOCATED_IN_CLAIMED),  # other under the strict bar never counts
    ],
)
def test_a_far_stronger_match_elsewhere_makes_the_photo_unplaced(
    twins, locator, monkeypatch, claimed_inliers, other_inliers, expected
):
    sweeps, _, _ = twins
    monkeypatch.setattr(
        "snapback.vision.locate.locate.verify",
        _scripted_verify({"fx-model-a": claimed_inliers, "fx-model-b": other_inliers}),
    )
    photo = listing_photo(sweeps, "fx-model-a", 2, 1)
    result = locator.locate("fx-amb", {"p": photo}, "fx-prop-1")
    assert result.photos[0].status is expected
    if expected is LocateStatus.NOT_LOCATED:
        assert result.photos[0].matched_model_id is None and "p" not in result.poses


def test_ambiguity_ratio_is_in_thresholds():
    assert load_thresholds().ambiguity_ratio == 3.0
