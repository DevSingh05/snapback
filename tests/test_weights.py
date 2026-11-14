"""Pinned weights: hashes are checked, and the matcher's weights reach thresholds_version."""

import re

import pytest

from snapback.vision.locate.weights import (
    DINOV2,
    DISK_DEPTH,
    LIGHTGLUE_DISK,
    Weight,
    WeightMismatchError,
    check,
    sha256_of,
    tag,
)


def test_pins_are_full_sha256():
    for weight in (DISK_DEPTH, LIGHTGLUE_DISK, DINOV2):
        assert re.fullmatch(r"[0-9a-f]{64}", weight.sha256)


def test_check_accepts_the_pinned_file_and_refuses_any_other(tmp_path):
    path = tmp_path / "w.bin"
    path.write_bytes(b"weights")
    pinned = Weight("test", "w.bin", sha256_of(path))
    assert check(pinned, path) == pinned.sha256
    path.write_bytes(b"weights, changed upstream")
    with pytest.raises(WeightMismatchError, match="not the pinned"):
        check(pinned, path)
    with pytest.raises(WeightMismatchError, match="missing"):
        check(pinned, tmp_path / "absent.bin")


def test_tag_names_each_weight_and_its_hash():
    assert tag() == "disk-depth-9c2ee4de+lightglue-disk-b5b21d47"
