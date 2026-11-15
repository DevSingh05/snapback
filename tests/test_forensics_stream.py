"""The SYNTHETIC 90-day ad stream: reproducible, the right size, nothing real in it, and the
rings change how they work over time while honest look-alikes sit beside them."""

import json
import re
from collections import Counter

import pytest

from snapback.forensics.corpus import PHONE_RE, PHOTO_RE, Corpus
from snapback.forensics.stream import DAYS, PHASES, generate_stream

SITE = re.compile(r"https?://([^/\s]+)")


@pytest.fixture(scope="module")
def stream():
    data, truth = generate_stream()
    return Corpus.model_validate(data), truth


def test_same_seed_gives_the_same_bytes_and_another_seed_does_not():
    one, two = generate_stream(7), generate_stream(7)
    assert json.dumps(one, sort_keys=True) == json.dumps(two, sort_keys=True)
    assert json.dumps(generate_stream(8)[0], sort_keys=True) != json.dumps(one[0], sort_keys=True)


def test_about_three_thousand_ads_over_ninety_days_with_ten_rings(stream):
    corpus, truth = stream
    assert 2700 <= len(corpus.ads) <= 3400
    days = sorted({ad.posted_at for ad in corpus.ads})
    assert len(days) == DAYS
    assert [ad.id for ad in corpus.ads] == list(range(1, len(corpus.ads) + 1))
    assert [ad.posted_at for ad in corpus.ads] == sorted(ad.posted_at for ad in corpus.ads)
    assert len(truth["rings"]) == 10
    assert all(len(ids) >= 16 for ids in truth["rings"].values())


@pytest.mark.parametrize("n", [8, 12])
def test_eight_to_twelve_rings_can_be_planted(n):
    assert len(generate_stream(3, n)[1]["rings"]) == n


@pytest.mark.parametrize("n", [7, 13])
def test_other_ring_counts_are_refused(n):
    with pytest.raises(ValueError):
        generate_stream(3, n)


def test_nothing_in_it_is_real(stream):
    corpus, truth = stream
    assert corpus.label.startswith("SYNTHETIC") and truth["label"].startswith("SYNTHETIC")
    for ad in corpus.ads:
        assert ad.synthetic
        assert PHONE_RE.match(ad.phone)
        assert all(PHOTO_RE.match(photo) for photo in ad.photos)
        assert all(host.endswith(".example") for host in SITE.findall(ad.text))
        assert not re.search(r"\d{3}[-.\s]\d{3}[-.\s]\d{4}", ad.text)  # no ten-digit numbers


def test_every_way_of_working_is_planted(stream):
    _, truth = stream
    assert set(truth["styles"].values()) == {"photos", "sites", "wording", "copier"}


def test_rings_rotate_phones(stream):
    corpus, truth = stream
    by_id = corpus.by_id()
    for ids in truth["rings"].values():
        used = Counter(by_id[i].phone for i in ids)
        assert len(used) >= 4
        assert max(used.values()) <= 4  # a number is dropped after a few ads


def test_ring_phases_run_early_middle_late(stream):
    corpus, truth = stream
    by_id = corpus.by_id()
    for name, ids in truth["rings"].items():
        phases = [truth["phase_of_ad"][str(i)] for i in sorted(ids)]
        assert sorted(phases, key=PHASES.index) == phases
        assert set(phases) == set(PHASES)
        started = [truth["phase_started"][name][p] for p in PHASES]
        assert started == sorted(started)
        assert started[0] == min(by_id[i].posted_at for i in ids)


def test_sites_move_from_none_to_a_pay_site_to_lookalikes(stream):
    corpus, truth = stream
    by_id = corpus.by_id()
    hosts = {p: set() for p in PHASES}
    for ids in truth["rings"].values():
        for i in ids:
            hosts[truth["phase_of_ad"][str(i)]].update(SITE.findall(by_id[i].text))
    assert hosts["early"] == set()
    assert hosts["middle"] and all("deposit" in h for h in hosts["middle"])
    # a lookalike: a doubled letter, an added word or a swapped ending on the manager's name
    assert hosts["late"]
    assert all("harborow" in re.sub(r"(.)\1+", r"\1", h) for h in hosts["late"])
    assert "harborrow.example" not in hosts["late"]  # lookalikes, never the manager's own site


def test_reused_photos_drift_further_as_a_ring_goes_on(stream):
    """Late copies sit further from the ring's original photo than early ones."""
    corpus, truth = stream
    by_id = corpus.by_id()

    def bits(a: str, b: str) -> int:
        return bin(int(a[3:], 16) ^ int(b[3:], 16)).count("1")

    gaps = {p: [] for p in PHASES}
    for name, ids in truth["rings"].items():
        if truth["styles"][name] != "photos":
            continue
        originals = [photo for group in truth["photo_pools"][name] for photo in group]
        for i in ids:
            for photo in by_id[i].photos:
                near = min(bits(photo, old) for old in originals)
                if near <= 16:  # a copy, not one of the fresh sets a ring mixes in late
                    gaps[truth["phase_of_ad"][str(i)]].append(near)
    mean = {p: sum(v) / len(v) for p, v in gaps.items()}
    assert mean["early"] < mean["middle"] < mean["late"]
    assert max(gaps["early"]) <= 3 and max(gaps["late"]) > 6


def test_hard_honest_negatives_are_in_the_stream(stream):
    corpus, truth = stream
    ring_ads = {i for ids in truth["rings"].values() for i in ids}
    honest = [ad for ad in corpus.ads if ad.id not in ring_ads]
    by_phone = Counter(ad.phone for ad in honest)
    assert by_phone.most_common(1)[0][1] >= 80  # one manager, one number, many buildings
    assert truth["hard_negatives"]["second_manager_ads"] >= 20
    photo_sets = Counter(tuple(ad.photos) for ad in honest)
    assert sum(1 for n in photo_sets.values() if n >= 2) >= 10  # owners relisting a unit
    assert sum(1 for ad in honest if re.search(r"deposit|zelle", ad.text, re.I)) >= 500
    assert any("harborrow.example" in ad.text for ad in honest)
