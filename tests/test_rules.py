"""Code-owned rules over the renter's own text, and the rent-versus-record check."""

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from snapback.agent.rules import RULES, apply_rules, check_price
from snapback.card import strings
from snapback.contracts import (
    CardRowKind,
    ModuleEvidence,
    PriceStatus,
    PropertyRecord,
    RuleCategory,
    VerdictState,
)
from snapback.verdict import build_card, decide, to_evidence

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "fixtures" / "rules" / "cases.json").read_text())
ZELLE_FOR_KEYS = "Send the deposit by Zelle and I will mail the keys."


def fired(text: str, category: str | None = None) -> list[str]:
    return [hit.rule_id for hit in apply_rules(text) if category in (None, hit.category)]


def record(**rents) -> PropertyRecord:
    data = json.loads((ROOT / "fixtures" / "contracts" / "property_record.json").read_text())
    return PropertyRecord.model_validate(data | rents)


# --- the cases named in the task -----------------------------------------------------------


def test_zelle_before_viewing_fires():
    hit = next(
        h for h in apply_rules(ZELLE_FOR_KEYS) if h.rule_id == "payment.zelle_before_viewing"
    )
    assert hit.category is RuleCategory.PAYMENT_METHOD
    assert hit.red_flag is True
    assert hit.evidence_span == ZELLE_FOR_KEYS


def test_zelle_after_signed_lease_does_not_fire():
    text = (
        "After you tour the unit and we both sign the lease, you can pay the first month by Zelle."
    )
    assert "payment.zelle_before_viewing" not in fired(text)


def test_refund_the_difference_fires():
    text = "Send $2,400 now; it is more than the deposit but I will refund the difference."
    assert "payment.overpayment_refund" in fired(text)


def test_ssn_before_viewing_fires():
    assert "data.ssn_before_viewing" in fired("Before I can show it, text me your SSN.")


def test_payment_link_from_poster_fires_link_rule():
    hits = apply_rules("Pay the deposit here to lock it in: https://pay.example.com/hold/123")
    link = next(h for h in hits if h.rule_id == "link.payment_link")
    assert link.category is RuleCategory.LINK
    assert link.red_flag is True


def test_below_range_is_not_dont_pay_alone():
    price = check_price(900, record(rent_min=1600, rent_median=1850, rent_max=2300))
    assert price.status is PriceStatus.BELOW_RANGE
    hold = json.loads((ROOT / "fixtures" / "contracts" / "module_evidence_hold.json").read_text())
    evidence = ModuleEvidence.model_validate(
        hold | {"price": price.model_dump(mode="json"), "rules": []}
    )
    assert decide(to_evidence(evidence)).state is VerdictState.HOLD


# --- the fixture table: what fires and what does not ---------------------------------------


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_fixture_fires_exactly_the_expected_rules_in_its_category(case):
    assert sorted(fired(case["text"], case["category"])) == sorted(case["expect"])


@pytest.mark.parametrize("category", [category.value for category in RuleCategory])
def test_every_category_has_two_firing_and_two_quiet_fixtures(category):
    cases = [case for case in CASES if case["category"] == category]
    assert sum(bool(case["expect"]) for case in cases) >= 2
    assert sum(not case["expect"] for case in cases) >= 2


def test_every_rule_is_exercised_by_a_fixture():
    expected = {rule_id for case in CASES for rule_id in case["expect"]}
    assert {rule.rule_id for rule in RULES} <= expected


def test_fixture_ids_are_marked_as_fixtures():
    assert all(case["id"].startswith("fx-") for case in CASES)


# --- behaviour that keeps the rules honest -------------------------------------------------


def test_paying_first_to_get_a_viewing_is_not_excused_by_the_word_viewing():
    assert "payment.zelle_before_viewing" in fired(
        "Once you send the deposit by Zelle I will arrange a viewing."
    )


def test_looking_at_photos_is_not_a_viewing():
    assert "payment.zelle_before_viewing" in fired(
        "After viewing the photos, send the deposit by Zelle to hold it."
    )


def test_a_warning_against_a_payment_method_is_not_an_ask():
    assert fired("We never ask for payment by Zelle, wire transfer or gift card.") == []


def test_telling_the_renter_not_to_pay_someone_else_is_still_an_ask():
    text = "Do not pay the front office. Zelle the deposit to me instead."
    assert "payment.zelle_before_viewing" in fired(text)


def test_gift_cards_and_crypto_fire_even_after_a_tour():
    assert "payment.gift_card" in fired(
        "After your tour you can pay the first month in gift cards."
    )
    assert "payment.crypto" in fired("Once the lease is signed, send the deposit in Bitcoin.")


def test_a_rule_fires_once_however_often_it_matches():
    text = "Zelle me today. Zelle is the only way. Did you Zelle it yet?"
    assert Counter(fired(text))["payment.zelle_before_viewing"] == 1


def test_evidence_span_is_the_renters_own_sentence():
    text = "Lovely two bedroom near the park. Wire the deposit to hold it. Thanks!"
    hit = next(h for h in apply_rules(text) if h.rule_id == "payment.wire_before_viewing")
    assert hit.evidence_span == "Wire the deposit to hold it."
    assert hit.evidence_span in text


def test_nothing_to_read_means_no_hits():
    assert apply_rules("") == []
    assert apply_rules("   \n\n ") == []


def test_matching_ignores_case():
    assert "payment.zelle_before_viewing" in fired("SEND IT BY ZELLE NOW")


# --- review fixes: excuses that leaked, odd characters, honest sentences -------------------


@pytest.mark.parametrize(
    "text",
    [
        "I don't take checks, Zelle the deposit today please.",
        "We never ask for a deposit before you tour, but send the $500 deposit by Zelle today.",
        "Don't pay by check, pay by Zelle.",
        "Don't send cash, only Zelle.",
        "I don't take checks so Zelle me the deposit.",
    ],
)
def test_refusing_one_thing_does_not_excuse_asking_for_another(text):
    assert "payment.zelle_before_viewing" in fired(text)


@pytest.mark.parametrize(
    "text",
    [
        "Zelle the deposit today, after signing you get the keys.",
        "After signing you get the keys, Zelle the deposit today.",
        "Zelle me the deposit now and after the tour I will hand over the lease.",
    ],
)
def test_paying_now_is_not_excused_by_something_else_happening_after_signing(text):
    assert "payment.zelle_before_viewing" in fired(text)


@pytest.mark.parametrize(
    "text",
    [
        "After signing the lease you can Zelle the deposit.",
        "You can pay the deposit by Zelle after your tour.",
        "Pay by Zelle after you sign the lease at our office.",
        "The deposit can be paid by Zelle, after your tour.",
        "Once you have toured the unit, you may send the deposit by Zelle.",
    ],
)
def test_paying_after_a_viewing_or_a_signed_lease_is_still_excused(text):
    assert "payment.zelle_before_viewing" not in fired(text)


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        ("I\u2019m out of the country so I can\u2019t show the apartment.", "pressure.cannot_show"),
        ("Send a copy of your driver\u2019s license.", "data.id_before_viewing"),
        ("Send the deposit by \uff3a\uff45\uff4c\uff4c\uff45.", "payment.zelle_before_viewing"),
        ("Send the deposit by Zel\u200ble.", "payment.zelle_before_viewing"),
        ("Send the deposit by Zel\u00adle.", "payment.zelle_before_viewing"),
    ],
    ids=[
        "curly apostrophes",
        "curly apostrophe in licence",
        "fullwidth",
        "zero width",
        "soft hyphen",
    ],
)
def test_odd_characters_do_not_hide_an_ask(text, rule_id):
    assert rule_id in fired(text)


@pytest.mark.parametrize(
    "text",
    [
        "Tenants can pay rent by Venmo or Zelle.",
        "Do not pay anyone by Zelle before a showing.",
        "Apply at https://apply.example.com, application fee $40 paid to the management office.",
        "Never pay by Zelle, wire transfer or gift card before you have seen the unit.",
        "Rent is paid monthly by check, Zelle or the resident portal.",
        "We accept Zelle, Venmo and checks for monthly rent.",
    ],
)
def test_honest_sentences_raise_no_red_flag(text):
    # A red flag holds a case below the top state, so an honest listing must not raise one.
    assert [hit.rule_id for hit in apply_rules(text) if hit.red_flag] == []


def test_rent_terms_do_not_excuse_an_ask_for_a_deposit_now():
    assert "payment.zelle_before_viewing" in fired("We accept Zelle for the deposit today.")
    assert "payment.zelle_before_viewing" in fired("Tenants pay by Zelle, so Zelle me the deposit.")


# --- the table itself ----------------------------------------------------------------------


def test_rule_ids_are_unique_and_shaped_like_category_dot_name():
    ids = [rule.rule_id for rule in RULES]
    assert len(ids) == len(set(ids))
    for rule in RULES:
        assert re.fullmatch(r"[a-z]+\.[a-z0-9_]+", rule.rule_id), rule.rule_id


@pytest.mark.parametrize("rule", [r for r in RULES if r.red_flag], ids=lambda r: r.rule_id)
def test_every_red_flag_rule_has_its_own_card_string(rule):
    # A1's string table keys on the rule id. The wording must carry the tone in words.
    text = strings.text(f"rule.{rule.rule_id}")
    assert text.endswith("Red flag.")


def test_hits_carry_the_rule_table_values():
    by_id = {rule.rule_id: rule for rule in RULES}
    for hit in apply_rules(ZELLE_FOR_KEYS + " Many people are interested, act fast."):
        assert hit.category is by_id[hit.rule_id].category
        assert hit.red_flag is by_id[hit.rule_id].red_flag


def test_a_fired_rule_reaches_the_card_in_its_own_words():
    hold = json.loads((ROOT / "fixtures" / "contracts" / "module_evidence_hold.json").read_text())
    hits = apply_rules("Please wire the deposit today. I am overseas and cannot show it.")
    evidence = ModuleEvidence.model_validate(
        hold | {"rules": [hit.model_dump(mode="json") for hit in hits]}
    )
    card = build_card(evidence, checked_at=datetime.fromisoformat("2026-11-13T21:42:00-05:00"))
    price = next(row for row in card.rows if row.kind is CardRowKind.PRICE)
    shown = {(line.label, line.text) for line in price.lines}
    assert ("Payment ask", strings.text("rule.payment.wire_before_viewing")) in shown
    assert ("Pressure", strings.text("rule.pressure.cannot_show")) in shown


# --- rent versus the record ----------------------------------------------------------------


def test_rent_well_inside_the_record_is_within_range():
    price = check_price(1900, record(rent_min=1600, rent_median=1850, rent_max=2300))
    assert price.status is PriceStatus.WITHIN_RANGE
    assert (price.listed_rent, price.record_min, price.record_median, price.record_max) == (
        1900,
        1600,
        1850,
        2300,
    )
    assert price.n_floor_plans == 2


def test_a_modest_discount_is_still_within_range():
    # Concessions happen. Only rent far under the lowest rent on record is flagged.
    price = check_price(1450, record(rent_min=1600, rent_median=1850, rent_max=2300))
    assert price.status is PriceStatus.WITHIN_RANGE


def test_rent_above_the_record_is_not_flagged():
    price = check_price(4000, record(rent_min=1600, rent_median=1850, rent_max=2300))
    assert price.status is PriceStatus.WITHIN_RANGE


def test_median_is_used_when_the_record_has_no_minimum():
    assert check_price(900, record(rent_median=1850)).status is PriceStatus.BELOW_RANGE
    assert check_price(1700, record(rent_median=1850)).status is PriceStatus.WITHIN_RANGE


@pytest.mark.parametrize(
    ("listed", "property_record"),
    [(1800, None), (1800, record()), (None, record(rent_min=1600, rent_median=1850))],
    ids=["no record", "record without rent", "no rent in the listing"],
)
def test_price_is_not_checked_without_both_numbers(listed, property_record):
    price = check_price(listed, property_record)
    assert price.status is PriceStatus.NOT_CHECKED
    assert price.listed_rent == listed
