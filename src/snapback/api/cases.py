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
from typing import Literal

from pydantic import BaseModel

from snapback.agent import (
    CaseSession,
    FixtureModules,
    PolicyChooser,
    Trace,
    detect_scope,
    run_case,
)
from snapback.agent.modules import CODE_ALPHABET, FIXTURES_DIR
from snapback.card import strings
from snapback.contracts import (
    Card,
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


class LiveModeNotWired(Exception):
    """A case was asked for in live mode before the live modules exist."""


class ChallengeView(BaseModel):
    """The message the renter is asked to approve."""

    text: str
    spot_label: str
    code: str


class CaseStatus(BaseModel):
    """Where a case stands. Local to the API; the card and the trace are the shared contracts."""

    case_id: str
    source: DataSource
    status: Literal["running", "waiting_for_approval", "done"]
    state: VerdictState | None = None  # set once the case is done
    photos: int = 0
    challenge: ChallengeView | None = None


def public_id(case_id: str) -> str:
    """The short id people see: no fixture prefix, upper case."""
    return case_id.strip().upper().removeprefix(FIXTURE_ID_PREFIX.upper())


def _now() -> datetime:
    return datetime.now().astimezone()


class RecordedCase:
    done = True

    def __init__(self, case_id: str, card: Card, events: list[TraceEvent], photos: int) -> None:
        self.case_id = case_id
        self._card = card
        self._events = events
        self._photos = photos

    def events(self) -> list[TraceEvent]:
        return self._events

    def card(self, verify_base_url: str) -> Card:
        return self._card

    def status(self) -> CaseStatus:
        return CaseStatus(
            case_id=self.case_id,
            source=self._card.source,
            status="done",
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
        photos: int,
        runner: Callable[[CaseSession], object],
    ) -> None:
        self.case_id = case_id
        self.session = session
        self._photos = photos
        self._runner = runner
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

    def card(self, verify_base_url: str) -> Card:
        return build_card(
            self.session.evidence,
            checked_at=self._checked_at or _now(),
            verify_base_url=verify_base_url,
            lang=self.session.lang,
        )

    def status(self) -> CaseStatus:
        draft = self.session.pending_challenge
        if self.session.done:
            status = "done"
        elif self.session.waiting_for_approval:
            status = "waiting_for_approval"
        else:
            status = "running"
        return CaseStatus(
            case_id=self.case_id,
            source=self.session.trace.source,
            status=status,
            state=self.session.verdict.state if self.session.verdict else None,
            photos=self._photos,
            challenge=(
                ChallengeView(text=draft.text, spot_label=draft.spot_label, code=draft.code)
                if draft and status == "waiting_for_approval"
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
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
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
        photos = len(evidence.locate.photos) if evidence.locate else 0
        self._cases[public_id(card.case_id)] = RecordedCase(card.case_id, card, events, photos)

    def get(self, case_id: str) -> RecordedCase | SessionCase | None:
        return self._cases.get(public_id(case_id))

    def _new_id(self) -> str:
        while True:
            candidate = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
            if candidate not in self._cases:
                return candidate

    def create(self, listing_text: str, photos: int) -> SessionCase:
        if self._settings.snapback_data_source is not DataSource.FIXTURE:
            raise LiveModeNotWired
        with self._lock:
            short_id = self._new_id()
            full_id = f"{FIXTURE_ID_PREFIX}{short_id}"
            # The fixture modules stand in for the evidence. The kind of listing is still read
            # from the text that was posted, so an out-of-scope listing is treated as one.
            modules = FixtureModules(listing_scope=detect_scope(listing_text))
            session = CaseSession(full_id, modules, Trace(full_id, DataSource.FIXTURE))
            case = SessionCase(short_id, session, photos, self._runner)
            self._cases[short_id] = case
        case.advance()
        return case
