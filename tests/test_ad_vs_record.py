"""Ad vs record, step 2: compare what the ad claims with what CoStar's record says.

A mismatch is stated only when the record clearly says otherwise. When the record has nothing,
nothing is said. At most three notes, at most one of them a quiet confirmation. Synthetic
records only (ids start with fx-).
"""

from datetime import date

import pytest

from snapback.agent.intake.claims import extract_claims
from snapback.agent.rules.ad_vs_record import MAX_NOTES, compare_ad_to_record
from snapback.contracts import DataSource, PropertyRecord

TODAY = date(2026, 11, 14)


def record(**fields) -> PropertyRecord:
    return PropertyRecord(property_id="fx-home-1", source=DataSource.FIXTURE, **fields)


def notes(ad: str, rec: PropertyRecord | None, today: date = TODAY):
    return compare_ad_to_record(extract_claims(ad), rec, today)


def keys(ad: str, rec: PropertyRecord | None) -> list[str]:
    return [n.key for n in notes(ad, rec)]


# --- floors -----------------------------------------------------------------------------------


def test_hardwood_ad_against_photos_labelled_carpet():
    found = notes(
        "Hardwood floors throughout", record(floors_photos=["carpet"], floor_photo_count=4)
    )
    assert [(n.key, n.claim, n.record, n.matches) for n in found] == [
        ("floor_photos", "floor_wood", ["carpet"], False)
    ]


def test_one_labelled_photo_is_not_enough_to_contradict_a_floor_claim():
    assert keys("Hardwood floors", record(floors_photos=["carpet"], floor_photo_count=1)) == []


def test_listing_features_can_contradict_when_photos_cannot():
    found = notes("hardwood floors", record(floors_listing=["tile", "carpet"]))
    assert [(n.key, n.record) for n in found] == [("floor_listing", ["tile", "carpet"])]


def test_hardwood_in_either_source_is_not_a_mismatch():
    rec = record(floors_photos=["carpet"], floor_photo_count=3, floors_listing=["wood"])
    found = notes("Hardwood floors", rec)
    assert [(n.key, n.matches) for n in found] == [("floor_match", True)]


def test_each_floor_claim_is_held_to_its_own_kind():
    rec = record(floors_listing=["wood", "tile"])
    found = notes("hardwood and carpet and laminate", rec)
    assert [(n.claim, n.key) for n in found] == [
        ("floor_carpet", "floor_listing"),
        ("floor_laminate", "floor_listing"),
        ("floor_wood", "floor_match"),
    ]


def test_no_floor_words_in_the_record_means_no_line():
    assert keys("hardwood floors", record()) == []


# --- washer, pool, parking, yard, pets -------------------------------------------------------


def test_washer_claim_against_hookups_only():
    found = notes("Washer and dryer included", record(laundry_listing=["hookup", "room"]))
    assert [(n.key, n.record) for n in found] == [("wd_listing", ["hookup", "room"])]


def test_washer_claim_confirmed_by_a_machine_on_record():
    found = notes("in-unit laundry", record(laundry_listing=["machine"]))
    assert [(n.key, n.matches) for n in found] == [("wd_match", True)]


def test_pool_claim_against_listed_features_with_no_pool():
    assert keys("Private pool", record(pool_on_record=False)) == ["pool_none"]
    assert keys("Private pool", record(pool_on_record=None)) == []
    assert [(n.key, n.matches) for n in notes("Private pool", record(pool_on_record=True))] == [
        ("pool_match", True)
    ]


def test_parking_claim_against_zero_spaces_only():
    assert keys("Two car garage", record(parking_spaces=0)) == ["parking_none"]
    assert keys("Two car garage", record(parking_spaces=2)) == ["parking_match"]
    assert keys("Two car garage", record(parking_spaces=None)) == []


def test_pets_claim_against_a_no_pets_record():
    assert keys("Pet friendly", record(pets_ok=False)) == ["pets_no"]
    assert keys("Pet friendly", record(pets_ok=None)) == []


def test_a_yard_can_be_confirmed_but_never_contradicted():
    assert keys("Fenced yard", record(yard_on_record=True)) == ["yard_match"]
    assert keys("Fenced yard", record(yard_on_record=None)) == []


# --- beds, baths, square feet -----------------------------------------------------------------


def test_beds_baths_and_sqft_mismatch_only_outside_the_range_on_record():
    rec = record(beds_range=(2, 2), baths_range=(1.0, 2.0), sqft_range=(1100, 1150))
    found = {n.key: (n.ad_value, n.record_value) for n in notes("3 bed, 3 bath, 1,500 sq ft", rec)}
    assert found == {
        "beds_differ": ("3", "2"),
        "baths_differ": ("3", "1 to 2"),
        "sqft_differ": ("1,500", "1,100 to 1,150"),
    }


def test_numbers_inside_the_tolerance_are_not_mismatches():
    rec = record(beds_range=(3, 3), baths_range=(2.0, 2.0), sqft_range=(1400, 1400))
    assert keys("3 bed, 2.5 bath, 1,450 sq ft", rec) == ["beds_match"]


# --- pretext ----------------------------------------------------------------------------------


def test_new_management_against_the_same_manager_for_years():
    found = notes("Now under new management!", record(manager_since=date(2019, 3, 1)))
    assert [(n.key, n.year, n.matches) for n in found] == [("manager_same", 2019, False)]


def test_new_management_confirmed_by_a_recent_start():
    found = notes("under new management", record(manager_since=date(2026, 6, 1)))
    assert [(n.key, n.year, n.matches) for n in found] == [("manager_new", 2026, True)]


def test_new_management_with_no_manager_on_record_says_nothing():
    assert keys("under new management", record()) == []


def test_just_sold_against_no_sale_in_twelve_months():
    rec = record(sale_history_known=True, last_sale=None)
    assert keys("The house just sold", rec) == ["sale_none"]
    older = record(sale_history_known=True, last_sale=date(2021, 5, 2))
    found = notes("The house just sold", older)
    assert [(n.key, n.year) for n in found] == [("sale_older", 2021)]


def test_just_sold_confirmed_by_a_sale_in_the_last_year():
    rec = record(sale_history_known=True, last_sale=date(2026, 8, 20))
    found = notes("recently sold", rec)
    assert [(n.key, n.matches) for n in found] == [("sale_recent", True)]


def test_a_record_that_does_not_cover_sales_says_nothing_about_a_sale():
    assert keys("just sold", record(sale_history_known=False)) == []


def test_just_sold_and_new_ownership_make_one_line():
    rec = record(sale_history_known=True)
    assert keys("just sold, under new ownership", rec) == ["sale_none"]


def test_new_ownership_has_its_own_claim_wording():
    found = notes("Under new ownership", record(sale_history_known=True))
    assert [(n.key, n.claim) for n in found] == [("sale_none", "new_ownership")]


def test_cant_show_with_an_office_on_record_points_to_the_office():
    rec = record(website_host="fx-oak.example")
    found = notes("Owner is out of town, so I can't show it", rec)
    assert [(n.key, n.matches) for n in found] == [("office_listed", False)]


def test_cant_show_with_no_office_on_record_says_nothing():
    assert keys("I can't show it", record()) == []


# --- the limits -------------------------------------------------------------------------------


def test_nothing_without_claims_or_without_a_record():
    assert notes("Nice home", record(floors_listing=["carpet"])) == []
    assert notes("hardwood floors", None) == []


def test_at_most_three_notes_and_pretext_comes_first():
    rec = record(
        floors_listing=["carpet"],
        laundry_listing=["hookup"],
        pool_on_record=False,
        parking_spaces=0,
        pets_ok=False,
        manager_since=date(2018, 1, 1),
    )
    ad = "New management! hardwood floors, washer and dryer, pool, garage, pet friendly"
    found = notes(ad, rec)
    assert len(found) == MAX_NOTES == 3
    assert found[0].key == "manager_same"


def test_one_quiet_confirmation_at_most_and_only_after_the_mismatches():
    rec = record(floors_listing=["wood"], pool_on_record=True, yard_on_record=True, pets_ok=True)
    found = notes("hardwood floors, pool, fenced yard, pets allowed", rec)
    assert len(found) == 1 and found[0].matches
    mixed = record(floors_listing=["carpet"], pool_on_record=True, pets_ok=True)
    found = notes("hardwood floors, pool, pets allowed", mixed)
    assert [(n.key, n.matches) for n in found] == [("floor_listing", False), ("pool_match", True)]


@pytest.mark.parametrize(
    "ad",
    [
        "No carpet, all hardwood",
        "Not pet friendly",
        "carpet-free",
    ],
)
def test_a_denied_claim_is_never_compared(ad):
    rec = record(floors_listing=["carpet"], pets_ok=True)
    assert all(n.claim not in ("floor_carpet", "pets") for n in notes(ad, rec))


# --- buildings' parking, and the aerial date --------------------------------------------------


def test_a_building_with_a_parking_ratio_can_confirm_a_parking_claim_never_contradict_it():
    found = notes("Garage parking included", record(parking_ratio=1.5))
    assert [(n.key, n.matches, n.record_value) for n in found] == [
        ("parking_ratio_match", True, "1.5")
    ]
    assert keys("Covered carport", record(parking_ratio=None)) == []


def test_a_home_count_beats_a_building_ratio():
    assert keys("garage", record(parking_spaces=0, parking_ratio=1.5)) == ["parking_none"]


AERIAL = date(2025, 3, 14)


def aerial(ad: str, rec: PropertyRecord | None):
    return compare_ad_to_record(extract_claims(ad), rec, TODAY, aerial_on=AERIAL)


def test_the_aerial_date_follows_an_exterior_claim_and_says_nothing_about_it():
    found = aerial("Private pool", record(pool_on_record=False))
    assert [(n.key, n.ad_value, n.matches) for n in found] == [
        ("pool_none", None, False),
        ("aerial_date", "2025-03-14", False),
    ]


def test_no_aerial_line_without_an_exterior_claim_or_a_date():
    assert aerial("Hardwood floors", record(floors_listing=["carpet"]))[-1].key != "aerial_date"
    assert aerial("Nice home", record(pool_on_record=False)) == []
    only_aerial = compare_ad_to_record(
        extract_claims("Private pool"), record(pool_on_record=False), TODAY
    )
    assert [n.key for n in only_aerial] == ["pool_none"]


def test_the_aerial_line_is_not_a_confirmation_and_needs_room_under_the_cap():
    full = record(pool_on_record=False, parking_spaces=0, pets_ok=False)
    found = aerial("pool, garage, pets allowed", full)
    assert [n.key for n in found] == ["pool_none", "parking_none", "pets_no"]
    both = aerial("pool, fenced yard", record(pool_on_record=False, yard_on_record=True))
    assert [n.key for n in both] == ["pool_none", "yard_match", "aerial_date"]
    assert sum(n.matches for n in both) == 1
