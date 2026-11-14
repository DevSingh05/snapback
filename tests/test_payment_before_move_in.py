"""Card gap (conductor, Sat 10:03): an ad that asks for money before move-in.

The price row must not say "Matches" about such an ad. When the owner of record publishes how
it takes money, or is not the poster, the payment line is a warning and the owner's rule sits
beside it. That changes a tone and nothing else: no verdict moves. And a home that is a house
is called a home on the placement line, not a building.

Every name here is made up.
"""

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from snapback.agent.intake.fields import ContactClaims
from snapback.agent.rules.apply import apply_rules
from snapback.agent.rules.owner import check_owner
from snapback.agent.rules.published import PublishedRuleRow
from snapback.agent.rules.table import RULES
from snapback.card import strings
from snapback.contracts import (
    CardLine,
    CardRowKind,
    CardTone,
    ModuleEvidence,
    OwnerKind,
    OwnerResult,
    RuleCategory,
)
from snapback.verdict import build_card, decide, to_evidence

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")
RULE_ID = "fee.money_before_move_in"
MOVE_IN = [
    {
        "rule_id": RULE_ID,
        "category": "fee_ask",
        "evidence_span": "first month and deposit are due before move-in",
        "red_flag": False,
    }
]
ZELLE = [
    {
        "rule_id": "payment.zelle_before_viewing",
        "category": "payment_method",
        "evidence_span": "send the deposit by Zelle",
        "red_flag": True,
    }
]
MATCHES = {
    "status": "matches_record",
    "manager_on_record": "Fixture Living LLC",
    "office_phone_match": "yes",
}
COMPANY = OwnerResult(kind=OwnerKind.COMPANY, company="Fixture Homes LLC", company_known=True)
FX_RULES = (
    PublishedRuleRow(
        company="Fixture Homes",
        rule="we only take applications on fixturehomes.example",
        source_url="https://fixturehomes.example/leasing-fraud",
        checked_on=date(2026, 11, 14),
    ),
)
SAYS_OWNER = ContactClaims(says_owner=True)
SAYS_NOTHING = ContactClaims()


def evidence(**sections) -> ModuleEvidence:
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    return ModuleEvidence.model_validate(raw | sections)


def passing(owner: OwnerResult | None = None, **sections) -> ModuleEvidence:
    """A case that is VERIFIED unless something in it holds it."""
    base = {"authority": MATCHES, "rules": [], "price": None}
    if owner is not None:
        base["owner"] = owner.model_dump(mode="json")
    return evidence(**(base | sections))


def price_lines(modules: ModuleEvidence, lang: str = "en") -> list[CardLine]:
    card = build_card(modules, checked_at=CHECKED_AT, lang=lang)
    return next(row for row in card.rows if row.kind is CardRowKind.PRICE).lines


def payment_line(modules: ModuleEvidence, lang: str = "en") -> CardLine:
    label = strings.text("label.payment_ask", lang)
    found = [line for line in price_lines(modules, lang) if line.label == label]
    assert len(found) == 1, found
    return found[0]


def all_lines(modules: ModuleEvidence, lang: str = "en") -> list[CardLine]:
    card = build_card(modules, checked_at=CHECKED_AT, lang=lang)
    return [line for row in card.rows for line in row.lines]


# --- the rule: is the ad asking for rent or a deposit before move-in? ----------------------


@pytest.mark.parametrize(
    "text",
    [
        "First month's rent and a $1,200 deposit are due before move-in.",
        "The deposit must be paid before you move in.",
        "Security deposit and first month required prior to move in.",
        "You pay the deposit before moving in.",
        "We need first month and deposit before you move in.",
        "Before move-in we need the deposit.",
        "You will need first month and deposit to move in.",
        "To move in you need $2,200.",
        "Total move-in cost is $2,400.",
        "$2,200 is due before move in",
        "FIRST MONTH AND DEPOSIT DUE BEFORE MOVE IN",
        # A deposit is paid before move-in by its nature, so naming one is the ask. This is
        # the sentence in the replay that showed the gap.
        "Rent is $1,100 a month and the deposit is $1,100.",
        "$500 deposit. Pets ok.",
        "$2,500 security deposit",
        "Deposit required.",
        "The deposit is one month of rent.",
        "First and last month due at signing.",
        "First month's rent up front.",
    ],
)
def test_an_ask_for_money_before_move_in_is_heard(text):
    hits = [hit for hit in apply_rules(text) if hit.rule_id == RULE_ID]
    assert len(hits) == 1, text
    assert hits[0].category is RuleCategory.FEE_ASK
    # Honest listings say this too. It is never a red flag, so it can never hold a case.
    assert hits[0].red_flag is False


@pytest.mark.parametrize(
    "text",
    [
        "Rent is $1,900 and you can tour before moving in.",
        "Move-in ready. Rent is $1,900 a month.",
        "Move-in special: first month free.",
        "Available for move-in before December.",
        "Rent is due on the first of each month.",
        "No deposit is needed before move-in.",
        "We never ask for a deposit before move-in.",
        "Never pay a deposit before move-in to anyone but the office.",
        "The deposit is refundable at move-out.",
        "Schedule a tour before you move in.",
        "No deposit is needed.",
        "$0 deposit for qualified renters.",
        "$45 application fee, no deposit.",
        "A deposit is not required.",
        "Rent is $1,900 a month.",
        "Rent is $1,900 a month, water included.",
        # The writer refusing the thing is not the writer asking for it.
        "We do not require first month's rent to be paid before move-in.",
        "We never ask for a deposit of $500.",
        "",
    ],
)
def test_other_sentences_about_moving_in_are_not_an_ask(text):
    assert RULE_ID not in [hit.rule_id for hit in apply_rules(text)], text


def test_the_rule_is_in_the_table_and_is_not_a_red_flag():
    rule = next(rule for rule in RULES if rule.rule_id == RULE_ID)
    assert rule.red_flag is False and rule.category is RuleCategory.FEE_ASK


# --- the card: never "Matches" about such an ad ---------------------------------------------


def test_with_no_money_ask_the_payment_line_still_reads_matches():
    line = payment_line(passing())
    assert (line.tone, line.text) == (CardTone.OK, strings.text("payment.none", "en"))


def test_an_ask_before_move_in_never_reads_matches():
    line = payment_line(passing(rules=MOVE_IN))
    assert line.tone is not CardTone.OK
    # With nothing known about the owner it is "Not confirmed": the ask is in the ad, and
    # who the money would go to is not something we checked.
    assert (line.tone, line.text) == (
        CardTone.NOT_SHOWN,
        "The ad asks for rent or a deposit before move-in. "
        "We could not confirm who it would go to.",
    )
    assert "No risky payment ask" not in " ".join(
        item.text for item in price_lines(passing(rules=MOVE_IN))
    )
    # No owner data: nothing is quoted, because there is nothing to quote.
    assert "Owner's rule" not in [item.label for item in all_lines(passing(rules=MOVE_IN))]


def test_an_owner_with_a_published_rule_makes_it_a_warning_with_the_rule_beside_it():
    # The poster claims nothing about owning it. The owner's rule alone is enough.
    found = check_owner(SAYS_NOTHING, COMPANY, rules=FX_RULES)
    modules = passing(found, rules=MOVE_IN)
    lines = price_lines(modules)
    labels = [item.label for item in lines]
    place = labels.index("Owner's rule")
    assert labels[place - 1] == "Payment ask"  # right after the payment ask it speaks to
    assert (lines[place - 1].tone, lines[place - 1].text) == (
        CardTone.HOLD,
        "The ad asks for rent or a deposit before move-in. "
        "We could not confirm who it would go to.",
    )
    assert (lines[place].tone, lines[place].text) == (
        CardTone.HOLD,
        'Fixture Homes, the owner of record, says: "we only take applications on '
        'fixturehomes.example" (fixturehomes.example/leasing-fraud, read 2026-11-14).',
    )
    # The rule is quoted once on the card: the owner line does not repeat it.
    quoted = [item for item in all_lines(modules) if "fixturehomes.example" in item.text]
    assert [item.label for item in quoted] == ["Owner's rule"]


def test_an_owner_who_is_not_the_poster_makes_it_a_warning_even_without_a_rule():
    found = check_owner(SAYS_OWNER, COMPANY, rules=())
    modules = passing(found, rules=MOVE_IN)
    line = payment_line(modules)
    assert (line.tone, line.text) == (
        CardTone.HOLD,
        "The ad asks for rent or a deposit before move-in, "
        "and the owner of record is not the poster.",
    )
    assert "Owner's rule" not in [item.label for item in all_lines(modules)]


def test_an_owner_who_is_not_the_poster_and_has_a_rule_gets_both():
    found = check_owner(SAYS_OWNER, COMPANY, rules=FX_RULES)
    lines = price_lines(passing(found, rules=MOVE_IN))
    labels = [item.label for item in lines]
    place = labels.index("Owner's rule")
    assert labels[place - 1] == "Payment ask"
    assert lines[place - 1].tone is CardTone.HOLD
    assert lines[place - 1].text.endswith("and the owner of record is not the poster.")
    assert lines[place].tone is CardTone.HOLD


def test_an_owner_who_matches_and_has_no_rule_is_not_a_warning_and_not_matches():
    # Naming the owner is a supporting line only (anyone can read the owner roll), so the
    # ask is still not "Matches". With no rule and no mismatch there is nothing to warn of.
    named = ContactClaims(says_owner=True, company="Fixture Homes LLC")
    found = check_owner(named, COMPANY, rules=())
    line = payment_line(passing(found, rules=MOVE_IN))
    assert line.tone is CardTone.NOT_SHOWN


def test_a_red_flag_payment_ask_keeps_its_own_line_and_the_move_in_line_is_not_added():
    found = check_owner(SAYS_OWNER, COMPANY, rules=FX_RULES)
    modules = passing(found, rules=ZELLE + MOVE_IN)
    lines = price_lines(modules)
    payment = [item for item in lines if item.label == "Payment ask"]
    assert [(item.tone, item.text) for item in payment] == [
        (CardTone.RED_FLAG, strings.text("rule.payment.zelle_before_viewing", "en"))
    ]
    # The owner's rule is beside it once, as before.
    assert [item.label for item in lines].count("Owner's rule") == 1


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_lines_are_written_in_the_card_s_language(lang):
    bare = payment_line(passing(rules=MOVE_IN), lang)
    assert bare.text == strings.text("payment.before_move_in", lang)
    found = check_owner(SAYS_OWNER, COMPANY, rules=())
    not_owner = payment_line(passing(found, rules=MOVE_IN), lang)
    assert not_owner.text == strings.text("payment.before_move_in_not_owner", lang)
    for line in (bare, not_owner):
        assert "—" not in line.text and "{" not in line.text
    if lang == "es":
        assert bare.text == (
            "El anuncio pide renta o depósito antes de la mudanza. "
            "No pudimos confirmar a quién iría."
        )


# --- tone only: no verdict moves -----------------------------------------------------------


@pytest.mark.parametrize(
    "owner, claims, rules",
    [
        (None, SAYS_NOTHING, ()),
        (COMPANY, SAYS_NOTHING, FX_RULES),
        (COMPANY, SAYS_OWNER, FX_RULES),
        (COMPANY, SAYS_OWNER, ()),
        (OwnerResult(kind=OwnerKind.PERSON), SAYS_OWNER, ()),
        (OwnerResult(kind=OwnerKind.COMPANY), SAYS_NOTHING, ()),
    ],
)
@pytest.mark.parametrize("flagged", [[], ZELLE])
def test_the_ask_changes_no_verdict_and_no_reason(owner, claims, rules, flagged):
    found = check_owner(claims, owner, rules=rules) if owner is not None else None
    without = decide(to_evidence(passing(found, rules=flagged)))
    with_ask = decide(to_evidence(passing(found, rules=flagged + MOVE_IN)))
    assert with_ask.state is without.state
    assert with_ask.reasons == without.reasons
    assert to_evidence(passing(found, rules=flagged + MOVE_IN)) == to_evidence(
        passing(found, rules=flagged)
    )


def test_a_verified_case_stays_verified_with_the_ask_on_the_card():
    quiet = build_card(passing(), checked_at=CHECKED_AT)
    asked = build_card(passing(rules=MOVE_IN), checked_at=CHECKED_AT)
    assert asked.state is quiet.state
    assert (asked.not_checked, asked.footer) == (quiet.not_checked, quiet.footer)


def card_and_verdict(case_id: str):
    from snapback.agent.demo import run_demo_case

    verdict, card = run_demo_case(case_id)
    lines = [(line.label, line.tone, line.text) for row in card.rows for line in row.lines]
    return (verdict.state, verdict.reasons, card.state), lines


def test_no_staged_case_or_replay_changes_its_verdict(monkeypatch):
    # Conductor, on #8: demo cases a, b and c and both replays give the same states. Each is
    # run with the rule in the table and with it taken out.
    from snapback.agent.demo import demo_case_ids
    from snapback.agent.rules import apply

    cases = demo_case_ids()
    assert {"a", "b", "c"} <= set(cases) and sum(c.startswith("replay-") for c in cases) >= 2
    with_rule = {case: card_and_verdict(case) for case in cases}
    monkeypatch.setattr(apply, "RULES", tuple(r for r in RULES if r.rule_id != RULE_ID))
    without = {case: card_and_verdict(case) for case in cases}
    for case in cases:
        assert with_rule[case][0] == without[case][0], case
    # And the rule is live in these runs: the replay whose ad names a deposit reads
    # differently with it, on the payment line and the owner's rule beside it.
    changed = [case for case in cases if with_rule[case][1] != without[case][1]]
    assert changed == ["replay-owner-not-poster-door-code"]


def test_a_staged_house_is_called_a_home_and_an_apartment_a_building():
    _, replay = card_and_verdict("replay-owner-not-poster-door-code")
    assert ("Real", CardTone.OK, "Taken in this home (3 of 3 photos).") in replay
    _, apartment = card_and_verdict("a")
    assert any(text.startswith("Taken in this building") for _, _, text in apartment)


# --- a house is a home, not a building ------------------------------------------------------


def located(property_type: str | None, floor_plan: str | None = None) -> ModuleEvidence:
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    raw["locate"]["chosen"]["floor_plan"] = floor_plan
    if property_type is not None:
        raw["property_type"] = property_type
    return ModuleEvidence.model_validate(raw)


def real_line(modules: ModuleEvidence, lang: str = "en") -> CardLine:
    card = build_card(modules, checked_at=CHECKED_AT, lang=lang)
    place = next(row for row in card.rows if row.kind is CardRowKind.PLACE)
    return place.lines[0]


def test_photos_placed_in_a_house_are_taken_in_this_home():
    line = real_line(located("house"))
    assert (line.tone, line.text) == (CardTone.OK, "Taken in this home (3 of 3 photos).")
    assert real_line(located("house"), "es").text == "Tomadas en esta vivienda (3 de 3 fotos)."


@pytest.mark.parametrize("property_type", ["house", "single family", "single_family", "House"])
def test_every_way_a_record_names_a_house_is_a_home(property_type):
    assert real_line(located(property_type)).text == "Taken in this home (3 of 3 photos)."


@pytest.mark.parametrize("property_type", [None, "multifamily", "", "townhouse", "house boat"])
def test_any_other_home_keeps_the_building_wording(property_type):
    assert real_line(located(property_type)).text == "Taken in this building (3 of 3 photos)."
    assert real_line(located(property_type, "2 bed / 2 bath")).text == (
        "Taken in this building, in the 2 bed / 2 bath floor plan (3 of 3 photos)."
    )


def test_the_house_wording_changes_no_verdict():
    assert decide(to_evidence(located("house"))) == decide(to_evidence(located(None)))


# --- the kind of home reaches the card from a case that has a record ------------------------


def joined_case(record):
    from snapback.agent import CaseSession, FixtureModules, PolicyChooser, Trace, run_case
    from snapback.agent.intake import read_listing
    from snapback.agent.join import JoinedModules
    from snapback.agent.rules.contact import FIXTURE_PHONE_SALT
    from snapback.contracts import DataSource

    modules = JoinedModules(
        stand_in=FixtureModules(),
        listing=read_listing("3 bed house for rent, $1,900 a month."),
        record=record,
        for_sale=None,
        salt=FIXTURE_PHONE_SALT,
        record_source=DataSource.FIXTURE if record is not None else None,
    )
    case = CaseSession("fx-HOME", modules, Trace("fx-HOME", DataSource.FIXTURE))
    run_case(case, PolicyChooser(), lambda draft: "send")
    return modules, case


@pytest.mark.parametrize("kind", ["house", "multifamily", None])
def test_the_record_s_kind_of_home_reaches_the_evidence(kind):
    from snapback.contracts import DataSource, PropertyRecord

    record = PropertyRecord(property_id="fx-home-1", source=DataSource.FIXTURE, property_type=kind)
    modules, case = joined_case(record)
    assert modules.property_type("fx-HOME") == kind
    assert case.evidence.property_type == kind


def test_a_case_with_no_record_has_no_kind_of_home():
    modules, case = joined_case(None)
    assert modules.property_type("fx-HOME") is None
    assert case.evidence.property_type is None
