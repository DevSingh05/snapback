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


def new_case(client: TestClient) -> dict:
    response = client.post("/cases", data={"text": "Two bed near the park."})
    assert response.status_code == 201, response.text
    return response.json()


def test_the_columns_are_the_ones_in_the_shared_fixture():
    rows = [line for line in SAMPLE.read_text().splitlines() if not line.startswith("#")]
    assert tuple(rows[0].split(",")) == RESULTS_COLUMNS


def test_the_file_is_served_as_it_was_written(client, results):
    results.parent.mkdir(parents=True)
    results.write_bytes(SAMPLE.read_bytes())
    case = new_case(client)

    response = client.get(URL, params={"token": case["read_token"]})
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["cache-control"] == "no-store"
    assert response.content == SAMPLE.read_bytes()
    assert response.text.startswith("# FIXTURE")  # the label travels in the file itself


def test_no_file_yet_is_a_404(client, results):
    case = new_case(client)
    assert not results.exists()
    assert client.get(URL, params={"token": case["read_token"]}).status_code == 404


def test_a_secret_is_needed_and_is_checked_before_the_file(client, results):
    # Without a secret the answer is the same whether or not the file exists.
    assert client.get(URL).status_code == 401
    write(results, f"{HEADER}\n{ROW}\n")
    assert client.get(URL).status_code == 401
    assert client.get(URL, params={"token": "nope"}).status_code == 403
    assert client.get(URL, headers={"Authorization": "Bearer nope"}).status_code == 403


def test_any_case_on_this_server_can_read_with_its_read_token(client, results):
    write(results, f"{HEADER}\n{ROW}\n")
    first, second = new_case(client), new_case(client)
    for case in (first, second):
        assert client.get(URL, params={"token": case["read_token"]}).status_code == 200
        bearer = {"Authorization": f"Bearer {case['read_token']}"}
        assert client.get(URL, headers=bearer).status_code == 200


def test_the_write_secret_reads_from_a_header_and_is_refused_in_the_address(client, results):
    write(results, f"{HEADER}\n{ROW}\n")
    case = new_case(client)
    assert client.get(URL, headers={"Authorization": f"Bearer {case['token']}"}).status_code == 200
    assert client.get(URL, headers={"X-Case-Token": case["token"]}).status_code == 200
    assert client.get(URL, params={"token": case["token"]}).status_code == 403


def test_a_secret_from_another_server_is_refused(tmp_path, client, results):
    write(results, f"{HEADER}\n{ROW}\n")
    other = TestClient(create_app(Settings(_env_file=None, snapback_data_dir=tmp_path / "other")))
    stranger = new_case(other)
    assert client.get(URL, params={"token": stranger["read_token"]}).status_code == 403


@pytest.mark.parametrize(
    "text",
    [
        "",
        "# FIXTURE\n",
        "name,phone,rent\nA,555-0100,1200\n",
        f"{HEADER},extra\n{ROW},1\n",
        ",".join(reversed(RESULTS_COLUMNS)) + "\n",
    ],
)
def test_a_file_that_is_not_the_agreed_csv_is_never_served(client, results, text):
    # The path is a setting. If it is pointed at some other CSV, nothing from it leaves.
    write(results, text)
    case = new_case(client)
    response = client.get(URL, params={"token": case["read_token"]})
    assert response.status_code == 500
    assert "555-0100" not in response.text
    assert "csv" not in response.headers["content-type"]


def test_a_file_that_is_too_large_or_not_text_is_never_served(client, results):
    case = new_case(client)
    write(results, f"{HEADER}\n" + f"{ROW}\n" * (MAX_RESULTS_BYTES // len(ROW) + 1))
    assert client.get(URL, params={"token": case["read_token"]}).status_code == 500
    results.write_bytes(HEADER.encode() + b"\n\xff\xfe\x00")
    assert client.get(URL, params={"token": case["read_token"]}).status_code == 500


def test_a_folder_at_that_path_counts_as_no_file(client, results):
    results.mkdir(parents=True)
    case = new_case(client)
    assert client.get(URL, params={"token": case["read_token"]}).status_code == 404


def test_comment_lines_and_windows_line_ends_are_fine(client, results):
    results.parent.mkdir(parents=True)
    results.write_bytes(f"# LIVE: frozen Sat 02:00\r\n# n per row below\r\n{HEADER}\r\n".encode())
    case = new_case(client)
    response = client.get(URL, params={"token": case["read_token"]})
    assert response.status_code == 200
    assert response.text.startswith("# LIVE")


def test_the_route_only_reads(client, results):
    write(results, f"{HEADER}\n{ROW}\n")
    before = results.read_bytes()
    case = new_case(client)
    bearer = {"Authorization": f"Bearer {case['token']}"}
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(URL, headers=bearer).status_code == 405
    assert results.read_bytes() == before


def test_the_path_comes_from_settings_and_not_from_the_request(client, results, tmp_path):
    write(results, f"{HEADER}\n{ROW}\n")
    write(tmp_path / "eval" / "other.csv", f"{HEADER}\nsecret_row,x,1,1,1,1,1,X\n")
    case = new_case(client)
    token = {"token": case["read_token"]}
    assert client.get("/eval/other.csv", params=token).status_code == 404
    assert client.get("/eval/..%2Feval%2Fother.csv", params=token).status_code == 404
    assert "secret_row" not in client.get(URL, params={**token, "path": "other.csv"}).text


def test_the_default_path_is_where_make_eval_writes():
    assert Settings(_env_file=None).snapback_eval_results == Path("eval/results.csv")
