"""D13 #152: every field an adapter maps must be filled on the fixture, and the fixture must use
the real kit's key names, so a made-up key cannot pass the suite again."""

import json

from snapback.adapters.costar_jsonl import FIXTURE_KIT, load_records
from snapback.contracts import DataSource

REAL_KEYS = {"numBeds", "numBaths", "numStoriesAboveGrade"}
INVENTED_KEYS = {"beds", "baths", "bedrooms", "bathrooms", "numberOfStories", "stories"}


def _keys(obj, found: set[str]) -> set[str]:
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.add(key)
            _keys(value, found)
    elif isinstance(obj, list):
        for value in obj:
            _keys(value, found)
    return found


def test_the_fixture_uses_the_real_kit_key_names():
    keys: set[str] = set()
    for name in ("commercial-property.jsonl", "apartment-listing.jsonl"):
        for line in (FIXTURE_KIT / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                _keys(json.loads(line), keys)
    assert REAL_KEYS <= keys
    assert not (INVENTED_KEYS & keys), INVENTED_KEYS & keys


def test_every_mapped_field_fills_at_least_one_fixture_record():
    records = list(load_records(DataSource.FIXTURE).values())
    n = len(records)
    fills = {
        "floors": sum(r.floors is not None for r in records),
        "year_built": sum(r.year_built is not None for r in records),
        "floor_plans": sum(bool(r.floor_plans) for r in records),
        "floor_plan_rents.beds": sum(
            any(b.beds is not None for b in r.floor_plan_rents) for r in records
        ),
        "units": sum(bool(r.units) for r in records),
        "units.beds": sum(any(u.beds is not None for u in r.units) for r in records),
        "rent range": sum(r.rent_min is not None for r in records),
        "site_phone_hash": sum(r.site_phone_hash is not None for r in records),
        "website_host": sum(r.website_host is not None for r in records),
        "manager_company": sum(r.manager_company is not None for r in records),
        "model_ids": sum(bool(r.model_ids) for r in records),
    }
    empty = [field for field, count in fills.items() if count == 0]
    assert not empty, f"filled on 0 of {n} fixture records: {empty}"
