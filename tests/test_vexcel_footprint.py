"""Vexcel footprints (#11, 02:47): the claimed building's OSM outline, carried into the ad's
nadir tile by the matcher's transform, tells a shifted view of the same building from the house
next door. Synthetic scenes and polygons only (no real tiles, addresses or answers in git)."""

from types import SimpleNamespace

import pytest

from snapback.adapters import footprints as fp

# --- geometry and parsing (no opencv needed) ---------------------------------------------------

LAT0, LON0 = 10.0, 20.0  # a made-up point, not a real place


def _square_latlon(half_m: float, east_m: float = 0.0, north_m: float = 0.0):
    """A square outline `half_m` from its centre, centred east_m/north_m from (LAT0, LON0)."""
    dlat = 1 / fp.M_PER_DEG_LAT
    import math

    dlon = 1 / (fp.M_PER_DEG_LON_EQUATOR * math.cos(math.radians(LAT0)))
    cx, cy = east_m, north_m
    corners = [(-half_m, -half_m), (half_m, -half_m), (half_m, half_m), (-half_m, half_m)]
    pts = [(LAT0 + (cy + y) * dlat, LON0 + (cx + x) * dlon) for x, y in corners]
    return pts + [pts[0]]  # OSM ways close on themselves


def _overpass(*polys):
    return {
        "elements": [
            {"type": "way", "geometry": [{"lat": a, "lon": b} for a, b in poly]} for poly in polys
        ]
    }


def test_contains_is_ray_casting():
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert fp.contains(sq, 5, 5)
    assert not fp.contains(sq, 15, 5)
    assert not fp.contains(sq, -1, -1)


def test_the_footprint_is_the_outline_containing_the_claimed_point():
    mine = _square_latlon(10)
    neighbour = _square_latlon(8, east_m=30)
    assert fp.footprint_at(LAT0, LON0, _overpass(neighbour, mine)) == mine


def test_no_building_at_the_point_means_no_footprint():
    assert fp.footprint_at(LAT0, LON0, _overpass(_square_latlon(8, east_m=30))) is None
    assert fp.footprint_at(LAT0, LON0, {"elements": []}) is None


def test_fetch_gives_none_on_any_error_and_caches_answers(tmp_path):
    def boom(_url, _body):
        raise OSError("network down")

    assert fp.fetch(LAT0, LON0, post=boom) is None
    assert fp.fetch(None, LON0, post=boom) is None

    calls = []

    def post(url, body):
        calls.append(body)
        assert "building" in body and f"{LAT0}" in body
        return _overpass(_square_latlon(10))

    first = fp.fetch(LAT0, LON0, cache_dir=tmp_path, post=post)
    again = fp.fetch(LAT0, LON0, cache_dir=tmp_path, post=boom)  # served from the cache
    assert first is not None and again == first
    assert len(calls) == 1


def test_footprint_uv_puts_the_claimed_point_at_the_tile_centre():
    uv = fp.footprint_uv(LAT0, LON0, _square_latlon(10), ground_m=100)
    us, vs = [u for u, _ in uv], [v for _, v in uv]
    assert min(us) == pytest.approx(0.4, abs=1e-3) and max(us) == pytest.approx(0.6, abs=1e-3)
    assert min(vs) == pytest.approx(0.4, abs=1e-3) and max(vs) == pytest.approx(0.6, abs=1e-3)


# --- the matcher with a footprint (opencv) -----------------------------------------------------

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from snapback.adapters import vexcel_match as vm  # noqa: E402

TILE = 600  # square nadir tiles, vm.GROUND_M metres across
PX_PER_M = TILE / vm.GROUND_M


def _world(seed, size=(2400, 2400)):
    rng = np.random.default_rng(seed)
    img = (rng.random(size) * 60 + 90).astype(np.uint8)
    for _ in range(900):
        x, y = int(rng.integers(0, size[1])), int(rng.integers(0, size[0]))
        w, h = int(rng.integers(12, 70)), int(rng.integers(12, 70))
        cv2.rectangle(img, (x, y), (x + w, y + h), int(rng.integers(0, 255)), -1)
    return cv2.GaussianBlur(img, (3, 3), 0)


def _tile(tmp_path, world, east_m, north_m, name):
    h, w = world.shape
    cx = int(w / 2 + east_m * PX_PER_M)
    cy = int(h / 2 - north_m * PX_PER_M)
    crop = world[cy - TILE // 2 : cy + TILE // 2, cx - TILE // 2 : cx + TILE // 2]
    path = tmp_path / f"{name}.png"
    cv2.imwrite(str(path), crop)
    return str(path)


@pytest.fixture(scope="module")
def world():
    return _world(7)


# A building 30 m wide around the claimed point: a view shifted 12 m still lands on it; the house
# next door, 18 m away, does not, though both are under the old 18 m offset threshold.
BUILDING_UV = fp.footprint_uv(LAT0, LON0, _square_latlon(15), ground_m=vm.GROUND_M)


def test_a_shifted_view_of_the_same_building_lands_inside_its_footprint(tmp_path, world):
    claimed = _tile(tmp_path, world, 0, 0, "claimed")
    ad = _tile(tmp_path, world, 0, 12, "ad")  # the same building, the tile 12 m off
    m = vm.geo_match(claimed, ad, footprint_uv=BUILDING_UV)
    assert m is not None and m.inliers >= vm.MIN_INLIERS
    assert m.in_footprint is True


def test_the_house_next_door_lands_outside_the_claimed_footprint(tmp_path, world):
    claimed = _tile(tmp_path, world, 0, 0, "claimed")
    ad = _tile(tmp_path, world, 18, 0, "ad")  # a neighbour 18 m east
    m = vm.geo_match(claimed, ad, footprint_uv=BUILDING_UV)
    assert m is not None and m.inliers >= vm.MIN_INLIERS
    assert m.offset_m <= vm.MAX_OFFSET_M  # the old offset rule would call it the same building
    assert m.in_footprint is False


def test_without_a_footprint_nothing_changes(tmp_path, world):
    claimed = _tile(tmp_path, world, 0, 0, "claimed")
    ad = _tile(tmp_path, world, 0, 8, "ad")
    assert vm.geo_match(claimed, ad).in_footprint is None


# --- the ablation: both arms, held-out split, the anti-circularity rule -------------------------

from snapback.eval import vexcel_set  # noqa: E402


def _doc():
    import math

    dlat = 1 / fp.M_PER_DEG_LAT
    dlon = 1 / (fp.M_PER_DEG_LON_EQUATOR * math.cos(math.radians(LAT0)))
    props = {
        "c": {"lat": LAT0, "lon": LON0},
        "same": {"lat": LAT0 + 10 * dlat, "lon": LON0},  # 10 m north: same building
        "next": {"lat": LAT0, "lon": LON0 + 18 * dlon},  # 18 m east: next door
    }
    cases = []
    for i in range(4):
        cases.append(
            {
                "case_id": f"r{i}",
                "claimed_property_id": "c",
                "expected_property_id": "same",
                "label": "right",
                "kind": "right",
            }
        )
        cases.append(
            {
                "case_id": f"n{i}",
                "claimed_property_id": "c",
                "expected_property_id": "next",
                "label": "wrong",
                "kind": "next_door",
            }
        )
    return {"properties": props, "cases": cases}


def test_the_ablation_scores_both_arms_and_asks_for_the_claimed_footprint_only(tmp_path, world):
    tiles = {
        ("c",): _tile(tmp_path, world, 0, 0, "c"),
        ("same",): _tile(tmp_path, world, 0, 10, "same"),
        ("next",): _tile(tmp_path, world, 18, 0, "next"),
    }

    def tile_fn(record, direction, source=None):
        assert direction == "nadir"
        return SimpleNamespace(path=tiles[(record.property_id,)])

    asked = []

    def footprint_fn(lat, lon):
        asked.append((lat, lon))
        return _square_latlon(14)

    result = vexcel_set.run_ablation(_doc(), tile_fn=tile_fn, footprint_fn=footprint_fn)
    assert set(asked) == {(LAT0, LON0)}  # never the ad building's coordinates
    image = result["arms"]["image_footprint"]["all"]
    assert image["right"]["hits"] == 4 and image["next_door"]["hits"] == 4
    assert set(result["held_out_hits"]) == set(vexcel_set.ARMS)
    assert "image_gate_met" in result and "beats_footprint_only" in result
    # counts and case ids only: no coordinates or paths in the result
    flat = repr(result)
    assert str(LAT0) not in flat and "png" not in flat


def test_no_footprint_means_not_checked_for_both_arms(tmp_path):
    def tile_fn(record, direction, source=None):
        raise AssertionError("no tile is fetched without a footprint")

    result = vexcel_set.run_ablation(_doc(), tile_fn=tile_fn, footprint_fn=lambda lat, lon: None)
    for arm in vexcel_set.ARMS:
        t = result["arms"][arm]["all"]
        assert t["right"]["hits"] == 0 and t["right"]["not_checked"] == 4
    assert result["gate_open"] is False
