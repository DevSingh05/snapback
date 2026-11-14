"""The event, and what one may carry.

An event is small on purpose. Its subject is one of our own ids (a place, a session, a case),
never an address. Its payload holds only the keys its kind lists below, and only short plain
values, so an event cannot become a way for a record, a name or a renter's words to leave.

The kit is a snapshot: nothing in it changes while we run. So an event that says a record
changed is always SIMULATED, and no event says a place is "available now".
"""

import math
import re
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EventSource(StrEnum):
    RENTER = "renter"  # something the renter did in their session
    PIPELINE = "pipeline"  # something our own code did: an index warmed, a case made
    SIMULATED = "simulated"  # a scripted event for the demo; never a real change


class EventKind(StrEnum):
    SESSION_STARTED = "session_started"
    WATCH_ADDED = "watch_added"
    MATCH_FOUND = "match_found"
    PLACE_RECORD_CHANGED = "place_record_changed"
    INDEX_WARMED = "index_warmed"
    CASE_CREATED = "case_created"
    AERIAL_CACHED = "aerial_cached"


# The keys a payload may carry, per kind. Anything else is refused, not dropped: a caller
# that sends a key we did not plan for has a bug, and silence would hide it.
PAYLOAD_KEYS: dict[EventKind, frozenset[str]] = {
    EventKind.SESSION_STARTED: frozenset({"lang"}),
    EventKind.WATCH_ADDED: frozenset({"session", "kind"}),
    EventKind.MATCH_FOUND: frozenset({"session", "fits_brief", "rent_from", "has_scan"}),
    EventKind.PLACE_RECORD_CHANGED: frozenset({"field"}),
    EventKind.INDEX_WARMED: frozenset({"twins", "views"}),
    EventKind.CASE_CREATED: frozenset({"data_source"}),
    EventKind.AERIAL_CACHED: frozenset({"direction"}),
}

# A change to a record can only ever be scripted: the kit does not change under us.
ONLY_SIMULATED = frozenset({EventKind.PLACE_RECORD_CHANGED})

MAX_TEXT = 200
_SUBJECT = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
_AVAILABLE_NOW = re.compile(r"\bavailable\b[\s\w]{0,12}\bnow\b", re.IGNORECASE)


class EventRefused(ValueError):
    """The event would carry, or claim, something an event must not."""


class Event(BaseModel):
    id: str = ""  # "ev-000001", given by the bus when it is published
    kind: EventKind
    at: datetime
    source: EventSource
    subject: str  # one of our ids: a place, a session or a case. Never an address.
    payload: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


def _plain(value: object) -> bool:
    if value is None or isinstance(value, (bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, str) and len(value) <= MAX_TEXT


def new_event(
    *,
    kind: EventKind,
    source: EventSource,
    subject: str,
    payload: dict[str, object] | None = None,
    at: datetime | None = None,
) -> Event:
    """An event that is safe to log and to stream, or `EventRefused` saying why not."""
    kind, source = EventKind(kind), EventSource(source)
    payload = dict(payload or {})
    if kind in ONLY_SIMULATED and source is not EventSource.SIMULATED:
        raise EventRefused(f"{kind.value} can only be simulated: the kit is a snapshot")
    if not isinstance(subject, str) or not _SUBJECT.fullmatch(subject):
        raise EventRefused("the subject must be one of our short ids")
    extra = sorted(set(payload) - PAYLOAD_KEYS[kind])
    if extra:
        raise EventRefused(f"{kind.value} may not carry: {', '.join(extra)}")
    for key, value in payload.items():
        if not _plain(value):
            raise EventRefused(f"{kind.value}.{key} must be a short plain value")
        if isinstance(value, str) and _AVAILABLE_NOW.search(value):
            raise EventRefused("an event never says a place is available now")
    return Event(
        kind=kind,
        at=at or datetime.now(UTC),
        source=source,
        subject=subject,
        payload=payload,  # type: ignore[arg-type]
    )
