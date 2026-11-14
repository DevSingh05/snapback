"""The counts-only lane D self-check: integers only, every count fills on the fixture kits, and a
zero-filled field is named."""

import json
import re
from datetime import date
from pathlib import Path

import pytest

from snapback.adapters.costar_jsonl import FIXTURE_KIT
from snapback.adapters.kit_selfcheck import main, selfcheck

HOUSE_KIT = Path(FIXTURE_KIT).parent / "costar-house-kit"
TODAY = date(2026, 11, 14)
SAFE_KEY = re.compile(r"[a-z][a-z_0-9]{0,40}")  # a hex hash cannot pass as a key


def _leaves(obj, path=""):
    """Every (key path, leaf) in the report; keys and list items checked on the way."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert SAFE_KEY.fullmatch(str(key)), f"unsafe key {key!r} at {path}"
            yield from _leaves(value, f"{path}.{key}")
    else:
        assert not isinstance(obj, list), f"a list at {path}: the report has none"
        yield path, obj


def test_every_leaf_is_an_integer_and_every_key_is_safe(capsys):
    for kit in (FIXTURE_KIT, HOUSE_KIT):
        main(["--kit", str(kit), "--today", TODAY.isoformat()])
        report = json.loads(capsys.readouterr().out)
        for path, leaf in _leaves(report):
            assert isinstance(leaf, int) and not isinstance(leaf, bool), path


def test_every_commercial_count_fills_on_the_fixture_kit():
    commercial = selfcheck(FIXTURE_KIT, TODAY)["commercial"]
    empty = [k for k, v in commercial.items() if v == 0]
    assert not empty, empty
    assert commercial["records"] == 5


def test_every_residential_and_demo_count_fills_on_the_house_kit():
    report = selfcheck(HOUSE_KIT, TODAY)
    residential = report["residential"]
    for key in ("records", "public", "with_media_model", "houston"):
        assert residential[key] > 0, key
    assert sum(residential["d7_lookup_on_own_address_sample"].values()) > 0
    assert sum(residential["status"].values()) == residential["public"]
    demo = report["demo_house"]
    assert demo["candidates"] > 0 and demo["trio_found"] == 1
    assert demo["by_role"]["for_sale"] > 0 and demo["by_role"]["recently_sold"] > 0


def test_media_models_are_counted_on_public_records_only(tmp_path):
    kit = tmp_path / "kit"
    kit.mkdir()
    rows = [
        {"propertyId": 1, "permissionLevels": {"homes": 10},
         "media": [{"externalReferenceType": 36, "videoKey": "fx-a"}]},
        {"propertyId": 2, "permissionLevels": {"homes": 20},
         "media": [{"externalReferenceType": 36, "videoKey": "fx-b"}]},
    ]  # fmt: skip
    (kit / "residential-listings.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    assert selfcheck(kit, TODAY)["residential"]["with_media_model"] == 1


def test_zero_fill_names_commercial_and_residential_fields(tmp_path):
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "commercial-property.jsonl").write_text(
        '{"propertyId": "fx-z", "propertyType": 11}\n', encoding="utf-8"
    )
    (kit / "residential-listings.jsonl").write_text('{"propertyId": 7}\n', encoding="utf-8")
    zero = selfcheck(kit, TODAY)["zero_fill"]
    assert "commercial_with_floors" in zero and "commercial_with_model_ids" in zero
    assert "residential_public" in zero and "residential_with_media_model" in zero
    assert "residential_d7_lookup_on_own_address_sample" in zero  # an empty dict count
    assert "demo_house_candidates" in zero


def test_a_missing_kit_exits_1_without_a_path(tmp_path, capsys):
    with pytest.raises(SystemExit) as stop:
        main(["--kit", str(tmp_path / "nowhere")])
    assert stop.value.code == 1
    assert "nowhere" not in capsys.readouterr().out
