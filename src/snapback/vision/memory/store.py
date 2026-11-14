"""Photo memory: has this photo been seen before, in this case or in another check?

What is kept, per photo: a keyed hash of the case id (never the id itself), the photo's own
id, whether it was a listing or a reply photo, when it was seen, its perceptual hashes and,
when an embedder is set, its embedding. Never pixels. Rows older than the TTL (7 days) are
ignored on every lookup and deleted by `purge_expired`.

Answers come back as `MemoryResult`:

- SAME_CASE_LISTING: a reply photo matches one of this case's own listing photos. The listing
  photo's id is returned, because it belongs to this case.
- OTHER_CHECK: the photo matches one seen in a different check. Only the date it was first
  seen there is returned, never which check or which photo.
"""

import hashlib
import hmac
import secrets
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

from snapback.contracts import MemoryHitKind, MemoryResult
from snapback.vision.memory.hashes import (
    Fingerprint,
    HashPair,
    best_distance,
    fingerprint,
    prepare,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DB = REPO_ROOT / "data" / "memory" / "photo_memory.sqlite"
TTL = timedelta(days=7)

# Frozen with the thresholds version. A hash match needs both hashes close, because a false
# SAME_CASE_LISTING turns into "Don't pay". The eval harness (V6) measures these.
THRESHOLDS_VERSION = "memory-2026-11-14b"
PHASH_MAX = 10
DHASH_MAX = 14
COSINE_MIN = 0.92


class PhotoRole(StrEnum):
    LISTING = "listing"
    REPLY = "reply"


class Embedder(Protocol):
    def embed(self, image: Image.Image) -> np.ndarray:
        """One vector per image. It is normalised here, so any scale will do."""
        ...


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _Fingerprint:
    hashes: Fingerprint
    embedding: np.ndarray | None


# Stored hashes that stand for the whole photo, which a crop of a framed copy is compared with
# (with the stored photo's own trimmed regions, "trimmed0", "trimmed1", ...).
_WHOLE = frozenset({"full"})


@dataclass(frozen=True)
class _Stored:
    row: int
    same_case: bool
    photo_id: str
    role: PhotoRole
    seen_at: datetime
    hashes: list[HashPair]
    embedding: np.ndarray | None


@dataclass(frozen=True)
class _Match:
    method: str
    distance: float


_SCHEMA = """
create table if not exists photos (
    id integer primary key,
    case_key text not null,
    photo_id text not null,
    role text not null,
    seen_at text not null,
    embedding blob
);
create table if not exists hashes (
    photo integer not null references photos(id) on delete cascade,
    variant text not null,
    phash text not null,
    dhash text not null
);
create index if not exists photos_seen_at on photos(seen_at);
create index if not exists photos_case_key on photos(case_key);
"""


class PhotoMemory:
    def __init__(
        self,
        path: Path | str = DEFAULT_DB,
        *,
        clock: Callable[[], datetime] = _now,
        embedder: Embedder | None = None,
        ttl: timedelta = TTL,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._embedder = embedder
        self._ttl = ttl
        self._key = self._load_key()
        # One connection per call, so any thread may use this object (FastAPI runs sync routes
        # in a thread pool). The lock makes each check one read-then-write step in this process;
        # `begin immediate` does the same across processes.
        self._lock = threading.Lock()
        with self._transaction() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            db = sqlite3.connect(self.path, timeout=30)
            try:
                db.execute("pragma foreign_keys = on")
                # Deleted rows are overwritten on disk, not just unlinked (7-day TTL, delete).
                db.execute("pragma secure_delete = on")
                db.execute("begin immediate")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    # --- public -----------------------------------------------------------------------------

    def check(
        self, case_id: str, photo_id: str, image: Image.Image, role: PhotoRole
    ) -> MemoryResult:
        """Look the photo up, then remember it. Replies are checked against this case's own
        listing photos first; every photo is then checked against other checks."""
        now = self._time()
        fingerprint = self._fingerprint(image)
        with self._transaction() as db:
            self._delete_expired(db, now)
            stored = self._unexpired(db, case_id, now)
            result = self._lookup(fingerprint, stored, photo_id, role)
            self._store(db, case_id, photo_id, role, fingerprint, now)
        return result or MemoryResult(photo_id=photo_id, hit=MemoryHitKind.NONE, method="phash")

    def _lookup(
        self, fingerprint: "_Fingerprint", stored: list["_Stored"], photo_id: str, role: PhotoRole
    ) -> MemoryResult | None:
        result = None
        if role is PhotoRole.REPLY:
            own = [s for s in stored if s.same_case and s.role is PhotoRole.LISTING]
            best = self._best(fingerprint, own)
            if best is not None:
                photo, match = best
                result = MemoryResult(
                    photo_id=photo_id,
                    hit=MemoryHitKind.SAME_CASE_LISTING,
                    method=match.method,
                    distance=match.distance,
                    matched_listing_photo_id=photo.photo_id,
                )

        if result is None:
            others = [s for s in stored if not s.same_case]
            hits = [(s, m) for s in others if (m := self._match(fingerprint, s)) is not None]
            if hits:
                first = min(hits, key=lambda hit: hit[0].seen_at)
                closest = min(hits, key=lambda hit: hit[1].distance)
                result = MemoryResult(
                    photo_id=photo_id,
                    hit=MemoryHitKind.OTHER_CHECK,
                    method=closest[1].method,
                    distance=closest[1].distance,
                    first_seen_on=first[0].seen_at.date(),
                )

        return result

    def record(self, case_id: str, photo_id: str, image: Image.Image, role: PhotoRole) -> None:
        """Remember a photo without looking it up."""
        now = self._time()
        fingerprint = self._fingerprint(image)
        with self._transaction() as db:
            self._delete_expired(db, now)
            self._store(db, case_id, photo_id, role, fingerprint, now)

    def delete_case(self, case_id: str) -> None:
        with self._transaction() as db:
            db.execute("delete from photos where case_key = ?", (self._case_key(case_id),))

    def purge_expired(self) -> int:
        with self._transaction() as db:
            return self._delete_expired(db, self._time())

    def purge(self) -> None:
        """Delete everything, file and key included (`make purge`, after judging)."""
        with self._lock:
            for path in (self.path, self._key_path):
                path.unlink(missing_ok=True)

    def close(self) -> None:
        """Nothing to close: every call opens and closes its own connection."""

    # --- internals --------------------------------------------------------------------------

    @property
    def _key_path(self) -> Path:
        return self.path.with_suffix(".key")

    def _load_key(self) -> bytes:
        if self._key_path.exists():
            return self._key_path.read_bytes()
        key = secrets.token_bytes(32)
        self._key_path.write_bytes(key)
        self._key_path.chmod(0o600)
        return key

    def _case_key(self, case_id: str) -> str:
        return hmac.new(self._key, case_id.encode(), hashlib.sha256).hexdigest()

    def _time(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError(f"the memory clock must carry a timezone, got {now!r}")
        return now.astimezone(UTC)

    def _delete_expired(self, db: sqlite3.Connection, now: datetime) -> int:
        cutoff = (now - self._ttl).isoformat()
        return db.execute("delete from photos where seen_at < ?", (cutoff,)).rowcount

    def _fingerprint(self, image: Image.Image) -> _Fingerprint:
        image = prepare(image)
        embedding = None
        if self._embedder is not None:
            vector = np.asarray(self._embedder.embed(image), dtype=np.float32).flatten()
            norm = float(np.linalg.norm(vector))
            embedding = vector / norm if norm else vector
        return _Fingerprint(fingerprint(image), embedding)

    def _store(
        self,
        db: sqlite3.Connection,
        case_id: str,
        photo_id: str,
        role: PhotoRole,
        fingerprint: _Fingerprint,
        now: datetime,
    ) -> None:
        blob = None if fingerprint.embedding is None else fingerprint.embedding.tobytes()
        cursor = db.execute(
            "insert into photos (case_key, photo_id, role, seen_at, embedding)"
            " values (?, ?, ?, ?, ?)",
            (self._case_key(case_id), photo_id, role.value, now.isoformat(), blob),
        )
        db.executemany(
            "insert into hashes (photo, variant, phash, dhash) values (?, ?, ?, ?)",
            [
                (cursor.lastrowid, pair.variant, f"{pair.phash:016x}", f"{pair.dhash:016x}")
                for pair in fingerprint.hashes.all()
            ],
        )

    def _unexpired(self, db: sqlite3.Connection, case_id: str, now: datetime) -> list[_Stored]:
        cutoff = (now - self._ttl).isoformat()
        key = self._case_key(case_id)
        photos = db.execute(
            "select id, case_key, photo_id, role, seen_at, embedding from photos"
            " where seen_at >= ? order by id",
            (cutoff,),
        ).fetchall()
        hashes: dict[int, list[HashPair]] = {}
        for photo, variant, ph, dh in db.execute(
            "select h.photo, h.variant, h.phash, h.dhash from hashes h"
            " join photos p on p.id = h.photo where p.seen_at >= ? order by h.rowid",
            (cutoff,),
        ):
            hashes.setdefault(photo, []).append(HashPair(variant, int(ph, 16), int(dh, 16)))
        return [
            _Stored(
                row=row,
                same_case=case_key == key,
                photo_id=photo_id,
                role=PhotoRole(role),
                seen_at=datetime.fromisoformat(seen_at),
                hashes=hashes.get(row, []),
                embedding=None if blob is None else np.frombuffer(blob, dtype=np.float32),
            )
            for row, case_key, photo_id, role, seen_at, blob in photos
        ]

    def _match(self, fingerprint: _Fingerprint, stored: _Stored) -> _Match | None:
        """Closest agreement between the two photos, or None if nothing is close enough.

        The new photo's probes (itself, mirrored, trimmed) are compared with every stored hash
        (a crop, screenshot or mirror of the stored photo), and every crop of the new photo with
        the stored photo as a whole (the stored photo shown inside a bigger frame).
        """
        if not stored.hashes:
            return None
        whole = [
            pair
            for pair in stored.hashes
            if pair.variant in _WHOLE
            or (pair.variant.startswith("trimmed") and "-" not in pair.variant)
        ]
        found = [
            best_distance(fingerprint.hashes.probes, stored.hashes, PHASH_MAX, DHASH_MAX),
            best_distance(fingerprint.hashes.crops[1:], whole, PHASH_MAX, DHASH_MAX),
        ]
        distances = [d for d in found if d is not None]
        if distances:
            return _Match("phash", float(min(distances)))

        a, b = fingerprint.embedding, stored.embedding
        if a is not None and b is not None and a.shape == b.shape:
            cosine = float(np.dot(a, b))
            if cosine >= COSINE_MIN:
                return _Match("embedding", round(1.0 - cosine, 6))
        return None

    def _best(
        self, fingerprint: _Fingerprint, candidates: list[_Stored]
    ) -> tuple[_Stored, _Match] | None:
        hits = [(s, m) for s in candidates if (m := self._match(fingerprint, s)) is not None]
        if not hits:
            return None
        # Hash matches outrank embedding matches; within a method, the closest wins.
        return min(hits, key=lambda hit: (hit[1].method != "phash", hit[1].distance))
