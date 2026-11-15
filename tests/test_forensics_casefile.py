"""The ring case file and the case study: the export shape, and the study's steps checked
against a fresh run of the detector. All data is SYNTHETIC (`fixtures/forensics/`)."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from snapback.api.main import create_app
from snapback.forensics.casefile import (
    SCHEMA,
    build_case_file,
    build_case_study,
    pair_ties,
)
from snapback.forensics.corpus import PHONE_RE, Corpus
from snapback.forensics.pipeline import analyze, default_analysis
from snapback.forensics.rings import MIN_ADS


@pytest.fixture(scope="module")
def analysis():
    return default_analysis()


@pytest.fixture(scope="module")
def study(analysis):
    return build_case_study(analysis)


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def _detector_flags(analysis, ring, day: str) -> bool:
    """An independent run of the finder on only the ads posted up to `day`."""
    seen = [a for a in analysis.corpus.ads if a.posted_at <= day]
    prefix = analyze(Corpus(label="x", seed=0, ads=seen))
    return any(len(set(g.ad_ids) & set(ring.ad_ids)) >= MIN_ADS for g in prefix.rings)


def test_case_file_export_shape(analysis):
    cf = build_case_file(analysis, "D")
    ring = analysis.ring("D")
    assert cf["schema"] == SCHEMA
    assert cf["synthetic"] is True and cf["label"] == "SYNTHETIC DATA"
    assert set(cf) >= {
        "ring", "detection", "timeline", "contacts", "links", "signals", "strongest",
        "not_known", "findings", "sources",
    }  # fmt: skip
    json.dumps(cf)  # the export must be plain JSON
    assert [a["id"] for a in cf["timeline"]] == ring.ad_ids
    dates = [a["posted_at"] for a in cf["timeline"]]
    assert dates == sorted(dates)
    for a in cf["timeline"]:
        assert PHONE_RE.match(a["phone"])
        assert set(a["amount_asked"]) == {"sentence", "item", "usd", "basis"}
    assert sorted(p for c in cf["contacts"] for p in [c["phone"]]) == ring.phones
    assert cf["not_known"], "a case file always says what is not known"


def test_case_file_links_point_back_in_time_with_evidence(analysis):
    cf = build_case_file(analysis, "A")
    pos = {a["id"]: i for i, a in enumerate(cf["timeline"])}
    assert cf["links"]
    for lk in cf["links"]:
        assert pos[lk["from_ad"]] < pos[lk["to_ad"]]
        assert lk["kind"] in {"phone", "photo", "wording", "link"}
        assert lk["evidence"]
    kinds = {s["kind"] for s in cf["signals"]}
    assert kinds == {"phone", "photo", "wording", "link"}
    assert cf["strongest"] and set(cf["strongest"]) <= kinds


def test_flag_day_matches_a_fresh_detector_run(analysis):
    for rid in ("B", "D"):
        ring = analysis.ring(rid)
        cf = build_case_file(analysis, rid)
        flag = cf["detection"]["flagged_on"]
        first = cf["detection"]["first_ad_date"]
        assert _detector_flags(analysis, ring, flag)
        earlier = [d for d in sorted({a.posted_at for a in analysis.corpus.ads}) if d < flag]
        # the day before the flag, among days the ring posted, the detector did not flag it
        ring_days = sorted({a["posted_at"] for a in cf["timeline"] if a["posted_at"] < flag})
        assert ring_days and ring_days[-1] in earlier
        assert not _detector_flags(analysis, ring, ring_days[-1])
        assert (
            cf["detection"]["days_first_ad_to_flag"]
            == (date.fromisoformat(flag) - date.fromisoformat(first)).days
        )


def test_unknown_ring_is_none(analysis):
    assert build_case_file(analysis, "Z") is None


def test_study_steps_match_detector_output(analysis, study):
    ring = analysis.ring(study["ring"]["id"])
    steps = study["steps"]
    assert [s["step"] for s in steps] == list(range(1, len(steps) + 1))
    assert steps[0]["day_no"] == 1 and steps[0]["ties"] == []
    # one step per ring posting day, in order, ending on the flag
    assert [a for s in steps for a in s["ad_ids"]] == ring.ad_ids[
        : sum(len(s["ad_ids"]) for s in steps)
    ]
    assert steps[-1]["flagged"] and steps[-1]["date"] == study["flagged_on"]
    assert not any(s["flagged"] for s in steps[:-1])
    # the detector's verdict in each step equals a fresh run on that day's prefix
    for s in steps:
        assert _detector_flags(analysis, ring, s["date"]) == s["flagged"]
    # every tie in a step is exactly what the pair comparison finds on that day's graph
    for s in steps[1:]:
        seen = [a for a in analysis.corpus.ads if a.posted_at <= s["date"]]
        graph = analyze(Corpus(label="x", seed=0, ads=seen)).graph
        for t in s["ties"]:
            assert t in [
                {"from_ad": t["from_ad"], "to_ad": t["to_ad"], **x}
                for x in pair_ties(graph, t["from_ad"], t["to_ad"])
            ]


def test_study_text_is_built_from_the_evidence(analysis, study):
    graph = analysis.graph
    text = "\n".join(line for s in study["steps"] for line in s["lines"])
    for s in study["steps"]:
        for a in s["ad_ids"]:
            assert f"Ad {a} goes up from {graph.ads[a].phone}" in text
    for s in study["steps"]:
        for t in s["ties"]:
            ev = t["evidence"]
            if t["kind"] == "phone":
                assert ev["phone"] in text
            elif t["kind"] == "photo":
                assert f"{ev['closest_bits']} of 64 bits" in text
            elif t["kind"] == "wording":
                assert ev["span_newer"] in text
    # a step with no tie says so rather than inventing one
    quiet = [s for s in study["steps"][1:] if not s["ties"]]
    for s in quiet:
        assert any("No number, photo or wording ties it" in line for line in s["lines"])
    assert study["synthetic"] is True


def test_api_case_file_and_study(client, analysis):
    r = client.get("/forensics/rings/D/case-file")
    assert r.status_code == 200
    body = r.json()
    assert body == json.loads(json.dumps(build_case_file(analysis, "D")))
    assert client.get("/forensics/rings/Z/case-file").status_code == 404
    s = client.get("/forensics/case-study")
    assert s.status_code == 200
    assert s.json()["ring"]["id"] in {r.id for r in analysis.rings}


def _untied_note(cf) -> str:
    return next((n for n in cf["not_known"] if n.startswith("Why ad")), "")


def test_untied_counts_ties_in_both_directions(analysis, monkeypatch):
    """An ad that only a LATER ad reuses is tied, so it is not listed as untied."""
    from snapback.forensics import casefile as mod

    order = list(analysis.ring("D").ad_ids)
    early, late = order[1], order[2]
    real = mod.pair_ties

    def fake(graph, older, newer):
        # one photo tie, between `early` (older) and `late` (newer), nothing else
        if (older, newer) == (early, late):
            return [
                {
                    "kind": "photo",
                    "weight": 3,
                    "evidence": {"photo_sets": 1, "closest_bits": 0, "strong": True},
                }
            ]
        return []

    monkeypatch.setattr(mod, "pair_ties", fake)
    note = _untied_note(build_case_file(analysis, "D"))
    listed = note.split(".")[0]
    ids = {
        int(x)
        for x in listed.replace("Why ads", "")
        .replace("Why ad", "")
        .replace("belongs", "")
        .replace("belong", "")
        .replace(",", " ")
        .split()
    }
    assert early not in ids and late not in ids
    assert order[0] in ids
    assert "community step" not in note
    monkeypatch.setattr(mod, "pair_ties", real)


def test_untied_single_ad_uses_singular(analysis, monkeypatch):
    from snapback.forensics import casefile as mod

    order = list(analysis.ring("D").ad_ids)
    lone = order[0]

    def fake(graph, older, newer):
        if lone in (older, newer):
            return []
        return [{"kind": "phone", "weight": 5, "evidence": {"phone": "x"}}]

    monkeypatch.setattr(mod, "pair_ties", fake)
    note = _untied_note(build_case_file(analysis, "D"))
    assert note.startswith(f"Why ad {lone} belongs.")
    assert " It carries no number" in note


def test_recrop_wording_only_when_bits_differ():
    from snapback.forensics.casefile import _tie_sentence

    def tie(bits):
        return {
            "kind": "photo",
            "from_ad": 7,
            "evidence": {"photo_sets": 2, "closest_bits": bits, "strong": True},
        }

    assert "re-cropped" not in _tie_sentence(tie(0))
    assert "re-cropped" in _tie_sentence(tie(3))
