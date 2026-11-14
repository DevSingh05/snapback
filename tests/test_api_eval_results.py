"""GET /eval/results.csv: the eval harness's results, read-only, for the Lab panel (#69)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.api.eval_results import MAX_RESULTS_BYTES, RESULTS_COLUMNS
from snapback.api.main import create_app
from snapback.settings import Settings

SAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "results_sample.csv"
URL = "/eval/results.csv"
HEADER = ",".join(RESULTS_COLUMNS)
ROW = "rules_only,forged_false_accept,9,40,0.2250,0.1232,0.3750,FIXTURE"


@pytest.fixture
def results(tmp_path) -> Path:
    return tmp_path / "eval" / "results.csv"


@pytest.fixture
def client(tmp_path, results) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path, snapback_eval_results=results)
    return TestClient(create_app(settings))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_the_columns_are_the_ones_in_the_shared_fixture():
    rows = [line for line in SAMPLE.read_text().splitlines() if not line.startswith("#")]
    assert tuple(rows[0].split(",")) == RESULTS_COLUMNS


def test_the_file_is_served_as_it_was_written_with_no_token(client, results):
    results.parent.mkdir(parents=True)
    results.write_bytes(SAMPLE.read_bytes())

    response = client.get(URL)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["cache-control"] == "no-store"
    assert response.content == SAMPLE.read_bytes()
    assert response.text.startswith("# FIXTURE")  # the label travels in the file itself


def test_no_file_yet_is_a_404(client, results):
    assert not results.exists()
    assert client.get(URL).status_code == 404


def test_it_is_public_so_a_token_changes_nothing(client, results):
    # Aggregate numbers only, no case data (XO ruling on #69). A token is neither needed
    # nor looked at, so a wrong one does no harm.
    write(results, f"{HEADER}\n{ROW}\n")
    plain = client.get(URL)
    for extra in (
        {"params": {"token": "anything"}},
        {"headers": {"Authorization": "Bearer anything"}},
        {"headers": {"X-Case-Token": "anything"}},
    ):
        again = client.get(URL, **extra)
        assert (again.status_code, again.content) == (200, plain.content)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "# FIXTURE\n",
        "name,phone,rent\nA,555-0100,1200\n",
        f"{HEADER},extra\n{ROW},1\n",
        ",".join(reversed(RESULTS_COLUMNS)) + "\n",
        f"{HEADER}\nA,555-0100,1200\n",  # the right header on top of some other table
        f"{HEADER}\n{ROW}\nrules_only,forged_fal",  # caught half written
        f"{HEADER}\nrules_only,forged_false_accept,nine,40,0.2250,0.1232,0.3750,FIXTURE\n",
    ],
)
def test_a_file_that_is_not_the_agreed_csv_is_never_served(client, results, text):
    # The route is public and the path is a setting. If it is pointed at some other CSV, or
    # read while it is being written, nothing from the file leaves.
    write(results, text)
    response = client.get(URL)
    assert response.status_code == 500
    assert "555-0100" not in response.text and "forged_fal" not in response.text
    assert "csv" not in response.headers["content-type"]


def test_a_file_that_is_too_large_or_not_text_is_never_served(client, results):
    write(results, f"{HEADER}\n" + f"{ROW}\n" * (MAX_RESULTS_BYTES // len(ROW) + 1))
    assert client.get(URL).status_code == 500
    results.write_bytes(HEADER.encode() + b"\n\xff\xfe\x00")
    assert client.get(URL).status_code == 500


def test_a_folder_at_that_path_counts_as_no_file(client, results):
    results.mkdir(parents=True)
    assert client.get(URL).status_code == 404


def test_comment_lines_and_windows_line_ends_are_fine(client, results):
    results.parent.mkdir(parents=True)
    results.write_bytes(
        f"# LIVE: frozen Sat 02:00\r\n# n per row below\r\n{HEADER}\r\n{ROW}\r\n".encode()
    )
    response = client.get(URL)
    assert response.status_code == 200
    assert response.text.startswith("# LIVE")


def test_a_header_with_no_rows_yet_is_served(client, results):
    write(results, f"# FIXTURE\n{HEADER}\n")
    assert client.get(URL).status_code == 200


def test_the_route_only_reads(client, results):
    write(results, f"{HEADER}\n{ROW}\n")
    before = results.read_bytes()
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(URL).status_code == 405
    assert results.read_bytes() == before


def test_the_path_comes_from_settings_and_not_from_the_request(client, results, tmp_path):
    write(results, f"{HEADER}\n{ROW}\n")
    write(tmp_path / "eval" / "other.csv", f"{HEADER}\nsecret_row,x,1,1,1,1,1,X\n")
    assert client.get("/eval/other.csv").status_code == 404
    assert client.get("/eval/..%2Feval%2Fother.csv").status_code == 404
    assert "secret_row" not in client.get(URL, params={"path": "other.csv"}).text


def test_a_file_swapped_in_whole_is_never_seen_half_written(client, results):
    # What `make eval` should do (asked of lane V on #32): write beside the file, then rename.
    # A rename replaces the file in one step, so every read gets the old file or the new one.
    write(results, f"{HEADER}\n{ROW}\n")
    old = client.get(URL).content
    beside = results.with_suffix(".csv.tmp")
    beside.write_text(f"# LIVE\n{HEADER}\n{ROW}\n{ROW}\n")
    assert client.get(URL).content == old  # the half-finished copy is not what is served
    beside.replace(results)
    assert client.get(URL).text.startswith("# LIVE")


def test_the_default_path_is_where_make_eval_writes():
    assert Settings(_env_file=None).snapback_eval_results == Path("eval/results.csv")
