"""The strict bar's own inlier ratio (#10): a ChatGPT-regenerated photo named the wrong building
on 60 of 140 matches consistent. Naming a home from photos alone, or placing elsewhere, now needs
a consistent match; the claimed bar is unchanged."""

from dataclasses import replace

import pytest

from snapback.vision.locate.locate import passes_strict
from snapback.vision.locate.thresholds import THRESHOLDS_FILE, load_thresholds
from snapback.vision.locate.verify import Verification

T = load_thresholds()


def test_the_frozen_file_sets_a_strict_ratio_above_the_claimed_one():
    assert T.elsewhere_min_ratio == 0.6
    assert T.min_inlier_ratio == 0.25  # the claimed bar is untouched


def test_the_regenerated_photo_no_longer_clears_the_strict_bar():
    regenerated = Verification(matches=140, inliers=60, homography=None, spread=0.163)
    assert not passes_strict(regenerated, T)
    # The very same counts cleared it before this change.
    assert passes_strict(regenerated, replace(T, elsewhere_min_ratio=T.min_inlier_ratio))


def test_an_honest_consistent_match_still_clears_it():
    honest = Verification(matches=602, inliers=582, homography=None, spread=0.333)
    assert passes_strict(honest, T)
    weakest_kept = Verification(matches=431, inliers=360, homography=None, spread=0.59)  # 0.835
    assert passes_strict(weakest_kept, T)


def test_the_other_strict_bars_still_apply():
    few = Verification(matches=45, inliers=45, homography=None, spread=0.5)
    narrow = Verification(matches=300, inliers=290, homography=None, spread=0.1)
    assert not passes_strict(few, T) and not passes_strict(narrow, T)


def test_an_older_file_without_the_key_reads_as_before(tmp_path):
    text = THRESHOLDS_FILE.read_text().splitlines()
    old = tmp_path / "old.toml"
    kept = [row for row in text if not row.startswith("elsewhere_min_ratio")]
    old.write_text("\n".join(kept) + "\n")
    assert load_thresholds(old).elsewhere_min_ratio == load_thresholds(old).min_inlier_ratio


def test_a_strict_ratio_below_the_claimed_ratio_is_refused(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(
        THRESHOLDS_FILE.read_text().replace(
            "elsewhere_min_ratio = 0.6", "elsewhere_min_ratio = 0.1"
        )
    )
    with pytest.raises(ValueError):
        load_thresholds(bad)


@pytest.mark.parametrize(("inliers", "passes"), [(59, False), (60, True), (61, True)])
def test_the_strict_ratio_boundary_is_inclusive(inliers, passes):
    """At and just under the 60% bar, so a later >= to > change is caught (#296 review)."""
    check = Verification(matches=100, inliers=inliers, homography=None, spread=0.5)
    assert passes_strict(check, T) is passes
