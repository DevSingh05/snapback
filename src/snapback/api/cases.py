"""The cases the API is serving, kept in memory.

Two kinds of case answer the same questions (status, card, trace, approve):

- `RecordedCase`: the shared fixtures in `fixtures/contracts/`, served as they are. In fixture
  mode the fixture case is always there, so the web app and the sidecar can integrate against a
  known card and a known trace.
- `SessionCase`: a case created through `POST /cases` and driven by the agent session.

Live mode needs the locate, record and challenge modules from lanes V and D. Until they land,
creating a case in live mode says so instead of pretending.
"""

import json
import logging
import secrets
import threading
from collections.abc import Callable
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from snapback.agent import (
    CaseSession,
    FixtureModules,
    PolicyChooser,
    Trace,
    run_case,
)
from snapback.agent.demo import demo_modules, load_demo_case, staged
from snapback.agent.intake import Listing, read_listing
from snapback.agent.join import JoinedModules, KitLookups, Lookups
from snapback.agent.locate_live import LiveLocate
from snapback.agent.modules import CODE_ALPHABET, FIXTURES_DIR
from snapback.agent.reply import ReplyModules
from snapback.agent.rules.contact import phone_salt
from snapback.card import strings
from snapback.contracts import (
    Card,
    CaseProgress,
    DataSource,
    ModuleEvidence,
    PresenceStatus,
    PropertyRecord,
    ReplyCheck,
    TraceEvent,
    TraceKind,
    VerdictState,
)
from snapback.settings import Settings
from snapback.verdict import FIXTURE_ID_PREFIX, build_card, presence_of
from snapback.vision.memory.store import PhotoMemory

log = logging.getLogger("snapback.api")

# The zone each market's cards are stamped in. Lane D's adapter names the markets.
MARKET_ZONES = {"Houston": "America/Chicago", "Los Angeles": "America/Los_Angeles"}


class NothingWaiting(Exception):
    """An approval or a reply arrived for a case that is not waiting for one."""


class UnknownProperty(Exception):
    """A check named a building we hold no record for."""


class ChallengeView(BaseModel):
    """The message the renter is asked to approve."""

    text: str
    spot_label: str
    code: str


class CaseStatus(BaseModel):
    """Where a case stands, for `GET /cases/{id}` and after an approval.

    The same fields as `CreateCaseResponse` in contracts.py without the secret, plus the
    drafted challenge in parts for a client that wants the spot and the code separately.
    """

    case_id: str
    source: DataSource
    status: CaseProgress
    state: VerdictState | None = None  # set once the case is done
    challenge_text: str | None = None  # the message the renter may forward
    photos: int = 0
    screenshots: int = 0
    injection_noticed: bool = False
    challenge: ChallengeView | None = None


def public_id(case_id: str) -> str:
    """The short id people see: no fixture prefix, upper case."""
    return case_id.strip().upper().removeprefix(FIXTURE_ID_PREFIX.upper())


def _now(zone: tzinfo | None = None) -> datetime:
    """Now, on the card's clock: the building's zone when one is given."""
    return datetime.now(zone) if zone is not None else datetime.now().astimezone()


class RecordedCase:
    done = True
    token = None  # a recorded case can never be written to, so it has no secret
    read_token = None

    def __init__(
        self,
        case_id: str,
        card: Card,
        events: list[TraceEvent],
        evidence: ModuleEvidence,
        zone: tzinfo | None = None,
    ) -> None:
        self.case_id = case_id
        self._card = card
        self._events = events
        self._evidence = evidence
        self._zone = zone  # the card's clock: the building's zone, not the one it was saved in
        self._photos = len(evidence.locate.photos) if evidence.locate else 0

    @property
    def evidence(self) -> ModuleEvidence:
        """What the modules found for this case. Read-only for other lanes' routes."""
        return self._evidence

    @property
    def property_id(self) -> str | None:
        """Our id for the building the listing claims, if it named one."""
        return self._evidence.locate.claimed_property_id if self._evidence.locate else None

    def events(self) -> list[TraceEvent]:
        return self._events

    def card(self, verify_base_url: str, lang: str = strings.DEFAULT_LANG) -> Card:
        """The recorded case, laid out on the card's clock in the language asked for.

        The card is rebuilt from the recorded evidence at the recorded moment, so every time
        on it (when it was checked, when it expires, when the reply came) is shown in the
        building's zone. With no zone given it is served exactly as it was saved.
        """
        if self._zone is None and lang == self._card.lang:
            return self._card
        checked_at = self._card.checked_at
        if self._zone is not None:
            checked_at = checked_at.astimezone(self._zone)
        return build_card(
            self._evidence, checked_at=checked_at, verify_base_url=verify_base_url, lang=lang
        )

    def status(self, with_challenge: bool = False) -> CaseStatus:
        return CaseStatus(
            case_id=self.case_id,
            source=self._card.source,
            status=CaseProgress.DONE,
            state=self._card.state,
            photos=self._photos,
        )

    def approve(self, decision: str, text: str | None) -> None:
        raise NothingWaiting(self.case_id)

    def reply(self, photo: bytes) -> ReplyCheck:
        raise NothingWaiting(self.case_id)

    def presence(self) -> PresenceStatus:
        return presence_of(self._evidence).status


class SessionCase:
    def __init__(
        self,
        case_id: str,
        session: CaseSession,
        listing: Listing,
        runner: Callable[[CaseSession], object],
        zone: tzinfo | None = None,
    ) -> None:
        self.case_id = case_id  # short, shown to people, enough to read the case
        self._zone = zone  # the card's clock: the building's zone, not the server's
        self.token = secrets.token_urlsafe(24)  # 192 bits, needed for every write
        # A second secret that can only read. It is the one a browser may put in an address,
        # where servers log it, so it must never be able to approve anything.
        self.read_token = secrets.token_urlsafe(24)
        self.owner: str | None = None  # who it is registered under, for delete (A11)
        self.session = session
        self._listing = listing
        self._runner = runner
        self.staged = False  # made from a staged demo case (fixtures/demo)
        self.property_id: str | None = None  # our id for the building the listing claims
        self._checked_at: datetime | None = None
        self._lock = threading.Lock()

    @property
    def done(self) -> bool:
        return self.session.done

    def advance(self) -> None:
        """Run until the case needs the renter or has a verdict."""
        with self._lock:
            self._runner(self.session)
            if self.session.done and self._checked_at is None:
                self._checked_at = _now(self._zone)

    @property
    def evidence(self) -> ModuleEvidence:
        """What the modules found for this case so far. Read-only for other lanes' routes."""
        return self.session.evidence

    def events(self) -> list[TraceEvent]:
        return list(self.session.trace.events)

    def card(self, verify_base_url: str, lang: str = strings.DEFAULT_LANG) -> Card:
        card = build_card(
            self.session.evidence,
            checked_at=self._checked_at or _now(self._zone),
            verify_base_url=verify_base_url,
            lang=lang,
        )
        # A card made from a staged demo case says so on the card itself.
        return staged(card) if self.staged else card

    def status(self, with_challenge: bool = False) -> CaseStatus:
        """Where the case stands. The drafted challenge is left out unless asked for."""
        if self.session.done:
            status = CaseProgress.DONE
        elif self.session.waiting_for_approval:
            status = CaseProgress.WAITING_FOR_APPROVAL
        elif self.session.waiting_for_reply:
            status = CaseProgress.WAITING_FOR_REPLY
        else:
            status = CaseProgress.RUNNING
        draft = self.session.pending_challenge
        if status is not CaseProgress.WAITING_FOR_APPROVAL or not with_challenge:
            draft = None
        return CaseStatus(
            case_id=self.case_id,
            source=self.session.trace.source,
            status=status,
            state=self.session.verdict.state if self.session.verdict else None,
            challenge_text=draft.text if draft else None,
            photos=self._listing.photos,
            screenshots=self._listing.screenshots,
            injection_noticed=bool(self._listing.injection_spans),
            challenge=(
                ChallengeView(text=draft.text, spot_label=draft.spot_label, code=draft.code)
                if draft
                else None
            ),
        )

    def approve(self, decision: str, text: str | None) -> None:
        with self._lock:
            try:
                self.session.approve(decision, text)
            except RuntimeError as error:
                raise NothingWaiting(self.case_id) from error
        self.advance()

    def reply(self, photo: bytes) -> ReplyCheck:
        """Check the poster's reply photo and carry the case on (A14).

        Raises `NothingWaiting` unless a reply is awaited, and `UnreadablePhoto` if the file
        is not a picture; in both cases nothing about the case changes.
        """
        with self._lock:
            modules = self.session.modules
            if not self.session.waiting_for_reply or not isinstance(modules, ReplyModules):
                raise NothingWaiting(self.case_id)
            check, outcome = modules.check_reply(self.session.case_id, photo)
            self.session.reply(outcome)
        self.advance()
        return check

    def presence(self) -> PresenceStatus:
        return presence_of(self.session.evidence).status


def _policy_runner(session: CaseSession) -> object:
    return run_case(session, PolicyChooser())


def _deepagents_runner() -> Callable[[CaseSession], object]:
    """A runner that drives each case with its own deep agent, falling back to the policy."""
    agents: dict[str, object] = {}

    def run(session: CaseSession) -> object:
        try:
            from snapback.agent.graph import build_agent, run_case_with_agent

            agent = agents.setdefault(session.case_id, build_agent(session))
            return run_case_with_agent(session, agent)
        except Exception:
            # The extra is not installed, there is no key, or the graph could not be built.
            session.trace.emit(TraceKind.ERROR, strings.text("trace.error.model_failed"))
            return run_case(session, PolicyChooser())

    return run


class CaseStore:
    def __init__(
        self,
        settings: Settings,
        lookups: Lookups | None = None,
        live_locate: LiveLocate | None = None,
    ) -> None:
        self._settings = settings
        # Lane D's adapters: the record and the for-sale lookup (A10). The kit is read once.
        self._lookups = lookups or KitLookups(settings.snapback_data_source)
        self._live_locate = live_locate or LiveLocate(
            data_dir=settings.snapback_data_dir,
            records=lambda: self._lookups.records().values(),
            index_name=settings.snapback_locate_index,
            budget_s=settings.snapback_locate_budget_s,
        )
        self._cases: dict[str, RecordedCase | SessionCase] = {}
        self._lock = threading.Lock()
        self._memory: PhotoMemory | None = None
        self._runner = (
            _deepagents_runner() if settings.snapback_agent == "deepagents" else _policy_runner
        )
        if settings.snapback_data_source is DataSource.FIXTURE:
            self._add_recorded_fixture()
        elif settings.demo_case:
            # Easy to set both and expect the staged cards. A live case carries no stand-in,
            # so the pack gives only its listing text and the cards read "not checked".
            log.warning(
                "DEMO_CASE=%s with SNAPBACK_DATA_SOURCE=live: only the staged listing text "
                "is used. Photos and presence will read 'Not checked'. For the staged cards "
                "run with SNAPBACK_DATA_SOURCE=fixture.",
                settings.demo_case,
            )

    def _add_recorded_fixture(self) -> None:
        card = Card.model_validate_json((FIXTURES_DIR / "card_hold.json").read_text())
        lines = (FIXTURES_DIR / "trace_events.jsonl").read_text().strip().splitlines()
        events = [TraceEvent.model_validate(json.loads(line)) for line in lines]
        evidence = ModuleEvidence.model_validate_json(
            (FIXTURES_DIR / "module_evidence_hold.json").read_text()
        )
        zone = ZoneInfo(self._settings.snapback_card_timezone)
        self._cases[public_id(card.case_id)] = RecordedCase(
            card.case_id, card, events, evidence, zone
        )

    def get(self, case_id: str) -> RecordedCase | SessionCase | None:
        return self._cases.get(public_id(case_id))

    def _new_id(self) -> str:
        while True:
            candidate = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
            if candidate not in self._cases:
                return candidate

    def _photo_memory(self) -> PhotoMemory:
        """Lane V's photo memory under the data dir, opened the first time it is needed."""
        if self._memory is None:
            path = self._settings.snapback_data_dir / "memory" / "photo_memory.sqlite"
            self._memory = PhotoMemory(path)
        return self._memory

    def __len__(self) -> int:
        return len(self._cases)

    def discard(self, case_id: str) -> None:
        """Forget a case. Used when it has been deleted from disk by the renter's "delete"."""
        with self._lock:
            self._cases.pop(public_id(case_id), None)

    def _zone_of(self, record: PropertyRecord | None) -> ZoneInfo:
        """The card's clock: the zone of the building's market, else the configured one."""
        market = record.market if record is not None else None
        return ZoneInfo(MARKET_ZONES.get(market or "", self._settings.snapback_card_timezone))

    def create(
        self,
        listing: Listing,
        property_id: str | None = None,
        register: Callable[[str], None] | None = None,
        *,
        photos: list[bytes] | None = None,
    ) -> SessionCase:
        """Start a check. `property_id` is our id for the building the listing claims, and
        `photos` are the listing photos as sent, in order.

        `register` is told the new case's id before anything runs. If it raises, there is no
        case: a check that could not be recorded for later deletion is not started.

        The record and the for-sale lookup come from lane D's adapters and feed the price,
        unit and contact rules.

        The twin and the challenge are still stand-ins, and stand-ins are fixture data. They
        are used only in a fixture case. A live case, or any case on a live record, gets
        none: its photos are "not checked" and nobody is asked to prove presence, so it can
        never read VERIFIED on the strength of a stand-in.

        Raises `UnknownProperty` for an id we hold no record for, and `KitMissing` when the
        record is asked for and the kit is not on this machine.
        """
        record = None
        if property_id:
            record = self._lookups.record(property_id)
            if record is None:
                raise UnknownProperty

        demo = load_demo_case(self._settings.demo_case) if self._settings.demo_case else None
        if demo is not None and not listing.text:
            # A staged case (fixtures/demo). With nothing pasted, its own listing is read.
            own = read_listing(demo.listing_text)
            listing = own.model_copy(
                update={"photos": listing.photos, "screenshots": listing.screenshots}
            )
        for_sale = self._lookups.for_sale(listing.text) if listing.text else None

        live = self._settings.snapback_data_source is DataSource.LIVE or (
            record is not None and record.source is DataSource.LIVE
        )
        source = DataSource.LIVE if live else DataSource.FIXTURE

        with self._lock:
            short_id = self._new_id()
            # Fixture ids are marked as such. A live case carries no stand-in and no mark.
            full_id = short_id if live else f"{FIXTURE_ID_PREFIX}{short_id}"
            if register is not None:
                register(full_id)
            if demo is not None and not live and record is None:
                # The demo pack brings its own stand-ins, record included.
                modules = demo_modules(demo, listing)
            else:
                modules = JoinedModules(
                    stand_in=None if live else FixtureModules(listing_scope=listing.scope),
                    listing=listing,
                    record=record,
                    for_sale=for_sale,
                    salt=phone_salt(self._settings),
                    record_source=record.source if record else source,
                    live_locate=self._live_locate if live else None,
                    photo_bytes=photos,
                    lookups=self._lookups,
                    case_id=full_id,
                )
            if self._settings.snapback_challenge == "reply" and not live:
                # The poster's real reply is awaited and checked (A14). The listing photos
                # go into the photo memory now, so a reply that copies one is caught. A live
                # case has no challenge yet (no stand-in), so there is nothing to reply to.
                modules = ReplyModules(modules, self._photo_memory())
                modules.remember_listing_photos(full_id, photos or [])
            session = CaseSession(full_id, modules, Trace(full_id, source))
            if listing.truncated:
                session.trace.emit(TraceKind.STATUS, strings.text("trace.intake.truncated"))
            if listing.injection_spans:
                session.trace.emit(TraceKind.STATUS, strings.text("trace.intake.injection"))
            case = SessionCase(short_id, session, listing, self._runner, self._zone_of(record))
            case.staged = demo is not None
            case.property_id = property_id  # the building the listing claims, if it named one
            self._cases[short_id] = case
        case.advance()
        return case
