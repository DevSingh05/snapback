"""D2: Vexcel tile adapter. Fixture mode, 429 back-off, 7-day cache under data/."""

import os
import time
from pathlib import Path

import httpx
import pytest

from snapback.adapters.vexcel import VexcelKeyMissingError, get_tile
from snapback.contracts import DataSource, PropertyRecord

JPEG = b"\xff\xd8\xff\xe0fake-tile"
RECORD = PropertyRecord(property_id="fx-prop-1", source=DataSource.FIXTURE, lat=1.5, lon=-2.5)


def _client(responses: list[httpx.Response], seen: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses.pop(0)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fixture_tile_mode(tmp_path):
    tile = get_tile(RECORD, source=DataSource.FIXTURE, data_dir=tmp_path)
    assert tile is not None
    assert tile.source == DataSource.FIXTURE
    assert tile.property_id == "fx-prop-1"
    assert tile.path.startswith("fixtures/")


def test_429_backs_off(tmp_path):
    seen: list[httpx.Request] = []
    sleeps: list[float] = []
    responses = [
        httpx.Response(429, headers={"Retry-After": "2"}),
        httpx.Response(429),
        httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"}),
    ]
    tile = get_tile(
        RECORD,
        source=DataSource.LIVE,
        data_dir=tmp_path,
        api_key="fx-key",
        client=_client(responses, seen),
        sleep=sleeps.append,
    )
    assert tile is not None and tile.source == DataSource.LIVE
    assert len(seen) == 3
    assert sleeps[0] == 2.0  # Retry-After wins
    assert sleeps[1] > 0
    assert Path(tile.path).read_bytes() == JPEG
    assert seen[0].headers["X-API-KEY"] == "fx-key"


def test_gives_up_after_retries_and_returns_none(tmp_path):
    seen: list[httpx.Request] = []
    tile = get_tile(
        RECORD,
        source=DataSource.LIVE,
        data_dir=tmp_path,
        api_key="fx-key",
        client=_client([httpx.Response(429) for _ in range(10)], seen),
        sleep=lambda s: None,
    )
    assert tile is None  # the card ships record facts only
    assert len(seen) == 4


def test_cached_tile_skips_the_network_for_seven_days(tmp_path):
    seen: list[httpx.Request] = []
    ok = httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    args = dict(source=DataSource.LIVE, data_dir=tmp_path, api_key="fx-key", sleep=lambda s: None)
    first = get_tile(RECORD, client=_client([ok], seen), **args)
    again = get_tile(RECORD, client=_client([], seen), **args)
    assert first is not None and again is not None and again.path == first.path
    assert len(seen) == 1

    old = time.time() - 8 * 24 * 3600
    os.utime(first.path, (old, old))
    fresh = httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    assert get_tile(RECORD, client=_client([fresh], seen), **args) is not None
    assert len(seen) == 2


def test_live_without_a_key_says_so(tmp_path):
    with pytest.raises(VexcelKeyMissingError, match="VEXCEL_API_KEY"):
        get_tile(RECORD, source=DataSource.LIVE, data_dir=tmp_path, api_key=None)


def test_record_without_coordinates_has_no_tile(tmp_path):
    bare = PropertyRecord(property_id="fx-prop-2", source=DataSource.FIXTURE)
    assert get_tile(bare, source=DataSource.LIVE, data_dir=tmp_path, api_key="fx-key") is None


def test_non_image_reply_is_not_cached(tmp_path):
    seen: list[httpx.Request] = []
    bad = httpx.Response(200, json={"error": "nope"})
    tile = get_tile(
        RECORD,
        source=DataSource.LIVE,
        data_dir=tmp_path,
        api_key="fx-key",
        client=_client([bad], seen),
        sleep=lambda s: None,
    )
    assert tile is None
    assert not list(tmp_path.rglob("*.jpg"))
