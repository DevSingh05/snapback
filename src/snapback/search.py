"""Search CoStar's researched places by budget and must-haves (council 4 core).

A renter's `RenterBrief` in, `PlaceMatch` lines out. Code does all of it: the filters, the budget
comparison and the order. No model sees a kit row or picks what is shown.

Rules that never bend:

- The budget is compared with the ASKING price of the floor plan or listing, as CoStar reported
  it (`rent_min`/`rent_max`), never with a band. A floor plan priced per bed is skipped: the
  brief is a whole-unit budget. A missing price end reads "no full price on record" and is never
  counted as within budget.
- Availability is only ever "units reported available as of CoStar's last research". Never
  "available now".
- A must-have the record does not say (pets in an apartment, a missing walk-up flag) is shown as
  "not on record" and never read as a yes or a no. Only a known "no" removes a place.
- Only home facts and the renter's own stated needs appear anywhere. No area, school or people
  words (fair housing).
- Order: fits the budget, then cheapest, then most must-haves met, then the id, so the same kit and
  brief always give the same list.

The kit stays in memory; this module logs and prints no record value.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from snapback.contracts import (
    AS_OF,
    BudgetFit,
    DataSource,
    MustHaveLine,
    PlaceMatch,
    PropertyRecord,
    RentalHouse,
    RenterBrief,
    SearchResponse,
    TourDraft,
)

log = logging.getLogger("snapback.search")

MARKET = "Houston"
APARTMENT_SCAN = "a 3D scan in this building"
HOUSE_SCAN = "a 3D scan in this home"
NO_FULL_PRICE = "No full price on record"
MAX_ALTERNATIVES = 10


class AmbiguousPlace(Exception):
    """Several plans share the label asked for and no plan_key says which one."""


class NoOfficeOnRecord(Exception):
    """The place has no leasing office on record, so no request can be addressed."""


@dataclass(frozen=True)
class _Raw:
    """One priced place before the brief: the facts, in the kit's own terms."""

    kind: str  # "apartment" | "house"
    property_id: str
    floor_plan: str | None
    beds: int | None
    baths: float | None
    rent_min: int | None
    rent_max: int | None
    units_available: int | None = None
    available_on: date | None = None
    is_walkup: bool | None = None
    has_elevator: bool | None = None
    metering: str | None = None
    parking_ratio: float | None = None
    parking_spaces: int | None = None
    pets_ok: bool | None = None
    office: str | None = None
    has_scan: bool = False


def plan_key(raw: _Raw) -> str:
    """Stable within a building: label, both price ends and units reported available."""
    if raw.kind == "house":
        return "house"
    return f"{raw.floor_plan}|{raw.rent_min}|{raw.rent_max}|{raw.units_available}"


def _money(n: int) -> str:
    return f"${n:,}"


def price_text(rent_min: int | None, rent_max: int | None) -> str:
    """ "$1,450 to $1,600 a month as of CoStar's last research", or the no-full-price line."""
    if rent_min is None or rent_max is None:
        return f"{NO_FULL_PRICE} {AS_OF}"
    rent_min, rent_max = min(rent_min, rent_max), max(rent_min, rent_max)
    if rent_min == rent_max:
        return f"{_money(rent_min)} a month {AS_OF}"
    return f"{_money(rent_min)} to {_money(rent_max)} a month {AS_OF}"


def availability_text(raw: _Raw) -> str:
    if raw.kind == "house":
        if raw.available_on is None:
            return "Move-in date: not on record"
        d = raw.available_on
        return f"Listed for move-in from {d.strftime('%b')} {d.day}, {d.year} {AS_OF}"
    n = raw.units_available
    if n is None:
        return "Units available: not on record"
    if n == 0:
        return f"No units reported available {AS_OF}"
    return f"{n} unit{'s' if n != 1 else ''} reported available {AS_OF}"


# --- supply: every priced place the kit holds ------------------------------------------------


def _source_of(lookups: Any) -> DataSource:
    source = getattr(lookups, "source", DataSource.FIXTURE)
    return source if isinstance(source, DataSource) else DataSource(str(source))


def _apartment_raws(record: PropertyRecord) -> list[_Raw]:
    out = []
    for plan in record.floor_plan_rents:
        if plan.per_bed:
            continue  # a per-bed price is never compared with a whole-unit budget
        if plan.rent_min is None and plan.rent_max is None:
            continue  # nothing priced: not a place to show
        out.append(
            _Raw(
                kind="apartment",
                property_id=record.property_id,
                floor_plan=plan.name,
                beds=plan.beds,
                baths=plan.baths,
                rent_min=plan.rent_min,
                rent_max=plan.rent_max,
                units_available=plan.units_available,
                is_walkup=record.is_walkup,
                has_elevator=record.has_elevator,
                metering=record.metering,
                parking_ratio=record.parking_ratio,
                office=record.manager_company,
                has_scan=bool(record.model_ids),
            )
        )
    return out


def _house_raw(house: RentalHouse) -> _Raw | None:
    if house.rent_min is None and house.rent_max is None:
        return None
    return _Raw(
        kind="house",
        property_id=house.property_id,
        floor_plan=None,
        beds=house.beds,
        baths=house.baths,
        rent_min=house.rent_min,
        rent_max=house.rent_max,
        available_on=house.available_on,
        parking_spaces=house.parking_spaces,
        pets_ok=house.pets_ok,
        office=house.office,
        has_scan=house.has_scan,
    )


def _supply(lookups: Any) -> list[_Raw]:
    """Houston apartment floor plans with a reported price, plus active house rentals."""
    live = _source_of(lookups) is DataSource.LIVE
    out: list[_Raw] = []
    records = lookups.records()
    for pid in sorted(records):
        record = records[pid]
        if record.property_type == "house" or not record.floor_plan_rents:
            continue
        if live and record.market != MARKET:
            continue
        out.extend(_apartment_raws(record))
    rentals = getattr(lookups, "rentals", None)
    for house in rentals() if callable(rentals) else []:
        raw = _house_raw(house)
        if raw is not None:
            out.append(raw)
    return out


# --- the brief: fit, must-haves, filters -----------------------------------------------------


def _fit(raw: _Raw, budget: int | None) -> BudgetFit | None:
    """How the ASKING price sits against the budget; None when the place is over budget."""
    lo, hi = raw.rent_min, raw.rent_max
    if lo is not None and hi is not None:
        lo, hi = min(lo, hi), max(lo, hi)
        if budget is None:
            return BudgetFit.NO_BUDGET
        if hi <= budget:
            return BudgetFit.WITHIN
        return BudgetFit.STARTS_WITHIN if lo <= budget else None
    known = lo if lo is not None else hi
    if budget is not None and known is not None and known > budget:
        return None
    return BudgetFit.NO_FULL_PRICE


def _lines(raw: _Raw, brief: RenterBrief) -> list[MustHaveLine]:
    lines: list[MustHaveLine] = []
    if raw.kind == "apartment":
        if raw.is_walkup is True:
            text = "Walk-up building" + (
                "; an elevator is also on record" if raw.has_elevator else ""
            )
            lines.append(
                MustHaveLine(key="walkup", text=text, met=False if brief.needs_no_walkup else None)
            )
        elif raw.is_walkup is False:
            text = "Not a walk-up" + ("; elevator on record" if raw.has_elevator else "")
            lines.append(
                MustHaveLine(key="walkup", text=text, met=True if brief.needs_no_walkup else None)
            )
        else:
            lines.append(MustHaveLine(key="walkup", text="Walk-up or elevator: not on record"))
        if raw.metering == "individual":
            lines.append(
                MustHaveLine(
                    key="utilities",
                    text="Individually metered: the resident usually pays their own utilities "
                    "(confirm with the office)",
                )
            )
        elif raw.metering == "master":
            lines.append(
                MustHaveLine(
                    key="utilities",
                    text="Master metered: utilities may be included or billed back "
                    "(ask the office)",
                )
            )
        else:
            lines.append(MustHaveLine(key="utilities", text="Who pays utilities: not on record"))
        parking = raw.parking_ratio
        lines.append(
            MustHaveLine(
                key="parking",
                text=f"Parking: {parking:g} spaces per unit on record"
                if parking
                else "Parking: not on record",
                met=(True if parking else None) if brief.needs_parking else None,
            )
        )
        lines.append(
            MustHaveLine(
                key="pets",
                text="Pet rules: not in CoStar's record, ask the office",
                met=None,
            )
        )
    else:
        spaces = raw.parking_spaces
        lines.append(
            MustHaveLine(
                key="parking",
                text=f"Parking: {spaces} space{'s' if spaces != 1 else ''} on record"
                if spaces
                else "Parking: not on record",
                met=(True if spaces else None) if brief.needs_parking else None,
            )
        )
        pets_text = {
            True: "Pets welcome per the listing",
            False: "No pets per the listing",
            None: "Pet rules: not on record",
        }
        lines.append(
            MustHaveLine(
                key="pets",
                text=pets_text[raw.pets_ok],
                met=raw.pets_ok if brief.pets else None,
            )
        )
    return lines


def _passes(raw: _Raw, brief: RenterBrief, lines: list[MustHaveLine]) -> bool:
    if brief.beds_min is not None and (raw.beds is None or raw.beds < brief.beds_min):
        return False
    if brief.baths_min is not None and (raw.baths is None or raw.baths < brief.baths_min):
        return False
    if any(line.met is False for line in lines):  # only a known "no" removes a place
        return False
    if brief.move_in_by is not None:
        if (
            raw.kind == "house"
            and raw.available_on is not None
            and raw.available_on > brief.move_in_by
        ):
            return False
        if raw.kind == "apartment" and raw.units_available == 0:
            return False
    return True


def _match(raw: _Raw, brief: RenterBrief, source: DataSource) -> PlaceMatch | None:
    fit = _fit(raw, brief.max_rent_month)
    if fit is None:
        return None
    lines = _lines(raw, brief)
    if not _passes(raw, brief, lines):
        return None
    return PlaceMatch(
        property_id=raw.property_id,
        kind="apartment" if raw.kind == "apartment" else "house",
        floor_plan=raw.floor_plan,
        plan_key=plan_key(raw),
        beds=raw.beds,
        baths=raw.baths,
        rent_min=raw.rent_min,
        rent_max=raw.rent_max,
        budget_fit=fit,
        price_text=price_text(raw.rent_min, raw.rent_max),
        availability_text=availability_text(raw),
        must_haves=lines,
        musts_met=sum(1 for line in lines if line.met is True),
        has_3d_scan=raw.has_scan,
        scan_text=(APARTMENT_SCAN if raw.kind == "apartment" else HOUSE_SCAN)
        if raw.has_scan
        else None,
        office_on_record=raw.office,
        source=source,
    )


_FIT_RANK = {
    BudgetFit.WITHIN: 0,
    BudgetFit.NO_BUDGET: 0,
    BudgetFit.STARTS_WITHIN: 1,
    BudgetFit.NO_FULL_PRICE: 2,
}


def order_key(match: PlaceMatch) -> tuple[Any, ...]:
    """Fits the budget, then cheapest, then most must-haves met, then ids (so it is stable)."""
    lows = [p for p in (match.rent_min, match.rent_max) if p is not None]
    return (
        _FIT_RANK[match.budget_fit],
        min(lows) if lows else 0,
        -match.musts_met,
        match.property_id,
        match.floor_plan or "",
        match.rent_max if match.rent_max is not None else 0,
    )


def _all_matches(brief: RenterBrief, lookups: Any) -> tuple[int, list[PlaceMatch]]:
    source = _source_of(lookups)
    supply = _supply(lookups)
    matches = [m for raw in supply if (m := _match(raw, brief, source)) is not None]
    matches.sort(key=order_key)
    return len(supply), matches


def search_places(brief: RenterBrief, lookups: Any) -> list[PlaceMatch]:
    """The places that fit the brief, in code order, at most `brief.max_results`."""
    return _all_matches(brief, lookups)[1][: brief.max_results]


def search(brief: RenterBrief, lookups: Any) -> SearchResponse:
    """`search_places` with the counts the screen shows beside it (n is always printed)."""
    considered, matches = _all_matches(brief, lookups)
    return SearchResponse(
        source=_source_of(lookups),
        n_considered=considered,
        n_matches=len(matches),
        matches=matches[: brief.max_results],
    )


def place_for(
    property_id: str,
    floor_plan: str | None,
    lookups: Any,
    brief: RenterBrief | None = None,
    plan_key_: str | None = None,
) -> PlaceMatch | None:
    """One place by id, whatever the budget: the renter picked it. A plan is found by its
    `plan_key`; with only a label it must be unique in the building, else `AmbiguousPlace`."""
    found = place_and_raw_for(property_id, floor_plan, lookups, brief, plan_key_)
    return found[0] if found else None


def place_and_raw_for(
    property_id: str,
    floor_plan: str | None,
    lookups: Any,
    brief: RenterBrief | None = None,
    plan_key_: str | None = None,
) -> tuple[PlaceMatch, _Raw] | None:
    """`place_for`, plus the record facts the match was made from (the tour-prep pack needs
    the numbers, not just the lines of text)."""
    source = _source_of(lookups)
    # Only the renter's stated needs shape the must-have lines; no budget or size removes it.
    needs = brief or RenterBrief()
    open_brief = RenterBrief(pets=needs.pets, needs_parking=needs.needs_parking, max_results=50)
    found = [
        (m, raw)
        for raw in _supply(lookups)
        if raw.property_id == property_id
        and (plan_key_ is None or plan_key(raw) == plan_key_)
        and (floor_plan is None or raw.floor_plan == floor_plan)
        if (m := _match(raw, open_brief, source)) is not None
    ]
    if plan_key_ is None and len({m.plan_key for m, _ in found}) > 1:  # no silent cheapest pick
        raise AmbiguousPlace(property_id)
    found.sort(key=lambda pair: order_key(pair[0]))
    return found[0] if found else None


# --- alternatives for a checked ad ------------------------------------------------------------


def ad_facts(case: Any) -> tuple[int | None, int | None, str | None]:
    """The checked ad's rent, beds and building id, from the case (no listing text is kept)."""
    listing = getattr(case, "listing", None)
    evidence = getattr(case, "evidence", None)
    price = getattr(evidence, "price", None)
    rent = getattr(listing, "listed_rent", None) or getattr(price, "listed_rent", None)
    beds = getattr(listing, "beds", None)
    if beds is None:
        beds = getattr(price, "compared_beds", None)
    return rent, beds, getattr(case, "property_id", None)


def alternatives_for(
    case: Any, brief: RenterBrief | None, lookups: Any, n: int = 3
) -> list[PlaceMatch]:
    """Up to `n` places near a checked ad's price and size, never the ad's own building.

    The renter's brief wins where it speaks; the ad fills what it leaves out: the budget is the
    ad's rent, and the size is the ad's beds. Closest to the ad's price first."""
    rent, beds, own = ad_facts(case)
    brief = brief or RenterBrief()
    budget = brief.max_rent_month if brief.max_rent_month is not None else rent
    if budget is None:
        return []  # nothing to anchor on: no guess
    want_beds = brief.beds_min if brief.beds_min is not None else beds
    widened = brief.model_copy(
        update={"max_rent_month": budget, "beds_min": want_beds, "max_results": 50}
    )
    _, matches = _all_matches(widened, lookups)
    near = [
        m
        for m in matches
        if m.property_id != own
        and (beds is None or m.beds is None or m.beds == beds or brief.beds_min is not None)
        and m.budget_fit in (BudgetFit.WITHIN, BudgetFit.NO_BUDGET, BudgetFit.STARTS_WITHIN)
    ]
    anchor = rent if rent is not None else budget
    near.sort(
        key=lambda m: (
            abs((m.rent_max if m.rent_max is not None else m.rent_min or 0) - anchor),
            *order_key(m),
        )
    )
    return near[: max(0, min(n, MAX_ALTERNATIVES))]


# --- the tour request draft -------------------------------------------------------------------


def draft_tour_request(place: PlaceMatch, brief: RenterBrief | None = None) -> TourDraft:
    """A draft to the leasing office on record, for the renter to approve. Never sent.

    Addressed only to the office's company name: no phone digits, no poster, no person. It asks
    for a tour and for the application fee, because we hold no fees. Raises `NoOfficeOnRecord`
    when the place has none."""
    office = (place.office_on_record or "").strip()
    if not office:
        raise NoOfficeOnRecord(place.property_id)
    brief = brief or RenterBrief()
    what = (
        "the home"
        if place.kind == "house"
        else f"the {place.floor_plan or 'floor plan'} floor plan"
    )
    when = ""
    if brief.move_in_by is not None:
        d = brief.move_in_by
        when = f" I hope to move in by {d.strftime('%b')} {d.day}, {d.year}."
    asks = [
        "1. The application fee, and any other amount due when I apply.",
        "2. Whether a place like this is available" + (" by then." if when else "."),
    ]
    if brief.pets:
        asks.append(f"{len(asks) + 1}. Your pet rules and any pet fees.")
    text = "\n".join(
        [
            f"To: {office}",
            "",
            "Hello,",
            "",
            f"I am a renter interested in {what}, listed at {place.price_text}. "
            f"I would like to arrange a tour.{when}",
            "",
            "Before I apply, could you tell me:",
            *asks,
            "",
            "Please reply with times that work for a tour. I have not paid anything, "
            "and I will not pay before I have seen the place.",
        ]
    )
    return TourDraft(
        property_id=place.property_id, addressee=office, text=text, source=place.source
    )
