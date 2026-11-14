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


def _case(client: TestClient, property_id: str | None = None) -> dict:
    form = {"text": "Two bed near the park."}
    if property_id:
        form["property_id"] = property_id
    made = client.post("/cases", data=form)
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


def test_the_image_route_takes_the_token_in_a_header_only(tmp_path):
    client = _client(tmp_path)
    case = _case(client)
    url = f"/cases/{case['case_id']}/aerial/claimed.jpg"
    assert client.get(url).status_code == 401
    # header only (ruling on #113): a token in the address is not accepted
    assert client.get(url, params={"token": case["read_token"]}).status_code == 401
    assert client.get(url, headers={"X-Case-Token": "fx-wrong"}).status_code == 403
    # a fixture case has no live tile to serve
    assert client.get(url, headers={"X-Case-Token": case["read_token"]}).status_code == 404


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

    monkeypatch.setattr("snapback.api.main.aerial_side", lambda *a, **k: tile)
    client = _client(tmp_path)
    case = _case(client, "fx-prop-4")
    got = client.get(
        f"/cases/{case['case_id']}/aerial/claimed.jpg", headers={"X-Case-Token": case["read_token"]}
    )
    assert got.status_code == 200 and got.content == JPEG
    assert got.headers["content-type"] == "image/jpeg"
    assert got.headers["cache-control"] == "private, max-age=600"
    missing = client.get(
        f"/cases/{case['case_id']}/aerial/matched.jpg", headers={"X-Case-Token": case["read_token"]}
    )
    assert missing.status_code == 404


def test_a_bad_side_or_direction_is_refused(tmp_path):
    client = _client(tmp_path)
    case = _case(client)
    token = {"X-Case-Token": case["read_token"]}
    assert (
        client.get(f"/cases/{case['case_id']}/aerial/other.jpg", headers=token).status_code == 422
    )
    headers = {"X-Case-Token": case["read_token"]}
    bad = client.get(f"/cases/{case['case_id']}/aerial?direction=up", headers=headers)
    assert bad.status_code == 422


def test_module_budget_is_still_twenty_seconds():
    assert vexcel.TOTAL_BUDGET_S == 20.0
    assert Path(vexcel.__file__).name == "vexcel.py"


def test_the_recorded_fixture_case_needs_no_token(tmp_path):
    client = _client(tmp_path)
    assert client.get("/cases/7Q2M/aerial").status_code == 200


def test_a_tile_purged_between_calls_is_a_404_not_a_500(tmp_path, monkeypatch):
    tile = AerialTile(
        property_id="fx-prop-1",
        source=DataSource.LIVE,
        direction="north",
        path=str(tmp_path / "vexcel" / "gone.jpg"),
    )

    def fake_proof(case_id, source, claimed_id, matched_id, **kwargs):
        return AerialProofResponse(
            case_id=case_id, source=DataSource.LIVE, claimed=AerialSideOut(tile=tile)
        )

    monkeypatch.setattr("snapback.api.main.aerial_side", lambda *a, **k: tile)
    client = _client(tmp_path)
    case = _case(client, "fx-prop-4")
    got = client.get(
        f"/cases/{case['case_id']}/aerial/claimed.jpg", headers={"X-Case-Token": case["read_token"]}
    )
    assert got.status_code == 404


def test_a_tile_path_outside_the_data_dir_is_never_served(tmp_path, monkeypatch):
    outside = tmp_path.parent / "outside-secret.jpg"
    outside.write_bytes(JPEG)
    tile = AerialTile(
        property_id="fx-prop-1", source=DataSource.LIVE, direction="north", path=str(outside)
    )

    def fake_proof(case_id, source, claimed_id, matched_id, **kwargs):
        return AerialProofResponse(
            case_id=case_id, source=DataSource.LIVE, claimed=AerialSideOut(tile=tile)
        )

    monkeypatch.setattr("snapback.api.main.aerial_side", lambda *a, **k: tile)
    client = _client(tmp_path / "data")
    case = _case(client, "fx-prop-4")
    got = client.get(
        f"/cases/{case['case_id']}/aerial/claimed.jpg", headers={"X-Case-Token": case["read_token"]}
    )
    assert got.status_code == 404


def test_the_json_route_does_not_change_the_builders_object(tmp_path, monkeypatch):
    tile = AerialTile(
        property_id="fx-prop-1",
        source=DataSource.LIVE,
        direction="north",
        path=str(tmp_path / "vexcel" / "fx-prop-1-north.jpg"),
    )
    proof = AerialProofResponse(
        case_id="x", source=DataSource.LIVE, claimed=AerialSideOut(tile=tile)
    )
    monkeypatch.setattr("snapback.api.main.aerial_proof", lambda *a, **k: proof)
    client = _client(tmp_path)
    case = _case(client)
    client.get(f"/cases/{case['case_id']}/aerial", headers={"X-Case-Token": case["read_token"]})
    assert proof.claimed.tile.path == str(tmp_path / "vexcel" / "fx-prop-1-north.jpg")


def test_the_kit_is_parsed_once_per_process(monkeypatch, tmp_path):
    from snapback.adapters import costar_jsonl

    calls = []
    real = costar_jsonl.load_records

    def counting(source=None, kit_dir=None):
        calls.append(source)
        return real(source, kit_dir)

    monkeypatch.setattr(costar_jsonl, "load_records", counting)
    vexcel.kit_records.cache_clear()
    for _ in range(3):
        aerial_proof("fx-7Q2M", DataSource.FIXTURE, "fx-prop-1", None, data_dir=tmp_path)
    assert len(calls) == 1
    vexcel.kit_records.cache_clear()


def test_a_missing_vexcel_key_keeps_the_record_and_distance(tmp_path, monkeypatch):
    def no_key(*args, **kwargs):
        raise vexcel.VexcelKeyMissingError("VEXCEL_API_KEY is not set")

    monkeypatch.setattr(vexcel, "get_tile", no_key)
    proof = aerial_proof("fx-7Q2M", DataSource.LIVE, "fx-prop-1", "fx-prop-3", records=RECORDS)
    assert proof.claimed.tile is None and proof.claimed.record is not None
    assert proof.matched is not None and proof.matched.record is not None
    assert proof.distance_m is not None


def test_the_route_answers_200_without_a_vexcel_key(tmp_path, monkeypatch):
    def no_key(*args, **kwargs):
        raise vexcel.VexcelKeyMissingError("VEXCEL_API_KEY is not set")

    monkeypatch.setattr(vexcel, "get_tile", no_key)
    client = _client(tmp_path)
    made = client.post("/cases", data={"text": "Two bed.", "property_id": "fx-prop-4"})
    case = made.json()
    got = client.get(
        f"/cases/{case['case_id']}/aerial", headers={"X-Case-Token": case["read_token"]}
    )
    assert got.status_code == 200
    body = got.json()
    assert body["claimed"]["tile"] is None and body["claimed"]["record"]["year_built"] == 2019


def test_the_route_never_shows_the_phone_hash_site_units_or_rent_bands(tmp_path):
    client = _client(tmp_path)
    made = client.post("/cases", data={"text": "Two bed.", "property_id": "fx-prop-4"})
    case = made.json()
    got = client.get(
        f"/cases/{case['case_id']}/aerial", headers={"X-Case-Token": case["read_token"]}
    )
    assert got.status_code == 200
    record = got.json()["claimed"]["record"]
    assert record is not None and record["property_id"] == "fx-prop-4"
    assert record["site_phone_hash"] is None and record["website_host"] is None
    assert record["units"] == [] and record["floor_plan_rents"] == []
    assert "fixtureliving" not in got.text and "0123" not in got.text and "4B" not in got.text


def test_the_builder_has_a_hard_deadline(monkeypatch):
    import time as _time

    def slow(*args, **kwargs):
        _time.sleep(2.0)
        return None

    monkeypatch.setattr(vexcel, "get_tile", slow)
    monkeypatch.setattr(vexcel, "TOTAL_BUDGET_S", 0.3)
    start = _time.perf_counter()
    proof = aerial_proof("fx-7Q2M", DataSource.LIVE, "fx-prop-1", "fx-prop-3", records=RECORDS)
    assert _time.perf_counter() - start < 1.0
    assert proof.claimed.tile is None and proof.matched is not None


def test_a_missing_kit_is_not_cached_for_good(monkeypatch):
    from snapback.adapters import costar_jsonl

    calls = []

    def flaky(source=None, kit_dir=None):
        calls.append(source)
        if len(calls) == 1:
            raise costar_jsonl.KitNotFoundError("not yet")
        return RECORDS

    monkeypatch.setattr(costar_jsonl, "load_records", flaky)
    vexcel.kit_records.cache_clear()
    assert vexcel.kit_records(DataSource.LIVE) == {}
    assert vexcel.kit_records(DataSource.LIVE) == RECORDS  # the kit arrived: read again
    vexcel.kit_records(DataSource.LIVE)
    assert len(calls) == 2  # and then kept
    vexcel.kit_records.cache_clear()


def test_the_image_route_fetches_only_the_side_asked_for(tmp_path, monkeypatch):
    calls: list[str] = []

    def counting(rec, direction="north", **kwargs):
        calls.append(rec.property_id)
        return None

    monkeypatch.setattr(vexcel, "get_tile", counting)
    client = _client(tmp_path)
    made = client.post("/cases", data={"text": "Two bed.", "property_id": "fx-prop-4"})
    case = made.json()
    got = client.get(
        f"/cases/{case['case_id']}/aerial/claimed.jpg",
        headers={"X-Case-Token": case["read_token"]},
    )
    assert got.status_code == 404  # no tile, but only one building was asked for
    assert calls == ["fx-prop-4"]


def test_the_tile_cache_sits_under_the_settings_data_dir(tmp_path, monkeypatch):
    from snapback.safety import paths

    monkeypatch.setattr(paths, "REPO_ROOT", tmp_path)
    elsewhere = tmp_path / "apps" / "web"
    elsewhere.mkdir(parents=True)
    monkeypatch.chdir(elsewhere)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("oriented/collections"):
            feats = [{"properties": {"product-type": "oblique-north", "last-capture-date": "2025"}}]
            return httpx.Response(200, json={"features": feats})
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    live = MATCHED.model_copy(update={"source": DataSource.LIVE})
    tile = vexcel.get_tile(
        live,
        source=DataSource.LIVE,
        data_dir=Path("data"),
        api_key="fx-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda s: None,
    )
    assert tile is not None
    assert Path(tile.path).resolve().parent == (tmp_path / "data" / "vexcel").resolve()


class _NoKitLookups:
    """Live-mode lookups with the kit missing: every records() call raises KitMissing."""

    def record(self, property_id):
        return None

    def for_sale(self, listing_text):
        return None

    def records(self):
        from snapback.agent.join import KitMissing

        raise KitMissing()


def test_a_missing_kit_is_not_a_500(tmp_path):
    client = TestClient(
        create_app(Settings(_env_file=None, snapback_data_dir=tmp_path), lookups=_NoKitLookups())
    )
    case = _case(client)
    got = client.get(
        f"/cases/{case['case_id']}/aerial", headers={"X-Case-Token": case["read_token"]}
    )
    assert got.status_code == 200
    assert got.json()["claimed"]["tile"] is None


def test_a_disk_error_through_the_route_keeps_the_record(tmp_path, monkeypatch):
    def disk_full(*args, **kwargs):
        raise OSError("no space left")

    monkeypatch.setattr(vexcel, "get_tile", disk_full)
    client = _client(tmp_path)
    case = _case(client, "fx-prop-4")
    got = client.get(
        f"/cases/{case['case_id']}/aerial", headers={"X-Case-Token": case["read_token"]}
    )
    assert got.status_code == 200
    body = got.json()
    assert body["claimed"]["tile"] is None and body["claimed"]["record"]["year_built"] == 2019


def test_a_tile_is_written_atomically(tmp_path, monkeypatch):
    import os

    replaced: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src, dst):
        replaced.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(vexcel.os, "replace", spy)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("oriented/collections"):
            feats = [{"properties": {"product-type": "oblique-north", "last-capture-date": "2025"}}]
            return httpx.Response(200, json={"features": feats})
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    live = MATCHED.model_copy(update={"source": DataSource.LIVE})
    tile = vexcel.get_tile(
        live,
        source=DataSource.LIVE,
        data_dir=tmp_path,
        api_key="fx-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda s: None,
    )
    assert tile is not None and Path(tile.path).read_bytes() == JPEG
    assert any(dst == tile.path for _, dst in replaced)  # the jpg arrived by rename, whole
    assert all(Path(src).parent == Path(tile.path).parent for src, _ in replaced)
    assert not list((tmp_path / "vexcel").glob("*.tmp"))
