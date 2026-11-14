from fastapi.testclient import TestClient

from snapback.api.main import app

client = TestClient(app)


def test_healthz_reports_the_data_source():
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["data_source"] in {"live", "fixture"}


def test_verdict_endpoint_round_trips_the_contract():
    payload = {
        "case_id": "case-1",
        "source": "fixture",
        "photos": [{"photo_id": "p1", "status": "located_in_claimed"}],
    }
    response = client.post("/verdict", json=payload)
    assert response.status_code == 200
    assert response.json()["state"] == "hold"
