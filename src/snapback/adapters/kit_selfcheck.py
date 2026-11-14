"""Run every lane D adapter once on a kit and print counts only (the 02:55 rule, #116/#152).

So the machine that has the real kit can show that no merged lane D code reads made-up keys, and
show before/after counts for a key fix:
    uv run python -m snapback.adapters.kit_selfcheck --kit data/raw/costar/costar-hackathon-kit
Every value printed is an integer and every key a lowercase identifier: never an id, a name, an
address or a URL. A count that fills 0 of n records is listed under `zero_fill` (name: 0), the bug
this check exists to catch.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from snapback.adapters import costar_jsonl, costar_residential
from snapback.contracts import DataSource

SAMPLE = 200  # residential addresses run through the D7 lookup
HOUSTON = "Houston"


def commercial_counts(kit: Path) -> dict[str, int]:
    try:
        records = list(costar_jsonl.load_records(DataSource.LIVE, kit_dir=kit).values())
    except costar_jsonl.KitNotFoundError:
        return {"records": 0}
    plans = [b for r in records for b in r.floor_plan_rents]
    units = [u for r in records for u in r.units]
    return {
        "records": len(records),
        "in_houston": sum(r.market == HOUSTON for r in records),
        "with_model_ids": sum(bool(r.model_ids) for r in records),
        "with_floors": sum(r.floors is not None for r in records),
        "with_year_built": sum(r.year_built is not None for r in records),
        "with_floor_plans": sum(bool(r.floor_plans) for r in records),
        "rent_bands": len(plans),
        "rent_bands_with_beds": sum(b.beds is not None for b in plans),
        "rent_bands_per_bed": sum(b.per_bed for b in plans),
        "with_rent_range": sum(r.rent_min is not None for r in records),
        "units": len(units),
        "units_with_beds": sum(u.beds is not None for u in units),
        "with_site_phone_hash": sum(r.site_phone_hash is not None for r in records),
        "with_website_host": sum(r.website_host is not None for r in records),
        "with_manager_company": sum(r.manager_company is not None for r in records),
    }


def residential_counts(kit: Path, today: date) -> dict[str, Any]:
    path = costar_jsonl._find(kit, costar_residential.RESIDENTIAL_FILE)
    if path is None:
        return {"records": 0}
    enums = costar_jsonl._load_enums(kit)
    houses = list(costar_jsonl._iter_jsonl(path))
    public = [h for h in houses if costar_residential._public(h)]
    statuses = Counter(costar_residential._status(h, enums, today)[0].value for h in public)
    lookups: Counter[str] = Counter()
    for h in public[:SAMPLE]:
        street = costar_jsonl._first(h, costar_residential.RESIDENTIAL_FIELDS["street"])
        if isinstance(street, str):
            match = costar_residential.for_sale_lookup(street, DataSource.LIVE, kit, today)
            lookups[match.status.value if match else "not_looked_up"] += 1

    def houston(h: dict[str, Any]) -> bool:
        city = costar_jsonl._get_any(h, ["property.address.city"])
        return isinstance(city, str) and city.strip().lower() == costar_residential.CITY

    return {
        "records": len(houses),
        "public": len(public),
        "with_media_model": sum(bool(costar_residential._matterport_models(h)) for h in public),
        "houston": sum(houston(h) for h in public),
        "status": dict(statuses),
        "d7_lookup_on_own_address_sample": dict(lookups),
    }


def demo_house_counts(kit: Path, today: date) -> dict[str, Any]:
    """The #151 picker: how many houses can play each role, and whether a trio is found."""
    candidates = costar_residential._candidates(kit, today)
    if candidates is None:
        return {"candidates": 0, "by_role": {}, "trio_found": 0}
    roles = Counter(c["role"] or "none" for c in candidates)
    trio = costar_residential.pick_demo_houses(kit, today)
    return {"candidates": len(candidates), "by_role": dict(roles), "trio_found": int(bool(trio))}


MULTIFAMILY = "multifamily"
SINCE_MAY = date(2026, 5, 1)


def ad_vs_record_counts(kit: Path, today: date) -> dict[str, int]:
    """What an ad can be held to, as counts: houses with room labels, listing features and
    sale history, and buildings with a property-manager start or a sale in the last 12 months."""
    out: dict[str, int] = {}
    houses = costar_residential.house_records(DataSource.LIVE, kit)
    rows = list(houses.values())
    out["houses"] = len(rows)
    out["houses_with_floor_photos"] = sum(bool(h.floors_photos) for h in rows)
    out["houses_with_two_floor_photos"] = sum(h.floor_photo_count >= 2 for h in rows)
    out["houses_with_listing_floors"] = sum(bool(h.floors_listing) for h in rows)
    out["houses_with_laundry_features"] = sum(bool(h.laundry_listing) for h in rows)
    out["houses_with_pool_answer"] = sum(h.pool_on_record is not None for h in rows)
    out["houses_with_parking_count"] = sum(h.parking_spaces is not None for h in rows)
    out["houses_with_pets_answer"] = sum(h.pets_ok is not None for h in rows)
    out["houses_with_beds"] = sum(h.beds_range is not None for h in rows)
    out["houses_with_sale_history"] = sum(h.sale_history_known for h in rows)
    # The demo trio (for sale, recently sold, decoy), if one is found: do they have labels?
    trio = costar_residential.pick_demo_houses(kit, today) or []
    out["demo_houses"] = len(trio)
    out["demo_houses_with_floor_photos"] = sum(
        bool(houses.get(str(pick["propertyId"])) and houses[str(pick["propertyId"])].floors_photos)
        for pick in trio
    )
    path = costar_jsonl._find(kit, costar_residential.RESIDENTIAL_FILE)
    if path is not None:
        raw = list(costar_jsonl._iter_jsonl(path))
        media = [m for h in raw for m in h.get("media") or [] if isinstance(m, dict)]
        out["listing_photos_with_room_labels"] = sum(bool(m.get("scenes")) for m in media)
        out["listing_photos_with_keywords"] = sum(
            bool(m.get("computerVisionKeywords")) for m in media
        )
    try:
        buildings = list(costar_jsonl.load_records(DataSource.LIVE, kit_dir=kit).values())
    except costar_jsonl.KitNotFoundError:
        return out
    cutoff = today - timedelta(days=365)
    out["buildings"] = len(buildings)
    out["buildings_with_manager_start"] = sum(b.manager_since is not None for b in buildings)
    out["buildings_manager_started_in_12_months"] = sum(
        b.manager_since is not None and b.manager_since >= cutoff for b in buildings
    )
    out["buildings_with_sale_history"] = sum(b.sale_history_known for b in buildings)
    out["buildings_sold_in_12_months"] = sum(
        b.last_sale is not None and b.last_sale >= cutoff for b in buildings
    )
    out["multifamily_sold_since_may_2026"] = sum(
        b.property_type == MULTIFAMILY and b.last_sale is not None and b.last_sale >= SINCE_MAY
        for b in buildings
    )
    return out


def _zero_fill(section: str, counts: dict[str, Any]) -> dict[str, int]:
    """Every count that came back empty: an int of 0, or a dict of counts with nothing in it."""
    if not counts.get("records"):
        return {}
    empty = {}
    for key, value in counts.items():
        if key == "records":
            continue
        if (isinstance(value, int) and value == 0) or (isinstance(value, dict) and not value):
            empty[f"{section}_{key}"] = 0
    return empty


def selfcheck(kit: Path, today: date) -> dict[str, Any]:
    commercial = commercial_counts(kit)
    residential = residential_counts(kit, today)
    if not commercial["records"] and not residential["records"]:
        raise costar_jsonl.KitNotFoundError("no kit files")
    demo = demo_house_counts(kit, today)
    zero = _zero_fill("commercial", commercial) | _zero_fill("residential", residential)
    if residential["records"] and not demo["candidates"]:
        zero["demo_house_candidates"] = 0
    return {
        "commercial": commercial,
        "residential": residential,
        "demo_house": demo,
        "ad_vs_record": ad_vs_record_counts(kit, today),
        "zero_fill": zero,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Lane D adapters on a kit: counts only.")
    parser.add_argument("--kit", type=Path, default=costar_jsonl.DEFAULT_KIT)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    try:
        print(json.dumps(selfcheck(args.kit, args.today), indent=2))
    except costar_jsonl.KitNotFoundError:
        print("kit not found (commercial-property.jsonl or residential-listings.jsonl)")
        sys.exit(1)


if __name__ == "__main__":
    main()
