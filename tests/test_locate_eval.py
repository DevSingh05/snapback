"""A8 (#72): how well locate places a building's own listing photos. Synthetic photos only."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.agent.locate_eval import (
    COLUMNS,
    Placement,
    main,
    read_manifest,
    score,
    wilson,
    write_csv,
)
from snapback.api.eval_results import RESULTS_COLUMNS, read_results
from snapback.api.main import create_app
from snapback.contracts import LocateStatus
from snapback.settings import Settings

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


def test_a_decoy_placed_in_any_indexed_building_is_a_false_placement(tmp_path):
    rows = [{"photo": "d.jpg", "claimed_property_id": "fx-prop-1", "decoy": True}]
    for status, false in ((IN_CLAIMED, 1), (ELSEWHERE, 1), (NOWHERE, 0)):
        answers = {"d.jpg": Placement(status=status)}
        result = score(read_manifest(manifest(tmp_path, rows)), by_name(answers))
        assert result.decoy_false_placements == false


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
