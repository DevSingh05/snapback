"""V7 (locate half, learning-v2 L1b): calibrate placement scores into P(placement is right)."""

import json

import numpy as np
import pytest

from snapback.vision.locate.calibrate import (
    Calibration,
    fit_isotonic,
    placement_score,
    reliability_bins,
)


def test_isotonic_fit_is_monotone_and_matches_known_steps():
    x = np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype=float)
    y = np.array([0, 1, 0, 0, 1, 1, 1, 1], dtype=float)
    cal = fit_isotonic(x, y)
    probs = [cal.predict(v) for v in x]
    assert all(a <= b + 1e-12 for a, b in zip(probs, probs[1:], strict=False))
    # Pool-adjacent-violators: 0 stays alone, (1, 0, 0) pool to 1/3, the rest are 1.
    assert probs[0] == pytest.approx(0.0)
    assert probs[1:4] == pytest.approx([1 / 3] * 3) and probs[4:] == pytest.approx([1.0] * 4)
    assert 0.0 <= cal.predict(-100) <= cal.predict(100) <= 1.0


def test_placement_score_rises_with_inliers_and_spread():
    assert placement_score(400, 0.5) > placement_score(60, 0.5) > placement_score(60, 0.05)
    assert placement_score(0, 0.0) == 0.0


def test_reliability_bins_count_and_rate():
    probs = np.array([0.55, 0.58, 0.65, 0.92, 0.95, 0.97])
    right = np.array([1, 0, 1, 1, 1, 0])
    bins = reliability_bins(probs, right, edges=(0.5, 0.6, 0.7, 0.8, 0.9, 1.0))
    by_range = {(b.low, b.high): (b.k, b.n) for b in bins}
    assert by_range[(0.5, 0.6)] == (1, 2)
    assert by_range[(0.6, 0.7)] == (1, 1)
    assert by_range[(0.9, 1.0)] == (2, 3)
    assert (0.7, 0.8) not in by_range  # empty bins are left out, never shown as 0 of 0


def test_calibration_round_trips_and_names_its_data(tmp_path):
    cal = fit_isotonic(np.array([1.0, 2.0, 3.0]), np.array([0.0, 1.0, 1.0]))
    cal = Calibration(cal.xs, cal.ps, n=3, source="renders", version="cal-test")
    path = tmp_path / "cal.json"
    cal.save(path)
    again = Calibration.load(path)
    assert again.predict(2.5) == pytest.approx(cal.predict(2.5))
    meta = json.loads(path.read_text())
    assert meta["source"] == "renders" and meta["n"] == 3
