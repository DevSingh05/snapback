"""A11 (#102): each case is registered with its renter at creation, so delete-renter finds it,
and a case that was deleted is no longer served."""

import io
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from snapback.api.main import create_app
from snapback.safety import SafetyStore, delete_case, delete_renter
from snapback.settings import Settings
from snapback.vision.memory.store import PhotoMemory, PhotoRole

RENTER_1 = "imsg-" + "1a" * 12  # shaped like the sidecar's: "imsg-" and 24 hex characters
RENTER_2 = "imsg-" + "2b" * 12


class Recording:
    """Stand-in for lane D's safety store."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail = fail

    def register_case(self, case_id: str, renter_id: str) -> None:
        if self.fail:
            raise OSError("disk full")
        self.calls.append((case_id, renter_id))

    def cases_of(self, renter_id: str) -> list[str]:
        return [case_id for case_id, owner in self.calls if owner == renter_id]


def client_for(tmp_path: Path, registry, **settings) -> TestClient:
    made = Settings(_env_file=None, snapback_data_dir=tmp_path, **settings)
    return TestClient(create_app(made, registry=registry))


def picture(seed: int) -> Image.Image:
    """A synthetic picture: coloured shapes from a seeded generator."""
    rng = random.Random(seed)
    image = Image.new("RGB", (320, 240), tuple(rng.randrange(256) for _ in range(3)))
    pen = ImageDraw.Draw(image)
    for _ in range(30):
        x, y = rng.randrange(320), rng.randrange(240)
        box = (x, y, x + rng.randrange(20, 140), y + rng.randrange(20, 120))
        pen.rectangle(box, fill=tuple(rng.randrange(256) for _ in range(3)))
    return Image.open(io.BytesIO(_png(image)))


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


# --- registering ---------------------------------------------------------------------------


def test_a_sidecar_case_is_registered_under_the_renter_it_named(tmp_path):
    registry = Recording()
    client = client_for(tmp_path, registry)
    made = client.post("/cases", data={"text": "Two bed.", "renter_id": RENTER_1})
    assert made.status_code == 201
    # Registered under the id the other stores key on: the full one, not the short one shown.
    assert registry.calls == [(f"fx-{made.json()['case_id']}", RENTER_1)]


def test_each_of_a_renters_cases_is_registered(tmp_path):
    registry = Recording()
    client = client_for(tmp_path, registry)
    ids = [
        client.post("/cases", data={"text": "x", "renter_id": RENTER_1}).json()["case_id"]
        for _ in range(3)
    ]
    assert [call[0] for call in registry.calls] == [f"fx-{case_id}" for case_id in ids]
    assert {call[1] for call in registry.calls} == {RENTER_1}


def test_a_browser_case_is_registered_under_the_cookie_this_api_issued(tmp_path):
    registry = Recording()
    client = client_for(tmp_path, registry)
    first = client.post("/cases", data={"text": "x"})
    cookie = first.cookies["snapback_client"]
    client.post("/cases", data={"text": "x"})  # the same browser, cookie sent back
    assert [call[1] for call in registry.calls] == [f"browser:{cookie}"] * 2


def test_a_cookie_this_api_did_not_issue_is_replaced_not_stored(tmp_path):
    registry = Recording()
    client = client_for(tmp_path, registry)
    client.cookies.set("snapback_client", "555-010-0142 my name")
    made = client.post("/cases", data={"text": "x"})
    assert made.status_code == 201
    owner = registry.calls[0][1]
    assert "555" not in owner and " " not in owner
    assert owner == f"browser:{made.cookies['snapback_client']}"


def test_a_case_that_could_not_be_registered_is_not_started(tmp_path):
    # A check nobody can later delete must not exist.
    registry = Recording(fail=True)
    client = client_for(tmp_path, registry, snapback_daily_limit=1)
    refused = client.post("/cases", data={"text": "x", "renter_id": RENTER_1})
    assert refused.status_code == 503
    assert "disk full" not in refused.text
    assert len(client.app.state.store) == 1  # only the recorded fixture case

    registry.fail = False  # and it cost none of the day's checks
    assert client.post("/cases", data={"text": "x", "renter_id": RENTER_1}).status_code == 201


def test_a_refused_request_registers_nothing(tmp_path):
    registry = Recording()
    client = client_for(tmp_path, registry, snapback_daily_limit=1)
    bad_file = [("photos", ("run.exe", b"MZ\x90\x00", "application/x-msdownload"))]
    assert client.post("/cases", data={"text": "x"}, files=bad_file).status_code == 415
    assert registry.calls == []
    assert client.post("/cases", data={"text": "x", "renter_id": RENTER_1}).status_code == 201
    assert client.post("/cases", data={"text": "x", "renter_id": RENTER_1}).status_code == 429
    assert len(registry.calls) == 1


def test_with_no_registry_a_check_still_starts(tmp_path):
    client = client_for(tmp_path, None)
    made = client.post("/cases", data={"text": "x"})
    assert made.status_code == 201
    assert client.get(f"/cases/{made.json()['case_id']}/card").status_code == 200


@pytest.mark.parametrize(
    "bad",
    [
        "555-010-0142",  # a raw phone number must never be stored as an id
        "+15550100142",
        "Jo Renter",
        "imsg-12345",  # the right start, the wrong length
        "imsg-" + "G" * 24,  # not hex
        "browser:someone-elses-cookie",  # only this API names a browser
        "x" * 300,
    ],
)
def test_only_an_id_shaped_like_the_sidecars_is_taken(tmp_path, bad):
    registry = Recording()
    client = client_for(tmp_path, registry)
    assert client.post("/cases", data={"text": "x", "renter_id": bad}).status_code == 422
    assert registry.calls == []


def test_the_default_registry_makes_no_file_until_a_case_is_made(tmp_path):
    made = Settings(_env_file=None, snapback_data_dir=tmp_path)
    create_app(made)
    assert list(tmp_path.iterdir()) == []


# --- with lane D's store and delete itself -------------------------------------------------


def test_delete_renter_removes_that_renters_cases_and_leaves_the_others(tmp_path):
    made = Settings(_env_file=None, snapback_data_dir=tmp_path)
    client = TestClient(create_app(made))  # the default registry: lane D's store
    mine = [
        "fx-" + client.post("/cases", data={"text": "x", "renter_id": RENTER_1}).json()["case_id"]
        for _ in range(2)
    ]
    theirs = (
        "fx-" + (client.post("/cases", data={"text": "x", "renter_id": RENTER_2}).json()["case_id"])
    )

    # Something for the delete to remove: a listing photo of each case in the photo memory.
    memory = PhotoMemory(tmp_path / "memory" / "photo_memory.sqlite")
    memory.record(mine[0], "l1", picture(1), PhotoRole.LISTING)
    memory.record(theirs, "l1", picture(2), PhotoRole.LISTING)

    store = SafetyStore(tmp_path)
    assert store.cases_of(RENTER_1) == mine

    assert delete_renter(RENTER_1, tmp_path) == mine

    # Gone: the registration, and the photo row. A reply that copies the photo finds nothing.
    assert store.cases_of(RENTER_1) == []
    assert memory.check(mine[0], "r1", picture(1), PhotoRole.REPLY).hit == "none"
    # Kept: the other renter's case and its photo row.
    assert store.cases_of(RENTER_2) == [theirs]
    assert memory.check(theirs, "r1", picture(2), PhotoRole.REPLY).hit == "same_case_listing"


def test_a_deleted_case_is_no_longer_served_by_the_running_api(tmp_path):
    made = Settings(_env_file=None, snapback_data_dir=tmp_path)
    client = TestClient(create_app(made))
    case = client.post("/cases", data={"text": "x", "renter_id": RENTER_1}).json()
    kept = client.post("/cases", data={"text": "x", "renter_id": RENTER_2}).json()
    assert client.get(f"/cases/{case['case_id']}/card").status_code == 200

    delete_case(f"fx-{case['case_id']}", tmp_path)  # the renter's "delete", from another process

    for route in ("", "/card", "/card.png"):
        assert client.get(f"/cases/{case['case_id']}{route}").status_code == 404
    bearer = {"Authorization": f"Bearer {case['token']}"}
    approve = client.post(
        f"/cases/{case['case_id']}/challenge/approve", json={"decision": "send"}, headers=bearer
    )
    assert approve.status_code == 404
    assert len(client.app.state.store) == 2  # the recorded fixture case and the other renter's
    assert client.get(f"/cases/{kept['case_id']}/card").status_code == 200
    assert client.get("/cases/7Q2M/card").status_code == 200  # the recorded case is not owned


def test_a_browsers_case_is_deleted_and_dropped_the_same_way(tmp_path):
    made = Settings(_env_file=None, snapback_data_dir=tmp_path)
    client = TestClient(create_app(made))
    first = client.post("/cases", data={"text": "x"})
    owner = f"browser:{first.cookies['snapback_client']}"
    assert delete_renter(owner, tmp_path) == [f"fx-{first.json()['case_id']}"]
    assert client.get(f"/cases/{first.json()['case_id']}/card").status_code == 404
