"""Intake: turn what a renter sends into fields the rules and the agent use.

A renter sends some typed or pasted text, and images. An image that turns out to be mostly
text is a screenshot of the listing and is read locally; any other image is a listing photo
and is only counted here (placing it in the twin is the vision lane's job). A link is text:
intake never fetches it.

Everything read from the listing is data. The rules run on all of it, an instruction hidden in
it is logged and obeyed by nothing, and nothing is removed.
"""

import logging
from collections.abc import Callable, Iterable

from pydantic import BaseModel, Field

from snapback.agent.intake.fields import ContactClaims, extract_contacts, extract_rent
from snapback.agent.intake.injection import find_injections
from snapback.agent.intake.ocr import OcrUnavailable, read_image
from snapback.agent.rules import apply_rules
from snapback.agent.rules.apply import normalise
from snapback.agent.scope import ListingScope, detect_scope
from snapback.contracts import RuleHit

log = logging.getLogger("snapback.intake")

# An image is a screenshot of a listing, not a photo of a room, if this much text is in it.
SCREENSHOT_MIN_CHARS = 40


class Listing(BaseModel):
    """What intake read. `text` is everything the rules saw: typed text, then screenshots."""

    text: str = ""
    listed_rent: int | None = None
    rule_hits: list[RuleHit] = Field(default_factory=list)
    contacts: ContactClaims = Field(default_factory=ContactClaims)
    scope: ListingScope = ListingScope.RENTAL
    photos: int = 0
    screenshots: int = 0
    injection_spans: list[str] = Field(default_factory=list)
    ocr_available: bool = True


def read_listing(
    text: str = "",
    images: Iterable[bytes] = (),
    *,
    ocr: Callable[[bytes], str] = read_image,
) -> Listing:
    """Read a renter's text and images into a `Listing`. Never raises on a bad image."""
    parts = [text.strip()] if text.strip() else []
    photos = screenshots = 0
    ocr_available = True

    for image in images:
        try:
            seen = ocr(image).strip()
        except OcrUnavailable:
            ocr_available = False
            seen = ""
        except Exception:
            # Not an image we can read. It is still something the renter sent.
            seen = ""
        if len(seen) >= SCREENSHOT_MIN_CHARS:
            screenshots += 1
            parts.append(seen)
        else:
            photos += 1

    full_text = normalise("\n".join(parts))
    injections = find_injections(full_text)
    if injections:
        log.warning("listing carries %d sentence(s) addressed to an AI system", len(injections))

    return Listing(
        text=full_text,
        listed_rent=extract_rent(full_text),
        rule_hits=apply_rules(full_text),
        contacts=extract_contacts(full_text),
        scope=detect_scope(full_text),
        photos=photos,
        screenshots=screenshots,
        injection_spans=injections,
        ocr_available=ocr_available,
    )


__all__ = [
    "ContactClaims",
    "Listing",
    "OcrUnavailable",
    "extract_contacts",
    "extract_rent",
    "find_injections",
    "read_image",
    "read_listing",
]
