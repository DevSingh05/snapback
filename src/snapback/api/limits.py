"""How many checks one client may start in a day.

A stand-in until the safety module (lane D, D5) lands with `check_limit(renter_id)`. It keeps
counts in memory, so they reset when the server restarts.

Taking a place and giving it back are separate steps, each one atomic. A request reserves its
place before the check starts, so two requests arriving together cannot both take the last
one, and releases it if the check could not start (bad upload, live mode not wired), so a
failure costs nobody their allowance.
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

    def reserve(self, key: str) -> bool:
        """Take one of today's places for `key`, if there is one. Check and count in one step."""
        slot = (key, self._today())
        with self._lock:
            used = self._counts.get(slot, 0)
            if used >= self.per_day:
                return False
            self._counts[slot] = used + 1
            return True

    def release(self, key: str) -> None:
        """Give back a place that was reserved for a check that did not start."""
        slot = (key, self._today())
        with self._lock:
            used = self._counts.get(slot, 0)
            if used > 0:
                self._counts[slot] = used - 1
