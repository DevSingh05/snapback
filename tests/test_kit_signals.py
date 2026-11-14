"""D7 kit signals: for-sale lookup, unit list, per-bed rent bands, office phone hash, site."""

from datetime import date

from snapback.adapters.costar_jsonl import load_records
from snapback.adapters.costar_residential import for_sale_lookup, normalize_address
from snapback.agent.rules.contact import phone_hash, phone_salt
from snapback.contracts import DataSource, ForSaleStatus

TODAY = date(2026, 11, 14)


def _rec():
    return load_records(DataSource.FIXTURE)["fx-prop-4"]


def test_office_phone_is_kept_only_as_the_shared_keyed_hash():
    rec = _rec()
    assert rec.site_phone_hash == phone_hash("5550100123", phone_salt())
    assert "0123" not in rec.model_dump_json()


def test_website_is_the_host_only_lowercase_without_www():
    assert _rec().website_host == "fixtureliving.example"


def test_floor_plan_rents_flag_per_bed_plans():
    bands = {b.name: b for b in _rec().floor_plan_rents}
    assert bands["1 bed / 1 bath"].per_bed is False
    assert bands["4 bed / 4 bath"].per_bed is True
    assert (bands["4 bed / 4 bath"].rent_min, bands["4 bed / 4 bath"].beds) == (700, 4)


def test_per_bed_prices_never_enter_the_building_rent_range():
    rec = _rec()
    assert (rec.rent_min, rec.rent_max) == (1200, 1900)
    assert rec.rent_median == 1525  # midpoints 1300 and 1750, the per-bed plan left out


def test_unit_list_has_every_named_unit_and_its_beds():
    units = {u.unit: u for u in _rec().units}
    assert set(units) == {"101", "204", "4B"}  # a unit with no number is skipped
    assert units["204"].floor_plan == "2 bed / 2 bath"  # derived from beds and baths
    assert units["4B"].beds == 4


def test_active_for_sale_home_posted_as_a_rental_is_found():
    match = for_sale_lookup(
        "Cozy 2BR for rent at 100 Fixture Ln Apt 2!", DataSource.FIXTURE, today=TODAY
    )
    assert match is not None
    assert match.status is ForSaleStatus.ACTIVE
    assert match.site == "Homes.com"
    assert match.listed_on == date(2026, 10, 2)


def test_recently_rented_home_is_reported_with_its_date():
    match = for_sale_lookup("200 sample st, available now", DataSource.FIXTURE, today=TODAY)
    assert match is not None
    assert match.status is ForSaleStatus.RECENTLY_RENTED
    assert match.changed_on == date(2026, 10, 20)


def test_sold_or_long_ago_rented_homes_are_none():
    for text in ("300 Example Avenue", "400 Test Road"):
        match = for_sale_lookup(text, DataSource.FIXTURE, today=TODAY)
        assert match is not None and match.status is ForSaleStatus.NONE


def test_a_different_unit_in_the_same_building_does_not_match():
    match = for_sale_lookup("100 Fixture Lane Unit 7", DataSource.FIXTURE, today=TODAY)
    assert match is not None and match.status is ForSaleStatus.NONE


def test_no_address_in_the_text_is_none_status_not_a_crash():
    match = for_sale_lookup("great place, zelle me", DataSource.FIXTURE, today=TODAY)
    assert match is not None and match.status is ForSaleStatus.NONE


def test_no_residential_file_means_not_looked_up(tmp_path):
    kit = tmp_path / "kit"
    kit.mkdir()
    assert for_sale_lookup("100 Fixture Lane", DataSource.LIVE, kit_dir=kit, today=TODAY) is None


def test_address_normalisation_folds_suffixes_and_units():
    assert normalize_address("100 Fixture Ln., Apt #2") == normalize_address(
        "100 fixture lane unit 2"
    )


def test_coverage_counts_residential_paths_and_codes_without_values():
    import json

    from snapback.adapters.costar_jsonl import FIXTURE_KIT, coverage
    from snapback.adapters.costar_residential import coverage_residential

    report = coverage(FIXTURE_KIT) | coverage_residential(FIXTURE_KIT)
    assert report["residential_records"] == 4
    assert report["residential_fields"]["street"]["address.streetAddress"] == 4
    assert report["rent_pricing_codes"] == {"1": 2, "2": 1}
    text = json.dumps(report)
    assert "Fixture" not in text and "fx-" not in text and "2026" not in text


def test_listing_offices_on_record_are_companies_only():
    match = for_sale_lookup("100 Fixture Lane Apt 2", DataSource.FIXTURE, today=TODAY)
    assert match is not None
    assert match.offices == ["Fixture Realty Group", "Sample Homes Brokerage"]
    assert "Fx Agent Person" not in match.model_dump_json()  # agents are people: never exposed


def test_no_match_lists_no_offices():
    match = for_sale_lookup("somewhere else entirely", DataSource.FIXTURE, today=TODAY)
    assert match is not None and match.offices == []
