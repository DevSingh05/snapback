"""Measured batch run: many ads through the real pipeline, one verdict each, with n.

`make eval-ads` composes ad variants from the CoStar kit's buildings (the synthetic FIXTURE
kit by default, the local LIVE kit when it is unzipped under data/) and runs each through the
same code a renter's check uses: `read_listing`, the case session, then `decide`. It also runs
the labelled messages in `fixtures/rules/cases.json`. Nothing here picks a verdict.

Ad types (every composed ad is labelled composed in the CSV; none is a real ad):

    clone_phone            the office's own listing, a different phone number
    other_building_photos  the office's listing, one photo placed in another building's scan
    price_cut              the office's listing at a rent far under its plan's lowest rent
    for_sale_as_rental     a house the for-sale records list as active, posted as a rental
    clean_own_details      the office's own phone, site and a rent inside its plan, no asks

Expected verdicts are written down here before any run, from the policy in `verdict.decide`
(proof of another building gives Don't pay; a red flag or an unconfirmed phone gives Hold; an
honest ad with presence proven gives Verified), not read back from a run. A miss is any ad
whose verdict differs from its expected one, in either direction. Misses are reported, never
tuned away: a labelled message whose rule is soft in `decide` (pressure, a lease link, money
at move-in) and gets Verified is a miss against the Hold the docstring of `decide` lists.

What is composed: the placed-photo evidence (the locate result) and the challenge result are
stand-ins, so this measures rules, record comparison and `decide`, not the photo locator. The
LIVE output goes under data/ (git-ignored); only the FIXTURE CSV is committed.
"""

import argparse
import csv
import json
import os
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from snapback.adapters import costar_jsonl, costar_residential
from snapback.agent.demo import DEMO_DIR
from snapback.agent.intake import read_listing
from snapback.agent.modules import FixtureModules
from snapback.agent.rules.contact import FIXTURE_PHONE_SALT, phone_hash
from snapback.agent.rules.table import BELOW_RANGE_RATIO
from snapback.agent.runner import PolicyChooser, run_case
from snapback.agent.session import CaseSession
from snapback.agent.trace import Trace
from snapback.api.eval_results import ADS_COLUMNS
from snapback.contracts import (
    DataSource,
    ForSaleStatus,
    LocateResult,
    LocateStatus,
    PhotoLocation,
    PropertyRecord,
    VerdictState,
)
from snapback.eval.bank import REPO_ROOT
from snapback.eval.stats import wilson
from snapback.verdict import build_card

# Fixed, so the composition and the for-sale lookups do not depend on the day it runs.
EVAL_DAY = date(2026, 11, 14)

FIXTURE_OUT = REPO_ROOT / "eval" / "ads_results.csv"
LIVE_OUT = REPO_ROOT / "data" / "eval" / "ads_results.live.csv"
CASES_FILE = REPO_ROOT / "fixtures" / "rules" / "cases.json"

CLONE_PHONE = "clone_phone"
OTHER_PHOTOS = "other_building_photos"
PRICE_CUT = "price_cut"
FOR_SALE = "for_sale_as_rental"
CLEAN = "clean_own_details"
MESSAGE_FLAGGED = "labelled_message_asks"
MESSAGE_CLEAN = "labelled_message_clean"

COMPOSED = "composed"
LABELLED = "labelled"

# The verdict each type must get, decided before any run (see the module docstring).
EXPECTED: dict[str, VerdictState] = {
    CLONE_PHONE: VerdictState.HOLD,
    OTHER_PHOTOS: VerdictState.DONT_PAY,
    PRICE_CUT: VerdictState.HOLD,
    FOR_SALE: VerdictState.HOLD,
    CLEAN: VerdictState.VERIFIED,
    MESSAGE_FLAGGED: VerdictState.HOLD,
    MESSAGE_CLEAN: VerdictState.VERIFIED,
}
ORIGIN = {
    **dict.fromkeys((CLONE_PHONE, OTHER_PHOTOS, PRICE_CUT, FOR_SALE, CLEAN), COMPOSED),
    MESSAGE_FLAGGED: LABELLED,
    MESSAGE_CLEAN: LABELLED,
}
TYPE_ORDER = tuple(EXPECTED)

PRICE_CUTS = (0.40, 0.50, 0.60)  # fraction under the plan's lowest rent: far past the 25% line
MAX_BUILDINGS = 12
MAX_HOUSES = 6


@dataclass(frozen=True)
class Building:
    """One kit building with everything a composed ad needs. Digits live only in memory."""

    record: PropertyRecord  # site phone hash is keyed to the fixture salt, see `_buildings`
    office_phone: str
    name: str
    beds: int
    plan_name: str
    rent_low: int
    rent_high: int
    unit: str | None


@dataclass(frozen=True)
class Ad:
    ad_id: str
    ad_type: str
    text: str
    building: Building | None = None
    elsewhere_model: str | None = None  # a photo is placed in this other building's scan
    for_sale_text: str | None = None


@dataclass
class Run:
    source: DataSource
    ads: list[Ad] = field(default_factory=list)
    verdicts: dict[str, VerdictState] = field(default_factory=dict)


# --------------------------------------------------------------------------------------------
# Buildings from the kit
# --------------------------------------------------------------------------------------------


def _kit_dir(source: DataSource) -> Path:
    return costar_jsonl.FIXTURE_KIT if source == DataSource.FIXTURE else costar_jsonl.DEFAULT_KIT


def live_kit_present() -> bool:
    return costar_jsonl._find(costar_jsonl.DEFAULT_KIT, costar_jsonl.PROPERTY_FILE) is not None


def _raw_phones(kit: Path) -> dict[str, str]:
    """The offices' phone numbers as the kit holds them, by property id. In memory only."""
    path = costar_jsonl._find(kit, costar_jsonl.PROPERTY_FILE)
    out: dict[str, str] = {}
    if path is None:
        return out
    for obj in costar_jsonl._iter_jsonl(path):
        pid = costar_jsonl._first(obj, costar_jsonl.FIELDS["property_id"])
        phone = costar_jsonl._first(obj, costar_jsonl.FIELDS["site_phone"])
        if pid is not None and phone:
            out[str(pid)] = str(phone)
    return out


def _buildings(source: DataSource) -> list[Building]:
    """Kit buildings with an office, a rent plan sold by the unit and a scan to place photos in.

    FIXTURE completes what the synthetic kit leaves out (a phone, a site, a scan id) with
    reserved 555-01xx numbers and `.example` hosts, because every FIXTURE value is team-made.
    LIVE completes nothing: a building missing any of it is skipped.
    """
    kit = _kit_dir(source)
    phones = _raw_phones(kit)
    fixture = source == DataSource.FIXTURE
    out: list[Building] = []
    for index, (pid, record) in enumerate(sorted(costar_jsonl.load_records(source).items())):
        plans = [p for p in record.floor_plan_rents if not p.per_bed and p.beds is not None]
        plans = [p for p in plans if p.rent_min is not None]
        if not record.manager_company or not plans:
            continue
        phone = phones.get(pid)
        host, models = record.website_host, record.model_ids
        if fixture:
            phone = phone or f"(555) 010-{100 + index:04d}"[:14]
            phone = phone if phone in phones.values() else f"(555) 010-01{index:02d}"
            host = host or f"fixture-office-{pid}.example"
            models = models or [f"fx-model-{pid}"]
        if not (phone and host and models):
            continue
        plan = plans[0]
        unit = next((u.unit for u in record.units if u.floor_plan == plan.name), None)
        record = record.model_copy(
            update={
                "site_phone_hash": phone_hash(phone, FIXTURE_PHONE_SALT),
                "website_host": host,
                "model_ids": models,
            }
        )
        out.append(
            Building(
                record=record,
                office_phone=phone,
                name=record.building_name or f"the building at {pid}",
                beds=plan.beds,
                plan_name=plan.name,
                rent_low=plan.rent_min,
                rent_high=plan.rent_max or plan.rent_min,
                unit=unit,
            )
        )
        if len(out) == MAX_BUILDINGS:
            break
    return out


def _houses(source: DataSource) -> list[str]:
    """Street addresses of homes the kit lists for sale right now, found by the real lookup."""
    kit = _kit_dir(source)
    path = costar_jsonl._find(kit, costar_residential.RESIDENTIAL_FILE)
    if path is None:
        return []
    enums = costar_jsonl._load_enums(kit)
    found: list[str] = []
    for rec in costar_jsonl._iter_jsonl(path):
        if not costar_residential._public(rec):
            continue
        status, _, _ = costar_residential._status(rec, enums, EVAL_DAY)
        if status is not ForSaleStatus.ACTIVE:
            continue
        address = costar_jsonl._get_any(
            rec, ["property.address.fullStreetAddress", "address.fullStreetAddress"]
        )
        if address and address not in found:
            found.append(str(address))
    return sorted(found)[:MAX_HOUSES]


# --------------------------------------------------------------------------------------------
# Composition (deterministic: no clock, no randomness)
# --------------------------------------------------------------------------------------------


def _ad_text(b: Building, *, phone: str | None = None, rent: int | None = None) -> str:
    unit = f", Unit {b.unit}" if b.unit else ""
    rent = b.rent_low if rent is None else rent
    return (
        f"{b.beds} bed at {b.name}{unit}. ${rent:,} a month.\n"
        f"Managed by {b.record.manager_company}. Text me at {phone or b.office_phone}.\n"
        f"More info: https://{b.record.website_host}/availability"
    )


def _other_phone(index: int) -> str:
    """A reserved-range number that is nobody's: 555-0199 is the top of the 555-01xx block."""
    return f"(555) 010-{9000 + index:04d}"


def compose(source: DataSource) -> list[Ad]:
    """Every composed ad for these kit buildings, in a fixed order."""
    buildings = _buildings(source)
    ads: list[Ad] = []
    for i, b in enumerate(buildings):
        key = b.record.property_id
        for j in range(3):
            ads.append(
                Ad(
                    f"{CLONE_PHONE}-{key}-{j}",
                    CLONE_PHONE,
                    _ad_text(b, phone=_other_phone(i * 3 + j)),
                    b,
                )
            )
        for j, cut in enumerate(PRICE_CUTS):
            rent = int(b.rent_low * (1 - cut))
            assert rent < BELOW_RANGE_RATIO * b.rent_low
            ads.append(Ad(f"{PRICE_CUT}-{key}-{j}", PRICE_CUT, _ad_text(b, rent=rent), b))
        for j, other in enumerate(o for o in buildings if o is not b):
            ads.append(
                Ad(
                    f"{OTHER_PHOTOS}-{key}-{j}",
                    OTHER_PHOTOS,
                    _ad_text(b),
                    b,
                    elsewhere_model=other.record.model_ids[0],
                )
            )
        for j, rent in enumerate((b.rent_low, b.rent_high)):
            ads.append(Ad(f"{CLEAN}-{key}-{j}", CLEAN, _ad_text(b, rent=rent), b))
    for k, address in enumerate(_houses(source)):
        text = (
            f"3 bedroom house for rent at {address}, $1,400 a month. Fenced yard.\n"
            "Call 555-010-0188."
        )
        ads.append(Ad(f"{FOR_SALE}-{k}", FOR_SALE, text, for_sale_text=text))
    return ads


def compose_messages(source: DataSource) -> list[Ad]:
    """The 49 labelled messages, each sent under a clean ad for a kit building (the office's
    own phone and site), so the message is the only thing that can change the verdict."""
    buildings = _buildings(source)
    cases = json.loads(CASES_FILE.read_text())
    ads: list[Ad] = []
    for i, case in enumerate(cases):
        b = buildings[i % len(buildings)]
        kind = MESSAGE_FLAGGED if case["expect"] else MESSAGE_CLEAN
        ads.append(Ad(case["id"], kind, f"{_ad_text(b)}\n{case['text']}", b))
    return ads


# --------------------------------------------------------------------------------------------
# Running one ad through the real pipeline
# --------------------------------------------------------------------------------------------

_TEMPLATE_DIR = DEMO_DIR / "b"  # the staged case whose reply evidence is genuine, not copied
_HOUSE_DIR = DEMO_DIR / "c"


def _locate(b: Building, elsewhere_model: str | None) -> LocateResult:
    """Three listing photos placed in the claimed building's scan; one in another if asked."""
    model = b.record.model_ids[0]
    photos = [
        PhotoLocation(
            photo_id=f"l{n}",
            status=LocateStatus.LOCATED_IN_CLAIMED,
            model_id=model,
            pano_id=f"sweep-{n}",
            inliers=150 + n,
            inlier_ratio=0.5,
        )
        for n in (1, 2, 3)
    ]
    if elsewhere_model:
        photos[2] = photos[2].model_copy(
            update={"status": LocateStatus.LOCATED_ELSEWHERE, "model_id": elsewhere_model}
        )
    template = FixtureModules(
        evidence_file="module_evidence.json", fixtures_dir=_TEMPLATE_DIR
    ).evidence.locate
    assert template is not None and template.chosen is not None
    chosen = template.chosen.model_copy(
        update={
            "property_id": b.record.property_id,
            "model_id": model,
            "floor_plan": b.plan_name,
            "photos_located": 3 - bool(elsewhere_model),
        }
    )
    return template.model_copy(
        update={
            "photos": photos,
            "claimed_property_id": b.record.property_id,
            "chosen": chosen,
            "alternatives": [],
            "poses": {},
        }
    )


def run_ad(ad: Ad) -> VerdictState:
    listing = read_listing(ad.text)
    if ad.ad_type == FOR_SALE:
        modules = FixtureModules(
            evidence_file="module_evidence.json",
            fixtures_dir=_HOUSE_DIR,
            record_file="property_record.json",
            listing_scope=listing.scope,
            rules=listing.rule_hits,
            listed_rent=listing.listed_rent,
            contacts=listing.contacts,
            unit=listing.unit,
            beds=listing.beds,
            for_sale=costar_residential.for_sale_lookup(
                ad.for_sale_text or ad.text, source=_SOURCE.get(), today=EVAL_DAY
            ),
            ad_text=ad.text,
            today=EVAL_DAY,
        )
    else:
        assert ad.building is not None
        modules = FixtureModules(
            evidence_file="module_evidence.json",
            fixtures_dir=_TEMPLATE_DIR,
            listing_scope=listing.scope,
            rules=listing.rule_hits,
            listed_rent=listing.listed_rent,
            contacts=listing.contacts,
            unit=listing.unit,
            beds=listing.beds,
            ad_text=ad.text,
            today=EVAL_DAY,
        )
        modules.record = ad.building.record
        modules.evidence = modules.evidence.model_copy(
            update={"locate": _locate(ad.building, ad.elsewhere_model)}
        )
    case_id = f"fx-eval-{ad.ad_id}"
    session = CaseSession(case_id, modules, Trace(case_id, DataSource.FIXTURE))
    verdict = run_case(session, PolicyChooser(), lambda draft: "send")
    assert verdict is not None
    build_card(session.evidence, checked_at=None)  # the card must build for every verdict
    return verdict.state


class _Source:
    """The kit the current run reads, for the for-sale lookup (set once per run)."""

    def __init__(self) -> None:
        self._value = DataSource.FIXTURE

    def set(self, value: DataSource) -> None:
        self._value = value

    def get(self) -> DataSource:
        return self._value


_SOURCE = _Source()


def run(source: DataSource) -> Run:
    _SOURCE.set(source)
    result = Run(source)
    result.ads = [*compose(source), *compose_messages(source)]
    for ad in result.ads:
        result.verdicts[ad.ad_id] = run_ad(ad)
    return result


# --------------------------------------------------------------------------------------------
# The CSV
# --------------------------------------------------------------------------------------------


def _row(ad_type: str, origin: str, expected: str, got: str, k: int, n: int, miss: int, tag: str):
    low, high = wilson(k, n)
    return [
        ad_type, origin, expected, got, k, n,
        f"{k / n:.4f}", f"{low:.4f}", f"{high:.4f}", miss, tag,
    ]  # fmt: skip


def rows(result: Run) -> list[list]:
    """One row per (ad type, verdict got), then per type a matches-expected and a missed row,
    then the same two for all ads together. n is the ads of that type; the interval is Wilson."""
    tag = result.source.value.upper()
    by_type: dict[str, list[VerdictState]] = {t: [] for t in TYPE_ORDER}
    for ad in result.ads:
        by_type[ad.ad_type].append(result.verdicts[ad.ad_id])
    out: list[list] = []
    hits = total = 0
    for ad_type in TYPE_ORDER:
        got = by_type[ad_type]
        if not got:
            continue
        expected = EXPECTED[ad_type]
        counts = Counter(got)
        for state in VerdictState:
            if counts[state]:
                miss = int(state != expected)
                out.append(
                    _row(
                        ad_type, ORIGIN[ad_type], expected.value, state.value,
                        counts[state], len(got), miss, tag,
                    )
                )  # fmt: skip
        ok = counts[expected]
        out.append(
            _row(ad_type, ORIGIN[ad_type], expected.value, "(as expected)", ok, len(got), 0, tag)
        )
        out.append(
            _row(
                ad_type, ORIGIN[ad_type], expected.value, "(missed)",
                len(got) - ok, len(got), 1, tag,
            )
        )  # fmt: skip
        hits, total = hits + ok, total + len(got)
    out.append(_row("all", "mixed", "per type", "(as expected)", hits, total, 0, tag))
    out.append(_row("all", "mixed", "per type", "(missed)", total - hits, total, 1, tag))
    return out


def comment(result: Run) -> str:
    n = len(result.ads)
    composed = sum(ORIGIN[a.ad_type] == COMPOSED for a in result.ads)
    kit = "synthetic FIXTURE kit" if result.source == DataSource.FIXTURE else "local LIVE kit"
    head = (
        "FIXTURE: composed ads and team-labelled messages, not real ads"
        if (result.source == DataSource.FIXTURE)
        else "LIVE: buildings from the local kit; composed ads are not real ads"
    )
    return (
        f"{head}\n"
        f"n={n}: {composed} composed from the {kit}, {n - composed} labelled messages "
        f"(fixtures/rules/cases.json)\n"
        "stand-ins: placed-photo result and challenge reply are composed; "
        "the photo locator is not run\n"
        "miss = verdict differs from the expected one for the type "
        "(expected is fixed in eval/ads.py)"
    )


def write(result: Run, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="") as handle:
            for line in comment(result).splitlines():
                handle.write(f"# {line}\n")
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(ADS_COLUMNS)
            writer.writerows(rows(result))
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def summary(result: Run) -> str:
    lines = [comment(result).splitlines()[0], f"n={len(result.ads)}"]
    for row in rows(result):
        if row[3] in ("(as expected)", "(missed)"):
            lines.append(
                f"{row[0]:<24} {row[3]:<14} {row[4]}/{row[5]}  rate {row[6]}  "
                f"95% CI [{row[7]}, {row[8]}]"
            )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m snapback.eval.ads", description=__doc__)
    parser.add_argument(
        "--source",
        choices=("auto", "fixture", "live"),
        default="auto",
        help="auto: LIVE when the kit is unzipped under data/, else FIXTURE",
    )
    parser.add_argument("--out", type=Path, help="CSV to write (default by source)")
    args = parser.parse_args(argv)

    live = args.source == "live" or (args.source == "auto" and live_kit_present())
    source = DataSource.LIVE if live else DataSource.FIXTURE
    if live and not live_kit_present():
        print("eval-ads: no local kit under data/raw/costar; unzip it or use --source fixture")
        return 2
    result = run(source)
    out = args.out or (LIVE_OUT if live else FIXTURE_OUT)
    write(result, out)
    print(summary(result))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
