"""Events: what happened to a place, a renter's session or the pipeline (M3, plan/map-plan.md).

`new_event` builds one and refuses anything its kind does not allow. `EventBus` numbers it,
appends it to a log and hands it to whoever is listening.
"""

from snapback.events.bus import EventBus
from snapback.events.models import (
    PAYLOAD_KEYS,
    Event,
    EventKind,
    EventRefused,
    EventSource,
    new_event,
)

__all__ = [
    "PAYLOAD_KEYS",
    "Event",
    "EventBus",
    "EventKind",
    "EventRefused",
    "EventSource",
    "new_event",
]
