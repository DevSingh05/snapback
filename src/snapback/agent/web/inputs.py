"""W1: what the web checks are given, derived by code from the ad and the building's record.

Only small derived values leave: the record's website host, the ad's link host (never its path
or query, which can carry tracking ids), a short phrase of the ad's own words with no link, mail
or phone in it, the area rounded to 2 decimals, the bed count, and phone numbers as keyed hashes.
"""

from snapback.agent.intake import Listing
from snapback.agent.rules.contact import phone_hash
from snapback.agent.web.facts import WebInputs
from snapback.agent.web.run import ad_phrase
from snapback.contracts import PropertyRecord


def plan_words(listing: Listing) -> list[str]:
    """Words the building's own page would use for the ad's home: its size and its unit."""
    words: list[str] = []
    if listing.beds == 0:
        words.append("studio")
    elif listing.beds is not None:
        words += [f"{listing.beds} bed", f"{listing.beds} bedroom"]
    if listing.unit:
        words += [f"unit {listing.unit}", f"apt {listing.unit}", f"#{listing.unit}"]
    return words


def web_inputs_for(listing: Listing, record: PropertyRecord | None, salt: str) -> WebInputs:
    links = listing.contacts.links
    phones = listing.contacts.phones
    center = None
    if record is not None and record.lat is not None and record.lon is not None:
        center = (round(record.lat, 2), round(record.lon, 2))
    return WebInputs(
        website_host=record.website_host if record else None,
        plan_words=plan_words(listing),
        site_phone_hash=record.site_phone_hash if record else None,
        ad_link=f"https://{links[0]}/" if links else None,
        ad_phrase=ad_phrase(listing.text),
        ad_phone_hash=(phone_hash(phones[0], salt) or None) if phones else None,
        city=record.market if record else None,
        center=center,
        beds=listing.beds,
    )
