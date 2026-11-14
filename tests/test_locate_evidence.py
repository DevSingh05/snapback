"""E2b: what verification measured, kept for the evidence file: spread, rival_ratio, bar_failed on
every photo, and up to 48 normalised matched pairs that never reach a log or a chooser payload."""

import io
import json
import logging
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from snapback.adapters.matterport import FixtureMatterport
from snapback.contracts import EvidencePoints, LocateStatus
from snapback.vision.embed import TinyEmbedder
from snapback.vision.locate.index import LocateIndex
from snapback.vision.locate.locate import Catalog, Locator, ModelInfo
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
    catalog = Catalog([ModelInfo("fx-model-a", "fx-prop-1"), ModelInfo("fx-model-b", "fx-prop-2")])
    return sweeps, index, catalog


@pytest.fixture
def locator(twins):
    sweeps, index, catalog = twins
    return Locator(index, sweeps, catalog, PatchMatcher(), THRESHOLDS)


def photo(sweeps, model="fx-model-a", sweep=2, face=1) -> Image.Image:
    with Image.open(sweeps[model][sweep].faces[face]) as opened:
        crop = opened.convert("RGB").crop((30, 20, 230, 190))
    buffer = io.BytesIO()
    crop.save(buffer, format="JPEG", quality=85)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def scripted(per_model):
    """verify() stand-in: model -> (inliers, spread); n inlier pairs on a diagonal."""

    def fake(matcher, image, face, ransac_px):
        n, spread = per_model.get(face.info[FEATURE_KEY].split("/")[0], (0, 0.0))
        pairs = np.array([[i, i, i + 1, i + 1] for i in range(n)], dtype=float) if n else None
        return Verification(max(n, 4), n, np.eye(3) if n else None, spread, pairs)

    return fake


def test_a_placed_photo_carries_spread_rival_ratio_and_points(twins, locator):
    sweeps, _, _ = twins
    result, points = locator.locate_with_points("fx-1", {"p": photo(sweeps)}, "fx-prop-1")
    placed = result.photos[0]
    assert placed.status is LocateStatus.LOCATED_IN_CLAIMED
    assert placed.spread is not None and 0.0 < placed.spread <= 1.0
    assert placed.bar_failed is None
    sample = points["p"]
    assert isinstance(sample, EvidencePoints)
    assert sample.n_total == placed.inliers and 1 <= len(sample.sampled) <= 48
    assert all(0.0 <= v <= 1.0 for pair in sample.sampled for v in pair)


def test_at_most_48_pairs_are_kept_from_many(twins, locator, monkeypatch):
    monkeypatch.setattr(
        "snapback.vision.locate.locate.verify", scripted({"fx-model-a": (300, 0.5)})
    )
    sweeps, _, _ = twins
    _, points = locator.locate_with_points("fx-2", {"p": photo(sweeps)}, "fx-prop-1")
    assert points["p"].n_total == 300 and len(points["p"].sampled) == 48


@pytest.mark.parametrize(
    ("per_model", "bar", "rival"),
    [
        ({"fx-model-a": (8, 0.5)}, "inliers", None),  # under min_inliers (12)
        ({"fx-model-a": (70, 0.018)}, "spread", None),  # under the claimed spread floor
        ({"fx-model-a": (51, 0.3), "fx-model-b": (263, 0.04)}, "ambiguity", 263 / 51),
    ],
)
def test_bar_failed_names_the_bar_that_stopped_the_photo(
    twins, locator, monkeypatch, per_model, bar, rival
):
    monkeypatch.setattr("snapback.vision.locate.locate.verify", scripted(per_model))
    sweeps, _, _ = twins
    result, points = locator.locate_with_points("fx-3", {"p": photo(sweeps)}, "fx-prop-1")
    p = result.photos[0]
    assert p.status is LocateStatus.NOT_LOCATED and p.bar_failed == bar
    assert p.rival_ratio == (pytest.approx(rival, abs=1e-3) if rival else None)
    assert "p" not in points  # nothing placed, nothing drawn


def test_a_claimed_placement_reports_its_rival_ratio(twins, locator, monkeypatch):
    monkeypatch.setattr(
        "snapback.vision.locate.locate.verify",
        scripted({"fx-model-a": (200, 0.4), "fx-model-b": (100, 0.4)}),
    )
    sweeps, _, _ = twins
    result, _ = locator.locate_with_points("fx-4", {"p": photo(sweeps)}, "fx-prop-1")
    assert result.photos[0].status is LocateStatus.LOCATED_IN_CLAIMED
    assert result.photos[0].rival_ratio == pytest.approx(0.5)


def test_points_never_reach_the_result_a_log_or_a_chooser_payload(twins, locator, caplog):
    """The pairs live only in the second return value: not in LocateResult (what the agent's
    chooser and the trace are built from), not in any log line, not in the Verification repr."""
    sweeps, _, _ = twins
    caplog.set_level(logging.DEBUG)
    result, points = locator.locate_with_points("fx-5", {"p": photo(sweeps)}, "fx-prop-1")
    payload = result.model_dump_json()
    assert "sampled" not in payload and "points" not in payload
    values = {f"{v:.6f}"[:6] for pair in points["p"].sampled for v in pair if 0.0 < v < 1.0}
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert not any(v in logged for v in values if len(v) == 6)
    assert "pairs" not in repr(Verification(4, 4, None, 0.5, np.zeros((4, 4))))
    # locate() keeps its old shape: a LocateResult and nothing else
    assert (
        type(locator.locate("fx-6", {"p": photo(sweeps)}, "fx-prop-1")).__name__ == "LocateResult"
    )
    json.loads(payload)
