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

import json
import math
import re
from collections import Counter
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
from snapback.contracts import (
    DataSource,
    ForSaleMatch,
    ForSaleStatus,
    PropertyRecord,
    RentalHouse,
)
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


_UNIT_WORD = r"(?:\b(?i:apt|apartment|unit|suite|ste)\b\.?|#)\s*#?\s*"
_LETTER_UPPER = re.compile(_UNIT_WORD + r"([A-Z])\b")
_LETTER_THEN_STOP = re.compile(_UNIT_WORD + r"([A-Za-z])(?=\s*(?:[,.;:!?)]|$))")


def letter_units(raw_text: str) -> set[str]:
    """Single letters the raw text really names as units: right after apt/unit/suite/# and either
    uppercase ('Apt B', '#C') or followed by punctuation or the end ('unit b.'). The article in
    'apartment a short walk' is neither."""
    found = {m.group(1) for m in _LETTER_UPPER.finditer(raw_text)}
    found |= {m.group(1) for m in _LETTER_THEN_STOP.finditer(raw_text)}
    return {letter.lower() for letter in found}


def _looks_like_unit(word: str, letters: set[str]) -> bool:
    """A unit number has a digit in it ('2', '4b', '305'), or is a single letter the raw text
    names as a unit. 'for' in 'apartment for rent' and 'a' in 'apartment a short walk' are prose."""
    if any(ch.isdigit() for ch in word):
        return True
    return len(word) == 1 and word in letters


def _unit_after(text: str, street: str, letters: set[str] = frozenset()) -> str | None:
    """The unit the text names right after the street, if any."""
    i = f" {text} ".find(f" {street} ")
    if i < 0:
        return None
    rest = f" {text} "[i + len(street) + 2 :].split()
    if len(rest) >= 2 and rest[0] == "unit" and _looks_like_unit(rest[1], letters):
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
    """The first 5-digit number after the street: a zip, never the house number in front of it,
    and never a later number such as a deposit amount."""
    i = f" {text} ".find(f" {street} ")
    tail = f" {text} "[i + len(street) + 2 :] if i >= 0 else ""
    found = ZIP_TOKEN.findall(tail)
    return found[0] if found else None


def _any_unit(text: str, letters: set[str] = frozenset()) -> str | None:
    """The first unit the text names anywhere ('unit 7'), for a match made on coordinates."""
    words = text.split()
    for w, nxt in zip(words, words[1:], strict=False):
        if w == "unit" and _looks_like_unit(nxt, letters):
            return nxt
    return None


def _same_unit(rec: dict[str, Any], asked: str | None) -> bool:
    """A different unit in the same building is not that home; a missing unit on either side is."""
    unit = _first(rec, RESIDENTIAL_FIELDS["unit"])
    return unit is None or asked is None or normalize_address(str(unit)) == asked


def _matches(
    rec: dict[str, Any],
    text: str,
    lat: float | None,
    lon: float | None,
    letters: set[str] = frozenset(),
) -> bool:
    street_raw = _first(rec, RESIDENTIAL_FIELDS["street"])
    street = normalize_address(street_raw) if isinstance(street_raw, str) else ""
    if street and f" {street} " in f" {text} ":
        record_zip = _first(rec, RESIDENTIAL_FIELDS["zip"])
        zip_in_text = _zip_after(text, street)
        if zip_in_text and record_zip and str(record_zip)[:5] != zip_in_text:
            return False  # same street text, a different town
        return _same_unit(rec, _unit_after(text, street, letters))
    if lat is None or lon is None:
        return False
    rlat, rlon = _get_any(rec, RESIDENTIAL_FIELDS["lat"]), _get_any(rec, RESIDENTIAL_FIELDS["lon"])
    try:
        near = _metres(lat, lon, float(rlat), float(rlon)) <= NEAR_M
    except (TypeError, ValueError):
        return False
    return near and _same_unit(rec, _any_unit(text, letters))


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
    letters = letter_units(listing_text)

    best: ForSaleMatch | None = None
    rank = {ForSaleStatus.ACTIVE: 2, ForSaleStatus.RECENTLY_RENTED: 1, ForSaleStatus.NONE: 0}
    for rec in _iter_jsonl(path):
        if not _public(rec) or not _matches(rec, text, lat, lon, letters):
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


# --- #74: the demo houses (direction A trio) --------------------------------------------------

DEMO_HOUSE_FILE = Path("demo") / "house.json"
DEMO_HOUSE_SHOWN = "data/demo/house.json"  # printed in place of the absolute path
DEMO_ROLES = ("for_sale", "recently_sold", "decoy")
CITY = "houston"
DETACHED = 1  # ListingPropertyType: a house, not a condo or townhouse
FOR_SALE_CODE = 1  # ForSaleStatus.ForSale
SOLD_CODE = 5  # ForSaleStatus.Sold
TRANSACTION_SALE = 1  # TransactionType.ForSale
NEWLY_SOLD_CODE = 8  # ListingUpdateType.NewlySold
MATTERPORT_TYPES = {36, 234}  # media[].externalReferenceType


def _matterport_models(rec: dict[str, Any]) -> list[str]:
    """Matterport model ids on a residential record: `media[].videoKey` where
    `media[].externalReferenceType` is 36 or 234 (the real kit's key paths)."""
    keys = [
        str(m["videoKey"])
        for m in rec.get("media") or []
        if isinstance(m, dict)
        and m.get("externalReferenceType") in MATTERPORT_TYPES
        and m.get("videoKey")
    ]
    return list(dict.fromkeys(keys))


FEATURES_FILE = "residential-listing-features.jsonl"
SOLD_UPDATE = 8  # ListingUpdateType NewlySold (enums.json)
# SceneClassificationType codes (enums.json) that say something an ad can be held to.
SCENE_FLOOR = {126: "carpet", 218: "carpet", 219: "carpet", 220: "carpet", 221: "carpet",
               222: "carpet", 117: "tile", 180: "wood"}  # fmt: skip
SCENE_POOL = {19, 33}
SCENE_YARD = {65, 129}
SCENE_MACHINE = {135, 163}  # InUnitLaundry, StackedWasherAndDryer
_SHARED_POOL = re.compile(
    r"community|association|shared|common|club|hoa|resort|complex|building|view", re.IGNORECASE
)
_WOOD_LOOK = re.compile(r"wood[- ]?(?:look|grain)", re.IGNORECASE)


def floor_kind(text: str, *, need_floor_word: bool = False) -> str | None:
    """The floor kind a label names ("wood", "carpet", "tile", "laminate"), or None.

    A photo keyword counts only if it names a floor (`need_floor_word`): "Wood Staircase" and
    "Brick Siding" do not. Wood-look tile is tile."""
    low = text.lower()
    if need_floor_word and not ("floor" in low or "carpet" in low):
        return None
    if "carpet" in low:
        return "carpet"
    if _WOOD_LOOK.search(low):
        return "tile" if "tile" in low else None
    if "wood" in low or "parquet" in low:
        return "wood"
    if "laminate" in low or "vinyl" in low:
        return "laminate"
    if any(word in low for word in ("tile", "ceramic", "porcelain", "stone", "marble", "slate")):
        return "tile"
    return None


def _features_by_listing(kit: Path) -> dict[int, dict[str, Any]]:
    """`residential-listing-features.jsonl` by listing id: the feature names under their
    subcategory, and the derived parking count. Names stay in memory; the record keeps words."""
    path = _find(kit, FEATURES_FILE)
    if path is None:
        return {}
    out: dict[int, dict[str, Any]] = {}
    for rec in _iter_jsonl(path):
        listing_id = rec.get("id")
        if isinstance(listing_id, bool) or not isinstance(listing_id, int):
            continue
        names: dict[str, list[str]] = {}
        for feature in rec.get("features") or []:
            if isinstance(feature, dict) and isinstance(feature.get("name"), str):
                names.setdefault(str(feature.get("subcategory1")), []).append(feature["name"])
        derived = rec.get("derivedValues")
        out[listing_id] = {
            "names": names,
            "parking": _whole(derived.get("totalParkingSpaces"))
            if isinstance(derived, dict)
            else None,
        }
    return out


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _laundry_kind(name: str) -> str:
    low = name.lower()
    if "hookup" in low or "hook up" in low or "hook-up" in low:
        return "hookup"
    if "washer" in low or "dryer" in low or "in unit" in low or "in-unit" in low:
        return "machine"
    return "room"


def _home_facts(rec: dict[str, Any], features: dict[str, Any] | None) -> dict[str, Any]:
    """What an ad can be held to, as words and numbers, from one listing. Nothing from the kit
    is kept as text: floors, laundry and the rest become the fixed words the compare uses."""
    photo_floors: list[str] = []
    floor_photos = 0
    pool_photo = yard_photo = machine_photo = False
    for item in rec.get("media") or []:
        if not isinstance(item, dict):
            continue
        kinds = [
            SCENE_FLOOR[s["type"]]
            for s in item.get("scenes") or []
            if isinstance(s, dict) and s.get("type") in SCENE_FLOOR
        ]
        words = [w for w in item.get("computerVisionKeywords") or [] if isinstance(w, str)]
        kinds += [k for k in (floor_kind(w, need_floor_word=True) for w in words) if k]
        if kinds:
            floor_photos += 1
            photo_floors += kinds
        scenes = {s.get("type") for s in item.get("scenes") or [] if isinstance(s, dict)}
        lowered = [w.lower() for w in words]
        pool_photo |= bool(scenes & SCENE_POOL) or any("pool" in w for w in lowered)
        yard_photo |= bool(scenes & SCENE_YARD) or any("yard" in w or "fence" in w for w in lowered)
        machine_photo |= bool(scenes & SCENE_MACHINE)
    names = features["names"] if features else {}
    everything = [name.lower() for group in names.values() for name in group]
    laundry = _unique([_laundry_kind(n) for n in names.get("Laundry", [])])
    if machine_photo and "machine" not in laundry:
        laundry.append("machine")
    # A community, association or shared pool, or a pool view, is not this home's pool.
    own_pool = [n for n in everything if "pool" in n and not _SHARED_POOL.search(n)]
    shared_pool = any("pool" in n and _SHARED_POOL.search(n) for n in everything)
    pool: bool | None = None
    if pool_photo or own_pool:
        pool = True
    elif shared_pool:
        pool = None  # only a shared pool is listed: the record cannot say about a private one
    elif everything:
        pool = False  # a listed feature set that names no pool, and no photo shows one
    prop = rec.get("property") if isinstance(rec.get("property"), dict) else {}
    # isPetFriendly is a default (False on nearly every house), not an answer. An answer is a
    # Pet Policy feature: "No Pets Allowed" says no; "Pets/Cats/Dogs Allowed" or a True flag
    # says yes.
    policy = [n.lower() for n in names.get("Pet Policy", [])]
    flag = _get_any(rec, ["resoValues.isPetFriendly"])
    if any(n.startswith("no pets") for n in policy):
        pets: bool | None = False
    elif flag is True or any(n in ("pets allowed", "cats allowed", "dogs allowed") for n in policy):
        pets = True
    else:
        pets = None
    sold = [
        d
        for d in (
            _date(_first(h, HISTORY_FIELDS["date"]))
            for h in rec.get("history") or []
            if isinstance(h, dict) and _first(h, HISTORY_FIELDS["type"]) == SOLD_UPDATE
        )
        if d
    ]
    parking = features["parking"] if features and features["parking"] is not None else None
    if parking is None:
        parking = _whole(prop.get("totalParkingSpaces"))

    def span(low_key: str, high_key: str, cast: Any) -> tuple[Any, Any] | None:
        low, high = prop.get(low_key), prop.get(high_key)
        low = low if isinstance(low, (int, float)) and not isinstance(low, bool) else high
        high = high if isinstance(high, (int, float)) and not isinstance(high, bool) else low
        if not isinstance(low, (int, float)) or isinstance(low, bool) or low <= 0:
            return None
        return cast(min(low, high)), cast(max(low, high))

    return {
        "floors_photos": _unique(photo_floors),
        "floor_photo_count": floor_photos,
        "floors_listing": _unique(
            [k for k in (floor_kind(n) for n in names.get("Flooring", [])) if k]
        ),
        "laundry_listing": laundry,
        "pool_on_record": pool,
        "parking_spaces": parking,
        "yard_on_record": True
        if yard_photo or any("yard" in n or "fenced" in n for n in everything)
        else None,
        "pets_ok": pets,
        "beds_range": span("bedsMin", "bedsMax", int),
        "baths_range": span("bathsMin", "bathsMax", float),
        "sqft_range": span("sqftMin", "sqftMax", int),
        # other recently sold or off-market listings of this home mean the history is not whole
        "sale_history_known": bool(rec.get("history"))
        and rec.get("hasOtherRecentlySoldOrOffMarketListings") is not True,
        "last_sale": max(sold, default=None),
    }


def _merge_facts(into: PropertyRecord, facts: dict[str, Any]) -> None:
    """Fold a second listing of the same house into its record."""
    for key in ("floors_photos", "floors_listing", "laundry_listing"):
        setattr(into, key, _unique([*getattr(into, key), *facts[key]]))
    into.floor_photo_count += facts["floor_photo_count"]
    if facts["pool_on_record"] is True or into.pool_on_record is None:
        into.pool_on_record = facts["pool_on_record"] or into.pool_on_record
    into.yard_on_record = into.yard_on_record or facts["yard_on_record"]
    if into.parking_spaces is None:
        into.parking_spaces = facts["parking_spaces"]
    if into.pets_ok is None:
        into.pets_ok = facts["pets_ok"]
    elif facts["pets_ok"] is not None and facts["pets_ok"] != into.pets_ok:
        into.pets_ok = None  # two listings disagree: the record gives no answer
    for key in ("beds_range", "baths_range", "sqft_range"):
        old, new = getattr(into, key), facts[key]
        if old is None or new is None:
            setattr(into, key, old or new)
        else:
            setattr(into, key, (min(old[0], new[0]), max(old[1], new[1])))
    into.sale_history_known = into.sale_history_known and facts["sale_history_known"]
    sales = [d for d in (into.last_sale, facts["last_sale"]) if d]
    into.last_sale = max(sales, default=None)


def house_records(
    source: DataSource | None = None, kit_dir: Path | None = None
) -> dict[str, PropertyRecord]:
    """A PropertyRecord for each PUBLIC detached house with a Matterport model, by our id (the kit's
    `propertyId` as text). Lat/lon are the listing's, the models are `_matterport_models`.
    A house on several listings is one record holding every model. Nothing else (price,
    owner, address) is kept: the locator only needs the home's id, models and position."""
    source = source or get_settings().snapback_data_source
    kit = kit_dir or (FIXTURE_KIT if source == DataSource.FIXTURE else DEFAULT_KIT)
    path = _find(kit, RESIDENTIAL_FILE)
    if path is None:
        return {}
    out: dict[str, PropertyRecord] = {}
    features = _features_by_listing(kit)
    for rec in _iter_jsonl(path):
        pid, models = rec.get("propertyId"), _matterport_models(rec)
        if (
            not _public(rec)
            or not models
            or isinstance(pid, bool)
            or not isinstance(pid, int)
            or _get_any(rec, ["property.listingPropertyType"]) != DETACHED
        ):
            continue
        listing_id = rec.get("id")
        facts = _home_facts(rec, features.get(listing_id) if isinstance(listing_id, int) else None)
        found = out.get(str(pid))
        if found is not None:
            found.model_ids = list(dict.fromkeys([*found.model_ids, *models]))
            _merge_facts(found, facts)
            continue
        lat, lon = (
            _get_any(rec, RESIDENTIAL_FIELDS["lat"]),
            _get_any(rec, RESIDENTIAL_FIELDS["lon"]),
        )
        city = _get_any(rec, ["property.address.city"])
        out[str(pid)] = PropertyRecord(
            property_id=str(pid),
            source=source,
            market=city.strip().title() if isinstance(city, str) and city.strip() else None,
            property_type="house",
            lat=float(lat) if isinstance(lat, (int, float)) else None,
            lon=float(lon) if isinstance(lon, (int, float)) else None,
            model_ids=models,
            **facts,
        )
    # A model on more than one house cannot say which house a photo is in, and the catalog
    # would keep the last owner: such a model belongs to none of them, so it can place no
    # photo anywhere (never "elsewhere", never an identification).
    owners = Counter(model for record in out.values() for model in record.model_ids)
    for property_id, record in list(out.items()):
        record.model_ids = [model for model in record.model_ids if owners[model] == 1]
        if not record.model_ids:
            del out[property_id]
    return out


def _whole(value: Any) -> int | None:
    return (
        int(round(value))
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else None
    )


def _coord(value: Any, limit: float) -> float | None:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value) if ok and -limit <= value <= limit else None


def rental_houses(
    source: DataSource | None = None, kit_dir: Path | None = None
) -> list[RentalHouse]:
    """The active house rentals in the kit (search supply): public on Homes.com, a rental
    transaction, `forRentStatus` ForRent and `listingStatus` Active. A Texas home only when the
    record names a state. The asking price is `rentMin`/`rentMax` exactly as listed; no other
    field is kept. Our id is the kit's `propertyId` as text (the same as `house_records`)."""
    source = source or get_settings().snapback_data_source
    kit = kit_dir or (FIXTURE_KIT if source == DataSource.FIXTURE else DEFAULT_KIT)
    path = _find(kit, RESIDENTIAL_FILE)
    if path is None:
        return []
    enums = _load_enums(kit)
    out: dict[str, RentalHouse] = {}
    for rec in _iter_jsonl(path):
        if not _public(rec):
            continue
        transaction = _label(
            enums, "TransactionType", _first(rec, RESIDENTIAL_FIELDS["transaction"])
        )
        rent_status = _label(
            enums, "ForRentStatus", _first(rec, RESIDENTIAL_FIELDS["for_rent_status"])
        )
        code = _get_any(rec, RESIDENTIAL_FIELDS["listing_status"])
        active = _label(enums, "ListingStatus", code) == "active" or str(code) == str(ACTIVE_CODE)
        if "rent" not in transaction or rent_status != "forrent" or not active:
            continue
        state = _get_any(rec, ["property.address.state"])
        if isinstance(state, str) and state.strip().upper() not in ("", "TX"):
            continue
        pid = rec.get("propertyId", rec.get("homeListingId"))
        if pid is None or isinstance(pid, bool):
            continue
        parking = _get_any(rec, ["property.totalParkingSpaces"])
        # a False flag is a default, not an answer (see _home_facts): only True is kept
        pets = True if _get_any(rec, ["resoValues.isPetFriendly"]) is True else None
        baths = _get_any(rec, ["property.bathsMin"])
        beds = _get_any(rec, ["property.bedsMin"])
        offices = _offices(rec)
        out.setdefault(
            str(pid),
            RentalHouse(
                property_id=str(pid),
                source=source,
                beds=_whole(beds),
                baths=float(baths) if isinstance(baths, (int, float)) else None,
                rent_min=_whole(rec.get("rentMin")),
                rent_max=_whole(rec.get("rentMax")),
                pets_ok=pets,
                parking_spaces=_whole(parking),
                available_on=_date(rec.get("availabilityDate")),
                office=offices[0] if offices else None,
                has_scan=bool(_matterport_models(rec)),
                lat=_coord(_get_any(rec, RESIDENTIAL_FIELDS["lat"]), 90),
                lon=_coord(_get_any(rec, RESIDENTIAL_FIELDS["lon"]), 180),
            ),
        )
    return sorted(out.values(), key=lambda h: h.property_id)


def _sold_on(rec: dict[str, Any]) -> date | None:
    """When the home sold: `closeDate`, else the last NewlySold entry in `history[]`."""
    closed = _date(rec.get("closeDate"))
    if closed is not None:
        return closed
    dates = [
        d
        for h in rec.get("history") or []
        if isinstance(h, dict) and h.get("updateType") == NEWLY_SOLD_CODE
        if (d := _date(h.get("date"))) is not None
    ]
    return max(dates, default=None)


def _role(rec: dict[str, Any], enums: dict[str, dict[str, str]], today: date) -> str | None:
    status, _, _ = _status(rec, enums, today)
    if status is ForSaleStatus.ACTIVE and rec.get("forSaleStatus") == FOR_SALE_CODE:
        return "for_sale"
    sold_on = _sold_on(rec)
    is_sale = (
        rec.get("forSaleStatus") == SOLD_CODE or rec.get("transactionType") == TRANSACTION_SALE
    )
    if is_sale and sold_on is not None and 0 <= (today - sold_on).days <= RECENT_DAYS:
        return "recently_sold"
    return None


def _candidates(kit_dir: Path, today: date) -> list[dict[str, Any]] | None:
    """Houston, public, detached homes with a Matterport model, tagged with the role each can
    play. None when the kit has no residential file."""
    path = _find(kit_dir, RESIDENTIAL_FILE)
    if path is None:
        return None
    enums = _load_enums(kit_dir)
    out: list[dict[str, Any]] = []
    rented: set[int] = set()  # a propertyId with ANY recently rented record, in any city
    for rec in _iter_jsonl(path):
        city = _get_any(rec, ["property.address.city"])
        models = _matterport_models(rec)
        pid = rec.get("propertyId")
        if isinstance(pid, int) and _status(rec, enums, today)[0] is ForSaleStatus.RECENTLY_RENTED:
            rented.add(pid)
        if (
            not _public(rec)
            or not isinstance(city, str)
            or city.strip().lower() != CITY
            or _get_any(rec, ["property.listingPropertyType"]) != DETACHED
            or not models
            or not isinstance(pid, int)
        ):
            continue
        zip_code = _get_any(rec, RESIDENTIAL_FIELDS["zip"])
        subdivision = _get_any(rec, ["property.subdivision"])
        out.append(
            {
                "property_id": pid,
                "listing_id": rec.get("residentialListingId") or 0,
                "zip": str(zip_code)[:5] if zip_code else "",
                "subdivision": subdivision.strip().lower() if isinstance(subdivision, str) else "",
                "models": models,
                "role": _role(rec, enums, today),
            }
        )
    return [c for c in out if c["property_id"] not in rented]


def indexed_model_ids(data_dir: Path) -> set[str]:
    """Model ids already in a locate index under `data/index/*/index.json`."""
    found: set[str] = set()
    for path in sorted((Path(data_dir) / "index").glob("*/index.json")):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        found |= {str(e["model_id"]) for e in meta.get("entries", []) if "model_id" in e}
    return found


def _choose(
    pool: list[dict[str, Any]], taken: set[int], indexed: set[str]
) -> tuple[dict[str, Any], int, str] | None:
    """One home per propertyId; indexed twins first, then the smallest propertyId, then the
    smallest listing id, so ties and file order never change the pick."""
    best: dict[int, dict[str, Any]] = {}
    for c in pool:
        if c["property_id"] in taken:
            continue
        cur = best.get(c["property_id"])
        if cur is None or c["listing_id"] < cur["listing_id"]:
            best[c["property_id"]] = c

    def key(c: dict[str, Any]) -> tuple[bool, int]:
        return (not indexed.intersection(c["models"]), c["property_id"])

    if not best:
        return None
    pick = min(best.values(), key=key)
    rule = "indexed twin" if indexed.intersection(pick["models"]) else "first by propertyId"
    return pick, len(best), rule


def pick_demo_houses(
    kit_dir: Path, today: date | None = None, indexed: set[str] | None = None
) -> list[dict[str, Any]] | None:
    """The trio: for_sale, recently_sold, and a decoy (another house with a model in the same
    zip as the for-sale pick). None when the kit has no residential file or a role has no
    candidate. Each entry also carries the rule, candidate count and indexed flag for printing."""
    cands = _candidates(kit_dir, today or date.today())
    if cands is None:
        return None
    indexed = indexed or set()
    picks: list[dict[str, Any]] = []
    taken: set[int] = set()
    zip_code = subdivision = ""
    for role in DEMO_ROLES:
        if role == "decoy":
            pool = [c for c in cands if zip_code and c["zip"] == zip_code]
            if subdivision:  # a different subdivision, until tract twins are proven on real scans
                pool = [c for c in pool if c["subdivision"] and c["subdivision"] != subdivision]
        else:
            pool = [c for c in cands if c["role"] == role]
        chosen = _choose(pool, taken, indexed)
        if chosen is None:
            return None
        pick, count, rule = chosen
        taken.add(pick["property_id"])
        if role == "for_sale":
            zip_code, subdivision = pick["zip"], pick["subdivision"]
        picks.append(
            {
                "propertyId": pick["property_id"],
                "role": role,
                "rule": rule,
                "candidates": count,
                "indexed": bool(indexed.intersection(pick["models"])),
                "models": pick["models"],
            }
        )
    return picks


def write_demo_house(kit_dir: Path, data_dir: Path, today: date | None = None) -> Path | None:
    """Save the trio (propertyId and role only) under data/ (git-ignored) for lane V. Prints
    roles, rules, counts and indexed yes/no: the sponsor terms keep record ids out of logs."""
    kit_dir = Path(kit_dir)
    if _find(kit_dir, RESIDENTIAL_FILE) is None:
        print(f"kit not found ({RESIDENTIAL_FILE})")
        return None
    picks = pick_demo_houses(kit_dir, today, indexed_model_ids(Path(data_dir)))
    if picks is None:
        print("demo house: no Houston, public house with a Matterport model for every role")
        return None
    out = Path(data_dir) / DEMO_HOUSE_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    saved = [{"propertyId": p["propertyId"], "role": p["role"]} for p in picks]
    out.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    for p in picks:
        answer = "yes" if p["indexed"] else "no"
        print(f"{p['role']}: rule={p['rule']}, candidates={p['candidates']}, indexed={answer}")
    print(f"written to {DEMO_HOUSE_SHOWN}")
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    from snapback.safety.paths import resolve_data_dir

    parser = argparse.ArgumentParser(description="Pick the demo houses (#74) from the kit.")
    parser.add_argument("--kit", type=Path, default=DEFAULT_KIT)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="YYYY-MM-DD")
    args = parser.parse_args(argv)
    return 0 if write_demo_house(args.kit, resolve_data_dir(args.data), args.today) else 1


if __name__ == "__main__":
    raise SystemExit(main())
