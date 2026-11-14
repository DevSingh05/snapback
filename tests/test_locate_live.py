"""A22 (#141): the merged V2 locator, wired into live cases.

Fixture twins (FixtureMatterport), a tiny embedder index and the numpy PatchMatcher: no
network, no weights, no torch. The real DISK+LightGlue timing is not measured here.
"""

import io
import json
import shutil
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from snapback.adapters.matterport import FixtureMatterport
from snapback.agent import CaseSession, PolicyChooser, Trace, run_case
from snapback.agent.intake import read_listing
from snapback.agent.join import JoinedModules, KitLookups
from snapback.agent.locate_live import LiveLocate
from snapback.agent.rules.contact import FIXTURE_PHONE_SALT
from snapback.contracts import (
    CardTone,
    DataSource,
    ForSaleMatch,
    ForSaleStatus,
    LocateStatus,
    PropertyRecord,
    VerdictState,
)
from snapback.verdict import build_card
from snapback.vision.embed import TinyEmbedder
from snapback.vision.locate.index import LocateIndex
from snapback.vision.locate.thresholds import load_thresholds
from snapback.vision.locate.verify import PatchMatcher

CHECKED_AT = datetime.fromisoformat("2026-11-14T04:00:00-05:00")
THRESHOLDS = replace(
    load_thresholds(), min_inliers=12, stop_at_inliers=60, elsewhere_min_inliers=16
)


def record(prop: str, models: list[str], **changes) -> PropertyRecord:
    base = {
        "property_id": prop,
        "source": DataSource.LIVE,
        "model_ids": models,
        "floor_plans": ["2 bed / 2 bath"] * len(models),
        "lat": 29.76,
        "lon": -95.36,
    }
    return PropertyRecord.model_validate(base | changes)


RECORDS = [
    record("fx-prop-1", ["fx-model-a"]),
    record("fx-prop-2", ["fx-model-b"], lat=29.77),
    record("fx-prop-3", ["fx-model-c"]),  # on record, not in the index
]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("world")
    adapter = FixtureMatterport(root / "faces")
    sweeps = {m: adapter.sweeps(m) for m in ("fx-model-a", "fx-model-b")}
    index = LocateIndex.build("demo", [s for ss in sweeps.values() for s in ss], TinyEmbedder())
    index.save(root / "data" / "index" / "demo")
    return root / "data", sweeps, adapter


def photo(sweeps, model: str, sweep: int, face: int) -> bytes:
    with Image.open(sweeps[model][sweep].faces[face]) as opened:
        crop = opened.convert("RGB").crop((30, 20, 230, 190))
    out = io.BytesIO()
    crop.save(out, format="JPEG", quality=85)
    return out.getvalue()


class SlowMatcher(PatchMatcher):
    def __init__(self, delay: float) -> None:
        super().__init__()
        self.delay = delay

    def match(self, a, b):
        time.sleep(self.delay)
        return super().match(a, b)


class ExplodingMatcher(PatchMatcher):
    def match(self, a, b):
        raise AssertionError("the matcher ran, so the cache was not used")


def make_live(data_dir, adapter, *, matcher=PatchMatcher, budget=25.0, index="demo"):
    return LiveLocate(
        data_dir=data_dir,
        records=lambda: RECORDS,
        index_name=index,
        sweeps_for=adapter.sweeps,
        matcher_factory=matcher,
        budget_s=budget,
        thresholds=THRESHOLDS,
    )


class Lookups:
    def __init__(self, for_sale: ForSaleMatch | None = None) -> None:
        self._for_sale = for_sale
        self.at: list[tuple[float, float]] = []

    def record(self, property_id):
        return next((r for r in RECORDS if r.property_id == property_id), None)

    def for_sale(self, text):
        return None

    def for_sale_at(self, text, lat, lon):
        self.at.append((lat, lon))
        return self._for_sale


def joined(live, photos, claimed=None, lookups=None, text="2 bed, $1,500 a month."):
    lookups = lookups or Lookups()
    return JoinedModules(
        stand_in=None,
        listing=read_listing(text, photos, ocr=lambda blob: ""),
        record=lookups.record(claimed) if claimed else None,
        for_sale=None,
        salt=FIXTURE_PHONE_SALT,
        record_source=DataSource.LIVE,
        live_locate=live,
        photo_bytes=photos,
        lookups=lookups,
    )


def run(modules):
    case = CaseSession("LIVE-1", modules, Trace("LIVE-1", DataSource.FIXTURE))
    verdict = run_case(case, PolicyChooser(), lambda draft: "send")
    return verdict, build_card(case.evidence, checked_at=CHECKED_AT), case


def place_line(card):
    row = next(r for r in card.rows if r.kind.value == "place")
    return row.lines[0]


# --- the five behaviours -----------------------------------------------------------------------


def test_live_indexed_claimed_home_is_located_in_claimed(world):
    data, sweeps, adapter = world
    photos = [photo(sweeps, "fx-model-a", 2, 1), photo(sweeps, "fx-model-a", 0, 3)]
    modules = joined(make_live(data, adapter), photos, "fx-prop-1")
    assert modules.has_twin("c")
    verdict, card, case = run(modules)
    located = case.evidence.locate
    assert [p.status for p in located.photos] == [LocateStatus.LOCATED_IN_CLAIMED] * 2
    assert located.photos[0].room_label is None or located.photos[0].pano_id
    assert located.poses  # the twin page's "Taken here" reads the pose
    assert located.chosen.model_id == "fx-model-a" and located.chosen.photos_located == 2
    assert place_line(card).tone is CardTone.OK
    # placed, nobody has proven presence yet, and no stand-in: HOLD, never VERIFIED
    assert verdict.state is VerdictState.HOLD


def test_no_index_falls_back_to_not_indexed(tmp_path, world):
    _, sweeps, adapter = world
    live = make_live(tmp_path, adapter)  # no data/index/demo here
    assert live.available("fx-prop-1", ["fx-model-a"]) is False
    modules = joined(live, [photo(sweeps, "fx-model-a", 2, 1)], "fx-prop-1")
    assert modules.has_twin("c") is False
    _, card, case = run(modules)
    assert [p.status for p in case.evidence.locate.photos] == [LocateStatus.NOT_INDEXED]
    assert place_line(card).tone is CardTone.NOT_CHECKED


def test_claimed_home_not_in_the_index_is_not_indexed(world):
    data, sweeps, adapter = world
    modules = joined(make_live(data, adapter), [photo(sweeps, "fx-model-a", 2, 1)], "fx-prop-3")
    assert modules.has_twin("c") is False
    assert modules.locate("c").photos[0].status is LocateStatus.NOT_INDEXED


def test_a_timeout_is_not_located_never_elsewhere(world, tmp_path):
    data, sweeps, adapter = world
    # This photo is from building 1; the ad claims building 2. Control: with time, it is
    # placed elsewhere. Out of time, it must read NOT_LOCATED.
    blob = [photo(sweeps, "fx-model-a", 1, 2)]
    control = make_live(data, adapter).locate("c", blob, "fx-prop-2")
    assert control.result.photos[0].status is LocateStatus.LOCATED_ELSEWHERE

    slow = LiveLocate(
        data_dir=tmp_path,
        records=lambda: RECORDS,
        sweeps_for=adapter.sweeps,
        matcher_factory=lambda: SlowMatcher(0.4),
        budget_s=0.05,
        thresholds=THRESHOLDS,
    )
    (tmp_path / "index").symlink_to(data / "index")
    outcome = slow.locate("c", blob + blob, "fx-prop-2")
    assert [p.status for p in outcome.result.photos] == [LocateStatus.NOT_LOCATED] * 2
    assert not (tmp_path / "locate").exists()  # an unfinished run is never cached
    # and the card for it is never DON'T PAY
    verdict, _, _ = run(joined(slow, blob, "fx-prop-2"))
    assert verdict.state is not VerdictState.DONT_PAY


def test_cache_is_used_and_labelled_live(world, tmp_path):
    data, sweeps, adapter = world
    (tmp_path / "index").symlink_to(data / "index")
    blob = [photo(sweeps, "fx-model-a", 2, 1)]
    first = make_live(tmp_path, adapter).locate("c1", blob, "fx-prop-1")
    assert first.from_cache is False
    (entry,) = list((tmp_path / "locate").glob("*.json"))
    assert json.loads(entry.read_text())["source"] == "live"

    # A fresh locator whose matcher would blow up: the answer must come from the cache.
    again = make_live(tmp_path, adapter, matcher=ExplodingMatcher).locate("c2", blob, "fx-prop-1")
    assert again.from_cache is True and again.result.case_id == "c2"
    assert again.result.photos == first.result.photos

    # An entry that does not say it is live data is never used in a live case.
    raw = json.loads(entry.read_text())
    entry.write_text(json.dumps(raw | {"source": "fixture"}))
    rerun = make_live(tmp_path, adapter).locate("c3", blob, "fx-prop-1")
    assert rerun.from_cache is False
    assert json.loads(entry.read_text())["source"] == "live"  # and the live rerun relabels it


def test_cache_key_includes_the_claimed_home(world, tmp_path):
    data, sweeps, adapter = world
    (tmp_path / "index").symlink_to(data / "index")
    blob = [photo(sweeps, "fx-model-a", 2, 1)]
    live = make_live(tmp_path, adapter)
    live.locate("c1", blob, "fx-prop-1")
    other = live.locate("c2", blob, "fx-prop-2")
    assert other.from_cache is False
    assert other.result.photos[0].status is LocateStatus.LOCATED_ELSEWHERE


def test_identified_home_record_feeds_the_for_sale_line(world):
    data, sweeps, adapter = world
    sale = ForSaleMatch(status=ForSaleStatus.ACTIVE, site="Homes.com")
    lookups = Lookups(sale)
    modules = joined(
        make_live(data, adapter),
        [photo(sweeps, "fx-model-a", 2, 1), photo(sweeps, "fx-model-a", 0, 3)],
        claimed=None,
        lookups=lookups,
    )
    assert modules.has_twin("c")  # no claimed home, index not empty
    verdict, card, case = run(modules)
    assert lookups.at == [(29.76, -95.36)]  # looked up at the identified home's position
    assert case.evidence.for_sale == sale
    assert case.evidence.locate.claimed_property_id == "fx-prop-1"
    statuses = {p.status for p in case.evidence.locate.photos}
    assert statuses == {LocateStatus.LOCATED_IN_CLAIMED}  # identified, never elsewhere
    assert verdict.state is VerdictState.HOLD  # for sale outranks; never DON'T PAY


def test_no_claimed_home_never_reads_elsewhere_and_two_buildings_identify_nothing(world):
    data, sweeps, adapter = world
    live = make_live(data, adapter)
    mixed = live.locate(
        "c", [photo(sweeps, "fx-model-a", 2, 1), photo(sweeps, "fx-model-b", 1, 1)], None
    )
    assert mixed.identified_property_id is None
    assert {p.status for p in mixed.result.photos} == {LocateStatus.NOT_LOCATED}
    single = live.locate("c", [photo(sweeps, "fx-model-b", 1, 1)], None)
    assert single.identified_property_id == "fx-prop-2"
    assert LocateStatus.LOCATED_ELSEWHERE not in {p.status for p in single.result.photos}


def test_a_fixture_case_never_uses_the_live_locator(world):
    from snapback.agent.modules import FixtureModules

    data, sweeps, adapter = world
    modules = JoinedModules(
        stand_in=FixtureModules(),
        listing=read_listing("2 bed"),
        record=None,
        for_sale=None,
        salt=FIXTURE_PHONE_SALT,
        record_source=None,
        live_locate=make_live(data, adapter, matcher=ExplodingMatcher),
        photo_bytes=[photo(sweeps, "fx-model-a", 2, 1)],
    )
    assert modules._live_locate is None


def test_a_timeout_with_no_claimed_home_leaves_every_photo_not_located(world, tmp_path):
    data, sweeps, adapter = world
    (tmp_path / "index").symlink_to(data / "index")
    slow = LiveLocate(
        data_dir=tmp_path,
        records=lambda: RECORDS,
        sweeps_for=adapter.sweeps,
        matcher_factory=lambda: SlowMatcher(0.4),
        budget_s=0.05,
        thresholds=THRESHOLDS,
    )
    blobs = [photo(sweeps, "fx-model-a", 2, 1), photo(sweeps, "fx-model-a", 0, 3)]
    outcome = slow.locate("c", blobs, None)
    assert outcome.identified_property_id is None
    assert [p.status for p in outcome.result.photos] == [LocateStatus.NOT_LOCATED] * 2
    assert not (tmp_path / "locate").exists()


class GatedMatcher(PatchMatcher):
    """Blocks every match until the test opens the gate."""

    def __init__(self, gate) -> None:
        super().__init__()
        self.gate = gate

    def match(self, a, b):
        self.gate.wait(10)
        return super().match(a, b)


def test_a_late_complete_answer_writes_the_cache_for_the_next_case(world, tmp_path):
    import threading

    data, sweeps, adapter = world
    (tmp_path / "index").symlink_to(data / "index")
    gate = threading.Event()
    live = LiveLocate(
        data_dir=tmp_path,
        records=lambda: RECORDS,
        sweeps_for=adapter.sweeps,
        matcher_factory=lambda: GatedMatcher(gate),
        budget_s=0.05,
        thresholds=THRESHOLDS,
    )
    blobs = [photo(sweeps, "fx-model-a", 2, 1), photo(sweeps, "fx-model-a", 0, 3)]
    first = live.locate("c1", blobs, None)
    assert {p.status for p in first.result.photos} == {LocateStatus.NOT_LOCATED}
    assert not (tmp_path / "locate").exists()  # nothing yet: the run is still going
    gate.set()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not list((tmp_path / "locate").glob("*.json")):
        time.sleep(0.1)
    second = live.locate("c2", blobs, None)
    assert second.from_cache is True
    assert second.identified_property_id == "fx-prop-1"


def test_changed_thresholds_or_index_miss_the_cache(world, tmp_path):
    data, sweeps, adapter = world
    (tmp_path / "index").symlink_to(data / "index")
    blob = [photo(sweeps, "fx-model-a", 2, 1)]
    make_live(tmp_path, adapter).locate("c1", blob, "fx-prop-1")
    assert make_live(tmp_path, adapter).locate("c2", blob, "fx-prop-1").from_cache is True

    stricter = LiveLocate(
        data_dir=tmp_path,
        records=lambda: RECORDS,
        sweeps_for=adapter.sweeps,
        matcher_factory=PatchMatcher,
        thresholds=replace(THRESHOLDS, min_inliers=THRESHOLDS.min_inliers + 1),
    )
    assert stricter.locate("c3", blob, "fx-prop-1").from_cache is False


# --- houses: residential listings with a Matterport model are in the catalog -------------------

HOUSE_KIT = Path(__file__).resolve().parents[1] / "fixtures" / "adapters" / "costar-house-kit"
BUILDING_KIT = Path(__file__).resolve().parents[1] / "fixtures" / "adapters" / "costar-kit"


@pytest.fixture(scope="module")
def house_world(tmp_path_factory):
    root = tmp_path_factory.mktemp("houses")
    kit = root / "kit"
    kit.mkdir()
    for name in ("residential-listings.jsonl", "enums.json"):
        shutil.copy(HOUSE_KIT / name, kit / name)
    shutil.copy(BUILDING_KIT / "commercial-property.jsonl", kit / "commercial-property.jsonl")
    adapter = FixtureMatterport(root / "faces")
    models = ("fx-fs-a", "fx-fs-b", "fx-fs-c")
    sweeps = {m: adapter.sweeps(m) for m in models}
    index = LocateIndex.build("demo", [s for ss in sweeps.values() for s in ss], TinyEmbedder())
    index.save(root / "data" / "index" / "demo")
    return root / "data", kit, sweeps, adapter


class HouseLookups(KitLookups):
    def __init__(self, kit) -> None:
        super().__init__(DataSource.FIXTURE, kit_dir=kit)
        self.at: list[tuple[float, float]] = []

    def for_sale_at(self, text, lat, lon):
        self.at.append((lat, lon))
        return ForSaleMatch(status=ForSaleStatus.ACTIVE, site="Homes.com")


def house_live(world):
    data, kit, sweeps, adapter = world
    lookups = HouseLookups(kit)
    live = LiveLocate(
        data_dir=data,
        records=lambda: lookups.records().values(),
        sweeps_for=adapter.sweeps,
        matcher_factory=PatchMatcher,
        thresholds=THRESHOLDS,
    )
    return live, lookups, sweeps


def test_house_records_come_from_the_residential_file(house_world):
    _, kit, _, _ = house_world
    records = KitLookups(DataSource.FIXTURE, kit_dir=kit).records()
    house = records["9001"]
    assert house.property_type == "house" and house.market == "Houston"
    assert house.model_ids == ["fx-fs-b", "fx-fs-a"]  # two listings of one house, one record
    assert (house.lat, house.lon) == (29.7604, -95.3698)
    assert "9010" not in records  # not public on Homes.com
    assert "9011" not in records  # a condo
    assert "9012" not in records  # no Matterport model
    assert "fx-prop-1" in records  # buildings are still there


def test_a_house_photo_is_identified_and_for_sale_is_read_at_its_position(house_world):
    live, lookups, sweeps = house_live(house_world)
    photos = [photo(sweeps, "fx-fs-a", 2, 1), photo(sweeps, "fx-fs-a", 0, 3)]
    modules = joined(live, photos, claimed=None, lookups=lookups)
    assert modules.has_twin("c")
    verdict, _, case = run(modules)
    assert lookups.at == [(29.7604, -95.3698)]
    assert case.evidence.locate.claimed_property_id == "9001"
    assert case.evidence.locate.identified_by_scan is True
    assert case.evidence.for_sale.status is ForSaleStatus.ACTIVE
    assert verdict.state is VerdictState.HOLD


def test_a_claimed_house_id_is_located_in_claimed(house_world):
    live, lookups, sweeps = house_live(house_world)
    modules = joined(live, [photo(sweeps, "fx-fs-c", 2, 1)], claimed="9002", lookups=lookups)
    assert modules.has_twin("c")
    _, card, case = run(modules)
    assert [p.status for p in case.evidence.locate.photos] == [LocateStatus.LOCATED_IN_CLAIMED]
    assert place_line(card).tone is CardTone.OK


# --- follow-up: the cache key, id collisions, the worker rules, shared models -------------------


class PatchV2(PatchMatcher):
    version = "patch@v2"


def prime(data_dir, adapter, blob, **kwargs):
    live = make_live(data_dir, adapter, **kwargs)
    live.locate("c0", blob, "fx-prop-1")
    return live


def test_an_edited_index_file_misses_the_cache(world, tmp_path):
    data, sweeps, adapter = world
    shutil.copytree(data / "index", tmp_path / "index")
    blob = [photo(sweeps, "fx-model-a", 2, 1)]
    prime(tmp_path, adapter, blob)
    assert make_live(tmp_path, adapter).locate("c1", blob, "fx-prop-1").from_cache is True

    meta_path = tmp_path / "index" / "demo" / "index.json"
    meta = json.loads(meta_path.read_text())
    meta["built_at"] = "2030-01-01T00:00:00+00:00"  # same views, a different build
    meta_path.write_text(json.dumps(meta))
    assert make_live(tmp_path, adapter).locate("c2", blob, "fx-prop-1").from_cache is False


def test_a_new_matcher_version_misses_the_cache(world, tmp_path):
    data, sweeps, adapter = world
    (tmp_path / "index").symlink_to(data / "index")
    blob = [photo(sweeps, "fx-model-a", 2, 1)]
    prime(tmp_path, adapter, blob)
    assert make_live(tmp_path, adapter).locate("c1", blob, "fx-prop-1").from_cache is True
    again = make_live(tmp_path, adapter, matcher=PatchV2).locate("c2", blob, "fx-prop-1")
    assert again.from_cache is False


def test_a_building_wins_an_id_collision_with_a_house(monkeypatch):
    from snapback.adapters import costar_residential

    building = KitLookups(DataSource.FIXTURE).records()["fx-prop-1"]
    assert building.property_type != "house"
    imposter = record("fx-prop-1", ["fx-fs-a"], property_type="house")
    monkeypatch.setattr(
        costar_residential, "house_records", lambda *a, **k: {"fx-prop-1": imposter}
    )
    kept = KitLookups(DataSource.FIXTURE).records()["fx-prop-1"]
    assert kept == building and kept.model_ids != ["fx-fs-a"]


def drain(live):
    """Wait for the single worker to be idle: callbacks of finished jobs have run by then."""
    live._executor().submit(lambda: None).result(30)


def gated_live(tmp_path, adapter, gate):
    return LiveLocate(
        data_dir=tmp_path,
        records=lambda: RECORDS,
        sweeps_for=adapter.sweeps,
        matcher_factory=lambda: GatedMatcher(gate),
        budget_s=0.05,
        thresholds=THRESHOLDS,
    )


def test_a_claimed_case_that_times_out_never_writes_the_cache_later(world, tmp_path):
    import threading

    data, sweeps, adapter = world
    (tmp_path / "index").symlink_to(data / "index")
    gate = threading.Event()
    live = gated_live(tmp_path, adapter, gate)
    blobs = [photo(sweeps, "fx-model-a", 2, 1), photo(sweeps, "fx-model-a", 0, 3)]
    first = live.locate("c1", blobs, "fx-prop-1")
    assert {p.status for p in first.result.photos} == {LocateStatus.NOT_LOCATED}
    gate.set()
    drain(live)
    assert not (tmp_path / "locate").exists()  # the late photo did not complete the case


def test_a_job_queued_behind_a_stuck_one_is_cancelled_and_never_runs(world, tmp_path):
    import threading

    data, sweeps, adapter = world
    (tmp_path / "index").symlink_to(data / "index")
    gate = threading.Event()
    live = gated_live(tmp_path, adapter, gate)
    live._load()
    ran: list[str] = []
    real = live._ready.locator.locate

    def counting(case_id, photos, claimed):
        ran.append(case_id)
        return real(case_id, photos, claimed)

    live._ready.locator.locate = counting
    blob = [photo(sweeps, "fx-model-a", 2, 1)]
    live.locate("stuck", blob, "fx-prop-1")  # running on the one worker, blocked on the gate
    queued = live.locate("queued", [photo(sweeps, "fx-model-a", 0, 3)], "fx-prop-1")
    assert {p.status for p in queued.result.photos} == {LocateStatus.NOT_LOCATED}
    gate.set()
    drain(live)
    assert ran == ["stuck"]  # the queued job was cancelled before it started


def test_a_model_on_two_houses_belongs_to_neither(tmp_path):
    from snapback.adapters.costar_residential import house_records
    from snapback.vision.locate.locate import catalog_from_records

    text = (HOUSE_KIT / "residential-listings.jsonl").read_text()
    rows = [json.loads(line) for line in text.splitlines()]
    base = next(r for r in rows if r["propertyId"] == 9001 and r["residentialListingId"] == 5001)

    def house(pid, listing, keys):
        row = json.loads(json.dumps(base))
        row["propertyId"], row["residentialListingId"] = pid, listing
        row["media"] = [
            {"id": n, "type": 3, "externalReferenceType": 36, "videoKey": key}
            for n, key in enumerate(keys, start=1)
        ]
        return json.dumps(row)

    lines = [
        house(7001, 1, ["fx-shared", "fx-own-1"]),
        house(7002, 2, ["fx-shared"]),  # only a shared model: no twin at all
        house(7003, 3, ["fx-shared", "fx-own-3"]),
        house(7004, 4, ["fx-own-4"]),
    ]
    (tmp_path / "residential-listings.jsonl").write_text("\n".join(lines) + "\n")
    shutil.copy(HOUSE_KIT / "enums.json", tmp_path / "enums.json")

    records = house_records(DataSource.FIXTURE, tmp_path)
    assert {pid: r.model_ids for pid, r in records.items()} == {
        "7001": ["fx-own-1"],
        "7003": ["fx-own-3"],
        "7004": ["fx-own-4"],
    }
    catalog = catalog_from_records(records.values())
    assert catalog.property_of("fx-shared") is None  # so it can never read "elsewhere"
