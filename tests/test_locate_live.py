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
    real = live._ready.locator.locate_with_points  # what a live job calls

    def counting(case_id, photos, claimed, **kwargs):
        ran.append(case_id)
        return real(case_id, photos, claimed, **kwargs)

    live._ready.locator.locate_with_points = counting
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


# --- room labels on a live result (#74, #205) -----------------------------------------------------


@pytest.mark.parametrize(
    ("rooms", "expected"), [({"fx-sweep-02": "Bedroom"}, "Bedroom"), ({}, None)]
)
def test_a_live_result_carries_the_room_label_when_the_cache_has_it(world, rooms, expected):
    data, sweeps, adapter = world
    live = LiveLocate(
        data_dir=data,
        records=lambda: RECORDS,
        sweeps_for=adapter.sweeps,
        matcher_factory=PatchMatcher,
        thresholds=THRESHOLDS,
        rooms_for=lambda model_id: rooms if model_id == "fx-model-a" else {},
    )
    outcome = live.locate("LIVE-ROOM", [photo(sweeps, "fx-model-a", 2, 1)], "fx-prop-1")
    placed = outcome.result.photos[0]
    assert placed.status is LocateStatus.LOCATED_IN_CLAIMED and placed.pano_id == "fx-sweep-02"
    assert placed.room_label == expected


# --- E2b: matched pairs ride beside the result, for the evidence file only (#224) -------------


def fresh_data(world, tmp_path):
    """The world's index in a data dir of its own, so no earlier test's cache answers."""
    data, sweeps, adapter = world
    shutil.copytree(data / "index", tmp_path / "index")
    return tmp_path, sweeps, adapter


def pair_values(points):
    return {round(v, 6) for p in points.values() for pair in p.sampled for v in pair}


def test_a_live_claimed_case_carries_points_for_each_placed_photo(world, tmp_path):
    from snapback.contracts import EvidencePoints

    data, sweeps, adapter = fresh_data(world, tmp_path)
    blobs = [photo(sweeps, "fx-model-a", 2, 1), photo(sweeps, "fx-model-a", 0, 3)]
    outcome = make_live(data, adapter).locate("c", blobs, "fx-prop-1")
    placed = {
        p.photo_id for p in outcome.result.photos if p.status is LocateStatus.LOCATED_IN_CLAIMED
    }
    assert placed == {"l1", "l2"} and set(outcome.points) == placed
    for points in outcome.points.values():
        assert isinstance(points, EvidencePoints) and 0 < len(points.sampled) <= 48
        assert all(0.0 <= v <= 1.0 for pair in points.sampled for v in pair)
    assert "points" not in repr(outcome)  # never printed with the outcome


def test_a_live_case_with_no_claimed_home_carries_points_too(world, tmp_path):
    data, sweeps, adapter = fresh_data(world, tmp_path)
    blobs = [photo(sweeps, "fx-model-a", 2, 1), photo(sweeps, "fx-model-a", 0, 3)]
    outcome = make_live(data, adapter).locate("c", blobs, None)
    placed = {p.photo_id for p in outcome.result.photos if p.matched_model_id}
    assert set(outcome.points) == placed


def test_points_are_kept_in_the_cache_body_but_never_in_its_key(world, tmp_path):
    """#231 review: a second run of the same ad must still have lines to draw, so the pairs ride
    in the cache file's body. The key stays the photo hashes, the claimed id and the
    index/thresholds/matcher, with no pairs in it."""
    data, sweeps, adapter = fresh_data(world, tmp_path)
    blobs = [photo(sweeps, "fx-model-a", 2, 1)]
    live = make_live(data, adapter)
    outcome = live.locate("c", blobs, "fx-prop-1")
    assert outcome.points
    files = list((data / "locate").glob("*.json"))
    assert len(files) == 1
    ready = live._load()
    assert files[0] == live._cache_path(ready, blobs, "fx-prop-1")
    # the key does not move whatever the pairs are
    outcome.points.clear()
    assert live._cache_path(ready, blobs, "fx-prop-1") == files[0]
    stored = json.loads(files[0].read_text())
    assert set(stored) == {"source", "identified_property_id", "result", "points"}
    assert "points" not in json.dumps(stored["result"])  # never inside the result
    for value in stored["points"].values():
        assert len(value["sampled"]) <= 48
        assert all(0.0 <= v <= 1.0 for pair in value["sampled"] for v in pair)


def test_a_cached_run_still_carries_its_points(world, tmp_path):
    data, sweeps, adapter = fresh_data(world, tmp_path)
    blobs = [photo(sweeps, "fx-model-a", 2, 1), photo(sweeps, "fx-model-a", 0, 3)]
    first = make_live(data, adapter, budget=120.0).locate("c1", blobs, "fx-prop-1")
    assert first.points and not first.from_cache
    # the matcher must not run: the answer and its pairs come from the cache
    again = make_live(data, adapter, matcher=ExplodingMatcher).locate("c2", blobs, "fx-prop-1")
    assert again.from_cache and again.result.case_id == "c2"
    assert again.points == first.points
    # same on the no-claimed-home path
    whole = make_live(data, adapter, budget=120.0).locate("c3", blobs, None)
    cached = make_live(data, adapter, matcher=ExplodingMatcher).locate("c4", blobs, None)
    assert cached.from_cache and cached.points == whole.points


def assert_no_pairs(points, texts):
    """No pair field name and no run of pair values (as stored, 4 decimals) in any text."""
    values = {str(v) for v in pair_values(points) if len(str(v)) >= 5}
    assert values, "the live runs produced pairs"
    for where, text in texts.items():
        assert "sampled" not in text and "n_total" not in text, where
        hits = sum(value in text for value in values)
        assert hits <= len(values) // 10, where  # no run of pair values leaked


def test_points_never_reach_a_log_the_trace_the_chooser_the_card_or_the_status(
    world, tmp_path, caplog
):
    """#234 review: every path a live case takes, under caplog at DEBUG: a fresh claimed case,
    a second (cached) case of the same ad, a no-claimed case, and a live SessionCase.advance()
    with its card and status."""
    from snapback.api.cases import SessionCase

    data, sweeps, adapter = fresh_data(world, tmp_path)
    blobs = [photo(sweeps, "fx-model-a", 2, 1), photo(sweeps, "fx-model-a", 0, 3)]
    seen: list = []
    events: list = []
    kept: dict = {}

    class Watching(PolicyChooser):
        def choose(self, offer):
            seen.append(repr(offer))
            return super().choose(offer)

    def spied(live):
        real = live.locate

        def spy(*args, **kwargs):
            outcome = real(*args, **kwargs)
            if outcome is not None:
                kept.update(outcome.points)
            return outcome

        live.locate = spy  # type: ignore[method-assign]
        return live

    def run_one(case_id, live, claimed):
        case = CaseSession(case_id, joined(live, blobs, claimed), Trace(case_id, DataSource.LIVE))
        case.trace.subscribe(events.append)
        run_case(case, Watching(), lambda draft: "send")
        return case

    caplog.set_level("DEBUG")
    fresh = run_one("LIVE-P1", spied(make_live(data, adapter)), "fx-prop-1")
    cached_live = spied(make_live(data, adapter, matcher=ExplodingMatcher))
    cached = run_one("LIVE-P2", cached_live, "fx-prop-1")  # (a) the same ad, from the cache
    assert cached_live._load() is not None
    unclaimed = run_one("LIVE-P3", spied(make_live(data, adapter)), None)  # (b) no claimed home

    live, modules = live_session(world, tmp_path / "api")  # (c) the API's case
    live.trace.subscribe(events.append)
    api_case = SessionCase(
        "LV9", live, modules._listing, lambda c: run_case(c, Watching(), lambda d: "send")
    )
    api_case.advance()
    kept.update(modules.live_points("LIVE-E"))
    assert api_case.files is not None and api_case.files.evidence is not None

    texts = {
        "logs": "\n".join(r.getMessage() for r in caplog.records),
        "trace": "\n".join(repr(e) for e in events),
        "chooser": "\n".join(seen),
        "card": api_case.card("https://example.test").model_dump_json(),
        "status": api_case.status(with_challenge=True).model_dump_json(),
    }
    for case in (fresh, cached, unclaimed, live):
        texts[f"evidence {case.case_id}"] = case.evidence.model_dump_json()
    assert_no_pairs(kept, texts)


def test_a_retry_desk_keeps_the_first_pass_points_of_a_placed_photo(world, tmp_path):
    """#234 review: the live pairs reach the retry desk (session.py, `points=`). One photo is
    placed, one is not; a stub searcher retries the unplaced one and finds nothing."""
    from snapback.agent.place import SearchOutcome
    from snapback.contracts import PhotoLocation

    data, sweeps, adapter = fresh_data(world, tmp_path)
    noise = Image.new("RGB", (200, 170), (127, 127, 127))
    out = io.BytesIO()
    noise.save(out, format="JPEG")
    blobs = [photo(sweeps, "fx-model-a", 2, 1), out.getvalue()]
    modules = joined(make_live(data, adapter), blobs, "fx-prop-1")

    class StubSearcher:
        calls = 0

        def search(self, photo_id, option, claimed_property_id, thresholds, deadline_s=None):
            StubSearcher.calls += 1
            return SearchOutcome(PhotoLocation(photo_id=photo_id, status=LocateStatus.NOT_LOCATED))

    session = CaseSession("LIVE-R", modules, Trace("LIVE-R", DataSource.LIVE))
    session.place_searcher = StubSearcher()
    run_case(session, PolicyChooser(), lambda draft: "send")
    pairs = modules.live_points("LIVE-R")
    assert set(pairs) == {"l1"}  # only the placed photo has pairs
    desk = session.place_desk
    assert desk is not None and StubSearcher.calls >= 1  # the desk opened and retried l2
    assert desk.rows["l1"].points == pairs["l1"]
    assert desk.rows["l2"].points is None
    evidence = session.evidence_file()
    assert evidence.photos[0].points == pairs["l1"] and evidence.photos[1].points is None


# --- the live evidence file: pairs reach EvidencePhoto.points and nowhere else (#231) ----------


def live_session(world, tmp_path, claimed="fx-prop-1", source=DataSource.LIVE):
    data, sweeps, adapter = fresh_data(world, tmp_path)
    blobs = [photo(sweeps, "fx-model-a", 2, 1), photo(sweeps, "fx-model-a", 0, 3)]
    modules = joined(make_live(data, adapter), blobs, claimed)
    return CaseSession("LIVE-E", modules, Trace("LIVE-E", source)), modules


def test_a_live_case_writes_an_evidence_file_with_each_placed_photos_points(world, tmp_path):
    session, modules = live_session(world, tmp_path)
    run_case(session, PolicyChooser(), lambda draft: "send")
    evidence = session.evidence_file()
    assert evidence is not None and evidence.source is DataSource.LIVE
    assert [p.alias for p in evidence.photos] == ["P1", "P2"]
    pairs = modules.live_points("LIVE-E")
    for photo_id, row in zip(["l1", "l2"], evidence.photos, strict=True):
        assert row.status is LocateStatus.LOCATED_IN_CLAIMED and row.scan_alias == "S1"
        assert row.points == pairs[photo_id] and 0 < len(row.points.sampled) <= 48
        assert all(0.0 <= v <= 1.0 for pair in row.points.sampled for v in pair)
    assert {"min_inliers", "claimed_min_spread", "ambiguity_ratio"} <= set(evidence.bars)
    # the case's own evidence (what decide() and the card read) still carries no pairs
    assert "sampled" not in session.evidence.model_dump_json()


def test_a_cached_live_case_still_has_points_in_its_evidence_file(world, tmp_path):
    data, sweeps, adapter = fresh_data(world, tmp_path)
    blobs = [photo(sweeps, "fx-model-a", 2, 1)]
    make_live(data, adapter).locate("warm", blobs, "fx-prop-1")  # fills the cache
    modules = joined(make_live(data, adapter, matcher=ExplodingMatcher), blobs, "fx-prop-1")
    session = CaseSession("LIVE-C", modules, Trace("LIVE-C", DataSource.LIVE))
    run_case(session, PolicyChooser(), lambda draft: "send")
    evidence = session.evidence_file()
    assert evidence.photos[0].points is not None and evidence.photos[0].points.sampled


def test_a_case_with_no_live_pairs_writes_no_points(world, tmp_path):
    from snapback.agent.place import write_evidence_file
    from snapback.contracts import LocateResult, PhotoLocation

    located = LocateResult(
        case_id="x",
        photos=[PhotoLocation(photo_id="l1", status=LocateStatus.NOT_LOCATED)],
        thresholds_version="t",
    )
    evidence = write_evidence_file("x", DataSource.FIXTURE, located)
    assert evidence.photos[0].points is None and evidence.photos[0].alias == "P1"


def test_the_api_case_attaches_the_evidence_file_only_when_live(world, tmp_path):
    from snapback.api.cases import SessionCase

    def runner(session):
        return run_case(session, PolicyChooser(), lambda draft: "send")

    live, modules = live_session(world, tmp_path / "live")
    case = SessionCase("LV1", live, modules._listing, runner)
    case.advance()
    assert case.files is not None and case.files.evidence is not None
    assert all(p.points is not None for p in case.files.evidence.photos)

    fixture, modules = live_session(world, tmp_path / "fx", source=DataSource.FIXTURE)
    staged = SessionCase("FX1", fixture, modules._listing, runner)
    staged.advance()
    assert staged.files is None  # the routes keep serving the team-made fixture


def test_a_cache_entry_from_before_the_pairs_were_kept_is_run_again(world, tmp_path):
    """An entry written by older code has no "points" field: using it would show no lines for
    that ad forever. It is run again, and the rewritten entry carries the pairs."""
    data, sweeps, adapter = fresh_data(world, tmp_path)
    blobs = [photo(sweeps, "fx-model-a", 2, 1)]
    live = make_live(data, adapter)
    first = live.locate("c1", blobs, "fx-prop-1")
    path = live._cache_path(live._load(), blobs, "fx-prop-1")
    old = json.loads(path.read_text())
    del old["points"]
    path.write_text(json.dumps(old))
    again = make_live(data, adapter).locate("c2", blobs, "fx-prop-1")
    assert not again.from_cache and again.points == first.points
    assert "points" in json.loads(path.read_text())


def test_a_cache_entry_whose_poses_lack_the_viewer_angles_is_run_again(world, tmp_path):
    """#244 review: an entry written before poses carried yaw_deg/pitch_deg would make the walk
    read the quaternion again. It is run again, and the rewritten entry carries the angles."""
    data, sweeps, adapter = fresh_data(world, tmp_path)
    blobs = [photo(sweeps, "fx-model-a", 2, 1)]
    live = make_live(data, adapter, budget=120.0)
    first = live.locate("c1", blobs, "fx-prop-1")
    assert first.result.poses and all(p.yaw_deg is not None for p in first.result.poses.values())
    path = live._cache_path(live._load(), blobs, "fx-prop-1")
    old = json.loads(path.read_text())
    for pose in old["result"]["poses"].values():
        pose.pop("yaw_deg", None)
        pose.pop("pitch_deg", None)
    path.write_text(json.dumps(old))
    again = make_live(data, adapter, budget=120.0).locate("c2", blobs, "fx-prop-1")
    assert not again.from_cache
    rewritten = json.loads(path.read_text())["result"]["poses"]
    assert all(p["yaw_deg"] is not None and p["pitch_deg"] is not None for p in rewritten.values())
