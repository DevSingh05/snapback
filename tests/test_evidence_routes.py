"""E3: GET /cases/{id}/evidence, /files/{path} and /evidence/{alias}/{photo|scan}.jpg.

The read token goes in a header only. A token in the address is refused with 401 even beside a
good header, and nothing in the code or the web app builds an address with one.
"""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.agent.join import KitLookups
from snapback.api.casefiles import CaseFiles
from snapback.api.main import create_app
from snapback.contracts import DataSource, EvidenceFile
from snapback.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "demo" / "evidence.fixture.json"
JPEG = b"\xff\xd8\xff\xe0" + b"synthetic test bytes, not an image" + b"\xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n" + b"not a jpeg"


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))


def new_case(client):
    made = client.post("/cases", data={"text": "Nice 1 bed, $1,500 a month"})
    assert made.status_code == 201
    return made.json()


def read(case):
    return {"Authorization": f"Bearer {case['read_token']}"}


def load_file() -> EvidenceFile:
    return EvidenceFile.model_validate_json(FIXTURE.read_text())


def attach(client, case, **kw) -> CaseFiles:
    files = CaseFiles(evidence=load_file(), **kw)
    client.app.state.store.get(case["case_id"]).files = files
    return files


# --- /evidence ----------------------------------------------------------------------------------


def test_evidence_needs_a_token_and_refuses_one_in_the_address(client):
    case = new_case(client)
    attach(client, case)
    url = f"/cases/{case['case_id']}/evidence"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer nope"}).status_code == 403
    in_address = client.get(f"{url}?token={case['read_token']}", headers=read(case))
    assert in_address.status_code == 401  # even beside a good header
    assert client.get(f"{url}?token={case['read_token']}").status_code == 401


def test_evidence_returns_the_file_the_code_wrote(client):
    case = new_case(client)
    attach(client, case)
    r = client.get(f"/cases/{case['case_id']}/evidence", headers=read(case))
    assert r.status_code == 200
    body = EvidenceFile.model_validate(r.json())
    assert body.written_by == "code" and body.source is DataSource.FIXTURE
    assert body.case_id == case["case_id"]  # the case's own id, not the fixture's
    assert [p.alias for p in body.photos] == ["P1", "P2", "P3", "P4"]
    assert r.headers["cache-control"] == "private, no-store"


def test_evidence_is_404_when_the_case_has_none_and_for_an_unknown_case(client):
    case = new_case(client)
    r = client.get(f"/cases/{case['case_id']}/evidence", headers=read(case))
    assert r.status_code == 404 and "No evidence file" in r.json()["detail"]
    assert client.get("/cases/NOPE/evidence").status_code == 404


def test_a_write_token_may_read_too(client):
    case = new_case(client)
    attach(client, case)
    ok = client.get(f"/cases/{case['case_id']}/evidence", headers={"X-Case-Token": case["token"]})
    assert ok.status_code == 200


# --- /files/{path} ------------------------------------------------------------------------------


def test_files_serves_a_note_the_agent_wrote_read_only(client):
    case = new_case(client)
    attach(client, case, notes={"notes/place.md": ("Photo P1 was placed in S1.", "model")})
    url = f"/cases/{case['case_id']}/files/notes/place.md"
    assert client.get(url).status_code == 401
    r = client.get(url, headers=read(case))
    assert r.status_code == 200
    assert r.json() == {
        "path": "notes/place.md",
        "text": "Photo P1 was placed in S1.",
        "written_by": "model",
    }
    assert client.get(f"{url}?token={case['read_token']}", headers=read(case)).status_code == 401
    # Read only: nothing can write or delete a file through this route.
    for method in (client.post, client.put, client.delete, client.patch):
        assert method(url, headers=read(case)).status_code in (404, 405)


def test_files_also_lists_evidence_json_as_a_file_the_code_wrote(client):
    case = new_case(client)
    attach(client, case)
    r = client.get(f"/cases/{case['case_id']}/files/evidence/photos.json", headers=read(case))
    assert r.status_code == 200 and r.json()["written_by"] == "code"
    assert json.loads(r.json()["text"])["photos"][0]["alias"] == "P1"


@pytest.mark.parametrize(
    "path",
    ["../etc/passwd", "notes/../../x", "%2e%2e/secret", "/etc/passwd", "notes\\place.md", "a%00b"],
)
def test_files_refuses_paths_that_climb_out(client, path):
    case = new_case(client)
    attach(client, case, notes={"notes/place.md": ("x", "policy")})
    r = client.get(f"/cases/{case['case_id']}/files/{path}", headers=read(case))
    assert r.status_code in (400, 404)
    assert "root:" not in r.text


def test_files_unknown_path_is_404(client):
    case = new_case(client)
    attach(client, case)
    r = client.get(f"/cases/{case['case_id']}/files/notes/none.md", headers=read(case))
    assert r.status_code == 404


# --- /evidence/{alias}/{photo|scan}.jpg ---------------------------------------------------------


def test_image_route_serves_jpeg_bytes_with_the_header_token_only(client):
    case = new_case(client)
    attach(client, case, images={("P1", "photo"): JPEG, ("P1", "scan"): JPEG + b"2"})
    base = f"/cases/{case['case_id']}/evidence/P1"
    assert client.get(f"{base}/photo.jpg").status_code == 401
    r = client.get(f"{base}/photo.jpg", headers=read(case))
    assert r.status_code == 200 and r.content == JPEG
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"{base}/scan.jpg", headers=read(case)).content == JPEG + b"2"
    in_address = client.get(f"{base}/photo.jpg?token={case['read_token']}", headers=read(case))
    assert in_address.status_code == 401


def test_image_route_404s_for_missing_alias_kind_or_non_jpeg_bytes(client):
    case = new_case(client)
    attach(client, case, images={("P1", "photo"): JPEG, ("P2", "photo"): PNG})
    base = f"/cases/{case['case_id']}/evidence"
    assert client.get(f"{base}/P1/scan.jpg", headers=read(case)).status_code == 404
    assert client.get(f"{base}/P9/photo.jpg", headers=read(case)).status_code == 404
    assert client.get(f"{base}/P2/photo.jpg", headers=read(case)).status_code == 404  # not a jpeg
    assert client.get(f"{base}/P1/other.jpg", headers=read(case)).status_code in (404, 422)
    assert client.get(f"{base}/..%2fP1/photo.jpg", headers=read(case)).status_code in (404, 422)
    assert client.get(f"{base}/P1/photo.png", headers=read(case)).status_code == 404


def test_image_alias_must_look_like_an_alias(client):
    case = new_case(client)
    attach(client, case, images={("P1", "photo"): JPEG})
    r = client.get(f"/cases/{case['case_id']}/evidence/photo-1/photo.jpg", headers=read(case))
    assert r.status_code in (404, 422)


# --- the staged demo case -----------------------------------------------------------------------


def test_a_staged_demo_case_a_serves_the_fixture_evidence_labelled_fixture(client):
    case = new_case(client)
    client.app.state.store.get(case["case_id"]).demo_case_id = "a"
    r = client.get(f"/cases/{case['case_id']}/evidence", headers=read(case))
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "fixture" and body["thresholds_version"] == "fixture-synthetic"
    assert body["case_id"] == case["case_id"]
    other = new_case(client)  # a case that is not staged gets no stand-in
    assert client.get(f"/cases/{other['case_id']}/evidence", headers=read(other)).status_code == 404


# --- no token in an address, anywhere -----------------------------------------------------------

TOKEN_IN_ADDRESS = re.compile(r"[?&]token=")


def test_no_source_file_builds_an_address_with_a_token():
    offenders = []
    for base in (ROOT / "src", ROOT / "apps" / "web" / "src"):
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html"}:
                continue
            if ".test." in path.name or path.name.startswith("test_"):
                continue  # tests assert the refusal, so they spell it out
            for n, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
                if TOKEN_IN_ADDRESS.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{n}")
    assert offenders == []


def test_the_three_new_routes_all_refuse_a_token_in_the_address(client):
    case = new_case(client)
    attach(client, case, images={("P1", "photo"): JPEG}, notes={"notes/a.md": ("t", "policy")})
    cid, tok = case["case_id"], case["read_token"]
    for path in (
        f"/cases/{cid}/evidence",
        f"/cases/{cid}/files/notes/a.md",
        f"/cases/{cid}/evidence/P1/photo.jpg",
    ):
        for headers in (None, read(case)):
            r = client.get(f"{path}?token={tok}", headers=headers)
            assert r.status_code == 401, path
            assert tok not in r.text
