"""Matcher v2: local features plus a RANSAC transform say where the claimed building sits in
the ad building's tile. Synthetic scenes only (no real tiles in git)."""

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from snapback.adapters import vexcel_match as vm  # noqa: E402

TILE_W, TILE_H = 800, 600  # one tile spans vm.GROUND_M metres both ways
PX_PER_M_X = TILE_W / vm.GROUND_M
PX_PER_M_Y = TILE_H / vm.GROUND_M


def _world(seed, size=(2400, 2400)):
    """A textured 'neighbourhood': random roofs (rectangles) over noise, deterministic."""
    rng = np.random.default_rng(seed)
    img = (rng.random(size) * 60 + 90).astype(np.uint8)
    for _ in range(900):
        x, y = int(rng.integers(0, size[1])), int(rng.integers(0, size[0]))
        w, h = int(rng.integers(12, 70)), int(rng.integers(12, 70))
        cv2.rectangle(img, (x, y), (x + w, y + h), int(rng.integers(0, 255)), -1)
    return cv2.GaussianBlur(img, (3, 3), 0)


def _tile(tmp_path, world, cx_m, cy_m, name):
    """The tile centred cx_m east and cy_m north of the world's middle."""
    h, w = world.shape
    cx = int(w / 2 + cx_m * PX_PER_M_X)
    cy = int(h / 2 - cy_m * PX_PER_M_Y)
    crop = world[cy - TILE_H // 2 : cy + TILE_H // 2, cx - TILE_W // 2 : cx + TILE_W // 2]
    path = tmp_path / f"{name}.png"
    cv2.imwrite(str(path), crop)
    return str(path)


@pytest.fixture(scope="module")
def world():
    return _world(1)


def test_an_8_m_shift_of_the_same_scene_is_found_about_8_m_away(tmp_path, world):
    a = _tile(tmp_path, world, 0, 0, "a")
    b = _tile(tmp_path, world, 0, 8, "b")
    m = vm.geo_match(a, b)
    assert m is not None
    assert m.inliers >= vm.MIN_INLIERS
    assert 6.0 <= m.offset_m <= 10.0
    assert vm.same_building(m)


def test_the_house_next_door_25_m_east_is_not_the_same_building(tmp_path, world):
    a = _tile(tmp_path, world, 25, 0, "a")
    b = _tile(tmp_path, world, 0, 0, "b")
    m = vm.geo_match(a, b)
    assert m is not None
    assert m.inliers >= vm.MIN_INLIERS  # the scenes overlap a lot...
    assert 22.0 <= m.offset_m <= 28.0  # ...but the claimed centre is a house away
    assert not vm.same_building(m)


def test_a_different_neighbourhood_has_too_few_inliers(tmp_path, world):
    a = _tile(tmp_path, world, 0, 0, "a")
    b = _tile(tmp_path, _world(2), 0, 0, "b")
    m = vm.geo_match(a, b)
    assert m is not None
    assert m.inliers < vm.MIN_INLIERS
    assert not vm.same_building(m)


def test_an_unreadable_tile_says_nothing(tmp_path, world):
    a = _tile(tmp_path, world, 0, 0, "a")
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not an image")
    assert vm.geo_match(a, str(bad)) is None
    assert vm.geo_match(a, str(tmp_path / "missing.jpg")) is None


# --- the matcher inside the labelled-set harness ---

from snapback.contracts import AerialStatus, AerialTile, DataSource, PropertyRecord  # noqa: E402
from snapback.eval import vexcel_set as vs  # noqa: E402


def _rec(pid, lat=29.76, lon=-95.37):
    return PropertyRecord(property_id=pid, source=DataSource.LIVE, lat=lat, lon=lon)


def test_live_aerial_match_uses_the_geometric_matcher(tmp_path, world):
    paths = {
        "claimed": _tile(tmp_path, world, 0, 0, "c"),
        "same8": _tile(tmp_path, world, 0, 8, "s"),
        "next30": _tile(tmp_path, world, 30, 0, "n"),
        "far": _tile(tmp_path, _world(3), 0, 0, "f"),
    }

    def tile(record, direction="north", **_):
        return AerialTile(
            property_id=record.property_id,
            source=DataSource.LIVE,
            direction=direction,
            path=paths[record.property_id],
        )

    def match(other):
        return vs.aerial_match(_rec("claimed"), _rec(other), source=DataSource.LIVE, tile_fn=tile)

    right = match("same8")
    assert right.status is AerialStatus.RIGHT_BUILDING
    assert right.inliers >= vm.MIN_INLIERS and right.offset_m is not None
    assert match("next30").status is AerialStatus.WRONG_BUILDING
    assert match("far").status is AerialStatus.WRONG_BUILDING


def _row(cid, kind, inliers, offset):
    return {
        "case_id": cid,
        "kind": kind,
        "label": "right" if kind == "right" else "wrong",
        "inliers": inliers,
        "offset_m": offset,
    }


def _rows():
    rows = [_row(f"vx-r{i:02d}", "right", 600, 4.0 + i % 8) for i in range(1, 13)]
    rows += [_row(f"vx-n{i:02d}", "next_door", 600, 18.0 + 2 * i) for i in range(1, 9)]
    rows += [_row(f"vx-w{i:02d}", "wrong", 3, 30.0) for i in range(1, 7)]
    return rows


def test_the_split_halves_every_kind_and_never_overlaps():
    tune, held = vs.split_ids(_rows())
    assert not tune & held and len(tune | held) == 26
    for prefix, n in (("vx-r", 12), ("vx-n", 8), ("vx-w", 6)):
        assert sum(c.startswith(prefix) for c in held) == n // 2


def test_thresholds_are_picked_on_the_tune_half_only():
    rows = _rows()
    tune, held = vs.split_ids(rows)
    # Poison the held-out half: if tuning read it, the offset bar would move past 18 m.
    for r in rows:
        if r["case_id"] in held and r["kind"] == "right":
            r["offset_m"] = 40.0
    min_inl, max_off = vs.tune_thresholds(rows, tune)
    assert 3 < min_inl <= 600
    assert 11.0 <= max_off < 18.0
    held_score = vs.score(rows, held, min_inl, max_off)
    assert held_score["right"]["hits"] == 0  # the poisoned cases fail, as they should


def test_the_gate_needs_every_held_out_class():
    perfect = {
        "right": {"n": 6, "hits": 6},
        "next_door": {"n": 4, "hits": 4},
        "wrong": {"n": 3, "hits": 3},
    }
    assert vs.gate_met(perfect) is True
    one_wrong_missed = {**perfect, "wrong": {"n": 3, "hits": 2}}
    assert vs.gate_met(one_wrong_missed) is False  # other-wrong must be 100 percent
    right_low = {**perfect, "right": {"n": 10, "hits": 8}}
    assert vs.gate_met(right_low) is False  # 80 percent < 90
    assert vs.gate_met({**perfect, "next_door": {"n": 0, "hits": 0}}) is False


def test_extend_keeps_the_old_cases_and_adds_new_ones():
    rows = [
        {
            "propertyId": i,
            "address": f"{i} Main St",
            "lat": 29.7 + (i // 2) * 0.01 + (i % 2) * 0.0002,
            "lon": -95.3,
        }
        for i in range(80)
    ]
    base = vs.build_cases(rows[:40], n_right=4, n_next_door=3, n_wrong=0)
    big = vs.extend_cases(base, rows, add_right=8, add_next_door=4)
    assert big["cases"][: len(base["cases"])] == base["cases"]
    new = big["cases"][len(base["cases"]) :]
    ids = [c["case_id"] for c in big["cases"]]
    assert len(ids) == len(set(ids))
    assert sum(c["kind"] == "right" for c in new) == 8
    assert sum(c["kind"] == "next_door" for c in new) == 4
    old_props = set(base["properties"])
    for c in new:
        assert c["claimed_property_id"] not in old_props
        if c["kind"] == "right":
            assert 8.0 <= c["expected_offset_m"] <= 15.0


def test_a_blank_tile_says_nothing_rather_than_wrong_building(tmp_path, world):
    a = _tile(tmp_path, world, 0, 0, "a")
    blank = tmp_path / "blank.png"
    img = np.full((TILE_H, TILE_W), 128, np.uint8)
    for x in (300, 400, 500):  # a cloud-grey tile with a few marks: some keypoints, too few
        cv2.rectangle(img, (x, 280), (x + 20, 300), 30, -1)
    cv2.imwrite(str(blank), img)
    assert vm.geo_match(a, str(blank)) is None
    assert vm.geo_match(str(blank), a) is None
