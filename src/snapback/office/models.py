"""What the office-confirmation routes send and receive."""

from typing import Literal

from pydantic import BaseModel, Field

from snapback.contracts import DataSource


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
