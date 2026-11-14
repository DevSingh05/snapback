"""FastAPI entry point. Run with `make api`.

Routes the web app and the iMessage sidecar call:

    POST /cases                           start a check (form: link, text, renter_id,
                                          property_id, photos)
    GET  /cases/{case_id}                 where the case stands
    GET  /cases/{case_id}/card            the Card (?lang=en|es)
    GET  /cases/{case_id}/card.png        the same card as a picture, for iMessage (?lang=en|es)
    GET  /cases/{case_id}/trace           the agent trace as server-sent events
    GET  /cases/{case_id}/notes           the agent's working notes (read-only)
    POST /cases/{case_id}/challenge/approve   the renter's answer: send, edit or cancel
    POST /cases/{case_id}/reply           the poster's reply photo, checked (form: photo)
    GET  /eval/results.csv                the eval harness's results, for the Lab panel
    GET  /eval/locate_real.csv            locate accuracy on the buildings' own photos
    GET  /healthz                         liveness and the data source
    POST /verdict                         decide() on evidence the caller already has

A case's short id is accepted with or without the fixture prefix and in either case: `7Q2M`,
`7q2m` and `fx-7Q2M` are the same case. Short ids can be guessed, so the id alone opens only
the card and a summary. `POST /cases` returns two secrets for the case. `token` is needed for
every write. `read_token` opens the trace, the drafted challenge, the report and the aerial
proof. Both travel in a header only (`Authorization: Bearer` or `X-Case-Token`). No route
takes either in the address: servers log addresses, so a `token` there is answered 401,
valid or not.
"""

import asyncio
import json
import re
import secrets
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile

from snapback.adapters.vexcel import aerial_proof, aerial_side, known_capture_date
from snapback.agent.casework import CaseNotes
from snapback.agent.intake import OcrUnavailable, read_listing
from snapback.agent.join import KitLookups, KitMissing, Lookups
from snapback.agent.reply import UnreadablePhoto
from snapback.agent.search_agent import agentic_alternatives, agentic_search, search_chooser_for
from snapback.api.card_cache import CardPictures
from snapback.api.casefiles import ALIAS, CaseFiles
from snapback.api.cases import (
    CaseStatus,
    CaseStore,
    NothingWaiting,
    RecordedCase,
    SessionCase,
    UnknownProperty,
)
from snapback.api.eval_results import NotTheAgreedCsv, read_results
from snapback.api.finder import make_router as finder_router
from snapback.api.forensics import router as forensics_router
from snapback.api.limits import DailyLimit, PerMinuteLimit
from snapback.api.registry import CaseRegistry, SafetyRegistry
from snapback.api.report import build_report
from snapback.api.uploads import FORM_OVERHEAD, MB, UploadSizeGuard, parse_form, read_images
from snapback.card import strings
from snapback.contracts import (
    AerialProofResponse,
    AerialSideOut,
    AlternativesResponse,
    Card,
    CasePreferences,
    CreateCaseResponse,
    DataSource,
    Evidence,
    EvidenceFile,
    LocateStatus,
    PreferencesUpdate,
    RenterBrief,
    ReplyResponse,
    ReportResponse,
    SearchResponse,
    TourDraft,
    TourDraftRequest,
    Verdict,
)
from snapback.events import EventBus
from snapback.events.bus import seq_of
from snapback.office.context import listing_context
from snapback.office.domain import accepts_address, official_domain
from snapback.office.models import (
    ListingContext,
    OfficeAnswer,
    OfficeAnswered,
    OfficePeek,
    OfficeRequest,
    OfficeRequested,
    OfficeStatus,
    OfficeTokenBody,
)
from snapback.office.proof import TOKEN_TTL_SECONDS, OfficeProofs, Outcome, RateLimited, Redeemed
from snapback.pack import TourPrepPack, build_tour_prep
from snapback.preferences import merge as merge_preferences
from snapback.replays import SLUG as REPLAY_SLUG
from snapback.replays import Replay, load_replays
from snapback.safety.paths import resolve_data_dir
from snapback.search import (
    AmbiguousPlace,
    NoOfficeOnRecord,
    draft_tour_request,
    place_and_raw_for,
    place_for,
)
from snapback.settings import Settings, get_settings
from snapback.tour import (
    TourPlan,
    WalkResponse,
    ad_beds_of,
    ad_plan_word,
    attach_claims,
    build_tour,
    cached_sweeps,
    choose_walk,
    elsewhere_property,
    fixture_sweeps,
    map_elsewhere,
    map_locate,
    must_have_kinds_of,
    office_on_record,
    scan_model_of,
)
from snapback.verdict import decide

POLL_SECONDS = 0.1
KEEP_ALIVE_SECONDS = 15.0
CLIENT_COOKIE = "snapback_client"
# Our ids for records: short, and nothing that could be a path or a sentence.
SEARCH_MAX_BODY = 4096  # bytes: a RenterBrief is a few hundred
FORENSICS_MAX_BODY = 2048  # bytes: a question is at most 300 characters
SEARCH_PER_MINUTE = 30  # searches one address may make in a minute
PROPERTY_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")
# What the sidecar sends: "imsg-" and a keyed hash of the thread (apps/sidecar renterId).
# Nothing else is accepted, so a raw phone number or a name can never be stored as one.
RENTER_ID = re.compile(r"imsg-[0-9a-f]{24}")
# What a browser is known by: the client cookie this API issued. That is 16 random bytes in
# URL-safe base64, which is always 22 characters. Only that exact shape is accepted back, so
# a client cannot have a phone number or a name stored as its id by sending one as a cookie.
COOKIE_BYTES = 16
COOKIE_ID = re.compile(r"[A-Za-z0-9_-]{22}")
# Everything a case may be registered under.
OWNER = re.compile(r"imsg-[0-9a-f]{24}|browser:[A-Za-z0-9_-]{22}")
_DEFAULT = object()


class NotRegistered(Exception):
    """The case could not be recorded with its renter, so it must not be started."""


EVIDENCE_FIXTURE = (
    Path(__file__).resolve().parents[3] / "fixtures" / "demo" / "evidence.fixture.json"
)
Language = Literal["en", "es"]


class Approval(BaseModel):
    decision: Literal["send", "edit", "cancel"]
    text: str | None = None  # the renter's wording, with "edit"


class Answer(BaseModel):
    """The renter's answer to the license question. Blank means they have no number."""

    text: str | None = Field(default=None, max_length=500)


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


async def _event_stream(events: EventBus, after: int, follow: bool) -> AsyncIterator[str]:
    """Each event numbered above `after`, once and in order. With `follow`, more as they are
    published, with a keep-alive when it is quiet; without, the stream ends when caught up."""
    sent = after
    quiet = 0.0
    while True:
        fresh = events.after(sent)
        for event in fresh:
            yield f"id: {event.id}\nevent: event\ndata: {event.model_dump_json()}\n\n"
            sent = seq_of(event.id)
            quiet = 0.0
        if not follow:
            return
        if not fresh:
            await asyncio.sleep(POLL_SECONDS)
            quiet += POLL_SECONDS
            if quiet >= KEEP_ALIVE_SECONDS:
                yield ": keep-alive\n\n"
                quiet = 0.0


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
    office_clock: Callable[[], float] | None = None,
    search_chooser: object | None = None,
    finder_model: object | None = None,
) -> FastAPI:
    """The API. `lookups` replaces lane D's adapters, for tests. `registry` records who
    started each case; the default is lane D's safety store. `search_chooser` replaces the
    search agent's chooser (tests); by default the runner setting picks it."""
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
    search_limit = PerMinuteLimit(SEARCH_PER_MINUTE)
    chooser = search_chooser or search_chooser_for(settings.snapback_agent)

    app = FastAPI(title="SNAPBACK API", version="0.0.1")
    app.state.store = store
    # M3: one bus for the process, logged under the data folder (git-ignored, purged with it).
    events = EventBus(Path(settings.snapback_data_dir) / "events" / "log.jsonl")
    app.state.events = events
    # M9: the finder. A chat model (tests pass a scripted one) runs deepagents mode; with the
    # runner setting on and a key present it is Claude; otherwise the code policy runs.
    model = finder_model
    if model is None and settings.snapback_agent == "deepagents" and settings.anthropic_api_key:
        from snapback.agent.finder import build_model

        model = build_model(settings.anthropic_api_key.get_secret_value())
    app.include_router(finder_router(events, model))
    app.include_router(forensics_router)  # the investigator view: SYNTHETIC data only

    app.add_middleware(
        UploadSizeGuard,
        max_body_bytes=settings.snapback_max_photos * max_photo_bytes + FORM_OVERHEAD,
        small_posts={"/search": SEARCH_MAX_BODY, "/forensics/ask": FORENSICS_MAX_BODY},
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

    @app.get("/replays")
    def replays() -> list[Replay]:
        """Every replay of a reported case, read-only, from demo/replays. No case data."""
        return load_replays()

    @app.get("/replays/{slug}")
    def replay(slug: str) -> Replay:
        found = None
        if REPLAY_SLUG.match(slug):
            found = next((r for r in load_replays() if r.slug == slug), None)
        if found is None:
            raise HTTPException(status_code=404, detail="No replay with that name.")
        return found

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

    def check_read(case: RecordedCase | SessionCase, in_header: str | None) -> None:
        """Refuse unless the request may read this case's trace and challenge.

        The secret comes from a header and nowhere else (locked ruling, Sat 02:27). A header
        may carry either secret, since whoever may write may read. There is no way to hand
        this a value from the address, so no route can start reading the query again.
        """
        if case.token is None:
            return
        if in_header is not None:
            if same(in_header, case.token) or same(in_header, case.read_token):
                return
            raise HTTPException(status_code=403, detail="That token is not for this case.")
        raise HTTPException(status_code=401, detail="This needs the case's read token.")

    def no_token_in_the_address(request: Request) -> None:
        """Refuse a request whose address carries a token, valid or not (locked ruling, Sat
        02:27). Addresses are what servers and proxies log; a secret belongs in a header."""
        if "token" in request.query_params:
            raise HTTPException(
                status_code=401,
                detail=(
                    "Send the case's read token in the Authorization header, not in the address."
                ),
            )

    def start_case(
        text: str,
        link: str,
        photos: list[UploadFile],
        property_id: str | None,
        owner: str,
        demo_case: str | None = None,
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
            listing = read_listing(listing_text, images)
            listing_photos = [images[index] for index in listing.photo_indexes]
            case = store.create(
                listing, property_id, register, photos=listing_photos, demo_case=demo_case
            )
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
                                "demo_case": {"type": "string"},
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
            # "Run this case" on a replay page: only the case id of a served replay is accepted.
            demo_case = str(form.get("demo_case") or "").strip() or None
            if demo_case and demo_case not in {r.case_id for r in load_replays()}:
                raise HTTPException(status_code=422, detail="That is not a replay case.")
            photos = [item for item in form.getlist("photos") if isinstance(item, UploadFile)]
            if demo_case and (text.strip() or link.strip() or photos or property_id):
                # A replay's case runs its own staged listing and nothing the caller adds.
                raise HTTPException(
                    status_code=422, detail="A replay case takes no listing, link or photos."
                )
            if renter_id and not RENTER_ID.fullmatch(renter_id):
                raise HTTPException(status_code=422, detail="That is not a renter id.")

            # Who is asking. The sidecar names its renter; a browser is known by a cookie.
            address = request.client.host if request.client else "unknown"
            cookie = request.cookies.get(CLIENT_COOKIE)
            if cookie is not None and not COOKIE_ID.fullmatch(cookie):
                cookie = None  # not one we issued; a fresh one is set below
            new_cookie = None if renter_id or cookie else secrets.token_urlsafe(COOKIE_BYTES)
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
                case = await run_in_threadpool(
                    start_case, text, link, photos, property_id, owner, demo_case
                )
            except BaseException:
                per_client.release(client)
                per_address.release(address)
                raise
        finally:
            await form.close()

        if new_cookie:
            response.set_cookie(
                CLIENT_COOKIE,
                new_cookie,
                max_age=30 * 24 * 3600,
                httponly=True,
                samesite="lax",
                # Over https the cookie is never sent in the clear. Local development has no
                # TLS, so there it has to travel without the flag or it would not travel.
                secure=settings.snapback_public_base_url.lower().startswith("https://"),
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
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> CaseStatus:
        """Where the case stands. The drafted challenge is included only with the case's secret.

        Short ids can be guessed, so the id alone gives a summary and nothing that would help
        someone answer the challenge. The secret travels in a header only: a token in the
        address is refused with 401, even the right one.
        """
        case = find(case_id)
        no_token_in_the_address(request)
        in_header = _bearer(authorization, x_case_token)
        if in_header is None:
            return case.status(with_challenge=False)
        check_read(case, in_header)
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
        if not callable(records):
            return None
        try:
            return records()
        except KitMissing:
            return {}  # live mode without the kit: no buildings, so no tiles, never a 500

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
        request: Request,
        direction: AerialDirection = "north",
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> AerialProofResponse:
        """The claimed building and the one the photos matched, from the air, with the distance.

        Cases are private: this needs the case's read token in a header. Each tile is bounded at
        20 s and cached for 7 days under data/vexcel/ (`make purge` deletes it)."""
        case = find(case_id)
        no_token_in_the_address(request)
        # check_read answers 401 for a case that has a secret and got none; the recorded fixture
        # case has no secret, so it is readable without one, as for the trace.
        check_read(case, _bearer(authorization, x_case_token))
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
        request: Request,
        direction: AerialDirection = "north",
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> Response:
        """One live tile's bytes. The token goes in a header only (ruling on #113): lane T fetches
        the image with the header and shows it through a blob URL. Only the side asked for is
        fetched."""
        case = find(case_id)
        no_token_in_the_address(request)
        check_read(case, _bearer(authorization, x_case_token))
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

    def case_files(case, case_id: str) -> CaseFiles | None:
        """The case's evidence files. A staged demo case "a" with none of its own serves the
        team-made fixture (labelled FIXTURE inside), so the drawer works without a live run."""
        files = getattr(case, "files", None)
        if files is not None:
            return files
        if getattr(case, "demo_case_id", None) == "a" and EVIDENCE_FIXTURE.exists():
            fixture = EvidenceFile.model_validate_json(EVIDENCE_FIXTURE.read_text())
            return CaseFiles(evidence=fixture)
        return None

    NO_STORE = {"Cache-Control": "private, no-store"}

    @app.get("/cases/{case_id}/evidence")
    def get_evidence(
        case_id: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> Response:
        """The evidence file the code wrote for this case: every ad photo's measurements, the
        bars they were held to and where the bars came from. Read token in a header only."""
        case = find(case_id)
        no_token_in_the_address(request)
        check_read(case, _bearer(authorization, x_case_token))
        files = case_files(case, case_id)
        if files is None or files.evidence is None:
            raise HTTPException(status_code=404, detail="No evidence file for this case yet.")
        body = files.evidence.model_copy(update={"case_id": case_id})
        return Response(
            content=body.model_dump_json(), media_type="application/json", headers=NO_STORE
        )

    @app.get("/cases/{case_id}/files/{path:path}")
    def get_case_file(
        case_id: str,
        path: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> Response:
        """One file from the agent's file system, read only: its notes and the evidence file."""
        case = find(case_id)
        no_token_in_the_address(request)
        check_read(case, _bearer(authorization, x_case_token))
        files = case_files(case, case_id)
        found = files.read(path) if files is not None else None
        if found is None:
            raise HTTPException(status_code=404, detail="No file with that path.")
        text, by = found
        return Response(
            content=json.dumps({"path": path, "text": text, "written_by": by}),
            media_type="application/json",
            headers=NO_STORE,
        )

    @app.get("/cases/{case_id}/evidence/{alias}/{kind}.jpg")
    def get_evidence_image(
        case_id: str,
        alias: str,
        kind: Literal["photo", "scan"],
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> Response:
        """The ad's photo or the scan view it matched, for the drawer's side-by-side. Read token
        in a header only; the bytes are the session's, never a file path."""
        case = find(case_id)
        no_token_in_the_address(request)
        check_read(case, _bearer(authorization, x_case_token))
        files = case_files(case, case_id)
        data = files.image(alias, kind) if files is not None and ALIAS.fullmatch(alias) else None
        if data is None:
            raise HTTPException(status_code=404, detail="No picture for that photo.")
        return Response(
            content=data,
            media_type="image/jpeg",
            headers={**NO_STORE, "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/cases/{case_id}/report")
    def get_report(
        case_id: str,
        request: Request,
        lang: Language = "en",
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> ReportResponse:
        """The "Report this copy" pack (A20): what a listing agent takes to the platform.

        The home's own record, the reasons the check gave, which photos were matched, and
        where to click on Facebook Marketplace, Zillow and Craigslist. Listing facts only: no
        score, no hash, no image bytes, nothing about the renter, no word about a person.
        Report steps are given only on proof or a record that shows the home for sale.

        Needs the case's read token in a header. A token in the address is refused with 401
        even beside a good header: addresses are what servers log. 404 for an unknown case.
        """
        case = find(case_id)
        no_token_in_the_address(request)
        check_read(case, _bearer(authorization, x_case_token))
        return build_report(
            case.evidence,
            case.card(settings.snapback_public_base_url, lang),
            case_id=case_id,
            lang=lang,
            aerial=case.property_id is not None,
        )

    @app.get("/cases/{case_id}/trace")
    def get_trace(
        case_id: str,
        request: Request,
        last_event_id: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        """Server-sent events: `event: trace`, `id` is the seq, `data` is a TraceEvent.

        Needs a case secret, because the trace names the spot that was drawn. Either secret
        is sent as `Authorization: Bearer` or `X-Case-Token`, never in the address: a `token`
        there is answered 401. A browser reads the stream with `fetch` and a header, not with
        EventSource, which cannot send one. Send `Last-Event-ID` to resume after that seq.
        The stream ends after the verdict event.
        """
        case = find(case_id)
        no_token_in_the_address(request)
        check_read(case, _bearer(authorization, x_case_token))
        return StreamingResponse(
            _trace_stream(case, _after(last_event_id), settings.snapback_trace_pace_ms / 1000),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/events/stream")
    def get_events(
        request: Request,
        follow: bool = True,
        last_event_id: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
        x_events_token: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        """Server-sent events: `event: event`, `id` is the event's own id, `data` is an Event.

        Needs the events token (`SNAPBACK_EVENTS_TOKEN`) as `Authorization: Bearer` or
        `X-Events-Token`, never in the address: a `token` there is answered 401. With no
        token configured the stream is closed to everyone. Send `Last-Event-ID` to resume
        after that event. `follow=false` sends what there is and ends.
        """
        no_token_in_the_address(request)
        sent = _bearer(authorization, x_events_token)
        if not sent:
            raise HTTPException(status_code=401, detail="This needs the events token.")
        expected = settings.snapback_events_token
        if expected is None or not secrets.compare_digest(
            sent.encode(), expected.get_secret_value().encode()
        ):
            raise HTTPException(status_code=403, detail="That token does not open the events.")
        return StreamingResponse(
            _event_stream(events, seq_of(last_event_id), follow),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/cases/{case_id}/notes", response_model=CaseNotes)
    def get_notes(
        case_id: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> CaseNotes:
        """The working notes the agent wrote for this case, read-only: one note per check
        family, plus the explanation and tour questions when a model wrote them. Derived text
        only, each stamped with who wrote it. Same read token as the trace, in a header."""
        case = find(case_id)
        no_token_in_the_address(request)
        check_read(case, _bearer(authorization, x_case_token))
        return case.notes()

    @app.post("/search")
    def post_search(
        brief: RenterBrief,
        request: Request,
        case_id: Annotated[str | None, Query(max_length=64)] = None,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> SearchResponse:
        """CoStar's researched places that fit a renter's brief, in code order, and what the
        search agent decided about them.

        The budget is compared with the asking price as reported, never a band. Every price and
        availability line says "as of CoStar's last research". Code finds and orders the places;
        then up to three get a deep check (the model picks which, among options code wrote) and
        `decisions` lists each choice with who made it (`model` or `policy`) and why. A checked
        place carries `checked: true` and a line built by code; the rest are researched only.
        The search never gives a verdict. With `case_id` and that case's read token in a header,
        what the renter already rejected in that case (see `/preferences`) is applied. The
        response carries LIVE or FIXTURE and the counts. A brief is a few hundred bytes (413
        above `SEARCH_MAX_BODY`); one address gets `SEARCH_PER_MINUTE` searches a minute (429)."""
        address = request.client.host if request.client else "unknown"
        if not search_limit.allow(address):
            raise HTTPException(status_code=429, detail="Too many searches. Try again in a minute.")
        prefs = None
        if case_id is not None:
            case = find(case_id)
            no_token_in_the_address(request)
            check_read(case, _bearer(authorization, x_case_token))
            prefs = case.preferences
        try:
            return agentic_search(brief, lookups, chooser, prefs)
        except KitMissing as missing:
            raise HTTPException(status_code=503, detail=str(missing)) from None

    office = OfficeProofs(
        resolve_data_dir(settings.snapback_data_dir) / "outbox",
        settings.snapback_public_base_url,
        **({"clock": office_clock} if office_clock else {}),
    )

    def office_state(case_id: str, case: RecordedCase | SessionCase) -> OfficeStatus:
        domain = official_domain(getattr(case, "office_record", None))
        confirmed = getattr(case, "office_confirmed_domain", None)
        declined = getattr(case, "office_declined_domain", None)
        return OfficeStatus(
            case_id=case_id,
            source=case.evidence.source,
            domain=domain,
            offered=domain is not None and isinstance(case, SessionCase),
            confirmed=bool(confirmed),
            confirmed_domain=confirmed,
            declined=bool(declined),
            declined_domain=declined,
            guidance=(
                strings.text("office.call_yourself")
                if domain is None
                else f"Ask the poster for an email address at {domain}. A one-time link goes "
                "there; in this demo it lands in a local outbox file, never a real inbox."
            ),
        )

    @app.get("/cases/{case_id}/office")
    def get_office(
        case_id: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> OfficeStatus:
        """The website domain CoStar has on record for this case's office, and whether it was
        confirmed. Needs the case's read token in a header."""
        case = find(case_id)
        no_token_in_the_address(request)
        check_read(case, _bearer(authorization, x_case_token))
        return office_state(case_id, case)

    @app.post("/cases/{case_id}/confirm-office", status_code=202)
    def post_confirm_office(
        case_id: str,
        body: OfficeRequest,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> OfficeRequested:
        """Ask for a one-time link to an address the poster gave the renter.

        Accepted only if the address is at the website domain CoStar has on record for this
        office (never a domain from the ad). The "email" is written to a local outbox file;
        nothing is sent. Needs the case's write token in a header."""
        case = find(case_id)
        no_token_in_the_address(request)
        check_write(case, _bearer(authorization, x_case_token))
        if not isinstance(case, SessionCase):
            raise HTTPException(status_code=409, detail="A recorded example cannot be changed.")
        state = office_state(case_id, case)
        if state.domain is None:
            raise HTTPException(status_code=422, detail=state.guidance)
        if not accepts_address(body.address, state.domain):
            raise HTTPException(
                status_code=422,
                detail=f"That address is not at {state.domain}, the website on record for this "
                "office. Ask the poster for one that is.",
            )
        try:
            office.request(
                case.case_id,
                body.address,
                state.domain,
                listing_context(case.office_record, case.listing),
            )
        except RateLimited:
            raise HTTPException(
                status_code=429, detail="Too many requests for this case. Try again in a while."
            ) from None
        return OfficeRequested(
            case_id=case_id,
            source=state.source,
            domain=state.domain,
            expires_in_minutes=TOKEN_TTL_SECONDS // 60,
            detail="A one-time link was written to the outbox (nothing is sent in this demo).",
        )

    def office_token_state(token: str) -> tuple[SessionCase, Redeemed]:
        """The case and token state for a one-time token, without using it. Raises the plain
        HTTP errors for an unknown, used or expired token and for a case that is gone."""
        seen = office.peek(token)
        if seen.outcome is Outcome.UNKNOWN:
            raise HTTPException(status_code=404, detail="This link is not one we issued.")
        if seen.outcome is Outcome.USED:
            raise HTTPException(
                status_code=410, detail="This link was already used. It works once."
            )
        if seen.outcome is Outcome.EXPIRED:
            raise HTTPException(
                status_code=410, detail="This link expired. Ask the renter for a new one."
            )
        case = find(seen.case_id or "")  # 404 for a case the renter deleted
        if not isinstance(case, SessionCase):
            raise HTTPException(status_code=404, detail="This case is gone.")
        return case, seen

    @app.post("/office/peek")
    def post_office_peek(body: OfficeTokenBody) -> OfficePeek:
        """What the confirm page shows the office: which ad it is asked about. Changes nothing,
        so a mail scanner opening the link does no harm. The token travels in the body, never
        in an address, so it stays out of access logs."""
        case, seen = office_token_state(body.token)
        return OfficePeek(
            domain=seen.domain or "",
            source=case.evidence.source,
            listing=seen.context or ListingContext(),
        )

    @app.post("/office/answer")
    def post_office_answer(body: OfficeAnswer) -> OfficeAnswered:
        """ "Yes, ours" confirms the case; "Not ours" never does and records that the office did
        not recognise the ad. Either answer uses the token."""
        case, _ = office_token_state(body.token)
        redeemed = office.redeem(body.token)
        if redeemed.outcome is not Outcome.CONFIRMED:  # another answer got there first
            raise HTTPException(
                status_code=410, detail="This link was already used. It works once."
            )
        domain = redeemed.domain or ""
        if body.decision == "yes":
            case.confirm_office(domain)
            message = (
                f"Thank you. This ad is now confirmed through {domain}, the website on record "
                "for this office. You can close this page."
            )
        else:
            case.decline_office(domain)
            message = "Thank you. We recorded that this ad is not yours. You can close this page."
        return OfficeAnswered(decision=body.decision, domain=domain, message=message)

    @app.get("/cases/{case_id}/alternatives")
    def get_alternatives(
        case_id: str,
        request: Request,
        n: Annotated[int, Query(ge=1, le=10)] = 3,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> AlternativesResponse:
        """Up to `n` researched places near the checked ad's price and size, never its own
        building and never one the renter rejected. Up to three get the deep check; `decisions`
        says who chose. Needs the case's read token in a header; a token in the address is
        refused."""
        case = find(case_id)
        no_token_in_the_address(request)
        check_read(case, _bearer(authorization, x_case_token))
        try:
            return agentic_alternatives(
                case, lookups, chooser, n, case.preferences, settings.snapback_data_source
            )
        except KitMissing as missing:
            raise HTTPException(status_code=503, detail=str(missing)) from None

    @app.post("/cases/{case_id}/preferences")
    def post_preferences(
        case_id: str,
        body: PreferencesUpdate,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> CasePreferences:
        """The renter rejected a place or a trade-off ("no walk-ups"): remember it for this case.

        Only code-defined keys are kept (`no_walkup`, `needs_parking`, `max_rent`,
        `avoid_property_id`), never free text. Later searches and alternatives for the case
        apply them, so a rejected place does not come back. Needs the case's write token in a
        header; a recorded case cannot be written to (403)."""
        case = find(case_id)
        if case.token is None:
            raise HTTPException(status_code=403, detail="A recorded case cannot be changed.")
        check_write(case, _bearer(authorization, x_case_token))
        with case._lock:  # two writes at once must both land
            case.preferences = merge_preferences(case.preferences, body)
            return case.preferences

    def tour_for(
        property_id: str,
        plan_key: str | None,
        any_plan: bool = False,
        model_id: str | None = None,
    ) -> TourPlan:
        """The walkthrough plan for a researched place, from its record and the scan's cache."""
        try:
            place = place_for(property_id, None, lookups, None, plan_key)
            record = lookups.record(property_id)
        except AmbiguousPlace:
            if not any_plan:
                raise HTTPException(
                    status_code=422,
                    detail="Several floor plans share that building. Send the plan_key you picked.",
                ) from None
            place = None
            record = lookups.record(property_id)
        except KitMissing as missing:
            raise HTTPException(status_code=503, detail=str(missing)) from None
        if place is None and not any_plan:
            raise HTTPException(status_code=404, detail="No researched place with that id.")
        source = place.source if place else (record.source if record else DataSource.FIXTURE)
        sweeps: list = []
        # The scan the photos were placed in comes first; only then the record's other scans.
        wanted = [model_id] if model_id else []
        wanted += [m for m in (record.model_ids if record is not None else []) if m != model_id]
        for each in wanted:
            sweeps = fixture_sweeps(each) if source is DataSource.FIXTURE else cached_sweeps(each)
            if sweeps:
                break
        aerial_on = None
        aerial_ok = False
        if record is not None:
            tile = aerial_side(
                source,
                property_id,
                records=kit_records_for_aerial(),
                data_dir=settings.snapback_data_dir,
            )
            if tile is not None:
                aerial_on, aerial_ok = tile.captured_on, tile.source == DataSource.LIVE
        return build_tour(
            property_id=property_id,
            kind=place.kind if place else "apartment",
            source=source,
            sweeps=sweeps,
            has_scan=place.has_3d_scan if place else bool(record and record.model_ids),
            place=place,
            record=record,
            aerial_on=aerial_on,
            aerial_image=aerial_ok,
            plan_key=place.plan_key if place else None,
        )

    @app.get("/places/{property_id}/tour")
    def get_place_tour(
        property_id: str,
        request: Request,
        plan_key: Annotated[str | None, Query(max_length=128)] = None,
    ) -> TourPlan:
        """ "Walk it first": the guided walkthrough plan for a researched place. Public and read
        only, built by code from the place's own record and the scan cache (no model, no case
        data, no model id or image bytes). The aerial picture itself is served by the case
        route. 404 for a place we do not hold, 422 when a building has several floor plans and
        no `plan_key` was sent."""
        address = request.client.host if request.client else "unknown"
        if not search_limit.allow(address):
            raise HTTPException(status_code=429, detail="Too many searches. Try again in a minute.")
        return tour_for(property_id, plan_key)

    def ad_notes_of(case) -> list:
        """The case's ad-vs-record notes, when its modules produce them (never a network call
        beyond what the card already made). A recorded case, or any failure, has none."""
        modules = getattr(getattr(case, "session", None), "modules", None)
        fn = getattr(modules, "ad_notes", None)
        if not callable(fn):
            return []
        try:
            return list(fn(getattr(case.session, "case_id", case.case_id)) or [])
        except Exception:
            return []

    def office_of(property_id: str) -> str | None:
        return office_on_record(lookups, property_id)

    def case_tour(
        case_id: str, request: Request, authorization, x_case_token, mode: str = "claimed"
    ) -> tuple:
        case = find(case_id)
        no_token_in_the_address(request)
        check_read(case, _bearer(authorization, x_case_token))
        locate = case.evidence.locate
        if mode == "elsewhere":
            other = elsewhere_property(locate) if locate else None
            if other is None or locate is None:
                raise HTTPException(
                    status_code=404, detail="No photo of this case was placed in another building."
                )
            model = scan_model_of(locate, other)
            plan = tour_for(other, None, any_plan=True, model_id=model)
            plan, fields = map_elsewhere(plan, locate, other, office_of(other))
            return choose_walk(plan), locate, fields, model
        if case.property_id is None:
            raise HTTPException(status_code=404, detail="This case has no building on record.")
        model = scan_model_of(locate)
        plan = tour_for(case.property_id, None, any_plan=True, model_id=model)
        if locate is None:
            return plan, None, {}, model
        scan_plan = locate.chosen.floor_plan if locate.chosen else None
        plan, fields = map_locate(
            plan,
            locate,
            scan_plan=scan_plan,
            ad_plan=ad_plan_word(ad_beds_of(case)),
            model_id=model,
        )
        plan = attach_claims(plan, ad_notes_of(case))
        prefs = getattr(case, "preferences", None)
        return choose_walk(plan, None, must_have_kinds_of(prefs)), locate, fields, model

    @app.get("/cases/{case_id}/tour")
    def get_case_tour(
        case_id: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> TourPlan:
        """The same walkthrough for the ad's own building, with the case's placed photos on the
        rooms they were taken in. Needs the case's read token in a header."""
        return case_tour(case_id, request, authorization, x_case_token)[0]

    @app.get("/cases/{case_id}/walk")
    def get_case_walk(
        case_id: str,
        request: Request,
        mode: Annotated[Literal["claimed", "elsewhere"], Query()] = "claimed",
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> WalkResponse:
        """The case-scoped walk: the tour plan plus the case's locate result, so the page can
        show which ad photos were placed, which were taken elsewhere and which could not be
        placed. Needs the case's read token in a header."""
        plan, locate, fields, model = case_tour(case_id, request, authorization, x_case_token, mode)
        return WalkResponse(plan=plan, model_id=model, locate=locate, photos=fields)

    def capture_date_of(record):
        """The aerial capture date when already known (never a fetch), else None."""
        if record is None:
            return None
        return known_capture_date(record, source=record.source, data_dir=settings.snapback_data_dir)

    @app.get("/cases/{case_id}/tour-prep")
    def get_tour_prep(
        case_id: str,
        request: Request,
        lang: Language = "en",
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> TourPrepPack:
        """The tour-prep pack for a checked ad: what the record says, questions to ask, and
        steps before paying. Built by code from fixed text, EN or ES. Needs the case's read
        token in a header (a token in the address is refused with 401); the owner of record
        and licence lines come from the case."""
        case = find(case_id)
        no_token_in_the_address(request)
        check_read(case, _bearer(authorization, x_case_token))
        evidence = case.evidence
        record = None
        if case.property_id:
            try:
                record = lookups.record(case.property_id)
            except KitMissing:
                record = None
        photos = evidence.locate.photos if evidence.locate else []
        # A fixture case is FIXTURE even beside a live record: the label never overstates.
        live = evidence.source is DataSource.LIVE and (
            record is None or record.source is DataSource.LIVE
        )
        return build_tour_prep(
            source=DataSource.LIVE if live else DataSource.FIXTURE,
            lang=lang,
            record=record,
            owner=evidence.owner,
            licence=evidence.license,
            room_labels=[
                p.room_label
                for p in photos
                if p.room_label and p.status is LocateStatus.LOCATED_IN_CLAIMED
            ],
            aerial_on=capture_date_of(record),
        )

    @app.get("/places/{property_id}/tour-prep")
    def get_place_tour_prep(
        property_id: str,
        request: Request,
        plan_key: Annotated[str | None, Query(max_length=128)] = None,
        lang: Language = "en",
    ) -> TourPrepPack:
        """The tour-prep pack for a researched place. Public, and built only from the place's own
        record (no owner, licence or case data). 404 for a place we do not hold, 422 when a
        building has several floor plans and no `plan_key` was sent."""
        address = request.client.host if request.client else "unknown"
        if not search_limit.allow(address):
            raise HTTPException(status_code=429, detail="Too many searches. Try again in a minute.")
        try:
            found = place_and_raw_for(property_id, None, lookups, None, plan_key)
            record = lookups.record(property_id)
        except AmbiguousPlace:
            raise HTTPException(
                status_code=422,
                detail="Several floor plans share that building. Send the plan_key you picked.",
            ) from None
        except KitMissing as missing:
            raise HTTPException(status_code=503, detail=str(missing)) from None
        if found is None:
            raise HTTPException(status_code=404, detail="No researched place with that id.")
        place, raw = found
        return build_tour_prep(
            source=place.source,
            lang=lang,
            place=place,
            raw=raw,
            record=record,
            aerial_on=capture_date_of(record),
        )

    @app.post("/cases/{case_id}/tour-draft")
    def post_tour_draft(
        case_id: str,
        body: TourDraftRequest,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> TourDraft:
        """A tour-request draft addressed only to the leasing office on record, for the renter
        to approve. Needs the case's write token in a header. It is never sent: the response is
        a draft (`status: draft`, `sent: false`) and no route sends it. 404 for a place we do
        not hold, 422 when it has no office on record."""
        case = find(case_id)
        check_write(case, _bearer(authorization, x_case_token))
        try:
            place = place_for(body.property_id, body.floor_plan, lookups, body.brief, body.plan_key)
        except AmbiguousPlace:
            raise HTTPException(
                status_code=422,
                detail="Several floor plans share that label. Send the plan_key you picked.",
            ) from None
        except KitMissing as missing:
            raise HTTPException(status_code=503, detail=str(missing)) from None
        if place is None:
            raise HTTPException(status_code=404, detail="No researched place with that id.")
        try:
            return draft_tour_request(place, body.brief)
        except NoOfficeOnRecord:
            raise HTTPException(
                status_code=422, detail="That place has no leasing office on record."
            ) from None

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

    @app.post("/cases/{case_id}/answer")
    def post_answer(
        case_id: str,
        answer: Answer,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> CaseStatus:
        """The renter's answer when the agent asked for the license number (A24 stretch).

        Needs the case's write secret, as the approval does. The text is read for a number by
        code and goes no further; a blank answer or one with no number changes nothing.
        409 unless the renter was asked.
        """
        case = find(case_id)
        check_write(case, _bearer(authorization, x_case_token))
        try:
            case.answer(answer.text)
        except NothingWaiting:
            raise HTTPException(
                status_code=409, detail="This case is not waiting for an answer."
            ) from None
        return case.status(with_challenge=True)

    @app.post("/cases/{case_id}/reply")
    async def post_reply(
        case_id: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_case_token: Annotated[str | None, Header()] = None,
    ) -> ReplyResponse:
        """The photo the poster sent back, checked (A14). One image, in the form field `photo`.

        Needs the case's write secret in a header, as the approval does. The photo is checked
        on this machine: is it a copy of one of the listing's own photos, and is the code on
        it? A copy is forged, whenever it arrives. A code that cannot be read is not proof:
        another photo is asked for, up to the cap. A right code is not yet "proven": whether
        it was taken at the spot needs locate, so it stays not confirmed. A reply that comes
        too late and is not a copy is asked for again once. 409 unless a reply is awaited.
        """
        case = find(case_id)
        check_write(case, _bearer(authorization, x_case_token))
        form = await parse_form(request, 1, max_photo_bytes)
        try:
            files = [item for item in form.getlist("photo") if isinstance(item, UploadFile)]
            if len(files) != 1:
                raise HTTPException(status_code=422, detail="Send one image as `photo`.")
            [photo] = read_images(files, 1, max_photo_bytes)
            try:
                check = await run_in_threadpool(case.reply, photo)
            except NothingWaiting:
                raise HTTPException(
                    status_code=409, detail="This case is not waiting for a reply."
                ) from None
            except UnreadablePhoto:
                raise HTTPException(
                    status_code=415, detail="That file is not a picture we can open."
                ) from None
            except OcrUnavailable:
                raise HTTPException(
                    status_code=503,
                    detail="The reader for the code is not installed on this server.",
                ) from None
        finally:
            await form.close()

        status = case.status(with_challenge=True)
        return ReplyResponse(
            case_id=status.case_id,
            source=status.source,
            status=status.status,
            check=check,
            presence=case.presence(),
            state=status.state,
            challenge_text=status.challenge_text,
        )

    def eval_file(path: Path, missing: str) -> Response:
        """One of the eval harness's CSVs, as written. Only the agreed format is served."""
        try:
            results = read_results(path)
        except NotTheAgreedCsv:
            raise HTTPException(
                status_code=500, detail="The results file is not the agreed eval results CSV."
            ) from None
        if results is None:
            raise HTTPException(status_code=404, detail=missing)
        return Response(
            content=results, media_type="text/csv", headers={"Cache-Control": "no-store"}
        )

    @app.get("/eval/results.csv")
    def get_eval_results() -> Response:
        """The eval harness's results as CSV, for the Lab panel. Public and read-only (#69).

        The file holds aggregate numbers only (how often each condition caught what it should,
        with n), and no case data, so it needs no token. The path comes from settings, never
        from the request, and only the agreed CSV is ever served.
        """
        return eval_file(settings.snapback_eval_results, "No eval results yet. Run `make eval`.")

    @app.get("/eval/locate_real.csv")
    def get_eval_locate_real() -> Response:
        """Locate accuracy on the buildings' own listing photos (A8, #72). Totals only.

        Same columns and the same rules as `/eval/results.csv`: public, read-only, a fixed
        path, and only the agreed CSV is served.
        """
        return eval_file(
            settings.snapback_eval_locate_real,
            "No locate results yet. Run `make eval-locate-real`.",
        )

    return app


app = create_app()
