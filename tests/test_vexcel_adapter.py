"""D2: Vexcel adapter. Fixture mode, the oriented/collections + extract flow, 429 budget, cache,
and the two-building proof (claimed vs matched building, with the distance)."""

import json
import os
import time
from datetime import date
from pathlib import Path

import httpx
import pytest

from snapback.adapters.vexcel import (
    VexcelKeyMissingError,
    distance_m,
    get_tile,
    two_building_proof,
)
from snapback.contracts import DataSource, PropertyRecord

JPEG = b"\xff\xd8\xff\xe0fake-tile"
RECORD = PropertyRecord(property_id="fx-prop-1", source=DataSource.FIXTURE, lat=1.5, lon=-2.5)
OTHER = PropertyRecord(property_id="fx-prop-3", source=DataSource.FIXTURE, lat=1.5, lon=-2.49)


def _image() -> httpx.Response:
    return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})


def _coverage(*directions: str, captured: str = "2025-06-01T00:00:00Z") -> httpx.Response:
    feats = [
        {"properties": {"product-type": f"oblique-{d}", "last-capture-date": captured}}
        for d in directions
    ]
    return httpx.Response(200, json={"features": feats})


class Api:
    """Mock Vexcel: a queue of responses per route; records every request."""

    def __init__(self, **routes: list[httpx.Response]) -> None:
        self.routes = {k.replace("__", "/"): v for k, v in routes.items()}
        self.seen: list[httpx.Request] = []

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            self.seen.append(request)
            route = request.url.path.removeprefix("/v2/")
            return self.routes[route].pop(0)

        return httpx.Client(transport=httpx.MockTransport(handler))


def _live(tmp_path: Path, api: Api, sleeps: list[float] | None = None, **kw):
    return get_tile(
        kw.pop("record", RECORD),
        kw.pop("direction", "north"),
        source=DataSource.LIVE,
        data_dir=tmp_path,
        api_key="fx-key",
        client=api.client(),
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )


def test_fixture_tile_mode(tmp_path):
    tile = get_tile(RECORD, source=DataSource.FIXTURE, data_dir=tmp_path)
    assert tile is not None
    assert tile.source == DataSource.FIXTURE
    assert tile.property_id == "fx-prop-1"
    assert tile.path.startswith("fixtures/")


def test_live_oblique_checks_coverage_then_extracts(tmp_path):
    api = Api(oriented__collections=[_coverage("north", "east")], oriented__extract=[_image()])
    tile = _live(tmp_path, api)
    assert tile is not None and tile.source == DataSource.LIVE
    assert tile.captured_on == date(2025, 6, 1)
    assert Path(tile.path).read_bytes() == JPEG
    coverage, extract = api.seen
    assert coverage.method == "GET" and coverage.url.params["layer"] == "urban"
    body = json.loads(extract.content)
    assert body["product-type"] == "oblique-north" and body["srid"] == 4326
    assert body["wkt"].startswith("POLYGON((-2.5")  # WKT is lon lat
    assert all(r.headers["X-API-KEY"] == "fx-key" for r in api.seen)


def test_no_oblique_in_that_direction_means_no_tile(tmp_path):
    api = Api(oriented__collections=[_coverage("east")])
    assert _live(tmp_path, api) is None
    assert len(api.seen) == 1  # no extract was tried


def test_no_oblique_coverage_404_means_no_tile(tmp_path):
    api = Api(oriented__collections=[httpx.Response(404)])
    assert _live(tmp_path, api) is None


def test_nadir_uses_the_ortho_extract(tmp_path):
    api = Api(ortho__extract=[_image()])
    tile = _live(tmp_path, api, direction="nadir")
    assert tile is not None and tile.direction == "nadir"
    assert "urban-r" in json.loads(api.seen[0].content)["layer"]


def test_429_backs_off(tmp_path):
    sleeps: list[float] = []
    api = Api(
        oriented__collections=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(429),
            _coverage("north"),
        ],
        oriented__extract=[_image()],
    )
    tile = _live(tmp_path, api, sleeps)
    assert tile is not None
    assert sleeps[0] == 2.0  # Retry-After wins
    assert sleeps[1] > 0
    assert len(api.seen) == 4


def test_gives_up_after_retries_and_returns_none(tmp_path):
    api = Api(oriented__collections=[httpx.Response(429) for _ in range(10)])
    assert _live(tmp_path, api) is None  # the card ships record facts only
    assert len(api.seen) == 4


@pytest.mark.parametrize("retry_after", ["86400", "inf", "nan"])
def test_retry_after_over_budget_gives_up_without_sleeping(tmp_path, retry_after):
    sleeps: list[float] = []
    api = Api(oriented__collections=[httpx.Response(429, headers={"Retry-After": retry_after})])
    assert _live(tmp_path, api, sleeps) is None
    assert sleeps == []
    assert len(api.seen) == 1


def test_cached_tile_skips_the_network_for_seven_days(tmp_path):
    first = _live(
        tmp_path, Api(oriented__collections=[_coverage("north")], oriented__extract=[_image()])
    )
    again_api = Api()
    again = _live(tmp_path, again_api)
    assert first is not None and again is not None and again.path == first.path
    assert again.captured_on == date(2025, 6, 1)  # kept beside the cached image
    assert again_api.seen == []

    old = time.time() - 8 * 24 * 3600
    os.utime(first.path, (old, old))
    fresh = Api(oriented__collections=[_coverage("north")], oriented__extract=[_image()])
    assert _live(tmp_path, fresh) is not None
    assert len(fresh.seen) == 2


def test_live_without_a_key_says_so(tmp_path):
    with pytest.raises(VexcelKeyMissingError, match="VEXCEL_API_KEY"):
        get_tile(RECORD, source=DataSource.LIVE, data_dir=tmp_path, api_key=None)


def test_record_without_coordinates_has_no_tile(tmp_path):
    bare = PropertyRecord(property_id="fx-prop-2", source=DataSource.FIXTURE)
    assert get_tile(bare, source=DataSource.LIVE, data_dir=tmp_path, api_key="fx-key") is None


def test_non_image_reply_is_not_cached(tmp_path):
    api = Api(
        oriented__collections=[_coverage("north")],
        oriented__extract=[httpx.Response(200, json={"error": "nope"})],
    )
    assert _live(tmp_path, api) is None
    assert not list(tmp_path.rglob("*.jpg"))


def test_direction_cannot_walk_out_of_the_cache(tmp_path):
    assert _live(tmp_path, Api(), direction="../../evil") is None  # not a known direction


def test_distance_between_two_buildings():
    d = distance_m(RECORD, OTHER)
    assert d is not None and 1100 < d < 1125  # 0.01 degrees of longitude near the equator
    assert distance_m(RECORD, PropertyRecord(property_id="fx-x", source=DataSource.FIXTURE)) is None


def test_two_building_proof_has_both_tiles_and_the_distance(tmp_path):
    proof = two_building_proof(RECORD, OTHER, source=DataSource.FIXTURE, data_dir=tmp_path)
    assert proof.claimed is not None and proof.claimed.property_id == "fx-prop-1"
    assert proof.matched is not None and proof.matched.property_id == "fx-prop-3"
    assert proof.distance_m is not None and proof.distance_m > 1000


def test_a_hostile_property_id_stays_inside_the_cache(tmp_path):
    evil = PropertyRecord(property_id="../../evil", source=DataSource.FIXTURE, lat=1.5, lon=-2.5)
    api = Api(oriented__collections=[_coverage("north")], oriented__extract=[_image()])
    tile = _live(tmp_path, api, record=evil)
    assert tile is not None
    assert Path(tile.path).resolve().parent == (tmp_path / "vexcel").resolve()
    assert ".." not in Path(tile.path).name


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json=[1, 2, 3]),
        httpx.Response(200, json={"features": [None]}),
        httpx.Response(200, json={"features": [{"properties": None}]}),
    ],
)
def test_a_malformed_coverage_reply_means_no_tile_not_a_crash(tmp_path, reply):
    assert _live(tmp_path, Api(oriented__collections=[reply])) is None


def test_a_truncated_meta_file_is_ignored(tmp_path):
    first = _live(
        tmp_path, Api(oriented__collections=[_coverage("north")], oriented__extract=[_image()])
    )
    assert first is not None
    Path(first.path).with_suffix(".json").write_text('{"captured_on": ')
    again = _live(tmp_path, Api())
    assert again is not None and again.captured_on is None


def test_one_tile_never_takes_longer_than_the_total_budget(tmp_path, monkeypatch):
    from snapback.adapters import vexcel

    now = [0.0]
    monkeypatch.setattr(vexcel, "_monotonic", lambda: now[0])

    def slow_sleep(seconds: float) -> None:
        now[0] += seconds

    api = Api(oriented__collections=[httpx.Response(429, headers={"Retry-After": "15"})] * 10)
    tile = get_tile(
        RECORD,
        source=DataSource.LIVE,
        data_dir=tmp_path,
        api_key="fx-key",
        client=api.client(),
        sleep=slow_sleep,
    )
    assert tile is None
    assert now[0] <= vexcel.TOTAL_BUDGET_S
    assert len(api.seen) == 2  # a second 15 s wait would pass the 20 s budget


class _SlowBody(httpx.SyncByteStream):
    """A reply that trickles in: each chunk advances the fake clock."""

    def __init__(self, now: list[float], chunks: int, step: float, size: int = 1024) -> None:
        self.now, self.chunks, self.step, self.size = now, chunks, step, size
        self.pulled = 0

    def __iter__(self):
        for _ in range(self.chunks):
            self.now[0] += self.step
            self.pulled += 1
            yield b"\xff" * self.size


def _stream_api(now: list[float], body: httpx.SyncByteStream) -> Api:
    return Api(
        oriented__collections=[_coverage("north")],
        oriented__extract=[
            httpx.Response(200, headers={"content-type": "image/jpeg"}, stream=body)
        ],
    )


def test_a_reply_that_trickles_past_the_budget_gives_no_tile_and_caches_nothing(
    tmp_path, monkeypatch
):
    from snapback.adapters import vexcel

    now = [0.0]
    monkeypatch.setattr(vexcel, "_monotonic", lambda: now[0])
    api = _stream_api(now, _SlowBody(now, chunks=8, step=3.0))  # 24 s of trickle
    assert _live(tmp_path, api) is None
    assert not list(tmp_path.rglob("*.jpg"))


def test_a_reply_over_5_mb_gives_no_tile(tmp_path, monkeypatch):
    from snapback.adapters import vexcel

    now = [0.0]
    monkeypatch.setattr(vexcel, "_monotonic", lambda: now[0])
    big = _SlowBody(now, chunks=10, step=0.0, size=1024 * 1024)  # 10 MB, instantly
    assert _live(tmp_path, _stream_api(now, big)) is None
    assert not list(tmp_path.rglob("*.jpg"))
    assert big.pulled == 6  # stops on the first chunk over 5 MB, never reads the rest


def test_a_coverage_reply_that_trickles_past_the_budget_gives_no_tile(tmp_path, monkeypatch):
    from snapback.adapters import vexcel

    now = [0.0]
    monkeypatch.setattr(vexcel, "_monotonic", lambda: now[0])
    slow = _SlowBody(now, chunks=10, step=3.0, size=64)  # 30 s of trickle
    api = Api(oriented__collections=[httpx.Response(200, stream=slow)])
    assert _live(tmp_path, api) is None
    assert len(api.seen) == 1  # no extract after a coverage reply that ran out of time
    assert slow.pulled <= 7


def test_every_read_is_held_to_a_short_slice(tmp_path):
    timeouts: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        if request.url.path.endswith("oriented/collections"):
            return _coverage("north")
        return _image()

    tile = get_tile(
        RECORD,
        source=DataSource.LIVE,
        data_dir=tmp_path,
        api_key="fx-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda s: None,
    )
    assert tile is not None
    assert all(t["read"] <= 2.0 for t in timeouts)  # a slow first byte cannot eat the budget


def test_content_length_over_the_cap_is_refused_before_reading(tmp_path, monkeypatch):
    from snapback.adapters import vexcel

    now = [0.0]
    monkeypatch.setattr(vexcel, "_monotonic", lambda: now[0])
    body = _SlowBody(now, chunks=1, step=0.0, size=10)
    reply = httpx.Response(
        200,
        headers={"content-type": "image/jpeg", "content-length": str(6 * 1024 * 1024)},
        stream=body,
    )
    api = Api(oriented__collections=[_coverage("north")], oriented__extract=[reply])
    assert _live(tmp_path, api) is None
    assert body.pulled == 0


def test_a_compressed_reply_is_refused_and_identity_is_asked_for(tmp_path):
    gz = httpx.Response(
        200, headers={"content-type": "image/jpeg", "content-encoding": "gzip"}, content=b"x"
    )
    api = Api(oriented__collections=[_coverage("north")], oriented__extract=[gz])
    assert _live(tmp_path, api) is None
    assert all(r.headers["Accept-Encoding"] == "identity" for r in api.seen)


def test_an_empty_image_is_not_cached(tmp_path):
    empty = httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"")
    api = Api(oriented__collections=[_coverage("north")], oriented__extract=[empty])
    assert _live(tmp_path, api) is None
    assert not list(tmp_path.rglob("*.jpg"))
