"""A8 (#72): how well locate places a building's own listing photos. Synthetic photos only."""

import io
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from snapback.adapters.matterport import FixtureMatterport
from snapback.agent import locate_eval
from snapback.agent.locate_eval import (
    COLUMNS,
    Placement,
    live_for_eval,
    main,
    product_locator,
    read_manifest,
    score,
    wilson,
    write_csv,
)
from snapback.api.eval_results import RESULTS_COLUMNS, read_results
from snapback.api.main import create_app
from snapback.contracts import DataSource, LocateStatus, PropertyRecord
from snapback.settings import Settings
from snapback.vision.embed import TinyEmbedder
from snapback.vision.locate.index import LocateIndex
from snapback.vision.locate.thresholds import load_thresholds
from snapback.vision.locate.verify import PatchMatcher

IN_CLAIMED, ELSEWHERE, NOWHERE = (
    LocateStatus.LOCATED_IN_CLAIMED,
    LocateStatus.LOCATED_ELSEWHERE,
    LocateStatus.NOT_LOCATED,
)


def manifest(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "data" / "eval" / "manifest.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def by_name(answers: dict[str, Placement]):
    """A stand-in locator that answers by the photo's file name."""

    def locate(photo: Path, claimed_property_id: str) -> Placement:
        return answers[photo.name]

    return locate


ROWS = [
    # Six of the building's own photos; four say which floor plan they show.
    {"photo": "p1.jpg", "claimed_property_id": "fx-prop-1", "floor_plan": "2 bed / 2 bath"},
    {"photo": "p2.jpg", "claimed_property_id": "fx-prop-1", "floor_plan": "2 bed / 2 bath"},
    {"photo": "p3.jpg", "claimed_property_id": "fx-prop-1", "floor_plan": "1 bed / 1 bath"},
    {"photo": "p4.jpg", "claimed_property_id": "fx-prop-1", "floor_plan": "1 bed / 1 bath"},
    {"photo": "p5.jpg", "claimed_property_id": "fx-prop-1"},
    {"photo": "p6.jpg", "claimed_property_id": "fx-prop-1"},
    # Three decoys: photos of other buildings, claimed to be this one.
    {"photo": "d1.jpg", "claimed_property_id": "fx-prop-1", "decoy": True},
    {"photo": "d2.jpg", "claimed_property_id": "fx-prop-1", "decoy": True},
    {"photo": "d3.jpg", "claimed_property_id": "fx-prop-1", "decoy": True},
]
ANSWERS = {
    "p1.jpg": Placement(status=IN_CLAIMED, floor_plan="2 bed / 2 bath"),
    "p2.jpg": Placement(status=IN_CLAIMED, floor_plan="1 bed / 1 bath"),  # right building only
    "p3.jpg": Placement(status=IN_CLAIMED, floor_plan="1 bed / 1 bath"),
    "p4.jpg": Placement(status=NOWHERE),
    "p5.jpg": Placement(status=IN_CLAIMED),
    "p6.jpg": Placement(status=ELSEWHERE),  # one of its own photos put in another building
    "d1.jpg": Placement(status=NOWHERE),
    "d2.jpg": Placement(status=IN_CLAIMED),  # a false placement
    "d3.jpg": Placement(status=LocateStatus.NOT_INDEXED),
}


# --- counting ------------------------------------------------------------------------------


def test_counts_are_k_of_n_for_building_and_floor_plan_and_decoys(tmp_path):
    result = score(read_manifest(manifest(tmp_path, ROWS)), by_name(ANSWERS))
    assert (result.right_building, result.photos) == (4, 6)
    assert (result.right_floor_plan, result.photos_with_floor_plan) == (2, 4)
    assert (result.wrong_building, result.photos) == (1, 6)
    assert (result.decoy_false_placements, result.decoys) == (1, 3)


def test_a_decoy_counts_against_us_only_when_it_is_placed_in_the_claimed_building(tmp_path):
    # A decoy is a photo of another building, claimed to be this one. "Taken here" is the
    # false placement. "Taken in another building" is the right answer for a decoy whose own
    # building is indexed (V2, #148), so it is counted beside, not against.
    rows = [{"photo": "d.jpg", "claimed_property_id": "fx-prop-1", "decoy": True}]
    for status, false, elsewhere in ((IN_CLAIMED, 1, 0), (ELSEWHERE, 0, 1), (NOWHERE, 0, 0)):
        answers = {"d.jpg": Placement(status=status)}
        result = score(read_manifest(manifest(tmp_path, rows)), by_name(answers))
        assert (result.decoy_false_placements, result.decoys_placed_elsewhere) == (
            false,
            elsewhere,
        )


def test_a_floor_plan_only_counts_when_the_building_is_right_too(tmp_path):
    rows = [{"photo": "p.jpg", "claimed_property_id": "fx-prop-1", "floor_plan": "2 bed"}]
    answers = {"p.jpg": Placement(status=ELSEWHERE, floor_plan="2 bed")}
    result = score(read_manifest(manifest(tmp_path, rows)), by_name(answers))
    assert (result.right_building, result.right_floor_plan) == (0, 0)


def test_a_locator_that_fails_on_a_photo_counts_it_as_not_placed(tmp_path):
    def broken(photo: Path, claimed_property_id: str) -> Placement:
        raise RuntimeError("could not read the image")

    result = score(read_manifest(manifest(tmp_path, ROWS)), broken)
    assert (result.right_building, result.decoy_false_placements) == (0, 0)
    assert result.failed == len(ROWS)


def test_a_bad_manifest_line_is_an_error_that_names_the_line_not_its_content(tmp_path):
    path = manifest(tmp_path, ROWS[:1])
    path.write_text(path.read_text() + '{"photo": "secret-name.jpg"}\n')
    with pytest.raises(ValueError, match="line 2") as error:
        read_manifest(path)
    assert "secret-name" not in str(error.value)


# --- the interval --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [(8, 10, 0.4902, 0.9433), (0, 10, 0.0, 0.2775), (10, 10, 0.7225, 1.0), (1, 3, 0.0615, 0.7923)],
)
def test_wilson_interval_matches_known_values(k, n, low, high):
    got_low, got_high = wilson(k, n)
    assert (round(got_low, 4), round(got_high, 4)) == (low, high)


def test_wilson_needs_something_to_count():
    with pytest.raises(ValueError):
        wilson(0, 0)
    with pytest.raises(ValueError):
        wilson(5, 3)


# --- the file ------------------------------------------------------------------------------


def test_the_csv_is_the_lab_panels_format_and_holds_only_totals(tmp_path):
    result = score(read_manifest(manifest(tmp_path, ROWS)), by_name(ANSWERS))
    out = tmp_path / "eval" / "locate_real.csv"
    write_csv(result, out, source="fixture", frozen_at="FIXTURE")

    assert COLUMNS == RESULTS_COLUMNS
    assert read_results(out) is not None  # the API's own check accepts it
    text = out.read_text()
    assert text.startswith("# FIXTURE")
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    assert lines[0] == ",".join(COLUMNS)
    assert lines[1:] == [
        "locate_real,right_building,4,6,0.6667,0.3000,0.9032,FIXTURE",
        "locate_real,right_floor_plan,2,4,0.5000,0.1500,0.8500,FIXTURE",
        "locate_real,wrong_building,1,6,0.1667,0.0301,0.5635,FIXTURE",
        "locate_real,decoy_false_placement,1,3,0.3333,0.0615,0.7923,FIXTURE",
        "locate_real,decoy_placed_elsewhere,0,3,0.0000,0.0000,0.5615,FIXTURE",
    ]
    # Totals only: no photo, no building, no floor plan.
    for secret in ("p1", "d2", ".jpg", "fx-prop-1", "2 bed"):
        assert secret not in text


def test_a_count_with_nothing_under_it_is_left_out_not_written_as_zero_of_zero(tmp_path):
    rows = [{"photo": "p1.jpg", "claimed_property_id": "fx-prop-1"}]  # no decoys, no floor plans
    result = score(read_manifest(manifest(tmp_path, rows)), by_name(ANSWERS))
    out = tmp_path / "locate_real.csv"
    write_csv(result, out, source="fixture", frozen_at="FIXTURE")
    rows_written = [line for line in out.read_text().splitlines() if not line.startswith("#")]
    metrics = [line.split(",")[1] for line in rows_written[1:]]
    assert metrics == ["right_building", "wrong_building"]


def test_the_file_is_swapped_in_whole(tmp_path):
    result = score(read_manifest(manifest(tmp_path, ROWS)), by_name(ANSWERS))
    out = tmp_path / "eval" / "locate_real.csv"
    write_csv(result, out, source="fixture", frozen_at="FIXTURE")
    first = out.read_bytes()
    write_csv(result, out, source="live", frozen_at="2026-11-14T02:00")
    assert out.read_bytes() != first and out.read_text().startswith("# LIVE")
    assert [path.name for path in out.parent.iterdir()] == ["locate_real.csv"]  # no temp left


# --- the command ---------------------------------------------------------------------------


def test_the_command_writes_the_file_with_a_named_locator(tmp_path, capsys):
    path = manifest(tmp_path, ROWS)
    out = tmp_path / "eval" / "locate_real.csv"
    code = main(["--manifest", str(path), "--out", str(out), "--locator", "test_locate_eval:demo"])
    assert code == 0 and out.is_file()
    said = capsys.readouterr().out
    assert "4 of 6" in said and "1 of 3" in said
    assert ".jpg" not in said and "fx-prop-1" not in said  # the summary is totals too


def demo(photo: Path, claimed_property_id: str) -> Placement:
    return ANSWERS[photo.name]


def test_without_a_locator_the_command_says_what_is_missing_and_writes_nothing(tmp_path, capsys):
    path = manifest(tmp_path, ROWS)
    out = tmp_path / "eval" / "locate_real.csv"
    code = main(["--manifest", str(path), "--out", str(out), "--locator", "snapback.nope:none"])
    assert code == 2 and not out.exists()
    assert "locator" in capsys.readouterr().err.lower()


def test_without_a_manifest_the_command_says_where_it_looked(tmp_path, capsys):
    code = main(["--manifest", str(tmp_path / "missing.jsonl"), "--out", str(tmp_path / "o.csv")])
    assert code == 2
    assert "manifest" in capsys.readouterr().err.lower()


def test_make_has_the_target():
    makefile = (Path(__file__).resolve().parent.parent / "Makefile").read_text()
    assert "eval-locate-real:" in makefile
    assert "snapback.agent.locate_eval" in makefile


def test_the_module_runs_as_a_script():
    done = subprocess.run(
        [sys.executable, "-m", "snapback.agent.locate_eval", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0 and "--manifest" in done.stdout


# --- the default locator is the product's own (A22), with the thresholds main ships --------

# The numpy matcher finds fewer points than DISK+LightGlue, so these tests use a lower floor,
# as lane V's own tests do. The run that counts uses the thresholds in the config file.
RELAXED = replace(load_thresholds(), min_inliers=12, stop_at_inliers=60, elsewhere_min_inliers=16)
RECORDS = [
    PropertyRecord.model_validate(
        {
            "property_id": prop,
            "source": DataSource.LIVE,
            "model_ids": [model],
            "floor_plans": [plan],
        }
    )
    for prop, model, plan in (
        ("fx-prop-1", "fx-model-a", "2 bed / 2 bath"),
        ("fx-prop-2", "fx-model-b", "1 bed / 1 bath"),
        ("fx-prop-3", "fx-model-c", "studio"),  # on record, not in the index
    )
]


class CountingMatcher(PatchMatcher):
    calls = 0

    def match(self, a, b):
        type(self).calls += 1
        return super().match(a, b)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("world")
    adapter = FixtureMatterport(root / "faces")
    sweeps = {m: adapter.sweeps(m) for m in ("fx-model-a", "fx-model-b")}
    index = LocateIndex.build("demo", [s for ss in sweeps.values() for s in ss], TinyEmbedder())
    index.save(root / "data" / "index" / "demo")
    return root / "data", sweeps, adapter


def photo_file(folder: Path, name: str, sweeps, model: str, sweep: int, face: int) -> Path:
    """A crop of one face of a synthetic twin, saved the way a listing photo would be."""
    with Image.open(sweeps[model][sweep].faces[face]) as opened:
        crop = opened.convert("RGB").crop((30, 20, 230, 190))
    out = io.BytesIO()
    crop.save(out, format="JPEG", quality=85)
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out.getvalue())
    return path


def fixture_live(world, *, matcher=PatchMatcher, thresholds=RELAXED):
    data_dir, _, adapter = world
    settings = Settings(_env_file=None, snapback_data_dir=data_dir)
    return live_for_eval(
        settings,
        records=lambda: RECORDS,
        sweeps_for=adapter.sweeps,
        matcher_factory=matcher,
        thresholds=thresholds,
    )


def test_the_default_locator_scores_what_the_product_does_on_a_live_case(world, tmp_path):
    _, sweeps, _ = world
    locate = product_locator(fixture_live(world))

    own = photo_file(tmp_path, "own.jpg", sweeps, "fx-model-a", 2, 1)
    placed = locate(own, "fx-prop-1")
    assert (placed.status, placed.floor_plan) == (IN_CLAIMED, "2 bed / 2 bath")
    assert placed.thresholds_version and placed.thresholds_version.startswith("thresholds-")

    # A photo of another indexed building, claimed to be this one: traced to where it was
    # taken, never "taken here".
    decoy = photo_file(tmp_path, "decoy.jpg", sweeps, "fx-model-b", 1, 2)
    assert locate(decoy, "fx-prop-1").status is ELSEWHERE

    # A building with no twin in the index is "not indexed", as in the product, and the
    # matcher is never run for it.
    CountingMatcher.calls = 0
    cold = product_locator(fixture_live(world, matcher=CountingMatcher))
    assert cold(own, "fx-prop-3").status is LocateStatus.NOT_INDEXED
    assert cold(own, "fx-no-such-building").status is LocateStatus.NOT_INDEXED
    assert CountingMatcher.calls == 0


def test_a_whole_run_through_the_product_s_locator(world, tmp_path):
    _, sweeps, _ = world
    folder = tmp_path / "data" / "eval"
    rows = []
    for number, (sweep, face) in enumerate([(0, 3), (1, 2), (2, 1), (3, 0)]):
        photo_file(folder, f"own{number}.jpg", sweeps, "fx-model-a", sweep, face)
        rows.append(
            {
                "photo": f"own{number}.jpg",
                "claimed_property_id": "fx-prop-1",
                "floor_plan": "2 bed / 2 bath",
            }
        )
    for number, (sweep, face) in enumerate([(0, 1), (2, 3)]):
        photo_file(folder, f"decoy{number}.jpg", sweeps, "fx-model-b", sweep, face)
        rows.append(
            {"photo": f"decoy{number}.jpg", "claimed_property_id": "fx-prop-1", "decoy": True}
        )
    path = manifest(tmp_path, rows)
    result = score(read_manifest(path), product_locator(fixture_live(world)))
    assert (result.photos, result.decoys, result.failed) == (4, 2, 0)
    assert result.right_building >= 3 and result.wrong_building == 0
    assert result.right_floor_plan == result.right_building
    assert result.decoy_false_placements == 0  # no decoy reads "taken here"
    assert result.thresholds_versions == [RELAXED.version] or all(
        version.startswith("thresholds-") for version in result.thresholds_versions
    )


def test_the_run_measures_the_locator_and_never_the_product_s_answer_cache(world, tmp_path):
    data_dir, sweeps, _ = world
    CountingMatcher.calls = 0
    locate = product_locator(fixture_live(world, matcher=CountingMatcher))
    own = photo_file(tmp_path, "own.jpg", sweeps, "fx-model-a", 2, 1)
    assert locate(own, "fx-prop-1").status is IN_CLAIMED
    first = CountingMatcher.calls
    assert first > 0
    # The same photo again is matched again: nothing was saved, and nothing saved is read.
    assert locate(own, "fx-prop-1").status is IN_CLAIMED
    assert CountingMatcher.calls > first
    assert not (data_dir / "locate").exists()


def test_the_thresholds_are_the_ones_in_the_config_file_not_ours(world, tmp_path):
    # Nothing in the harness names a threshold. Built with no thresholds of its own, the
    # locator loads lane V's file, so the run scores whatever main ships.
    _, sweeps, _ = world
    source = Path(locate_eval.__file__).read_text()
    for name in ("min_inliers", "elsewhere_min_inliers", "min_inlier_ratio", "ransac_px"):
        assert name not in source, name
    locate = product_locator(fixture_live(world, thresholds=None))
    own = photo_file(tmp_path, "own.jpg", sweeps, "fx-model-a", 2, 1)
    assert locate(own, "fx-prop-1").thresholds_version.startswith(load_thresholds().version)


def test_the_thresholds_used_are_written_in_the_file_s_heading(tmp_path):
    rows = [{"photo": "p1.jpg", "claimed_property_id": "fx-prop-1"}]
    answers = {"p1.jpg": Placement(status=IN_CLAIMED, thresholds_version="thresholds-fx-1")}
    result = score(read_manifest(manifest(tmp_path, rows)), by_name(answers))
    assert result.thresholds_versions == ["thresholds-fx-1"]
    out = tmp_path / "locate_real.csv"
    write_csv(result, out, source="fixture", frozen_at="FIXTURE")
    assert "# thresholds: thresholds-fx-1" in out.read_text()
    assert read_results(out) is not None  # still the agreed format


def test_with_no_index_the_command_says_so_and_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("SNAPBACK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SNAPBACK_DATA_SOURCE", "fixture")
    path = manifest(tmp_path, ROWS)
    out = tmp_path / "eval" / "locate_real.csv"
    code = main(["--manifest", str(path), "--out", str(out), "--source", "fixture"])
    assert code == 2 and not out.exists()
    said = capsys.readouterr().err.lower()
    assert "index" in said and ".jpg" not in said


# --- the Lab reads it over the API ---------------------------------------------------------


def test_the_api_serves_the_file_and_404s_without_it(tmp_path):
    out = tmp_path / "eval" / "locate_real.csv"
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path, snapback_eval_locate_real=out)
    client = TestClient(create_app(settings))
    assert client.get("/eval/locate_real.csv").status_code == 404

    result = score(read_manifest(manifest(tmp_path, ROWS)), by_name(ANSWERS))
    write_csv(result, out, source="fixture", frozen_at="FIXTURE")
    served = client.get("/eval/locate_real.csv")
    assert served.status_code == 200
    assert served.headers["content-type"] == "text/csv; charset=utf-8"
    assert served.content == out.read_bytes()
    for method in ("post", "put", "delete"):
        assert getattr(client, method)("/eval/locate_real.csv").status_code == 405
