"""Public data, item 1: HUD Small Area FMR as the rent baseline when CoStar has no rents."""

import pytest

from snapback.agent.intake import read_listing
from snapback.agent.join import JoinedModules
from snapback.agent.rules.contact import FIXTURE_PHONE_SALT
from snapback.contracts import (
    CardTone,
    DataSource,
    FloorPlanRent,
    ModuleEvidence,
    PriceStatus,
    PropertyRecord,
    VerdictState,
)
from snapback.public import hud
from snapback.verdict import build_card, decide, to_evidence

AD = "3 bed 2 bath house, ${rent} a month. 14 Example Lane, Houston, TX 77096. Call 555-0100."


def joined(rent, record=None, text=AD):
    listing = read_listing(text.format(rent=rent))
    return JoinedModules(
        stand_in=None,
        listing=listing,
        record=record,
        for_sale=None,
        salt=FIXTURE_PHONE_SALT,
        record_source=DataSource.FIXTURE,
    )


def test_the_table_has_texas_zips_by_bedroom_count():
    assert hud.typical_rent("77096", 3) == 1930
    assert hud.typical_rent("77096", 0) == 1180
    assert hud.typical_rent("78701", 2) == 2730
    assert hud.typical_rent("90210", 3) is None  # not Texas, not shipped
    assert hud.typical_rent("77096", None) is None


def test_five_or_more_bedrooms_are_compared_with_the_four_bedroom_rent():
    assert hud.typical_rent("77096", 6) == hud.typical_rent("77096", 4)


@pytest.mark.parametrize(
    ("text", "zip_code"),
    [
        ("Houston, TX 77096", "77096"),
        ("Houston, Texas 77096-1234", "77096"),
        ("Houston TX77096", None),  # no space: not read
        ("Call 77096 times", None),  # a bare 5 digit number is not a ZIP
        ("Rent $75000 deposit", None),
        ("No zip here", None),
    ],
)
def test_the_zip_is_read_only_after_the_state(text, zip_code):
    assert hud.zip_in(text) == zip_code


def test_below_sixty_percent_of_hud_is_below_range_and_names_its_source():
    price = joined(1100).price("c")  # 57% of 1930
    assert price.status is PriceStatus.BELOW_RANGE
    assert price.baseline_source == "hud_safmr"
    assert (price.baseline_rent, price.baseline_zip, price.baseline_beds) == (1930, "77096", 3)


def test_exactly_at_the_ratio_is_within_range():
    at = round(hud.below_ratio() * 1930)
    assert joined(at).price("c").status is PriceStatus.WITHIN_RANGE
    assert joined(at - 1).price("c").status is PriceStatus.BELOW_RANGE


def test_the_ratio_is_a_named_setting(monkeypatch):
    from snapback.settings import get_settings

    monkeypatch.setenv("SNAPBACK_HUD_BELOW_RATIO", "0.9")
    get_settings.cache_clear()
    try:
        assert joined(1700).price("c").status is PriceStatus.BELOW_RANGE
    finally:
        monkeypatch.delenv("SNAPBACK_HUD_BELOW_RATIO")
        get_settings.cache_clear()


def test_no_zip_or_no_beds_is_not_checked():
    assert joined(900, text="Nice house ${rent} a month, 3 bed").price("c").status is (
        PriceStatus.NOT_CHECKED
    )
    nobeds = "House for rent ${rent} a month. 14 Example Lane, Houston, TX 77096."
    assert joined(900, text=nobeds).price("c").status is PriceStatus.NOT_CHECKED


def test_costar_rents_win_over_hud():
    record = PropertyRecord(
        property_id="fx-1",
        source=DataSource.FIXTURE,
        floor_plan_rents=[FloorPlanRent(beds=3, rent_min=1000, rent_max=1200)],
    )
    price = joined(1100, record).price("c")
    assert price.status is PriceStatus.WITHIN_RANGE
    assert price.baseline_source == "costar"


def test_a_hud_flag_holds_and_never_says_dont_pay():
    price = joined(1000).price("c")
    modules = ModuleEvidence(case_id="fx-1", source=DataSource.FIXTURE, price=price)
    assert decide(to_evidence(modules)).state is VerdictState.HOLD


def test_the_card_price_line_names_the_hud_baseline_and_the_gap():
    price = joined(1000).price("c")
    modules = ModuleEvidence(case_id="fx-1", source=DataSource.FIXTURE, price=price)
    card = build_card(modules)
    lines = [ln for row in card.rows for ln in row.lines if ln.key == "label.rent_vs_record"]
    assert len(lines) == 1
    line = lines[0]
    assert line.tone is CardTone.HOLD
    assert line.source_name == "HUD"
    assert "Typical rent here (HUD, ZIP 77096, 3 bed): $1,930" in line.text
    assert "48% under" in line.text


def test_the_card_price_line_in_spanish():
    price = joined(1000).price("c")
    modules = ModuleEvidence(case_id="fx-1", source=DataSource.FIXTURE, price=price)
    card = build_card(modules, lang="es")
    line = next(ln for row in card.rows for ln in row.lines if ln.key == "label.rent_vs_record")
    assert "HUD" in line.text and "77096" in line.text and "$1,930" in line.text
