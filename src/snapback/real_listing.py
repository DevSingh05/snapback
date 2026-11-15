"""The real listing: the ad's building as CoStar's record has it, beside what the ad says.

A pure function of what the modules found and the records already read. Code only, no model.
Rules held here:
- the building the photos were placed in wins when it is not the claimed one;
- plans are narrowed to the ad's unit or beds first, then per-bed plans are left out (as
  `check_price` does: a per-bed price is never compared with a whole-unit rent);
- a fixture case always shows its (synthetic) figures; a LIVE case shows rents, units and the
  building's name only when `Settings.snapback_show_record_figures` is on (the local demo), else
  company, host and counts. The "See the real listing" hand-off link shows either way;
- no phone number and no street address ever leaves here, and the office phone is yes / no.
"""

from snapback.agent.rules.apply import _plans_to_compare
from snapback.agent.rules.table import BELOW_RANGE_RATIO
from snapback.card import strings
from snapback.contracts import (
    DataSource,
    FloorPlanRent,
    LocateStatus,
    ModuleEvidence,
    PhoneMatch,
    PropertyRecord,
    RealListing,
    RealListingPlan,
)
from snapback.settings import Settings
from snapback.verdict import _PAYMENT_CATEGORIES

MAX_PLANS = 6


def _host_of(url: str | None) -> str | None:
    if not url:
        return None
    return url.split("//", 1)[-1].split("/", 1)[0].lower().removeprefix("www.") or None


def figures_visible(source: DataSource, settings: Settings) -> bool:
    """Fixture data is synthetic and always shows. Live record figures need the local-demo flag."""
    return source is DataSource.FIXTURE or settings.snapback_show_record_figures


def _money(value: int) -> str:
    return f"${value:,}"


def _plan_name(plan: RealListingPlan, lang: str) -> str:
    if plan.name:
        return plan.name
    if plan.beds == 0:
        return strings.text("real.plan_studio", lang)
    if plan.beds is not None:
        return strings.text("real.plan_beds", lang, beds=plan.beds)
    return strings.text("real.plan_unnamed", lang)


def _headline(
    ad_rent: int | None,
    irreversible: bool,
    plans: list[RealListingPlan],
    company: str | None,
    host: str | None,
    figures: bool,
    lang: str,
) -> str:
    parts = [
        strings.text("real.ad_rent", lang, ad_rent=_money(ad_rent))
        if ad_rent
        else strings.text("real.ad_no_rent", lang)
    ]
    if irreversible:
        parts.append(strings.text("real.ad_irreversible", lang))
    lows = [p.rent_min if p.rent_min is not None else p.rent_max for p in plans]
    highs = [p.rent_max if p.rent_max is not None else p.rent_min for p in plans]
    lows = [v for v in lows if v]
    highs = [v for v in highs if v]
    if figures and lows and highs:
        low, high = min(lows), max(highs)
        band = (
            _money(low)
            if low == high
            else strings.text("real.range", lang, low=_money(low), high=_money(high))
        )
        if len(plans) == 1:
            parts.append(
                strings.text("real.record_one", lang, band=band, plan=_plan_name(plans[0], lang))
            )
        else:
            parts.append(strings.text("real.record_many", lang, band=band, n=len(plans)))
    elif not figures and plans:
        parts.append(strings.text("real.record_hidden", lang))
    elif not figures:
        parts.append(strings.text("real.record_no_plan", lang))
    else:
        parts.append(strings.text("real.record_no_rent", lang))
    if company:
        parts.append(strings.text("real.managed_by", lang, company=company))
    if host:
        parts.append(strings.text("real.website", lang, host=host))
    return " ".join(parts)


def _whole_unit_plans(
    record: PropertyRecord, unit: str | None, beds: int | None
) -> list[FloorPlanRent]:
    """The ad's own floor plans on the record, narrowed first and per-bed ones dropped after, in
    the order `check_price` uses: a unit in a per-bed plan matches no whole-unit plan."""
    narrowed = _plans_to_compare(record.floor_plan_rents, unit, beds, record)
    return [p for p in narrowed if not p.per_bed]


def _plans(
    record: PropertyRecord, beds: int | None, unit: str | None, figures: bool
) -> list[RealListingPlan]:
    ours = _whole_unit_plans(record, unit, beds)
    out = []
    for plan in ours[:MAX_PLANS]:
        out.append(
            RealListingPlan(
                name=plan.name,
                beds=plan.beds,
                baths=plan.baths,
                rent_min=plan.rent_min if figures else None,
                rent_max=plan.rent_max if figures else None,
                units_available=plan.units_available if figures else None,
                availability_host=_host_of(plan.availability_url) if figures else None,
            )
        )
    return out


def _cta(record: PropertyRecord, plans: list[FloorPlanRent]) -> str | None:
    """Where the renter goes to see the real listing: the availability link on the record, else
    the building's own site. The hand-off shows whenever the record has a link, with the
    figures flag on or off: it is where the renter goes, not a rent. Only rents, units and
    the building's name stay behind the flag."""
    for plan in plans:
        if plan.availability_url:
            return plan.availability_url
    if record.availability_url:
        return record.availability_url
    if record.website_host:
        return f"https://{record.website_host}"
    return None


def real_listing(
    modules: ModuleEvidence,
    claimed: PropertyRecord | None,
    matched: PropertyRecord | None,
    settings: Settings,
    *,
    ad_beds: int | None = None,
    ad_unit: str | None = None,
    lang: str = strings.DEFAULT_LANG,
) -> RealListing | None:
    """The panel's content, or None when there is no record to show (neither building)."""
    which, record = ("matched", matched) if matched is not None else ("claimed", claimed)
    if record is None:
        return None
    figures = figures_visible(modules.source, settings)

    photos = modules.locate.photos if modules.locate else []
    if which == "matched":
        in_scan = sum(
            1
            for ph in photos
            if ph.status is LocateStatus.LOCATED_ELSEWHERE
            and ph.matched_property_id == record.property_id
        )
    else:
        in_scan = sum(1 for ph in photos if ph.status is LocateStatus.LOCATED_IN_CLAIMED)

    ad_rent = modules.price.listed_rent if modules.price else None
    irreversible = any(h.red_flag and h.category in _PAYMENT_CATEGORIES for h in modules.rules)
    # The office phone on record belongs to the building the ad names; it says nothing about
    # the building the photos were placed in.
    phone = PhoneMatch.NOT_CHECKED
    if which == "claimed" and modules.authority is not None:
        phone = modules.authority.office_phone_match

    plans = _plans(record, ad_beds, ad_unit, figures)
    raw_ours = _whole_unit_plans(record, ad_unit, ad_beds)[:MAX_PLANS]

    if not photos:
        provenance = None
    elif which == "matched":
        provenance = strings.text("real.provenance_elsewhere", lang, n=in_scan, m=len(photos))
    elif in_scan:
        provenance = strings.text("real.provenance_scan", lang, n=in_scan, m=len(photos))
    else:
        provenance = strings.text("real.provenance_none", lang, m=len(photos))
    phone_line = {
        PhoneMatch.YES: strings.text("real.phone_office", lang),
        PhoneMatch.NO: strings.text("real.phone_not_office", lang),
        PhoneMatch.NOT_CHECKED: None,
    }[phone]
    cta = _cta(record, raw_ours)

    return RealListing(
        case_id=modules.case_id,
        source=modules.source,
        property_id=record.property_id,
        which=which,
        building_name=record.building_name if figures else None,
        manager_company=record.manager_company,
        website_host=record.website_host,
        plans=plans,
        photos_in_scan=in_scan,
        photos_total=len(photos),
        ad_rent=ad_rent,
        ad_asks_irreversible=irreversible,
        phone_is_office=phone,
        figures_shown=figures,
        as_of=strings.text("real.as_of", lang),
        headline=_headline(
            ad_rent, irreversible, plans, record.manager_company, record.website_host, figures, lang
        ),
        provenance=provenance,
        phone_line=phone_line,
        cta_label=strings.text("real.cta", lang) if cta else None,
        cta_url=cta,
    )


def rent_percent_under(
    record: PropertyRecord, ad_rent: int | None, beds: int | None, unit: str | None
) -> int | None:
    """How far the ad's rent is under the lowest matching whole-unit plan on the record, as a
    whole percent, when it is under by the same bar the rent check uses. The percent is ours; the
    record's rents are not returned."""
    if not ad_rent:
        return None
    lows = [
        p.rent_min if p.rent_min is not None else p.rent_max
        for p in _whole_unit_plans(record, unit, beds)
    ]
    lows = [v for v in lows if v]
    if not lows:
        return None
    low = min(lows)
    if ad_rent >= BELOW_RANGE_RATIO * low:
        return None
    return round(100 * (low - ad_rent) / low)
