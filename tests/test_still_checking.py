"""The report's five reads answer 202, not an error, while the check is still running.

evidence, real-listing, copy-alert, report and alternatives have nothing true to say before the
modules have run. Asking early is not a failure: the answer is 202 `{"status", "retry_after_ms"}`
with a Retry-After header, and the page asks again. Once the check has moved on the same read
is served as before. Auth stays header-only and every answer is no-store.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from snapback.agent.join import KitLookups
from snapback.api.casefiles import CaseFiles
from snapback.api.main import create_app
from snapback.contracts import CaseProgress, DataSource, EvidenceFile
from snapback.settings import Settings

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "demo" / "evidence.fixture.json"
READS = ["evidence", "real-listing", "copy-alert", "report", "alternatives"]


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))


def started(client):
    made = client.post("/cases", data={"text": "Nice 1 bed, $1,500 a month"})
    assert made.status_code == 201
    body = made.json()
    case = client.app.state.store.get(body["case_id"])
    case.files = CaseFiles(evidence=EvidenceFile.model_validate_json(FIXTURE.read_text()))
    return body, case


def headers(body):
    return {"Authorization": f"Bearer {body['read_token']}"}


@pytest.mark.parametrize("what", READS)
def test_read_is_202_while_running_then_served(client, monkeypatch, what):
    body, case = started(client)
    url = f"/cases/{body['case_id']}/{what}"
    real_status = case.status
    monkeypatch.setattr(
        case, "status", lambda *a, **k: SimpleNamespace(status=CaseProgress.RUNNING)
    )

    waiting = client.get(url, headers=headers(body))
    assert waiting.status_code == 202
    assert waiting.json() == {"status": "running", "retry_after_ms": 500}
    assert waiting.headers["retry-after"] == "1"
    assert "no-store" in waiting.headers["cache-control"]

    monkeypatch.setattr(case, "status", real_status)
    served = client.get(url, headers=headers(body))
    assert served.status_code not in (202, 503)
    if what in ("evidence", "report", "alternatives", "copy-alert"):
        assert served.status_code == 200


@pytest.mark.parametrize("what", READS)
def test_202_still_needs_the_header_token(client, monkeypatch, what):
    body, case = started(client)
    monkeypatch.setattr(
        case, "status", lambda *a, **k: SimpleNamespace(status=CaseProgress.RUNNING)
    )
    url = f"/cases/{body['case_id']}/{what}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer nope"}).status_code == 403
    assert (
        client.get(url + f"?token={body['read_token']}", headers=headers(body)).status_code == 401
    )


def test_card_says_whether_there_is_an_evidence_file(client):
    body, case = started(client)
    url = f"/cases/{body['case_id']}/card"
    assert client.get(url).json()["has_evidence"] is True
    case.files = None
    assert client.get(url).json()["has_evidence"] is False
