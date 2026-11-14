"""CoStar kit adapter (lane D, D1): kit JSONL records in, `PropertyRecord` out.

Fixture and live run the same parser. Fixture reads the synthetic kit in `fixtures/adapters/`;
live reads the real kit, unzipped under `data/` (git-ignored). Sponsor values stay in memory and
in `data/`; nothing here logs or prints a record value.

Kit facts used here (from the #5 probe): null fields are omitted, so every read is a `.get`;
enum 0 means unknown; `propertyType` 11 is multifamily; Matterport model ids are
`attachments[].videoKey` where `videoExternalReferenceType` is 36 or 234; rent ranges, floor plans
and the manager company live in `apartment-listing.jsonl`.

Field paths not yet confirmed against the kit are listed as candidates in `FIELDS` (first present
wins). Run `uv run python -m snapback.adapters.costar_jsonl --coverage` on the real kit to see how
many records each path fills. It prints counts and key paths only, so it is safe to paste.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from snapback.contracts import DataSource, PropertyRecord
from snapback.settings import get_settings

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_KIT = REPO_ROOT / "fixtures" / "adapters" / "costar-kit"
DEFAULT_KIT = REPO_ROOT / "data" / "raw" / "costar" / "costar-hackathon-kit"

PROPERTY_FILE = "commercial-property.jsonl"
LISTING_FILE = "apartment-listing.jsonl"

MATTERPORT_REF_TYPES = {36, 234}
PROPERTY_TYPES = {11: "multifamily"}
MARKETS = {14: "Houston", 20: "Los Angeles"}

# Candidate key paths per output field, first present wins. Dotted paths walk nested objects.
FIELDS: dict[str, list[str]] = {
    "property_id": ["propertyId", "id"],
    "floors": ["numberOfStories", "stories", "buildingStories", "floors"],
    "year_built": ["yearBuilt", "builtYear"],
    "lat": ["primaryAddress.latitude", "location.latitude", "latitude"],
    "lon": ["primaryAddress.longitude", "location.longitude", "longitude"],
    "market_name": ["primaryAddress.researchMarketName", "researchMarketName"],
    "market_id": ["primaryAddress.researchMarketId", "researchMarketId"],
    "property_type": ["propertyType"],
}
LISTING_FIELDS: dict[str, list[str]] = {
    "property_id": ["propertyId", "commercialPropertyId"],
    "manager_company": ["propertyManagementCompanyName"],
    "rent_min": ["minRent"],
    "rent_max": ["maxRent"],
    "models": ["apartmentModels"],
}
MODEL_FIELDS: dict[str, list[str]] = {
    "beds": ["beds", "bedrooms", "bedroomCount"],
    "baths": ["baths", "bathrooms", "bathroomCount"],
    "rent_min": ["minRent"],
    "rent_max": ["maxRent"],
}


class KitNotFoundError(FileNotFoundError):
    """Live mode was asked for but the CoStar kit is not on this machine."""


def _get(obj: dict[str, Any], path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _present(value: Any) -> bool:
    """Missing, null, empty and enum 0 all mean unknown."""
    return value not in (None, "", [], {}) and not (isinstance(value, int | float) and value == 0)


def _first(obj: dict[str, Any], paths: list[str]) -> Any:
    for path in paths:
        value = _get(obj, path)
        if _present(value):
            return value
    return None


def _as_int(value: Any) -> int | None:
    try:
        return int(round(float(value))) if _present(value) else None
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _num(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


def _model_ids(record: Any) -> list[str]:
    found: list[str] = []

    def visit(o: Any) -> None:
        if isinstance(o, dict):
            if o.get("videoExternalReferenceType") in MATTERPORT_REF_TYPES and o.get("videoKey"):
                found.append(str(o["videoKey"]))
            for v in o.values():
                visit(v)
        elif isinstance(o, list):
            for v in o:
                visit(v)

    visit(record)
    return list(dict.fromkeys(found))


def _floor_plan(model: dict[str, Any]) -> str | None:
    """ "2 bed / 2 bath": model units per floor plan, never a unit number."""
    beds = _as_float(_get_any(model, MODEL_FIELDS["beds"]))
    baths = _as_float(_first(model, MODEL_FIELDS["baths"]))
    if baths is None:
        return None
    bed_text = "studio" if not beds else f"{_num(beds)} bed"
    return f"{bed_text} / {_num(baths)} bath"


def _get_any(obj: dict[str, Any], paths: list[str]) -> Any:
    """Like `_first`, but 0 is a real value here (0 beds is a studio)."""
    for path in paths:
        value = _get(obj, path)
        if value is not None:
            return value
    return None


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue  # counted by the probe; one bad line never drops the file
            if isinstance(obj, dict):
                yield obj


def _find(kit_dir: Path, name: str) -> Path | None:
    for candidate in (kit_dir / "data" / name, kit_dir / name):
        if candidate.is_file():
            return candidate
    return next(iter(sorted(kit_dir.rglob(name))), None) if kit_dir.is_dir() else None


def _listings(kit_dir: Path) -> dict[str, dict[str, Any]]:
    path = _find(kit_dir, LISTING_FILE)
    if path is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for obj in _iter_jsonl(path):
        pid = _first(obj, LISTING_FIELDS["property_id"])
        if pid is not None:
            out.setdefault(str(pid), obj)
    return out


def _apply_listing(fields: dict[str, Any], listing: dict[str, Any]) -> None:
    models = [m for m in (_first(listing, LISTING_FIELDS["models"]) or []) if isinstance(m, dict)]
    plans = [p for p in (_floor_plan(m) for m in models) if p]
    fields["floor_plans"] = list(dict.fromkeys(plans))

    company = _first(listing, LISTING_FIELDS["manager_company"])
    fields["manager_company"] = str(company) if company is not None else None

    lows = [_as_int(_first(m, MODEL_FIELDS["rent_min"])) for m in models]
    highs = [_as_int(_first(m, MODEL_FIELDS["rent_max"])) for m in models]
    mids = [(lo + hi) / 2 for lo, hi in zip(lows, highs, strict=True) if lo and hi]
    rent_min = _as_int(_first(listing, LISTING_FIELDS["rent_min"])) or min(
        (x for x in lows if x), default=None
    )
    rent_max = _as_int(_first(listing, LISTING_FIELDS["rent_max"])) or max(
        (x for x in highs if x), default=None
    )
    fields["rent_min"] = rent_min
    fields["rent_max"] = rent_max
    fields["rent_median"] = _as_int(statistics.median(mids)) if mids else None


def parse_record(
    record: dict[str, Any], source: DataSource, listing: dict[str, Any] | None = None
) -> PropertyRecord | None:
    """One kit record (plus its apartment listing, if any) to a `PropertyRecord`."""
    pid = _first(record, FIELDS["property_id"])
    if pid is None:
        return None
    ptype = _as_int(_first(record, FIELDS["property_type"]))
    market_name = _first(record, FIELDS["market_name"])
    market_id = _as_int(_first(record, FIELDS["market_id"]))
    market = str(market_name) if market_name else MARKETS.get(market_id or -1)
    if market is None and market_id is not None:
        market = f"market {market_id}"

    fields: dict[str, Any] = {
        "property_id": str(pid),
        "source": source,
        "market": market,
        "property_type": PROPERTY_TYPES.get(ptype, f"type {ptype}") if ptype else None,
        "floors": _as_int(_first(record, FIELDS["floors"])),
        "year_built": _as_int(_first(record, FIELDS["year_built"])),
        "lat": _as_float(_get_any(record, FIELDS["lat"])),
        "lon": _as_float(_get_any(record, FIELDS["lon"])),
        "model_ids": _model_ids(record),
    }
    if listing is not None:
        _apply_listing(fields, listing)
    return PropertyRecord(**fields)


def load_records(
    source: DataSource | None = None, kit_dir: Path | None = None
) -> dict[str, PropertyRecord]:
    """Every record in the kit by our property id. `source` defaults to SNAPBACK_DATA_SOURCE."""
    source = source or get_settings().snapback_data_source
    kit = kit_dir or (FIXTURE_KIT if source == DataSource.FIXTURE else DEFAULT_KIT)
    path = _find(kit, PROPERTY_FILE)
    if path is None:
        raise KitNotFoundError(
            f"SNAPBACK_DATA_SOURCE={source.value} but {PROPERTY_FILE} is not under {kit}. "
            "Download and unzip the CoStar kit there (README, 'Get the CoStar kit'), "
            "or set SNAPBACK_DATA_SOURCE=fixture."
        )
    listings = _listings(kit)
    out: dict[str, PropertyRecord] = {}
    for obj in _iter_jsonl(path):
        pid = _first(obj, FIELDS["property_id"])
        rec = parse_record(obj, source, listings.get(str(pid)) if pid is not None else None)
        if rec is not None:
            out.setdefault(rec.property_id, rec)
    return out


def get_record(property_id: str, source: DataSource | None = None) -> PropertyRecord | None:
    return load_records(source).get(property_id)


def coverage(kit_dir: Path) -> dict[str, Any]:
    """How many records each candidate path fills. Counts and key paths only, never values."""
    path = _find(kit_dir, PROPERTY_FILE)
    if path is None:
        raise KitNotFoundError(f"{PROPERTY_FILE} is not under {kit_dir}")
    fields = {name: dict.fromkeys(paths, 0) for name, paths in FIELDS.items()}
    records = with_models = 0
    for obj in _iter_jsonl(path):
        records += 1
        with_models += bool(_model_ids(obj))
        for name, paths in FIELDS.items():
            for p in paths:
                fields[name][p] += _present(_get(obj, p))
    listing_path = _find(kit_dir, LISTING_FILE)
    listing_fields = {name: dict.fromkeys(paths, 0) for name, paths in LISTING_FIELDS.items()}
    listings = 0
    if listing_path is not None:
        for obj in _iter_jsonl(listing_path):
            listings += 1
            for name, paths in LISTING_FIELDS.items():
                for p in paths:
                    listing_fields[name][p] += _present(_get(obj, p))
    return {
        "records": records,
        "records_with_model_ids": with_models,
        "fields": fields,
        "listings": listings,
        "listing_fields": listing_fields,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--coverage", action="store_true", help="field path counts, no values")
    parser.add_argument("--kit", type=Path, default=DEFAULT_KIT)
    args = parser.parse_args()
    if args.coverage:
        print(json.dumps(coverage(args.kit), indent=2))
    else:
        records = load_records(DataSource.LIVE, kit_dir=args.kit)
        print(f"records parsed: {len(records)}")


if __name__ == "__main__":
    main()
