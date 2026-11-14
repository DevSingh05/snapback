"""For-sale hijack lookup (lane D, D7): is a home posted as a rental for sale, or just rented?

Reads `residential-listings.jsonl` (Homes.com records in the CoStar kit) and decodes status and
history through the kit's `schemas/enums.json` (`TransactionType`, `ForRentStatus`,
`ListingUpdateType`). Returns the contract's `ForSaleMatch`:

- ACTIVE: the matching home is on Homes.com for sale right now.
- RECENTLY_RENTED: the record shows it was rented within the last 180 days.
- NONE: looked up, and neither (including no address match).
- None (no object): the kit has no residential file, so nothing was looked up.

Matching is on the street address the renter's listing text carries, normalised (suffixes and unit
words folded). Addresses stay in memory: never logged, printed or put on the card. Field paths
not yet confirmed on the kit are candidates (first present wins), as in `costar_jsonl`.
"""

from __future__ import annotations

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
    "street": ["address.streetAddress", "address.line1", "streetAddress", "address.street"],
    "unit": ["address.unitNumber", "address.unit", "unitNumber", "unit"],
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
UNIT_WORDS = {"apt", "apartment", "unit", "suite", "ste", "no"}
OFF_MARKET = ("sold", "withdrawn", "expired", "off market", "cancel", "rented", "leased")


def normalize_address(text: str) -> str:
    """Lowercase words with suffixes and unit words folded: '100 Fixture Ln., Apt #2' and
    '100 fixture lane unit 2' both become '100 fixture ln unit 2'."""
    text = text.lower().replace("#", " unit ")
    words = re.findall(r"[a-z0-9]+", text)
    out: list[str] = []
    for w in words:
        w = "unit" if w in UNIT_WORDS else SUFFIXES.get(w, w)
        if out and out[-1] == "unit" and w == "unit":
            continue
        out.append(w)
    return " ".join(out)


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


def _status(
    rec: dict[str, Any], enums: dict[str, dict[str, str]], today: date
) -> tuple[ForSaleStatus, date | None, date | None]:
    history = []
    for h in _first(rec, RESIDENTIAL_FIELDS["history"]) or []:
        if isinstance(h, dict):
            when = _date(_first(h, HISTORY_FIELDS["date"]))
            label = decode(enums, "ListingUpdateType", _get_any(h, HISTORY_FIELDS["type"]))
            if when is not None:
                history.append((when, (label or "").lower()))
    history.sort()
    listed_on = _date(_first(rec, RESIDENTIAL_FIELDS["listed_on"])) or (
        history[0][0] if history else None
    )
    changed_on, last = history[-1] if history else (listed_on, "")

    rent_status = (
        decode(enums, "ForRentStatus", _first(rec, RESIDENTIAL_FIELDS["for_rent_status"])) or ""
    ).lower()
    rented = "rented" in last or "leased" in last or rent_status == "rented"
    if rented:
        recent = changed_on is not None and today - changed_on <= timedelta(days=RECENT_DAYS)
        status = ForSaleStatus.RECENTLY_RENTED if recent else ForSaleStatus.NONE
        return status, listed_on, changed_on

    transaction = (
        decode(enums, "TransactionType", _first(rec, RESIDENTIAL_FIELDS["transaction"])) or ""
    ).lower()
    if "sale" in transaction and not any(word in last for word in OFF_MARKET):
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


def for_sale_lookup(
    listing_text: str,
    source: DataSource | None = None,
    kit_dir: Path | None = None,
    today: date | None = None,
) -> ForSaleMatch | None:
    """Look the renter's listing text up in the for-sale and recently-rented homes we hold."""
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
        street_raw = _first(rec, RESIDENTIAL_FIELDS["street"])
        if not isinstance(street_raw, str):
            continue
        street = normalize_address(street_raw)
        if not street or f" {street} " not in f" {text} ":
            continue
        unit = _first(rec, RESIDENTIAL_FIELDS["unit"])
        asked = _unit_after(text, street)
        if unit is not None and asked is not None and normalize_address(str(unit)) != asked:
            continue  # same building, a different unit
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
    codes: dict[str, dict[str, int]] = {"transaction": {}, "for_rent_status": {}, "update": {}}
    records = 0
    for rec in _iter_jsonl(path):
        records += 1
        for name, paths in RESIDENTIAL_FIELDS.items():
            for p in paths:
                fields[name][p] += _get_any(rec, [p]) is not None
        for key in ("transaction", "for_rent_status"):
            code = str(_get_any(rec, RESIDENTIAL_FIELDS[key]))
            codes[key][code] = codes[key].get(code, 0) + 1
        for h in _first(rec, RESIDENTIAL_FIELDS["history"]) or []:
            if isinstance(h, dict):
                code = str(_get_any(h, HISTORY_FIELDS["type"]))
                codes["update"][code] = codes["update"].get(code, 0) + 1
    return {"residential_records": records, "residential_fields": fields, "status_codes": codes}
