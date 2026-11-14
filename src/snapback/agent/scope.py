"""Is this listing something the check covers?

SNAPBACK checks long-term residential rentals. A short-term stay or a commercial space is a
different kind of listing, and for those the agent may be offered "state only": report what
is known and run nothing. The kind of listing is read here, by code, from the listing's own
link and wording. A sentence in the listing asking to skip the checks changes nothing.
"""

import re
from enum import StrEnum

from snapback.agent.rules.apply import normalise


class ListingScope(StrEnum):
    RENTAL = "rental"
    SHORT_TERM = "short_term"
    COMMERCIAL = "commercial"


_SHORT_TERM = re.compile(
    r"airbnb\.|vrbo\.|booking\.com|hotels?\.com"
    r"|\bper night\b|\bnightly\b|/night\b|\ba night\b"
    r"|\bvacation rental\b|\bshort[- ]term (?:rental|stay|let)\b|\bweekly rate\b",
    re.IGNORECASE,
)
_COMMERCIAL = re.compile(
    r"loopnet\.|crexi\."
    r"|\b(?:office|retail|warehouse|industrial|commercial) (?:space|suite|unit|property|lease)\b"
    r"|\btriple net\b|\bNNN\b",
    re.IGNORECASE,
)


def detect_scope(listing_text: str) -> ListingScope:
    listing_text = normalise(listing_text)  # bounded before any pattern reads it
    if _SHORT_TERM.search(listing_text):
        return ListingScope.SHORT_TERM
    if _COMMERCIAL.search(listing_text):
        return ListingScope.COMMERCIAL
    return ListingScope.RENTAL
