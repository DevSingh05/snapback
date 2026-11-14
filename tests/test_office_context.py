"""The ad as the office sees it, and the record fields behind it."""

from snapback.adapters.costar_jsonl import parse_record
from snapback.agent.intake import read_listing
from snapback.contracts import DataSource, PropertyRecord
from snapback.office.context import listing_context


def test_the_building_comes_from_the_record_and_the_rest_from_the_ad():
    record = PropertyRecord(
        property_id="p1",
        source=DataSource.FIXTURE,
        building_name="Fixture Lofts",
        street_address="100 Fixture Way, Fixture City, TX 00000",
    )
    listing = read_listing("Apt 5B $1,200 a month, managed by Fixture Living LLC, jo@x.example")
    context = listing_context(record, listing)
    assert context.building == "Fixture Lofts"
    assert context.address == "100 Fixture Way, Fixture City, TX 00000"
    assert (context.unit, context.rent, context.poster) == ("5B", 1200, "Fixture Living LLC")
    assert context.emails == ["jo@x.example"]


def test_control_characters_and_long_text_are_cut():
    record = PropertyRecord(
        property_id="p1",
        source=DataSource.FIXTURE,
        building_name="Lofts\r\nBcc: x@evil.example" + "x" * 500,
    )
    context = listing_context(record, None)
    assert "\n" not in context.building and "\r" not in context.building
    assert len(context.building) <= 120
    assert listing_context(None, None).building is None


def test_the_adapter_reads_the_building_name_and_address():
    raw = {
        "propertyId": "p1",
        "buildingName": "  Fixture   Lofts ",
        "primaryAddress": {
            "streetNumber": 100,
            "streetName": "Fixture",
            "streetType": "Way",
            "city": "Fixture City",
            "state": "TX",
            "postcode": "00000",
        },
    }
    record = parse_record(raw, DataSource.FIXTURE)
    assert record.building_name == "Fixture Lofts"
    assert record.street_address == "100 Fixture Way, Fixture City, TX 00000"
    bare = parse_record({"propertyId": "p2"}, DataSource.FIXTURE)
    assert bare.building_name is None and bare.street_address is None
