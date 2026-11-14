"""FastAPI entry point. Run with `make api`.

Routes the web app and the iMessage sidecar call:

    POST /cases                           start a check (form: link, text, renter_id, photos)
    GET  /cases/{case_id}                 where the case stands
    GET  /cases/{case_id}/card            the Card (?lang=en|es)
    GET  /cases/{case_id}/card.png        the same card as a picture, for iMessage (?lang=en|es)
    GET  /cases/{case_id}/trace           the agent trace as server-sent events
    POST /cases/{case_id}/challenge/approve   the renter's answer: send, edit or cancel
    GET  /healthz                         liveness and the data source
    POST /verdict                         decide() on evidence the caller already has

Reading a case needs only its short id, which is accepted with or without the fixture prefix
and in either case: `7Q2M`, `7q2m` and `fx-7Q2M` are the same case. Writing to a case needs the
secret that `POST /cases` returned for it.
"""

import asyncio
import secrets
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from snapback.agent.intake import read_listing
from snapback.api.cases import (
    CaseStatus,
    CaseStore,
    LiveModeNotWired,
    NothingWaiting,
    RecordedCase,
    SessionCase,
)
from snapback.api.limits import DailyLimit
from snapback.api.uploads import FORM_OVERHEAD, MB, UploadSizeGuard, read_images
from snapback.card.render import render_card_png
from snapback.contracts import Card, CreateCaseResponse, Evidence, Verdict
from snapback.settings import Settings, get_settings
from snapback.verdict import decide

POLL_SECONDS = 0.1
KEEP_ALIVE_SECONDS = 15.0
CLIENT_COOKIE = "snapback_client"


Language = Literal["en", "es"]


class Approval(BaseModel):
    decision: Literal["send", "edit", "cancel"]
    text: str | None = None  # the renter's wording, with "edit"


def _after(last_event_id: str | None) -> int:
    """The last sequence number the client already has, or -1 for "from the start"."""
    try:
        return int(last_event_id) if last_event_id is not None else -1
    except ValueError:
        return -1


def _bearer(authorization: str | None, case_token: str | None) -> str | None:
    """The case secret a request carries, from `Authorization: Bearer` or `X-Case-Token`."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return case_token


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
    # One allowance per renter or per browser, and a ceiling per network address so that
    # clearing cookies is not a way around it.
    per_client = DailyLimit(settings.snapback_daily_limit)
    per_address = DailyLimit(settings.snapback_daily_limit_per_address)
    max_photo_bytes = settings.snapback_max_photo_mb * MB

    app = FastAPI(title="SNAPBACK API", version="0.0.1")
    app.state.store = store

    app.add_middleware(
        UploadSizeGuard,
        max_body_bytes=settings.snapback_max_photos * max_photo_bytes + FORM_OVERHEAD,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(
            {"http://localhost:5173", "http://127.0.0.1:5173", settings.snapback_public_base_url}
        ),
        allow_credentials=True,  # so a browser can keep the client cookie across origins
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
        request: Request,
        response: Response,
        link: Annotated[str, Form()] = "",
        text: Annotated[str, Form()] = "",
        renter_id: Annotated[str, Form()] = "",
        photos: Annotated[list[UploadFile] | None, File()] = None,
    ) -> CreateCaseResponse:
        """Start a check. Runs until it needs the renter's approval, then returns.

        The form is `CreateCaseRequest` in contracts.py plus `photos` as files, which may be
        listing photos or screenshots of the listing. The link is read as part of the
        listing's text and is never fetched.
        """
        try:
            store.check_can_create()
        except LiveModeNotWired:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Live mode needs the locate, record and challenge modules, which are "
                    "not wired yet. Run with SNAPBACK_DATA_SOURCE=fixture."
                ),
            ) from None

        # Who is asking. The sidecar names its renter; a browser is known by a cookie we set.
        address = request.client.host if request.client else "unknown"
        cookie = request.cookies.get(CLIENT_COOKIE)
        new_cookie = None if renter_id or cookie else secrets.token_urlsafe(16)
        client = f"renter:{renter_id}" if renter_id else f"browser:{cookie or new_cookie}"
        if not per_client.has_room(client) or not per_address.has_room(address):
            raise HTTPException(
                status_code=429,
                detail=f"Limit reached: {per_client.per_day} checks per day. Try again tomorrow.",
            )

        images = read_images(photos or [], settings.snapback_max_photos, max_photo_bytes)
        listing_text = "\n".join(part for part in (text.strip(), link.strip()) if part)
        # An image that is mostly text is a screenshot of the listing and is read locally as
        # part of it; the rest are counted as photos.
        case = store.create(read_listing(listing_text, images))

        # Counted only now, so a check that could not start costs nothing.
        per_client.count(client)
        per_address.count(address)
        if new_cookie:
            response.set_cookie(
                CLIENT_COOKIE, new_cookie, max_age=30 * 24 * 3600, httponly=True, samesite="lax"
            )
        status = case.status()
        return CreateCaseResponse(token=case.token, **status.model_dump(exclude={"challenge"}))

    @app.get("/cases/{case_id}")
    def get_case(case_id: str) -> CaseStatus:
        return find(case_id).status()

    @app.get("/cases/{case_id}/card")
    def get_card(case_id: str, lang: Language = "en") -> Card:
        """The card for what is known so far. Its state is decide() on the evidence gathered."""
        return find(case_id).card(settings.snapback_public_base_url, lang)

    @app.get("/cases/{case_id}/card.png")
    def get_card_png(case_id: str, lang: Language = "en") -> Response:
        """The same card drawn as a PNG, with the verify link as a QR code."""
        card = find(case_id).card(settings.snapback_public_base_url, lang)
        return Response(content=render_card_png(card), media_type="image/png")

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
    def approve_challenge(
        case_id: str,
        approval: Approval,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> CaseStatus:
        """The renter's answer to the drafted challenge. Nothing is sent before this.

        Needs the case's secret, as `Authorization: Bearer <token>` or `X-Case-Token`. The
        short id is for reading and display; on its own it lets nobody act for the renter.
        """
        case = find(case_id)
        if case.token is not None:
            offered = _bearer(authorization, x_case_token)
            if offered is None:
                raise HTTPException(status_code=401, detail="This needs the case's token.")
            if not secrets.compare_digest(offered.encode(), case.token.encode()):
                raise HTTPException(status_code=403, detail="That token is not for this case.")
        try:
            case.approve(approval.decision, approval.text)
        except NothingWaiting:
            raise HTTPException(
                status_code=409, detail="This case is not waiting for an approval."
            ) from None
        return case.status()

    return app


app = create_app()
