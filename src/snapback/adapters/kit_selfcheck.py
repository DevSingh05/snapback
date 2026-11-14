"""Run every lane D adapter once on a kit and print counts only (the 02:55 rule, #116/#152).

So the machine that has the real kit can show that no merged lane D code reads made-up keys, and
show before/after counts for a key fix:
    uv run python -m snapback.adapters.kit_selfcheck --kit data/raw/costar/costar-hackathon-kit
Prints numbers only: never an id, a name, an address or a URL. A mapped field that fills 0 of n
records is listed under `zero_fill`, which is the bug this check exists to catch.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from snapback.adapters import costar_jsonl, costar_residential
from snapback.contracts import DataSource

SAMPLE = 200  # residential addresses run through the D7 lookup
MATTERPORT_TYPES = {36, 234}


def _media_models(rec: dict[str, Any]) -> int:
    media = rec.get("media") or []
    return sum(
        isinstance(m, dict)
        and m.get("externalReferenceType") in MATTERPORT_TYPES
        and bool(m.get("videoKey"))
        for m in media
    )


def commercial_counts(kit: Path) -> dict[str, int]:
    records = list(costar_jsonl.load_records(DataSource.LIVE, kit_dir=kit).values())
    plans = [b for r in records for b in r.floor_plan_rents]
    units = [u for r in records for u in r.units]
    return {
        "records": len(records),
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
    return {
        "records": len(houses),
        "public": len(public),
        "with_media_model": sum(_media_models(h) > 0 for h in houses),
        "status": dict(statuses),
        "d7_lookup_on_own_address_sample": dict(lookups),
    }


def selfcheck(kit: Path, today: date) -> dict[str, Any]:
    commercial = commercial_counts(kit)
    residential = residential_counts(kit, today)
    zero = [k for k, v in commercial.items() if k != "records" and v == 0 and commercial["records"]]
    return {"commercial": commercial, "residential": residential, "zero_fill": zero}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Lane D adapters on a kit: counts only.")
    parser.add_argument("--kit", type=Path, default=costar_jsonl.DEFAULT_KIT)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    try:
        print(json.dumps(selfcheck(args.kit, args.today), indent=2))
    except costar_jsonl.KitNotFoundError:
        print("kit not found (commercial-property.jsonl)")
        sys.exit(1)


if __name__ == "__main__":
    main()
