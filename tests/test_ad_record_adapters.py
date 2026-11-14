"""Ad vs record, step 3: lane D reads what an ad can be held to into the existing record.

Houses: floors, laundry, pool, yard, parking, pets, beds, baths and square feet from the
listing features and the photos' scene labels and keywords. Buildings: the latest property
manager start and the latest sale. Synthetic kit only (fixtures/adapters/costar-claims-kit).
"""

from datetime import date
from pathlib import Path

from snapback.adapters.costar_jsonl import load_records
from snapback.adapters.costar_residential import house_records
from snapback.agent.join import KitLookups
from snapback.contracts import DataSource

KIT = Path(__file__).resolve().parents[1] / "fixtures" / "adapters" / "costar-claims-kit"


def houses():
    return house_records(DataSource.FIXTURE, KIT)


def buildings():
    return load_records(DataSource.FIXTURE, KIT)


def test_a_house_whose_photos_and_features_say_carpet():
    home = houses()["9101"]
    assert home.floors_photos == ["carpet"]
    assert home.floor_photo_count == 2  # two photos name a floor; the bedroom shot does not
    assert home.floors_listing == ["carpet", "tile"]
    assert home.laundry_listing == ["hookup", "room"]


def test_a_house_with_a_listed_feature_set_and_no_pool_reads_no_pool():
    assert houses()["9101"].pool_on_record is False
    assert houses()["9102"].pool_on_record is True


def test_a_house_with_nothing_on_record_reads_unknown_not_no():
    home = houses()["9103"]
    assert home.pool_on_record is None
    assert home.parking_spaces is None
    assert home.pets_ok is None
    assert home.floors_photos == [] and home.floors_listing == []
    assert home.laundry_listing == []
    assert home.beds_range is None and home.sqft_range is None
    assert home.sale_history_known is False and home.last_sale is None


def test_house_numbers_pets_parking_and_yard():
    first, second = houses()["9101"], houses()["9102"]
    assert first.beds_range == (2, 2) and first.baths_range == (1.0, 2.0)
    assert first.sqft_range == (1100, 1150)
    assert first.parking_spaces == 0 and first.pets_ok is False
    assert second.parking_spaces == 2 and second.pets_ok is True
    assert second.yard_on_record is True
    assert first.yard_on_record is None  # the record never says "no yard"


def test_hardwood_laundry_machine_and_sales_history_of_a_house():
    home = houses()["9102"]
    assert home.floors_photos == ["wood"] and home.floors_listing == ["wood"]
    assert home.laundry_listing == ["machine"]
    assert home.sale_history_known is True
    assert home.last_sale == date(2021, 5, 2)
    assert houses()["9101"].last_sale == date(2026, 8, 20)


def test_building_manager_start_and_latest_sale():
    records = buildings()
    # the latest property-manager start; an owner contact is not a manager
    assert records["fx-bldg-1"].manager_since == date(2019, 3, 1)
    assert records["fx-bldg-2"].manager_since == date(2026, 6, 1)
    assert records["fx-bldg-3"].manager_since is None
    assert records["fx-bldg-1"].last_sale == date(2022, 6, 30)
    assert records["fx-bldg-2"].last_sale == date(2026, 7, 15)
    assert records["fx-bldg-3"].last_sale is None
    assert all(r.sale_history_known for r in records.values())


def test_without_a_sale_file_a_building_says_nothing_about_sales(tmp_path):
    (tmp_path / "commercial-property.jsonl").write_text(
        (KIT / "commercial-property.jsonl").read_text()
    )
    records = load_records(DataSource.FIXTURE, tmp_path)
    assert not any(r.sale_history_known for r in records.values())


def test_without_a_features_file_a_house_still_reads_its_photos(tmp_path):
    (tmp_path / "residential-listings.jsonl").write_text(
        (KIT / "residential-listings.jsonl").read_text()
    )
    home = house_records(DataSource.FIXTURE, tmp_path)["9101"]
    assert home.floors_photos == ["carpet"]
    assert home.floors_listing == [] and home.pool_on_record is None


def test_the_kit_lookups_carry_the_new_fields_to_the_join():
    lookups = KitLookups(DataSource.FIXTURE, KIT)
    assert lookups.record("9101").floors_photos == ["carpet"]
    assert lookups.record("fx-bldg-1").manager_since == date(2019, 3, 1)


def test_no_text_from_the_kit_is_kept_on_the_record():
    dumped = houses()["9101"].model_dump_json()
    for raw in ("Brown Carpet", "Granite", "Cabinetry", "Fixture Way", "example.invalid"):
        assert raw not in dumped


def test_the_selfcheck_counts_what_an_ad_can_be_held_to():
    from snapback.adapters.kit_selfcheck import ad_vs_record_counts

    counts = ad_vs_record_counts(KIT, date(2026, 11, 14))
    assert counts["houses"] == 4 and counts["houses_with_floor_photos"] == 2
    assert counts["houses_with_two_floor_photos"] == 2
    assert counts["houses_with_listing_floors"] == 2 and counts["houses_with_pool_answer"] == 2
    assert counts["listing_photos_with_room_labels"] == 8
    assert counts["buildings"] == 3 and counts["buildings_with_manager_start"] == 2
    assert counts["buildings_manager_started_in_12_months"] == 1
    assert counts["buildings_sold_in_12_months"] == 1
    assert all(isinstance(v, int) for v in counts.values())


def test_a_default_pet_flag_is_not_an_answer():
    # 9104: the flag is False but the Pet Policy only says "call for details" -> no answer
    assert houses()["9104"].pets_ok is None
    # 9101: a "No Pets Allowed" policy is the only way to read False
    assert houses()["9101"].pets_ok is False
    # 9102: the flag is True
    assert houses()["9102"].pets_ok is True


def test_a_flag_false_without_a_policy_reads_none(tmp_path):
    (tmp_path / "residential-listings.jsonl").write_text(
        (KIT / "residential-listings.jsonl").read_text()
    )
    assert house_records(DataSource.FIXTURE, tmp_path)["9101"].pets_ok is None


def test_a_community_pool_or_pool_view_is_not_this_homes_pool():
    assert houses()["9104"].pool_on_record is None  # only shared names: no answer either way


def test_other_listings_of_the_home_make_the_sale_history_not_known():
    assert houses()["9104"].sale_history_known is False
    assert houses()["9102"].sale_history_known is True


def test_rental_houses_keep_only_a_true_pet_flag(tmp_path):
    import json

    from snapback.adapters.costar_residential import rental_houses

    base = {
        "propertyId": 1, "permissionLevels": {"homes": 10}, "transactionType": 2,
        "listingStatus": 1, "forRentStatus": 1, "rentMin": 1500, "rentMax": 1500,
        "property": {"address": {"state": "TX"}}, "media": [],
    }  # fmt: skip
    rows = [
        base | {"propertyId": 1, "resoValues": {"isPetFriendly": False}},
        base | {"propertyId": 2, "resoValues": {"isPetFriendly": True}},
    ]
    (tmp_path / "residential-listings.jsonl").write_text("\n".join(map(json.dumps, rows)))
    (tmp_path / "enums.json").write_text(
        json.dumps(
            {
                "TransactionType": {"2": "ForRent"},
                "ForRentStatus": {"1": "ForRent"},
                "ListingStatus": {"1": "Active"},
            }
        )
    )
    pets = {h.property_id: h.pets_ok for h in rental_houses(DataSource.FIXTURE, tmp_path)}
    assert pets == {"1": None, "2": True}
