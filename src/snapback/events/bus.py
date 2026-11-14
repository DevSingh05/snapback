"""The bus: number an event, append it to the log, tell whoever is listening.

One process, one bus. The log is a JSONL file under the data folder: one event per line,
only ever appended to, so what was said is still there after a restart. Numbers follow the
log's line count, so a number is never used twice, even if a line in the log is unreadable.
"""

import logging
import threading
from collections.abc import Callable, Iterable
from pathlib import Path

from snapback.events.models import Event, EventKind, EventRefused, checked

log = logging.getLogger(__name__)

Subscriber = Callable[[Event], None]


def _seq(event_id: str) -> int:
    try:
        return int(event_id.removeprefix("ev-"))
    except ValueError:
        return 0


def seq_of(event_id: str | None) -> int:
    """The number in an id like "ev-000002", or 0 for none or nonsense ("from the start")."""
    return _seq(event_id) if event_id else 0


class EventBus:
    def __init__(self, log_path: Path) -> None:
        self._path = Path(log_path)
        self._lock = threading.Lock()
        self._subscribers: list[tuple[Subscriber, frozenset[EventKind] | None]] = []
        self._events: list[Event] = []
        self._lines = 0
        if self._path.is_file():
            text = self._path.read_text(encoding="utf-8")
            if text and not text.endswith("\n"):
                # A crash can leave half a line. End it, so the next event starts its own.
                with self._path.open("a", encoding="utf-8") as out:
                    out.write("\n")
            for line in text.splitlines():
                self._lines += 1
                try:
                    self._events.append(Event.model_validate_json(line))
                except ValueError:
                    log.warning("event log: line %d could not be read and is skipped", self._lines)

    def publish(self, event: Event) -> Event:
        """Number the event, log it and tell the subscribers. Returns the numbered event."""
        if event.id:
            raise EventRefused("that event was already published")
        event = checked(event)  # however it was built, and whatever was changed since
        with self._lock:
            self._lines += 1
            kept = event.model_copy(update={"id": f"ev-{self._lines:06d}"})
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as out:
                out.write(kept.model_dump_json() + "\n")
            self._events.append(kept)
            listeners = list(self._subscribers)
        for listener, kinds in listeners:
            if kinds is None or kept.kind in kinds:
                try:
                    listener(kept)
                except Exception:  # one listener's failure is not the publisher's
                    log.exception("event subscriber failed on %s", kept.kind.value)
        return kept

    def subscribe(
        self, listener: Subscriber, kinds: Iterable[EventKind] | None = None
    ) -> Callable[[], None]:
        """Call `listener` for each event of `kinds` (all, if None). Returns how to stop."""
        entry = (listener, frozenset(kinds) if kinds is not None else None)
        with self._lock:
            self._subscribers.append(entry)

        def stop() -> None:
            with self._lock:
                if entry in self._subscribers:
                    self._subscribers.remove(entry)

        return stop

    def after(self, seq: int) -> list[Event]:
        """Every event numbered above `seq`, in order."""
        with self._lock:
            return [event for event in self._events if _seq(event.id) > seq]
