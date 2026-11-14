"""Vidyut, Sat 07:35 and 09:05: an active Texas licence, checked by number, sponsored by the
brokerage on record, turns the contact "Not confirmed" line into an information line, but ONLY
when presence is also PROVEN (a fresh in-home photo with the code), which defeats a copied
licence. The headline never reads VERIFIED on a licence, even with everything else passing
(Vidyut revoked that at Sat 09:30: a self-tour scammer with a door code can copy the public
name and number, name the brokerage and send a fresh in-home photo).

The owner line and the for-sale hold are untouched. The default
fixture here has presence PROVEN and photos located; tests drop one condition at a time.
Synthetic names only; the lookup result holds no person and no number.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from snapback.card import strings
from snapback.contracts import (
    CardRowKind,
    CardTone,
    ModuleEvidence,
    VerdictState,
)
from snapback.verdict import build_card, decide, to_evidence

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")
OFFICE = {"status": "matches_record", "manager_on_record": "Fixture Realty LLC"}
DIFFERS = OFFICE | {"office_phone_match": "no"}
LICENSED = {
    "status": "licensed",
    "claimed_role": "agent",
    "sponsor_broker": "Fixture Realty Group",
    "number_from": "ad",
}
INFO_EN = (
    "Not the office's number. The license number given is active, under the name in the ad, "
    "and sponsored by Fixture Realty LLC, the brokerage on record. A license number can be "
    "copied from a real listing, so call Fixture Realty LLC on a number you look up yourself "
    "to confirm this agent."
)
INFO_ES = (
    "No es el número de la oficina. El número de licencia que se dio está activo, a nombre "
    "de quien firma el anuncio, y patrocinado por Fixture Realty LLC, la agencia que figura "
    "en el registro. Un número de licencia se puede copiar de un anuncio real, así que llame "
    "a Fixture Realty LLC a un número que usted mismo busque para confirmar a este agente."
)
NOT_CONFIRMED_START = "Not confirmed. This number is not the leasing office's"


def evidence(**sections) -> ModuleEvidence:
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    return ModuleEvidence.model_validate(raw | {"rules": [], "price": None} | sections)


NO_PRESENCE = {"challenge": None}  # no fresh in-home photo asked for or received
OWNER_MISMATCH = {
    "status": "matches_record",
    "kind": "company",
    "company": "Fixture Holdings LLC",
    "poster_says_owner": True,
    "poster_matches": "no",
}
SALE = {"status": "active", "offices": ["Fixture Realty LLC"]}


def waiting() -> dict:
    """The default challenge with the reply not in yet."""
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    return {"challenge": raw["challenge"] | {"presence": "waiting"}}


def person(modules: ModuleEvidence, lang: str = "en") -> dict[str, tuple[CardTone, str]]:
    card = build_card(modules, checked_at=CHECKED_AT, lang=lang)
    row = next(row for row in card.rows if row.kind is CardRowKind.PERSON)
    return {item.label: (item.tone, item.text) for item in row.lines}


def contact(modules: ModuleEvidence, lang: str = "en") -> tuple[CardTone, str]:
    return person(modules, lang)["Contact on record" if lang == "en" else _es_label()]


def _es_label() -> str:
    return strings.text("label.contact", "es")


def reasons(modules: ModuleEvidence) -> list[str]:
    return decide(to_evidence(modules)).reasons


def test_the_rule_fires_and_the_line_is_information_in_both_languages():
    modules = evidence(authority=DIFFERS, license=LICENSED)
    assert contact(modules) == (CardTone.NOT_SHOWN, INFO_EN)
    assert contact(modules, "es") == (CardTone.NOT_SHOWN, INFO_ES)


def test_before_the_rule_the_same_case_reads_not_confirmed():
    modules = evidence(authority=DIFFERS)
    assert contact(modules)[1].startswith(NOT_CONFIRMED_START)


def test_the_phone_mismatch_reason_is_dropped_and_only_that_one():
    # an owner mismatch keeps the case on HOLD so the reasons can be compared
    with_licence = reasons(evidence(authority=DIFFERS, license=LICENSED, owner=OWNER_MISMATCH))
    without = reasons(evidence(authority=DIFFERS, owner=OWNER_MISMATCH))
    gone = strings.text("reason.phone_flag")
    assert gone in without and gone not in with_licence
    assert set(without) - set(with_licence) == {gone}
    # the other holding reasons are the same; the generic "not shown to be the office" says
    # what is still true
    assert set(with_licence) - set(without) == {strings.text("reason.phone_not_confirmed")}
    # a contact reason always remains, once, in the unmatched case too
    unmatched = reasons(
        evidence(authority={**DIFFERS, "status": "unknown"}, license=LICENSED, owner=OWNER_MISMATCH)
    )
    assert unmatched.count(strings.text("reason.phone_not_confirmed")) == 1


def test_a_licence_without_presence_never_verifies_and_never_softens():
    for extra in (NO_PRESENCE, waiting()):
        modules = evidence(authority=DIFFERS, license=LICENSED, **extra)
        assert decide(to_evidence(modules)).state is VerdictState.HOLD
        assert to_evidence(modules).phone_confirmed is False
        assert contact(modules)[1].startswith(NOT_CONFIRMED_START)
        assert strings.text("reason.phone_flag") in reasons(modules)


@pytest.mark.parametrize(
    "change",
    [
        {"status": "not_checked"},  # not LICENSED, even with a sponsor on the result
        {"status": "not_found"},
        {"status": "not_found", "number_from": "renter"},  # the renter's number is no licence
        {"status": "not_checked", "number_from": "renter"},  # holder is not the claimed name
        {"number_from": None},  # a name-only lookup
        {"sponsor_broker": "Other Holdings Inc"},  # sponsor is not the brokerage on record
        {"sponsor_broker": None},  # sponsor is not a company
    ],
)
def test_each_condition_is_needed(change):
    modules = evidence(authority=DIFFERS, license=LICENSED | change)
    assert contact(modules)[1].startswith(NOT_CONFIRMED_START)
    assert strings.text("reason.phone_flag") in reasons(modules)


def test_a_number_the_renter_typed_counts_like_the_ad_s():
    modules = evidence(authority=DIFFERS, license=LICENSED | {"number_from": "renter"})
    assert contact(modules) == (CardTone.NOT_SHOWN, INFO_EN)


def test_no_office_named_on_record_means_nothing_to_match():
    modules = evidence(
        authority={"status": "unknown", "office_phone_match": "no"}, license=LICENSED
    )
    assert contact(modules)[1].startswith("Not confirmed.")
    assert strings.text("reason.phone_flag") in reasons(modules)


def test_the_listing_brokerage_of_an_active_for_sale_home_is_on_record():
    sale = {"status": "active", "offices": ["Fixture Realty LLC"]}
    modules = evidence(
        authority={"status": "unknown", "office_phone_match": "no"},
        license=LICENSED,
        for_sale=sale,
    )
    assert contact(modules) == (CardTone.NOT_SHOWN, INFO_EN)
    # a for-sale home that is not active gives no brokerage on record
    gone = evidence(
        authority={"status": "unknown", "office_phone_match": "no"},
        license=LICENSED,
        for_sale=sale | {"status": "none"},
    )
    assert contact(gone)[1].startswith("Not confirmed.")


def test_the_for_sale_hold_is_unchanged():
    sale = {"status": "active", "offices": ["Fixture Realty LLC"]}
    base = evidence(authority=DIFFERS, for_sale=sale)
    cleared = evidence(authority=DIFFERS, for_sale=sale, license=LICENSED)
    assert strings.text("reason.for_sale") in reasons(cleared)
    assert decide(to_evidence(cleared)).state is decide(to_evidence(base)).state
    base_rows, cleared_rows = _rows(base), _rows(cleared)
    for label, line in base_rows.items():
        if label not in ("Contact on record", "Licence", "License"):
            assert cleared_rows[label] == line


def _rows(modules: ModuleEvidence) -> dict:
    card = build_card(modules, checked_at=CHECKED_AT)
    return {item.label: (item.tone, item.text) for row in card.rows for item in row.lines}


def test_the_owner_line_is_identical():
    owner = {
        "status": "matches_record",
        "kind": "company",
        "company": "Fixture Holdings LLC",
        "poster_says_owner": True,
        "poster_matches": "no",
    }
    base = person(evidence(authority=DIFFERS, owner=owner))
    cleared = person(evidence(authority=DIFFERS, owner=owner, license=LICENSED))
    for label, line in base.items():
        if label not in ("Contact on record", "Licence", "License"):
            assert cleared[label] == line
    assert any("Owner of record" in line[1] for line in cleared.values())


def test_a_phone_that_really_matches_is_unchanged():
    modules = evidence(authority=OFFICE | {"office_phone_match": "yes"}, license=LICENSED)
    assert contact(modules)[0] is CardTone.OK


def test_a_renter_number_that_is_not_found_adds_no_second_contact_line():
    modules = evidence(
        authority=DIFFERS, license=LICENSED | {"status": "not_found", "number_from": "renter"}
    )
    card = build_card(modules, checked_at=CHECKED_AT)
    lines = [item for row in card.rows for item in row.lines if item.label == "Contact on record"]
    assert len(lines) == 1 and lines[0].text.startswith(NOT_CONFIRMED_START)


COPIED = {
    "status": "unknown",
    "manager_on_record": "Fixture Realty LLC",
    "office_phone_match": "no",
}


def test_a_copied_licence_without_presence_holds_and_says_call_the_office():
    # a scammer pastes a real agent's name and number; copied photos place in the claimed home
    for extra in (NO_PRESENCE, waiting()):
        modules = evidence(authority=COPIED, license=LICENSED, **extra)
        verdict = decide(to_evidence(modules))
        assert verdict.state is VerdictState.HOLD
        assert strings.text("reason.phone_flag") in verdict.reasons
        assert "check it with the office" in contact(modules)[1]
        assert "llame" not in contact(modules, "es")[1]
    unnamed = evidence(
        authority={"status": "unknown", "office_phone_match": "no"}, license=LICENSED, **NO_PRESENCE
    )
    assert "Call the office on record yourself" in contact(unnamed)[1]


def test_a_forged_reply_does_not_count_as_presence():
    copy = [{"photo_id": "r1", "hit": "same_case_listing", "method": "phash"}]
    modules = evidence(authority=COPIED, license=LICENSED, memory=copy)
    assert contact(modules)[1].startswith(NOT_CONFIRMED_START)
    assert decide(to_evidence(modules)).state is VerdictState.DONT_PAY


# --- the headline: all four parts, and nothing else holding the case ---------------------------


def state(modules: ModuleEvidence) -> VerdictState:
    return decide(to_evidence(modules)).state


def test_all_four_parts_stay_hold_with_the_softened_contact_line():
    modules = evidence(authority=DIFFERS, license=LICENSED)
    assert to_evidence(modules).phone_confirmed is False
    assert decide(to_evidence(modules)).state is VerdictState.HOLD
    assert contact(modules) == (CardTone.NOT_SHOWN, INFO_EN)
    assert "call Fixture Realty LLC on a number you look up yourself" in contact(modules)[1]


def test_a_self_tour_attacker_never_reads_verified():
    # a door code gives a fresh in-home photo; name, number and brokerage are all public
    for authority in (DIFFERS, COPIED):
        for extra in ({}, {"owner": None}):
            modules = evidence(authority=authority, license=LICENSED, **extra)
            assert to_evidence(modules).presence.value == "proven"
            assert state(modules) is VerdictState.HOLD


def test_the_for_sale_brokerage_counts_as_on_record_for_the_headline():
    modules = evidence(
        authority={"status": "unknown", "office_phone_match": "no"},
        license=LICENSED,
        for_sale=SALE | {"offices": ["Fixture Realty LLC"]},
    )
    # an ACTIVE for-sale home still holds: the for-sale reason is a red flag of its own
    assert state(modules) is VerdictState.HOLD


@pytest.mark.parametrize(
    "drop",
    [
        pytest.param({"license": LICENSED | {"status": "not_checked"}}, id="licence-not-active"),
        pytest.param({"license": LICENSED | {"number_from": None}}, id="name-only"),
        pytest.param(
            {"license": LICENSED | {"sponsor_broker": "Other Holdings Inc"}}, id="sponsor"
        ),
        pytest.param({"license": LICENSED | {"sponsor_broker": None}}, id="no-sponsor"),
        pytest.param(NO_PRESENCE, id="no-presence"),
    ],
)
def test_dropping_any_one_part_loses_the_softened_line(drop):
    assert contact(evidence(authority=DIFFERS, license=LICENSED))[0] is CardTone.NOT_SHOWN
    softened = contact(evidence(authority=DIFFERS, **({"license": LICENSED} | drop)))
    assert softened[1].startswith(NOT_CONFIRMED_START)


def test_photos_not_placed_in_the_claimed_home_is_not_verified():
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())["locate"]
    for photo in raw["photos"]:
        photo["status"] = "not_located"
    modules = evidence(authority=DIFFERS, license=LICENSED, locate=raw)
    assert state(modules) is VerdictState.UNVERIFIED


def test_presence_proven_with_a_name_only_licence_is_not_verified():
    modules = evidence(authority=DIFFERS, license=LICENSED | {"number_from": None})
    assert state(modules) is VerdictState.HOLD


@pytest.mark.parametrize(
    "other",
    [
        pytest.param({"owner": OWNER_MISMATCH}, id="owner-mismatch"),
        pytest.param({"for_sale": SALE}, id="for-sale-active"),
        pytest.param({"price": {"status": "below_range"}}, id="price-red-flag"),
        pytest.param({"authority": DIFFERS | {"link_domain": "lookalike"}}, id="lookalike-link"),
        pytest.param(
            {"license": LICENSED | {"number_from": "renter"}, "owner": OWNER_MISMATCH},
            id="renter-number-owner",
        ),
    ],
)
def test_any_other_hold_reason_keeps_the_case_on_hold(other):
    modules = evidence(**({"authority": DIFFERS, "license": LICENSED} | other))
    assert state(modules) is VerdictState.HOLD


def test_a_renter_typed_number_that_is_not_active_still_holds():
    # the licence fails (not LICENSED), so no headline; a typo is only ever "not confirmed"
    modules = evidence(
        authority=DIFFERS, license=LICENSED | {"status": "not_found", "number_from": "renter"}
    )
    assert state(modules) is VerdictState.HOLD


def test_a_payment_rule_red_flag_keeps_the_case_on_hold():
    hit = {
        "rule_id": "fx-pay",
        "category": "payment_method",
        "red_flag": True,
    }
    flagged = evidence(authority=DIFFERS, license=LICENSED, rules=[hit])
    assert state(flagged) is VerdictState.HOLD


def test_a_photo_elsewhere_or_a_forgery_is_still_dont_pay():
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())["locate"]
    raw["photos"][0]["status"] = "located_elsewhere"
    assert state(evidence(authority=DIFFERS, license=LICENSED, locate=raw)) is VerdictState.DONT_PAY
