"""Office confirmation, part 1: the domain comes from CoStar's record, and only from it."""

import json
from pathlib import Path

import pytest

from snapback.contracts import PropertyRecord
from snapback.office import domain as domain_module
from snapback.office.domain import (
    accepts_address,
    official_domain,
    registrable_domain,
)

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"


def record(**changes) -> PropertyRecord:
    raw = json.loads((CONTRACTS / "property_record_contact.json").read_text())
    return PropertyRecord.model_validate(raw | changes)


def test_the_official_domain_is_the_registrable_domain_of_the_records_website():
    assert official_domain(record(website_host="fixtureliving.example")) == "fixtureliving.example"
    assert official_domain(record(website_host="leasing.camdenliving.com")) == "camdenliving.com"
    assert official_domain(record(website_host="WWW.Camdenliving.COM")) == "camdenliving.com"
    assert official_domain(record(website_host="oakcourt.co.uk")) == "oakcourt.co.uk"
    assert official_domain(record(website_host="www.oakcourt.co.uk")) == "oakcourt.co.uk"


def test_no_website_on_record_means_no_official_domain():
    assert official_domain(record(website_host=None)) is None
    assert official_domain(None) is None


def test_the_domain_never_comes_from_the_ad():
    # The record is the only input. An ad-supplied domain has no way in: the function takes
    # nothing else, and a record with no website stays None whatever else the case holds.
    import inspect

    assert list(inspect.signature(official_domain).parameters) == ["record"]
    assert official_domain(record(website_host=None, manager_company="camdenliving.com")) is None


@pytest.mark.parametrize(
    "host",
    [
        "gmail.com",
        "mail.gmail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "outlook.com",
        "hotmail.com",
        "icloud.com",
        "proton.me",
        "protonmail.com",
        "aol.com",
        "zillow.com",
        "apartments.com",
        "www.apartments.com",
        "facebook.com",
        "craigslist.org",
        "sfbay.craigslist.org",
        "hotpads.com",
        "rent.com",
        "linktr.ee",
        "wixsite.com",
        "someone.godaddysites.com",
        "rentcafe.com",
        "someone.github.io",
        # Property-management software vendors host many unrelated offices' sites.
        "appfolio.com",
        "acme.appfolio.com",
        "prospectportal.com",
        "rentmanager.com",
        "managebuilding.com",
        "tenantturner.com",
        "rentcafewebsite.com",
        "securecafe.com",
        "entrata.com",
        "realpage.com",
        "rently.com",
        "buildium.com",
        "showmojo.com",
    ],
)
def test_free_mail_and_platform_hosts_are_never_an_official_domain(host):
    assert official_domain(record(website_host=host)) is None


@pytest.mark.parametrize(
    "host",
    [
        "xn--camdnliving-9db.com",  # punycode
        "camdénliving.com",  # homoglyph (non-ASCII)
        "саmdenliving.com",  # Cyrillic a
        "camden living.com",
        "camdenliving.com/path",
        "user@camdenliving.com",
        "localhost",
        "com",
        "co.uk",
        "10.0.0.1",
        "camden..com",
        "-camden.com",
        "camden-.com",
        "a" * 64 + ".com",
        "oakcourt.co.xx",  # an ending we do not know that starts with a generic label
        "oakcourt.com.xx",
        "oakcourt.org.zz",
        "",
    ],
)
def test_lookalike_and_malformed_hosts_are_rejected(host):
    assert official_domain(record(website_host=host)) is None
    assert registrable_domain(host) is None


@pytest.mark.parametrize(
    ("address", "ok"),
    [
        ("leasing@camdenliving.com", True),
        ("Anyone@CAMDENLIVING.com", True),
        ("a.b+c@camdenliving.com", True),
        ("agent@mail.camdenliving.com", False),  # exact domain only (decision 183)
        ("agent@camdenliving.com.evil.com", False),
        ("agent@evilcamdenliving.com", False),
        ("agent@camdenliving.co", False),
        ("agent@example.com", False),  # the kit's own addresses are never the answer
        ("agent@gmail.com", False),
        ("agent@xn--camdnliving-9db.com", False),
        ("agent@camdénliving.com", False),
        ("camdenliving.com", False),
        ("@camdenliving.com", False),
        ("a@b@camdenliving.com", False),
        ("agent@camdenliving.com\r\nBcc: x@evil.com", False),
        ("agent @camdenliving.com", False),
        ("agent@camdenliving.com.", False),
        ("a" * 65 + "@camdenliving.com", False),
        ("", False),
    ],
)
def test_the_address_must_be_at_the_official_domain_exactly(address, ok):
    assert accepts_address(address, "camdenliving.com") is ok


def test_an_address_is_never_accepted_without_an_official_domain():
    assert accepts_address("agent@camdenliving.com", None) is False


def test_no_network_client_is_imported_by_the_domain_code():
    source = Path(domain_module.__file__).read_text()
    for name in ("smtplib", "httpx", "requests", "urllib", "socket", "aiohttp"):
        assert f"import {name}" not in source and f"from {name}" not in source


def test_record_json_shape_is_unchanged_by_this_feature():
    # PropertyRecord gained no field: the website host is all the domain rule reads.
    assert "website_host" in PropertyRecord.model_fields


def test_a_private_ending_like_us_com_is_part_of_the_ending_not_the_name():
    assert official_domain(record(website_host="www.oakcourt.us.com")) == "oakcourt.us.com"
    assert accepts_address("me@oakcourt.us.com", "oakcourt.us.com") is True
    assert accepts_address("me@evil.us.com", "oakcourt.us.com") is False
    assert accepts_address("me@evil.us.com", "us.com") is False
    assert official_domain(record(website_host="us.com")) is None
