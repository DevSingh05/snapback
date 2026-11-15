"""The live demo case helper (snapback.eval.demo_case): the pick, the renders, the browser lines."""

import io
import json

from PIL import Image

from snapback.adapters.matterport import FixtureMatterport
from snapback.contracts import DataSource, PropertyRecord
from snapback.eval.demo_case import READ_TOKEN_PREFIX, browser_lines, pick_building, render_rooms


def record(pid, models, kind="multifamily", rent=1500):
    return PropertyRecord(
        property_id=pid,
        source=DataSource.LIVE,
        property_type=kind,
        model_ids=models,
        rent_median=rent,
    )


ROOMS = {
    "m-few": {"s1": "Kitchen", "s2": "Bedroom"},
    "m-many": {"s1": "Kitchen", "s2": "Bedroom", "s3": "Bathroom", "s4": "Living Room"},
    "m-house": {"s1": "Kitchen", "s2": "Bedroom", "s3": "Bathroom", "s4": "Office", "s5": "Den"},
    "m-unindexed": {"s1": "Kitchen", "s2": "Bedroom", "s3": "Bathroom", "s4": "Hall", "s5": "Den"},
}


def test_the_pick_is_the_indexed_rental_with_the_most_room_kinds():
    records = [
        record("p1", ["m-few"]),
        record("p2", ["m-many", "m-unindexed"]),
        record("p3", ["m-house"], kind="house"),  # not a rental building
        record("p4", ["m-unindexed"]),  # nothing indexed
        record("p5", ["m-many"], rent=None),  # no rents on record
    ]
    indexed = {"m-few", "m-many", "m-house"}
    pick = pick_building(records, indexed, lambda m: ROOMS.get(m, {}))
    assert (pick.property_id, pick.model_id, pick.room_kinds) == ("p2", "m-many", 4)
    assert pick_building(records, set(), lambda m: ROOMS.get(m, {})) is None


def test_a_building_with_one_indexed_scan_beats_one_with_two():
    """With two indexed scans a view can match the sibling, and the walk shows it on no stop."""
    rooms = dict(
        ROOMS,
        **{"m-twin": {"s1": "Kitchen", "s2": "Bedroom", "s3": "Hall", "s4": "Den", "s5": "Office"}},
    )
    records = [record("p-two", ["m-many", "m-twin"]), record("p-one", ["m-few"])]
    pick = pick_building(records, {"m-many", "m-twin", "m-few"}, lambda m: rooms.get(m, {}))
    assert (pick.property_id, pick.model_id) == ("p-one", "m-few")


def test_one_jpeg_per_labelled_room_in_the_asked_order(tmp_path):
    sweeps = FixtureMatterport(tmp_path).sweeps("fx-model-a")
    rooms = {sweeps[0].sweep_id: "Bedroom", sweeps[1].sweep_id: "Kitchen"}
    out = render_rooms(sweeps, rooms, ["Kitchen", "Living Room", "Bedroom"], seed=3)
    assert [room for room, _ in out] == ["Kitchen", "Bedroom"]  # no Living Room in this scan
    for _, data in out:
        with Image.open(io.BytesIO(data)) as image:
            assert image.format == "JPEG" and image.size == (1024, 768)


def test_the_browser_lines_keep_the_token_out_of_the_address():
    lines = browser_lines("http://localhost:5173/", "prop-9", "ab12", "tok-xyz")
    assert lines[0] == "Open: http://localhost:5173/tour/prop-9?case=ab12"
    assert "tok-xyz" not in lines[0]
    assert json.dumps(READ_TOKEN_PREFIX + "AB12") in lines[2] and '"tok-xyz"' in lines[2]


def test_the_browser_address_names_the_building_the_shown_case_was_made_for():
    """#247 review: try 1 makes a case for A (not full), try 2 skips B (no views). The address
    must pair A with A's case, never B with A's case."""
    from snapback.eval.demo_case import Pick, Tried, first_full_walk

    a, b = Pick("pA", "mA", 4), Pick("pB", "mB", 3)
    made = {"pA": Tried({"case_id": "C-FOR-pA"}, sent=4, on_walk=3)}
    shown = first_full_walk([a, b], 3, lambda pick: made.get(pick.property_id))
    assert shown is not None
    pick, tried = shown
    assert (pick.property_id, tried.case["case_id"]) == ("pA", "C-FOR-pA")


def test_the_first_full_walk_wins_and_no_case_means_none():
    from snapback.eval.demo_case import Pick, Tried, first_full_walk

    a, b, c = Pick("pA", "mA", 4), Pick("pB", "mB", 3), Pick("pC", "mC", 2)
    made = {
        "pA": Tried({"case_id": "A"}, 4, 3),
        "pB": Tried({"case_id": "B"}, 4, 4),
        "pC": Tried({"case_id": "C"}, 4, 4),
    }
    calls = []

    def attempt(pick):
        calls.append(pick.property_id)
        return made[pick.property_id]

    pick, tried = first_full_walk([a, b, c], 3, attempt)
    assert (pick.property_id, tried.case["case_id"]) == ("pB", "B") and calls == ["pA", "pB"]
    assert first_full_walk([a, b], 3, lambda pick: None) is None
    assert first_full_walk([a, b, c], 1, attempt)[0].property_id == "pA"  # --tries is honoured
