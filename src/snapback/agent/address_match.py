"""Find the kit record for the street address an ad gives (proof run, #8, Sun 02:40).

A judge types an ad for a real Houston building with no photo. Without this, the check never
reads that building's CoStar record: the record was joined only when a photo placed the
building or the caller sent our id. Here the ad's street address is matched to a record.

The match is exact on purpose. The house number and the street name must be the same once
spelled the same way ("Street" and "St", "North" and "N"), and when both the ad and the record
give a ZIP the two must agree. Two records at one address, or none, is no match: a check on the
wrong building would be worse than a check on no building. Nothing here logs an address.
"""

import re
from collections.abc import Iterable

from snapback.contracts import PropertyRecord
from snapback.public.census import address_in

_SPELLED = {
    "street": "st",
    "avenue": "ave",
    "av": "ave",
    "road": "rd",
    "boulevard": "blvd",
    "drive": "dr",
    "lane": "ln",
    "court": "ct",
    "parkway": "pkwy",
    "highway": "hwy",
    "place": "pl",
    "circle": "cir",
    "trail": "trl",
    "terrace": "ter",
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
}
_WORD = re.compile(r"[a-z0-9]+")
_ZIP = re.compile(r"\b(\d{5})(?:-?\d{4})?\s*$")

AddressKey = tuple[str, str]


def street_key(street: str) -> AddressKey | None:
    """("1717", "college st") for "1717 College Street", or None when there is no number."""
    words = _WORD.findall(street.lower())
    if len(words) < 2 or not words[0].isdigit():
        return None
    return words[0], " ".join(_SPELLED.get(word, word) for word in words[1:])


def _split(address: str) -> tuple[AddressKey | None, str | None]:
    """The street key and the 5-digit ZIP of a one-line address ("street, city, TX zip")."""
    street = address.split(",", 1)[0]
    found = _ZIP.search(address.strip())
    return street_key(street), found.group(1) if found else None


def build_index(records: Iterable[PropertyRecord]) -> dict[AddressKey, list[PropertyRecord]]:
    """Every record with a street address, under its street key."""
    index: dict[AddressKey, list[PropertyRecord]] = {}
    for record in records:
        if not record.street_address:
            continue
        key, _ = _split(record.street_address)
        if key is not None:
            index.setdefault(key, []).append(record)
    return index


def match_address(
    listing_text: str, index: dict[AddressKey, list[PropertyRecord]]
) -> PropertyRecord | None:
    """The one record at the address the ad gives, or None (no address, none, or several)."""
    address = address_in(listing_text)
    if address is None:
        return None
    key, ad_zip = _split(address)
    if key is None:
        return None
    found = index.get(key, [])
    if ad_zip is not None:
        found = [r for r in found if _split(r.street_address or "")[1] in (ad_zip, None)]
    return found[0] if len(found) == 1 else None
