"""Census Geocoder: does this address exist, and in which ZIP and county.

Free, no key, US Government public data. It matches an address against the Census address
ranges, so a brand new home can miss. That is why a miss is an information line, never a flag.
A match gives the ZIP (which feeds the HUD rent baseline) and the county (Harris, FIPS 48201,
routes to the HCAD owner lookup). Any failure is "not checked".
"""

import re
from urllib.parse import urlencode

from snapback.contracts import PlaceCheck, PublicStatus
from snapback.public.fetch import Fetcher

SOURCE_NAME = "Census"
URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
_SUFFIXES = (
    r"st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ln|lane|way|ct|court|pkwy|parkway|"
    r"hwy|highway|pl|place|cir|circle|trl|trail|ter|terrace|loop"
)
# "14 Example Lane, Houston, TX 77096": a street, an optional city, then the state. Every
# quantifier is bounded: the text is written by the person being checked.
_ADDRESS = re.compile(
    rf"\b(\d{{1,6}}\s+(?!(?:bed|beds|bath|baths|br|ba|bd|bdrm|bedroom|bedrooms)\b)"
    rf"(?:[A-Za-z0-9.'-]{{1,24}}\s+){{0,3}}(?:{_SUFFIXES})\b\.?)"
    r"(?:,?\s+([A-Za-z][A-Za-z .'-]{0,28}?))?,?\s+(?:TX|Texas)\b\.?(?:,?\s+(\d{5}))?",
    re.I,
)


def address_in(text: str) -> str | None:
    """The street address the ad gives, in one line, if it names one with its state."""
    found = _ADDRESS.search(text or "")
    if not found:
        return None
    street, city, zip_code = found.group(1).rstrip("."), found.group(2), found.group(3)
    parts = [street, (city or "").strip(), "TX" + (f" {zip_code}" if zip_code else "")]
    return ", ".join(part for part in parts if part)


def check(address: str, fetcher: Fetcher, timeout: float = 2.0) -> PlaceCheck:
    """Ask the Census Geocoder. NOT_CHECKED on any failure; NO_MATCH is a real answer."""
    query = urlencode(
        {
            "address": address,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "format": "json",
        }
    )
    key = " ".join(address.lower().split())
    body = fetcher.get("census", key, f"{URL}?{query}", timeout)
    try:
        matches = body["result"]["addressMatches"] if body else None
    except (KeyError, TypeError):
        matches = None
    if matches is None:
        return PlaceCheck(status=PublicStatus.NOT_CHECKED, source=fetcher.source)
    if not matches:
        return PlaceCheck(status=PublicStatus.NO_MATCH, source=fetcher.source)
    first = matches[0]
    try:
        zip_code = first["addressComponents"].get("zip") or None
        county = (first.get("geographies", {}).get("Counties") or [{}])[0]
        fips = county.get("GEOID") or None
        name = county.get("BASENAME") or None
    except (AttributeError, KeyError, TypeError, IndexError):
        return PlaceCheck(status=PublicStatus.NOT_CHECKED, source=fetcher.source)
    return PlaceCheck(
        status=PublicStatus.FOUND,
        zip=zip_code,
        county_fips=fips,
        county=name,
        source=fetcher.source,
    )


HARRIS_FIPS = "48201"
# Cities that sit in Harris County (a city that straddles a county line, like Katy, is left out).
_HARRIS_CITIES = (
    "Houston", "Pasadena", "Baytown", "Humble", "Spring", "Tomball", "Cypress", "Channelview",
    "Bellaire", "Deer Park", "La Porte", "Galena Park", "Jersey Village", "South Houston",
    "West University Place", "Seabrook", "Crosby", "Highlands", "Kingwood", "Atascocita",
    "Aldine", "Katy Heights",
)  # fmt: skip
_HARRIS_CITY = re.compile(
    r"(?<![A-Za-z])(?:" + "|".join(re.escape(c) for c in _HARRIS_CITIES) + r")(?![A-Za-z])", re.I
)


def in_harris_county(text: str, place: PlaceCheck | None) -> bool:
    """May the HCAD owner roll be asked about this ad? When the Census check found the address,
    its county decides (48201 is Harris). Without that, only an ad that names a Harris County
    city. The HCAD street key has no city or county, so a street in Dallas must never be matched
    against a Harris street of the same name."""
    if place is not None and place.status is PublicStatus.FOUND and place.county_fips:
        return place.county_fips == HARRIS_FIPS
    return _HARRIS_CITY.search(text or "") is not None
