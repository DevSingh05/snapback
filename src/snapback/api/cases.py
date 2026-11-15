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
import os
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
from snapback.agent.background import BackgroundAgents
from snapback.agent.casework import CaseNotes, notes_view, places_text, refresh_policy_notes
from snapback.agent.demo import demo_modules, load_demo_case, staged
from snapback.agent.intake import Listing, read_listing
from snapback.agent.join import JoinedModules, KitLookups, Lookups, license_of, owner_of
from snapback.agent.locate_live import LiveLocate
from snapback.agent.modules import CODE_ALPHABET, FIXTURES_DIR
from snapback.agent.reply import ReplyModules
from snapback.agent.rules.contact import phone_salt
from snapback.api.casefiles import CaseFiles
from snapback.card import strings
from snapback.contracts import (
    Card,
    CasePreferences,
    CaseProgress,
    DataSource,
    ForSaleMatch,
    ForSaleStatus,
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
    question: str | None = None  # code-written; set only while status is waiting_for_answer


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
    # What the renter rejected; a recorded case is read-only, so this stays empty.
    preferences = CasePreferences()
    agent_running = False  # no agent works a recorded case

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

    def answer(self, text: str | None) -> None:
        raise NothingWaiting(self.case_id)

    def presence(self) -> PresenceStatus:
        return presence_of(self._evidence).status

    def notes(self) -> CaseNotes:
        """A recorded case was not worked by an agent here, so it has no working notes."""
        return CaseNotes(case_id=self.case_id, source=self._evidence.source, notes=[])


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
        self.demo_case_id: str | None = None  # which one, so a replay can name its source
        # What the renter rejected in this case ("no walk-ups", a place), code-defined keys only.
        self.preferences = CasePreferences()
        self.property_id: str | None = None  # our id for the building the listing claims
        self.files: CaseFiles | None = None  # evidence file, notes and pictures (E3 serves them)
        self._checked_at: datetime | None = None
        self._lock = threading.RLock()
        # Evidence an agent adds waits for the policy's turn. Re-entrant, so a caller already
        # inside the case cannot deadlock on it.
        session.evidence_lock = self._lock
        self.agents: BackgroundAgents | None = None  # set when the agent runs in the background

    @property
    def agent_running(self) -> bool:
        """The deep agent is still working this case in the background (queued or running)."""
        return self.agents is not None and self.agents.running(self.case_id)

    @property
    def listing(self) -> Listing:
        """What intake read from the ad. Read-only for other routes (search alternatives)."""
        return self._listing

    @property
    def done(self) -> bool:
        return self.session.done

    def advance(self) -> None:
        """Run until the case needs the renter or has a verdict."""
        with self._lock:
            self._runner(self.session)
            if self.session.done and self._checked_at is None:
                self._checked_at = _now(self._zone)
            self._write_evidence_file()

    def _write_evidence_file(self) -> None:
        """A live case's evidence file (with each photo's matched pairs), for the "How we know"
        drawer. A fixture or staged case keeps the team-made file the routes fall back to."""
        if self.session.trace.source is not DataSource.LIVE:
            return
        evidence = self.session.evidence_file()
        if evidence is None:
            return
        if self.files is None:
            self.files = CaseFiles(evidence=evidence)
        else:
            self.files.evidence = evidence

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
        return staged(card, self.demo_case_id) if self.staged else card

    def status(self, with_challenge: bool = False) -> CaseStatus:
        """Where the case stands. The drafted challenge is left out unless asked for."""
        if self.session.done:
            status = CaseProgress.DONE
        elif self.session.waiting_for_approval:
            status = CaseProgress.WAITING_FOR_APPROVAL
        elif self.session.waiting_for_reply:
            status = CaseProgress.WAITING_FOR_REPLY
        elif self.session.waiting_for_answer:
            status = CaseProgress.WAITING_FOR_ANSWER
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
            question=self.session.question,
        )

    @property
    def office_record(self) -> object | None:
        """The property record this case runs on, if any. Read-only, for the office proof."""
        return getattr(self.session.modules, "record", None)

    @property
    def office_confirmed_domain(self) -> str | None:
        return self.session.evidence.office_confirmed_domain

    @property
    def office_declined_domain(self) -> str | None:
        return self.session.evidence.office_declined_domain

    def confirm_office(self, domain: str) -> None:
        """Someone at the office's own domain on record answered "Yes, ours"."""
        with self._lock:
            self.session.confirm_office(domain)

    def decline_office(self, domain: str) -> None:
        """Someone at the office's own domain on record answered "Not ours"."""
        with self._lock:
            self.session.decline_office(domain)

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

    def answer(self, text: str | None) -> None:
        """The renter's answer to the license question (A24 stretch); the case carries on.

        Raises `NothingWaiting` unless the renter was asked."""
        with self._lock:
            try:
                self.session.answer(text)
            except RuntimeError as error:
                raise NothingWaiting(self.case_id) from error
        self.advance()

    def presence(self) -> PresenceStatus:
        return presence_of(self.session.evidence).status

    def notes(self) -> CaseNotes:
        """The notes the agent wrote for this case (read-only; see casework.py)."""
        return notes_view(self.session)


def _policy_runner(session: CaseSession) -> object:
    try:
        return run_case(session, PolicyChooser())
    finally:
        refresh_policy_notes(session)  # the same notes, written by code


def _setup_langsmith(settings: Settings) -> None:
    """Trace with LangSmith when a key is set (settings or the environment). Only the project name
    is set here; each run's metadata is the case id and the mode, nothing from the ad."""
    try:
        from snapback.agent.graph import enable_langsmith

        key = settings.langsmith_api_key
        enable_langsmith(key.get_secret_value() if key else None, settings.langsmith_project)
    except Exception:
        log.warning("LangSmith tracing could not be set up; carrying on without it")


def _background_job(
    case: "SessionCase", settings: Settings, model_factory: Callable[[], object] | None
) -> Callable[[], None]:
    """What one background run does: build the advisory agent (main model for the plan, the small
    one for the sub-agents) and run it within the time limit. Any failure is a trace line, never
    an exception, and never touches the result."""

    def model(name: str, max_tokens: int) -> object:
        if model_factory is not None:
            return model_factory()
        from snapback.agent.graph import build_model

        key = settings.anthropic_api_key
        if key is None and not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("no model key")
        return build_model(
            key.get_secret_value() if key else None,
            name,
            settings.agent_timeout_s,
            max_tokens,
            "low",
        )

    def run() -> None:
        session = case.session
        try:
            from snapback.agent.graph import build_advisory_agent, run_advisory

            agent = build_advisory_agent(
                session,
                model(settings.snapback_agent_model, 2048),
                subagent_model=model(settings.snapback_subagent_model, 1024),
            )
        except Exception:
            session.trace.emit(
                TraceKind.ERROR, strings.text("trace.error.model_failed", session.lang)
            )
            return
        run_advisory(session, agent, deadline_s=settings.agent_timeout_s)

    return run


def _deepagents_runner(
    settings: Settings | None = None, model_factory: Callable[[], object] | None = None
) -> Callable[[CaseSession], object]:
    """A runner that drives each case with its own deep agent, falling back to the policy.

    The agent plans (its todo list), orders the checks and hands each family to a sub-agent;
    `decide()` still sets the result. It gets `snapback_agent_timeout_s` per run. On any error
    or on the time limit the trace says so, code finishes the case, and that case stays on the
    policy from then on. `model_factory` makes the chat model (tests); by default Claude, with
    the key from settings (read from the environment), never printed."""
    agents: dict[str, object] = {}
    timeout_s = settings.agent_timeout_s if settings is not None else None
    if settings is not None:
        _setup_langsmith(settings)

    def make_model() -> object:
        if model_factory is not None:
            return model_factory()
        from snapback.agent.graph import build_model

        key = settings.anthropic_api_key if settings is not None else None
        if key is None and not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("no model key")
        return build_model(
            key.get_secret_value() if key else None,
            settings.snapback_agent_model if settings is not None else None,
            timeout_s,
        )

    def policy(session: CaseSession) -> object:
        try:
            return run_case(session, PolicyChooser())
        finally:
            refresh_policy_notes(session)

    def run(session: CaseSession) -> object:
        if session.__dict__.get("agent_fell_back"):
            return policy(session)  # the agent stopped once on this case; code carries on
        try:
            from snapback.agent.graph import build_agent, run_case_with_agent

            agent = agents.get(session.case_id)
            if agent is None:
                agent = agents[session.case_id] = build_agent(session, make_model())
        except Exception:
            # The extra is not installed, there is no key, or the graph could not be built.
            session.__dict__["agent_fell_back"] = True
            session.trace.emit(
                TraceKind.ERROR, strings.text("trace.error.model_failed", session.lang)
            )
            return policy(session)
        return run_case_with_agent(session, agent, deadline_s=timeout_s)

    return run


class CaseStore:
    def __init__(
        self,
        settings: Settings,
        lookups: Lookups | None = None,
        live_locate: LiveLocate | None = None,
        agent_model: Callable[[], object] | None = None,
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
            _deepagents_runner(settings, agent_model)
            if settings.snapback_agent == "deepagents"
            else _policy_runner
        )
        # deepagents_async: the answer comes from the policy at once; the agent follows on its
        # own thread (see `_start_agent`), at most N at a time.
        self._agent_model = agent_model
        self._background: BackgroundAgents | None = None
        if settings.snapback_agent == "deepagents_async":
            _setup_langsmith(settings)
            self._background = BackgroundAgents(settings.snapback_agent_max_concurrent)
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

    def _search_text_for(self, case: SessionCase) -> Callable[[], str]:
        """The search sub-agent's source: the #195 planner over places near the checked ad, as
        text. The chooser is the model when the agent setting says so, else the code policy."""

        def search(use_model: bool = False) -> str:
            from snapback.agent.search_agent import agentic_alternatives, search_chooser_for

            response = agentic_alternatives(
                case,
                self._lookups,
                search_chooser_for(self._settings.snapback_agent if use_model else "policy"),
                3,
                case.preferences,
                self._settings.snapback_data_source,
            )
            return places_text(response)

        return search

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

    def _for_sale_by_position(
        self, text: str, record: PropertyRecord | None, by_text: ForSaleMatch | None
    ) -> ForSaleMatch | None:
        """The for-sale answer for a named home, also looked up by the record's position (#10).

        An ad with no street finds nothing by its text, while the home's own lat/lon does. The
        same rule as the identify path (`JoinedModules._adopt_identified`): a position lookup
        that finds nothing never undoes a listing the text lookup found."""
        at = getattr(self._lookups, "for_sale_at", None)
        if record is None or at is None or record.lat is None or record.lon is None:
            return by_text
        nearby = at(text, record.lat, record.lon)
        if nearby is None:
            return by_text
        if (
            by_text is not None
            and by_text.status is not ForSaleStatus.NONE
            and nearby.status is ForSaleStatus.NONE
        ):
            return by_text
        return nearby

    def create(
        self,
        listing: Listing,
        property_id: str | None = None,
        register: Callable[[str], None] | None = None,
        *,
        photos: list[bytes] | None = None,
        demo_case: str | None = None,
    ) -> SessionCase:
        """Start a check. `property_id` is our id for the building the listing claims, and
        `photos` are the listing photos as sent, in order. `demo_case` names one staged case
        (a replay's) for this request alone; without it the server's DEMO_CASE setting applies.

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

        demo_id = demo_case or self._settings.demo_case
        demo = load_demo_case(demo_id) if demo_id else None
        if demo is not None and not listing.text:
            # A staged case (fixtures/demo). With nothing pasted, its own listing is read.
            own = read_listing(demo.listing_text)
            listing = own.model_copy(
                update={"photos": listing.photos, "screenshots": listing.screenshots}
            )
        # A case asked for by name (a replay's "Run this case") always runs on its own
        # fixtures, on any server: it is a staged example, so it is never a LIVE card and
        # calls no lookup.
        asked_by_name = demo_case is not None
        for_sale = license = owner = None
        if not asked_by_name:
            for_sale = self._lookups.for_sale(listing.text) if listing.text else None
            for_sale = self._for_sale_by_position(listing.text, record, for_sale)
            # D10: only a live run calls the licence list, and a lookup that breaks is "not
            # looked up". It reads the poster's own claim in the text and keeps no name.
            license = license_of(self._lookups, listing.text)
            # D12: the owner of record of the home the listing claims, when lane D holds one.
            owner = owner_of(self._lookups, listing.text)

        live = not asked_by_name and (
            self._settings.snapback_data_source is DataSource.LIVE
            or (record is not None and record.source is DataSource.LIVE)
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
                    license=license,
                    owner=owner,
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
            session = CaseSession(
                full_id,
                modules,
                Trace(full_id, source),
                ask_enabled=self._settings.snapback_ask_renter,
            )
            if listing.truncated:
                session.trace.emit(TraceKind.STATUS, strings.text("trace.intake.truncated"))
            if listing.injection_spans:
                session.trace.emit(TraceKind.STATUS, strings.text("trace.intake.injection"))
            case = SessionCase(short_id, session, listing, self._runner, self._zone_of(record))
            session.search_places = self._search_text_for(case)
            case.staged = demo is not None
            case.demo_case_id = demo.case_id if demo is not None else None
            case.property_id = property_id  # the building the listing claims, if it named one
            self._cases[short_id] = case
        case.advance()
        self._start_agent(case)
        return case

    def _start_agent(self, case: SessionCase) -> None:
        """Queue the deep agent on this case, once (SNAPBACK_AGENT=deepagents_async). The request
        has its answer already and does not wait for this."""
        if self._background is None:
            return
        case.agents = self._background
        self._background.submit(
            case.case_id, _background_job(case, self._settings, self._agent_model)
        )

    def shutdown_agents(self) -> None:
        """Stop taking background runs and drop the queued ones (the app is shutting down)."""
        if self._background is not None:
            self._background.shutdown()

    def wait_for_agents(self, timeout: float = 30.0) -> None:
        """Block until every background run has ended. For tests and scripts, never a request."""
        if self._background is None:
            return
        for case in list(self._cases.values()):
            if isinstance(case, SessionCase):
                self._background.wait(case.case_id, timeout)
