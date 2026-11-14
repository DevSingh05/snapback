"""A23 (#144): three card fixes from the red team (conductor rulings, Sat 03:25).

H1  a typed manager name and a presence photo must not give "Checks passed": VERIFIED also
    needs the ad's phone to be the office's on record.
H5  the for-sale line says what the record says and no more. It never says "not for rent".
H8  ordinary agent copy raises no red flag.

Every name, number and sentence here is made up.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from snapback.agent.intake.fields import ContactClaims
from snapback.agent.rules import apply_rules
from snapback.agent.rules.contact import FIXTURE_PHONE_SALT, check_authority, phone_hash
from snapback.card import strings
from snapback.contracts import (
    AuthorityStatus,
    CardRowKind,
    CardTone,
    ModuleEvidence,
    PhoneMatch,
    PropertyRecord,
    VerdictState,
)
from snapback.verdict import build_card, decide, to_evidence

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")
OFFICE = "(555) 010-0142"  # 555-01xx numbers are reserved for fiction
OTHER = "555-010-0177"


def evidence(**sections) -> ModuleEvidence:
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    return ModuleEvidence.model_validate(raw | sections)


def record() -> PropertyRecord:
    raw = json.loads((CONTRACTS / "property_record.json").read_text())
    raw |= {
        "manager_company": "Fixture Living LLC",
        "site_phone_hash": phone_hash(OFFICE, FIXTURE_PHONE_SALT),
    }
    return PropertyRecord.model_validate(raw)


def case(claims: ContactClaims, **sections) -> ModuleEvidence:
    """Presence proven, nothing flagged, and whatever the listing says about the poster."""
    authority = check_authority(claims, record(), FIXTURE_PHONE_SALT)
    base = {"authority": authority.model_dump(mode="json"), "rules": [], "price": None}
    return evidence(**(base | sections))


def lines(modules: ModuleEvidence, kind: CardRowKind, lang: str = "en"):
    card = build_card(modules, checked_at=CHECKED_AT, lang=lang)
    row = next(row for row in card.rows if row.kind is kind)
    return {item.label: (item.tone, item.text) for item in row.lines}


# --- H1: a typed manager name is not enough ------------------------------------------------


def test_a_typed_manager_name_and_a_presence_photo_no_longer_pass():
    # The red team's repro: anyone can type the manager's public name, and a door code or a
    # former tenant gets a photo taken inside. That used to read "Checks passed".
    modules = case(ContactClaims(company="Fixture Living LLC"))
    assert modules.authority.status is AuthorityStatus.MATCHES_RECORD
    assert modules.authority.office_phone_match is PhoneMatch.NOT_CHECKED

    verdict = decide(to_evidence(modules))
    assert verdict.state is VerdictState.HOLD
    assert strings.text("reason.phone_not_confirmed") in verdict.reasons
    card = build_card(modules, checked_at=CHECKED_AT)
    assert card.state is VerdictState.HOLD
    # The card says what was not checked, so the hold is not a mystery.
    tone, text = lines(modules, CardRowKind.PERSON)["Contact on record"]
    assert tone is CardTone.NOT_CHECKED and text.startswith("Not checked (")


def test_the_name_and_the_office_phone_together_pass():
    modules = case(ContactClaims(company="Fixture Living LLC", phones=[OFFICE]))
    assert modules.authority.office_phone_match is PhoneMatch.YES
    evidence_ = to_evidence(modules)
    assert evidence_.phone_confirmed is True
    verdict = decide(evidence_)
    assert verdict.state is VerdictState.VERIFIED
    assert strings.text("reason.phone_not_confirmed") not in verdict.reasons


def test_the_office_phone_alone_still_never_passes():
    # Ruling on #87: the number is public, so a phone match alone is not who the poster is.
    modules = case(ContactClaims(phones=[OFFICE]))
    assert modules.authority.status is not AuthorityStatus.MATCHES_RECORD
    assert decide(to_evidence(modules)).state is VerdictState.HOLD


def test_a_phone_that_is_not_the_office_s_still_holds_and_is_said_once():
    modules = case(ContactClaims(company="Fixture Living LLC", phones=[OTHER]))
    verdict = decide(to_evidence(modules))
    assert verdict.state is VerdictState.HOLD
    assert strings.text("reason.phone_flag") in verdict.reasons
    assert strings.text("reason.phone_not_confirmed") not in verdict.reasons


def test_nothing_else_about_the_verdict_moved():
    # Proof still gives DON'T PAY, and an unplaced case is still UNVERIFIED.
    forged = ModuleEvidence.model_validate_json(
        (CONTRACTS / "module_evidence_forged.json").read_text()
    )
    assert decide(to_evidence(forged)).state is VerdictState.DONT_PAY
    unplaced = ModuleEvidence(case_id="fx-1", source="fixture")
    assert decide(to_evidence(unplaced)).state is VerdictState.UNVERIFIED


# --- H5: the for-sale line -----------------------------------------------------------------

LEASE = "Homes for sale are sometimes also offered for lease, so confirm with"


@pytest.mark.parametrize(
    ("for_sale", "said"),
    [
        (
            {"listed_on": "2026-10-02", "offices": ["Fixture Realty Group"]},
            "Listed for sale on Homes.com by Fixture Realty Group since 2026-10-02. "
            f"{LEASE} that brokerage before you pay.",
        ),
        (
            {"offices": ["Fixture Realty Group"]},
            f"Listed for sale on Homes.com by Fixture Realty Group. {LEASE} that brokerage "
            "before you pay.",
        ),
        (
            {"listed_on": "2026-10-02"},
            f"Listed for sale on Homes.com since 2026-10-02. {LEASE} the listing brokerage "
            "before you pay.",
        ),
        ({}, f"Listed for sale on Homes.com. {LEASE} the listing brokerage before you pay."),
    ],
)
def test_the_for_sale_line_is_a_warning_that_says_what_the_record_says(for_sale, said):
    modules = evidence(for_sale={"status": "active", "site": "Homes.com"} | for_sale)
    tone, text = lines(modules, CardRowKind.PLACE)["For sale"]
    assert (tone, text) == (CardTone.HOLD, said)
    assert strings.tone_word(tone, CardRowKind.PLACE) == "Warning"
    assert decide(to_evidence(modules)).state is VerdictState.HOLD


@pytest.mark.parametrize("lang", ["en", "es"])
def test_nothing_about_a_home_for_sale_says_it_is_not_for_rent(lang):
    # We never say whether a home is leased or not. The record says "for sale"; so do we.
    said = [text for key, text in strings.TABLES[lang].items() if "for_sale" in key]
    assert said
    for text in said:
        lowered = text.lower()
        assert "not for rent" not in lowered and "no en alquiler" not in lowered
        assert "red flag" not in lowered and "señal de alerta" not in lowered
    modules = evidence(
        for_sale={"status": "active", "site": "Homes.com", "offices": ["Fixture Realty Group"]}
    )
    label = strings.text("label.for_sale", lang)
    tone, text = lines(modules, CardRowKind.PLACE, lang)[label]
    assert tone is CardTone.HOLD and "Fixture Realty Group" in text
    verdict = decide(to_evidence(modules, lang), lang)
    assert strings.text("reason.for_sale", lang) in verdict.reasons


def test_for_sale_by_the_office_on_record_is_information_and_holds_nothing():
    # Ruling, Sat 03:36: the record shows the home for sale AND the ad's phone is the office's
    # on record. That is the brokerage itself offering it, so for sale is an information
    # line and no hold comes from it.
    for_sale = {
        "status": "active",
        "site": "Homes.com",
        "listed_on": "2026-10-02",
        "offices": ["Fixture Realty Group"],
    }
    office = case(ContactClaims(company="Fixture Living LLC", phones=[OFFICE]), for_sale=for_sale)
    assert office.authority.office_phone_match is PhoneMatch.YES
    assert to_evidence(office).for_sale_flag is False
    verdict = decide(to_evidence(office))
    assert verdict.state is VerdictState.VERIFIED
    assert strings.text("reason.for_sale") not in verdict.reasons
    assert lines(office, CardRowKind.PLACE)["For sale"] == (
        CardTone.NOT_SHOWN,
        "Not confirmed. Listed for sale on Homes.com by Fixture Realty Group since "
        "2026-10-02. The contact in this listing is the office on record, so ask them "
        "whether it is also offered for lease.",
    )

    # Any other contact, or none, and the same record still holds the case with a warning.
    for claims in (
        ContactClaims(company="Fixture Living LLC", phones=[OTHER]),
        ContactClaims(company="Fixture Living LLC"),
        ContactClaims(),
    ):
        other = case(claims, for_sale=for_sale)
        assert to_evidence(other).for_sale_flag is True
        assert decide(to_evidence(other)).state is VerdictState.HOLD
        assert lines(other, CardRowKind.PLACE)["For sale"][0] is CardTone.HOLD

    # With nothing placed, the office's own ad is not held for being for sale either.
    unplaced = ModuleEvidence.model_validate(
        {
            "case_id": "fx-1",
            "source": "fixture",
            "authority": office.authority.model_dump(mode="json"),
            "for_sale": for_sale,
        }
    )
    assert decide(to_evidence(unplaced)).state is VerdictState.UNVERIFIED
    spanish = lines(office, CardRowKind.PLACE, "es")[strings.text("label.for_sale", "es")]
    assert spanish[0] is CardTone.NOT_SHOWN and spanish[1].startswith("Sin confirmar.")


def test_the_brokerage_on_the_line_is_one_line_and_never_long():
    odd = {"status": "active", "site": "Homes.com", "offices": ["Fx  Realty\n" * 40]}
    _, text = lines(evidence(for_sale=odd), CardRowKind.PLACE)["For sale"]
    assert "\n" not in text and "  " not in text and len(text) < 320


# --- H8: ordinary agent copy ---------------------------------------------------------------

# The red team's eight honest sentences, verbatim (conductor, #144). Six of them raised a
# red flag on main.
HONEST_REPORT = [
    "Pay the $50 application fee through our online portal",
    "Holding deposit is due once your application is approved, payable through the resident portal",
    "I'm out of town this week, but you can tour anytime with the lockbox code",
    "I am the listing agent and I can't show it until Saturday",
    "We can't meet in person, but we offer a live video tour",
    "Send your application and the application fee to our office",
    "Self-tour with the lockbox code",
    "A holding deposit is due after approval",
]
# The same things said the other ways agents say them.
HONEST_MORE = [
    "Application fee is $50 per adult, paid online through our resident portal.",
    "Once approved, a holding deposit secures the home until move-in.",
    "Upon approval, a holding deposit equal to one month's rent is due within 48 hours.",
    "You can pay the application fee on our website when you apply.",
    "Register for a self-guided tour and we will text you a one-time lockbox code.",
    "We cannot show the home until the current tenant moves out on the 1st.",
    "I can't meet until Saturday morning, the office is closed Friday.",
    "Showings start Saturday. Text the leasing office to book a time.",
    "Drop the application fee at the leasing office with your paperwork.",
]
# Round 1 FIX, item 4: five realtor lines that still red-flagged.
HONEST_REALTOR = [
    "Holding deposit of one month's rent is due within 48 hours of approval to reserve the home.",
    "Holding deposit due within 24 hours of approval.",
    "Following approval, pay the holding deposit to reserve the home.",
    "Approved applicants pay a holding deposit to take the home off the market.",
    "Send the application fee to my office.",
]
HONEST = HONEST_REPORT + HONEST_MORE + HONEST_REALTOR

# The conductor's three, verbatim, from the locked rules.
SCAMS_REPORT = [
    ("Send the deposit by Zelle today to hold it, I'll show you after.", "payment."),
    (
        "I'm out of the country for work, so I'll mail you the keys once the first month is wired.",
        "pressure.cannot_show",
    ),
    (
        "Pay a $500 deposit now with a gift card and the place is yours, no viewing needed.",
        "payment.",
    ),
]
SCAMS_MORE = [
    # Zelle, wire or a gift card before a viewing.
    ("Send the deposit by Zelle before the viewing and I will hold it for you.", "payment."),
    ("Wire the first month's rent today and I will send the keys.", "payment."),
    ("Pay with gift cards to hold the unit.", "payment."),
    # Abroad, or keys by mail.
    ("I'm out of the country, I'll mail the keys.", "pressure.cannot_show"),
    ("I can't show it, I am overseas for work.", "pressure.cannot_show"),
    ("I can't show it in person, but I will ship the keys.", "pressure.cannot_show"),
    # A deposit to hold before any viewing or application.
    ("Send a $500 deposit to hold it before you see it.", "fee.holding_deposit"),
    ("A deposit is required to hold the home before any viewing or application.", "fee."),
    # The honest words do not launder the ask.
    ("Once approved, send the holding deposit by Zelle today.", "payment."),
    ("Once approved, send the holding deposit by Zelle today.", "fee.holding_deposit"),
    ("Pay the application fee through our portal, then Venmo me the deposit.", "payment."),
    ("Pay the application fee online by gift card.", "fee.application"),
    ("We can't show until you send the deposit.", "fee.holding_deposit"),
    ("Venmo me the $75 application fee and I will send you the address.", "fee.application"),
    ("Send the application fee to our office in cash today.", "fee.application"),
]
# Round 1 FIX, item 3: an ordinary step does not excuse a sentence that skips the viewing.
SCAMS_SKIP_VIEWING = [
    ("Send the $500 holding deposit through our website to reserve it before you tour.", "fee."),
    ("Once you are approved, send the deposit to hold the house, no need to see it.", "fee."),
    ("Pay the application fee online, sight unseen.", "fee.application"),
    ("Approved applicants send the holding deposit to hold it, no viewing.", "fee."),
]
SCAMS = SCAMS_REPORT + SCAMS_MORE + SCAMS_SKIP_VIEWING


def red_flags(text: str) -> list[str]:
    return [hit.rule_id for hit in apply_rules(text) if hit.red_flag]


@pytest.mark.parametrize("text", HONEST)
def test_ordinary_agent_copy_raises_no_red_flag(text):
    assert red_flags(text) == []


@pytest.mark.parametrize(("text", "family"), SCAMS)
def test_the_asks_that_matter_are_still_red_flags(text, family):
    assert any(rule_id.startswith(family) for rule_id in red_flags(text)), red_flags(text)


def test_the_report_s_eleven_sentences_are_all_here():
    assert len(HONEST_REPORT) == 8 and len(SCAMS_REPORT) == 3


def test_a_listing_made_of_honest_copy_is_not_held_by_the_rules():
    from snapback.agent.intake import read_listing

    listing = read_listing(". ".join(text.rstrip(".") for text in HONEST) + ".")
    assert [hit.rule_id for hit in listing.rule_hits if hit.red_flag] == []
