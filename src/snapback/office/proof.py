"""One-time links that confirm an office through its own website domain (fixture outbox).

A link goes to an address the renter was given by the poster, and only when that address is at
the office's official domain from CoStar's record (`snapback.office.domain`). Nothing here
sends anything: the "email" is a text file in a local outbox folder (AGENTS.md rule 8: humans
send outbound messages), and this module imports no mail or network client.

A token is 256 random bits, kept only as a SHA-256 hash, valid for 30 minutes, usable once, and
bound to one case and one domain. A new request for a case voids that case's earlier tokens.
Requests are limited per case. State is in memory, so a restart forgets pending links.
"""

import hashlib
import os
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

TOKEN_TTL_SECONDS = 30 * 60
REQUESTS_PER_WINDOW = 3
WINDOW_SECONDS = 15 * 60
MAX_PENDING = 5_000

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_-]")


class Outcome(StrEnum):
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    USED = "used"
    UNKNOWN = "unknown"


class RateLimited(Exception):
    """Too many link requests for one case in a short time."""


@dataclass
class Redeemed:
    outcome: Outcome
    case_id: str | None = None
    domain: str | None = None


@dataclass
class _Entry:
    case_id: str
    domain: str
    expires_at: float
    used: bool = False


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class OfficeProofs:
    def __init__(
        self,
        outbox_dir: Path,
        public_base_url: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._outbox = Path(outbox_dir)
        self._base = public_base_url.rstrip("/")
        self._clock = clock
        self._entries: dict[str, _Entry] = {}  # token hash -> entry
        self._by_case: dict[str, list[str]] = {}  # case id -> hashes, newest last
        self._requests: dict[str, list[float]] = {}  # case id -> request times
        self._lock = threading.Lock()
        self._count = 0

    def request(self, case_id: str, address: str, domain: str) -> Path:
        """Make a token for this case and write the message to the outbox.

        The caller has already checked that `address` is at `domain`. Raises `RateLimited`.
        Returns the outbox file. The token is in that file and nowhere else."""
        now = self._clock()
        token = secrets.token_urlsafe(32)
        with self._lock:
            recent = [t for t in self._requests.get(case_id, []) if now - t < WINDOW_SECONDS]
            if len(recent) >= REQUESTS_PER_WINDOW:
                self._requests[case_id] = recent
                raise RateLimited(case_id)
            self._requests[case_id] = [*recent, now]
            self._sweep(now)
            for old in self._by_case.get(case_id, []):
                self._entries.pop(old, None)  # one live token per case
            digest = _hash(token)
            self._entries[digest] = _Entry(case_id, domain, now + TOKEN_TTL_SECONDS)
            self._by_case[case_id] = [digest]
            self._count += 1
            number = self._count
        return self._write(case_id, number, address, domain, token)

    def redeem(self, token: str) -> Redeemed:
        """Use a token once. The first valid use confirms; every later use says it was used."""
        digest = _hash(token)
        with self._lock:
            entry = self._entries.get(digest)
            if entry is None:
                return Redeemed(Outcome.UNKNOWN)
            if entry.used:
                return Redeemed(Outcome.USED, entry.case_id, entry.domain)
            if self._clock() >= entry.expires_at:
                return Redeemed(Outcome.EXPIRED, entry.case_id, entry.domain)
            entry.used = True
            return Redeemed(Outcome.CONFIRMED, entry.case_id, entry.domain)

    def _sweep(self, now: float) -> None:
        """Forget long-dead tokens and quiet cases, and cap what is held."""
        stale = [h for h, e in self._entries.items() if now - e.expires_at > WINDOW_SECONDS]
        for digest in stale:
            self._entries.pop(digest, None)
        if len(self._entries) > MAX_PENDING:
            for digest in list(self._entries)[: len(self._entries) - MAX_PENDING]:
                self._entries.pop(digest, None)
        for case_id in [
            c for c, times in self._requests.items() if all(now - t > WINDOW_SECONDS for t in times)
        ]:
            self._requests.pop(case_id, None)
            self._by_case.pop(case_id, None)

    def _write(self, case_id: str, number: int, address: str, domain: str, token: str) -> Path:
        self._outbox.mkdir(parents=True, exist_ok=True)
        name = _SAFE_NAME.sub("_", case_id)[:40] or "case"
        path = self._outbox / f"{name}-{number:04d}.txt"
        body = (
            "FIXTURE OUTBOX: this message was not sent. A person would send it.\n"
            f"To: {address}\n"
            "Subject: Please confirm a listing at your property\n"
            "\n"
            f"Someone asked SNAPBACK to check a rental listing for a property whose website "
            f"on record is {domain}. If you work at that office and this listing is yours, "
            f"open this link within 30 minutes to confirm it. It works once.\n"
            f"{self._base}/confirm/{token}\n"
            "If you do not know this listing, ignore this message.\n"
        )
        # Created new, owner-only: the file holds a live link. Never overwritten.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(body)
        return path
