"""Find the kit record for the street address an ad gives (proof run, #8, Sun 02:40).

A judge types an ad for a real Houston building with no photo. Without this, the check never
reads that building's CoStar record: the record was joined only when a photo placed the
building or the caller sent our id. Here the ad's street address is matched to a record.

The match is exact on purpose. The house number and the street name, its direction included,
must be the same once spelled the same way ("Street" and "St", "North" and "N"). Only Texas
records are matched (the ad parser reads Texas addresses only, and the kit holds California
buildings too). When both the ad and the record give a city, or a ZIP, they must agree. Two
records at one address, or none, is no match: a check on the wrong building would be worse
than a check on no building. Nothing here logs an address.
"""

import re
from collections.abc import Iterable
from typing import NamedTuple

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


_STATE = re.compile(r"^(texas|[a-z]{2})\b")


class _Parts(NamedTuple):
    key: AddressKey | None
    city: str | None
    state: str | None
    zip: str | None


def _split(address: str) -> _Parts:
    """The street key, city, state and 5-digit ZIP of "street, city, ST zip" (city optional)."""
    parts = [" ".join(p.split()).lower() for p in address.split(",")]
    found_zip = _ZIP.search(address.strip())
    found_state = _STATE.match(parts[-1]) if len(parts) > 1 else None
    state = found_state.group(1) if found_state else None
    return _Parts(
        key=street_key(parts[0]),
        city=parts[1] or None if len(parts) >= 3 else None,
        state="tx" if state == "texas" else state,
        zip=found_zip.group(1) if found_zip else None,
    )


def _agree(mine: str | None, theirs: str | None) -> bool:
    """Two values agree unless both are given and differ."""
    return mine is None or theirs is None or mine == theirs


def build_index(records: Iterable[PropertyRecord]) -> dict[AddressKey, list[PropertyRecord]]:
    """Every Texas record with a street address, under its street key. The ad parser reads
    Texas addresses only, and the kit holds California buildings on the same street names."""
    index: dict[AddressKey, list[PropertyRecord]] = {}
    for record in records:
        if not record.street_address:
            continue
        parts = _split(record.street_address)
        if parts.key is not None and parts.state == "tx":
            index.setdefault(parts.key, []).append(record)
    return index


def match_address(
    listing_text: str, index: dict[AddressKey, list[PropertyRecord]]
) -> PropertyRecord | None:
    """The one record at the address the ad gives, or None (no address, none, or several).
    The city and the ZIP must each agree when both the ad and the record give one."""
    address = address_in(listing_text)
    if address is None:
        return None
    ad = _split(address)
    if ad.key is None:
        return None
    found = []
    for record in index.get(ad.key, []):
        theirs = _split(record.street_address or "")
        if _agree(ad.zip, theirs.zip) and _agree(ad.city, theirs.city):
            found.append(record)
    return found[0] if len(found) == 1 else None


MIN_NAME_TOKENS = 2
MIN_TOKEN_CHARS = 3


CONNECTORS = frozenset({"at", "on", "of", "by", "the", "and", "in"})


def _tokens(text: str) -> list[str]:
    """Lowercase words without connectors, so "District at Greenbriar" reads as two words and
    "The Oaks" as one. Used for the building names and for the ad alike."""
    return [word for word in _WORD.findall(text.lower()) if word not in CONNECTORS]


def build_name_index(
    records: Iterable[PropertyRecord],
) -> dict[tuple[str, ...], list[PropertyRecord]]:
    """Every record under its building name as lowercase word tokens, with or without a
    website: a name without one still blocks a shorter name inside it. A name of one word,
    or with a remaining word under 3 letters, is too common to name one building."""
    index: dict[tuple[str, ...], list[PropertyRecord]] = {}
    for record in records:
        name = tuple(_tokens(record.building_name or ""))
        if len(name) >= MIN_NAME_TOKENS and all(len(word) >= MIN_TOKEN_CHARS for word in name):
            index.setdefault(name, []).append(record)
    return index


def _inside(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    return len(short) < len(long) and any(
        long[i : i + len(short)] == short for i in range(len(long) - len(short) + 1)
    )


def website_for_name(
    listing_text: str, index: dict[tuple[str, ...], list[PropertyRecord]]
) -> str | None:
    """The website host of the one building whose whole name the ad contains as whole words, or
    None (no name, several buildings, several names, or a name that sits inside a longer
    building's name the ad also gives: "Example Greenbriar Park"). Exact, never fuzzy."""
    words = _tokens(listing_text)
    named = [
        name
        for name in index
        if any(tuple(words[i : i + len(name)]) == name for i in range(len(words) - len(name) + 1))
    ]
    named = [name for name in named if not any(_inside(name, other) for other in named)]
    if len(named) != 1 or len(index[named[0]]) != 1:
        return None
    return index[named[0]][0].website_host
