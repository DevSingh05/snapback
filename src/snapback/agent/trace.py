"""The agent's trace: one `TraceEvent` per choice, tool call, pause and verdict.

`seq` is handed out here and nowhere else, so it is strictly increasing per case. Listeners
(the SSE stream) are called with each event as it is emitted.
"""

import threading
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Literal

from snapback.contracts import ChoiceKind, DataSource, TraceEvent, TraceKind

MAX_REASON = 200

# A reason may be written by a model, and the trace is shown on screen. These words are the
# ones the product never uses about a listing or a person; a reason containing one is dropped
# in favour of the code-written fallback.
_BANNED_IN_REASONS = ("scam", "fraud", "safe", "verified", "legit")


def clean_reason(text: object, fallback: str) -> str:
    """One plain line, at most `MAX_REASON` characters, with none of the banned words."""
    line = " ".join(str(text or "").split())
    if not line or any(word in line.lower() for word in _BANNED_IN_REASONS):
        line = " ".join(fallback.split())
    if len(line) > MAX_REASON:
        line = line[: MAX_REASON - 1].rstrip() + "…"
    return line


def _now() -> datetime:
    return datetime.now(UTC)


class Trace:
    def __init__(
        self, case_id: str, source: DataSource, clock: Callable[[], datetime] = _now
    ) -> None:
        self.case_id = case_id
        self.source = source
        self.events: list[TraceEvent] = []
        self._clock = clock
        self._listeners: list[Callable[[TraceEvent], None]] = []
        self._lock = threading.Lock()

    def subscribe(self, listener: Callable[[TraceEvent], None]) -> None:
        self._listeners.append(listener)

    def emit(
        self,
        kind: TraceKind,
        reason: str,
        *,
        choice: ChoiceKind | None = None,
        options: Iterable[str] = (),
        pick: str | None = None,
        chosen_by: Literal["model", "policy"] = "policy",
    ) -> TraceEvent:
        with self._lock:
            event = TraceEvent(
                case_id=self.case_id,
                seq=len(self.events),
                at=self._clock(),
                kind=kind,
                choice=choice,
                options=list(options),
                pick=pick,
                reason=reason,
                source=self.source,
                chosen_by=chosen_by,
            )
            self.events.append(event)
        for listener in self._listeners:
            listener(event)
        return event
