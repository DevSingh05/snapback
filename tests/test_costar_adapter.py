"""D1: CoStar JSONL adapter. Fixture and live run the same parser; live needs the kit in data/."""

import json
from pathlib import Path

import pytest

from snapback.adapters import costar_jsonl
from snapback.adapters.costar_jsonl import KitNotFoundError, coverage, load_records
from snapback.contracts import DataSource, PropertyRecord

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "fixtures" / "contracts" / "property_record.json"


def test_fixture_record_parses_with_missing_fields():
    records = load_records(DataSource.FIXTURE)
    sparse = records["fx-prop-2"]
    # Omitted fields and enum 0 both mean unknown, never zero or "no".
    assert sparse.source == DataSource.FIXTURE
    assert sparse.property_type is None
    assert sparse.year_built is None
    assert sparse.floors is None
    assert sparse.lat is None and sparse.lon is None
    assert sparse.model_ids == [] and sparse.floor_plans == []
    assert sparse.manager_company is None
    assert sparse.rent_min is None and sparse.rent_median is None and sparse.rent_max is None


def test_live_mode_without_kit_fails_with_a_clear_message(tmp_path):
    with pytest.raises(KitNotFoundError) as err:
        load_records(DataSource.LIVE, kit_dir=tmp_path / "no-kit-here")
    message = str(err.value)
    assert "commercial-property.jsonl" in message
    assert "no-kit-here" in message
    assert "README" in message


def test_fixture_matches_the_shared_property_record_contract():
    expected = PropertyRecord.model_validate(json.loads(CONTRACT.read_text(encoding="utf-8")))
    d7 = {"site_phone_hash", "website_host", "floor_plan_rents", "units"}  # D7 fields, tested below
    got = load_records(DataSource.FIXTURE)["fx-prop-1"]
    assert got.model_dump(exclude=d7) == expected.model_dump(exclude=d7)


def test_only_matterport_attachment_types_count_and_ids_are_deduplicated():
    records = load_records(DataSource.FIXTURE)
    assert records["fx-prop-1"].model_ids == ["fx-model-a", "fx-model-b"]
    assert records["fx-prop-3"].model_ids == ["fx-model-c"]


def test_rent_range_and_manager_company_come_from_the_apartment_listing():
    rec = load_records(DataSource.FIXTURE)["fx-prop-3"]
    assert rec.manager_company == "Fixture Property Management Co"
    assert (rec.rent_min, rec.rent_max) == (1400, 2600)
    # Median of the per-floor-plan midpoints 1500, 1800, 2450.
    assert rec.rent_median == 1800
    assert rec.floor_plans == ["studio / 1 bath", "1 bed / 1 bath", "2 bed / 2 bath"]
    assert rec.property_type == "multifamily"
    assert rec.market == "Fixture Town"


def test_live_mode_reads_a_kit_dir_and_labels_records_live(tmp_path):
    kit = tmp_path / "kit"
    (kit / "data").mkdir(parents=True)
    line = {
        "propertyId": "fx-live-1",
        "propertyType": 11,
        "constructionEvents": [{"eventType": 2, "year": 2001}],
    }
    (kit / "data" / "commercial-property.jsonl").write_text(json.dumps(line) + "\n\n{broken\n")
    records = load_records(DataSource.LIVE, kit_dir=kit)
    assert list(records) == ["fx-live-1"]
    assert records["fx-live-1"].source == DataSource.LIVE
    assert records["fx-live-1"].year_built == 2001


def test_default_source_comes_from_settings(monkeypatch):
    monkeypatch.setenv("SNAPBACK_DATA_SOURCE", "fixture")
    costar_jsonl.get_settings.cache_clear()
    try:
        assert load_records()["fx-prop-1"].source == DataSource.FIXTURE
    finally:
        costar_jsonl.get_settings.cache_clear()


def test_coverage_reports_counts_and_field_paths_only():
    report = coverage(costar_jsonl.FIXTURE_KIT)
    assert report["records"] == 5
    assert report["year_built_events"] == 2  # fx-prop-1 and -4; the year-0 record does not count
    text = json.dumps(report)
    assert "fx-" not in text and "Fixture" not in text  # no ids or values, safe to paste


def test_year_built_is_the_earliest_construction_complete_event():
    records = load_records(DataSource.FIXTURE)
    # fx-prop-1: eventType 1 in 2010 is ignored; eventType 2 in 2015 and 2018 -> 2015
    assert records["fx-prop-1"].year_built == 2015
    # fx-prop-3: no construction event; the apartment listing's yearBuilt is the fallback
    assert records["fx-prop-3"].year_built == 1998
    # fx-prop-2: a year of 0 is unknown
    assert records["fx-prop-2"].year_built is None


def test_a_units_own_beds_win_over_its_model():
    units = {u.unit: u for u in load_records(DataSource.FIXTURE)["fx-prop-4"].units}
    assert units["206"].beds == 3  # listed under the 2-bed model, but the unit says 3
    assert units["204"].beds == 2  # no beds of its own: the model's


def test_coverage_counts_model_and_unit_fields():
    report = coverage(costar_jsonl.FIXTURE_KIT)
    assert report["model_fields"]["numBeds"] > 0 and report["model_fields"]["numBaths"] > 0
    assert report["unit_fields"]["unitNumber"] > 0 and report["unit_fields"]["numBeds"] > 0
