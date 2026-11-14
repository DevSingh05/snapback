"""Who started which case (A11, issue #102).

Lane D's safety store (D5) keeps "this renter started these cases", and its delete command
removes everything those cases left behind. That only works if every case is registered when
it is made, which is what happens here.

A case is registered under the renter id the iMessage sidecar sent (a keyed hash of the
thread, never a phone number). A browser has no renter id, so its cases go under
`browser:<its client cookie>`.
"""

import threading
from pathlib import Path
from typing import Protocol


class CaseRegistry(Protocol):
    def register_case(self, case_id: str, renter_id: str) -> None: ...


class SafetyRegistry:
    """Lane D's `SafetyStore`, opened the first time a case is made, not when the app starts."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._store: CaseRegistry | None = None
        self._missing = False
        self._lock = threading.Lock()

    def register_case(self, case_id: str, renter_id: str) -> None:
        with self._lock:
            if self._store is None and not self._missing:
                try:
                    from snapback.safety import SafetyStore
                except ImportError:
                    # Lane D's store is not on this branch yet. There is nothing to register
                    # with, and nothing that would later look.
                    self._missing = True
                else:
                    self._store = SafetyStore(self._data_dir)
            store = self._store
        if store is not None:
            store.register_case(case_id, renter_id)
