"""Time to detect on the SYNTHETIC 90-day stream: the day arithmetic on a hand-made case, and
the committed timeline checked against the ring finder it claims to come from."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from snapback.api.main import create_app
from snapback.forensics.corpus import PHONE_RE, Corpus
from snapback.forensics.detect import (
    SIGNAL_WEIGHTS,
    TIMELINE_PATH,
    VIEWS_PER_AD_DAY,
    ad_flag_days,
    day_index,
    detection,
    exposure,
    first_flag_day,
    first_union_flag_day,
    load_timeline,
    signals,
    summarize_signals,
)
from snapback.forensics.pipeline import analyze
from snapback.forensics.rings import MIN_ADS, W_PHONE, W_PHOTO, W_PHRASE
from snapback.forensics.stream import DAYS, START, generate_stream

# A hand-made run: nothing on days 0 and 1, a group of three on day 2 (too few), the same
# operator's fourth ad on day 3, and a second group from day 4.
DAILY = [
    [],
    [],
    [{1, 2, 3}],
    [{1, 2, 3, 4}],
    [{1, 2, 3, 4, 5}, {10, 11, 12, 13}],
]


def test_day_zero_is_the_first_day_of_the_stream():
    assert day_index("2026-08-17", date(2026, 8, 17)) == 0
    assert day_index("2026-09-01", date(2026, 8, 17)) == 15


def test_a_group_is_flagged_the_first_day_one_reported_group_shares_enough_ads():
    assert first_flag_day({1, 2, 3, 4, 5}, DAILY, need=4) == 3
    assert first_flag_day({10, 11, 12, 13}, DAILY, need=4) == 4
    assert first_flag_day({1, 2, 3, 4, 5}, DAILY, need=3) == 2
    assert first_flag_day({20, 21, 22, 23}, DAILY, need=4) is None


def test_a_seeded_ring_split_across_groups_is_flagged_on_the_union():
    split = {4, 5, 10, 11}  # two ads in each reported group on day 4
    assert first_flag_day(split, DAILY, need=4) is None
    assert first_union_flag_day(split, DAILY, need=4) == 4


def test_each_ad_keeps_the_first_day_it_sat_in_a_group():
    assert ad_flag_days(DAILY) == {1: 2, 2: 2, 3: 2, 4: 3, 5: 4, 10: 4, 11: 4, 12: 4, 13: 4}


def test_time_to_detect_and_what_was_up_before_the_flag():
    # ads posted on days 3, 4, 6 and 9; flagged on day 7
    found = detection([3, 4, 6, 9], 7)
    assert found["first_day"] == 3 and found["flag_day"] == 7 and found["gap_days"] == 4
    assert found["ads_before_flag"] == 3  # the day-9 ad came after the flag
    assert found["ad_days_before_flag"] == (7 - 3) + (7 - 4) + (7 - 6)
    assert found["renters_est"] == 8 * VIEWS_PER_AD_DAY


def test_a_group_flagged_on_its_first_day_exposed_nobody():
    assert detection([5, 5, 5, 5], 5) == {
        "first_day": 5,
        "flag_day": 5,
        "gap_days": 0,
        "ads_before_flag": 0,
        "ad_days_before_flag": 0,
        "renters_est": 0,
    }


def test_never_flagged_counts_every_ad_to_the_end_of_the_stream():
    assert detection([88, 89], None)["gap_days"] is None
    assert exposure([88, 89], None, views=1)["ad_days_before_flag"] == (DAYS - 88) + (DAYS - 89)


def test_signal_weights_are_the_ring_finders_own():
    assert SIGNAL_WEIGHTS == {"phone": W_PHONE, "photo": W_PHOTO, "wording": W_PHRASE, "site": 0}


def test_signal_summary_counts_values_and_different_ads():
    items = [
        {"kind": "phone", "ad_ids": [1, 2]},
        {"kind": "phone", "ad_ids": [3, 4, 5]},
        {"kind": "wording", "ad_ids": [1, 2, 3]},
        {"kind": "wording", "ad_ids": [2, 3, 4]},
    ]
    assert summarize_signals(items) == {
        "phone": {"values": 2, "ads": 5, "weight": W_PHONE},
        "wording": {"values": 2, "ads": 4, "weight": W_PHRASE},
    }


# ---- the committed timeline against the finder -------------------------------------------


@pytest.fixture(scope="module")
def timeline():
    return load_timeline()


@pytest.fixture(scope="module")
def stream():
    data, truth = generate_stream()
    return Corpus.model_validate(data), truth


@pytest.fixture(scope="module")
def full(stream):
    return analyze(stream[0])


def _prefix(corpus: Corpus, day: int) -> list[set[int]]:
    seen = [ad for ad in corpus.ads if day_index(ad.posted_at, START) <= day]
    return [set(r.ad_ids) for r in analyze(Corpus(label="x", seed=0, ads=seen)).rings]


def test_the_timeline_is_labelled_and_holds_nothing_real(timeline):
    assert timeline["label"] == "SYNTHETIC DATA" and timeline["synthetic"] is True
    assert timeline["source"] == "FIXTURE"
    assert timeline["days"] == DAYS and timeline["start"] == START.isoformat()
    for group in timeline["groups"]:
        assert all(PHONE_RE.match(ad["phone"]) for ad in group["ads"])
        for s in group["signals"]:
            if s["kind"] == "site":
                assert s["key"].endswith(".example")


def test_the_timelines_groups_are_the_finders_groups_on_the_whole_stream(timeline, stream, full):
    assert timeline["n_ads"] == len(stream[0].ads)
    assert [[ad["id"] for ad in g["ads"]] for g in timeline["groups"]] == [
        r.ad_ids for r in full.rings
    ]
    in_groups = sum(g["n_ads"] for g in timeline["groups"])
    assert sum(timeline["other_ads_by_day"]) == timeline["n_ads"] - in_groups


def test_the_timelines_signals_are_recomputed_from_the_graph(timeline, full):
    for group, ring in zip(timeline["groups"], full.rings, strict=True):
        fresh = signals(full.graph, ring)
        assert group["signals"] == fresh
        assert group["by_kind"] == summarize_signals(fresh)
        for s in fresh:
            assert s["n_ads"] >= 2 and set(s["ad_ids"]) <= set(ring.ad_ids)
            if s["kind"] == "phone":
                assert all(full.graph.ads[a].phone == s["key"] for a in s["ad_ids"])


def test_the_earliest_flag_day_holds_on_a_fresh_run_and_the_day_before_does_not(timeline, stream):
    group = min(timeline["groups"], key=lambda g: g["flag_day"])
    members = {ad["id"] for ad in group["ads"]}
    day = group["flag_day"]
    assert any(len(g & members) >= MIN_ADS for g in _prefix(stream[0], day))
    assert not any(len(g & members) >= MIN_ADS for g in _prefix(stream[0], day - 1))
    assert group["gap_days"] == day - min(ad["day"] for ad in group["ads"])


def test_every_groups_detection_follows_from_its_own_ads(timeline):
    for group in timeline["groups"]:
        again = detection([ad["day"] for ad in group["ads"]], group["flag_day"])
        assert {k: group[k] for k in again} == again
        assert all(ad["day"] <= ad["flag_day"] for ad in group["ads"])


def test_the_summary_is_the_median_over_the_groups_with_its_n(timeline):
    gaps = sorted(g["gap_days"] for g in timeline["groups"])
    summary = timeline["summary"]
    assert summary["n_gap"] == len(gaps) == summary["groups_found"]
    mid = len(gaps) // 2
    middle = gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2
    assert summary["median_gap_days"] == middle


def test_the_answer_key_score_matches_the_truth_file(timeline, stream, full):
    key, truth = timeline["answer_key"], stream[1]
    assert key["n_seeded"] == len(truth["rings"]) == len(key["seeded"])
    assert key["ring_ads"] == sum(len(v) for v in truth["rings"].values())
    flagged = set().union(*(set(r.ad_ids) for r in full.rings))
    real = {a for ids in truth["rings"].values() for a in ids}
    assert key["ring_ads_flagged"] == len(flagged & real)
    assert key["honest_flagged"] == len(flagged - real)
    assert key["seeded_flagged"] == sum(1 for r in key["seeded"] if r["flag_day"] is not None)
    assert key["n_gap"] == key["seeded_flagged"]


def test_the_api_serves_the_committed_timeline():
    body = TestClient(create_app()).get("/forensics/stream").json()
    assert body == json.loads(TIMELINE_PATH.read_text())
    assert body["label"] == "SYNTHETIC DATA" and body["source"] == "FIXTURE"
