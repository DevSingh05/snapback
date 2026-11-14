"""Forensics (Arlequin track): the SYNTHETIC corpus, the pipeline, the investigator and the API.

Every ad, number and photo id here is made by `snapback.forensics.generate`; nothing is real and
nothing comes from CoStar, Matterport or Vexcel.
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from snapback.api.main import create_app
from snapback.forensics.corpus import (
    ADS_PATH,
    PHONE_RE,
    PHOTO_RE,
    TRUTH_PATH,
    Corpus,
    load_corpus,
    load_truth,
)
from snapback.forensics.evaluate import evaluate, evaluate_seed, keyword_groups
from snapback.forensics.generate import DEFAULT_SEED, generate
from snapback.forensics.graph import hamming
from snapback.forensics.investigator import EXAMPLES, NO_EVIDENCE, Answer, ask, verify_answer
from snapback.forensics.pipeline import default_analysis


@pytest.fixture(scope="module")
def analysis():
    return default_analysis()


# ---- generator ----------------------------------------------------------------------------


def test_generator_is_deterministic():
    first, second = generate(7), generate(7)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert json.dumps(generate(8)[0], sort_keys=True) != json.dumps(first[0], sort_keys=True)


def test_committed_fixture_is_what_the_generator_makes():
    corpus, truth = generate(DEFAULT_SEED)
    assert json.loads(ADS_PATH.read_text()) == json.loads(json.dumps(corpus))
    assert json.loads(TRUTH_PATH.read_text()) == json.loads(json.dumps(truth))


def test_corpus_shape_and_label():
    corpus = load_corpus()
    assert 280 <= len(corpus.ads) <= 320
    assert "SYNTHETIC" in corpus.label
    assert all(ad.synthetic for ad in corpus.ads)
    assert [ad.id for ad in corpus.ads] == list(range(1, len(corpus.ads) + 1))
    truth = load_truth()
    assert sorted(truth) == ["A", "B", "C", "D"]
    assert 3 <= len(truth) <= 4 + 1


def test_every_phone_is_a_555_number_and_photo_ids_are_hash_shaped():
    corpus = load_corpus()
    for ad in corpus.ads:
        assert PHONE_RE.match(ad.phone), ad.phone
        assert ad.phone.startswith("555-")
        assert not re.search(r"\b(?!555)\d{3}[-. )]\d{3,4}", ad.text), ad.id
        assert all(PHOTO_RE.match(p) for p in ad.photos)


def test_no_real_looking_street_number_or_sponsor_text():
    blob = ADS_PATH.read_text().lower()
    for banned in ("costar", "matterport", "vexcel", "homes.com", "apartments.com", "@"):
        assert banned not in blob


def test_recropped_photos_differ_by_few_bits_but_not_zero():
    corpus = load_corpus()
    truth = load_truth()
    by_id = corpus.by_id()
    a_ads = [by_id[i] for i in truth["A"]]
    distances = {
        hamming(p, q)
        for x in a_ads
        for y in a_ads
        if x.id < y.id
        for p in x.photos
        for q in y.photos
        if hamming(p, q) <= 6
    }
    assert any(d > 0 for d in distances), "re-crops must not be exact copies"


# ---- pipeline -----------------------------------------------------------------------------


def test_ring_recovery_on_the_seed(analysis):
    metrics = evaluate(analysis)
    assert metrics["synthetic"] is True
    pipe = metrics["pipeline"]
    assert pipe["ring_recall"] == 1.0
    assert pipe["ring_precision"] == 1.0
    assert pipe["ad_precision"] >= 0.95
    assert pipe["ad_recall"] >= 0.95
    assert [len(r.ad_ids) for r in analysis.rings] == [22, 15, 12, 8]


def test_keyword_baseline_misses_what_the_pipeline_finds(analysis):
    metrics = evaluate(analysis)
    base = metrics["keyword_baseline"]
    assert base["ring_recall"] < 0.5
    assert base["ad_recall"] < 0.4
    assert metrics["pipeline"]["ad_recall"] - base["ad_recall"] > 0.5
    # the groups a keyword search can build never recover a rotated-number ring
    truth = load_truth()
    for group in keyword_groups(analysis.corpus):
        assert len(group & set(truth["D"])) < len(truth["D"]) * 0.7


def test_ring_recovery_holds_on_unseen_seeds():
    for seed in (101, 102, 104):
        pipe = evaluate_seed(seed)["pipeline"]
        assert pipe["ring_recall"] >= 0.75, seed
        assert pipe["ad_precision"] >= 0.95, seed


def test_honest_look_alikes_stay_out(analysis):
    truth = load_truth()
    in_ring = {a for r in analysis.rings for a in r.ad_ids}
    real = {a for ids in truth.values() for a in ids}
    assert in_ring <= real
    # the ads whose photos ring B copied are honest and are reported as sources, not members
    sources = json.loads(TRUTH_PATH.read_text())["ring_b_source_ads"]
    assert not set(sources) & in_ring
    ring_b = max(analysis.rings, key=lambda r: len(set(r.sources) & set(sources)))
    assert set(ring_b.sources) <= set(sources)
    assert len(ring_b.sources) >= 10


def test_property_manager_with_one_number_is_not_a_ring(analysis):
    real = {a for ids in load_truth().values() for a in ids}
    managers = [
        p for p, ids in analysis.graph.phone_ads.items() if len(ids) >= 5 and not set(ids) & real
    ]
    assert len(managers) == 5
    ring_ads = {a for r in analysis.rings for a in r.ad_ids}
    for phone in managers:
        assert not set(analysis.graph.phone_ads[phone]) & ring_ads


def test_reworded_text_is_linked_without_shared_keywords(analysis):
    # ring C never says "zelle", "wire" or "before move-in", yet its wordings are one finding
    ring_c = analysis.rings[2]
    text = " ".join(analysis.graph.ads[a].text.lower() for a in ring_c.ad_ids)
    assert "zelle" not in text and "before move-in" not in text
    kinds = {f.kind for f in ring_c.findings}
    assert "shared_phrasing" in kinds and "phone_rotation" in kinds


def test_every_finding_cites_evidence_that_exists(analysis):
    for ring in analysis.rings:
        assert ring.findings
        for finding in ring.findings:
            assert finding.evidence, (ring.id, finding.id)
            assert 0.0 <= finding.score <= 1.0
            for e in finding.evidence:
                ad = analysis.graph.ads[e.ad_id]
                if e.span is not None:
                    assert e.span in ad.text
                assert all(p in ad.photos for p in e.photo_ids)
                if e.phone is not None:
                    assert e.phone == ad.phone


def test_timeline_is_ordered_and_starts_at_first_ad(analysis):
    for ring in analysis.rings:
        dates = [e.date for e in ring.timeline]
        assert dates == sorted(dates)
        assert ring.timeline[0].kind == "first_ad"
        assert ring.timeline[0].date == ring.first_seen
        assert sum(n for _, n in ring.weekly) == len(ring.ad_ids)


# ---- investigator -------------------------------------------------------------------------


def _questions(analysis):
    ring_ad = analysis.rings[0].ad_ids[3]
    copier = next(f for f in analysis.rings[1].findings if f.kind == "copied_listing").evidence[0]
    return [
        f"Which ads share photos with ad {ring_ad}?",
        f"Which ring is ad {ring_ad} in?",
        "When did ring B start?",
        "When did ring B end?",
        "What numbers does ring C use?",
        "How does ring D ask for money?",
        f"Where were the photos in ad {copier.ad_id} copied from?",
        f"Which phone does ad {ring_ad} use?",
        "How many ads are in ring A?",
        "List the rings.",
        "Which ring is ad 1 in?",
    ]


def test_every_answer_cites_evidence_and_the_evidence_is_real(analysis):
    for q in _questions(analysis):
        answer = ask(analysis, q)
        assert answer.grounded, q
        assert answer.evidence, q
        assert verify_answer(analysis, answer), q
        assert answer.mode == "fixture" and answer.synthetic


def test_answers_name_the_right_things(analysis):
    ring_ad = analysis.rings[0].ad_ids[3]
    shared = ask(analysis, f"Which ads share photos with ad {ring_ad}?")
    others = {e.ad_id for e in shared.evidence} - {ring_ad}
    assert others and others <= set(analysis.rings[0].ad_ids)
    start = ask(analysis, "When did ring B start?")
    assert analysis.rings[1].first_seen in start.answer
    copier = next(f for f in analysis.rings[1].findings if f.kind == "copied_listing").evidence[0]
    src = ask(analysis, f"Where were the photos in ad {copier.ad_id} copied from?")
    assert (
        str(analysis.graph.ads[copier.ad_id].posted_at) in src.answer
        or "first posted" in src.answer
    )
    assert {e.ad_id for e in src.evidence} >= {copier.ad_id}


def test_no_evidence_means_it_says_so(analysis):
    for q in [
        "Who owns the building in ad 5?",
        "What is the weather like?",
        "Which ads share photos with ad 99999?",
        "When did ring Z start?",
    ]:
        answer = ask(analysis, q)
        assert answer.grounded is False, q
        assert answer.evidence == [], q
        assert verify_answer(analysis, answer), q
    assert ask(analysis, "Who owns the building in ad 5?").answer == NO_EVIDENCE


def test_verify_answer_rejects_a_forged_citation(analysis):
    good = ask(analysis, "When did ring B start?")
    forged = good.model_copy(deep=True)
    forged.evidence[0].span = "This sentence is not in the ad."
    assert not verify_answer(analysis, forged)
    ghost = good.model_copy(deep=True)
    ghost.evidence[0].ad_id = 99999
    assert not verify_answer(analysis, ghost)
    empty = Answer(question="q", answer="x", grounded=True, intent="x", evidence=[])
    assert not verify_answer(analysis, empty)


def test_model_reply_must_stay_inside_the_evidence(analysis):
    from snapback.forensics.agent_tool import accept_model_reply

    base = ask(analysis, "When did ring B start?")
    cited = base.evidence[0].ad_id
    ok = accept_model_reply(analysis, base, f"Ring B began with ad {cited}.")
    assert ok.mode == "model"
    drift = accept_model_reply(analysis, base, "Ring B began with ad 3 and ad 4.")
    assert drift.mode == "fixture" and drift.answer == base.answer
    uncited = accept_model_reply(analysis, base, "It started in March.")
    assert uncited.mode == "fixture"
    none = ask(analysis, "What is the weather like?")
    assert accept_model_reply(analysis, none, "Ad 3 says it is sunny.").mode == "fixture"


def test_examples_are_answerable(analysis):
    ring_ad = analysis.rings[0].ad_ids[3]
    for template in EXAMPLES:
        answer = ask(analysis, template.format(ad=ring_ad, ring="A"))
        assert answer.grounded, template


# ---- API ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from snapback.settings import Settings

    data = tmp_path_factory.mktemp("data")
    return TestClient(create_app(Settings(snapback_data_dir=str(data))))


def test_api_rings_shape(client):
    body = client.get("/forensics/rings").json()
    assert body["label"] == "SYNTHETIC DATA" and body["synthetic"] is True
    assert body["source"] == "FIXTURE"
    assert [r["id"] for r in body["rings"]] == ["A", "B", "C", "D"]
    first = body["rings"][0]
    assert {"id", "label", "n_ads", "n_phones", "first_seen", "last_seen", "score"} <= set(first)
    assert body["metrics"]["pipeline"]["ring_recall"] == 1.0
    assert body["metrics"]["keyword_baseline"]["ring_recall"] < 0.5
    assert body["example_questions"]


def test_api_one_ring_shape(client):
    body = client.get("/forensics/rings/b").json()
    assert body["synthetic"] is True
    ring = body["ring"]
    assert ring["id"] == "B" and len(ring["ad_ids"]) == 15
    assert ring["findings"] and ring["timeline"] and ring["weekly"]
    node_ids = {n["id"] for n in body["graph"]["nodes"]}
    assert all(e["source"] in node_ids and e["target"] in node_ids for e in body["graph"]["edges"])
    assert len(body["ads"]) == 15
    assert client.get("/forensics/rings/Z").status_code == 404


def test_api_ask_shape(client):
    ok = client.post("/forensics/ask", json={"question": "When did ring B start?"}).json()
    assert ok["grounded"] is True and ok["evidence"] and ok["mode"] == "fixture"
    none = client.post("/forensics/ask", json={"question": "Is the moon made of cheese?"}).json()
    assert none["grounded"] is False and none["evidence"] == []
    assert client.post("/forensics/ask", json={"question": ""}).status_code == 422
    assert client.post("/forensics/ask", json={"question": "x" * 400}).status_code == 422


def test_corpus_type_roundtrip():
    corpus = load_corpus()
    assert Corpus.model_validate(json.loads(corpus.model_dump_json())) == corpus
