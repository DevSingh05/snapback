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
import secrets
import threading
from collections.abc import Callable
from datetime import datetime

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
from snapback.agent.modules import CODE_ALPHABET, FIXTURES_DIR
from snapback.agent.rules.contact import phone_salt
from snapback.card import strings
from snapback.contracts import (
    Card,
    CaseProgress,
    DataSource,
    ModuleEvidence,
    TraceEvent,
    TraceKind,
    VerdictState,
)
from snapback.settings import Settings
from snapback.verdict import FIXTURE_ID_PREFIX, build_card


class NothingWaiting(Exception):
    """An approval arrived for a case that is not waiting for one."""


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


def _now() -> datetime:
    return datetime.now().astimezone()


class RecordedCase:
    done = True
    token = None  # a recorded case can never be written to, so it has no secret
    read_token = None

    def __init__(
        self, case_id: str, card: Card, events: list[TraceEvent], evidence: ModuleEvidence
    ) -> None:
        self.case_id = case_id
        self._card = card
        self._events = events
        self._evidence = evidence
        self._photos = len(evidence.locate.photos) if evidence.locate else 0

    def events(self) -> list[TraceEvent]:
        return self._events

    def card(self, verify_base_url: str, lang: str = strings.DEFAULT_LANG) -> Card:
        """The recorded card as it is. In another language, the same evidence laid out again."""
        if lang == self._card.lang:
            return self._card
        return build_card(
            self._evidence,
            checked_at=self._card.checked_at,
            verify_base_url=verify_base_url,
            lang=lang,
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


class SessionCase:
    def __init__(
        self,
        case_id: str,
        session: CaseSession,
        listing: Listing,
        runner: Callable[[CaseSession], object],
    ) -> None:
        self.case_id = case_id  # short, shown to people, enough to read the case
        self.token = secrets.token_urlsafe(24)  # 192 bits, needed for every write
        # A second secret that can only read. It is the one a browser may put in an address,
        # where servers log it, so it must never be able to approve anything.
        self.read_token = secrets.token_urlsafe(24)
        self.session = session
        self._listing = listing
        self._runner = runner
        self.staged = False  # made from a staged demo case (fixtures/demo)
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
                self._checked_at = _now()

    def events(self) -> list[TraceEvent]:
        return list(self.session.trace.events)

    def card(self, verify_base_url: str, lang: str = strings.DEFAULT_LANG) -> Card:
        card = build_card(
            self.session.evidence,
            checked_at=self._checked_at or _now(),
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
    def __init__(self, settings: Settings, lookups: Lookups | None = None) -> None:
        self._settings = settings
        # Lane D's adapters: the record and the for-sale lookup (A10). The kit is read once.
        self._lookups = lookups or KitLookups(settings.snapback_data_source)
        self._cases: dict[str, RecordedCase | SessionCase] = {}
        self._lock = threading.Lock()
        self._runner = (
            _deepagents_runner() if settings.snapback_agent == "deepagents" else _policy_runner
        )
        if settings.snapback_data_source is DataSource.FIXTURE:
            self._add_recorded_fixture()

    def _add_recorded_fixture(self) -> None:
        card = Card.model_validate_json((FIXTURES_DIR / "card_hold.json").read_text())
        lines = (FIXTURES_DIR / "trace_events.jsonl").read_text().strip().splitlines()
        events = [TraceEvent.model_validate(json.loads(line)) for line in lines]
        evidence = ModuleEvidence.model_validate_json(
            (FIXTURES_DIR / "module_evidence_hold.json").read_text()
        )
        self._cases[public_id(card.case_id)] = RecordedCase(card.case_id, card, events, evidence)

    def get(self, case_id: str) -> RecordedCase | SessionCase | None:
        return self._cases.get(public_id(case_id))

    def _new_id(self) -> str:
        while True:
            candidate = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
            if candidate not in self._cases:
                return candidate

    def create(self, listing: Listing, property_id: str | None = None) -> SessionCase:
        """Start a check. `property_id` is our id for the building the listing claims.

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
                )
            session = CaseSession(full_id, modules, Trace(full_id, source))
            if listing.truncated:
                session.trace.emit(TraceKind.STATUS, strings.text("trace.intake.truncated"))
            if listing.injection_spans:
                session.trace.emit(TraceKind.STATUS, strings.text("trace.intake.injection"))
            case = SessionCase(short_id, session, listing, self._runner)
            case.staged = demo is not None
            self._cases[short_id] = case
        case.advance()
        return case
