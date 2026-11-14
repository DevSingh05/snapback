"""FastAPI entry point. Run with `make api`.

Routes the web app and the iMessage sidecar call:

    POST /cases                           start a check (form: link, text, renter_id, photos)
    GET  /cases/{case_id}                 where the case stands
    GET  /cases/{case_id}/card            the Card
    GET  /cases/{case_id}/trace           the agent trace as server-sent events
    POST /cases/{case_id}/challenge/approve   the renter's answer: send, edit or cancel
    GET  /healthz                         liveness and the data source
    POST /verdict                         decide() on evidence the caller already has

A case's short id is accepted with or without the fixture prefix and in either case: `7Q2M`,
`7q2m` and `fx-7Q2M` are the same case. Short ids can be guessed, so the id alone opens only
the card and a summary. The trace, the drafted challenge and every write need the secret that
`POST /cases` returned for the case.
"""

import asyncio
import secrets
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.datastructures import UploadFile

from snapback.api.cases import (
    CaseStatus,
    CaseStore,
    LiveModeNotWired,
    NothingWaiting,
    RecordedCase,
    SessionCase,
)
from snapback.api.limits import DailyLimit
from snapback.api.uploads import FORM_OVERHEAD, MB, UploadSizeGuard, parse_form, read_images
from snapback.contracts import Card, CreateCaseResponse, Evidence, Verdict
from snapback.settings import Settings, get_settings
from snapback.verdict import decide

POLL_SECONDS = 0.1
KEEP_ALIVE_SECONDS = 15.0
CLIENT_COOKIE = "snapback_client"


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
    limit_reached = f"Limit reached: {per_client.per_day} checks per day. Try again tomorrow."

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

    def check_secret(case: RecordedCase | SessionCase, offered: str | None) -> None:
        """Refuse unless `offered` is this case's secret. A recorded case has none to check."""
        if case.token is None:
            return
        if offered is None:
            raise HTTPException(status_code=401, detail="This needs the case's token.")
        if not secrets.compare_digest(offered.encode(), case.token.encode()):
            raise HTTPException(status_code=403, detail="That token is not for this case.")

    def start_case(text: str, link: str, photos: list[UploadFile]) -> SessionCase:
        images = read_images(photos, settings.snapback_max_photos, max_photo_bytes)
        listing_text = "\n".join(part for part in (text.strip(), link.strip()) if part)
        return store.create(listing_text, len(images))

    @app.post(
        "/cases",
        status_code=201,
        openapi_extra={
            "requestBody": {
                "content": {
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "link": {"type": "string"},
                                "text": {"type": "string"},
                                "renter_id": {"type": "string"},
                                "photos": {
                                    "type": "array",
                                    "items": {"type": "string", "format": "binary"},
                                },
                            },
                        }
                    }
                }
            }
        },
    )
    async def create_case(request: Request, response: Response) -> CreateCaseResponse:
        """Start a check. Runs until it needs the renter's approval, then returns.

        The form is `CreateCaseRequest` in contracts.py plus `photos` as files. The link is
        read as part of the listing's text and is never fetched.
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

        form = await parse_form(request, settings.snapback_max_photos, max_photo_bytes)
        try:
            text, link, renter_id = (
                str(form.get(name) or "") for name in ("text", "link", "renter_id")
            )
            photos = [item for item in form.getlist("photos") if isinstance(item, UploadFile)]

            # Who is asking. The sidecar names its renter; a browser is known by a cookie.
            address = request.client.host if request.client else "unknown"
            cookie = request.cookies.get(CLIENT_COOKIE)
            new_cookie = None if renter_id or cookie else secrets.token_urlsafe(16)
            client = f"renter:{renter_id}" if renter_id else f"browser:{cookie or new_cookie}"

            # A place is taken before the check starts, in one step, so two requests arriving
            # together cannot both take the last one. It is given back if nothing starts.
            if not per_client.reserve(client):
                raise HTTPException(status_code=429, detail=limit_reached)
            if not per_address.reserve(address):
                per_client.release(client)
                raise HTTPException(status_code=429, detail=limit_reached)
            try:
                case = await run_in_threadpool(start_case, text, link, photos)
            except BaseException:
                per_client.release(client)
                per_address.release(address)
                raise
        finally:
            await form.close()

        if new_cookie:
            response.set_cookie(
                CLIENT_COOKIE, new_cookie, max_age=30 * 24 * 3600, httponly=True, samesite="lax"
            )
        status = case.status(with_challenge=True)
        return CreateCaseResponse(token=case.token, **status.model_dump(exclude={"challenge"}))

    @app.get("/cases/{case_id}")
    def get_case(
        case_id: str,
        token: str | None = None,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> CaseStatus:
        """Where the case stands. The drafted challenge is included only with the case's secret.

        Short ids can be guessed, so the id alone gives a summary and nothing that would help
        someone answer the challenge.
        """
        case = find(case_id)
        offered = _bearer(authorization, x_case_token) or token
        if offered is None:
            return case.status(with_challenge=False)
        check_secret(case, offered)
        return case.status(with_challenge=True)

    @app.get("/cases/{case_id}/card")
    def get_card(case_id: str) -> Card:
        """The card for what is known so far. Its state is decide() on the evidence gathered."""
        return find(case_id).card(settings.snapback_public_base_url)

    @app.get("/cases/{case_id}/trace")
    def get_trace(
        case_id: str,
        token: str | None = None,
        last_event_id: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        """Server-sent events: `event: trace`, `id` is the seq, `data` is a TraceEvent.

        Needs the case's secret, because the trace names the spot that was drawn. A browser's
        EventSource cannot set headers, so it may be sent as `?token=`; other clients can use
        `Authorization: Bearer` or `X-Case-Token`. Send `Last-Event-ID` to resume after that
        seq. The stream ends after the verdict event.
        """
        case = find(case_id)
        check_secret(case, _bearer(authorization, x_case_token) or token)
        return StreamingResponse(
            _trace_stream(case, _after(last_event_id), settings.snapback_trace_pace_ms / 1000),
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
        check_secret(case, _bearer(authorization, x_case_token))
        try:
            case.approve(approval.decision, approval.text)
        except NothingWaiting:
            raise HTTPException(
                status_code=409, detail="This case is not waiting for an approval."
            ) from None
        return case.status(with_challenge=True)

    return app


app = create_app()
