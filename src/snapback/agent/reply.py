"""A14 (issue #109): the poster's reply, checked by real code on real bytes.

`ReplyModules` wraps whatever modules a case uses and replaces the canned challenge answer:

- when the case starts, the renter's listing photos are recorded in the photo memory (lane V,
  V5): hashes only, no pixels kept;
- when the renter approves the message, nothing is judged. The case waits for the reply;
- when the reply photo arrives, it is checked: is it a copy of one of the listing's own
  photos (photo memory), and is the code we asked for on it (local OCR, lane D's compare)?

What comes out, and what it means for the state:

    copy of a listing photo   forged, whenever it arrives, deadline or not. This is proof,
                              and the only thing here that is.
    code not on the photo     not confirmed; ask again, up to the retry cap, then HOLD. Never
                              "forged": the reader can miss handwriting, and a wrong "Don't
                              pay" is the worst mistake (ruling, Sat 02:45).
    code read, not a copy     not confirmed. Whether it was taken AT THE SPOT needs locate
                              (lane V, V2). Until a locator is given, nothing says "proven".
    too late, not a copy      not counted; ask again once (ruling, Sat 02:45). No dead end.

The spot and the code are the ones the session drew and the renter approved. Lane D's
`Challenge` keeps the state (spots, deadlines) and decides everything once a locator exists.
"""

import io
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from PIL import Image

from snapback.agent.intake.ocr import read_image
from snapback.agent.modules import ChallengeOutcome, Modules
from snapback.challenge import Challenge, Reply, new_code
from snapback.challenge.codes import compare
from snapback.challenge.engine import STEP_DEADLINE_S
from snapback.contracts import (
    ChallengeResult,
    MemoryHitKind,
    MemoryResult,
    PresenceStatus,
    ReplyCheck,
    SpotCandidate,
    SpotResult,
)
from snapback.vision.memory.store import PhotoMemory, PhotoRole

MAX_PIXELS = 40_000_000  # the same order as the OCR reader's cap

# Is the reply taken at the spot? (photo bytes, spot) -> (located, inliers). Lane V's, V2.
Locator = Callable[[bytes, SpotCandidate], tuple[bool, int | None]]


class UnreadablePhoto(ValueError):
    """The bytes are not a picture we can open, or it is too large."""


def _now() -> datetime:
    return datetime.now(UTC)


def open_photo(data: bytes) -> Image.Image:
    """The picture in `data`, held to a sane size before anything is decoded."""
    try:
        picture = Image.open(io.BytesIO(data))
        if picture.width * picture.height > MAX_PIXELS:
            raise UnreadablePhoto("the picture has too many pixels")
        picture.load()
    except UnreadablePhoto:
        raise
    except Exception:
        raise UnreadablePhoto("the file is not a picture we can open") from None
    return picture.convert("RGB")


class ReplyModules:
    """`inner`'s modules, with the challenge answered by the poster's real reply."""

    def __init__(
        self,
        inner: Modules,
        memory: PhotoMemory,
        *,
        ocr: Callable[[bytes], str] | None = None,
        locator: Locator | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._inner = inner
        self._memory = memory
        self._ocr = ocr
        self._locator = locator
        self._clock = clock
        self._challenge: Challenge | None = None
        self._spot: SpotCandidate | None = None
        self._replies = 0
        self._lock = threading.Lock()
        self.sent_messages: list[str] = []
        self.listing_photos = 0  # how many were recorded in the photo memory

    def __getattr__(self, name: str):
        # Everything that is not the challenge is the inner modules' business.
        return getattr(self._inner, name)

    # --- the listing's own photos ----------------------------------------------------------

    def remember_listing_photos(self, case_id: str, photos: list[bytes]) -> int:
        """Record each listing photo, in order, as l1, l2, ... A file we cannot open is skipped."""
        kept = 0
        for number, data in enumerate(photos, start=1):
            try:
                picture = open_photo(data)
            except UnreadablePhoto:
                continue
            self._memory.record(case_id, f"l{number}", picture, PhotoRole.LISTING)
            kept += 1
        self.listing_photos = kept
        return kept

    # --- the challenge ---------------------------------------------------------------------

    def new_code(self, case_id: str) -> str:
        return new_code()  # lane D's alphabet: nothing handwriting or OCR mixes up

    def challenge(
        self, case_id: str, spot: SpotCandidate, code: str, text: str, attempt: int
    ) -> ChallengeOutcome:
        """The renter approved `text`. Start waiting for the reply; judge nothing yet."""
        ranking = self._inner.spot_ranking(case_id, None)
        pool = [s for s in (ranking.spots if ranking else []) if not s.overlaps_listing_photo]
        with self._lock:
            self.sent_messages.append(text)
            self._spot = spot
            self._challenge = Challenge(
                case_id=case_id,
                challenge_id=f"ch-{case_id}-{attempt}",
                code=code,
                pool=pool,
                clock=self._clock,
                rng=None,  # type: ignore[arg-type]  # set below; the engine draws spot 2 with it
                spots=[
                    SpotResult(
                        spot_id=spot.spot_id,
                        step=1,
                        revealed_at=self._clock(),
                        deadline_s=STEP_DEADLINE_S[1],
                    )
                ],
            )
            import secrets

            self._challenge.rng = secrets.SystemRandom()
            return ChallengeOutcome(challenge=self._challenge.result(), awaiting_reply=True)

    def check_reply(self, case_id: str, photo: bytes) -> tuple[ReplyCheck, ChallengeOutcome]:
        """Check one reply photo. Raises `UnreadablePhoto` if it is not a picture."""
        picture = open_photo(photo)
        with self._lock:
            challenge = self._challenge
            if challenge is None or self._spot is None:
                raise RuntimeError("no challenge has been sent for this case")
            if challenge.closed or challenge.presence is not PresenceStatus.WAITING:
                return ReplyCheck.IGNORED, self._outcome(challenge.result(), [], waiting=False)

            now = self._clock()
            current = challenge.spots[-1]
            late = now > current.revealed_at + timedelta(seconds=current.deadline_s)

            self._replies += 1
            photo_id = f"r{self._replies}"
            memory = self._memory.check(case_id, photo_id, picture, PhotoRole.REPLY)

            # A copy of one of this case's listing photos. Proof, whatever else is on it and
            # whenever it arrives: this is checked before the deadline, as lane D's engine
            # does, so a late copy cannot leave the case on HOLD for good.
            if memory.hit is MemoryHitKind.SAME_CASE_LISTING:
                challenge.reply(Reply(photo_id=photo_id, ocr_text="", located=False, memory=memory))
                return (
                    ReplyCheck.COPY_OF_LISTING_PHOTO,
                    self._outcome(challenge.result(), [memory], waiting=False),
                )

            if late:
                # Too late to count, and not a copy. Nothing on it is judged, and the spot
                # is left unanswered. The session asks again once (decision 4, Sat 02:45).
                outcome = self._outcome(challenge.result(), [memory], waiting=False)
                return ReplyCheck.LATE, replace(outcome, late=True)

            ocr = self._ocr or read_image
            code_read, other_text = compare(challenge.code, ocr(photo))
            if not code_read:
                # Not forged: the reader can miss handwriting. Not confirmed, and ask again.
                result = self._answered(challenge, photo_id, now, code_read=False, located=None)
                return ReplyCheck.CODE_NOT_READ, self._outcome(result, [memory], waiting=False)

            if self._locator is None:
                # The code is there and it is not a copy. Nothing can say "at the spot" yet.
                result = self._answered(
                    challenge, photo_id, now, code_read=True, located=None, other_text=other_text
                )
                return (
                    ReplyCheck.CODE_READ_SPOT_NOT_CHECKED,
                    self._outcome(result, [memory], waiting=False),
                )

            # With a locator, lane D's engine decides everything, as it was written to.
            located, inliers = self._locator(photo, self._spot)
            before = len(challenge.spots)
            presence = challenge.reply(
                Reply(
                    photo_id=photo_id,
                    ocr_text=challenge.code,  # the code was read above; no other text passes on
                    located=located,
                    inliers=inliers,
                    memory=memory,
                )
            )
            if other_text:
                challenge.injection_text_seen = True
            if presence is PresenceStatus.PROVEN:
                check = ReplyCheck.PROVEN
            elif len(challenge.spots) > before:
                check = ReplyCheck.NEXT_SPOT
            else:
                check = ReplyCheck.ASK_AGAIN
            waiting = check is ReplyCheck.NEXT_SPOT
            return check, self._outcome(challenge.result(), [memory], waiting=waiting)

    # --- helpers ---------------------------------------------------------------------------

    def _answered(
        self,
        challenge: Challenge,
        photo_id: str,
        now: datetime,
        *,
        code_read: bool,
        located: bool | None,
        other_text: bool = False,
    ) -> ChallengeResult:
        """Record what the reply showed on the current spot. Presence stays WAITING."""
        challenge.spots[-1] = challenge.spots[-1].model_copy(
            update={
                "replied_at": now,
                "reply_photo_id": photo_id,
                "code_read": code_read,
                "located": located,
            }
        )
        if other_text:
            challenge.injection_text_seen = True
        return challenge.result()

    @staticmethod
    def _outcome(
        result: ChallengeResult, memory: list[MemoryResult], *, waiting: bool
    ) -> ChallengeOutcome:
        return ChallengeOutcome(challenge=result, memory=memory, awaiting_reply=waiting)
