"""A22 (#141): the merged V2 locator, wired into live cases.

Fixture twins (FixtureMatterport), a tiny embedder index and the numpy PatchMatcher: no
network, no weights, no torch. The real DISK+LightGlue timing is not measured here.
"""

import io
import json
import time
from dataclasses import replace
from datetime import datetime

import pytest
from PIL import Image

from snapback.adapters.matterport import FixtureMatterport
from snapback.agent import CaseSession, PolicyChooser, Trace, run_case
from snapback.agent.intake import read_listing
from snapback.agent.join import JoinedModules
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
