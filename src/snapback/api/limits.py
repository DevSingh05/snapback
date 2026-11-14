"""How many checks one client may start in a day.

A stand-in until the safety module (lane D, D5) lands with `check_limit(renter_id)`. It keeps
counts in memory, so they reset when the server restarts.

Checking and counting are separate on purpose: a check that could not start (bad upload, live
mode not wired) must not use up someone's allowance.
"""

import threading
from collections.abc import Callable
from datetime import UTC, date, datetime


def _today() -> date:
    return datetime.now(UTC).date()


class DailyLimit:
    def __init__(self, per_day: int, today: Callable[[], date] = _today) -> None:
        self.per_day = per_day
        self._today = today
        self._counts: dict[tuple[str, date], int] = {}
        self._lock = threading.Lock()

    def has_room(self, key: str) -> bool:
        with self._lock:
            return self._counts.get((key, self._today()), 0) < self.per_day

    def count(self, key: str) -> None:
        """Record one check that did start."""
        slot = (key, self._today())
        with self._lock:
            self._counts[slot] = self._counts.get(slot, 0) + 1
