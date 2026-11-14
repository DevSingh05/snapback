"""D6: scripted attack generator. Team-made photos in, labelled synthetic attacks out."""

import csv
import hashlib
from pathlib import Path

import pytest
from PIL import Image

from snapback.contracts import RecaptureLabel
from snapback.redteam import ATTACKS, AttackType, generate, write_manifest


def _photo(path: Path, shade: int) -> Path:
    img = Image.new("RGB", (320, 240))
    img.putdata([((x + shade) % 256, (y * 2) % 256, shade) for y in range(240) for x in range(320)])
    img.save(path)
    return path


@pytest.fixture
def sources(tmp_path: Path) -> list[Path]:
    src = tmp_path / "src"
    src.mkdir()
    return [_photo(src / f"fx-team-{i}.png", 40 * i) for i in range(3)]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_every_generated_case_is_labelled_synthetic(sources, tmp_path):
    rows = generate(sources, tmp_path / "out", seed=1)
    assert len(rows) == len(sources) * len(ATTACKS)
    assert all(row.synthetic for row in rows)
    assert all(row.attack in ATTACKS and row.label for row in rows)
    assert all(Path(row.path).is_file() for row in rows)
    assert {row.source_photo_id for row in rows} == {"fx-team-0", "fx-team-1", "fx-team-2"}


def test_generator_is_deterministic_with_seed(sources, tmp_path):
    a = generate(sources, tmp_path / "a", seed=7)
    b = generate(sources, tmp_path / "b", seed=7)
    c = generate(sources, tmp_path / "c", seed=8)
    strip = [r.model_dump(exclude={"path"}) for r in a]
    assert strip == [r.model_dump(exclude={"path"}) for r in b]
    assert [_digest(Path(r.path)) for r in a] == [_digest(Path(r.path)) for r in b]
    assert [_digest(Path(r.path)) for r in a] != [_digest(Path(r.path)) for r in c]


def test_labels_match_the_recapture_classes(sources, tmp_path):
    rows = {r.attack: r for r in generate(sources[:1], tmp_path / "out", seed=1)}
    assert rows[AttackType.PASTE].label is RecaptureLabel.PASTE
    assert rows[AttackType.SCREEN].label is RecaptureLabel.SCREEN
    assert rows[AttackType.PRINT].label is RecaptureLabel.PRINT
    # A crop of a listing photo is a copy for memory/, not a recapture class.
    assert rows[AttackType.CROP_REENCODE].label is RecaptureLabel.UNKNOWN
    assert all(r.expect_presence == "forged" for r in rows.values())


def test_injection_case_carries_its_text_and_a_code(sources, tmp_path):
    row = next(r for r in generate(sources[:1], tmp_path / "o", seed=3) if r.attack == "injection")
    assert row.injection_text and len(row.code) == 4
    assert row.expect_injection is True


def test_attack_pixels_differ_from_the_source(sources, tmp_path):
    src_digest = _digest(sources[0])
    for row in generate(sources[:1], tmp_path / "out", seed=1):
        assert _digest(Path(row.path)) != src_digest


def test_manifest_round_trips_as_csv_with_counts(sources, tmp_path):
    rows = generate(sources, tmp_path / "out", seed=1)
    manifest = write_manifest(rows, tmp_path / "manifest.csv")
    with manifest.open(newline="", encoding="utf-8") as fh:
        read = list(csv.DictReader(fh))
    assert len(read) == len(rows)
    assert {r["synthetic"] for r in read} == {"1"}
    assert sum(r["attack"] == "screen" for r in read) == len(sources)
