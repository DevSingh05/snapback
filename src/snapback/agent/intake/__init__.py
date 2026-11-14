"""Intake: turn what a renter sends into fields the rules and the agent use.

A renter sends some typed or pasted text, and images. An image that turns out to be mostly
text is a screenshot of the listing and is read locally; any other image is a listing photo
and is only counted here (placing it in the twin is the vision lane's job). A link is text:
intake never fetches it.

Everything read from the listing is data. The rules run on all of it, an instruction hidden in
it is logged and obeyed by nothing, and nothing is removed.

One limit: only the first `MAX_TEXT_CHARS` characters are read, so that nobody can stall the
check with a huge paste. A listing longer than that is marked `truncated`, and the renter is
told in the trace that the rest was not checked.
"""

import logging
from collections.abc import Callable, Iterable

from pydantic import BaseModel, Field

from snapback.agent.intake.fields import (
    ContactClaims,
    extract_beds,
    extract_contacts,
    extract_rent,
    extract_unit,
)
from snapback.agent.intake.injection import find_injections
from snapback.agent.intake.ocr import OcrUnavailable, read_image
from snapback.agent.rules import apply_rules
from snapback.agent.rules.apply import MAX_TEXT_CHARS, exceeds_cap, normalise
from snapback.agent.scope import ListingScope, detect_scope
from snapback.contracts import RuleHit

log = logging.getLogger("snapback.intake")

# An image is a screenshot of a listing, not a photo of a room, if this much text is in it.
SCREENSHOT_MIN_CHARS = 40


class Listing(BaseModel):
    """What intake read. `text` is everything the rules saw: typed text, then screenshots."""

    text: str = ""
    listed_rent: int | None = None
    unit: str | None = None  # "204", "4B": the unit the listing names
    beds: int | None = None  # 0 for a studio
    rule_hits: list[RuleHit] = Field(default_factory=list)
    contacts: ContactClaims = Field(default_factory=ContactClaims)
    scope: ListingScope = ListingScope.RENTAL
    photos: int = 0
    screenshots: int = 0
    # Which of the images given were counted as photos, by position. The bytes are not kept
    # here; whoever holds them uses this to know which ones are listing photos.
    photo_indexes: list[int] = Field(default_factory=list)
    injection_spans: list[str] = Field(default_factory=list)
    ocr_available: bool = True
    # There was more text than is read (`MAX_TEXT_CHARS`). What came after it was not checked.
    truncated: bool = False


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

    photo_indexes: list[int] = []
    for position, image in enumerate(images):
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
            photo_indexes.append(position)

    # Cut and folded before any pattern runs: the text is written by the person being checked.
    sent = "\n".join(parts)
    full_text = normalise(sent)
    truncated = exceeds_cap(sent)
    if truncated:
        log.warning("listing text was cut to %d characters", MAX_TEXT_CHARS)
    injections = find_injections(full_text)
    if injections:
        log.warning("listing carries %d sentence(s) addressed to an AI system", len(injections))

    return Listing(
        text=full_text,
        listed_rent=extract_rent(full_text),
        unit=extract_unit(full_text),
        beds=extract_beds(full_text),
        rule_hits=apply_rules(full_text),
        contacts=extract_contacts(full_text),
        scope=detect_scope(full_text),
        photos=photos,
        screenshots=screenshots,
        photo_indexes=photo_indexes,
        injection_spans=injections,
        ocr_available=ocr_available,
        truncated=truncated,
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
