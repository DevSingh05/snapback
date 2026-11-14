"""Who started which case (A11, issue #102).

Lane D's safety store (D5) keeps "this renter started these cases", and its delete command
removes everything those cases left behind. That only works if every case is registered when
it is made, which is what happens here.

A case is registered under the renter id the iMessage sidecar sent (`imsg-` and a keyed hash
of the thread, never a phone number). A browser has no renter id, so its cases go under
`browser:<its client cookie>`.

The same store answers "is this case still registered?". A case that lane D's delete removed
is no longer registered, and the API then drops it from memory instead of serving it until
the next restart.
"""

import threading
from pathlib import Path
from typing import Protocol

from snapback.safety import SafetyStore


class CaseRegistry(Protocol):
    def register_case(self, case_id: str, renter_id: str) -> None: ...

    def cases_of(self, renter_id: str) -> list[str]: ...


class SafetyRegistry:
    """Lane D's `SafetyStore`, opened the first time a case is made, not when the app starts."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._store: SafetyStore | None = None
        self._lock = threading.Lock()

    def _opened(self) -> SafetyStore:
        with self._lock:
            if self._store is None:
                self._store = SafetyStore(self._data_dir)
            return self._store

    def register_case(self, case_id: str, renter_id: str) -> None:
        self._opened().register_case(case_id, renter_id)

    def cases_of(self, renter_id: str) -> list[str]:
        return self._opened().cases_of(renter_id)
