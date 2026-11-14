"""A11 (#102): each case is registered with its renter at creation, so delete-renter finds it."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.api.main import create_app
from snapback.settings import Settings


class Recording:
    """Stand-in for lane D's safety store."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail = fail

    def register_case(self, case_id: str, renter_id: str) -> None:
        if self.fail:
            raise OSError("disk full")
        self.calls.append((case_id, renter_id))


def client_for(tmp_path: Path, registry, **settings) -> TestClient:
    made = Settings(_env_file=None, snapback_data_dir=tmp_path, **settings)
    return TestClient(create_app(made, registry=registry))


def test_a_sidecar_case_is_registered_under_the_renter_it_named(tmp_path):
    registry = Recording()
    client = client_for(tmp_path, registry)
    made = client.post("/cases", data={"text": "Two bed.", "renter_id": "fx-renter-hash-1"})
    assert made.status_code == 201
    # Registered under the id the other stores key on: the full one, not the short one shown.
    assert registry.calls == [(f"fx-{made.json()['case_id']}", "fx-renter-hash-1")]


def test_each_of_a_renters_cases_is_registered(tmp_path):
    registry = Recording()
    client = client_for(tmp_path, registry)
    ids = [
        client.post("/cases", data={"text": "x", "renter_id": "fx-renter-hash-1"}).json()["case_id"]
        for _ in range(3)
    ]
    assert [call[0] for call in registry.calls] == [f"fx-{case_id}" for case_id in ids]
    assert {call[1] for call in registry.calls} == {"fx-renter-hash-1"}


def test_a_browser_case_is_registered_under_its_client_cookie(tmp_path):
    registry = Recording()
    client = client_for(tmp_path, registry)
    first = client.post("/cases", data={"text": "x"})
    cookie = first.cookies["snapback_client"]
    client.post("/cases", data={"text": "x"})  # the same browser, cookie sent back
    owners = [call[1] for call in registry.calls]
    assert owners == [f"browser:{cookie}"] * 2


def test_a_case_that_could_not_be_registered_is_not_started(tmp_path):
    # A check nobody can later delete must not exist.
    registry = Recording(fail=True)
    client = client_for(tmp_path, registry, snapback_daily_limit=1)
    refused = client.post("/cases", data={"text": "x", "renter_id": "fx-renter-hash-1"})
    assert refused.status_code == 503
    assert "disk full" not in refused.text
    assert len(client.app.state.store) == 1  # only the recorded fixture case

    registry.fail = False  # and it cost none of the day's checks
    assert (
        client.post("/cases", data={"text": "x", "renter_id": "fx-renter-hash-1"}).status_code
        == 201
    )


def test_a_refused_request_registers_nothing(tmp_path):
    registry = Recording()
    client = client_for(tmp_path, registry, snapback_daily_limit=1)
    bad_file = [("photos", ("run.exe", b"MZ\x90\x00", "application/x-msdownload"))]
    assert client.post("/cases", data={"text": "x"}, files=bad_file).status_code == 415
    assert registry.calls == []
    assert client.post("/cases", data={"text": "x", "renter_id": "r"}).status_code == 201
    assert client.post("/cases", data={"text": "x", "renter_id": "r"}).status_code == 429
    assert len(registry.calls) == 1


def test_with_no_registry_a_check_still_starts(tmp_path):
    client = client_for(tmp_path, None)
    assert client.post("/cases", data={"text": "x"}).status_code == 201


def test_a_renter_id_that_could_not_be_one_is_refused(tmp_path):
    registry = Recording()
    client = client_for(tmp_path, registry)
    for bad in ("x" * 300, "has spaces in it", "semi;colon"):
        assert client.post("/cases", data={"text": "x", "renter_id": bad}).status_code == 422
    assert registry.calls == []


def test_the_default_registry_makes_no_file_until_a_case_is_made(tmp_path):
    made = Settings(_env_file=None, snapback_data_dir=tmp_path)
    create_app(made)
    assert list(tmp_path.iterdir()) == []


# --- with lane D's store itself, once it is on the branch ----------------------------------


def test_delete_renter_finds_the_cases_the_api_registered(tmp_path):
    safety = pytest.importorskip("snapback.safety")
    made = Settings(_env_file=None, snapback_data_dir=tmp_path)
    client = TestClient(create_app(made))  # the default registry: lane D's store
    mine = [
        client.post("/cases", data={"text": "x", "renter_id": "fx-renter-hash-1"}).json()["case_id"]
        for _ in range(2)
    ]
    client.post("/cases", data={"text": "x", "renter_id": "fx-renter-hash-2"})

    store = safety.SafetyStore(tmp_path)
    assert store.cases_of("fx-renter-hash-1") == [f"fx-{case_id}" for case_id in mine]
    deleted = safety.delete_renter("fx-renter-hash-1", tmp_path)
    assert deleted == [f"fx-{case_id}" for case_id in mine]
    assert len(store.cases_of("fx-renter-hash-2")) == 1
