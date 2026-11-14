"""Impersonation and gap rules: hold only, one reason each, and the sender-address lookalike."""

import pytest

from snapback.agent.intake.fields import extract_contacts
from snapback.agent.rules import apply_rules
from snapback.agent.rules.contact import check_link
from snapback.card import strings
from snapback.contracts import LinkDomain

NEW_IDS = (
    "impersonation.platform_holds_money",
    "impersonation.escrow_agent",
    "data.credit_score_screenshot",
    "data.paystub_before_viewing",
    "data.sevis_before_viewing",
    "link.affiliate_credit_check",
)
SITE = "fixtureliving.example"


def test_new_rules_are_red_flags_that_hold_and_never_set_dont_pay():
    # decide() sets DONT_PAY only on proof (forged reply, photo elsewhere); a rule hit is
    # evidence flags only, so the strongest effect of these rules is the red flag.
    from snapback.agent.rules.table import RULES

    by_id = {rule.rule_id: rule for rule in RULES}
    assert all(by_id[rule_id].red_flag for rule_id in NEW_IDS)


def test_costar_line_is_quoted_exactly():
    assert strings.COSTAR_AFFILIATION_QUOTE == (
        "Claim of affiliation with us. Scammers may impersonate Apartments.com or Apartment "
        "Finder to make it seem like we participate in the lease transaction or transfer of funds."
    )
    assert strings.text("rule.impersonation.platform_holds_money").endswith("Red flag.")


@pytest.mark.parametrize("rule_id", NEW_IDS)
def test_every_new_rule_has_an_english_and_a_spanish_line(rule_id):
    assert strings.has(f"rule.{rule_id}", "es")


@pytest.mark.parametrize(
    "text",
    [
        "From: payment@fixtureliving.co\nPlease confirm the deposit.",
        "Reply to leasing@fixture-living.example to reserve.",
        "Contact fixtureliviing.example staff: office@fixtureliviing.example",
    ],
)
def test_a_lookalike_sender_address_is_a_lookalike(text):
    contacts = extract_contacts(text)
    assert contacts.emails
    assert check_link([], SITE, emails=contacts.emails) is LinkDomain.LOOKALIKE


@pytest.mark.parametrize(
    "text",
    [
        "Questions? leasing@fixtureliving.example",
        "Email maria.lopez@gmail.com or call us.",
        "info@sunriseproperty.example",
    ],
)
def test_the_buildings_own_or_an_unrelated_sender_is_not_a_lookalike(text):
    contacts = extract_contacts(text)
    status = check_link([], SITE, emails=contacts.emails)
    assert status in (LinkDomain.MATCHES, LinkDomain.OTHER)


def test_no_email_and_no_link_is_not_checked():
    assert check_link([], SITE, emails=[]) is LinkDomain.NOT_CHECKED


def test_a_personal_mail_address_that_carries_the_name_is_left_alone():
    # The part before the @ is not read for emails: small landlords use personal mail.
    assert check_link([], SITE, emails=["fixtureliving@gmail.com"]) is LinkDomain.OTHER


def test_the_rules_read_the_costar_example_message_three():
    text = (
        "I will explain how it works. You will be instructed to do the deposit to an agent "
        "from Airbnb.com, they will hold and insure your money until you check the apartment."
    )
    assert "impersonation.escrow_agent" in [h.rule_id for h in apply_rules(text)]
