"""Background agent runs (SNAPBACK_AGENT=deepagents_async): at most N at once, never on a request.

The answer to a renter comes from the code policy at once. The deep agent then works the same
case on one of these threads, so it never holds a request, and the rest wait their turn when more
than N cases arrive together. Each job bounds itself (the agent's own time limit); this class
counts and queues, and backs the job's own limit with two more: a case that waits too long for a
worker, and a job still running long past its limit, are both given up on and reported through
`on_expire`, so `running()` turns false and no screen waits on them forever. It imports nothing
heavy, so it works without the `agent` extra.
"""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

log = logging.getLogger(__name__)


BUSY = "busy"  # on_expire reason: it never got a worker in time
STUCK = "stuck"  # on_expire reason: it got one and did not end in time


class BackgroundAgents:
    def __init__(self, max_concurrent: int = 2) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, max_concurrent), thread_name_prefix="agent-bg"
        )
        self._jobs: dict[str, Future[None]] = {}
        self._begun: set[str] = set()
        self._given_up: set[str] = set()
        self._lock = threading.Lock()

    def submit(
        self,
        key: str,
        job: Callable[[], None],
        *,
        max_wait_s: float | None = None,
        max_run_s: float | None = None,
        on_expire: Callable[[str], None] | None = None,
    ) -> bool:
        """Queue `job` for `key`. A key runs once: a second submit is ignored (returns False).

        `max_wait_s`: give up if no worker has taken the job by then. `max_run_s`: give up if the
        job is still running that long after a worker took it. Giving up marks the key finished
        for `running()` and calls `on_expire(BUSY | STUCK)` once; a job that was never started
        never starts."""
        with self._lock:
            if key in self._jobs:
                return False

            def begin() -> None:
                with self._lock:
                    if key in self._given_up:
                        return
                    self._begun.add(key)
                if max_run_s is not None:
                    self._after(max_run_s, lambda: self._give_up(key, STUCK, on_expire))
                self._guard(key, job)

            self._jobs[key] = self._pool.submit(begin)
            if max_wait_s is not None:
                self._after(max_wait_s, lambda: self._give_up(key, BUSY, on_expire))
            return True

    @staticmethod
    def _after(seconds: float, call: Callable[[], None]) -> None:
        timer = threading.Timer(seconds, call)
        timer.daemon = True
        timer.start()

    def _give_up(self, key: str, why: str, on_expire: Callable[[str], None] | None) -> None:
        with self._lock:
            job = self._jobs.get(key)
            if job is None or job.done() or key in self._given_up:
                return
            if why == BUSY and key in self._begun:
                return  # it got its worker in time
            self._given_up.add(key)
            job.cancel()  # a no-op once running; the job then stays out of `running()`
        if on_expire is not None:
            try:
                on_expire(why)
            except Exception:
                log.exception("background agent expiry failed for %s", key)

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
        return job is not None and not job.done() and key not in self._given_up

    def wait(self, key: str, timeout: float | None = None) -> None:
        """Block until the job for `key` has ended or been given up on (tests and scripts; never
        a request)."""
        job = self._jobs.get(key)
        if job is None:
            return
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.running(key):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(key)
            time.sleep(0.01)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
