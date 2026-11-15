"""W1: what the three web checks found, as facts, and the pure code that reads each answer.

Nothing here touches the network. `clients.py` fetches, `run.py` runs the three checks in
parallel, and these functions turn a page, a search answer or a list of postings into a few
yes/no values and counts. No phone digits and no names leave this module: a phone found on a
page is compared through the same keyed hash the record uses (`rules.contact.phone_hash`).
`decide()` never reads any of it; the web lines are evidence for the explanation only.
"""

import html
import re
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from snapback.agent.rules.contact import check_link, host_of, phone_hash
from snapback.contracts import DataSource, LinkDomain


class CheckStatus(StrEnum):
    DONE = "done"
    NOT_CHECKED = "not_checked"  # no key, or nothing to check (no link in the ad, no site)
    FAILED = "failed"  # the service answered with an error or something we could not read
    TIMED_OUT = "timed_out"  # past the shared limit; the case goes on without it


class SiteCheck(BaseModel):
    """1. The building's own site (host from CoStar's record), read through Bright Data."""

    status: CheckStatus = CheckStatus.NOT_CHECKED
    host: str | None = None
    lists_unit: bool | None = None  # the page names the ad's floor plan or unit
    phone_matches: bool | None = None  # the page shows the office phone on record (by hash)
    ms: int | None = None


class LinkCheck(BaseModel):
    """2. The ad's own link, opened in a real browser by Browser Use."""

    status: CheckStatus = CheckStatus.NOT_CHECKED
    final_host: str | None = None  # where 'Apply / Pay deposit' really ends up
    same_as_record: bool | None = None  # that host is the building's own site
    link_domain: LinkDomain | None = None  # matches / lookalike / other, against the record
    asks_payment_on_page: bool | None = None
    cost_usd: float | None = None
    ms: int | None = None


class ElsewhereCheck(BaseModel):
    """3. Two separate counts, never a name:
    - the same ad's words posted elsewhere: an exact-phrase web search (Bright Data). Only these
      hits can say another poster uses a different phone (`poster_differs`, from their snippets).
    - rentals of this size nearby: Apify's area search. A market figure, never "the same home":
      a different phone there is just another landlord, so it is never compared."""

    status: CheckStatus = CheckStatus.NOT_CHECKED
    postings: int | None = None  # pages carrying the ad's own words (search hits), own site dropped
    poster_differs: bool | None = None  # one of those pages shows a different phone
    nearby: int | None = None  # rentals of the ad's size in the area (Apify)
    by_source: dict[str, int] = Field(default_factory=dict)  # nearby rentals per source
    rent_low: int | None = None  # asked rent among the nearby rentals
    rent_high: int | None = None
    ms: int | None = None


class WebFacts(BaseModel):
    source: DataSource
    site: SiteCheck = Field(default_factory=SiteCheck)
    link: LinkCheck = Field(default_factory=LinkCheck)
    elsewhere: ElsewhereCheck = Field(default_factory=ElsewhereCheck)


class WebInputs(BaseModel):
    """What the checks are given. Derived by code from the case; no sponsor image, no record
    row. The record's office phone arrives only as its keyed hash."""

    website_host: str | None = None  # from CoStar's record, host only
    plan_words: list[str] = Field(default_factory=list)  # "2 bed", a floor plan name, "Unit 4B"
    site_phone_hash: str | None = None
    ad_link: str | None = None
    ad_phrase: str | None = None  # a short quoted phrase from the ad's own words
    ad_phone_hash: str | None = None
    city: str | None = None  # "Houston, TX"
    # The area to search for rentals: the building's position rounded to 2 decimals (about a
    # kilometre), so no exact location leaves us. None means no rental search.
    center: tuple[float, float] | None = None
    beds: int | None = None


# --- page text --------------------------------------------------------------------------------

_TAGS = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.S | re.I)
_SPACE = re.compile(r"\s+")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
_TEL = re.compile(r"""href=["']tel:([^"']{7,24})["']""", re.I)
MAX_PAGE_CHARS = 400_000
MAX_PHONES_ON_PAGE = 40


def page_text(raw: str) -> str:
    """Visible text of an HTML page, one space between words."""
    text = _TAGS.sub(" ", raw[:MAX_PAGE_CHARS])
    return _SPACE.sub(" ", html.unescape(text)).strip()


def phone_hashes(raw: str, salt: str) -> set[str]:
    """Keyed hashes of the phone numbers a page shows (its text and its tel: links)."""
    found = [*_TEL.findall(raw[:MAX_PAGE_CHARS]), *_PHONE.findall(page_text(raw))]
    hashes = {phone_hash(number, salt) for number in found[:MAX_PHONES_ON_PAGE]}
    return {h for h in hashes if h}


def _word_pattern(word: str) -> re.Pattern[str]:
    parts = [re.escape(p) for p in word.lower().split()]
    return re.compile(r"(?<![a-z0-9])" + r"[\s-]*".join(parts) + r"(?![a-z0-9])")


def mentions(text: str, words: Iterable[str]) -> bool:
    low = text.lower()
    return any(_word_pattern(w).search(low) for w in words if w.strip())


def site_facts(raw: str, inputs: WebInputs, salt: str) -> SiteCheck:
    """Does the building's own page name the ad's plan or unit, and show the office phone?"""
    text = page_text(raw)
    lists = mentions(text, inputs.plan_words) if inputs.plan_words else None
    phone: bool | None = None
    if inputs.site_phone_hash:
        on_page = phone_hashes(raw, salt)
        phone = (inputs.site_phone_hash in on_page) if on_page else None
    return SiteCheck(
        status=CheckStatus.DONE, host=inputs.website_host, lists_unit=lists, phone_matches=phone
    )


# --- the ad's link ----------------------------------------------------------------------------


def link_facts(
    final_url: str | None, asks_payment: bool | None, website_host: str | None
) -> LinkCheck:
    """Where the ad's link ended up, against the building's own site."""
    final_host = host_of(final_url) if final_url else None
    same: bool | None = None
    domain: LinkDomain | None = None
    if final_host and website_host:
        domain = check_link([final_url or ""], website_host)
        same = domain is LinkDomain.MATCHES
    return LinkCheck(
        status=CheckStatus.DONE if final_host else CheckStatus.FAILED,
        final_host=final_host,
        same_as_record=same,
        link_domain=domain,
        asks_payment_on_page=asks_payment,
    )


# --- the same home elsewhere ------------------------------------------------------------------

_MONEY = re.compile(r"\$\s?(\d{1,2}(?:,\d{3})+|\d{3,5})")
PRICE_KEYS = ("unformattedPrice", "price", "rent", "priceValue", "amount", "monthlyRent")
PHONE_KEYS = ("phone", "phoneNumber", "contactPhone", "brokerPhone", "agentPhone")
BED_KEYS = ("beds", "bedrooms", "bedroomCount")
LINK_KEYS = ("propertyUrl", "detailUrl", "url", "link", "postingUrl")
RENT_FLOOR, RENT_CEILING = 200, 20_000  # a monthly rent; anything else is a misread


def money(value: Any) -> int | None:
    """A monthly rent from a number or a price string ("$1,250/mo"), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        n = int(value)
    elif isinstance(value, str):
        m = _MONEY.search(value) or re.fullmatch(r"\s*(\d{3,5})\s*", value)
        if not m:
            return None
        n = int(m.group(1).replace(",", ""))
    else:
        return None
    return n if RENT_FLOOR <= n <= RENT_CEILING else None


def _first(item: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if item.get(key) not in (None, ""):
            return item[key]
    return None


def _beds(item: Mapping[str, Any]) -> int | None:
    value = _first(item, BED_KEYS)
    try:
        return int(float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _postings(items: Sequence[Any]) -> list[Mapping[str, Any]]:
    """One row per offered unit. Zillow's search gives a listing with a `units` list (beds and
    price as text); each unit is a posting, carrying the listing's link and phone."""
    rows: list[Mapping[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        units = item.get("units")
        if isinstance(units, list) and units:
            shared = {k: item[k] for k in (*LINK_KEYS, *PHONE_KEYS) if k in item}
            for n, unit in enumerate(units):
                if isinstance(unit, Mapping) and not unit.get("roomForRent"):
                    link = _first(shared, LINK_KEYS)
                    tag = {"_unit_link": f"{link}#{n}"} if isinstance(link, str) else {}
                    rows.append({**shared, **unit, **tag})
        else:
            rows.append(item)
    return rows


class SearchHit(BaseModel):
    link: str
    snippet: str = ""


def search_hits(answer: Mapping[str, Any], website_host: str | None) -> list[SearchHit]:
    """Web search results (link and snippet), minus the building's own site."""
    own = website_host.lower() if website_host else None
    hits: list[SearchHit] = []
    for row in answer.get("organic") or []:
        if not isinstance(row, Mapping):
            continue
        link = row.get("link") or row.get("url")
        if not isinstance(link, str):
            continue
        host = host_of(link)
        if host and own and (host == own or host.endswith("." + own)):
            continue
        snippet = " ".join(str(row.get(k) or "") for k in ("title", "description", "snippet"))
        hits.append(SearchHit(link=link, snippet=snippet))
    return hits


def elsewhere_facts(
    hits: Sequence[SearchHit] | None,
    rentals: Mapping[str, Sequence[Mapping[str, Any]]],
    inputs: WebInputs,
    salt: str,
) -> ElsewhereCheck:
    """The exact-phrase hits (and whether one shows another phone) and, apart from them, the
    count and rent range of nearby rentals of the ad's size."""
    differs: bool | None = None
    if hits is not None and inputs.ad_phone_hash:
        found: set[str] = set()
        for hit in hits:
            found |= phone_hashes(html.escape(hit.snippet), salt)
        differs = bool(found - {inputs.ad_phone_hash}) if found else None
    by_source: dict[str, int] = {}
    rents: list[int] = []
    seen: set[str] = set()
    for name, items in rentals.items():
        kept = 0
        for item in _postings(items):
            beds = _beds(item)
            if inputs.beds is not None and beds is not None and beds != inputs.beds:
                continue
            link = item.get("_unit_link") or _first(item, LINK_KEYS)
            if isinstance(link, str):
                if link in seen:
                    continue
                seen.add(link)
            kept += 1
            rent = money(_first(item, PRICE_KEYS))
            if rent is not None:
                rents.append(rent)
        by_source[name] = kept
    return ElsewhereCheck(
        status=CheckStatus.DONE,
        postings=len(hits) if hits is not None else None,
        poster_differs=differs,
        nearby=sum(by_source.values()) if rentals else None,
        by_source=by_source,
        rent_low=min(rents) if rents else None,
        rent_high=max(rents) if rents else None,
    )
