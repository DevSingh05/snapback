"""Two-step presence challenge (spec v3.1 section 2).

Step 1: a fresh code and one spot, drawn at random from the top 5 eligible spots of lane V's
ranking, revealed at send with 10 minutes to reply. Step 2: a second spot is drawn and revealed
only after spot 1 matches, with 90 seconds. The short second window is what makes a pre-staged
photo useless.

Outcomes (verdict.py reads only `presence`):
- PROVEN: both spots matched in time with the code read.
- FORGED: the code is wrong or missing, or the reply copies a listing photo of this case (even
  when late). That is what produces "Don't pay · could not verify".
- WAITING: everything else, including no reply at all and late replies. An honest landlord gets
  time; silence is HOLD, never failure. A recapture flag only blocks the pass (ask again); it
  never accuses on its own, matching `verdict.presence_of`.

Text on the paper other than the code is logged as an injection event and ignored. The log keeps
the event, never the text.
"""

from __future__ import annotations

import random
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from snapback.challenge.codes import compare, new_code
from snapback.contracts import (
    ChallengeResult,
    MemoryHitKind,
    MemoryResult,
    PresenceStatus,
    RecaptureResult,
    SpotCandidate,
    SpotRanking,
    SpotResult,
)

STEP_DEADLINE_S = {1: 600, 2: 90}
TOP_N = 5
MAX_RETRIES = 2

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Reply:
    """One reply photo, already checked locally by OCR, locate, recapture and memory."""

    photo_id: str
    ocr_text: str
    located: bool  # placed at the current spot in the twin
    inliers: int | None = None
    recapture: RecaptureResult | None = None
    memory: MemoryResult | None = None


@dataclass(frozen=True)
class LogEvent:
    kind: str  # "injection_text", "late_reply", "retry", "recapture_block", "ignored"
    at: datetime
    spot_id: str
    photo_id: str


@dataclass
class Challenge:
    case_id: str
    challenge_id: str
    code: str
    pool: list[SpotCandidate]
    clock: Clock
    rng: random.Random | secrets.SystemRandom
    spots: list[SpotResult] = field(default_factory=list)
    presence: PresenceStatus = PresenceStatus.WAITING
    retries: int = 0
    injection_text_seen: bool = False
    log: list[LogEvent] = field(default_factory=list)

    @classmethod
    def start(
        cls,
        case_id: str,
        ranking: SpotRanking,
        clock: Clock = _utc_now,
        rng: random.Random | None = None,
    ) -> Challenge:
        pool = [s for s in ranking.spots if not s.overlaps_listing_photo][:TOP_N]
        if len(pool) < 2:
            raise ValueError("the ranking needs at least 2 spots that are not in a listing photo")
        ch = cls(
            case_id=case_id,
            challenge_id=f"ch-{uuid.uuid4().hex[:8]}",
            code=new_code(rng),
            pool=pool,
            clock=clock,
            rng=rng or secrets.SystemRandom(),
        )
        ch._reveal(step=1)
        return ch

    def _reveal(self, step: int) -> None:
        used = {s.spot_id for s in self.spots}
        spot = self.rng.choice([s for s in self.pool if s.spot_id not in used])
        self.spots.append(
            SpotResult(
                spot_id=spot.spot_id,
                step=step,
                revealed_at=self.clock(),
                deadline_s=STEP_DEADLINE_S[step],
            )
        )

    def visible_spots(self) -> list[SpotResult]:
        """Only the spots revealed so far. Spot 2 does not exist until spot 1 matches."""
        return list(self.spots)

    def _event(self, kind: str, photo_id: str) -> None:
        self.log.append(LogEvent(kind, self.clock(), self.spots[-1].spot_id, photo_id))

    def reply(self, reply: Reply) -> PresenceStatus:
        if self.presence is not PresenceStatus.WAITING:
            self._event("ignored", reply.photo_id)
            return self.presence

        now = self.clock()
        current = self.spots[-1]

        # A copy of this case's own listing photo is forged whenever it arrives.
        if reply.memory is not None and reply.memory.hit is MemoryHitKind.SAME_CASE_LISTING:
            self._record(current, reply, now, code_read=None)
            self.presence = PresenceStatus.FORGED
            return self.presence

        if now > current.revealed_at + timedelta(seconds=current.deadline_s):
            self._event("late_reply", reply.photo_id)
            return self.presence

        code_read, extra_text = compare(self.code, reply.ocr_text)
        if extra_text:
            self.injection_text_seen = True
            self._event("injection_text", reply.photo_id)
        self._record(current, reply, now, code_read=code_read)

        if not code_read:
            self.presence = PresenceStatus.FORGED
            return self.presence

        if reply.recapture is not None and reply.recapture.blocks_pass:
            self._retry("recapture_block", reply.photo_id)
            return self.presence

        if not reply.located:
            self._retry("retry", reply.photo_id)
            return self.presence

        if current.step == 1:
            self._reveal(step=2)
        else:
            self.presence = PresenceStatus.PROVEN
        return self.presence

    def _retry(self, kind: str, photo_id: str) -> None:
        self._event(kind, photo_id)
        if self.retries < MAX_RETRIES:
            self.retries += 1

    def _record(
        self, spot: SpotResult, reply: Reply, now: datetime, code_read: bool | None
    ) -> None:
        self.spots[-1] = spot.model_copy(
            update={
                "replied_at": now,
                "reply_photo_id": reply.photo_id,
                "code_read": code_read,
                "located": reply.located,
                "inliers": reply.inliers,
            }
        )

    def result(self) -> ChallengeResult:
        return ChallengeResult(
            case_id=self.case_id,
            challenge_id=self.challenge_id,
            code=self.code,
            spots=self.visible_spots(),
            retries=self.retries,
            presence=self.presence,
            injection_text_seen=self.injection_text_seen,
        )
