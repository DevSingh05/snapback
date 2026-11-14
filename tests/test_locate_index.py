"""V1: Matterport skybox fetch (fixture and live behind one switch) and the retrieval index."""

import io
import json
import os

import httpx
import pytest
from PIL import Image

from snapback.adapters.matterport import (
    FixtureMatterport,
    LiveMatterport,
    MatterportSettings,
    get_matterport,
)
from snapback.contracts import DataSource
from snapback.vision.embed import TinyEmbedder
from snapback.vision.locate.index import LocateIndex, views


def jpeg(image: Image.Image, quality: int = 60) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


# --- the adapter -------------------------------------------------------------------------------


def test_matterport_adapter_fixture_mode_needs_no_key(tmp_path):
    settings = MatterportSettings(_env_file=None, snapback_data_source=DataSource.FIXTURE)
    adapter = get_matterport(settings, cache_dir=tmp_path)
    assert isinstance(adapter, FixtureMatterport)

    sweeps = adapter.sweeps("fx-model-a")
    assert len(sweeps) >= 3
    for sweep in sweeps:
        assert len(sweep.faces) == 6
        assert all(path.is_file() and path.is_relative_to(tmp_path) for path in sweep.faces)
        assert sweep.position is not None


def test_fixture_mode_refuses_ids_that_are_not_fixtures(tmp_path):
    with pytest.raises(ValueError, match="fx-"):
        FixtureMatterport(tmp_path).sweeps("abcDEF12345")


def test_live_mode_without_keys_says_which_keys(tmp_path):
    settings = MatterportSettings(_env_file=None, snapback_data_source=DataSource.LIVE)
    with pytest.raises(RuntimeError, match="MATTERPORT_API_KEY"):
        get_matterport(settings, cache_dir=tmp_path)


def _face_bytes(colour: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), colour).save(buffer, format="JPEG")
    return buffer.getvalue()


def _graph(with_pose: bool) -> dict:
    location = {
        "id": "sw1",
        "panos": [{"skybox": {"children": [f"https://cdn.test/f{i}.jpg?sig=x" for i in range(6)]}}],
    }
    if with_pose:
        location["position"] = {"x": 1.0, "y": 2.0, "z": 0.5}
        location["panos"][0]["rotation"] = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    return {"data": {"model": {"locations": [location]}}}


def test_live_adapter_fetches_faces_into_the_cache(tmp_path):
    seen = {"auth": None, "faces": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.matterport.com":
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json=_graph(with_pose=True))
        seen["faces"] += 1
        return httpx.Response(200, content=_face_bytes((200, 10, 10)))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = LiveMatterport("key-id", "secret", cache_dir=tmp_path, client=client)
    sweeps = adapter.sweeps("model123")

    assert seen["auth"].startswith("Basic ")
    assert len(sweeps) == 1 and len(sweeps[0].faces) == 6
    assert sweeps[0].position == (1.0, 2.0, 0.5)
    assert sweeps[0].rotation_quat == (0.0, 0.0, 0.0, 1.0)
    assert all(path.is_file() for path in sweeps[0].faces)

    # A second call reads the cache and downloads nothing.
    again = adapter.sweeps("model123")
    assert seen["faces"] == 6
    assert [s.faces for s in again] == [s.faces for s in sweeps]
    # No signed URL is kept on disk.
    assert "sig=" not in json.dumps(json.loads((tmp_path / "model123" / "sweeps.json").read_text()))


def test_live_adapter_falls_back_when_pose_fields_are_rejected(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.matterport.com":
            query = json.loads(request.content)["query"]
            calls.append("position" in query)
            if "position" in query:
                return httpx.Response(200, json={"errors": [{"message": "no field position"}]})
            return httpx.Response(200, json=_graph(with_pose=False))
        return httpx.Response(200, content=_face_bytes((0, 0, 200)))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sweeps = LiveMatterport("k", "s", cache_dir=tmp_path, client=client).sweeps("m1")
    assert calls == [True, False]
    assert sweeps[0].position is None and len(sweeps[0].faces) == 6


def test_live_adapter_retries_after_429(tmp_path, monkeypatch):
    monkeypatch.setattr("snapback.adapters.matterport.time.sleep", lambda _: None)
    replies = iter([httpx.Response(429), httpx.Response(200, json=_graph(with_pose=True))])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.matterport.com":
            return next(replies)
        return httpx.Response(200, content=_face_bytes((9, 9, 9)))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert LiveMatterport("k", "s", cache_dir=tmp_path, client=client).sweeps("m2")


# --- the index ---------------------------------------------------------------------------------


@pytest.fixture
def fixture_sweeps(tmp_path):
    return FixtureMatterport(tmp_path).sweeps("fx-model-a")


def test_views_include_the_face_and_narrower_crops():
    named = views(Image.new("RGB", (512, 512)))
    names = [name for name, _ in named]
    assert names[0] == "face" and len(named) == 6
    assert all(image.size[0] < 512 for _, image in named[1:])


def test_index_retrieves_the_same_view_top1(fixture_sweeps):
    index = LocateIndex.build("fx-model-a", fixture_sweeps, TinyEmbedder())
    assert len(index) == len(fixture_sweeps) * 6 * 6

    for sweep in fixture_sweeps:
        for face_number in (1, 4):
            with Image.open(sweep.faces[face_number]) as face:
                width, height = face.size
                query = jpeg(face.crop((40, 30, width - 20, height - 50)).resize((300, 300)))
            top = index.search(query, k=3)[0]
            assert (top.entry.sweep_id, top.entry.face) == (sweep.sweep_id, face_number)


def test_index_round_trips_through_disk(fixture_sweeps, tmp_path):
    index = LocateIndex.build("fx-model-a", fixture_sweeps, TinyEmbedder())
    index.save(tmp_path / "idx")
    again = LocateIndex.load(tmp_path / "idx")
    assert again.entries == index.entries
    assert again.embedder_name == "tiny"
    with Image.open(fixture_sweeps[0].faces[2]) as face:
        query = face.convert("RGB")
    assert again.search(query, k=1)[0].entry == index.search(query, k=1)[0].entry


def test_index_refuses_a_different_embedder(fixture_sweeps):
    index = LocateIndex.build("fx-model-a", fixture_sweeps, TinyEmbedder())

    class Other(TinyEmbedder):
        name = "other"

    with pytest.raises(ValueError, match="embedder"):
        index.search(Image.new("RGB", (64, 64)), k=1, embedder=Other())


@pytest.mark.skipif(
    os.environ.get("SNAPBACK_TEST_DINOV2") != "1",
    reason="downloads DINOv2 weights; run with SNAPBACK_TEST_DINOV2=1",
)
def test_dinov2_index_retrieves_the_same_view_top1(fixture_sweeps):  # pragma: no cover
    from snapback.vision.embed import Dinov2Embedder

    index = LocateIndex.build("fx-model-a", fixture_sweeps, Dinov2Embedder())
    with Image.open(fixture_sweeps[1].faces[3]) as face:
        query = jpeg(face.convert("RGB"))
    top = index.search(query, k=1)[0]
    assert (top.entry.sweep_id, top.entry.face) == (fixture_sweeps[1].sweep_id, 3)


# --- follow-ups from the V1 review (#10) -------------------------------------------------------


def test_purge_deletes_the_faces_and_the_index(tmp_path):
    from snapback.adapters.matterport import purge

    faces, index = tmp_path / "matterport", tmp_path / "index"
    (faces / "m1").mkdir(parents=True)
    (faces / "m1" / "sweeps.json").write_text("[]")
    (index / "demo").mkdir(parents=True)
    (index / "demo" / "vectors.npy").write_bytes(b"x")
    purge(faces, index_dir=index)
    assert not faces.exists() and not index.exists()


def test_model_with_no_skybox_sweeps_is_a_clear_error_and_is_not_cached(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        empty = {"id": "sw1", "panos": [{"skybox": {"children": []}}]}
        return httpx.Response(200, json={"data": {"model": {"locations": [empty]}}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = LiveMatterport("k", "s", cache_dir=tmp_path, client=client)
    with pytest.raises(RuntimeError, match="no skybox"):
        adapter.sweeps("m-empty")
    assert not (tmp_path / "m-empty" / "sweeps.json").exists()


def test_dinov2_is_pinned_to_a_commit():
    import re

    from snapback.vision.embed import DINOV2_REPO

    assert re.fullmatch(r"facebookresearch/dinov2:[0-9a-f]{40}", DINOV2_REPO)


def test_build_command_indexes_fixture_models_and_prints_counts_only(tmp_path, capsys):
    from snapback.vision.locate.index import main

    out = tmp_path / "idx"
    code = main(
        [
            "build",
            "fx-model-a",
            "fx-model-b",
            "--embedder",
            "tiny",
            "--out",
            str(out),
            "--cache",
            str(tmp_path / "faces"),
            "--source",
            "fixture",
        ]
    )
    assert code == 0
    index = LocateIndex.load(out)
    assert {entry.model_id for entry in index.entries} == {"fx-model-a", "fx-model-b"}
    printed = capsys.readouterr().out
    assert "models 2" in printed and "fx-model" not in printed


def test_build_command_with_every_model_skipped_says_so(tmp_path, capsys):
    from snapback.vision.locate.index import main

    code = main(
        [
            "build",
            "not-a-fixture-id",
            "--embedder",
            "tiny",
            "--out",
            str(tmp_path / "i"),
            "--cache",
            str(tmp_path / "faces"),
            "--source",
            "fixture",
        ]
    )
    assert code == 1
    assert "all 1 models were skipped" in capsys.readouterr().out
    assert not (tmp_path / "i").exists()


def test_live_adapter_retries_a_dropped_connection(tmp_path, monkeypatch):
    monkeypatch.setattr("snapback.adapters.matterport.time.sleep", lambda _: None)
    calls = {"graph": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.matterport.com":
            calls["graph"] += 1
            if calls["graph"] == 1:
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
            return httpx.Response(200, json=_graph(with_pose=True))
        return httpx.Response(200, content=_face_bytes((1, 2, 3)))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert LiveMatterport("k", "s", cache_dir=tmp_path, client=client).sweeps("m3")
    assert calls["graph"] == 2


def test_live_adapter_gives_up_after_repeated_drops_with_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr("snapback.adapters.matterport.time.sleep", lambda _: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="network"):
        LiveMatterport("k", "s", cache_dir=tmp_path, client=client).sweeps("m4")


@pytest.mark.parametrize("status", [401, 403])
def test_an_auth_refusal_is_one_call_no_sleep_and_no_secret_in_the_error(
    tmp_path, monkeypatch, status
):
    slept = []
    monkeypatch.setattr("snapback.adapters.matterport.time.sleep", slept.append)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError) as caught:
        LiveMatterport("key-id-123", "secret-xyz", cache_dir=tmp_path, client=client).sweeps("m5")
    assert len(calls) == 1 and slept == []
    message = str(caught.value)
    assert "api.matterport.com" not in message and "key-id-123" not in message
    assert "secret-xyz" not in message and str(status) in message


@pytest.mark.parametrize(
    ("retry_after", "expected"),
    [("2", 2.0), ("Wed, 21 Oct 2015 07:28:00 GMT", 1.0), ("3600", 30.0), ("nonsense", 1.0)],
)
def test_retry_after_is_parsed_safely_and_capped(tmp_path, monkeypatch, retry_after, expected):
    slept = []
    monkeypatch.setattr("snapback.adapters.matterport.time.sleep", slept.append)
    replies = iter(
        [
            httpx.Response(429, headers={"retry-after": retry_after}),
            httpx.Response(200, json=_graph(with_pose=True)),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.matterport.com":
            return next(replies)
        return httpx.Response(200, content=_face_bytes((5, 5, 5)))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    LiveMatterport("k", "s", cache_dir=tmp_path, client=client).sweeps("m6")
    assert slept == [expected]


def test_cached_room_labels_read_the_cache_and_never_the_network(tmp_path, monkeypatch):
    from snapback.adapters.matterport import cached_room_labels

    (tmp_path / "m7").mkdir()
    (tmp_path / "m7" / "rooms.json").write_text(json.dumps({"sw1": "Kitchen", "sw2": None}))
    monkeypatch.setattr(httpx.Client, "request", lambda *a, **k: pytest.fail("network used"))
    assert cached_room_labels("m7", cache_dir=tmp_path) == {"sw1": "Kitchen", "sw2": None}
    assert cached_room_labels("never-fetched", cache_dir=tmp_path) == {}
    (tmp_path / "m7" / "rooms.json").write_text("{not json")
    assert cached_room_labels("m7", cache_dir=tmp_path) == {}
