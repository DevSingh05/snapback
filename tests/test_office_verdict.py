"""Office confirmation, part 2: what it changes in the verdict, and what it never does."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from snapback.card import strings
from snapback.contracts import (
    CardRowKind,
    CardTone,
    LocateStatus,
    ModuleEvidence,
    PresenceStatus,
    VerdictState,
)
from snapback.verdict import REASON_ORDER, build_card, decide, to_evidence

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")
DOMAIN = "fixtureliving.example"

CONFIRMED_EN = (
    "Confirmed through fixtureliving.example, the website CoStar has on record for this office."
)
CONFIRMED_ES = (
    "Confirmado a través de fixtureliving.example, el sitio web que CoStar tiene registrado "
    "para esta oficina."
)
REASON_EN = (
    "Confirmed through fixtureliving.example, the website CoStar has on record for this "
    "office; the photos are of this home."
)


def evidence(**sections) -> ModuleEvidence:
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    return ModuleEvidence.model_validate(raw | sections)


def base(**sections) -> ModuleEvidence:
    """Photos placed, presence proven, the name on record matches, the phone is NOT the
    office's (so without the domain this is a HOLD), nothing flagged."""
    matches = {"status": "matches_record", "manager_on_record": "Fixture Living LLC"}
    sections.setdefault("authority", matches)
    return evidence(rules=[], price=None, **sections)


def with_phone() -> ModuleEvidence:
    matches = {"status": "matches_record", "manager_on_record": "Fixture Living LLC"}
    return base(authority={**matches, "office_phone_match": "yes"})


def state(modules: ModuleEvidence) -> VerdictState:
    return decide(to_evidence(modules)).state


def test_the_fixture_base_is_a_hold_without_the_domain():
    assert state(base()) is VerdictState.HOLD
    assert state(with_phone()) is VerdictState.VERIFIED  # the old path is untouched


def test_the_full_combination_is_verified_with_the_reason_that_says_what_was_confirmed():
    modules = base(office_confirmed_domain=DOMAIN)
    verdict = decide(to_evidence(modules))
    assert verdict.state is VerdictState.VERIFIED
    assert REASON_EN in verdict.reasons
    es = decide(to_evidence(modules, "es"), "es")
    assert es.state is VerdictState.VERIFIED
    assert "fixtureliving.example" in " ".join(es.reasons)


def test_without_the_domain_confirmation_it_is_not_verified():
    assert state(base(office_confirmed_domain=None)) is VerdictState.HOLD


def test_without_photos_placed_in_the_claimed_home_it_is_not_verified():
    # Mutate: a domain confirmation alone never verifies.
    modules = base(office_confirmed_domain=DOMAIN)
    photos = [
        photo.model_copy(update={"status": LocateStatus.NOT_LOCATED})
        for photo in modules.locate.photos
    ]
    unplaced = modules.model_copy(
        update={"locate": modules.locate.model_copy(update={"photos": photos})}
    )
    assert state(unplaced) is not VerdictState.VERIFIED


def test_presence_not_proven_or_a_name_mismatch_is_not_verified_with_the_domain():
    clean = base(office_confirmed_domain=DOMAIN)
    waiting = ModuleEvidence.model_validate(
        json.loads(clean.model_dump_json()) | {"challenge": None}
    )
    assert to_evidence(waiting).presence is not PresenceStatus.PROVEN
    assert state(waiting) is not VerdictState.VERIFIED
    mismatch = base(
        office_confirmed_domain=DOMAIN,
        authority={"status": "mismatch", "manager_on_record": "Fixture Living LLC"},
    )
    assert state(mismatch) is VerdictState.HOLD


RED_RULE = {
    "rule_id": "payment.zelle_before_viewing",
    "category": "payment_method",
    "red_flag": True,
    "evidence_span": "send the deposit by Zelle",
}


@pytest.mark.parametrize(
    "extra",
    [
        {"rules": [RED_RULE]},
        {"for_sale": {"status": "active", "offices": []}},
        {"price": {"status": "below_range"}},
    ],
    ids=["red_flag_rule", "for_sale", "price_below_range"],
)
def test_any_other_hold_reason_beats_the_domain_confirmation(extra):
    clean = base(office_confirmed_domain=DOMAIN)
    assert state(clean) is VerdictState.VERIFIED
    flagged = ModuleEvidence.model_validate(json.loads(clean.model_dump_json()) | extra)
    assert state(flagged) is not VerdictState.VERIFIED


def test_a_phone_that_is_not_the_offices_still_holds_the_case_with_the_domain_confirmed():
    modules = base(
        office_confirmed_domain=DOMAIN,
        authority={
            "status": "matches_record",
            "manager_on_record": "Fixture Living LLC",
            "office_phone_match": "no",
        },
    )
    assert state(modules) is VerdictState.HOLD


def test_the_door_code_attacker_without_the_domain_confirmation_is_hold():
    # A self-tour scammer copies the public name, sends a fresh in-home photo (presence
    # proven) and the photos place in the home. He cannot read mail at the office's domain.
    attacker = base()
    assert to_evidence(attacker).presence is PresenceStatus.PROVEN
    assert decide(to_evidence(attacker)).state is VerdictState.HOLD


def test_forged_or_elsewhere_photos_are_still_dont_pay_with_the_domain_confirmed():
    forged = base(office_confirmed_domain=DOMAIN)
    photos = [
        photo.model_copy(update={"status": LocateStatus.LOCATED_ELSEWHERE})
        for photo in forged.locate.photos
    ]
    elsewhere = forged.model_copy(
        update={"locate": forged.locate.model_copy(update={"photos": photos})}
    )
    assert state(elsewhere) is VerdictState.DONT_PAY


def test_the_card_line_is_an_info_line_on_the_person_row_in_both_languages():
    modules = base(office_confirmed_domain=DOMAIN)
    for lang, expected in (("en", CONFIRMED_EN), ("es", CONFIRMED_ES)):
        card = build_card(modules, checked_at=CHECKED_AT, lang=lang)
        person = next(row for row in card.rows if row.kind is CardRowKind.PERSON)
        lines = [line for line in person.lines if line.text == expected]
        assert len(lines) == 1 and lines[0].tone is CardTone.OK


def test_no_line_and_no_reason_without_the_confirmation():
    card = build_card(base(), checked_at=CHECKED_AT)
    assert "Confirmed through" not in card.model_dump_json()
    assert not any("Confirmed through" in r for r in decide(to_evidence(base())).reasons)


def test_the_hold_card_with_the_confirmation_still_shows_the_info_line():
    # Confirmed, but another reason holds the case: the line stays, the state does not move.
    modules = base(
        office_confirmed_domain=DOMAIN,
        for_sale={"status": "active", "offices": []},
    )
    card = build_card(modules, checked_at=CHECKED_AT)
    assert card.state is not VerdictState.VERIFIED
    assert CONFIRMED_EN in card.model_dump_json()


def test_the_new_wording_has_both_languages_and_a_place_in_the_reason_order():
    for key in (
        "label.office",
        "contact.office_confirmed",
        "reason.office_confirmed",
        "office.call_yourself",
    ):
        assert strings.has(key, "en") and strings.has(key, "es"), key
    assert "reason.office_confirmed" in REASON_ORDER
    assert "{domain}" in strings.TABLES["en"]["reason.office_confirmed"]
    assert "{domain}" in strings.TABLES["es"]["reason.office_confirmed"]
    assert (
        "call the office on a number you look up yourself"
        in strings.text("office.call_yourself", "en").lower()
    )
    for banned in ("estafa", "seguro", "verificado"):
        assert (
            banned not in strings.text("reason.office_confirmed", "es", domain="x.example").lower()
        )


def test_no_phone_digits_or_names_in_the_new_lines():
    import re

    modules = base(office_confirmed_domain=DOMAIN)
    card = build_card(modules, checked_at=CHECKED_AT)
    person = next(row for row in card.rows if row.kind is CardRowKind.PERSON)
    new = " ".join(line.text for line in person.lines if "Confirmed through" in line.text)
    assert not re.search(r"\d{3}", new)


DECLINED_EN = (
    "Not confirmed. Someone at fixtureliving.example, the website CoStar has on record for "
    "this office, said the office does not recognise this ad."
)


def test_not_ours_holds_the_case_with_a_reason_and_never_verifies_or_accuses():
    verified = base(office_confirmed_domain=DOMAIN)
    assert state(verified) is VerdictState.VERIFIED
    declined = base(office_declined_domain=DOMAIN)
    verdict = decide(to_evidence(declined))
    assert verdict.state is VerdictState.HOLD  # never DONT_PAY: an answer, not proof
    assert any("did not recognise this ad" in r for r in verdict.reasons)
    # Even a phone that matches the office cannot lift a "not ours".
    phone = base(
        office_declined_domain=DOMAIN,
        authority={
            "status": "matches_record",
            "manager_on_record": "Fixture Living LLC",
            "office_phone_match": "yes",
        },
    )
    assert state(phone) is VerdictState.HOLD


def test_the_declined_card_line_is_not_confirmed_in_both_languages():
    modules = base(office_declined_domain=DOMAIN)
    card = build_card(modules, checked_at=CHECKED_AT)
    person = next(row for row in card.rows if row.kind is CardRowKind.PERSON)
    lines = [line for line in person.lines if "does not recognise" in line.text]
    assert [line.text for line in lines] == [DECLINED_EN] and lines[0].tone is CardTone.NOT_SHOWN
    es = build_card(modules, checked_at=CHECKED_AT, lang="es")
    assert "no reconoce este anuncio" in es.model_dump_json()
    assert "Confirmed through" not in card.model_dump_json()


def test_the_declined_reason_has_a_place_and_both_languages():
    assert "reason.office_declined" in REASON_ORDER
    for key in ("contact.office_declined", "reason.office_declined"):
        assert strings.has(key, "en") and strings.has(key, "es")
