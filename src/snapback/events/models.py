"""The event, and what one may carry.

An event is small on purpose. Its subject is one of our own ids (a place, a session, a case),
never an address. Its payload holds only the keys its kind lists below, and only short plain
values, so an event cannot become a way for a record, a name or a renter's words to leave.

The kit is a snapshot: nothing in it changes while we run. So an event that says a record
changed is always SIMULATED. No value is free text, so no event can say a place is
"available now", or anything else we did not plan for.
"""

import re
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


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
    # M9: what the renter did in the finder. Attributes of the place only, never which place.
    PLACE_PICKED = "place_picked"
    PLACE_PASSED = "place_passed"
    BRIEF_CHANGED = "brief_changed"


# What each payload key may hold. A key is never free text: it is one of a few words, a
# number, a yes or no, or one of our own ids. That is what keeps an address, a phone number
# or a renter's words out of an event, whoever builds it.
_ID = re.compile(r"(?=.*[A-Za-z])[A-Za-z0-9_.:-]{1,80}")  # one of our ids: never only digits


def _one_of(*words: str):
    return lambda value: isinstance(value, str) and value in words


def _is_id(value: object) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _is_bool(value: object) -> bool:
    return isinstance(value, bool)


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10_000_000


VALUE_RULES = {
    "lang": _one_of("en", "es"),
    "session": _is_id,
    "kind": _one_of("place", "brief"),
    "fits_brief": _is_bool,
    "has_scan": _is_bool,
    "rent_from": _is_count,
    "field": _one_of("rent_from", "units_reported", "n_plans", "has_scan"),
    "twins": _is_count,
    "views": _is_count,
    "data_source": _one_of("fixture", "live"),
    "direction": _one_of("north", "east", "south", "west", "nadir"),
    "place_kind": _one_of("apartment", "house"),
    "walkup": _is_bool,
    "parking": _is_bool,
    "brief_field": _one_of("budget", "beds", "parking", "no_walkup", "pets"),
    "rent_max": _is_count,
}

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
    EventKind.PLACE_PICKED: frozenset(
        {"session", "place_kind", "has_scan", "rent_from", "walkup", "parking"}
    ),
    EventKind.PLACE_PASSED: frozenset(
        {"session", "place_kind", "has_scan", "rent_from", "walkup", "parking"}
    ),
    EventKind.BRIEF_CHANGED: frozenset({"session", "brief_field", "rent_max"}),
}

# A change to a record can only ever be scripted: the kit does not change under us.
ONLY_SIMULATED = frozenset({EventKind.PLACE_RECORD_CHANGED})


class EventRefused(ValueError):
    """The event would carry, or claim, something an event must not."""


class Event(BaseModel):
    """Checked however it is made: by `new_event`, by hand, or read back from a line of JSON."""

    id: str = ""  # "ev-000001", given by the bus when it is published
    kind: EventKind
    at: datetime
    source: EventSource
    subject: str  # one of our ids: a place, a session or a case. Never an address.
    payload: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _carries_only_what_it_may(self) -> "Event":
        if self.kind in ONLY_SIMULATED and self.source is not EventSource.SIMULATED:
            raise EventRefused(f"{self.kind.value} can only be simulated: the kit is a snapshot")
        if not _is_id(self.subject):
            raise EventRefused("the subject must be one of our short ids")
        extra = sorted(set(self.payload) - PAYLOAD_KEYS[self.kind])
        if extra:
            raise EventRefused(f"{self.kind.value} may not carry: {', '.join(extra)}")
        for key, value in self.payload.items():
            if not VALUE_RULES[key](value):
                raise EventRefused(f"{self.kind.value}.{key} holds a value it may not")
        return self


def new_event(
    *,
    kind: EventKind,
    source: EventSource,
    subject: str,
    payload: dict[str, object] | None = None,
    at: datetime | None = None,
) -> Event:
    """An event that is safe to log and to stream, or `EventRefused` saying why not."""
    try:
        return Event(
            kind=kind,
            at=at or datetime.now(UTC),
            source=source,
            subject=subject,
            payload=dict(payload or {}),  # type: ignore[arg-type]
        )
    except ValueError as error:  # pydantic wraps the refusal; callers get the one type
        raise EventRefused(str(error)) from None


def checked(event: Event) -> Event:
    """The same event, checked again. A payload can be changed after an event is built."""
    try:
        return Event.model_validate(event.model_dump())
    except ValueError as error:
        raise EventRefused(str(error)) from None
