"""Background agent runs (SNAPBACK_AGENT=deepagents_async): at most N at once, never on a request.

The answer to a renter comes from the code policy at once. The deep agent then works the same
case on one of these threads, so it never holds a request, and the rest wait their turn when more
than N cases arrive together. Each job bounds itself (the agent's own time limit); this class
only counts, queues and reports. It imports nothing heavy, so it works without the `agent` extra.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

log = logging.getLogger(__name__)


class BackgroundAgents:
    def __init__(self, max_concurrent: int = 2) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, max_concurrent), thread_name_prefix="agent-bg"
        )
        self._jobs: dict[str, Future[None]] = {}
        self._lock = threading.Lock()

    def submit(self, key: str, job: Callable[[], None]) -> bool:
        """Queue `job` for `key`. A key runs once: a second submit is ignored (returns False)."""
        with self._lock:
            if key in self._jobs:
                return False
            self._jobs[key] = self._pool.submit(self._guard, key, job)
            return True

    @staticmethod
    def _guard(key: str, job: Callable[[], None]) -> None:
        try:
            job()
        except Exception:  # a job must never take the pool down; the job reports its own failure
            log.exception("background agent job failed for %s", key)

    def started(self, key: str) -> bool:
        return key in self._jobs

    def running(self, key: str) -> bool:
        """Queued or working: the agent has not finished (or failed) on this case yet."""
        job = self._jobs.get(key)
        return job is not None and not job.done()

    def wait(self, key: str, timeout: float | None = None) -> None:
        """Block until the job for `key` has ended (tests and scripts; never a request)."""
        job = self._jobs.get(key)
        if job is not None:
            job.result(timeout)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
