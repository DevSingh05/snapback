"""Public data, items 2 and 4: Census address check and RDAP domain age. No network: every
answer is a recording in fixtures/public/recorded.json or a stub."""

from datetime import date

import pytest

from snapback.agent.intake import read_listing
from snapback.agent.join import JoinedModules, KitLookups, public_checks_of
from snapback.agent.rules.contact import FIXTURE_PHONE_SALT
from snapback.contracts import (
    CardTone,
    DataSource,
    ModuleEvidence,
    PlaceCheck,
    PriceStatus,
    PublicStatus,
    RuleCategory,
    VerdictState,
)
from snapback.public import census, rdap
from snapback.public.fetch import LiveFetcher, RecordedFetcher
from snapback.verdict import build_card, decide, to_evidence

TODAY = date(2026, 11, 14)


class Down:
    """A service that times out or errors: every answer is None."""

    source = DataSource.LIVE

    def get(self, kind, key, url, timeout):
        return None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Cute home at 14 Example Lane, Houston, TX 77096. Call 555-0100",
            "14 Example Lane, Houston, TX 77096",
        ),
        ("house at 14 Example Ln Houston Texas", "14 Example Ln, Houston, TX"),
        ("2 bed on Example Lane, TX 77096", None),  # no house number
        ("14 Example Lane Houston", None),  # no state
        ("Rent $1,400 a month, TX", None),
    ],
)
def test_the_address_is_read_from_the_ad_with_its_state(text, expected):
    assert census.address_in(text) == expected


def test_a_match_gives_the_zip_and_county():
    found = census.check("14 Example Lane, Houston, TX 77096", RecordedFetcher())
    assert found.status is PublicStatus.FOUND
    assert (found.zip, found.county_fips, found.county) == ("77096", "48201", "Harris")
    assert found.source is DataSource.FIXTURE


def test_no_match_is_an_answer_and_not_a_failure():
    found = census.check("9 Nowhere Court, Houston, TX 77096", RecordedFetcher())
    assert found.status is PublicStatus.NO_MATCH and found.zip is None


def test_a_failed_lookup_is_not_checked():
    assert census.check("14 Example Lane, Houston, TX", Down()).status is PublicStatus.NOT_CHECKED
    assert census.check("1 Unrecorded Way, TX", RecordedFetcher()).status is (
        PublicStatus.NOT_CHECKED
    )


def test_a_garbled_body_is_not_checked():
    class Odd:
        source = DataSource.LIVE

        def get(self, kind, key, url, timeout):
            return {"result": "oops"}

    assert census.check("14 Example Lane, TX", Odd()).status is PublicStatus.NOT_CHECKED


def test_the_live_fetcher_never_raises_on_a_dead_host():
    assert LiveFetcher().get("census", "k", "http://127.0.0.1:9/none", 0.2) is None


def test_the_request_is_the_public_geocoder_with_no_key():
    seen = {}

    class Spy:
        source = DataSource.LIVE

        def get(self, kind, key, url, timeout):
            seen.update(url=url, timeout=timeout)

    census.check("14 Example Lane, Houston, TX 77096", Spy(), timeout=2.0)
    assert seen["url"].startswith("https://geocoding.geo.census.gov/geocoder/geographies/")
    assert "key=" not in seen["url"] and seen["timeout"] == 2.0


# --- RDAP -----------------------------------------------------------------------------------


def test_the_link_domain_skips_platforms_and_reads_the_posters_own():
    text = "Pay at https://www.new-lease-portal.example/pay or see https://craigslist.org/x"
    assert rdap.link_host(text) == "new-lease-portal.example"
    assert rdap.link_host("Apply on https://forms.gle/abc and https://zillow.com/h/1") is None
    assert rdap.link_host("no link") is None
    assert rdap.link_host("see https://shop.example.co.uk/a") == "example.co.uk"


def test_a_domain_five_days_old_is_new_and_holds():
    found = rdap.check("new-lease-portal.example", RecordedFetcher(), today=TODAY)
    assert found.status is PublicStatus.FOUND and found.age_days == 5
    hit = rdap.rule_hit(found, 30)
    assert hit is not None
    assert (hit.rule_id, hit.category, hit.red_flag) == ("link.new_domain", RuleCategory.LINK, True)


def test_an_old_domain_is_no_hit():
    found = rdap.check("old-property-co.example", RecordedFetcher(), today=TODAY)
    assert found.age_days > 5000 and rdap.rule_hit(found, 30) is None


def test_the_edge_is_the_named_number_of_days():
    found = rdap.check("new-lease-portal.example", RecordedFetcher(), today=TODAY)
    assert rdap.rule_hit(found, 5) is None and rdap.rule_hit(found, 6) is not None


@pytest.mark.parametrize("host", ["no-date.example", "unrecorded.example"])
def test_no_date_or_no_answer_is_not_checked_and_never_a_flag(host):
    found = rdap.check(host, RecordedFetcher(), today=TODAY)
    assert found.status is PublicStatus.NOT_CHECKED and rdap.rule_hit(found, 30) is None
    assert rdap.rule_hit(rdap.check(host, Down(), today=TODAY), 30) is None


# --- the join and the card ------------------------------------------------------------------


AD = (
    "3 bed house, $1,100 a month. 14 Example Lane, Houston, TX 77096. "
    "Pay the deposit at https://new-lease-portal.example/pay. Call 555-0100."
)


def lookups():
    return KitLookups(DataSource.FIXTURE)


def joined(text=AD, **checks):
    return JoinedModules(
        stand_in=None,
        listing=read_listing(text),
        record=None,
        for_sale=None,
        salt=FIXTURE_PHONE_SALT,
        record_source=DataSource.FIXTURE,
        **checks,
    )


def card_lines(modules, label_key, lang="en"):
    card = build_card(modules, lang=lang)
    return [ln for row in card.rows for ln in row.lines if ln.key == label_key]


def test_a_fixture_run_reads_the_recordings_for_the_ads_address_and_link(monkeypatch):
    place, domain = public_checks_of(lookups(), AD)
    assert place.status is PublicStatus.FOUND and place.source is DataSource.FIXTURE
    assert domain.host == "new-lease-portal.example" and domain.status is PublicStatus.FOUND


def test_a_fixture_run_with_no_recording_looks_nothing_up():
    ad = "House at 1 Unrecorded Way, Houston, TX 77096, see https://unrecorded.example/x"
    assert public_checks_of(lookups(), ad) == (None, None)
    assert public_checks_of(lookups(), "no address and no link here") == (None, None)


def test_the_flags_turn_the_lookups_off(monkeypatch):
    from snapback.settings import get_settings

    monkeypatch.setenv("SNAPBACK_CENSUS_GEOCODER", "false")
    monkeypatch.setenv("SNAPBACK_RDAP", "false")
    get_settings.cache_clear()
    try:
        assert public_checks_of(lookups(), AD) == (None, None)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_a_broken_lookup_is_not_looked_up():
    class Broken:
        def place_check(self, text):
            raise RuntimeError("boom")

    assert public_checks_of(Broken(), AD) == (None, None)


def test_a_new_domain_in_the_ad_adds_the_rule_hit_and_holds_the_case():
    _, domain = public_checks_of(lookups(), AD)
    domain = domain.model_copy(update={"age_days": 5})
    rules = joined(domain_check=domain).rules("c")
    assert [h.rule_id for h in rules].count("link.new_domain") == 1
    modules = ModuleEvidence(
        case_id="fx-1", source=DataSource.FIXTURE, rules=rules, domain_check=domain
    )
    assert decide(to_evidence(modules)).state is VerdictState.HOLD
    new = [ln for row in build_card(modules).rows for ln in row.lines if ln.source_name == "RDAP"]
    assert len(new) == 1 and new[0].tone is CardTone.RED_FLAG


def test_an_old_domain_or_an_unchecked_one_adds_no_hit():
    old = rdap.check("old-property-co.example", RecordedFetcher(), today=TODAY)
    assert joined(domain_check=old).rules("c") == joined().rules("c")
    unchecked = old.model_copy(update={"status": PublicStatus.NOT_CHECKED, "age_days": None})
    assert joined(domain_check=unchecked).rules("c") == joined().rules("c")


def test_the_census_zip_feeds_the_hud_baseline_when_the_ad_has_no_zip():
    ad = "3 bed house, $1,000 a month, 14 Example Lane, Houston, TX."
    assert joined(ad).price("c").status is PriceStatus.NOT_CHECKED
    place = PlaceCheck(status=PublicStatus.FOUND, zip="77096", source=DataSource.FIXTURE)
    price = joined(ad, place_check=place).price("c")
    assert price.status is PriceStatus.BELOW_RANGE and price.baseline_zip == "77096"


@pytest.mark.parametrize(
    ("status", "tone", "words"),
    [
        (PublicStatus.FOUND, CardTone.OK, "Harris County, ZIP 77096"),
        (PublicStatus.NO_MATCH, CardTone.NOT_CHECKED, "no match"),
        (PublicStatus.NOT_CHECKED, CardTone.NOT_CHECKED, "Not checked"),
    ],
)
def test_the_card_names_census_and_never_flags_a_miss(status, tone, words):
    place = PlaceCheck(
        status=status,
        zip="77096" if status is PublicStatus.FOUND else None,
        county="Harris" if status is PublicStatus.FOUND else None,
        source=DataSource.FIXTURE,
    )
    modules = ModuleEvidence(case_id="fx-1", source=DataSource.FIXTURE, place_check=place)
    (line,) = card_lines(modules, "label.address")
    assert line.source_name == "Census" and line.tone is tone and words in line.text
    assert line.source is DataSource.FIXTURE
    assert (
        decide(to_evidence(modules)).state
        is decide(to_evidence(modules.model_copy(update={"place_check": None}))).state
    )


def test_an_old_domain_line_reads_info_only_in_both_languages():
    found = rdap.check("old-property-co.example", RecordedFetcher(), today=TODAY)
    modules = ModuleEvidence(case_id="fx-1", source=DataSource.FIXTURE, domain_check=found)
    for lang in ("en", "es"):
        (line,) = card_lines(modules, "label.link_domain", lang)
        assert line.source_name == "RDAP" and line.tone is CardTone.NOT_CHECKED
        assert "17" in line.text


# --- every line names its source, in the card, the timeline and the report ------------------


def _evidence_with_public_data():
    from snapback.contracts import PriceResult

    place = PlaceCheck(
        status=PublicStatus.FOUND, zip="77096", county="Harris", source=DataSource.FIXTURE
    )
    domain = rdap.check("old-property-co.example", RecordedFetcher(), today=TODAY)
    price = PriceResult(
        status=PriceStatus.BELOW_RANGE,
        listed_rent=1000,
        baseline_source="hud_safmr",
        baseline_rent=1930,
        baseline_zip="77096",
        baseline_beds=3,
    )
    return ModuleEvidence(
        case_id="fx-1",
        source=DataSource.FIXTURE,
        price=price,
        place_check=place,
        domain_check=domain,
    )


def test_the_report_names_every_source_and_copies_only_the_public_lines():
    from snapback.api.report import build_report

    modules = _evidence_with_public_data()
    card = build_card(modules)
    report = build_report(modules, card, case_id="7Q2M", lang="en", aerial=False)
    assert {"HUD", "Census", "RDAP"} <= set(report.source_names)
    assert {s.source_name for s in report.sources} == {"HUD", "Census", "RDAP"}
    assert all(s.data_source is DataSource.FIXTURE for s in report.sources)


def test_the_timeline_steps_carry_the_source_name():
    from snapback.agent.timeline import _Builder

    builder = _Builder(DataSource.FIXTURE, _evidence_with_public_data(), "en")
    builder.record_lines(0)
    names = {step["source_name"] for step in builder.steps}
    assert {"HUD", "Census", "RDAP"} <= names
    assert all(step["result"] for step in builder.steps)
