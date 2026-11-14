"""The Finder's voice routes (ElevenLabs). The network is a mock transport: no key is real, no
call leaves the machine."""

import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from snapback.api.main import create_app
from snapback.api.voice import STT_MAX_BYTES, TTS_MAX_CHARS
from snapback.settings import Settings

KEY = "xi-test-key-not-real-0042"
MP3 = b"ID3\x04fake-mp3-bytes"
CLIP = b"\x1aE\xdf\xa3fake-webm-opus"


class Upstream:
    """Stands in for api.elevenlabs.io and remembers every request."""

    def __init__(self, heard: str = "Under $1,500, no walk-ups.", status: int = 200) -> None:
        self.heard = heard
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "upstream says no"})
        if request.url.path.startswith("/v1/text-to-speech/"):
            return httpx.Response(200, content=MP3, headers={"content-type": "audio/mpeg"})
        if request.url.path == "/v1/speech-to-text":
            return httpx.Response(200, json={"text": self.heard, "language_code": "en"})
        return httpx.Response(404)


def make(tmp_path, upstream: Upstream | None = None, key: str | None = KEY) -> TestClient:
    settings = Settings(snapback_data_dir=tmp_path, elevenlabs_api_key=key)
    transport = httpx.MockTransport(upstream or Upstream())
    return TestClient(create_app(settings, voice_transport=transport))


def stt(client: TestClient, data: bytes = CLIP, **form):
    return client.post(
        "/voice/stt", files={"audio": ("clip.webm", data, "audio/webm;codecs=opus")}, data=form
    )


def test_no_key_means_503_and_status_says_off(tmp_path):
    upstream = Upstream()
    client = make(tmp_path, upstream, key=None)
    assert client.get("/voice/status").json() == {"tts": False, "stt": False}
    for res in (client.post("/voice/tts", json={"text": "Hello"}), stt(client)):
        assert res.status_code == 503
        assert res.json() == {"reason": "voice not configured"}
    assert upstream.requests == []


def test_tts_returns_mp3_and_sends_the_key_only_in_the_header(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    upstream = Upstream()
    client = make(tmp_path, upstream)
    assert client.get("/voice/status").json() == {"tts": True, "stt": True}
    res = client.post("/voice/tts", json={"text": "I put three places up front."})
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/mpeg"
    assert res.content == MP3
    (sent,) = upstream.requests
    assert sent.headers["xi-api-key"] == KEY
    assert KEY not in str(sent.url)
    assert KEY.encode() not in sent.content
    assert b"I put three places up front." in sent.content
    assert KEY not in caplog.text
    assert all(KEY not in v for v in res.headers.values())


def test_stt_text_is_sanitised_before_anyone_reads_it(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    upstream = Upstream(heard="Under $1,500, text me at 713-555-0142 or 12 Main Street.")
    client = make(tmp_path, upstream)
    res = stt(client, seconds="4.2")
    assert res.status_code == 200
    text = res.json()["text"]
    assert "713" not in text and "Main Street" not in text
    assert "[removed]" in text and "Under $1,500" in text
    (sent,) = upstream.requests
    assert sent.headers["xi-api-key"] == KEY
    assert KEY not in str(sent.url) and KEY.encode() not in sent.content
    assert b"scribe_v1" in sent.content
    assert KEY not in caplog.text
    assert KEY not in res.text


def test_oversize_is_413_and_never_reaches_elevenlabs(tmp_path):
    upstream = Upstream()
    client = make(tmp_path, upstream)
    too_big = stt(client, data=b"\0" * (STT_MAX_BYTES + 128 * 1024))
    assert too_big.status_code == 413
    too_long = stt(client, seconds="75")
    assert too_long.status_code == 413
    long_text = client.post("/voice/tts", json={"text": "a" * (TTS_MAX_CHARS + 1)})
    assert long_text.status_code == 422
    huge_body = client.post("/voice/tts", content=b"{" + b" " * 8000 + b"}")
    assert huge_body.status_code == 413
    assert upstream.requests == []


def test_only_audio_is_accepted(tmp_path):
    client = make(tmp_path)
    res = client.post("/voice/stt", files={"audio": ("x.png", b"\x89PNG", "image/png")})
    assert res.status_code == 415


def test_upstream_failure_is_a_plain_502_without_its_body(tmp_path):
    client = make(tmp_path, Upstream(status=401))
    res = client.post("/voice/tts", json={"text": "Hello"})
    assert res.status_code == 502
    assert "upstream" not in res.text and KEY not in res.text


@pytest.mark.parametrize("route", ["tts", "stt"])
def test_rate_limited_per_address(tmp_path, route):
    client = make(tmp_path)
    codes = [
        (
            client.post("/voice/tts", json={"text": "Hi"}) if route == "tts" else stt(client)
        ).status_code
        for _ in range(22)
    ]
    assert codes[:20] == [200] * 20
    assert codes[-1] == 429
