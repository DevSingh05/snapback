"""A7 (#67): contact on record, for-sale, and unit and rent rules. Synthetic records only."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from snapback.agent.intake import read_listing
from snapback.agent.intake.fields import ContactClaims, extract_beds, extract_contacts, extract_unit
from snapback.agent.rules import check_price, check_unit
from snapback.agent.rules.contact import (
    FIXTURE_PHONE_SALT,
    check_authority,
    check_link,
    host_of,
    phone_hash,
)
from snapback.card import strings
from snapback.contracts import (
    AuthorityStatus,
    CardRowKind,
    CardTone,
    ForSaleMatch,
    LinkDomain,
    ModuleEvidence,
    PhoneMatch,
    PriceStatus,
    PropertyRecord,
    UnitStatus,
    VerdictState,
)
from snapback.verdict import build_card, decide, to_evidence

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
SALT = FIXTURE_PHONE_SALT
OFFICE = "(555) 010-0142"  # 555-01xx numbers are reserved for fiction
OTHER = "555-010-0177"
SITE = "fixtureliving.example"
# A fixed clock: a card or a trace stamped "now" could hold any four digits by chance, and
# several tests here assert that certain digits appear nowhere.
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")


def record(**changes) -> PropertyRecord:
    raw = json.loads((CONTRACTS / "property_record_contact.json").read_text())
    raw["site_phone_hash"] = phone_hash(OFFICE, SALT)
    return PropertyRecord.model_validate(raw | changes)


def evidence(**sections) -> ModuleEvidence:
    """The HOLD fixture with presence proven, so only the section under test decides."""
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    return ModuleEvidence.model_validate(raw | sections)


def state(modules: ModuleEvidence) -> VerdictState:
    return decide(to_evidence(modules)).state


def card_lines(modules: ModuleEvidence, kind: CardRowKind) -> dict[str, tuple[CardTone, str]]:
    card = build_card(modules, checked_at=CHECKED_AT)
    row = next(row for row in card.rows if row.kind is kind)
    return {item.label: (item.tone, item.text) for item in row.lines}


def everything_on(modules: ModuleEvidence) -> str:
    card = build_card(modules, checked_at=CHECKED_AT)
    verdict = decide(to_evidence(modules))
    return " ".join([card.model_dump_json(), verdict.model_dump_json(), modules.model_dump_json()])


# --- the new contract shapes ---------------------------------------------------------------


def test_the_new_fixtures_parse_and_old_records_still_do():
    assert record().website_host == SITE
    assert ForSaleMatch.model_validate_json((CONTRACTS / "for_sale_match.json").read_text())
    old = PropertyRecord.model_validate_json((CONTRACTS / "property_record.json").read_text())
    assert (old.site_phone_hash, old.website_host, old.floor_plan_rents, old.units) == (
        None, None, [], [],
    )  # fmt: skip


# --- phone: a keyed hash, compared, never shown --------------------------------------------


@pytest.mark.parametrize(
    ("phones", "expected"),
    [
        ([OFFICE], PhoneMatch.YES),
        ([OTHER, OFFICE], PhoneMatch.NO),
        ([OFFICE, OTHER], PhoneMatch.NO),
        ([OFFICE, "(555) 010-0142"], PhoneMatch.YES),
        ([OTHER], PhoneMatch.NO),
        ([], PhoneMatch.NOT_CHECKED),
    ],
)
def test_the_listing_phone_is_compared_with_the_leasing_office(phones, expected):
    result = check_authority(ContactClaims(phones=phones), record(), SALT)
    assert result.office_phone_match is expected


def test_no_phone_on_the_record_means_not_checked():
    result = check_authority(ContactClaims(phones=[OTHER]), record(site_phone_hash=None), SALT)
    assert result.office_phone_match is PhoneMatch.NOT_CHECKED
    assert check_authority(ContactClaims(phones=[OTHER]), None, SALT).office_phone_match is (
        PhoneMatch.NOT_CHECKED
    )


def test_a_phone_that_is_not_the_office_holds_the_case_even_if_the_name_matches():
    claims = ContactClaims(company="Fixture Living LLC", phones=[OTHER])
    authority = check_authority(claims, record(), SALT)
    assert authority.status is AuthorityStatus.MATCHES_RECORD
    modules = evidence(authority=authority.model_dump(mode="json"))
    assert to_evidence(modules).phone_flag is True
    assert state(modules) is VerdictState.HOLD

    # Ruling, Sat 02:10 (#121): a number that is not the office's reads Not confirmed. A
    # licensed locator or listing agent posting with their own number is normal and legal.
    tone, text = card_lines(modules, CardRowKind.PERSON)["Contact on record"]
    assert tone is CardTone.NOT_SHOWN
    # The one "Call {manager} yourself" on this row is on the "Allowed to rent it" line, so
    # this line does not say "call" a second time.
    assert text == (
        "Not confirmed. This number is not the leasing office's on record. "
        "Agents often use their own, so check it with the office."
    )
    assert "Fixture Living LLC" in card_lines(modules, CardRowKind.PERSON)["Allowed to rent it"][1]

    # With no manager on record nothing else on the row says who to call, so this line does.
    unnamed = check_authority(ContactClaims(phones=[OTHER]), record(manager_company=None), SALT)
    tone, said = card_lines(
        evidence(authority=unnamed.model_dump(mode="json")), CardRowKind.PERSON
    )["Contact on record"]
    assert tone is CardTone.NOT_SHOWN
    assert said == (
        "Not confirmed. This number is not the leasing office's on record. "
        "Agents often use their own. Call the office on record yourself to confirm."
    )


def test_a_phone_mismatch_alone_holds_the_case_and_puts_no_red_flag_anywhere_on_the_card():
    # Everything else is in order: presence proven, the company named is the manager on
    # record, nothing flagged. Only the phone differs.
    claims = ContactClaims(company="Fixture Living LLC", phones=[OTHER])
    authority = check_authority(claims, record(), SALT)
    assert authority.office_phone_match is PhoneMatch.NO
    modules = evidence(authority=authority.model_dump(mode="json"), rules=[], price=None)

    verdict = decide(to_evidence(modules))
    # It still holds: the card cannot say "Checks passed" while the contact is unconfirmed.
    assert verdict.state is VerdictState.HOLD
    assert strings.text("reason.phone_flag") in verdict.reasons

    card = build_card(modules, checked_at=CHECKED_AT)
    tones = [item.tone for row in card.rows for item in row.lines]
    assert CardTone.RED_FLAG not in tones
    assert not any("Red flag" in item.text for row in card.rows for item in row.lines)
    # And with the office's own number the same case passes, so the phone is what holds it.
    passing = check_authority(
        ContactClaims(company="Fixture Living LLC", phones=[OFFICE]), record(), SALT
    )
    assert passing.office_phone_match is PhoneMatch.YES
    assert state(evidence(authority=passing.model_dump(mode="json"), rules=[], price=None)) is (
        VerdictState.VERIFIED
    )


def test_a_lookalike_link_is_still_a_red_flag_beside_an_unconfirmed_phone():
    claims = ContactClaims(phones=[OTHER], links=["fixtureliving-apply.example"])
    authority = check_authority(claims, record(), SALT)
    person = card_lines(evidence(authority=authority.model_dump(mode="json")), CardRowKind.PERSON)
    assert person["Contact on record"][0] is CardTone.NOT_SHOWN
    assert person["Link"][0] is CardTone.RED_FLAG


def test_a_matching_phone_is_a_supporting_line_and_never_authority():
    # XO ruling on #87: anyone can copy the office's public number into a listing.
    authority = check_authority(ContactClaims(phones=[OFFICE]), record(), SALT)
    assert authority.office_phone_match is PhoneMatch.YES
    assert authority.status is AuthorityStatus.UNKNOWN

    modules = evidence(authority=authority.model_dump(mode="json"))
    person = card_lines(modules, CardRowKind.PERSON)
    assert person["Contact on record"] == (
        CardTone.OK,
        "The phone matches the leasing office on record. Call it yourself to confirm.",
    )
    assert person["Allowed to rent it"] == (
        CardTone.NOT_SHOWN,
        strings.text("allowed.not_shown"),
    )


def test_a_matching_phone_with_presence_proven_and_no_company_is_not_verified():
    authority = check_authority(ContactClaims(phones=[OFFICE]), record(), SALT)
    modules = evidence(authority=authority.model_dump(mode="json"), rules=[], price=None)
    assert to_evidence(modules).presence == "proven"
    assert not any(
        (to_evidence(modules).rule_flag, to_evidence(modules).price_flag)
    )  # nothing else holds it
    assert state(modules) is VerdictState.HOLD

    # The same case with the company named is what VERIFIED takes.
    named = check_authority(
        ContactClaims(company="Fixture Living LLC", phones=[OFFICE]), record(), SALT
    )
    assert state(evidence(authority=named.model_dump(mode="json"), rules=[], price=None)) is (
        VerdictState.VERIFIED
    )


def test_a_different_company_is_a_mismatch_whatever_the_phone_says():
    claims = ContactClaims(company="Sunrise Property Group", phones=[OFFICE])
    assert check_authority(claims, record(), SALT).status is AuthorityStatus.MISMATCH


def test_no_phone_number_or_hash_or_web_address_reaches_card_verdict_or_evidence():
    claims = ContactClaims(phones=[OTHER], links=["fixtureliving-apply.example"])
    authority = check_authority(claims, record(), SALT)
    modules = evidence(authority=authority.model_dump(mode="json"))
    out = everything_on(modules)
    for secret in ("0142", "0177", phone_hash(OFFICE, SALT), phone_hash(OTHER, SALT), SITE):
        assert secret not in out
    assert "fixtureliving-apply" not in out


# --- the name they gave --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("Fixture Living LLC", AuthorityStatus.MATCHES_RECORD),
        ("fixture living", AuthorityStatus.MATCHES_RECORD),
        ("Fixture Living, L.L.C.", AuthorityStatus.MATCHES_RECORD),
        ("Fixture", AuthorityStatus.MATCHES_RECORD),
        ("Sunrise Property Group", AuthorityStatus.MISMATCH),
        ("Living", AuthorityStatus.MISMATCH),
        (None, AuthorityStatus.UNKNOWN),
    ],
)
def test_the_company_the_poster_named_is_compared_with_the_manager_on_record(said, expected):
    result = check_authority(ContactClaims(company=said), record(), SALT)
    assert result.status is expected
    assert result.manager_on_record == "Fixture Living LLC"


def test_without_a_record_or_a_manager_nothing_is_claimed():
    claims = ContactClaims(company="Fixture Living LLC")
    assert check_authority(claims, None, SALT).status is AuthorityStatus.UNKNOWN
    assert check_authority(claims, record(manager_company=None), SALT).status is (
        AuthorityStatus.UNKNOWN
    )


# --- links: the building's own site, or something dressed up as it -------------------------


@pytest.mark.parametrize(
    "link",
    [
        "fixtureliving.example",
        "www.fixtureliving.example",
        "https://fixtureliving.example/floorplans?x=1",
        "apply.fixtureliving.example",
        "FixtureLiving.example:443",
    ],
)
def test_the_buildings_own_site_is_recognised(link):
    assert check_link([host_of(link)], SITE) is LinkDomain.MATCHES


@pytest.mark.parametrize(
    "link",
    [
        "fixtureliving.co",  # another ending
        "fixtureliving-apply.example",  # extra word
        "apply-fixtureliving.example",
        "fixtureliving.example.pay-now.co",  # the real name as a subdomain of something else
        "fixtureliviing.example",  # one letter added
        "fixtureiving.example",  # one letter dropped
        "fixtureilving.example",  # two letters swapped
        "fixturel1ving.example",  # a digit for a letter
        "xn--fixturelving-zfb.example",  # punycode: an accented i
        "fіxtureliving.example",  # a Cyrillic i
        "https://fixtureliving.example@pay-now.co/deposit",  # the real name before an @
    ],
)
def test_a_lookalike_of_the_buildings_site_is_caught(link):
    assert check_link([host_of(link)], SITE) is LinkDomain.LOOKALIKE


@pytest.mark.parametrize(
    "link",
    ["zillow.com", "www.apartments.com", "docs.google.com", "sunriseproperty.example", "fix.co"],
)
def test_an_unrelated_site_is_not_called_a_lookalike(link):
    assert check_link([host_of(link)], SITE) is LinkDomain.OTHER


def test_a_lookalike_outweighs_the_real_site_and_no_link_or_no_website_is_not_checked():
    assert check_link(["fixtureliving.example", "fixtureliving.co"], SITE) is LinkDomain.LOOKALIKE
    assert check_link([], SITE) is LinkDomain.NOT_CHECKED
    assert check_link(["fixtureliving.co"], None) is LinkDomain.NOT_CHECKED
    # A record that points at a big shared site gives nothing to imitate.
    assert check_link(["apartments-com.example"], "apartments.com") is LinkDomain.OTHER


def test_a_lookalike_link_is_a_red_flag_on_the_person_row_and_holds_the_case():
    claims = ContactClaims(company="Fixture Living LLC", links=["fixtureliving-apply.example"])
    authority = check_authority(claims, record(), SALT)
    assert authority.link_domain is LinkDomain.LOOKALIKE
    modules = evidence(authority=authority.model_dump(mode="json"))
    assert state(modules) is VerdictState.HOLD
    tone, text = card_lines(modules, CardRowKind.PERSON)["Link"]
    assert tone is CardTone.RED_FLAG
    assert text == "A link in the listing imitates this building's website but is not it. Red flag."


def test_links_are_read_from_the_listing_text():
    text = (
        "Managed by Fixture Living LLC. Apply at https://fixtureliving-apply.example/now "
        "or see www.fixtureliving.example. Also on fixtureliving.co today."
    )
    assert extract_contacts(text).links == [
        "fixtureliving-apply.example",
        "fixtureliving.example",
        "fixtureliving.co",
    ]
    assert extract_contacts("Email me at jo@fixtureliving.example.").links == []


# --- for sale ------------------------------------------------------------------------------


def test_a_home_listed_for_sale_is_a_warning_on_the_place_row_and_holds_the_case():
    modules = evidence(for_sale={"status": "active"})
    assert to_evidence(modules).for_sale_flag is True
    assert state(modules) is VerdictState.HOLD
    # Red team H5 (Sat 03:25): a warning, not a red flag, and never "not for rent". Homes
    # for sale are sometimes also offered for lease, and lease status is not ours to claim.
    tone, text = card_lines(modules, CardRowKind.PLACE)["For sale"]
    assert tone is CardTone.HOLD
    assert text == (
        "Listed for sale on Homes.com. Homes for sale are sometimes also offered for lease, "
        "so confirm with the listing brokerage before you pay."
    )


def test_for_sale_holds_a_case_even_when_no_photo_could_be_placed():
    # Conductor ruling, Sat 02:00: for sale outranks "could not place". A home that is for
    # sale usually has no 3D scan, and "we could not check" is the wrong headline for it.
    nothing_placed = ModuleEvidence(case_id="fx-1", source="fixture", for_sale={"status": "active"})
    verdict = decide(to_evidence(nothing_placed))
    assert verdict.state is VerdictState.HOLD
    assert verdict.reasons[0] == strings.text("reason.for_sale")
    assert strings.text("reason.not_indexed") in verdict.reasons  # and why nothing was placed

    unplaced = evidence(
        for_sale={"status": "active"},
        locate={
            "case_id": "fx-7Q2M",
            "photos": [{"photo_id": "l1", "status": "not_located"}],
            "thresholds_version": "none",
        },
    )
    assert state(unplaced) is VerdictState.HOLD


def test_for_sale_is_never_dont_pay_and_nothing_else_outranks_could_not_place():
    # DON'T PAY needs proof: a forged reply or a photo taken elsewhere. For sale is neither.
    assert state(evidence(for_sale={"status": "active"}, challenge=None)) is VerdictState.HOLD
    nothing = {"case_id": "fx-1", "source": "fixture"}
    for other in (
        {"for_sale": {"status": "recently_rented"}},
        {"authority": {"status": "unknown", "office_phone_match": "no"}},
        {"authority": {"status": "unknown", "link_domain": "lookalike"}},
        {"price": {"status": "not_checked", "unit": "not_on_record"}},
    ):
        verdict = decide(to_evidence(ModuleEvidence.model_validate(nothing | other)))
        assert verdict.state is VerdictState.UNVERIFIED, other
    # A photo taken in another building still outranks everything.
    elsewhere = evidence(
        for_sale={"status": "active"},
        locate={
            "case_id": "fx-7Q2M",
            "photos": [{"photo_id": "l1", "status": "located_elsewhere"}],
            "thresholds_version": "none",
        },
    )
    assert state(elsewhere) is VerdictState.DONT_PAY


def verified_but_for(**sections) -> ModuleEvidence:
    """A case that would be VERIFIED: presence proven, the company and the office phone
    match (red team H1: a name alone never verifies), nothing flagged."""
    matches = {
        "status": "matches_record",
        "manager_on_record": "Fixture Living LLC",
        "office_phone_match": "yes",
    }
    return evidence(authority=matches, rules=[], price=None, **sections)


def test_recently_rented_is_information_and_holds_nothing_by_itself():
    # Ruling, Sat 01:20: lease status is something we do not know and never claim.
    assert state(verified_but_for()) is VerdictState.VERIFIED
    rented = verified_but_for(for_sale={"status": "recently_rented", "changed_on": "2026-11-01"})
    verdict = decide(to_evidence(rented))
    assert verdict.state is VerdictState.VERIFIED
    assert not any("rented" in reason for reason in verdict.reasons)

    # Lane T replaces its own line by these two labels: "For sale" and "Rental history".
    assert card_lines(rented, CardRowKind.PLACE)["Rental history"] == (
        CardTone.NOT_SHOWN,
        "Not confirmed. The record shows it was rented on 2026-11-01. "
        "Ask the manager on record if it's still available.",
    )
    undated = verified_but_for(for_sale={"status": "recently_rented"})
    tone, text = card_lines(undated, CardRowKind.PLACE)["Rental history"]
    assert tone is CardTone.NOT_SHOWN and text.startswith("Not confirmed.")
    assert "Red flag" not in text


def test_for_sale_holds_a_case_unless_the_ad_s_contact_is_the_office_on_record():
    # A named manager, presence proven, and the record shows the home for sale: held, and
    # the for-sale reason is given.
    by_name = {"status": "matches_record", "manager_on_record": "Fixture Living LLC"}
    held = evidence(authority=by_name, rules=[], price=None, for_sale={"status": "active"})
    verdict = decide(to_evidence(held))
    assert verdict.state is VerdictState.HOLD
    assert strings.text("reason.for_sale") in verdict.reasons
    # Ruling, Sat 03:36: when the ad's phone is the office's on record, the brokerage itself
    # is offering the home. For sale is then information and holds nothing.
    by_the_office = verified_but_for(for_sale={"status": "active"})
    assert to_evidence(by_the_office).for_sale_flag is False
    assert state(by_the_office) is VerdictState.VERIFIED


def test_one_matching_number_among_several_is_not_the_office_calling():
    # Review round 1, H: [OFFICE, OTHER] must not read as "the contact is the office".
    claims = ContactClaims(phones=[OFFICE, OTHER], company="Fixture Living LLC")
    authority = check_authority(claims, record(), SALT)
    assert authority.office_phone_match is PhoneMatch.NO
    mixed = evidence(
        authority=authority.model_dump(mode="json"),
        rules=[],
        price=None,
        for_sale={"status": "active"},
    )
    verdict = decide(to_evidence(mixed))
    assert verdict.state is VerdictState.HOLD
    assert strings.text("reason.for_sale") in verdict.reasons
    assert strings.text("reason.phone_flag") in verdict.reasons


def test_naming_a_listing_brokerage_on_record_matches_as_naming_the_manager_does():
    # Ruling, Sat 01:20: the manager, the leasing office and the listing brokerage on record
    # may all market a home. Lane D passes the brokerage names (D7, `ForSaleMatch.offices`).
    claims = ContactClaims(company="Fixture Realty Group")
    assert check_authority(claims, record(), SALT).status is AuthorityStatus.MISMATCH
    offices = ["Fixture Realty Group LLC", "Another Brokerage Inc"]
    assert check_authority(claims, record(), SALT, offices).status is (
        AuthorityStatus.MATCHES_RECORD
    )
    # With no manager on the record, a brokerage on record is still something to match.
    no_manager = record(manager_company=None)
    assert check_authority(claims, no_manager, SALT, offices).status is (
        AuthorityStatus.MATCHES_RECORD
    )
    assert check_authority(claims, no_manager, SALT).status is AuthorityStatus.UNKNOWN


def test_the_card_carries_the_for_sale_finding_and_its_line_together():
    modules = evidence(for_sale={"status": "active", "listed_on": "2026-10-02"})
    card = build_card(modules, checked_at=CHECKED_AT)
    assert card.for_sale.listed_on.isoformat() == "2026-10-02"
    assert "For sale" in card_lines(modules, CardRowKind.PLACE)


def test_every_a7_line_exists_in_spanish_with_its_tone_in_words():
    authority = check_authority(
        ContactClaims(phones=[OTHER], links=["fixtureliving.co"]), record(), SALT
    )
    modules = evidence(
        authority=authority.model_dump(mode="json"),
        for_sale={"status": "active"},
        price=check_price(1100, record(), beds=2, unit="999").model_dump(mode="json"),
    )
    english = build_card(modules, checked_at=CHECKED_AT)
    spanish = build_card(modules, checked_at=CHECKED_AT, lang="es")
    for en_row, es_row in zip(english.rows, spanish.rows, strict=True):
        for en_line, es_line in zip(en_row.lines, es_row.lines, strict=True):
            assert es_line.tone is en_line.tone
            assert (es_line.label, es_line.text) != (en_line.label, en_line.text)
            if es_line.tone is CardTone.RED_FLAG:
                assert es_line.text.endswith("Señal de alerta.")
            for banned in ("estafa", "seguro", "verificado"):
                assert banned not in es_line.text.lower()
    assert set(strings.TABLES["es"]) == set(strings.TABLES["en"])


def test_a_lookup_that_found_nothing_adds_nothing():
    plain, looked = evidence(), evidence(for_sale={"status": "none"})
    assert build_card(looked, checked_at=CHECKED_AT).rows == (
        build_card(plain, checked_at=CHECKED_AT).rows
    )
    assert state(looked) is state(plain)


# --- unit and beds -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "unit", "beds"),
    [
        ("Unit 204, 2 bed / 2 bath, $1,700 a month", "204", 2),
        ("Apt #4B. 4BR student housing.", "4B", 4),
        ("Sunny studio near the park, apartment 101", "101", 0),
        ("3 bedroom house, big yard", None, 3),
        ("Two rooms. Call 555-010-0142.", None, None),
        ("Suite 12 with 1 bd", "12", 1),
        ("2 bed at 12 Fixture St #305, near the park", "305", 2),
        ("Unit 4, 1 bed", "4", 1),
    ],
)
def test_unit_and_bedrooms_are_read_from_the_listing(text, unit, beds):
    assert (extract_unit(text), extract_beds(text)) == (unit, beds)
    listing = read_listing(text)
    assert (listing.unit, listing.beds) == (unit, beds)


@pytest.mark.parametrize(
    "text",
    [
        "Spacious apartment 2 bedrooms, 1 bath",
        "#1 rated community in Fixture City",
        "Studio apartment 1 block from campus",
        "Gate code #4521, ask the office",
        "Apartment 5 minutes from downtown",
        "Suite of 3 rooms; unit 2 bath remodel",
        "Call 555-010-0142 #2",
    ],
)
def test_a_number_that_counts_something_is_not_read_as_a_unit(text):
    # XO review of #87: with a unit list on record, each of these gave a false HOLD.
    assert extract_unit(text) is None
    assert check_unit(extract_unit(text), extract_beds(text), record()) is not (
        UnitStatus.NOT_ON_RECORD
    )


@pytest.mark.parametrize(
    ("unit", "beds", "expected"),
    [
        ("204", 2, UnitStatus.ON_RECORD),
        ("4b", 4, UnitStatus.ON_RECORD),
        ("#204", None, UnitStatus.ON_RECORD),
        ("999", 2, UnitStatus.NOT_ON_RECORD),
        ("204", 3, UnitStatus.BEDS_MISMATCH),
        (None, 3, UnitStatus.BEDS_MISMATCH),  # no floor plan here has three bedrooms
        (None, 2, UnitStatus.NOT_CHECKED),
        (None, None, UnitStatus.NOT_CHECKED),
    ],
)
def test_the_unit_is_looked_up_on_the_record(unit, beds, expected):
    assert check_unit(unit, beds, record()) is expected


def test_a_record_with_no_unit_list_checks_nothing():
    bare = record(units=[], floor_plan_rents=[])
    assert check_unit("999", 7, bare) is UnitStatus.NOT_CHECKED
    assert check_unit("999", 7, None) is UnitStatus.NOT_CHECKED


@pytest.mark.parametrize("unit_status", [UnitStatus.NOT_ON_RECORD, UnitStatus.BEDS_MISMATCH])
def test_a_unit_that_does_not_fit_the_record_holds_the_case(unit_status):
    price = {"status": "within_range", "listed_rent": 1700, "unit": unit_status.value}
    modules = evidence(price=price)
    assert to_evidence(modules).unit_flag is True
    assert state(modules) is VerdictState.HOLD
    tone, text = card_lines(modules, CardRowKind.PLACE)["Unit on record"]
    assert tone is CardTone.HOLD
    assert "999" not in text and "204" not in text  # the card never repeats a unit number
    assert "Unit on record" not in card_lines(modules, CardRowKind.PRICE)


# --- rent against the floor plan's own band ------------------------------------------------


@pytest.mark.parametrize(
    ("rent", "beds", "unit", "expected"),
    [
        (1700, 2, None, PriceStatus.WITHIN_RANGE),
        (1100, 2, None, PriceStatus.BELOW_RANGE),  # under 75% of the two-bed minimum, 1600
        (1100, 1, None, PriceStatus.WITHIN_RANGE),  # fine for a one-bed, whose minimum is 1200
        (1100, None, "204", PriceStatus.BELOW_RANGE),  # the unit says which floor plan it is
        (800, None, None, PriceStatus.BELOW_RANGE),  # no beds: the lowest whole-unit plan
    ],
)
def test_rent_is_compared_with_the_band_for_that_floor_plan(rent, beds, unit, expected):
    assert check_price(rent, record(), beds=beds, unit=unit).status is expected


def test_a_low_rent_is_put_as_a_percent_under_the_lowest_plan_of_that_size():
    # 1,100 against a two-bed band that starts at 1,600 is 31% under.
    result = check_price(1100, record(), beds=2)
    assert (result.status, result.compared_beds) == (PriceStatus.BELOW_RANGE, 2)
    tone, text = card_lines(evidence(price=result.model_dump(mode="json")), CardRowKind.PRICE)[
        "Rent vs record"
    ]
    assert tone is CardTone.HOLD
    assert text == ("31% under this building's lowest 2 bed on record. Ask why; discounts happen.")
    assert "1600" not in text and "1,600" not in text  # the record's own rent stays off

    studio = record(
        floor_plan_rents=[{"name": "Studio", "beds": 0, "rent_min": 1000, "rent_max": 1100}]
    )
    low = check_price(600, studio, beds=0)
    _, said = card_lines(evidence(price=low.model_dump(mode="json")), CardRowKind.PRICE)[
        "Rent vs record"
    ]
    assert said.startswith("40% under this building's lowest studio on record.")


def test_without_a_size_to_compare_the_plain_wording_is_used():
    result = check_price(800, record())  # no beds, no unit: compared with every plan
    assert (result.status, result.compared_beds) == (PriceStatus.BELOW_RANGE, None)
    _, text = card_lines(evidence(price=result.model_dump(mode="json")), CardRowKind.PRICE)[
        "Rent vs record"
    ]
    assert text == strings.text("rent.below_range")


def test_a_floor_plan_priced_by_the_bed_is_never_compared_with_a_whole_unit_rent():
    # 3,000 for four bedrooms against a per-bed band of 700 to 850 says nothing either way.
    result = check_price(3000, record(), beds=4)
    assert (result.status, result.per_bed) == (PriceStatus.NOT_CHECKED, True)
    by_unit = check_price(600, record(), unit="4B")
    assert (by_unit.status, by_unit.per_bed) == (PriceStatus.NOT_CHECKED, True)

    modules = evidence(price=result.model_dump(mode="json"))
    tone, text = card_lines(modules, CardRowKind.PRICE)["Rent vs record"]
    assert tone is CardTone.NOT_CHECKED
    assert text == "Not checked (priced per bed here, so the rent was not compared)."


def test_a_building_priced_only_by_the_bed_is_not_compared_at_all():
    plans = [{"name": "4 bed", "beds": 4, "rent_min": 700, "rent_max": 850, "per_bed": True}]
    result = check_price(700, record(floor_plan_rents=plans))
    assert (result.status, result.per_bed) == (PriceStatus.NOT_CHECKED, True)


def test_a_record_without_floor_plan_rents_is_compared_as_before():
    bare = record(floor_plan_rents=[], units=[])
    assert check_price(1300, bare).status is PriceStatus.WITHIN_RANGE
    assert check_price(800, bare).status is PriceStatus.BELOW_RANGE
    assert check_price(None, bare).status is PriceStatus.NOT_CHECKED


def test_check_price_reports_the_unit_too():
    assert check_price(1700, record(), beds=2, unit="999").unit is UnitStatus.NOT_ON_RECORD
    assert check_price(None, record(), unit="204").unit is UnitStatus.ON_RECORD


# --- wording -------------------------------------------------------------------------------


def test_every_new_line_follows_the_card_wording_rules():
    authority = check_authority(
        ContactClaims(phones=[OTHER], links=["fixtureliving.co"]), record(), SALT
    )
    modules = evidence(
        authority=authority.model_dump(mode="json"),
        for_sale={"status": "active"},
        price=check_price(3000, record(), beds=4, unit="999").model_dump(mode="json"),
    )
    card = build_card(modules, checked_at=CHECKED_AT)
    for row in card.rows:
        for item in row.lines:
            assert not any(word in item.text.lower() for word in ("safe", "verified", "scam"))
            assert "—" not in item.text
            if item.tone is CardTone.RED_FLAG:
                assert item.text.endswith("Red flag.")
            else:
                assert "red flag" not in item.text.lower()
            if item.tone is CardTone.NOT_CHECKED:
                assert item.text.startswith("Not checked")
            if item.tone is CardTone.NOT_SHOWN:
                assert item.text.startswith(("NOT SHOWN.", "Not confirmed."))
    assert card.state is VerdictState.HOLD


# --- through the agent, start to finish ----------------------------------------------------


def run(text: str, tmp_path, **module_options):
    """Read a listing and run the whole check on a record that has contact fields."""
    from snapback.agent import CaseSession, FixtureModules, PolicyChooser, Trace, run_case
    from snapback.contracts import DataSource

    # The shared fixture has a placeholder digest. Write a copy whose digest is the office's.
    for name in ("module_evidence_hold.json", "spot_ranking.json"):
        (tmp_path / name).write_text((CONTRACTS / name).read_text())
    (tmp_path / "record.json").write_text(record().model_dump_json())

    listing = read_listing(text)
    modules = FixtureModules(
        fixtures_dir=tmp_path,
        record_file="record.json",
        rules=listing.rule_hits,
        listed_rent=listing.listed_rent,
        contacts=listing.contacts,
        unit=listing.unit,
        beds=listing.beds,
        **module_options,
    )
    ticks = iter(CHECKED_AT + timedelta(seconds=n) for n in range(10_000))
    trace = Trace("fx-A7", DataSource.FIXTURE, clock=lambda: next(ticks))
    case = CaseSession("fx-A7", modules, trace)
    verdict = run_case(case, PolicyChooser(), lambda draft: "send")
    return verdict, build_card(case.evidence, checked_at=CHECKED_AT), case


def test_an_honest_listing_from_the_office_shows_matches_and_no_new_flag(tmp_path):
    text = (
        "Unit 204, 2 bed / 2 bath, $1,700 a month. Managed by Fixture Living LLC. "
        f"Call the leasing office at {OFFICE} or see www.fixtureliving.example."
    )
    verdict, card, case = run(text, tmp_path)
    flags = to_evidence(case.evidence)
    assert not any(
        (flags.phone_flag, flags.lookalike_link_flag, flags.unit_flag, flags.for_sale_flag)
    )
    person = {item.label: item for row in card.rows for item in row.lines}
    assert person["Contact on record"].tone is CardTone.OK
    assert person["Rent vs record"].tone is CardTone.OK
    assert "Link" not in person and "Unit on record" not in person
    assert person["Allowed to rent it"].tone is CardTone.NOT_SHOWN


def test_a_dressed_up_listing_is_held_with_each_reason_named_and_nothing_leaked(tmp_path):
    text = (
        "Unit 999, 2 bed, $900 a month. Managed by Fixture Living LLC. "
        f"Text me at {OTHER}. Apply at https://fixtureliving-apply.example/now"
    )
    for_sale = ForSaleMatch(status="active")
    verdict, card, case = run(text, tmp_path, for_sale=for_sale)
    assert verdict.state is VerdictState.HOLD
    for key in ("for_sale", "phone_flag", "lookalike_link", "unit_flag", "price_flag"):
        assert strings.text(f"reason.{key}") in verdict.reasons

    lines = {item.label: item for row in card.rows for item in row.lines}
    assert lines["For sale"].tone is CardTone.HOLD  # a warning, not a red flag (H5)
    assert lines["Link"].tone is CardTone.RED_FLAG
    assert lines["Contact on record"].tone is CardTone.NOT_SHOWN
    assert lines["Unit on record"].tone is CardTone.HOLD
    assert lines["Rent vs record"].tone is CardTone.HOLD

    said = " ".join([card.model_dump_json(), verdict.model_dump_json()])
    said += " ".join(event.model_dump_json() for event in case.trace.events)
    for secret in ("0177", "0142", "999", SITE, "fixtureliving-apply", phone_hash(OFFICE, SALT)):
        assert secret not in said


def test_the_shared_fixture_record_has_nothing_to_compare_so_nothing_changes(tmp_path):
    from snapback.agent import FixtureModules

    listing = read_listing(f"Managed by Somebody Else Inc. Call {OTHER}. See fixtureliving.co")
    plain = FixtureModules()
    with_claims = FixtureModules(contacts=listing.contacts)
    assert with_claims.authority("fx-1") == plain.authority("fx-1")
    assert plain.for_sale("fx-1") is None
