"""Conductor ruling on #10 (Sat 19:0x): an honest ad reads HOLD, the same verdict word a scam
gets. When a HOLD has nothing against it, only the presence step left, the card says so in its
headline. The state stays HOLD and `decide` is untouched: this is words only.

Every name here is made up.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from snapback.card import strings
from snapback.contracts import CardTone, ModuleEvidence, PresenceStatus, VerdictState
from snapback.verdict import build_card, decide, headline_text, to_evidence

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")
MATCHES = {
    "status": "matches_record",
    "manager_on_record": "Fixture Living LLC",
    "office_phone_match": "yes",
}
ZELLE = [
    {
        "rule_id": "payment.zelle_before_viewing",
        "category": "payment_method",
        "evidence_span": "send the deposit by Zelle",
        "red_flag": True,
    }
]
CLEAN_EN = (
    "Everything we checked matches the record. "
    "One step left before you pay: ask them to prove they're inside."
)
CLEAN_ES = (
    "Todo lo que revisamos coincide con el registro. "
    "Falta un paso antes de pagar: pídales que demuestren que están dentro."
)


def evidence(**sections) -> ModuleEvidence:
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    return ModuleEvidence.model_validate(raw | sections)


def honest(**sections) -> ModuleEvidence:
    """Photos placed, the office's own phone, no risky ask, and nobody asked to prove they are
    inside yet: the honest ad as it first comes back."""
    return evidence(
        **({"authority": MATCHES, "rules": [], "price": None, "challenge": None} | sections)
    )


def card(modules: ModuleEvidence, lang: str = "en"):
    return build_card(modules, checked_at=CHECKED_AT, lang=lang)


def test_an_honest_ad_is_still_hold_and_says_what_is_left():
    made = card(honest())
    assert made.state is VerdictState.HOLD
    assert made.headline == CLEAN_EN
    assert headline_text(made) == CLEAN_EN
    assert card(honest(), "es").headline == CLEAN_ES
    # Nothing on such a card is a flag or a warning.
    tones = {line.tone for row in made.rows for line in row.lines}
    assert not tones & {CardTone.RED_FLAG, CardTone.HOLD}


def test_such_a_case_is_one_presence_proof_away_from_passing():
    held = to_evidence(honest())
    assert decide(held).state is VerdictState.HOLD
    assert strings.text("reason.presence_missing") in decide(held).reasons
    proven = held.model_copy(update={"presence": PresenceStatus.PROVEN})
    assert decide(proven).state is VerdictState.VERIFIED


def test_a_reply_that_is_still_awaited_counts_as_the_step_left():
    waiting = to_evidence(honest()).model_copy(update={"presence": PresenceStatus.WAITING})
    assert decide(waiting).state is VerdictState.HOLD


@pytest.mark.parametrize(
    "sections",
    [
        {"rules": ZELLE},  # a red flag
        {"authority": MATCHES | {"office_phone_match": "no"}},  # a contact that is not confirmed
        {"authority": {"status": "unknown", "manager_on_record": None}},  # nobody on record matched
    ],
)
def test_a_hold_with_anything_against_it_keeps_the_plain_headline(sections):
    made = card(honest(**sections))
    assert made.state is VerdictState.HOLD
    assert made.headline is None
    assert headline_text(made) == strings.text("state.hold")


def test_other_states_never_get_it():
    verified = card(evidence(authority=MATCHES, rules=[], price=None))  # presence proven
    assert verified.state is VerdictState.VERIFIED and verified.headline is None
    assert headline_text(verified) == strings.text("state.verified")
    dont_pay = json.loads((CONTRACTS / "module_evidence_forged.json").read_text())
    forged = card(ModuleEvidence.model_validate(dont_pay))
    assert forged.state is VerdictState.DONT_PAY and forged.headline is None


def test_it_is_words_only_the_verdict_and_the_evidence_do_not_know_about_it():
    modules = honest()
    assert decide(to_evidence(modules)).state is VerdictState.HOLD
    dumped = card(modules).model_dump(mode="json")
    assert dumped["state"] == "hold" and dumped["headline"] == CLEAN_EN


def test_the_headline_follows_the_card_s_language_and_the_wording_rules():
    for lang, text in (("en", CLEAN_EN), ("es", CLEAN_ES)):
        assert strings.text("state.hold_clean", lang) == text
        assert "—" not in text
        assert "for rent" not in text.lower()


def test_the_png_and_the_mcp_server_read_the_same_headline():
    from snapback.card import render

    made = card(honest())
    assert render.headline(made) == CLEAN_EN
    assert render.headline(card(honest(rules=ZELLE))) == strings.text("state.hold")
