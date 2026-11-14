"""FastAPI entry point. Run with `make api`.

Routes the web app and the iMessage sidecar call:

    POST /cases                           start a check (form: link, text, renter_id,
                                          property_id, photos)
    GET  /cases/{case_id}                 where the case stands
    GET  /cases/{case_id}/card            the Card (?lang=en|es)
    GET  /cases/{case_id}/card.png        the same card as a picture, for iMessage (?lang=en|es)
    GET  /cases/{case_id}/trace           the agent trace as server-sent events
    POST /cases/{case_id}/challenge/approve   the renter's answer: send, edit or cancel
    GET  /eval/results.csv                the eval harness's results, for the Lab panel
    GET  /healthz                         liveness and the data source
    POST /verdict                         decide() on evidence the caller already has

A case's short id is accepted with or without the fixture prefix and in either case: `7Q2M`,
`7q2m` and `fx-7Q2M` are the same case. Short ids can be guessed, so the id alone opens only
the card and a summary. `POST /cases` returns two secrets for the case. `token` is needed for
every write and is accepted in a header only. `read_token` opens the trace and the drafted
challenge and is the only one accepted as `?token=`, because servers log addresses.
"""

import asyncio
import re
import secrets
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.datastructures import UploadFile

from snapback.adapters.vexcel import aerial_proof, aerial_side
from snapback.agent.intake import read_listing
from snapback.agent.join import KitLookups, KitMissing, Lookups
from snapback.api.card_cache import CardPictures
from snapback.api.cases import (
    CaseStatus,
    CaseStore,
    NothingWaiting,
    RecordedCase,
    SessionCase,
    UnknownProperty,
)
from snapback.api.eval_results import NotTheAgreedCsv, read_results
from snapback.api.limits import DailyLimit
from snapback.api.registry import CaseRegistry, SafetyRegistry
from snapback.api.uploads import FORM_OVERHEAD, MB, UploadSizeGuard, parse_form, read_images
from snapback.contracts import (
    AerialProofResponse,
    AerialSideOut,
    Card,
    CreateCaseResponse,
    DataSource,
    Evidence,
    LocateStatus,
    Verdict,
)
from snapback.safety.paths import resolve_data_dir
from snapback.settings import Settings, get_settings
from snapback.verdict import decide

POLL_SECONDS = 0.1
KEEP_ALIVE_SECONDS = 15.0
CLIENT_COOKIE = "snapback_client"
# Our ids for records: short, and nothing that could be a path or a sentence.
PROPERTY_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")
# What the sidecar sends: "imsg-" and a keyed hash of the thread (apps/sidecar renterId).
# Nothing else is accepted, so a raw phone number or a name can never be stored as one.
RENTER_ID = re.compile(r"imsg-[0-9a-f]{24}")
# What a browser is known by: the client cookie this API issued.
COOKIE_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")
# Everything a case may be registered under.
OWNER = re.compile(r"imsg-[0-9a-f]{24}|browser:[A-Za-z0-9_-]{8,64}")
_DEFAULT = object()


class NotRegistered(Exception):
    """The case could not be recorded with its renter, so it must not be started."""


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


NO_TILE = "No aerial tile for this building."
AerialDirection = Literal["north", "east", "south", "west", "nadir"]


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


def create_app(
    settings: Settings | None = None,
    lookups: Lookups | None = None,
    *,
    registry: CaseRegistry | None | object = _DEFAULT,
) -> FastAPI:
    """The API. `lookups` replaces lane D's adapters, for tests. `registry` records who
    started each case; the default is lane D's safety store."""
    settings = settings or get_settings()
    # One set of lane D lookups for the case store and the aerial route: the kit is parsed once.
    lookups = lookups or KitLookups(settings.snapback_data_source)
    store = CaseStore(settings, lookups)
    if registry is _DEFAULT:
        registry = SafetyRegistry(settings.snapback_data_dir)
    # One allowance per renter or per browser, and a ceiling per network address so that
    # clearing cookies is not a way around it.
    per_client = DailyLimit(settings.snapback_daily_limit)
    per_address = DailyLimit(settings.snapback_daily_limit_per_address)
    max_photo_bytes = settings.snapback_max_photo_mb * MB
    limit_reached = f"Limit reached: {per_client.per_day} checks per day. Try again tomorrow."

    pictures = CardPictures()

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
        # A case the renter deleted (lane D's delete, run from anywhere) is no longer
        # registered. Forget it here too, so it is not served from memory until a restart.
        owner = getattr(case, "owner", None)
        deleted = (
            registry is not None
            and owner is not None
            and case.session.case_id not in registry.cases_of(owner)
        )
        if deleted:
            store.discard(case_id)
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

    def same(offered: str, secret: str | None) -> bool:
        return secret is not None and secrets.compare_digest(offered.encode(), secret.encode())

    def check_write(case: RecordedCase | SessionCase, in_header: str | None) -> None:
        """Refuse unless the write secret came in a header. A recorded case has none to check."""
        if case.token is None:
            return
        if in_header is None:
            raise HTTPException(
                status_code=401, detail="This needs the case's token in the Authorization header."
            )
        if not same(in_header, case.token):
            raise HTTPException(status_code=403, detail="That token cannot write to this case.")

    def check_read(
        case: RecordedCase | SessionCase, in_header: str | None, in_query: str | None
    ) -> None:
        """Refuse unless the request may read this case's trace and challenge.

        A header may carry either secret, since whoever may write may read. The address may
        carry only the read-only one: servers log addresses, so the write secret is refused
        there.
        """
        if case.token is None:
            return
        if in_header is not None:
            if same(in_header, case.token) or same(in_header, case.read_token):
                return
            raise HTTPException(status_code=403, detail="That token is not for this case.")
        if in_query is not None:
            if same(in_query, case.read_token):
                return
            raise HTTPException(
                status_code=403,
                detail="Only this case's read token is accepted in the address.",
            )
        raise HTTPException(status_code=401, detail="This needs the case's read token.")

    def start_case(
        text: str, link: str, photos: list[UploadFile], property_id: str | None, owner: str
    ) -> SessionCase:
        if property_id is not None and not PROPERTY_ID.fullmatch(property_id):
            raise HTTPException(status_code=422, detail="That is not one of our building ids.")

        def register(case_id: str) -> None:
            # So lane D's delete finds every case this renter started (A11).
            if registry is None:
                return
            try:
                registry.register_case(case_id, owner)
            except Exception:
                raise NotRegistered from None

        images = read_images(photos, settings.snapback_max_photos, max_photo_bytes)
        listing_text = "\n".join(part for part in (text.strip(), link.strip()) if part)
        # An image that is mostly text is a screenshot of the listing and is read locally as
        # part of it; the rest are counted as photos.
        try:
            case = store.create(read_listing(listing_text, images), property_id, register)
            case.owner = owner if registry is not None else None
            return case
        except NotRegistered:
            raise HTTPException(
                status_code=503,
                detail="The check could not be recorded, so it was not started. Try again.",
            ) from None
        except UnknownProperty:
            raise HTTPException(
                status_code=422, detail="We hold no record for that building id."
            ) from None
        except KitMissing as missing:
            raise HTTPException(status_code=503, detail=str(missing)) from None

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
                                "property_id": {"type": "string"},
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

        The form is `CreateCaseRequest` in contracts.py plus `photos` as files, which may be
        listing photos or screenshots of the listing. The link is read as part of the
        listing's text and is never fetched. `property_id` is our id for the building the
        listing claims; with it the check runs on that building's record (422 if we hold
        none, 503 if the kit is not on this server).
        """
        form = await parse_form(request, settings.snapback_max_photos, max_photo_bytes)
        try:
            text, link, renter_id = (
                str(form.get(name) or "") for name in ("text", "link", "renter_id")
            )
            property_id = str(form.get("property_id") or "").strip() or None
            photos = [item for item in form.getlist("photos") if isinstance(item, UploadFile)]
            if renter_id and not RENTER_ID.fullmatch(renter_id):
                raise HTTPException(status_code=422, detail="That is not a renter id.")

            # Who is asking. The sidecar names its renter; a browser is known by a cookie.
            address = request.client.host if request.client else "unknown"
            cookie = request.cookies.get(CLIENT_COOKIE)
            if cookie is not None and not COOKIE_ID.fullmatch(cookie):
                cookie = None  # not one we issued; a fresh one is set below
            new_cookie = None if renter_id or cookie else secrets.token_urlsafe(16)
            client = f"renter:{renter_id}" if renter_id else f"browser:{cookie or new_cookie}"
            # Who the case is registered under, for delete: the sidecar's own renter id as
            # it sent it, or the browser's client cookie.
            owner = renter_id or client
            if not OWNER.fullmatch(owner):  # cannot happen with the checks above
                raise HTTPException(status_code=422, detail="That is not a renter id.")

            # A place is taken before the check starts, in one step, so two requests arriving
            # together cannot both take the last one. It is given back if nothing starts.
            if not per_client.reserve(client):
                raise HTTPException(status_code=429, detail=limit_reached)
            if not per_address.reserve(address):
                per_client.release(client)
                raise HTTPException(status_code=429, detail=limit_reached)
            try:
                case = await run_in_threadpool(start_case, text, link, photos, property_id, owner)
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
        return CreateCaseResponse(
            token=case.token,
            read_token=case.read_token,
            **status.model_dump(exclude={"challenge"}),
        )

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
        in_header = _bearer(authorization, x_case_token)
        if in_header is None and token is None:
            return case.status(with_challenge=False)
        check_read(case, in_header, token)
        return case.status(with_challenge=True)

    @app.get("/cases/{case_id}/card")
    def get_card(case_id: str, lang: Language = "en") -> Card:
        """The card for what is known so far. Its state is decide() on the evidence gathered."""
        return find(case_id).card(settings.snapback_public_base_url, lang)

    @app.get("/cases/{case_id}/card.png")
    def get_card_png(
        case_id: str,
        lang: Language = "en",
        if_none_match: Annotated[str | None, Header()] = None,
    ) -> Response:
        """The same card drawn as a PNG, with the verify link as a QR code.

        Each distinct card is drawn once and kept. The reply carries an `ETag`; send it back
        as `If-None-Match` and an unchanged picture comes back as 304 with no body.
        """
        card = find(case_id).card(settings.snapback_public_base_url, lang)
        tag = f'"{pictures.etag(card)}"'
        headers = {"ETag": tag, "Cache-Control": "no-cache"}
        if if_none_match is not None and tag in if_none_match:
            return Response(status_code=304, headers=headers)
        return Response(content=pictures.png(card), media_type="image/png", headers=headers)

    # --- D9 aerial proof (lane D builder in adapters/vexcel.py; contract approved on #41) ---

    def kit_records_for_aerial() -> dict | None:
        """The shared lookups' parsed kit, when they offer one (a test stand-in may not)."""
        records = getattr(lookups, "records", None)
        return records() if callable(records) else None

    def matched_id_of(case: RecordedCase | SessionCase) -> str | None:
        """The building a photo was located in when it was not the claimed one (V2)."""
        locate = case.evidence.locate
        for photo in locate.photos if locate is not None else []:
            if photo.status == LocateStatus.LOCATED_ELSEWHERE:
                found = getattr(photo, "matched_property_id", None)
                if found:
                    return found
        return None

    def aerial_for(case: RecordedCase | SessionCase, case_id: str, direction: str):
        """The two buildings for this case. The claimed one is the case's property id (A10); the
        matched one is a photo located in another building (V2). Either may be missing."""
        return aerial_proof(
            case_id,
            case.evidence.source,
            case.property_id,
            matched_id_of(case),
            direction=direction,
            records=kit_records_for_aerial(),
            data_dir=settings.snapback_data_dir,
            image_url=lambda side: f"/cases/{case_id}/aerial/{side}.jpg?direction={direction}",
        )

    @app.get("/cases/{case_id}/aerial")
    def get_aerial(
        case_id: str,
        direction: AerialDirection = "north",
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> AerialProofResponse:
        """The claimed building and the one the photos matched, from the air, with the distance.

        Cases are private: this needs the case's read token in a header. Each tile is bounded at
        20 s and cached for 7 days under data/vexcel/ (`make purge` deletes it)."""
        case = find(case_id)
        # check_read answers 401 for a case that has a secret and got none; the recorded fixture
        # case has no secret, so it is readable without one, as for the trace.
        check_read(case, _bearer(authorization, x_case_token), None)
        proof = aerial_for(case, case_id, direction)

        # The image is served by our own route; the client never sees where it sits on disk.
        # A trimmed copy, so the builder's own object is never changed.
        def trimmed(side: AerialSideOut | None) -> AerialSideOut | None:
            if side is None or side.tile is None:
                return side
            name = Path(side.tile.path).name
            return side.model_copy(update={"tile": side.tile.model_copy(update={"path": name})})

        return proof.model_copy(
            update={"claimed": trimmed(proof.claimed), "matched": trimmed(proof.matched)}
        )

    @app.get("/cases/{case_id}/aerial/{side}.jpg")
    def get_aerial_image(
        case_id: str,
        side: Literal["claimed", "matched"],
        direction: AerialDirection = "north",
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> Response:
        """One live tile's bytes. The token goes in a header only (ruling on #113): lane T fetches
        the image with the header and shows it through a blob URL. Only the side asked for is
        fetched."""
        case = find(case_id)
        check_read(case, _bearer(authorization, x_case_token), None)
        property_id = case.property_id if side == "claimed" else matched_id_of(case)
        if property_id is None:
            raise HTTPException(status_code=404, detail=NO_TILE)
        tile = aerial_side(
            case.evidence.source,
            property_id,
            direction=direction,
            records=kit_records_for_aerial(),
            data_dir=settings.snapback_data_dir,
        )
        if tile is None or tile.source != DataSource.LIVE:
            raise HTTPException(status_code=404, detail=NO_TILE)
        tile_path = Path(tile.path).resolve()
        data_root = resolve_data_dir(settings.snapback_data_dir).resolve()
        if not tile_path.is_relative_to(data_root):
            raise HTTPException(status_code=404, detail=NO_TILE)
        try:
            content = tile_path.read_bytes()
        except FileNotFoundError:  # purged between the JSON call and this one
            raise HTTPException(status_code=404, detail=NO_TILE) from None
        return Response(
            content=content,
            media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=600"},
        )

    @app.get("/cases/{case_id}/trace")
    def get_trace(
        case_id: str,
        token: str | None = None,
        last_event_id: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        """Server-sent events: `event: trace`, `id` is the seq, `data` is a TraceEvent.

        Needs a case secret, because the trace names the spot that was drawn. A browser's
        EventSource cannot set headers, so the read-only `read_token` may be sent as
        `?token=`; the write token is refused there. Other clients can send either secret as
        `Authorization: Bearer` or `X-Case-Token`. Send `Last-Event-ID` to resume after that
        seq. The stream ends after the verdict event.
        """
        case = find(case_id)
        check_read(case, _bearer(authorization, x_case_token), token)
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
        check_write(case, _bearer(authorization, x_case_token))
        try:
            case.approve(approval.decision, approval.text)
        except NothingWaiting:
            raise HTTPException(
                status_code=409, detail="This case is not waiting for an approval."
            ) from None
        return case.status(with_challenge=True)

    @app.get("/eval/results.csv")
    def get_eval_results() -> Response:
        """The eval harness's results as CSV, for the Lab panel. Public and read-only (#69).

        The file holds aggregate numbers only (how often each condition caught what it should,
        with n), and no case data, so it needs no token. The path comes from settings, never
        from the request, and only the agreed CSV is ever served.
        """
        try:
            results = read_results(settings.snapback_eval_results)
        except NotTheAgreedCsv:
            raise HTTPException(
                status_code=500, detail="The results file is not the agreed eval results CSV."
            ) from None
        if results is None:
            raise HTTPException(status_code=404, detail="No eval results yet. Run `make eval`.")
        return Response(
            content=results, media_type="text/csv", headers={"Cache-Control": "no-store"}
        )

    return app


app = create_app()
