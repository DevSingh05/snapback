"""How many checks one renter may start in a day.

A stand-in until the safety module (lane D, D5) lands with `check_limit(renter_id)`. It keeps
counts in memory, so they reset when the server restarts.
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

    def allow(self, renter_id: str) -> bool:
        """Count one check for this renter if they have one left today."""
        key = (renter_id, self._today())
        with self._lock:
            used = self._counts.get(key, 0)
            if used >= self.per_day:
                return False
            self._counts[key] = used + 1
            return True
