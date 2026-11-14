"""#74: pick the demo house (case c) where the kit lives; never print or post its ids."""

import json

from snapback.adapters.costar_jsonl import FIXTURE_KIT
from snapback.adapters.costar_residential import pick_demo_house, write_demo_house


def test_the_pick_is_public_active_for_sale_with_the_most_models():
    house = pick_demo_house(FIXTURE_KIT)
    assert house is not None
    # fx-home-6 (2 models) beats fx-home-1 (1); fx-home-5 has 3 but is not public on Homes.com
    assert house["home_listing_id"] == "fx-home-6"
    assert house["model_ids"] == ["fx-house-model-6a", "fx-house-model-6b"]


def test_the_pick_is_written_under_data_and_not_printed(tmp_path, capsys):
    out = write_demo_house(FIXTURE_KIT, tmp_path / "data")
    assert out == tmp_path / "data" / "demo" / "house.json"
    saved = json.loads(out.read_text())
    assert saved["home_listing_id"] == "fx-home-6"
    printed = capsys.readouterr().out
    assert "fx-home-6" not in printed and "fx-house-model" not in printed


def test_no_kit_file_means_no_pick(tmp_path):
    assert pick_demo_house(tmp_path) is None
