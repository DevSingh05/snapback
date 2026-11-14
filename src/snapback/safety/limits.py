"""3 checks per renter per day, kept in data/ so a restart does not reset them.

Same split as the API's stand-in (`api/limits.DailyLimit`): asking never uses up an allowance;
`count` is called only for a check that did start.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from snapback.safety.store import SafetyStore
from snapback.settings import get_settings


def _today() -> date:
    return datetime.now(UTC).date()


class RenterLimits:
    def __init__(
        self, data_dir: Path, per_day: int = 3, today: Callable[[], date] = _today
    ) -> None:
        self.per_day = per_day
        self._today = today
        self._store = SafetyStore(data_dir)

    def check_limit(self, renter_id: str) -> bool:
        """True when this renter may start another check today."""
        return self._store.checks_on(renter_id, self._today().isoformat()) < self.per_day

    def has_room(self, renter_id: str) -> bool:
        """Drop-in name for `api/limits.DailyLimit.has_room`."""
        return self.check_limit(renter_id)

    def count(self, renter_id: str) -> None:
        self._store.add_check(renter_id, self._today().isoformat())


def check_limit(renter_id: str) -> bool:
    """For A4: the configured limit, stored under SNAPBACK_DATA_DIR."""
    settings = get_settings()
    limits = RenterLimits(settings.snapback_data_dir, settings.snapback_daily_limit)
    return limits.check_limit(renter_id)
