"""Shared data contracts between lanes.

Every lane reads and writes these shapes, so a change here can break three other lanes.
Change this file only through a pull request reviewed by the integrator lane.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class DataSource(StrEnum):
    """Where a case's data came from. Every screen and every number shows this label."""

    LIVE = "live"
    FIXTURE = "fixture"


class LocateStatus(StrEnum):
    """Result of placing one listing photo in the 3D twins we have indexed."""

    LOCATED_IN_CLAIMED = "located_in_claimed"  # geometrically verified inside the claimed property
    LOCATED_ELSEWHERE = "located_elsewhere"  # verified inside a different indexed property
    NOT_LOCATED = "not_located"  # the claimed property is indexed and the photo matches nowhere
    NOT_INDEXED = "not_indexed"  # the claimed property has no twin in our index


class PhotoLocation(BaseModel):
    """One listing photo and where (if anywhere) it was found."""

    photo_id: str
    status: LocateStatus
    model_id: str | None = None
    pano_id: str | None = None
    inliers: int | None = None
    inlier_ratio: float | None = None


class AuthorityStatus(StrEnum):
    """Does the poster match the contact on the property record?"""

    MATCHES_RECORD = "matches_record"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class PresenceStatus(StrEnum):
    """State of the proof-of-presence challenge. Presence is never the same thing as authority."""

    NOT_REQUESTED = "not_requested"
    WAITING = "waiting"  # includes "no reply yet": an honest landlord gets time
    PROVEN = "proven"
    FORGED = "forged"  # the reply was a reused listing photo, a tour screenshot, or similar


class Evidence(BaseModel):
    """Everything the verdict is allowed to look at for one case."""

    case_id: str
    source: DataSource
    photos: list[PhotoLocation] = Field(default_factory=list)
    authority: AuthorityStatus = AuthorityStatus.UNKNOWN
    presence: PresenceStatus = PresenceStatus.NOT_REQUESTED
    forgery_reason: str | None = None
    price_flag: bool = False  # listed rent is far below comparable units
    payment_flag: bool = False  # asked for a deposit before viewing, or an irreversible payment


class VerdictState(StrEnum):
    VERIFIED = "verified"
    HOLD = "hold"
    DONT_PAY = "dont_pay"  # always shown as "Don't pay · could not verify", never as "scam"
    UNVERIFIED = "unverified"


class Verdict(BaseModel):
    case_id: str
    state: VerdictState
    reasons: list[str]
    source: DataSource
