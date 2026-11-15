"""The Vexcel labelled-set measurement: matcher, scoring, case builder, and the committed set."""

import json
from pathlib import Path

from snapback.adapters import vexcel
from snapback.contracts import AerialStatus, AerialTile, DataSource, PropertyRecord
from snapback.eval import vexcel_set as vs

REPO = Path(__file__).resolve().parent.parent
FIXTURE_SET = REPO / "eval" / "vexcel" / "cases.fixture.json"


def rec(pid, lat, lon):
    return PropertyRecord(property_id=pid, source=DataSource.FIXTURE, lat=lat, lon=lon)


def test_same_point_is_the_right_building_in_fixture_mode():
    a = rec("a", 29.76, -95.37)
    result = vs.aerial_match(a, a, source=DataSource.FIXTURE)
    assert result.status is AerialStatus.RIGHT_BUILDING


def test_a_neighbour_is_the_wrong_building_in_fixture_mode():
    a, b = rec("a", 29.76, -95.37), rec("b", 29.7604, -95.37)  # about 45 m
    result = vs.aerial_match(b, a, source=DataSource.FIXTURE)
    assert result.status is AerialStatus.WRONG_BUILDING
    assert 40 < result.distance_m < 50


def test_no_coordinates_says_nothing():
    a = rec("a", 29.76, -95.37)
    assert vs.aerial_match(rec("b", None, None), a, source=DataSource.FIXTURE).status is (
        AerialStatus.NOT_CHECKED
    )


def _png(path, seed):
    from PIL import Image

    img = Image.new("L", (64, 64))
    img.putdata([(x * seed + y * (seed + 3)) % 256 for y in range(64) for x in range(64)])
    img.save(path, "PNG")
    return str(path)


def test_live_compares_the_two_tiles(tmp_path):
    same = _png(tmp_path / "s.png", 7)
    other = _png(tmp_path / "o.png", 29)
    paths = {"a": same, "b": same, "c": other}

    def tile(record, direction="north", **_):
        return AerialTile(
            property_id=record.property_id,
            source=DataSource.LIVE,
            direction=direction,
            path=paths[record.property_id],
        )

    a, b, c = rec("a", 29.76, -95.37), rec("b", 29.7601, -95.3701), rec("c", 29.762, -95.37)
    assert vs.aerial_match(a, b, source=DataSource.LIVE, tile_fn=tile).status is (
        AerialStatus.RIGHT_BUILDING
    )
    assert vs.aerial_match(c, a, source=DataSource.LIVE, tile_fn=tile).status is (
        AerialStatus.WRONG_BUILDING
    )


def test_live_with_a_missing_tile_is_not_checked():
    a = rec("a", 29.76, -95.37)
    result = vs.aerial_match(a, a, source=DataSource.LIVE, tile_fn=lambda *a, **k: None)
    assert result.status is AerialStatus.NOT_CHECKED


def test_live_without_a_key_is_not_checked_and_never_raises():
    def tile(*a, **k):
        raise vexcel.VexcelKeyMissingError("x")

    a = rec("a", 29.76, -95.37)
    assert vs.aerial_match(a, a, source=DataSource.LIVE, tile_fn=tile).status is (
        AerialStatus.NOT_CHECKED
    )


def doc(n_right=3, n_wrong=2):
    props = {"p0": {"address": "1 A St", "lat": 29.76, "lon": -95.37}}
    cases = []
    for i in range(n_right):
        props[f"r{i}"] = {"address": f"{i} R St", "lat": 29.7 + i * 0.01, "lon": -95.3}
        cases.append(
            {
                "case_id": f"r{i}",
                "claimed_address": f"{i} R St",
                "claimed_property_id": f"r{i}",
                "expected_property_id": f"r{i}",
                "label": "right",
            }
        )
    for i in range(n_wrong):
        props[f"w{i}"] = {"address": f"{i} W St", "lat": 29.9 + i * 0.01, "lon": -95.3}
        props[f"x{i}"] = {"address": f"{i} X St", "lat": 29.9 + i * 0.01 + 0.001, "lon": -95.3}
        cases.append(
            {
                "case_id": f"w{i}",
                "claimed_address": f"{i} X St",
                "claimed_property_id": f"x{i}",
                "expected_property_id": f"w{i}",
                "label": "wrong",
            }
        )
    return {"properties": props, "cases": cases}


def test_run_scores_hits_and_misses():
    d = doc()
    d["cases"][0]["label"] = "wrong"  # make one miss
    result = vs.run_cases(d, source=DataSource.FIXTURE)
    assert (result["n"], result["hits"], result["misses"]) == (5, 4, ["r0"])
    assert result["wrong_building_cases"] == 3  # the relabelled one counts


def test_bar_needs_twenty_cases_and_ninety_percent():
    r = vs.run_cases(doc(18, 2), source=DataSource.FIXTURE)
    assert (r["n"], r["hits"], r["bar_met"]) == (20, 20, True)
    assert vs.run_cases(doc(5, 2), source=DataSource.FIXTURE)["bar_met"] is False  # n < 20
    d = doc(18, 2)
    for c in d["cases"][:3]:
        c["label"] = "wrong"
    assert vs.run_cases(d, source=DataSource.FIXTURE)["bar_met"] is False  # 17 of 20


def test_a_fixture_pass_never_opens_the_gate():
    r = vs.run_cases(doc(18, 2), source=DataSource.FIXTURE)
    assert r["bar_met"] is True and r["gate_open"] is False and r["mode"] == "fixture"


def test_results_json_carries_no_addresses(tmp_path):
    r = vs.run_cases(doc(18, 2), source=DataSource.FIXTURE)
    out = tmp_path / "r.json"
    vs.write_results(r, out)
    text = out.read_text()
    assert "R St" not in text and "W St" not in text
    assert json.loads(text)["n"] == 20


def test_builder_makes_right_and_wrong_cases_from_listings():
    rows = [
        {
            "propertyId": i,
            "address": f"{i} Main St",
            "lat": 29.7 + (i // 2) * 0.01 + (i % 2) * 0.001,
            "lon": -95.3,
        }
        for i in range(60)
    ]
    built = vs.build_cases(rows, n_right=14, n_wrong=10)
    labels = [c["label"] for c in built["cases"]]
    assert labels.count("right") == 14 and labels.count("wrong") == 10
    for c in built["cases"]:
        same = c["claimed_property_id"] == c["expected_property_id"]
        assert same == (c["label"] == "right")
    wrong = [c for c in built["cases"] if c["label"] == "wrong"]
    assert all(40 <= c["distance_m"] <= 500 for c in wrong)


def test_the_committed_fixture_set_is_big_enough_and_synthetic():
    d = json.loads(FIXTURE_SET.read_text())
    assert len(d["cases"]) >= 20
    assert sum(c["label"] == "wrong" for c in d["cases"]) >= 6
    assert d["synthetic"] is True
    r = vs.run_cases(d, source=DataSource.FIXTURE)
    assert r["bar_met"] is True
