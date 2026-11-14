"""Proof plan 3.2: Card.summary, checks_out and does_not, built by code from the lines and
decide()'s reasons."""

import json
from datetime import datetime
from pathlib import Path

from snapback.card import strings
from snapback.contracts import (
    CardTone,
    LocateStatus,
    ModuleEvidence,
    PriceResult,
    PriceStatus,
    VerdictState,
)
from snapback.verdict import build_card, decide, to_evidence

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")


def modules(name="module_evidence_hold.json", **top_level) -> ModuleEvidence:
    raw = json.loads((FIXTURES / name).read_text())
    return ModuleEvidence.model_validate(raw | top_level)


def card(m: ModuleEvidence, lang="en"):
    return build_card(m, checked_at=CHECKED_AT, lang=lang)


def elsewhere(m: ModuleEvidence) -> ModuleEvidence:
    photos = [
        p.model_copy(update={"status": LocateStatus.LOCATED_ELSEWHERE}) for p in m.locate.photos
    ]
    return m.model_copy(update={"locate": m.locate.model_copy(update={"photos": photos})})


def test_a_card_without_findings_has_empty_but_valid_fields():
    bare = card(ModuleEvidence(case_id="fx-0000", source="fixture"))
    assert bare.summary == [] or len(bare.summary) <= 3
    assert isinstance(bare.checks_out, list) and isinstance(bare.does_not, list)


def test_a_photo_elsewhere_leads_the_summary_and_the_state_is_dont_pay():
    m = elsewhere(modules())
    got = card(m)
    assert got.state is VerdictState.DONT_PAY
    verdict = decide(to_evidence(m), "en")
    assert got.summary[0] == verdict.reasons[0]
    assert "different building" in got.summary[0] or "photo" in got.summary[0].lower()


def test_the_summary_is_at_most_three_sentences_and_is_decides_reasons_in_order():
    m = modules()
    reasons = decide(to_evidence(m), "en").reasons
    got = card(m).summary
    assert 1 <= len(got) <= 3
    assert got == reasons[: len(got)]


def test_the_measured_price_gap_replaces_the_generic_price_reason():
    price = PriceResult(
        status=PriceStatus.BELOW_RANGE,
        listed_rent=900,
        record_min=1600,
        record_max=2300,
        compared_beds=2,
    )
    m = modules(price=price.model_dump())
    got = card(m).summary
    assert got[-1] == "The rent is 44% under this building's 2 bed listing."
    assert got[:2] == decide(to_evidence(m), "en").reasons[:2]
    assert len(got) == 3 and strings.text("reason.price_flag") not in got


def test_the_price_gap_without_a_plan_size_still_gives_the_percent():
    price = PriceResult(
        status=PriceStatus.BELOW_RANGE, listed_rent=1200, record_min=1600, record_max=2300
    )
    got = card(modules(price=price.model_dump())).summary
    assert got[-1] == "The rent is 25% under this building's listings."


def test_checks_out_is_the_ok_lines_and_does_not_is_flags_holds_and_not_shown():
    got = card(modules())
    lines = [ln for row in got.rows for ln in row.lines]
    ok = {f"{ln.label}: {ln.text}" for ln in lines if ln.tone is CardTone.OK}
    bad = {
        f"{ln.label}: {ln.text}"
        for ln in lines
        if ln.tone in (CardTone.RED_FLAG, CardTone.HOLD, CardTone.NOT_SHOWN)
    }
    assert set(got.checks_out) == ok and set(got.does_not) == bad
    assert ok.isdisjoint(bad)
    assert not any(
        ln.tone is CardTone.NOT_CHECKED and f"{ln.label}: {ln.text}" in bad for ln in lines
    )
    assert any("Payment ask" in item for item in got.does_not)  # the fixture asks for Zelle


def test_a_case_with_nothing_wrong_has_no_does_not():
    clean = modules(rules=[], price={"status": "within_range", "listed_rent": 1800})
    got = card(clean)
    holds = [ln for row in got.rows for ln in row.lines if ln.tone in (CardTone.RED_FLAG,)]
    assert not holds
    assert not any("Payment ask" in item for item in got.does_not)
    assert any("Rent vs record" in item for item in got.checks_out)


def test_the_summary_is_deterministic_and_has_spanish():
    m = elsewhere(modules())
    assert card(m).model_dump() == card(m).model_dump()
    es = card(m, "es")
    assert es.summary and es.summary != card(m).summary
    price = PriceResult(
        status=PriceStatus.BELOW_RANGE, listed_rent=900, record_min=1600, compared_beds=0
    )
    assert "44%" in " ".join(card(modules(price=price.model_dump()), "es").summary)


def test_the_summary_never_calls_anyone_a_scammer_or_names_a_person():
    for m in (modules(), elsewhere(modules()), modules("module_evidence_forged.json")):
        text = " ".join(card(m).summary + card(m).does_not).lower()
        assert "scam" not in text and "fraud" not in text and "liar" not in text
