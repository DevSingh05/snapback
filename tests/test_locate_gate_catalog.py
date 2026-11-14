"""The locate gate groups twins by property, like the product, so a sister floor plan of the
claimed building is never counted as another building."""

from snapback.contracts import DataSource, PropertyRecord
from snapback.eval.locate_gate import gate_catalog, other_property_models


def record(pid: str, models: list[str]) -> PropertyRecord:
    return PropertyRecord(property_id=pid, source=DataSource.FIXTURE, model_ids=models)


def test_twins_of_one_record_share_its_property_and_unknown_twins_stand_alone():
    catalog = gate_catalog(
        ["fx-a1", "fx-a2", "fx-b", "fx-c"],
        [record("fx-P", ["fx-a1", "fx-a2", "fx-zz"]), record("fx-Q", ["fx-b"])],
    )
    assert catalog.property_of("fx-a1") == catalog.property_of("fx-a2") == "fx-P"
    assert catalog.property_of("fx-b") == "fx-Q"
    assert catalog.property_of("fx-c") == "gate-prop-fx-c"  # no record: its own property
    assert catalog.models_of("fx-P") == {"fx-a1", "fx-a2"}


def test_other_buildings_exclude_the_claimed_buildings_floor_plans():
    catalog = gate_catalog(["fx-a1", "fx-a2", "fx-b", "fx-c"], [record("fx-P", ["fx-a1", "fx-a2"])])
    assert other_property_models(catalog, ["fx-a1", "fx-a2", "fx-b", "fx-c"], "fx-a1") == [
        "fx-b",
        "fx-c",
    ]


def test_without_records_every_twin_is_its_own_property():
    catalog = gate_catalog(["fx-a1", "fx-a2"], [])
    assert catalog.property_of("fx-a1") != catalog.property_of("fx-a2")
