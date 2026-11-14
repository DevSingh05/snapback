"""The ad, described for the office that is asked to recognise it (or not)."""

import re

from snapback.office.models import ListingContext

_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
MAX_TEXT = 120
MAX_ITEMS = 3


def _clean(value: object, limit: int = MAX_TEXT) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(_CONTROL.sub(" ", value).split())[:limit]
    return text or None


def _clean_all(values: object) -> list[str]:
    if not isinstance(values, list | tuple):
        return []
    kept = (_clean(item, 80) for item in values)
    return [item for item in kept if item][:MAX_ITEMS]


def listing_context(record: object | None, listing: object | None) -> ListingContext:
    """The building (from CoStar's record) and what the ad says (unchecked claims).

    Everything is cut to a short plain line: the text goes into an email file and a page."""
    contacts = getattr(listing, "contacts", None)
    rent = getattr(listing, "listed_rent", None)
    return ListingContext(
        building=_clean(getattr(record, "building_name", None)),
        address=_clean(getattr(record, "street_address", None)),
        unit=_clean(getattr(listing, "unit", None), 20),
        rent=rent if isinstance(rent, int) and 0 < rent < 1_000_000 else None,
        poster=_clean(getattr(contacts, "company", None)),
        phones=_clean_all(getattr(contacts, "phones", None)),
        emails=_clean_all(getattr(contacts, "emails", None)),
        links=_clean_all(getattr(contacts, "links", None)),
    )
