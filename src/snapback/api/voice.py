"""The Finder's voice, through ElevenLabs, so the browser never holds the key.

    GET  /voice/status   {"tts": bool, "stt": bool}: whether voice is configured on this server
    POST /voice/tts      {"text": "..."} (600 characters at most) -> audio/mpeg
    POST /voice/stt      multipart: audio (2 MB at most), seconds (60 at most) -> {"text": "..."}

`ELEVENLABS_API_KEY` goes only in the `xi-api-key` header of the call to ElevenLabs. It is never
logged, never echoed in an error and never sent to the browser. Without it both routes answer
503 {"reason": "voice not configured"}. What Scribe hears passes through the Finder's own
sanitiser (phone numbers, emails, links and street addresses become [removed]) before the web
app shows it or the Finder reads it. Audio is not stored.
"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from snapback.agent.finder import clean_words
from snapback.api.limits import DailyLimit, PerMinuteLimit
from snapback.api.uploads import MB
from snapback.settings import Settings

ELEVENLABS = "https://api.elevenlabs.io"
TTS_MAX_CHARS = 600
STT_MAX_BYTES = 2 * MB
STT_MAX_SECONDS = 60
STT_MODEL = "scribe_v1"
PER_MINUTE = 20
TIMEOUT = httpx.Timeout(30.0, connect=5.0)
# Body caps for UploadSizeGuard: a short JSON body, and one clip plus its form framing.
TTS_MAX_BODY = 4096
STT_MAX_BODY = STT_MAX_BYTES + 64 * 1024

NOT_CONFIGURED = {"reason": "voice not configured"}


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=TTS_MAX_CHARS)


class Heard(BaseModel):
    text: str


def _refuse(status: int, reason: str) -> JSONResponse:
    return JSONResponse({"reason": reason}, status_code=status)


def make_router(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> APIRouter:
    """`transport` replaces the network in tests (httpx.MockTransport)."""
    router = APIRouter()
    per_minute = PerMinuteLimit(PER_MINUTE)
    per_day = DailyLimit(settings.snapback_voice_daily_limit)

    def key() -> str | None:
        secret = settings.elevenlabs_api_key
        value = secret.get_secret_value().strip() if secret else ""
        return value or None

    def allowed(request: Request, direction: str) -> JSONResponse | None:
        address = request.client.host if request.client else "unknown"
        if not per_minute.allow(f"{direction}:{address}"):
            return _refuse(429, "Too many voice requests. Wait a minute.")
        if not per_day.reserve(f"{direction}:{address}"):
            return _refuse(429, "Daily voice limit reached. You can still type.")
        return None

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=ELEVENLABS, timeout=TIMEOUT, transport=transport)

    @router.get("/voice/status")
    def status() -> dict[str, bool]:
        on = key() is not None
        return {"tts": on, "stt": on}

    @router.post("/voice/tts", response_model=None)
    async def tts(body: SpeakRequest, request: Request) -> Response:
        """The Finder's reply as speech, in a warm natural voice."""
        secret = key()
        if secret is None:
            return JSONResponse(NOT_CONFIGURED, status_code=503)
        refused = allowed(request, "tts")
        if refused is not None:
            return refused
        text = body.text.strip()
        if not text:
            return _refuse(422, "Nothing to say.")
        try:
            async with client() as http:
                res = await http.post(
                    f"/v1/text-to-speech/{settings.elevenlabs_voice_id}",
                    params={"output_format": "mp3_44100_128"},
                    headers={"xi-api-key": secret, "accept": "audio/mpeg"},
                    json={
                        "text": text,
                        "model_id": settings.elevenlabs_tts_model,
                        "voice_settings": {
                            "stability": 0.45,
                            "similarity_boost": 0.8,
                            "style": 0.2,
                            "use_speaker_boost": True,
                        },
                    },
                )
        except httpx.HTTPError:
            return _refuse(502, "The voice service did not answer.")
        if res.status_code == 429:
            return _refuse(429, "The voice service is busy. Try again soon.")
        if res.status_code != 200:
            return _refuse(502, "The voice service could not speak that.")
        return Response(
            content=res.content, media_type="audio/mpeg", headers={"Cache-Control": "no-store"}
        )

    @router.post("/voice/stt", response_model=None)
    async def stt(
        request: Request,
        audio: UploadFile,
        seconds: Annotated[float | None, Form()] = None,
    ) -> Heard | JSONResponse:
        """What the renter said, as text, cleaned like typed words before anyone reads it."""
        secret = key()
        if secret is None:
            return JSONResponse(NOT_CONFIGURED, status_code=503)
        if seconds is not None and seconds > STT_MAX_SECONDS:
            return _refuse(413, f"Keep it under {STT_MAX_SECONDS} seconds.")
        kind = (audio.content_type or "").split(";")[0].strip().lower()
        if not (kind.startswith("audio/") or kind == "video/webm"):
            return _refuse(415, "Only audio can be sent.")
        data = await audio.read(STT_MAX_BYTES + 1)
        if len(data) > STT_MAX_BYTES:
            return _refuse(413, "That recording is too long.")
        if not data:
            return _refuse(422, "The recording was empty.")
        refused = allowed(request, "stt")
        if refused is not None:
            return refused
        try:
            async with client() as http:
                res = await http.post(
                    "/v1/speech-to-text",
                    headers={"xi-api-key": secret},
                    data={
                        "model_id": STT_MODEL,
                        "language_code": "en",
                        "tag_audio_events": "false",
                    },
                    files={"file": (audio.filename or "clip.webm", data, kind)},
                )
        except httpx.HTTPError:
            return _refuse(502, "The voice service did not answer.")
        if res.status_code == 429:
            return _refuse(429, "The voice service is busy. Try again soon.")
        if res.status_code != 200:
            return _refuse(502, "The voice service could not hear that.")
        try:
            heard = str(res.json().get("text") or "")
        except ValueError:
            return _refuse(502, "The voice service sent something unreadable.")
        return Heard(text=clean_words(heard))

    return router
