"""#301 (Texas records) meets #302 (public data): the Census hit gates the Houston fallback, the
two HUD lines read differently, and two copy bugs in #301's lines stay fixed."""

import pytest

from snapback.agent.intake import read_listing
from snapback.agent.join import JoinedModules
from snapback.agent.rules.contact import FIXTURE_PHONE_SALT
from snapback.contracts import (
    DataSource,
    ModuleEvidence,
    PlaceCheck,
    PriceResult,
    PriceStatus,
    PublicStatus,
    RecordLine,
)
from snapback.verdict import build_card


def lines_of(records, lang="en", **fields):
    modules = ModuleEvidence(
        case_id="fx-1", source=DataSource.FIXTURE, public_records=records, **fields
    )
    card = build_card(modules, lang=lang)
    return [ln for row in card.rows for ln in row.lines]


def line(key, source, **facts):
    return RecordLine(key=key, source=source, data_source=DataSource.FIXTURE, **facts)


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("en", "Texas Comptroller: Fixture Property Management is an active Texas company."),
        ("es", "Contralor de Texas: Fixture Property Management es una empresa activa de Texas."),
    ],
)
def test_an_active_company_with_no_year_has_no_dangling_since(lang, expected):
    record = line("comptroller_active", "Texas Comptroller", company="Fixture Property Management")
    (found,) = [ln for ln in lines_of([record], lang) if ln.source_name == "Texas Comptroller"]
    assert found.text == expected and "since" not in found.text and "desde" not in found.text


def test_an_active_company_with_a_year_still_says_since():
    record = line(
        "comptroller_active", "Texas Comptroller", company="Fixture Property Management", year=1994
    )
    (found,) = [ln for ln in lines_of([record]) if ln.source_name == "Texas Comptroller"]
    assert found.text.endswith("is an active Texas company since 1994.")


@pytest.mark.parametrize("zip_code", [None, "", "770", "7700A", "770000"])
@pytest.mark.parametrize("lang", ["en", "es"])
def test_an_address_point_with_no_valid_zip_leaves_the_zip_out(zip_code, lang):
    record = line("address_point", "City of Houston", zip_code=zip_code)
    (found,) = [ln for ln in lines_of([record], lang) if ln.source_name == "City of Houston"]
    assert "ZIP" not in found.text and "postal" not in found.text and "()" not in found.text
    assert found.text.endswith(".") and "  " not in found.text


def test_an_address_point_with_a_zip_still_names_it():
    record = line("address_point", "City of Houston", zip_code="77096")
    (found,) = [ln for ln in lines_of([record]) if ln.source_name == "City of Houston"]
    assert "(ZIP 77096)" in found.text


def test_the_two_hud_lines_have_different_labels():
    price = PriceResult(
        status=PriceStatus.BELOW_RANGE,
        listed_rent=1000,
        baseline_source="hud_safmr",
        baseline_rent=1930,
        baseline_zip="77096",
        baseline_beds=3,
    )
    manager = line("hud_manager", "HUD", company="Fixture Residential LLC")
    found = lines_of([manager], price=price)
    hud = [ln for ln in found if ln.source_name == "HUD"]
    assert len(hud) == 2
    assert {ln.label for ln in hud} == {"HUD record", "Rent vs HUD typical"}
    assert {ln.key for ln in hud} == {"label.src_hud", "label.rent_vs_record"}


class RecordingLookups:
    def __init__(self):
        self.calls = []

    def public_records(self, text, **kwargs):
        self.calls.append(kwargs)
        return []


def joined(lookups, place):
    return JoinedModules(
        stand_in=None,
        listing=read_listing("House at 14 Example Lane, Houston, TX 77096 for rent"),
        record=None,
        for_sale=None,
        salt=FIXTURE_PHONE_SALT,
        record_source=DataSource.FIXTURE,
        lookups=lookups,
        place_check=place,
    )


@pytest.mark.parametrize(
    ("status", "skips_houston"),
    [
        (PublicStatus.FOUND, True),
        (PublicStatus.NO_MATCH, False),
        (PublicStatus.NOT_CHECKED, False),
        (None, False),
    ],
)
def test_the_houston_fallback_runs_only_when_census_missed(status, skips_houston):
    place = None if status is None else PlaceCheck(status=status, source=DataSource.FIXTURE)
    lookups = RecordingLookups()
    joined(lookups, place).public_records("c")
    expected = [{"geocoder_hit": True}] if skips_houston else [{}]
    assert lookups.calls == expected


def test_the_lookup_passes_the_hit_on_to_the_registries(monkeypatch):
    from snapback.adapters import tx_records
    from snapback.agent.join import KitLookups

    seen = {}

    def fake(text, data_source, *, geocoder_hit=None):
        seen["hit"] = geocoder_hit
        return []

    monkeypatch.setattr(tx_records, "public_records", fake)
    KitLookups(DataSource.FIXTURE).public_records("x", geocoder_hit=True)
    assert seen["hit"] is True
    KitLookups(DataSource.FIXTURE).public_records("x")
    assert seen["hit"] is None
