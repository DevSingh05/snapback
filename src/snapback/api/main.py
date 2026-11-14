"""FastAPI entry point. Run with `make api`.

Routes the web app and the iMessage sidecar call:

    POST /cases                           start a check (form: listing_text, renter_id, photos)
    GET  /cases/{case_id}                 where the case stands
    GET  /cases/{case_id}/card            the Card
    GET  /cases/{case_id}/trace           the agent trace as server-sent events
    POST /cases/{case_id}/challenge/approve   the renter's answer: send, edit or cancel
    GET  /healthz                         liveness and the data source
    POST /verdict                         decide() on evidence the caller already has

A case id is accepted with or without the fixture prefix and in either case: `7Q2M`, `7q2m`
and `fx-7Q2M` are the same case.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from snapback.api.cases import (
    CaseStatus,
    CaseStore,
    LiveModeNotWired,
    NothingWaiting,
    RecordedCase,
    SessionCase,
)
from snapback.api.limits import DailyLimit
from snapback.contracts import Card, Evidence, Verdict
from snapback.settings import Settings, get_settings
from snapback.verdict import decide

MAX_PHOTOS = 20
POLL_SECONDS = 0.1
KEEP_ALIVE_SECONDS = 15.0


class Approval(BaseModel):
    decision: Literal["send", "edit", "cancel"]
    text: str | None = None  # the renter's wording, with "edit"


def _after(last_event_id: str | None) -> int:
    """The last sequence number the client already has, or -1 for "from the start"."""
    try:
        return int(last_event_id) if last_event_id is not None else -1
    except ValueError:
        return -1


async def _trace_stream(
    case: RecordedCase | SessionCase, after: int, pace: float
) -> AsyncIterator[str]:
    """Each trace event once, in order, then more as they happen, until the case is done."""
    sent = after
    quiet = 0.0
    while True:
        fresh = [event for event in case.events() if event.seq > sent]
        for event in fresh:
            yield f"id: {event.seq}\nevent: trace\ndata: {event.model_dump_json()}\n\n"
            sent = event.seq
            quiet = 0.0
            if pace:
                await asyncio.sleep(pace)
        if case.done and not any(event.seq > sent for event in case.events()):
            return
        if not fresh:
            await asyncio.sleep(POLL_SECONDS)
            quiet += POLL_SECONDS
            if quiet >= KEEP_ALIVE_SECONDS:
                yield ": keep-alive\n\n"
                quiet = 0.0


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = CaseStore(settings)
    limit = DailyLimit(settings.snapback_daily_limit)
    app = FastAPI(title="SNAPBACK API", version="0.0.1")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(
            {"http://localhost:5173", "http://127.0.0.1:5173", settings.snapback_public_base_url}
        ),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def find(case_id: str) -> RecordedCase | SessionCase:
        case = store.get(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="No case with that id.")
        return case

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness plus the active data source, so every client can show LIVE or FIXTURE."""
        return {"status": "ok", "data_source": settings.snapback_data_source.value}

    @app.post("/verdict")
    def verdict(evidence: Evidence) -> Verdict:
        """Decide a verdict from evidence the caller already gathered. No model is involved."""
        return decide(evidence)

    @app.post("/cases", status_code=201)
    def create_case(
        listing_text: Annotated[str, Form()] = "",
        renter_id: Annotated[str, Form()] = "anonymous",
        photos: Annotated[list[UploadFile] | None, File()] = None,
    ) -> CaseStatus:
        """Start a check. Runs until it needs the renter's approval, then returns."""
        photos = photos or []
        if len(photos) > MAX_PHOTOS:
            raise HTTPException(status_code=413, detail=f"At most {MAX_PHOTOS} photos per check.")
        if not limit.allow(renter_id):
            raise HTTPException(
                status_code=429,
                detail=f"Limit reached: {limit.per_day} checks per renter per day.",
            )
        try:
            return store.create(listing_text, len(photos)).status()
        except LiveModeNotWired:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Live mode needs the locate, record and challenge modules, which are "
                    "not wired yet. Run with SNAPBACK_DATA_SOURCE=fixture."
                ),
            ) from None

    @app.get("/cases/{case_id}")
    def get_case(case_id: str) -> CaseStatus:
        return find(case_id).status()

    @app.get("/cases/{case_id}/card")
    def get_card(case_id: str) -> Card:
        """The card for what is known so far. Its state is decide() on the evidence gathered."""
        return find(case_id).card(settings.snapback_public_base_url)

    @app.get("/cases/{case_id}/trace")
    def get_trace(
        case_id: str, last_event_id: Annotated[str | None, Header()] = None
    ) -> StreamingResponse:
        """Server-sent events: `event: trace`, `id` is the seq, `data` is a TraceEvent.

        Send `Last-Event-ID` to resume after that seq; a browser's EventSource does it by
        itself. The stream ends after the verdict event.
        """
        return StreamingResponse(
            _trace_stream(
                find(case_id), _after(last_event_id), settings.snapback_trace_pace_ms / 1000
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/cases/{case_id}/challenge/approve")
    def approve_challenge(case_id: str, approval: Approval) -> CaseStatus:
        """The renter's answer to the drafted challenge. Nothing is sent before this."""
        case = find(case_id)
        try:
            case.approve(approval.decision, approval.text)
        except NothingWaiting:
            raise HTTPException(
                status_code=409, detail="This case is not waiting for an approval."
            ) from None
        return case.status()

    return app


app = create_app()
