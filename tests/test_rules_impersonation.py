"""Impersonation and gap rules: hold only, one reason each, and the sender-address lookalike."""

import json
from pathlib import Path

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
ROOT = Path(__file__).resolve().parent.parent
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
        "From: payment@fixtureliving.pay.example\nPlease confirm the deposit.",
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
        "Email leasing@mailhost.example or call us.",
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
    assert check_link([], SITE, emails=["fixtureliving@mailhost.example"]) is LinkDomain.OTHER


def test_the_rules_read_the_costar_example_message_three():
    text = (
        "I will explain how it works. You will be instructed to do the deposit to an agent "
        "from Airbnb.com, they will hold and insure your money until you check the apartment."
    )
    assert "impersonation.escrow_agent" in [h.rule_id for h in apply_rules(text)]


@pytest.mark.parametrize(
    "email",
    [
        "office@live.com",
        "office@hotmail.com",
        "office@ymail.com",
        "office@icloud.com",
        "office@yahoo.co.in",
        "office@proton.me",
        "oliveoffice@gmail.com",
    ],
)
def test_free_mail_domains_are_never_a_lookalike(email):
    assert check_link([], "olive.example", emails=[email]) is LinkDomain.OTHER
    assert check_link([], "gmailhome.example", emails=[email]) is LinkDomain.OTHER


def test_a_free_mail_name_does_not_hide_a_real_lookalike():
    assert (
        check_link([], "olive.example", emails=["office@live.com", "office@olive.pay.example"])
        is LinkDomain.LOOKALIKE
    )


def test_affiliate_credit_check_skips_the_buildings_own_host():
    text = "Run your credit check at fixtureliving.example/residents."
    assert "link.affiliate_credit_check" in [h.rule_id for h in apply_rules(text)]
    assert "link.affiliate_credit_check" not in [
        h.rule_id for h in apply_rules(text, own_host="fixtureliving.example")
    ]


def test_the_payment_reason_covers_papers_as_well_as_money():
    line = strings.text("reason.payment_flag")
    assert line == "Money or personal papers were asked for before any viewing."


def test_a_sender_only_lookalike_has_its_own_card_line():
    assert strings.has("contact.lookalike_sender") and strings.has("contact.lookalike_sender", "es")
    assert "email address" in strings.text("contact.lookalike_sender")


def test_a_lookalike_found_only_in_the_sender_is_marked_and_a_link_one_is_not():
    from types import SimpleNamespace

    from snapback.agent.rules.contact import check_authority
    from snapback.contracts import PropertyRecord

    data = json.loads((ROOT / "fixtures" / "contracts" / "property_record.json").read_text())
    record = PropertyRecord.model_validate(data | {"website_host": SITE})
    sender = SimpleNamespace(
        company=None, phones=[], links=[], emails=["pay@fixtureliving.pay.example"]
    )
    link = SimpleNamespace(company=None, phones=[], links=["fixtureliving.pay.example"], emails=[])
    assert check_authority(sender, record, "s").lookalike_sender_only is True
    assert check_authority(link, record, "s").lookalike_sender_only is False


@pytest.mark.parametrize(
    "text",
    [
        "Photos at fixtureliving.example; run your credit at freecredit.example, text me.",
        "Run your credit at freecredit.example/?ref=fixtureliving.example and send me the score.",
        "Run your credit at fixtureliving.example.freecredit.example now.",
        "Run your credit at fixtureliving.example/residents or at freecredit.example now.",
    ],
)
def test_naming_the_real_site_does_not_switch_the_affiliate_rule_off(text):
    hits = [h.rule_id for h in apply_rules(text, own_host="fixtureliving.example")]
    assert "link.affiliate_credit_check" in hits


def test_a_subdomain_of_the_buildings_own_site_is_its_own():
    text = "Run your credit check at apply.fixtureliving.example/residents."
    hits = [h.rule_id for h in apply_rules(text, own_host="fixtureliving.example")]
    assert "link.affiliate_credit_check" not in hits
