"""The counts-only lane D self-check: numbers only, and a zero-filled mapped field is named."""

import json

import pytest

from snapback.adapters.costar_jsonl import FIXTURE_KIT
from snapback.adapters.kit_selfcheck import main, selfcheck


def test_it_prints_counts_and_no_ids_or_values(capsys):
    main(["--kit", str(FIXTURE_KIT), "--today", "2026-11-14"])
    printed = capsys.readouterr().out
    report = json.loads(printed)
    assert report["commercial"]["records"] >= 4
    assert report["residential"]["public"] >= 1
    for secret in ("fx-", "Fixture Lane", "fixtureliving", "Fixture Living"):
        assert secret not in printed


def test_a_zero_filled_field_is_named(tmp_path):
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "commercial-property.jsonl").write_text(
        '{"propertyId": "fx-z", "propertyType": 11}\n', encoding="utf-8"
    )
    report = selfcheck(kit, __import__("datetime").date(2026, 11, 14))
    assert "with_floors" in report["zero_fill"] and "with_model_ids" in report["zero_fill"]


def test_a_missing_kit_exits_1_without_a_path(tmp_path, capsys):
    with pytest.raises(SystemExit) as stop:
        main(["--kit", str(tmp_path / "nowhere")])
    assert stop.value.code == 1
    assert "nowhere" not in capsys.readouterr().out
