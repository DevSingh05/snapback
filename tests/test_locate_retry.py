"""E2a: the place sub-agent's retry primitive. `Locator.search(photo, option, claimed)` re-runs
placement with more candidates of a chosen kind, under the very same bars."""

import io
from dataclasses import fields, replace

import pytest
from PIL import Image

from snapback.adapters.matterport import FixtureMatterport
from snapback.contracts import LocateStatus
from snapback.vision.embed import TinyEmbedder
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
from snapback.vision.locate.verify import PatchMatcher

THRESHOLDS = replace(
    load_thresholds(), min_inliers=12, stop_at_inliers=60, elsewhere_min_inliers=16
)


@pytest.fixture(scope="module")
def twins(tmp_path_factory):
    adapter = FixtureMatterport(tmp_path_factory.mktemp("faces"))
    sweeps = {m: adapter.sweeps(m) for m in ("fx-model-a", "fx-model-b")}
    index = LocateIndex.build("fx", [s for ss in sweeps.values() for s in ss], TinyEmbedder())
    catalog = Catalog([ModelInfo("fx-model-a", "fx-prop-1"), ModelInfo("fx-model-b", "fx-prop-2")])
    return sweeps, index, catalog


@pytest.fixture
def locator(twins):
    sweeps, index, catalog = twins
    return Locator(index, sweeps, catalog, PatchMatcher(), THRESHOLDS)


def photo(sweeps, model: str, sweep: int, face: int) -> Image.Image:
    with Image.open(sweeps[model][sweep].faces[face]) as opened:
        crop = opened.convert("RGB").crop((30, 20, 230, 190))
    buffer = io.BytesIO()
    crop.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


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


@pytest.mark.parametrize("option", ["focus_scan", "wider_index", "deeper_claimed"])
def test_every_option_places_a_claimed_photo_like_the_base_locator(twins, locator, option):
    sweeps, _, _ = twins
    result = locator.search(photo(sweeps, "fx-model-a", 2, 1), option, "fx-prop-1")
    assert result.option == option
    assert result.status is LocateStatus.LOCATED_IN_CLAIMED
    assert result.model_id == "fx-model-a" and result.sweep_id == "fx-sweep-02"
    assert result.verified >= 1 and result.seconds >= 0.0


def test_stop_does_no_work(twins, locator, monkeypatch):
    sweeps, _, _ = twins
    monkeypatch.setattr(
        "snapback.vision.locate.locate.verify", lambda *a: pytest.fail("verify ran on stop")
    )
    result = locator.search(photo(sweeps, "fx-model-a", 2, 1), "stop", "fx-prop-1")
    assert result.option == "stop" and result.status is None and result.verified == 0


def test_each_option_widens_the_kind_of_candidate_it_names(twins, locator):
    sweeps, _, _ = twins
    image = photo(sweeps, "fx-model-a", 2, 1)
    base = locator.candidates_for(image, {"fx-model-a"}, "base")
    wider = locator.candidates_for(image, {"fx-model-a"}, "wider_index")
    deeper = locator.candidates_for(image, {"fx-model-a"}, "deeper_claimed")
    focus = locator.candidates_for(image, {"fx-model-a"}, "focus_scan")

    def keys(hits):
        return {(h.entry.model_id, h.entry.sweep_id, h.entry.face) for h in hits}

    assert keys(base) <= keys(wider) and keys(base) <= keys(deeper) and keys(base) <= keys(focus)
    assert len(keys(focus)) > len(keys(base))
    # focus_scan adds every face of the sweeps the best hits came from
    top_sweep = (base[0].entry.model_id, base[0].entry.sweep_id)
    assert {(top_sweep[0], top_sweep[1], f) for f in range(6)} <= keys(focus)


def test_an_unknown_option_is_refused(twins, locator):
    sweeps, _, _ = twins
    with pytest.raises(ValueError, match="option"):
        locator.search(photo(sweeps, "fx-model-a", 2, 1), "everything", "fx-prop-1")


def test_a_search_never_accepts_weaker_evidence_than_the_base(twins, locator, monkeypatch):
    """Same bars: a claimed match under min_inliers stays unplaced whatever the option."""
    from snapback.vision.locate.verify import Verification

    monkeypatch.setattr(
        "snapback.vision.locate.locate.verify",
        lambda matcher, photo, face, px: Verification(20, 11, None, 0.5),
    )
    sweeps, _, _ = twins
    for option in ("focus_scan", "wider_index", "deeper_claimed"):
        result = locator.search(photo(sweeps, "fx-model-a", 2, 1), option, "fx-prop-1")
        assert result.status is LocateStatus.NOT_LOCATED, option


def test_search_thresholds_match_the_plan():
    base = load_thresholds()
    assert (base.top_k, base.top_k_claimed) == (6, 48)
    assert search_thresholds(base, "wider_index").top_k == 12
    assert search_thresholds(base, "deeper_claimed").top_k_claimed == 96
    assert search_thresholds(base, "focus_scan") == base == search_thresholds(base, "stop")
    with pytest.raises(ValueError, match="option"):
        search_thresholds(base, "everything")
