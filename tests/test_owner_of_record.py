"""A19 (#125): the owner of record, and the rules big owners publish.

Every name here is made up. The one real company is in the published-rule table itself, and
the tests about that row check its shape, not a person or an address.
"""

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.agent.intake import read_listing
from snapback.agent.intake.fields import ContactClaims, extract_contacts
from snapback.agent.rules.owner import check_owner, company_match, published_rule
from snapback.agent.rules.published import PUBLISHED_RULES, PublishedRuleRow
from snapback.api.main import create_app
from snapback.card import strings
from snapback.contracts import (
    CardRowKind,
    CardTone,
    ModuleEvidence,
    OwnerKind,
    OwnerMatch,
    OwnerResult,
    VerdictState,
)
from snapback.settings import Settings
from snapback.verdict import REASON_ORDER, build_card, decide, to_evidence

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")
MATCHES = {
    "status": "matches_record",
    "manager_on_record": "Fixture Living LLC",
    "office_phone_match": "yes",
}
# A company we know (a row in the published-rule table, or an office on record in the kit):
# lane D sends its name only then (conductor ruling, round 5 on #160).
COMPANY = OwnerResult(kind=OwnerKind.COMPANY, company="Fixture Homes LLC", company_known=True)
# Any other company: lane D sends no name, and the card says "a company owner".
UNNAMED = OwnerResult(kind=OwnerKind.COMPANY)
PERSON = OwnerResult(kind=OwnerKind.PERSON)
FX_RULES = (
    PublishedRuleRow(
        company="Fixture Homes",
        rule="we only take applications on fixturehomes.example",
        source_url="https://fixturehomes.example/leasing-fraud",
        checked_on=date(2026, 11, 14),
    ),
)
SAYS_OWNER = ContactClaims(says_owner=True)


def evidence(**sections) -> ModuleEvidence:
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    return ModuleEvidence.model_validate(raw | sections)


def passing(owner: OwnerResult | None = None, **sections) -> ModuleEvidence:
    """A case that is VERIFIED unless something in it holds it."""
    base = {"authority": MATCHES, "rules": [], "price": None}
    if owner is not None:
        base["owner"] = owner.model_dump(mode="json")
    return evidence(**(base | sections))


def state(modules: ModuleEvidence) -> VerdictState:
    return decide(to_evidence(modules)).state


def person_row(modules: ModuleEvidence, lang: str = "en") -> dict[str, tuple[CardTone, str]]:
    card = build_card(modules, checked_at=CHECKED_AT, lang=lang)
    row = next(row for row in card.rows if row.kind is CardRowKind.PERSON)
    return {item.label: (item.tone, item.text) for item in row.lines}


def owner_line(modules: ModuleEvidence, lang: str = "en") -> tuple[CardTone, str]:
    label = strings.text("label.owner", lang)
    return person_row(modules, lang)[label]


# --- a company owns it, and the poster says they are the owner -----------------------------


def test_a_company_owner_and_a_poster_who_says_they_own_it_is_held_and_not_confirmed():
    found = check_owner(SAYS_OWNER, COMPANY, rules=())
    # "I am the owner", and the owner is a company the poster does not name: that is a no.
    assert (found.poster_says_owner, found.poster_matches) == (True, OwnerMatch.NO)
    modules = passing(found)
    assert to_evidence(modules).owner_flag is True

    verdict = decide(to_evidence(modules))
    assert verdict.state is VerdictState.HOLD
    assert strings.text("reason.owner_not_poster") in verdict.reasons
    assert owner_line(modules) == (
        CardTone.NOT_SHOWN,
        "Not confirmed. Owner of record: Fixture Homes LLC, not the poster.",
    )
    # The same listing without the claim passes, so the claim is what holds it.
    assert state(passing(check_owner(ContactClaims(), COMPANY, rules=()))) is VerdictState.VERIFIED


def test_it_is_never_a_red_flag_by_itself():
    # Ruling, Sat 01:20: a name that does not match is never a red flag on its own.
    modules = passing(check_owner(SAYS_OWNER, COMPANY, rules=()))
    card = build_card(modules, checked_at=CHECKED_AT)
    lines = [item for row in card.rows for item in row.lines]
    assert CardTone.RED_FLAG not in [item.tone for item in lines]
    assert not any("Red flag" in item.text for item in lines)


def test_naming_the_company_that_owns_it_is_a_supporting_line_and_nothing_more():
    claims = ContactClaims(company="Fixture Homes", says_owner=True)
    found = check_owner(claims, COMPANY, rules=())
    assert found.poster_matches is OwnerMatch.YES
    assert to_evidence(passing(found)).owner_flag is False
    assert owner_line(passing(found)) == (
        CardTone.OK,
        "The company they named is the owner of record: Fixture Homes LLC.",
    )
    # Anyone can type a company's public name, so a match never lifts "Allowed to rent it".
    unknown = {"status": "unknown"}
    without = passing(authority=unknown)
    assert state(passing(found, authority=unknown)) is state(without) is VerdictState.HOLD
    assert (
        person_row(passing(found, authority=unknown))["Allowed to rent it"]
        == person_row(without)["Allowed to rent it"]
    )


def test_naming_another_company_while_saying_owner_is_held_too():
    claims = ContactClaims(company="Other Fixture Rentals", says_owner=True)
    found = check_owner(claims, COMPANY, rules=())
    assert found.poster_matches is OwnerMatch.NO
    assert state(passing(found)) is VerdictState.HOLD
    assert owner_line(passing(found))[0] is CardTone.NOT_SHOWN


def test_a_near_miss_spelling_of_the_company_is_not_checked_and_never_held():
    # Conductor, Sat 03:00: never flag on a near-miss spelling; return not checked.
    for said in ("Fixure Homes", "Fixture Home", "Fixture Homs LLC", "Fixture-Homes, Inc."):
        claims = ContactClaims(company=said, says_owner=True)
        found = check_owner(claims, COMPANY, rules=())
        assert found.poster_matches is not OwnerMatch.NO, said
        assert to_evidence(passing(found)).owner_flag is False, said
        assert state(passing(found)) is VerdictState.VERIFIED, said
    # "LLC", "Inc" and punctuation are ignored, and a shorter form that starts the same matches.
    assert company_match("Fixture Homes, L.L.C.", "FIXTURE HOMES LLC") is OwnerMatch.YES
    assert company_match("Fixture", "Fixture Homes LLC") is OwnerMatch.YES
    assert company_match("FixtureHomes", "Fixture Homes LLC") is OwnerMatch.YES
    assert company_match("Fixture Homes", "FixtureHomes, Inc.") is OwnerMatch.YES
    assert company_match("Fixure Homes", "Fixture Homes LLC") is OwnerMatch.NOT_CHECKED
    assert company_match("Other Fixture Rentals", "Fixture Homes LLC") is OwnerMatch.NO
    assert company_match(None, "Fixture Homes LLC") is OwnerMatch.NOT_CHECKED


def test_a_company_owner_is_named_for_a_poster_who_claims_nothing():
    # An agent or a manager posting a company's home: the card says who owns it, and holds
    # nothing on that account.
    found = check_owner(ContactClaims(), COMPANY, rules=())
    assert found.poster_matches is OwnerMatch.NOT_CHECKED
    assert owner_line(passing(found)) == (
        CardTone.NOT_SHOWN,
        "Not confirmed. Owner of record: Fixture Homes LLC.",
    )
    assert state(passing(found)) is VerdictState.VERIFIED


# --- a person owns it ----------------------------------------------------------------------


def test_a_person_owner_shows_yes_or_no_and_never_a_name():
    assert set(OwnerResult.model_fields) == {
        "kind",
        "company",
        "company_known",  # a yes or no about the company, never a name
        "poster_matches",
        "poster_says_owner",
        "published_rule",
    }
    yes = check_owner(
        SAYS_OWNER, PERSON.model_copy(update={"poster_matches": OwnerMatch.YES}), rules=()
    )
    assert owner_line(passing(yes)) == (
        CardTone.OK,
        "The owner of record is a private owner, and the name given matches.",
    )
    assert state(passing(yes)) is VerdictState.VERIFIED
    # A match never verifies: the owner roll is public, so anyone can type the owner's name.
    unknown = {"status": "unknown"}
    assert state(passing(yes, authority=unknown)) is VerdictState.HOLD

    no = check_owner(
        SAYS_OWNER, PERSON.model_copy(update={"poster_matches": OwnerMatch.NO}), rules=()
    )
    assert owner_line(passing(no)) == (
        CardTone.NOT_SHOWN,
        "Not confirmed. The owner of record is a private owner, and the name given doesn't "
        "match. Owners can rent through family or a trust; check with the owner of record or "
        "the county records yourself.",
    )


def test_a_company_field_on_a_person_owner_is_never_shown():
    # Lane D sends no name for a person. If one ever arrived in `company`, it stays off.
    odd = OwnerResult(kind=OwnerKind.PERSON, company="Fx Person", poster_matches=OwnerMatch.NO)
    found = check_owner(SAYS_OWNER, odd, rules=())
    assert found.company is None
    said = build_card(passing(found), checked_at=CHECKED_AT).model_dump_json()
    assert "Fx Person" not in said


@pytest.mark.parametrize(
    "unnamed",
    [
        UNNAMED,
        OwnerResult(kind=OwnerKind.COMPANY, company=""),
        OwnerResult(kind=OwnerKind.COMPANY, company="   ", company_known=True),
        # a name that is not known is never shown, even if a producer sends one
        OwnerResult(kind=OwnerKind.COMPANY, company="Fxhidden Holdings LLC"),
    ],
)
def test_an_unknown_company_is_a_company_owner_with_no_name_and_still_holds(unnamed):
    found = check_owner(SAYS_OWNER, unnamed, rules=FX_RULES)
    # "I am the owner", and a company owns it: a no, so the HOLD still works
    assert (found.poster_matches, found.company, found.published_rule) == (
        OwnerMatch.NO,
        None,
        None,
    )
    modules = passing(found)
    verdict = decide(to_evidence(modules))
    assert verdict.state is VerdictState.HOLD
    assert strings.text("reason.owner_not_poster") in verdict.reasons
    assert owner_line(modules) == (
        CardTone.NOT_SHOWN,
        "Not confirmed. Owner of record: a company owner, not the poster.",
    )
    assert owner_line(modules, "es") == (
        CardTone.NOT_SHOWN,
        "Sin confirmar. Propietario registrado: una empresa, no quien publica.",
    )
    # without the claim: the same line without "not the poster", and nothing holds the case
    quiet = passing(check_owner(ContactClaims(), unnamed, rules=FX_RULES))
    assert owner_line(quiet) == (
        CardTone.NOT_SHOWN,
        "Not confirmed. Owner of record: a company owner.",
    )
    assert state(quiet) is VerdictState.VERIFIED
    for lang in ("en", "es"):
        said = build_card(modules, checked_at=CHECKED_AT, lang=lang).model_dump_json()
        assert "Fxhidden" not in said and "Fixture Homes" not in said


def test_the_card_never_prints_a_company_name_that_is_not_known():
    # the card's own gate, apart from check_owner: a name a producer sends unknown is not shown
    sent = OwnerResult(kind=OwnerKind.COMPANY, company="Fxhidden Holdings LLC")
    for lang in ("en", "es"):
        card = build_card(passing(sent), checked_at=CHECKED_AT, lang=lang).model_dump_json()
        assert "Fxhidden" not in card
    assert owner_line(passing(sent)) == (
        CardTone.NOT_SHOWN,
        "Not confirmed. Owner of record: a company owner.",
    )


def test_an_unknown_company_the_poster_names_is_not_checked_and_does_not_hold():
    # the poster names a company, and we cannot say which company owns it: no comparison
    found = check_owner(ContactClaims(company="Fixture Homes", says_owner=True), UNNAMED)
    assert found.poster_matches is OwnerMatch.NOT_CHECKED
    assert state(passing(found)) is VerdictState.VERIFIED


def test_a_known_company_shows_its_name_and_still_holds_a_poster_who_says_they_own_it():
    found = check_owner(SAYS_OWNER, COMPANY, rules=FX_RULES)
    modules = passing(found)
    assert decide(to_evidence(modules)).state is VerdictState.HOLD
    tone, text = owner_line(modules)
    assert tone is CardTone.NOT_SHOWN
    assert text.startswith("Not confirmed. Owner of record: Fixture Homes LLC, not the poster.")
    assert "fixturehomes.example" in text  # its row in the published-rule table is quoted


def test_a_person_owner_loses_any_company_even_with_no_claims_to_compare():
    from snapback.agent.modules import FixtureModules

    odd = OwnerResult(kind=OwnerKind.PERSON, company="Fx Person")
    assert FixtureModules(owner=odd).owner("c").company is None


def test_a_person_owner_who_does_not_match_holds_a_poster_who_says_they_own_it():
    no = check_owner(
        SAYS_OWNER, PERSON.model_copy(update={"poster_matches": OwnerMatch.NO}), rules=()
    )
    assert to_evidence(passing(no)).owner_flag is True
    assert state(passing(no)) is VerdictState.HOLD
    # A poster who does not say they own it is not compared with the owner at all.
    agent = check_owner(
        ContactClaims(), PERSON.model_copy(update={"poster_matches": OwnerMatch.NO}), rules=()
    )
    assert to_evidence(passing(agent)).owner_flag is False
    assert state(passing(agent)) is VerdictState.VERIFIED
    assert owner_line(passing(agent)) == (
        CardTone.NOT_CHECKED,
        "Not checked (a private owner is on record, and the poster does not say they are the "
        "owner).",
    )


def test_a_person_owner_and_no_name_to_compare_is_not_checked():
    found = check_owner(SAYS_OWNER, PERSON, rules=())
    assert owner_line(passing(found)) == (
        CardTone.NOT_CHECKED,
        "Not checked (a private owner is on record, and the poster gave no name to compare).",
    )
    assert state(passing(found)) is VerdictState.VERIFIED


# --- no owner data -------------------------------------------------------------------------


def test_no_owner_data_is_not_checked():
    assert check_owner(SAYS_OWNER, None) is None
    modules = passing()
    assert strings.text("label.owner") not in person_row(modules)
    card = build_card(modules, checked_at=CHECKED_AT)
    assert strings.text("not_checked.ownership") in card.not_checked
    assert to_evidence(modules).owner_flag is False


def test_the_standing_not_checked_list_drops_ownership_only_when_it_was_compared():
    compared = passing(check_owner(SAYS_OWNER, COMPANY, rules=()))
    assert (
        strings.text("not_checked.ownership")
        not in build_card(compared, checked_at=CHECKED_AT).not_checked
    )
    not_compared = passing(check_owner(SAYS_OWNER, PERSON, rules=()))
    assert (
        strings.text("not_checked.ownership")
        in build_card(not_compared, checked_at=CHECKED_AT).not_checked
    )


# --- the published-rule table --------------------------------------------------------------


def test_an_owner_with_a_row_in_the_table_has_its_rule_quoted_with_source_and_date():
    found = check_owner(SAYS_OWNER, COMPANY, rules=FX_RULES)
    assert found.published_rule == FX_RULES[0].quoted()
    assert owner_line(passing(found)) == (
        CardTone.NOT_SHOWN,
        "Not confirmed. Owner of record: Fixture Homes LLC, not the poster. Fixture Homes "
        'says: "we only take applications on fixturehomes.example" '
        "(fixturehomes.example/leasing-fraud, read 2026-11-14).",
    )
    # The rule is in the evidence, so a recorded case is redrawn with the rule it had.
    again = ModuleEvidence.model_validate_json(passing(found).model_dump_json())
    assert owner_line(again) == owner_line(passing(found))


def test_an_owner_without_a_row_gets_no_rule_and_none_is_guessed():
    other = OwnerResult(
        kind=OwnerKind.COMPANY, company="Other Fixture Rentals LLC", company_known=True
    )
    found = check_owner(SAYS_OWNER, other, rules=FX_RULES)
    assert found.published_rule is None
    assert "says:" not in owner_line(passing(found))[1]
    assert published_rule("Homes of Fixture", FX_RULES) is None  # a shared word is not a match
    assert published_rule(None, FX_RULES) is None
    # A person is never looked up in a table of companies.
    assert check_owner(SAYS_OWNER, PERSON, rules=FX_RULES).published_rule is None


ZELLE = [
    {
        "rule_id": "payment.zelle_before_viewing",
        "category": "payment_method",
        "evidence_span": "send the deposit by Zelle",
        "red_flag": True,
    }
]


def test_when_the_ad_asks_for_money_the_owner_s_rule_is_quoted_beside_the_payment_line():
    # Conductor, Sat 03:00: the owner only takes money on its own site and the ad asks for
    # Zelle. The rule goes next to the payment line. The payment ask is the flag; this adds
    # none, and the case stays on HOLD.
    found = check_owner(SAYS_OWNER, COMPANY, rules=FX_RULES)
    modules = passing(found, rules=ZELLE)
    card = build_card(modules, checked_at=CHECKED_AT)
    price = next(row for row in card.rows if row.kind is CardRowKind.PRICE)
    labels = [item.label for item in price.lines]
    place = labels.index("Owner's rule")
    assert labels[place - 1] == "Payment ask"  # right after the payment ask it speaks to
    line = price.lines[place]
    assert (line.tone, line.text) == (
        CardTone.HOLD,
        'Fixture Homes, the owner of record, says: "we only take applications on '
        'fixturehomes.example" (fixturehomes.example/leasing-fraud, read 2026-11-14).',
    )
    # It is quoted once: the owner line does not repeat it.
    assert owner_line(modules)[1] == (
        "Not confirmed. Owner of record: Fixture Homes LLC, not the poster."
    )
    assert card.state is VerdictState.HOLD
    red = [item for row in card.rows for item in row.lines if item.tone is CardTone.RED_FLAG]
    assert [item.label for item in red] == ["Payment ask"]

    # With no payment ask there is no such line, and an owner without a rule never gets one.
    quiet = build_card(passing(found), checked_at=CHECKED_AT)
    assert "Owner's rule" not in [item.label for row in quiet.rows for item in row.lines]
    bare = passing(check_owner(SAYS_OWNER, COMPANY, rules=()), rules=ZELLE)
    assert "Owner's rule" not in [
        item.label for row in build_card(bare, checked_at=CHECKED_AT).rows for item in row.lines
    ]


def test_a_row_can_list_the_names_the_owner_roll_uses_for_the_company():
    from dataclasses import replace

    aliased = (replace(FX_RULES[0], also_known_as=("FX Borrower 2018 LP",)),)
    assert published_rule("FX BORROWER 2018 LP", aliased) == aliased[0]
    assert published_rule("FX BORROWER 2019 LP", aliased) is None


def test_every_row_in_the_real_table_is_a_short_quote_with_a_source_and_a_date():
    assert PUBLISHED_RULES, "the table ships with at least its first verified row"
    for row in PUBLISHED_RULES:
        assert row.company.strip() and row.rule.strip()
        assert len(row.rule.split()) <= 14, "a quote, not a passage"
        assert row.source_url.startswith("https://")
        assert date(2026, 11, 1) <= row.checked_on <= date.today()
        assert "—" not in row.rule
    first = PUBLISHED_RULES[0]
    assert first.company == "Invitation Homes"
    assert first.source_url.startswith("https://www.invitationhomes.com/")
    assert len({row.company.lower() for row in PUBLISHED_RULES}) == len(PUBLISHED_RULES)


# --- never proof, and where the reason sits ------------------------------------------------


def test_the_owner_rule_never_gives_dont_pay():
    flagged = check_owner(SAYS_OWNER, COMPANY, rules=FX_RULES).model_dump(mode="json")
    assert state(evidence(owner=flagged)) is VerdictState.HOLD
    nothing_placed = ModuleEvidence(case_id="fx-1", source="fixture", owner=flagged)
    verdict = decide(to_evidence(nothing_placed))
    assert verdict.state is VerdictState.UNVERIFIED
    assert strings.text("reason.owner_not_poster") in verdict.reasons


def test_the_owner_reason_sits_with_who_after_the_licence():
    order = list(REASON_ORDER)
    assert order.index("reason.license_not_found") < order.index("reason.owner_not_poster")
    assert order.index("reason.owner_not_poster") < order.index("reason.for_sale")


@pytest.mark.parametrize(
    ("claims", "owner"),
    [
        (SAYS_OWNER, COMPANY),
        (ContactClaims(), COMPANY),
        (ContactClaims(company="Fixture Homes", says_owner=True), COMPANY),
        (SAYS_OWNER, PERSON),
        (SAYS_OWNER, UNNAMED),
        (ContactClaims(), UNNAMED),
        (SAYS_OWNER, PERSON.model_copy(update={"poster_matches": OwnerMatch.YES})),
        (SAYS_OWNER, PERSON.model_copy(update={"poster_matches": OwnerMatch.NO})),
        (ContactClaims(), PERSON.model_copy(update={"poster_matches": OwnerMatch.NO})),
    ],
)
def test_every_owner_line_follows_the_wording_rules_in_both_languages(claims, owner):
    found = check_owner(claims, owner, rules=FX_RULES)
    for lang, unconfirmed, unchecked, banned in (
        ("en", "Not confirmed.", "Not checked", ("safe", "verified", "scam", "red flag")),
        ("es", "Sin confirmar.", "No comprobado", ("estafa", "seguro", "verificado", "alerta")),
    ):
        tone, text = owner_line(passing(found), lang)
        assert not any(word in text.lower() for word in banned), text
        assert "—" not in text
        assert tone is not CardTone.RED_FLAG
        assert text.startswith(unconfirmed) == (tone is CardTone.NOT_SHOWN), text
        assert text.startswith(unchecked) == (tone is CardTone.NOT_CHECKED), text
    assert set(strings.TABLES["es"]) == set(strings.TABLES["en"])


# --- what the poster says about owning it --------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Hi, I am the owner of this house.",
        "I'm the owner. 3 bed, $1,800.",
        "We are the owners and live nearby.",
        "For rent by owner, no agents please.",
        "FOR RENT BY OWNER",
        "I'm the homeowner, text me.",
        "This is my house, I am renting it out.",
        "Renting out my home while I work abroad.",
        "Owner here. Available now.",
        "I own this property.",
        "I'm the property owner.",
        "I am  the owner of this house.",
    ],
)
def test_a_poster_who_says_they_own_it_is_heard(text):
    assert extract_contacts(text).says_owner is True
    assert read_listing(text).contacts.says_owner is True


@pytest.mark.parametrize(
    "text",
    [
        "2 bed near the park, $1,400.",
        "I am not the owner, I manage it.",
        "I'm the owner's agent.",
        "Contact the owner at the office.",
        "The owner pays water and trash.",
        "I'm a pet owner and so are my neighbours.",
        "Managed by Fixture Living LLC.",
        "Feels like home. Make it your home today.",
        "Owner financing available on the sale.",
        "For Rent By Owner Realty",
        "Managed by Owner Direct Properties",
        "Sold by owner last year",
        "The owner here pays all utilities",
        "Pet owner here?",
        "I'm the leasing agent. The owner here is Invitation Homes",
        "We are the owners' agents",
        "homeowners association",
        "This is not my house",
        "like it's my home",
        "Sold by owner in 2019.",
        "It was for rent by owner last year.",
        "Previous owner here, new management now.",
        "FORMER OWNER HERE",
        "Former owner of the house",
    ],
)
def test_other_mentions_of_an_owner_are_not_a_claim(text):
    assert extract_contacts(text).says_owner is False


# --- the same claim in Spanish ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Soy el dueño. 3 recámaras, $1,800.",
        "Soy la dueña de la casa.",
        "Yo soy el propietario, llámeme.",
        "Somos los dueños y vivimos cerca.",
        "Somos los propietarios.",
        "Se renta por dueño, sin agentes.",
        "SE RENTA POR EL DUEÑO",
        "En renta por su propietario.",
        "Casa en renta, trato directo con el dueño.",
        "Dueño directo, sin intermediarios.",
        "Es mi casa y la estoy rentando.",
        "Rento mi propiedad mientras trabajo fuera.",
        "soy el dueno de la casa",  # typed without the ñ
        "Soy  el   dueño.",
    ],
)
def test_a_poster_who_says_in_spanish_that_they_own_it_is_heard(text):
    assert extract_contacts(text).says_owner is True
    assert read_listing(text).contacts.says_owner is True


@pytest.mark.parametrize(
    "text",
    [
        "2 recámaras cerca del parque, $1,400.",
        "No soy el dueño, soy el administrador.",
        "Soy el agente del dueño.",
        "Contacte al dueño en la oficina.",
        "El dueño paga el agua y la basura.",
        "Soy dueño de un perro y mis vecinos también.",
        "Soy dueña de dos gatos.",
        "Administrado por Fixture Living LLC.",
        "Se siente como mi casa. Hágala su casa hoy.",
        "Aquí estará como en mi casa.",
        "Esta no es mi casa.",
        "Vendido por el dueño el año pasado.",
        "Fue rentada por el dueño anterior.",
        "Asociación de propietarios incluida.",
        "El antiguo dueño dejó los muebles.",
        "Queda cerca de mi casa.",
        "Mi casa es su casa!",  # a welcome, in listings written in English too
        "Bienvenidos, mi casa es tu casa.",
    ],
)
def test_other_mentions_of_an_owner_in_spanish_are_not_a_claim(text):
    assert extract_contacts(text).says_owner is False


@pytest.mark.parametrize(
    "text",
    [
        # Something the owner pays for or does is not the poster saying they are the owner.
        "Water and trash paid by owner.",
        "Lawn care covered by the owner.",
        "Appliances provided by owner.",
        "Yard maintained by owner.",
        "Utilities paid for by owner.",
        "Agua y basura pagadas por el dueño.",
        "Luz pagada por el propietario.",
        "El agua está incluida por el dueño.",
        # Asking for the owner is not being the owner.
        "Pregunte por el dueño en la oficina.",
        "Pregunta por la dueña al llegar.",
        # Where the home is, told from the poster's own house.
        "A 5 minutos de mi casa.",
        "Se ve desde mi casa.",
        "Mi casa está a la vuelta.",
        # A pet, with any article.
        "Soy dueño del perro que ladra al lado.",
        "Soy dueña de la gata, es muy tranquila.",
        "Somos dueños de los perros.",
        # "MI" and "Mi Casa" in listings written in English.
        "Detroit, MI Townhouse, 3 bed.",
        "Ann Arbor MI house near campus.",
        "Mi Casa Apartments, 2 bed available.",
        "Welcome to Mi Casa Townhomes.",
        # One sentence for each excluded word, so removing any one of them fails a test.
        "Linens supplied by owner.",
        "Repairs handled by the owner.",
        "Internet included by owner.",
        "Upstairs unit occupied by owner.",
        "Se renta por el dueño anterior.",
        "En venta por el dueño pasado.",
        # A home between the verb and "por" does not turn something the owner paid for
        # into a claim.
        "Se renta casa pagada por el dueño.",
        "Se renta departamento con agua pagada por el dueño.",
    ],
)
def test_more_mentions_that_are_not_a_claim_in_either_language(text):
    assert extract_contacts(text).says_owner is False


@pytest.mark.parametrize(
    "text",
    [
        # The claims that were heard before are still heard.
        "For rent by owner, no agents please.",
        "For lease by owner.",
        "Listed by the owner.",
        "Se renta por dueño, sin agentes.",
        "Se alquila por su propietario.",
        "En renta por el dueño.",
        "Casa en venta por su dueña.",
        "Es mi casa y la estoy rentando.",
        "Rento mi propiedad mientras trabajo fuera.",
        "Alquilo mi casa por temporada.",
        # The most common headers put the home between the verb and "por" (review of #178).
        "Se renta casa por dueño",
        "Se vende casa por dueño",
        "Vendo casa por dueño",
        "Se renta departamento por el dueño",
        "Se alquila habitación por su dueño",
        "Se renta casa directo por dueño",
        "Renta de casa por su propietario",
        # "Se renta mi casa" is the home being offered as mine.
        "Se renta mi casa.",
        "Se alquila mi propiedad amueblada.",
        "Se vende mi casa.",
    ],
)
def test_the_claims_are_still_heard_after_the_exclusions(text):
    assert extract_contacts(text).says_owner is True


def test_a_spanish_claim_holds_a_case_the_same_way_an_english_one_does():
    # The rule does not care which language the claim was made in.
    for text in ("I am the owner.", "Soy el dueño."):
        found = check_owner(extract_contacts(text), COMPANY, rules=())
        assert (found.poster_says_owner, found.poster_matches) == (True, OwnerMatch.NO)
        assert to_evidence(passing(found)).owner_flag is True
        assert state(passing(found)) is VerdictState.HOLD


# --- through the join ----------------------------------------------------------------------


class Lookups:
    """Stand-in for lane D's adapters with an owner answer (D12 is not built yet)."""

    def __init__(self, owner: OwnerResult | None = None, fail: bool = False) -> None:
        self._owner, self._fail = owner, fail

    def record(self, property_id: str):
        return None

    def for_sale(self, listing_text: str):
        return None

    def owner(self, listing_text: str) -> OwnerResult | None:
        if self._fail:
            raise RuntimeError("the owner roll did not answer")
        return self._owner


def card_from(tmp_path, lookups, text="3 bed house. I am the owner. $1,900.") -> dict:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    client = TestClient(create_app(settings, lookups))
    made = client.post("/cases", data={"text": text}).json()
    if made["status"] == "waiting_for_approval":
        client.post(
            f"/cases/{made['case_id']}/challenge/approve",
            json={"decision": "send"},
            headers={"Authorization": f"Bearer {made['token']}"},
        )
    return client.get(f"/cases/{made['case_id']}/card").json()


def test_the_owner_answer_and_the_poster_s_claim_meet_on_the_card(tmp_path):
    card = card_from(tmp_path, Lookups(COMPANY))
    said = {line["label"]: line for row in card["rows"] for line in row["lines"]}
    assert said["Owner of record"]["tone"] == "not_shown"
    assert said["Owner of record"]["text"] == (
        "Not confirmed. Owner of record: Fixture Homes LLC, not the poster."
    )
    assert card["state"] == "hold"
    assert "ownership" not in card["not_checked"]


def test_an_owner_lookup_that_breaks_leaves_no_line_and_stops_nothing(tmp_path):
    card = card_from(tmp_path, Lookups(fail=True))
    labels = [line["label"] for row in card["rows"] for line in row["lines"]]
    assert "Owner of record" not in labels and "ownership" in card["not_checked"]


def test_an_unknown_company_s_name_is_nowhere_in_the_api_trace_or_report(tmp_path):
    """Lane D's real lookup over a lookup file whose company is not one we know."""
    from snapback.adapters import hcad

    subset = tmp_path / "owner_subset.jsonl"
    subset.write_text(
        json.dumps({"salt_fingerprint": hcad._salt_fingerprint("fx-salt")})
        + "\n"
        + json.dumps(
            {"key": hcad._key("100 Fixture Lane"), "kind": "company", "company": "FXHIDDEN LLC"}
        )
        + "\n",
        encoding="utf-8",
    )

    class RealOwner(Lookups):
        def owner(self, listing_text: str) -> OwnerResult | None:
            return hcad.owner(listing_text, subset, "fx-salt")

    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    client = TestClient(create_app(settings, RealOwner()))
    made = client.post(
        "/cases", data={"text": "3 bed house at 100 Fixture Lane. I am the owner. $1,900."}
    ).json()
    auth = {"Authorization": f"Bearer {made['token']}"}
    if made["status"] == "waiting_for_approval":
        client.post(
            f"/cases/{made['case_id']}/challenge/approve", json={"decision": "send"}, headers=auth
        )
    case = made["case_id"]
    card = client.get(f"/cases/{case}/card").json()
    said = {line["label"]: line["text"] for row in card["rows"] for line in row["lines"]}
    assert (
        said["Owner of record"]
        == "Not confirmed. Owner of record: a company owner, not the poster."
    )
    assert card["state"] == "hold"
    shown = [
        json.dumps(card),
        client.get(f"/cases/{case}", headers=auth).text,
        client.get(f"/cases/{case}/card?lang=es").text,
        client.get(f"/cases/{case}/report", headers=auth).text,
        client.get(f"/cases/{case}/trace", headers=auth).text,
    ]
    assert not [text for text in shown if "fxhidden" in text.lower()]
