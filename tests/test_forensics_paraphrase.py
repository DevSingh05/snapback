"""The reworded-ads robustness eval (SYNTHETIC data only): the paraphraser, the harness, the
committed results file, and the phone/photo-copy fallback in the ring finder."""

import json
import random

import pytest

from snapback.forensics.corpus import Corpus, load_corpus
from snapback.forensics.evaluate import evaluate
from snapback.forensics.extract import extract_facts, pressure_sentences
from snapback.forensics.paraphrase import (
    RESULTS_PATH,
    build_ask,
    live_rewriter,
    paraphrase_ad,
    paraphrase_corpus,
    reformat_prices,
    rings_found,
    run,
    text_overlap,
)
from snapback.forensics.pipeline import analyze
from snapback.forensics.stream import DEFAULT_SEED, generate_stream


@pytest.fixture(scope="module")
def stream():
    data, truth = generate_stream(DEFAULT_SEED)
    corpus = Corpus.model_validate(data)
    rings = {k: {int(i) for i in v} for k, v in truth["rings"].items()}
    return corpus, rings, set().union(*rings.values())


def test_paraphrase_is_deterministic(stream):
    corpus, _, ring_ids = stream
    ad = next(a for a in corpus.ads if a.id in ring_ids)
    a = paraphrase_ad(ad, 7, is_ring=True)
    b = paraphrase_ad(ad, 7, is_ring=True)
    assert a.text == b.text
    assert paraphrase_ad(ad, 8, is_ring=True).text != a.text


def test_paraphrase_keeps_phone_photos_and_label(stream):
    corpus, _, ring_ids = stream
    ad = next(a for a in corpus.ads if a.id in ring_ids)
    out = paraphrase_ad(ad, 7, is_ring=True)
    assert (out.phone, out.photos, out.synthetic) == (ad.phone, ad.photos, True)
    assert out.text != ad.text


def test_paraphrase_removes_shared_asks_inside_rings(stream):
    corpus, rings, ring_ids = stream
    para = paraphrase_corpus(corpus, ring_ids, 7)
    before, after = text_overlap(corpus, rings), text_overlap(para, rings)
    assert before > 0.03  # the original rings do share some identical ask sentences
    assert after < before / 3


def test_honest_guarded_deposit_lines_stay_guarded(stream):
    corpus, rings, ring_ids = stream
    para = paraphrase_corpus(corpus, ring_ids, 7)
    honest = [a for a in para.ads if a.id not in ring_ids]
    assert [a.text for a in honest] != [a.text for a in corpus.ads if a.id not in ring_ids]
    # no honest ad turns into a payment-first ask by being reworded
    originals = {a.id: a for a in corpus.ads}
    for ad in honest[:400]:
        was = bool(pressure_sentences(extract_facts(originals[ad.id])))
        now = bool(pressure_sentences(extract_facts(ad)))
        assert now <= was, ad.id


def test_price_formats_change_and_keep_the_amount():
    rng = random.Random(1)
    out = {reformat_prices("Pay $1,080 today.", random.Random(i)) for i in range(20)}
    assert len(out) > 1
    assert all("1080" in o or "1,080" in o for o in out)
    assert reformat_prices("no price here", rng) == "no price here"


def test_built_asks_vary():
    asks = {build_ask(random.Random(i)) for i in range(200)}
    assert len(asks) > 150


def test_rings_found_uses_min_ads():
    truth = {"R": {1, 2, 3, 4, 5}}
    assert rings_found([{1, 2, 3, 4}], truth) == 1
    assert rings_found([{1, 2, 3}], truth) == 0
    assert rings_found([], truth) == 0


def test_live_rewriter_needs_a_key_and_never_leaks(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert live_rewriter() is None
    seen = []
    rewrite = live_rewriter(post=lambda s: seen.append(s) or "Funds first.\nextra")
    assert rewrite("Zelle the deposit.", random.Random(1)) == "Funds first."
    boom = live_rewriter(post=lambda s: (_ for _ in ()).throw(RuntimeError("x")))
    assert boom("Zelle the deposit.", random.Random(1))  # falls back to a built ask
    capped = live_rewriter(post=lambda s: "ok", cap=1)
    capped("a", random.Random(1))
    assert capped("b", random.Random(1)) != "ok"


def test_fallback_hop_is_off_by_default_and_changes_nothing_on_the_seed():
    corpus = load_corpus()
    base, hop = evaluate(analyze(corpus)), evaluate(analyze(corpus, hop=True))
    assert base["pipeline"]["ring_recall"] == 1.0
    assert hop["pipeline"]["ring_recall"] == 1.0
    assert hop["pipeline"]["honest_flagged"] == 0


def test_results_file_is_labelled_and_reproducible():
    saved = json.loads(RESULTS_PATH.read_text())
    assert saved["synthetic"] is True and "SYNTHETIC" in saved["label"]
    made = run(DEFAULT_SEED)
    assert made == saved  # CI regenerates the same bytes
    v = made["variants"]
    n = made["n_rings"]
    assert n == 10 and made["n_honest"] == 2684
    assert v["original"]["pipeline"]["rings_found"] == 10
    # the honest result: rewording costs the shipped finder rings; the fallback wins most back
    assert v["paraphrased"]["pipeline"]["rings_found"] < 10
    assert (
        v["paraphrased"]["pipeline_hop"]["rings_found"]
        > v["paraphrased"]["pipeline"]["rings_found"]
    )
    assert (
        v["paraphrased"]["keyword_baseline"]["rings_found"]
        < v["paraphrased"]["pipeline"]["rings_found"]
    )
    for variant in v.values():
        for who in ("pipeline", "pipeline_hop", "keyword_baseline"):
            assert variant[who]["honest_flagged"] == 0
            assert variant[who]["n_rings"] == n
