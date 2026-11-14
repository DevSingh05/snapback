"""For-sale hijack lookup (lane D, D7): is a home posted as a rental for sale, or just rented?

Reads `residential-listings.jsonl` (Homes.com records in the CoStar kit) and decodes codes through
the kit's `schemas/enums.json`. Records not public on Homes.com (`permissionLevels.homes` != 10)
are never read. Returns the contract's `ForSaleMatch`:

- ACTIVE: `listingStatus` is Active (1) and the listing is for sale.
- RECENTLY_RENTED: the record shows it was rented within the last 180 days.
- NONE: looked up, and neither (including no address match).
- None (no object): the kit has no residential file, so nothing was looked up.

Matching is on the street address the renter's listing text carries, normalised (suffixes and unit
words folded); a zip in the text must agree with the record's; optional lat/lon match within 40 m.
Addresses stay in memory: never logged, printed or put on the card. Key paths are the ones the XO
read off the real kit (#95 review), listed first; older candidates stay behind them.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from snapback.adapters.costar_jsonl import (
    DEFAULT_KIT,
    FIXTURE_KIT,
    _find,
    _first,
    _get_any,
    _iter_jsonl,
    _load_enums,
    decode,
)
from snapback.contracts import DataSource, ForSaleMatch, ForSaleStatus
from snapback.settings import get_settings

RESIDENTIAL_FILE = "residential-listings.jsonl"
RECENT_DAYS = 180
SITE = "Homes.com"

RESIDENTIAL_FIELDS: dict[str, list[str]] = {
    "street": ["property.address.fullStreetAddress", "address.fullStreetAddress"],
    "unit": ["property.address.unitNumber", "address.unitNumber"],
    "zip": ["property.address.zipCode", "property.address.postalCode", "property.address.zip"],
    "lat": ["property.address.latitude", "property.location.latitude", "property.latitude"],
    "lon": ["property.address.longitude", "property.location.longitude", "property.longitude"],
    "listing_status": ["listingStatus"],
    "permission": ["permissionLevels.homes"],
    "transaction": ["transactionType", "listingTransactionType"],
    "for_rent_status": ["forRentStatus"],
    "listed_on": ["listedDate", "listingDate", "listDate"],
    "history": ["listingHistory", "history", "listingUpdates"],
    "offices": ["offices", "listingOffices"],
}
OFFICE_NAME = ["name", "officeName"]
HISTORY_FIELDS: dict[str, list[str]] = {
    "date": ["date", "updateDate", "eventDate"],
    "type": ["listingUpdateType", "updateType", "type"],
}
PUBLIC_ON_HOMES = 10
ACTIVE_CODE = 1
NEAR_M = 40.0
SUFFIXES = {
    "street": "st",
    "avenue": "ave",
    "av": "ave",
    "road": "rd",
    "lane": "ln",
    "drive": "dr",
    "boulevard": "blvd",
    "court": "ct",
    "place": "pl",
    "terrace": "ter",
    "circle": "cir",
    "parkway": "pkwy",
    "highway": "hwy",
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
}
UNIT_WORDS = {"apt", "apartment", "unit", "suite", "ste"}
ZIP_TOKEN = re.compile(r"\b(\d{5})\b")


def normalize_address(text: str) -> str:
    """Lowercase words with suffixes and unit words folded: '100 Fixture Ln., Apt #2' and
    '100 fixture lane unit 2' both become '100 fixture ln unit 2'. 'no' is a unit word only
    before a number ('No. 2'), so 'no pets' stays as it is."""
    text = text.lower().replace("#", " unit ")
    words = re.findall(r"[a-z0-9]+", text)
    out: list[str] = []
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if w in UNIT_WORDS or (w == "no" and any(ch.isdigit() for ch in nxt)):
            w = "unit"
        else:
            w = SUFFIXES.get(w, w)
        if out and out[-1] == "unit" and w == "unit":
            continue
        out.append(w)
    return " ".join(out)


def _label(enums: dict[str, dict[str, str]], enum: str, value: Any) -> str:
    """Decoded label folded to lowercase letters: 'OffMarket' and 'off market' both 'offmarket'."""
    return re.sub(r"[^a-z]", "", (decode(enums, enum, value) or "").lower())


def _date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _unit_after(text: str, street: str) -> str | None:
    """The unit the text names right after the street, if any."""
    i = f" {text} ".find(f" {street} ")
    if i < 0:
        return None
    rest = f" {text} "[i + len(street) + 2 :].split()
    if len(rest) >= 2 and rest[0] == "unit":
        return rest[1]
    return None


def _metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _public(rec: dict[str, Any]) -> bool:
    """Only records Homes.com shows publicly (`permissionLevels.homes` == 10) are ever used."""
    level = _get_any(rec, RESIDENTIAL_FIELDS["permission"])
    try:
        return int(level) == PUBLIC_ON_HOMES
    except (TypeError, ValueError):
        return False


def _status(
    rec: dict[str, Any], enums: dict[str, dict[str, str]], today: date
) -> tuple[ForSaleStatus, date | None, date | None]:
    history = []
    for h in _first(rec, RESIDENTIAL_FIELDS["history"]) or []:
        if isinstance(h, dict):
            when = _date(_first(h, HISTORY_FIELDS["date"]))
            label = _label(enums, "ListingUpdateType", _get_any(h, HISTORY_FIELDS["type"]))
            if when is not None:
                history.append((when, label))
    history.sort()
    listed_on = _date(_first(rec, RESIDENTIAL_FIELDS["listed_on"])) or (
        history[0][0] if history else None
    )
    changed_on, last = history[-1] if history else (listed_on, "")

    rent_status = _label(enums, "ForRentStatus", _first(rec, RESIDENTIAL_FIELDS["for_rent_status"]))
    if last in ("rented", "leased") or rent_status == "rented":
        recent = changed_on is not None and today - changed_on <= timedelta(days=RECENT_DAYS)
        status = ForSaleStatus.RECENTLY_RENTED if recent else ForSaleStatus.NONE
        return status, listed_on, changed_on

    # Active comes from listingStatus alone (filled on every kit record); history labels such as
    # OffMarket or Removed never make a home active or inactive on their own.
    code = _get_any(rec, RESIDENTIAL_FIELDS["listing_status"])
    active = _label(enums, "ListingStatus", code) == "active" or str(code) == str(ACTIVE_CODE)
    transaction = _label(enums, "TransactionType", _first(rec, RESIDENTIAL_FIELDS["transaction"]))
    for_sale = not transaction or "sale" in transaction
    if active and for_sale:
        return ForSaleStatus.ACTIVE, listed_on, changed_on
    return ForSaleStatus.NONE, listed_on, changed_on


def _offices(rec: dict[str, Any]) -> list[str]:
    """Brokerage company names on the listing. `agents[]` (people) are deliberately not read."""
    names = []
    for office in _first(rec, RESIDENTIAL_FIELDS["offices"]) or []:
        if isinstance(office, dict):
            name = _first(office, OFFICE_NAME)
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    return list(dict.fromkeys(names))


def _zip_after(text: str, street: str) -> str | None:
    """The last 5-digit number after the street: a zip, never the house number in front of it."""
    i = f" {text} ".find(f" {street} ")
    tail = f" {text} "[i + len(street) + 2 :] if i >= 0 else ""
    found = ZIP_TOKEN.findall(tail)
    return found[-1] if found else None


def _any_unit(text: str) -> str | None:
    """The first unit the text names anywhere ('unit 7'), for a match made on coordinates."""
    words = text.split()
    for w, nxt in zip(words, words[1:], strict=False):
        if w == "unit":
            return nxt
    return None


def _same_unit(rec: dict[str, Any], asked: str | None) -> bool:
    """A different unit in the same building is not that home; a missing unit on either side is."""
    unit = _first(rec, RESIDENTIAL_FIELDS["unit"])
    return unit is None or asked is None or normalize_address(str(unit)) == asked


def _matches(rec: dict[str, Any], text: str, lat: float | None, lon: float | None) -> bool:
    street_raw = _first(rec, RESIDENTIAL_FIELDS["street"])
    street = normalize_address(street_raw) if isinstance(street_raw, str) else ""
    if street and f" {street} " in f" {text} ":
        record_zip = _first(rec, RESIDENTIAL_FIELDS["zip"])
        zip_in_text = _zip_after(text, street)
        if zip_in_text and record_zip and str(record_zip)[:5] != zip_in_text:
            return False  # same street text, a different town
        return _same_unit(rec, _unit_after(text, street))
    if lat is None or lon is None:
        return False
    rlat, rlon = _get_any(rec, RESIDENTIAL_FIELDS["lat"]), _get_any(rec, RESIDENTIAL_FIELDS["lon"])
    try:
        near = _metres(lat, lon, float(rlat), float(rlon)) <= NEAR_M
    except (TypeError, ValueError):
        return False
    return near and _same_unit(rec, _any_unit(text))


def for_sale_lookup(
    listing_text: str,
    source: DataSource | None = None,
    kit_dir: Path | None = None,
    today: date | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> ForSaleMatch | None:
    """Look the renter's listing up in the public for-sale and recently-rented homes we hold.

    Matches on the street address in the text (and its zip, when the text has one), or, when
    `lat`/`lon` are given, on any home within 40 m of that point."""
    source = source or get_settings().snapback_data_source
    kit = kit_dir or (FIXTURE_KIT if source == DataSource.FIXTURE else DEFAULT_KIT)
    path = _find(kit, RESIDENTIAL_FILE)
    if path is None:
        return None
    today = today or date.today()
    enums = _load_enums(kit)
    text = normalize_address(listing_text)

    best: ForSaleMatch | None = None
    rank = {ForSaleStatus.ACTIVE: 2, ForSaleStatus.RECENTLY_RENTED: 1, ForSaleStatus.NONE: 0}
    for rec in _iter_jsonl(path):
        if not _public(rec) or not _matches(rec, text, lat, lon):
            continue
        status, listed_on, changed_on = _status(rec, enums, today)
        match = ForSaleMatch(
            status=status,
            site=SITE,
            listed_on=listed_on,
            changed_on=changed_on,
            offices=_offices(rec),
        )
        if best is None or rank[status] > rank[best.status]:
            best = match
    return best or ForSaleMatch(status=ForSaleStatus.NONE, site=SITE)


def coverage_residential(kit_dir: Path) -> dict[str, Any]:
    """How many residential records each candidate path fills, plus the status codes seen.
    Counts, key paths and enum codes only: no addresses, ids or dates."""
    path = _find(kit_dir, RESIDENTIAL_FILE)
    if path is None:
        return {"residential_records": 0}
    fields = {name: dict.fromkeys(paths, 0) for name, paths in RESIDENTIAL_FIELDS.items()}
    keys = ("listing_status", "permission", "transaction", "for_rent_status")
    codes: dict[str, dict[str, int]] = {key: {} for key in (*keys, "update")}
    records = 0
    for rec in _iter_jsonl(path):
        records += 1
        for name, paths in RESIDENTIAL_FIELDS.items():
            for p in paths:
                fields[name][p] += _get_any(rec, [p]) is not None
        for key in keys:
            code = str(_get_any(rec, RESIDENTIAL_FIELDS[key]))
            codes[key][code] = codes[key].get(code, 0) + 1
        for h in _first(rec, RESIDENTIAL_FIELDS["history"]) or []:
            if isinstance(h, dict):
                code = str(_get_any(h, HISTORY_FIELDS["type"]))
                codes["update"][code] = codes["update"].get(code, 0) + 1
    return {"residential_records": records, "residential_fields": fields, "status_codes": codes}
