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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

from snapback.contracts import MemoryHitKind, MemoryResult
from snapback.vision.memory.hashes import HashPair, hamming, variants

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DB = REPO_ROOT / "data" / "memory" / "photo_memory.sqlite"
TTL = timedelta(days=7)

# Frozen with the thresholds version. A hash match needs both hashes close, because a false
# SAME_CASE_LISTING turns into "Don't pay". The eval harness (V6) measures these.
THRESHOLDS_VERSION = "memory-2026-11-14a"
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
    hashes: list[HashPair]
    embedding: np.ndarray | None

    @property
    def full(self) -> HashPair:
        return self.hashes[0]


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
        self._db = sqlite3.connect(self.path)
        self._db.execute("pragma foreign_keys = on")
        self._db.executescript(_SCHEMA)

    # --- public -----------------------------------------------------------------------------

    def check(
        self, case_id: str, photo_id: str, image: Image.Image, role: PhotoRole
    ) -> MemoryResult:
        """Look the photo up, then remember it. Replies are checked against this case's own
        listing photos first; every photo is then checked against other checks."""
        now = self._time()
        fingerprint = self._fingerprint(image)
        stored = self._unexpired(case_id, now)

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

        self._store(case_id, photo_id, role, fingerprint, now)
        return result or MemoryResult(photo_id=photo_id, hit=MemoryHitKind.NONE, method="phash")

    def record(self, case_id: str, photo_id: str, image: Image.Image, role: PhotoRole) -> None:
        """Remember a photo without looking it up."""
        self._store(case_id, photo_id, role, self._fingerprint(image), self._time())

    def delete_case(self, case_id: str) -> None:
        with self._db:
            self._db.execute("delete from photos where case_key = ?", (self._case_key(case_id),))

    def purge_expired(self) -> int:
        cutoff = (self._time() - self._ttl).isoformat()
        with self._db:
            cursor = self._db.execute("delete from photos where seen_at < ?", (cutoff,))
        return cursor.rowcount

    def purge(self) -> None:
        """Delete everything, file and key included (`make purge`, after judging)."""
        self._db.close()
        for path in (self.path, self._key_path):
            path.unlink(missing_ok=True)

    def close(self) -> None:
        self._db.close()

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

    def _fingerprint(self, image: Image.Image) -> _Fingerprint:
        embedding = None
        if self._embedder is not None:
            vector = np.asarray(self._embedder.embed(image), dtype=np.float32).flatten()
            norm = float(np.linalg.norm(vector))
            embedding = vector / norm if norm else vector
        return _Fingerprint(variants(image), embedding)

    def _store(
        self,
        case_id: str,
        photo_id: str,
        role: PhotoRole,
        fingerprint: _Fingerprint,
        now: datetime,
    ) -> None:
        blob = None if fingerprint.embedding is None else fingerprint.embedding.tobytes()
        with self._db:
            cursor = self._db.execute(
                "insert into photos (case_key, photo_id, role, seen_at, embedding)"
                " values (?, ?, ?, ?, ?)",
                (self._case_key(case_id), photo_id, role.value, now.isoformat(), blob),
            )
            self._db.executemany(
                "insert into hashes (photo, variant, phash, dhash) values (?, ?, ?, ?)",
                [
                    (cursor.lastrowid, pair.variant, f"{pair.phash:016x}", f"{pair.dhash:016x}")
                    for pair in fingerprint.hashes
                ],
            )

    def _unexpired(self, case_id: str, now: datetime) -> list[_Stored]:
        cutoff = (now - self._ttl).isoformat()
        key = self._case_key(case_id)
        photos = self._db.execute(
            "select id, case_key, photo_id, role, seen_at, embedding from photos"
            " where seen_at >= ? order by id",
            (cutoff,),
        ).fetchall()
        hashes: dict[int, list[HashPair]] = {}
        for photo, variant, ph, dh in self._db.execute(
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

        The new photo's own hashes are compared with every stored crop (a cropped copy), and
        every crop of the new photo with the stored photo's own hashes (a framed copy).
        """
        if not stored.hashes:
            return None
        pairs = [(fingerprint.full, crop) for crop in stored.hashes]
        pairs += [(crop, stored.hashes[0]) for crop in fingerprint.hashes[1:]]
        best = None
        for a, b in pairs:
            p, d = hamming(a.phash, b.phash), hamming(a.dhash, b.dhash)
            if p <= PHASH_MAX and d <= DHASH_MAX and (best is None or p < best):
                best = p
        if best is not None:
            return _Match("phash", float(best))

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
