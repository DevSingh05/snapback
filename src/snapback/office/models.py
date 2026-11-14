"""What the office-confirmation routes send and receive."""

from typing import Literal

from pydantic import BaseModel, Field

from snapback.contracts import DataSource


class ListingContext(BaseModel):
    """What the office is asked about, so it can tell which ad this is: the building from
    CoStar's record and what the ad itself says. The ad's words are unchecked claims."""

    building: str | None = None  # from the record
    address: str | None = None  # from the record
    unit: str | None = None  # the ad's
    rent: int | None = None  # the ad's, dollars a month
    poster: str | None = None  # the company or name the ad signs with
    phones: list[str] = Field(default_factory=list)  # the ad's contacts, as printed
    emails: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)


class OfficeRequest(BaseModel):
    """The address the poster gave the renter. It must be at the domain on record."""

    address: str = Field(max_length=320)


class OfficeStatus(BaseModel):
    case_id: str
    source: DataSource  # LIVE or FIXTURE, as on the card
    domain: str | None  # the website domain CoStar has on record for this office, if any
    offered: bool  # a link can be asked for (there is a domain on record)
    confirmed: bool
    confirmed_domain: str | None = None
    declined: bool = False  # the office said the ad is not theirs; nothing clears it
    declined_domain: str | None = None
    delivery: Literal["outbox"] = "outbox"  # nothing is ever sent by this server
    guidance: str  # what to do next, in words


class OfficeRequested(BaseModel):
    case_id: str
    source: DataSource
    domain: str
    sent: Literal[False] = False
    delivery: Literal["outbox"] = "outbox"
    expires_in_minutes: int
    detail: str


class OfficeTokenBody(BaseModel):
    """The one-time token, sent in a body (never in an address, so it stays out of logs)."""

    token: str = Field(min_length=1, max_length=200)


class OfficeAnswer(OfficeTokenBody):
    decision: Literal["yes", "no"]


class OfficePeek(BaseModel):
    """What the confirm page shows. Looking changes nothing."""

    domain: str
    source: DataSource
    listing: ListingContext


class OfficeAnswered(BaseModel):
    decision: Literal["yes", "no"]
    domain: str
    message: str
