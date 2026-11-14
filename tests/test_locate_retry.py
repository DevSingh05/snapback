"""E2a: the place sub-agent's retry primitive. `Locator.search(photo, option, claimed)` re-runs
placement through the routine locate() runs, with more candidates of a chosen kind, under the
very same bars and guards."""

import io
from dataclasses import fields, replace

import numpy as np
import pytest
from PIL import Image

from snapback.adapters.matterport import FixtureMatterport
from snapback.contracts import EvidencePoints, LocateStatus, PhotoLocation, Pose
from snapback.vision.embed import TinyEmbedder
from snapback.vision.locate.cube import SIDE_FACES
from snapback.vision.locate.index import LocateIndex
from snapback.vision.locate.locate import (
    RETRIEVAL_FIELDS,
    SEARCH_OPTIONS,
    Catalog,
    Locator,
    ModelInfo,
    retrieve_only,
    search_thresholds,
)
from snapback.vision.locate.thresholds import load_thresholds
from snapback.vision.locate.verify import FEATURE_KEY, PatchMatcher, Verification

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
            ModelInfo("fx-model-c", "fx-prop-3"),  # on record, not indexed
        ]
    )
    return sweeps, index, catalog


@pytest.fixture
def locator(twins):
    sweeps, index, catalog = twins
    return Locator(index, sweeps, catalog, PatchMatcher(), THRESHOLDS)


def photo(sweeps, model: str = "fx-model-a", sweep: int = 2, face: int = 1) -> Image.Image:
    with Image.open(sweeps[model][sweep].faces[face]) as opened:
        crop = opened.convert("RGB").crop((30, 20, 230, 190))
    buffer = io.BytesIO()
    crop.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def scripted(per_model):
    """verify() stand-in: model -> (inliers, spread) for every face of that model."""

    def fake(matcher, image, face, ransac_px):
        n, spread = per_model.get(face.info[FEATURE_KEY].split("/")[0], (0, 0.0))
        pairs = np.array([[i, i, i + 1, i + 1] for i in range(n)], dtype=float) if n else None
        return Verification(max(n, 4), n, np.eye(3) if n else None, spread, pairs)

    return fake


# --- the options and the thresholds -------------------------------------------------------------


def test_the_options_are_the_four_named():
    assert SEARCH_OPTIONS == ("focus_scan", "wider_index", "deeper_claimed", "stop")


def test_retrieve_only_changes_retrieval_and_refuses_any_bar():
    t = load_thresholds()
    wider = retrieve_only(t, top_k=2 * t.top_k)
    assert wider.top_k == 2 * t.top_k
    for field in fields(t):
        if field.name not in RETRIEVAL_FIELDS:
            assert getattr(wider, field.name) == getattr(t, field.name)
    for bar in ("min_inliers", "elsewhere_min_inliers", "claimed_min_spread", "ambiguity_ratio"):
        with pytest.raises(ValueError, match="retrieval only"):
            retrieve_only(t, **{bar: 1})


def test_search_thresholds_match_the_plan():
    base = load_thresholds()
    assert (base.top_k, base.top_k_claimed) == (6, 48)
    assert search_thresholds(base, "wider_index").top_k == 12
    assert search_thresholds(base, "deeper_claimed").top_k_claimed == 96
    assert search_thresholds(base, "focus_scan") == base == search_thresholds(base, "stop")
    with pytest.raises(ValueError, match="option"):
        search_thresholds(base, "everything")


# --- a search reports what locate() would ---------------------------------------------------------


@pytest.mark.parametrize("option", ["focus_scan", "wider_index", "deeper_claimed"])
def test_every_option_places_a_claimed_photo_with_a_full_result(twins, locator, option):
    sweeps, _, _ = twins
    result = locator.search(photo(sweeps), option, "fx-prop-1", scan_model_id="fx-model-a")
    loc = result.location
    assert isinstance(loc, PhotoLocation) and result.option == option
    assert loc.status is LocateStatus.LOCATED_IN_CLAIMED
    assert loc.matched_model_id == "fx-model-a" and loc.matched_property_id == "fx-prop-1"
    assert loc.pano_id == "fx-sweep-02" and loc.room_label == "Bedroom"
    assert loc.inliers and loc.inlier_ratio and loc.spread is not None and loc.bar_failed is None
    assert isinstance(result.pose, Pose) and isinstance(result.points, EvidencePoints)
    assert result.verified >= 1 and not result.timed_out


def test_a_search_matches_locate_for_the_same_photo(twins, locator):
    sweeps, _, _ = twins
    image = photo(sweeps)
    located = locator.locate("fx-same", {"p": image}, "fx-prop-1").photos[0]
    searched = locator.search(image, "wider_index", "fx-prop-1").location
    assert (
        searched.status is located.status and searched.matched_model_id == located.matched_model_id
    )


def test_stop_does_no_work(twins, locator, monkeypatch):
    sweeps, _, _ = twins
    monkeypatch.setattr(
        "snapback.vision.locate.locate.verify", lambda *a: pytest.fail("verify ran on stop")
    )
    result = locator.search(photo(sweeps), "stop", "fx-prop-1")
    assert result.option == "stop" and result.location is None and result.verified == 0


def test_an_unknown_option_is_refused(twins, locator):
    sweeps, _, _ = twins
    with pytest.raises(ValueError, match="option"):
        locator.search(photo(sweeps), "everything", "fx-prop-1")


def test_a_search_never_accepts_weaker_evidence_than_the_base(twins, locator, monkeypatch):
    """Same bars: a claimed match under min_inliers stays unplaced whatever the option."""
    monkeypatch.setattr("snapback.vision.locate.locate.verify", scripted({"fx-model-a": (11, 0.5)}))
    sweeps, _, _ = twins
    for option in ("focus_scan", "wider_index", "deeper_claimed"):
        result = locator.search(photo(sweeps), option, "fx-prop-1", scan_model_id="fx-model-a")
        assert result.status is LocateStatus.NOT_LOCATED, option
        assert result.location.bar_failed == "inliers"


# --- the three guards locate() has (review on #223) ----------------------------------------------


def test_a_match_in_a_building_the_catalog_cannot_name_is_never_elsewhere(twins, monkeypatch):
    """(a) An indexed twin with no property on record: locate() drops it, so must search()."""
    sweeps, index, _ = twins
    partial = Catalog([ModelInfo("fx-model-a", "fx-prop-1")])  # fx-model-b is unknown
    locator = Locator(index, sweeps, partial, PatchMatcher(), THRESHOLDS)
    monkeypatch.setattr(
        "snapback.vision.locate.locate.verify", scripted({"fx-model-b": (300, 0.6)})
    )
    for option in ("wider_index", "deeper_claimed"):
        result = locator.search(photo(sweeps, "fx-model-b", 1, 2), option, "fx-prop-1")
        assert result.status is LocateStatus.NOT_LOCATED, option
        assert result.location.matched_model_id is None and result.location.bar_failed is not None


def test_a_claimed_home_with_no_indexed_scan_is_not_indexed(twins, locator):
    """(b) Claimed home on record but not indexed: not_indexed, never elsewhere."""
    sweeps, _, _ = twins
    for option in ("wider_index", "deeper_claimed"):
        result = locator.search(photo(sweeps, "fx-model-b", 1, 2), option, "fx-prop-3")
        assert result.status is LocateStatus.NOT_INDEXED, option
        assert result.location.matched_model_id is None


def test_no_claimed_home_identifies_the_home_like_locate(twins, locator):
    """(c) No claimed home: the identify rules (strict bar in any building) name the home."""
    sweeps, _, _ = twins
    image = photo(sweeps)
    located = locator.locate("fx-id", {"p": image}, None)
    result = locator.search(image, "wider_index", None)
    assert result.status is located.photos[0].status
    assert result.identified_property_id == (
        located.claimed_property_id if located.identified_by_scan else None
    )
    assert result.status is not LocateStatus.LOCATED_ELSEWHERE


# --- focus_scan names one scan ------------------------------------------------------------------


def test_focus_scan_verifies_only_the_named_scans_side_faces(twins, locator):
    sweeps, _, _ = twins
    image = photo(sweeps)
    focus = locator.candidates_for(image, "fx-prop-1", "focus_scan", scan_model_id="fx-model-a")
    claimed = [h for h in focus if h.entry.model_id == "fx-model-a"]
    assert claimed and all(h.entry.face in SIDE_FACES for h in claimed)
    assert len(claimed) <= THRESHOLDS.top_k_claimed + THRESHOLDS.top_k
    side_faces = {(s.sweep_id, f) for s in sweeps["fx-model-a"] for f in SIDE_FACES}
    focused = {(h.entry.sweep_id, h.entry.face) for h in claimed if h.entry.face in SIDE_FACES}
    assert focused == side_faces  # 16 side faces <= top_k_claimed: all of them


def test_focus_scan_needs_a_scan_of_the_claimed_home(twins, locator):
    sweeps, _, _ = twins
    with pytest.raises(ValueError, match="scan_model_id"):
        locator.search(photo(sweeps), "focus_scan", "fx-prop-1")
    with pytest.raises(ValueError, match="scan_model_id"):
        locator.search(photo(sweeps), "focus_scan", "fx-prop-1", scan_model_id="fx-model-b")


# --- the deadline ---------------------------------------------------------------------------------


def test_a_passed_deadline_stops_verifying_and_reports_not_located(twins, locator):
    sweeps, _, _ = twins
    result = locator.search(photo(sweeps), "deeper_claimed", "fx-prop-1", deadline_s=0.0)
    assert result.timed_out and result.verified == 0
    assert result.status is LocateStatus.NOT_LOCATED and result.location.bar_failed == "inliers"
    assert result.pose is None and result.points is None
    # the deadline belongs to that search only
    after = locator.search(photo(sweeps), "deeper_claimed", "fx-prop-1")
    assert after.status is LocateStatus.LOCATED_IN_CLAIMED and not after.timed_out
