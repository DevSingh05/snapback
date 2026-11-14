"""V4 recapture detector: screen, print and paste replies, behind RECAPTURE_MODEL=on.

Every image is drawn here from a seed: "genuine" replies are synthetic rooms with sensor noise and
a paper code photographed with them; attacks come from lane D's generator (D6). All synthetic, so
these tests check the pipeline, never a number we would quote.
"""

import io
import json

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from snapback.contracts import RecaptureLabel
from snapback.redteam.generator import AttackType, generate
from snapback.vision.recapture import (
    FEATURE_NAMES,
    RecaptureDetector,
    RecaptureModel,
    TrainingRow,
    features,
    read_manifest,
    train,
)


def genuine_photo(seed: int, size: tuple[int, int] = (640, 480)) -> Image.Image:
    """A synthetic phone photo of a room with a paper code in it: the paper is in the scene,
    so it carries the same sensor noise, blur and JPEG as everything else."""
    rng = np.random.default_rng(seed)
    width, height = size
    y, x = np.mgrid[0:height, 0:width] / max(width, height)
    channels = []
    for _ in range(3):
        a, b, c = rng.uniform(-1, 1, 3)
        channels.append(120 + 60 * np.sin(3 * a * x + 2 * b * y + c))
    pixels = np.stack(channels, axis=-1)
    for _ in range(25):
        x0, y0 = rng.integers(0, width - 40), rng.integers(0, height - 40)
        w, h = rng.integers(20, width // 4), rng.integers(20, height // 4)
        pixels[y0 : y0 + h, x0 : x0 + w] = rng.uniform(0, 255, 3)
    image = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(image)
    px, py = int(rng.integers(20, width - 200)), int(rng.integers(20, height - 120))
    draw.rectangle((px, py, px + 170, py + 90), fill=(236, 234, 228))
    for i in range(4):
        draw.line(
            (px + 20 + 35 * i, py + 25, px + 40 + 35 * i, py + 70), fill=(30, 30, 40), width=4
        )
    image = image.filter(ImageFilter.GaussianBlur(float(rng.uniform(0.4, 0.9))))
    noisy = np.asarray(image, np.float32) + rng.normal(0, rng.uniform(2.5, 5.0), (height, width, 3))
    image = Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8), "RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=int(rng.integers(80, 92)))
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def bank(tmp_path, seeds: range, generator_seed: int) -> list[TrainingRow]:
    """Genuine photos for `seeds`, and every recapture-class attack lane D makes from them."""
    src = tmp_path / f"src-{generator_seed}"
    src.mkdir()
    rows = []
    for seed in seeds:
        image = genuine_photo(seed)
        image.save(src / f"g{seed}.jpg", quality=90)
        rows.append(TrainingRow(image=image, label=RecaptureLabel.GENUINE, source=f"g{seed}"))
    for case in generate(sorted(src.iterdir()), tmp_path / f"rt-{generator_seed}", generator_seed):
        if case.attack in (AttackType.COPY_CROP,):
            continue  # a copy is photo memory's job, not recapture's
        with Image.open(case.path) as opened:
            rows.append(TrainingRow(opened.convert("RGB"), case.label, case.source_photo_id))
    return rows


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("recapture")
    rows = bank(tmp, range(0, 30), generator_seed=1)
    model, report = train(rows, version="v0", seed=0)
    return model, report, tmp


def test_features_are_finite_and_fixed_length():
    vector = features(genuine_photo(1))
    assert vector.shape == (len(FEATURE_NAMES),)
    assert np.isfinite(vector).all()


def test_model_off_returns_version_off_and_never_blocks(trained, monkeypatch):
    model, _, _ = trained
    monkeypatch.delenv("RECAPTURE_MODEL", raising=False)
    detector = RecaptureDetector(model)
    screen = Image.new("RGB", (64, 64))
    result = detector.check("r1", screen)
    assert result.model_version == "off"
    assert result.blocks_pass is False and result.score == 0.0
    assert result.label is RecaptureLabel.UNKNOWN
    monkeypatch.setenv("RECAPTURE_MODEL", "off")
    assert RecaptureDetector(model).check("r1", screen).model_version == "off"


def test_screen_fixture_blocks_pass(trained, monkeypatch):
    model, _, tmp = trained
    monkeypatch.setenv("RECAPTURE_MODEL", "on")
    detector = RecaptureDetector(model)
    held_out = bank(tmp, range(100, 106), generator_seed=2)  # photos and seed never trained on
    screens = [row for row in held_out if row.label is RecaptureLabel.SCREEN]
    results = [detector.check(f"r{i}", row.image) for i, row in enumerate(screens)]
    assert all(r.blocks_pass for r in results)
    assert all(r.label is RecaptureLabel.SCREEN for r in results)
    assert all(r.model_version == "v0" and 0.0 <= r.score <= 1.0 for r in results)


def test_fresh_genuine_photos_mostly_pass(trained, monkeypatch):
    model, _, _ = trained
    monkeypatch.setenv("RECAPTURE_MODEL", "on")
    detector = RecaptureDetector(model)
    results = [detector.check(f"g{s}", genuine_photo(s)) for s in range(200, 220)]
    assert sum(not r.blocks_pass for r in results) >= 18
    assert all(r.label is RecaptureLabel.GENUINE for r in results if not r.blocks_pass)


def test_print_and_paste_attacks_mostly_blocked(trained, monkeypatch):
    model, _, tmp = trained
    monkeypatch.setenv("RECAPTURE_MODEL", "on")
    detector = RecaptureDetector(model)
    held_out = bank(tmp, range(300, 306), generator_seed=3)
    for label in (RecaptureLabel.PRINT, RecaptureLabel.PASTE):
        rows = [row for row in held_out if row.label is label]
        blocked = sum(detector.check("r", row.image).blocks_pass for row in rows)
        assert blocked >= len(rows) - 1, label


def test_report_gives_dev_auroc_with_n_and_freezes_the_threshold(trained):
    _, report, _ = trained
    assert report.n_dev_genuine > 0 and report.n_dev_attack > 0
    assert 0.5 <= report.dev_auroc <= 1.0
    assert report.dev_genuine_false_reject <= 0.05
    assert report.synthetic_only is True


def test_split_keeps_every_row_of_a_source_on_one_side(trained):
    """Checked per row: a genuine photo and every attack made from it share one side."""
    _, report, _ = trained
    sides: dict[str, set[bool]] = {}
    for source, is_dev in report.row_split:
        sides.setdefault(source, set()).add(is_dev)
    assert sides and all(len(found) == 1 for found in sides.values())
    assert any(True in found for found in sides.values())
    assert any(False in found for found in sides.values())


def test_an_attack_whose_source_matches_no_genuine_photo_fails_loudly():
    rows = [
        TrainingRow(genuine_photo(1), RecaptureLabel.GENUINE, "jeffrey-0001"),
        TrainingRow(genuine_photo(2), RecaptureLabel.GENUINE, "jeffrey-0002"),
        TrainingRow(genuine_photo(1), RecaptureLabel.SCREEN, "IMG_0001"),  # lane D names by stem
    ]
    with pytest.raises(ValueError, match="no genuine photo"):
        train(rows, version="v0")


def test_manifest_genuine_source_must_be_the_file_stem(tmp_path):
    genuine_photo(1).save(tmp_path / "IMG_0001.jpg")
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("path,label,source,synthetic\nIMG_0001.jpg,genuine,jeffrey-0001,0\n")
    with pytest.raises(ValueError, match="file stem"):
        read_manifest(manifest)
    manifest.write_text("path,label,source,synthetic\nIMG_0001.jpg,genuine,IMG_0001,0\n")
    assert read_manifest(manifest)[0].source == "IMG_0001"


def test_manifest_paths_resolve_against_the_manifest_then_the_working_directory(
    tmp_path, monkeypatch
):
    (tmp_path / "team").mkdir()
    genuine_photo(1).save(tmp_path / "team" / "g1.jpg")
    manifest = tmp_path / "team" / "manifest.csv"
    manifest.write_text("path,label,source,synthetic\ng1.jpg,genuine,g1,0\n")
    assert read_manifest(manifest)[0].source == "g1"
    monkeypatch.chdir(tmp_path)
    manifest.write_text("path,label,source,synthetic\nteam/g1.jpg,genuine,g1,0\n")
    assert read_manifest(manifest)[0].source == "g1"


def test_real_and_synthetic_attacks_are_reported_apart(tmp_path):
    rows = bank(tmp_path, range(0, 24), generator_seed=4)
    # Pretend the genuine photos and the screen attacks are team captures (real).
    rows = [
        TrainingRow(
            r.image,
            r.label,
            r.source,
            synthetic=r.label not in (RecaptureLabel.GENUINE, RecaptureLabel.SCREEN),
        )
        for r in rows
    ]
    _, report = train(rows, version="v0", seed=0)
    assert report.n_dev_attack_real + report.n_dev_attack_synthetic == report.n_dev_attack
    assert report.n_dev_attack_real > 0 and report.n_dev_attack_synthetic > 0
    assert 0.0 <= report.dev_auroc_real <= 1.0 and 0.0 <= report.dev_auroc_synthetic <= 1.0
    assert report.synthetic_only is False


@pytest.mark.parametrize("size", [(10, 10), (4000, 100), (100, 4000)])
def test_tiny_or_thin_images_ask_for_a_new_photo(trained, monkeypatch, size):
    model, _, _ = trained
    monkeypatch.setenv("RECAPTURE_MODEL", "on")
    result = RecaptureDetector(model).check("r", Image.new("RGB", size, (120, 120, 120)))
    assert result.blocks_pass is True
    assert result.label is RecaptureLabel.UNKNOWN


def test_model_round_trips_through_json(trained, tmp_path):
    model, _, _ = trained
    path = tmp_path / "v0.json"
    model.save(path)
    again = RecaptureModel.load(path)
    photo = genuine_photo(7)
    assert again.score(photo) == pytest.approx(model.score(photo))
    meta = json.loads(path.read_text())
    assert meta["version"] == "v0" and meta["synthetic_only"] is True
    assert meta["features"] == list(FEATURE_NAMES)


def test_on_without_a_model_file_is_off(monkeypatch, tmp_path):
    monkeypatch.setenv("RECAPTURE_MODEL", "on")
    detector = RecaptureDetector.from_file(tmp_path / "missing.json")
    assert detector.check("r1", genuine_photo(1)).model_version == "off"


# --- second review (#112) ---------------------------------------------------------------------


def test_real_and_synthetic_auroc_match_a_recomputation(tmp_path):
    from snapback.vision.recapture import auroc

    # Lane D's attacks (synthetic, easy here) plus "real" attacks that look exactly like genuine
    # photos (hard): the two AUROCs must differ, so a mixed number cannot pass for either.
    rows = bank(tmp_path, range(0, 24), generator_seed=5)
    rows += [
        TrainingRow(genuine_photo(seed + 500), RecaptureLabel.SCREEN, f"g{seed}", synthetic=False)
        for seed in range(0, 24)
    ]
    rows = [
        TrainingRow(
            r.image,
            r.label,
            r.source,
            synthetic=r.synthetic and r.label is not RecaptureLabel.GENUINE,
        )
        for r in rows
    ]
    model, report = train(rows, version="v0", seed=0)
    assert abs(report.dev_auroc_real - report.dev_auroc_synthetic) > 0.1
    kept = [
        r
        for r in rows
        if r.label
        in (
            RecaptureLabel.GENUINE,
            RecaptureLabel.SCREEN,
            RecaptureLabel.PRINT,
            RecaptureLabel.PASTE,
        )
    ]
    dev = [r for r, (_, is_dev) in zip(kept, report.row_split, strict=True) if is_dev]
    genuine = [model.score(r.image) for r in dev if r.label is RecaptureLabel.GENUINE]
    real = [
        model.score(r.image)
        for r in dev
        if r.label is not RecaptureLabel.GENUINE and not r.synthetic
    ]
    synthetic = [
        model.score(r.image) for r in dev if r.label is not RecaptureLabel.GENUINE and r.synthetic
    ]
    assert report.dev_auroc_real == pytest.approx(auroc(genuine, real))
    assert report.dev_auroc_synthetic == pytest.approx(auroc(genuine, synthetic))
    assert (report.n_dev_attack_real, report.n_dev_attack_synthetic) == (len(real), len(synthetic))


def test_command_prints_synthetic_apart_with_both_n(tmp_path, capsys):
    import csv

    from snapback.vision.recapture.train import main as train_main

    src = tmp_path / "genuine"
    src.mkdir()
    rows = []
    for seed in range(16):
        genuine_photo(seed).save(src / f"g{seed}.jpg", quality=90)
        rows.append(
            {
                "path": f"genuine/g{seed}.jpg",
                "label": "genuine",
                "source": f"g{seed}",
                "synthetic": 0,
            }
        )
    with (tmp_path / "team.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    from snapback.redteam.generator import write_manifest

    cases = generate(sorted(src.iterdir()), tmp_path / "rt", 1)
    write_manifest(cases, tmp_path / "rt" / "manifest.csv")
    code = train_main(
        [
            "--manifest",
            str(tmp_path / "team.csv"),
            "--manifest",
            str(tmp_path / "rt" / "manifest.csv"),
            "--out",
            str(tmp_path / "v0.json"),
        ]
    )
    printed = capsys.readouterr().out
    assert code == 0
    assert "SYNTHETIC attacks" in printed and "real attacks" in printed
    assert printed.count("n=") >= 4  # train, dev genuine, real attacks, synthetic attacks
    meta = json.loads((tmp_path / "v0.json").read_text())["meta"]
    assert "dev_auroc" not in meta and "dev_auroc_synthetic" in meta  # no mixed number saved


def test_train_skips_a_photo_too_small_to_measure():
    rows = [TrainingRow(genuine_photo(s), RecaptureLabel.GENUINE, f"g{s}") for s in range(8)]
    rows.append(TrainingRow(Image.new("RGB", (10, 10)), RecaptureLabel.GENUINE, "tiny"))
    _, report = train(rows, version="v0")
    assert "tiny" not in {source for source, _ in report.row_split}
    assert len(report.row_split) == 8
