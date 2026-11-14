"""D9: the aerial proof route. Builder (adapters/vexcel.aerial_proof) and GET /cases/{id}/aerial."""

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from snapback.adapters import vexcel
from snapback.adapters.vexcel import aerial_proof, public_record
from snapback.api.main import create_app
from snapback.contracts import (
    AerialProofResponse,
    AerialSideOut,
    AerialTile,
    DataSource,
    PropertyRecord,
)
from snapback.settings import Settings

JPEG = b"\xff\xd8\xff\xe0fake-tile"
CLAIMED = PropertyRecord(
    property_id="fx-prop-1",
    source=DataSource.FIXTURE,
    floors=4,
    year_built=2015,
    lat=1.5,
    lon=-2.5,
    manager_company="Fixture Living LLC",
    site_phone_hash="fx-hash",
    website_host="fixtureliving.example",
)
MATCHED = PropertyRecord(property_id="fx-prop-3", source=DataSource.FIXTURE, lat=1.5, lon=-2.49)
RECORDS = {r.property_id: r for r in (CLAIMED, MATCHED)}


# --- builder ---------------------------------------------------------------------------------


def test_builder_returns_both_buildings_and_the_distance(tmp_path):
    proof = aerial_proof(
        "fx-7Q2M", DataSource.FIXTURE, "fx-prop-1", "fx-prop-3", records=RECORDS, data_dir=tmp_path
    )
    assert proof.claimed.tile is not None and proof.claimed.tile.property_id == "fx-prop-1"
    assert proof.matched is not None and proof.matched.tile.property_id == "fx-prop-3"
    assert proof.distance_m is not None and 1100 < proof.distance_m < 1125
    assert proof.claimed.image_url is None  # fixture: lane T draws its stand-in


def test_the_record_carries_building_facts_and_company_only():
    rec = public_record(CLAIMED)
    assert (rec.floors, rec.year_built, rec.manager_company) == (4, 2015, "Fixture Living LLC")
    assert rec.site_phone_hash is None and rec.website_host is None
    assert rec.units == [] and rec.floor_plan_rents == []


def test_no_matched_building_means_no_matched_side(tmp_path):
    proof = aerial_proof(
        "fx-7Q2M", DataSource.FIXTURE, "fx-prop-1", None, records=RECORDS, data_dir=tmp_path
    )
    assert proof.matched is None and proof.distance_m is None
    same = aerial_proof(
        "fx-7Q2M", DataSource.FIXTURE, "fx-prop-1", "fx-prop-1", records=RECORDS, data_dir=tmp_path
    )
    assert same.matched is None  # located in the claimed building is not a second building


def test_unknown_or_missing_property_ids_give_empty_sides(tmp_path):
    proof = aerial_proof("fx-7Q2M", DataSource.FIXTURE, None, "fx-nope", records=RECORDS)
    assert proof.claimed.tile is None and proof.claimed.record is None
    assert proof.matched is None


def test_live_tiles_get_our_own_image_url_never_vexcels(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("oriented/collections"):
            feats = [{"properties": {"product-type": "oblique-north", "last-capture-date": "2025"}}]
            return httpx.Response(200, json={"features": feats})
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    live = {k: v.model_copy(update={"source": DataSource.LIVE}) for k, v in RECORDS.items()}
    proof = aerial_proof(
        "fx-7Q2M",
        DataSource.LIVE,
        "fx-prop-1",
        "fx-prop-3",
        records=live,
        data_dir=tmp_path,
        api_key="fx-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda s: None,
        image_url=lambda side: f"/cases/fx-7Q2M/aerial/{side}.jpg",
    )
    assert proof.claimed.image_url == "/cases/fx-7Q2M/aerial/claimed.jpg"
    assert proof.matched is not None and proof.matched.image_url.endswith("/matched.jpg")
    text = proof.model_dump_json()
    assert "api.vexcelgroup.com" not in text and "fx-key" not in text


# --- routes ----------------------------------------------------------------------------------


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, snapback_data_dir=tmp_path)))


def _case(client: TestClient) -> dict:
    made = client.post("/cases", data={"text": "Two bed near the park."})
    assert made.status_code == 201
    return made.json()


def test_the_aerial_route_needs_a_token_in_a_header(tmp_path):
    client = _client(tmp_path)
    case = _case(client)
    url = f"/cases/{case['case_id']}/aerial"
    assert client.get(url).status_code == 401
    assert client.get(url, params={"token": case["read_token"]}).status_code == 401  # header only
    assert client.get(url, headers={"X-Case-Token": "fx-wrong"}).status_code == 403
    ok = client.get(url, headers={"Authorization": f"Bearer {case['read_token']}"})
    assert ok.status_code == 200
    body = AerialProofResponse.model_validate(ok.json())
    assert body.case_id == case["case_id"]


def test_the_json_route_never_shows_a_server_file_path(tmp_path, monkeypatch):
    tile = AerialTile(
        property_id="fx-prop-1",
        source=DataSource.LIVE,
        direction="north",
        path=str(tmp_path / "vexcel" / "fx-prop-1-north.jpg"),
    )

    def fake_proof(case_id, source, claimed_id, matched_id, **kwargs):
        return AerialProofResponse(
            case_id=case_id, source=DataSource.LIVE, claimed=AerialSideOut(tile=tile)
        )

    monkeypatch.setattr("snapback.api.main.aerial_proof", fake_proof)
    client = _client(tmp_path)
    case = _case(client)
    got = client.get(
        f"/cases/{case['case_id']}/aerial", headers={"X-Case-Token": case["read_token"]}
    )
    assert got.json()["claimed"]["tile"]["path"] == "fx-prop-1-north.jpg"
    assert str(tmp_path) not in got.text


def test_the_image_route_takes_only_the_read_token_in_the_address(tmp_path):
    client = _client(tmp_path)
    case = _case(client)
    url = f"/cases/{case['case_id']}/aerial/claimed.jpg"
    assert client.get(url).status_code == 401
    assert client.get(url, params={"token": case["token"]}).status_code == 403  # write token
    # a fixture case has no live tile to serve
    assert client.get(url, params={"token": case["read_token"]}).status_code == 404


def test_the_image_route_streams_a_live_tile_privately(tmp_path, monkeypatch):
    tile_path = tmp_path / "vexcel" / "fx-prop-1-north.jpg"
    tile_path.parent.mkdir(parents=True)
    tile_path.write_bytes(JPEG)
    tile = AerialTile(
        property_id="fx-prop-1", source=DataSource.LIVE, direction="north", path=str(tile_path)
    )

    def fake_proof(case_id, source, claimed_id, matched_id, **kwargs):
        return AerialProofResponse(
            case_id=case_id, source=DataSource.LIVE, claimed=AerialSideOut(tile=tile)
        )

    monkeypatch.setattr("snapback.api.main.aerial_proof", fake_proof)
    client = _client(tmp_path)
    case = _case(client)
    got = client.get(
        f"/cases/{case['case_id']}/aerial/claimed.jpg", params={"token": case["read_token"]}
    )
    assert got.status_code == 200 and got.content == JPEG
    assert got.headers["content-type"] == "image/jpeg"
    assert got.headers["cache-control"] == "private, max-age=600"
    missing = client.get(
        f"/cases/{case['case_id']}/aerial/matched.jpg", params={"token": case["read_token"]}
    )
    assert missing.status_code == 404


def test_a_bad_side_or_direction_is_refused(tmp_path):
    client = _client(tmp_path)
    case = _case(client)
    token = {"token": case["read_token"]}
    assert client.get(f"/cases/{case['case_id']}/aerial/other.jpg", params=token).status_code == 422
    headers = {"X-Case-Token": case["read_token"]}
    bad = client.get(f"/cases/{case['case_id']}/aerial?direction=up", headers=headers)
    assert bad.status_code == 422


def test_module_budget_is_still_twenty_seconds():
    assert vexcel.TOTAL_BUDGET_S == 20.0
    assert Path(vexcel.__file__).name == "vexcel.py"
