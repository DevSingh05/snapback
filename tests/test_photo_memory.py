"""Photo memory (V5): hashes of listing and reply photos, never pixels, kept for 7 days.

Every image here is drawn by the test itself from a seed, so no photo file is committed.
"""

import io
import sqlite3
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest
from PIL import Image

from snapback.contracts import MemoryHitKind
from snapback.vision.memory import (
    PhotoMemory,
    PhotoRole,
    dhash,
    hamming,
    phash,
)

T0 = datetime(2026, 11, 14, 1, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def room(seed: int, size: tuple[int, int] = (640, 480)) -> Image.Image:
    """A synthetic 'room': smooth light gradients plus a few hard-edged blocks, like walls,
    doors and furniture. Different seeds give images with unrelated structure."""
    rng = np.random.default_rng(seed)
    width, height = size
    y, x = np.mgrid[0:height, 0:width] / max(width, height)
    channels = []
    for _ in range(3):
        a, b, c = rng.uniform(-1, 1, 3)
        channels.append(120 + 60 * np.sin(3 * a * x + 2 * b * y + c))
    pixels = np.stack(channels, axis=-1)
    for _ in range(12):
        x0, y0 = rng.integers(0, width - 40), rng.integers(0, height - 40)
        w, h = rng.integers(30, width // 3), rng.integers(30, height // 3)
        pixels[y0 : y0 + h, x0 : x0 + w] = rng.uniform(0, 255, 3)
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB")


def jpeg(image: Image.Image, quality: int) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def center_crop(image: Image.Image, share: float) -> Image.Image:
    width, height = image.size
    w, h = int(width * share), int(height * share)
    left, top = (width - w) // 2, (height - h) // 2
    return image.crop((left, top, left + w, top + h))


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def memory(tmp_path, clock) -> PhotoMemory:
    return PhotoMemory(tmp_path / "memory.sqlite", clock=clock)


# --- the hashes ----------------------------------------------------------------------------


def test_hashes_are_64_bit_and_stable():
    image = room(1)
    assert 0 <= phash(image) < 2**64
    assert 0 <= dhash(image) < 2**64
    assert phash(image) == phash(room(1))


def test_reencode_and_resize_stay_close_and_other_rooms_stay_far():
    image = room(1)
    copy = jpeg(image.resize((320, 240)), quality=40)
    assert hamming(phash(image), phash(copy)) <= 6
    for seed in range(2, 12):
        assert hamming(phash(image), phash(room(seed))) > 16


# --- same case: the reply copies one of this case's listing photos -------------------------


def test_crop_of_listing_photo_hits_same_case_listing(memory):
    listing = {"fx-p1": room(1), "fx-p2": room(2), "fx-p3": room(3)}
    for photo_id, image in listing.items():
        memory.record("fx-case-a", photo_id, image, PhotoRole.LISTING)

    reply = jpeg(center_crop(room(2), 0.8), quality=60)
    result = memory.check("fx-case-a", "fx-reply-1", reply, PhotoRole.REPLY)

    assert result.hit is MemoryHitKind.SAME_CASE_LISTING
    assert result.matched_listing_photo_id == "fx-p2"
    assert result.photo_id == "fx-reply-1"
    assert result.method in {"phash", "dhash", "embedding"}
    assert result.first_seen_on is None


def test_listing_photo_inside_a_bigger_frame_hits_same_case_listing(memory):
    """A photo of a screen shows the listing photo with a border around it."""
    memory.record("fx-case-a", "fx-p1", room(1), PhotoRole.LISTING)
    framed = Image.new("RGB", (800, 600), (20, 20, 20))
    framed.paste(room(1), (80, 60))

    result = memory.check("fx-case-a", "fx-reply-1", framed, PhotoRole.REPLY)

    assert result.hit is MemoryHitKind.SAME_CASE_LISTING
    assert result.matched_listing_photo_id == "fx-p1"


def test_fresh_reply_is_no_hit(memory):
    memory.record("fx-case-a", "fx-p1", room(1), PhotoRole.LISTING)
    result = memory.check("fx-case-a", "fx-reply-1", room(50), PhotoRole.REPLY)
    assert result.hit is MemoryHitKind.NONE
    assert result.matched_listing_photo_id is None


def test_listing_photos_are_never_same_case_hits_against_each_other(memory):
    memory.record("fx-case-a", "fx-p1", room(1), PhotoRole.LISTING)
    result = memory.check("fx-case-a", "fx-p1-again", room(1), PhotoRole.LISTING)
    assert result.hit is MemoryHitKind.NONE


# --- other checks: a date, never which check -------------------------------------------------


def test_other_check_hit_has_date_not_case_id(memory, clock, tmp_path):
    memory.record("fx-case-a", "fx-p1", room(1), PhotoRole.LISTING)
    clock.now = T0 + timedelta(days=2)

    result = memory.check("fx-case-b", "fx-q1", jpeg(room(1), 50), PhotoRole.LISTING)

    assert result.hit is MemoryHitKind.OTHER_CHECK
    assert result.first_seen_on == date(2026, 11, 14)
    assert result.matched_listing_photo_id is None
    assert "fx-case-a" not in result.model_dump_json()
    assert "fx-p1" not in result.model_dump_json()


def test_case_ids_are_not_stored_in_the_clear(memory, tmp_path):
    memory.record("fx-case-secret", "fx-p1", room(1), PhotoRole.LISTING)
    dump = "\n".join(sqlite3.connect(tmp_path / "memory.sqlite").iterdump())
    assert "fx-case-secret" not in dump


def test_reply_reused_from_another_case_is_other_check(memory):
    memory.record("fx-case-a", "fx-p1", room(1), PhotoRole.LISTING)
    result = memory.check("fx-case-b", "fx-reply-1", room(1), PhotoRole.REPLY)
    assert result.hit is MemoryHitKind.OTHER_CHECK


def test_earliest_date_wins_when_seen_in_several_checks(memory, clock):
    memory.record("fx-case-a", "fx-p1", room(1), PhotoRole.LISTING)
    clock.now = T0 + timedelta(days=3)
    memory.record("fx-case-b", "fx-p1", room(1), PhotoRole.LISTING)
    clock.now = T0 + timedelta(days=4)
    result = memory.check("fx-case-c", "fx-p1", room(1), PhotoRole.LISTING)
    assert result.first_seen_on == date(2026, 11, 14)


def test_check_records_the_photo_for_later_checks(memory, clock):
    first = memory.check("fx-case-a", "fx-p1", room(1), PhotoRole.LISTING)
    assert first.hit is MemoryHitKind.NONE
    clock.now = T0 + timedelta(hours=1)
    later = memory.check("fx-case-b", "fx-q1", room(1), PhotoRole.LISTING)
    assert later.hit is MemoryHitKind.OTHER_CHECK


# --- retention ----------------------------------------------------------------------------


def test_ttl_expires_after_7_days(memory, clock, tmp_path):
    memory.record("fx-case-a", "fx-p1", room(1), PhotoRole.LISTING)

    clock.now = T0 + timedelta(days=7) - timedelta(seconds=1)
    assert memory.check("fx-case-b", "fx-q1", room(1), PhotoRole.LISTING).hit is (
        MemoryHitKind.OTHER_CHECK
    )

    clock.now = T0 + timedelta(days=14, seconds=1)
    assert memory.check("fx-case-c", "fx-r1", room(1), PhotoRole.LISTING).hit is (
        MemoryHitKind.NONE
    )
    memory.purge_expired()
    rows = sqlite3.connect(tmp_path / "memory.sqlite").execute("select count(*) from photos")
    assert rows.fetchone()[0] == 1  # only fx-r1, recorded just now


def test_delete_case_forgets_its_photos(memory):
    memory.record("fx-case-a", "fx-p1", room(1), PhotoRole.LISTING)
    memory.delete_case("fx-case-a")
    assert memory.check("fx-case-b", "fx-q1", room(1), PhotoRole.LISTING).hit is (
        MemoryHitKind.NONE
    )


def test_purge_removes_the_database_file(tmp_path, clock):
    path = tmp_path / "memory.sqlite"
    memory = PhotoMemory(path, clock=clock)
    memory.record("fx-case-a", "fx-p1", room(1), PhotoRole.LISTING)
    memory.purge()
    assert not path.exists()


def test_naive_clock_is_refused(tmp_path):
    memory = PhotoMemory(tmp_path / "m.sqlite", clock=lambda: datetime(2026, 11, 14))
    with pytest.raises(ValueError):
        memory.record("fx-case-a", "fx-p1", room(1), PhotoRole.LISTING)


# --- embedding lookup (DINOv2 in production, a stand-in here) --------------------------------


class FakeEmbedder:
    """Maps chosen images to chosen vectors, so the test controls what 'looks alike'."""

    def __init__(self) -> None:
        self.vectors: dict[int, np.ndarray] = {}

    def embed(self, image: Image.Image) -> np.ndarray:
        key = phash(image)
        for known, vector in self.vectors.items():
            if hamming(known, key) <= 16:
                return vector
        rng = np.random.default_rng(key % 2**32)
        return rng.normal(size=8)


def test_embedding_catches_what_the_hashes_miss(tmp_path, clock):
    embedder = FakeEmbedder()
    listing, reply = room(1), room(77)  # unrelated pixels, so no hash will match
    shared = np.ones(8)
    embedder.vectors[phash(listing)] = shared
    embedder.vectors[phash(reply)] = shared + 0.01

    memory = PhotoMemory(tmp_path / "m.sqlite", clock=clock, embedder=embedder)
    memory.record("fx-case-a", "fx-p1", listing, PhotoRole.LISTING)
    result = memory.check("fx-case-a", "fx-reply-1", reply, PhotoRole.REPLY)

    assert result.hit is MemoryHitKind.SAME_CASE_LISTING
    assert result.method == "embedding"
    assert result.matched_listing_photo_id == "fx-p1"
