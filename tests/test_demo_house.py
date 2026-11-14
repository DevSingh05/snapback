"""#74: pick the demo trio where the kit lives; never print or post its ids.

The fixture kit copies the real key paths (`propertyId`, `media[].externalReferenceType` with
`media[].videoKey`, `property.address.city`, `history[].updateType`); every value is made up.
Property ids 9000 to 9014 are synthetic.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from snapback.adapters.costar_residential import (
    indexed_model_ids,
    main,
    pick_demo_houses,
    write_demo_house,
)

KIT = Path(__file__).resolve().parents[1] / "fixtures" / "adapters" / "costar-house-kit"
TODAY = date(2026, 11, 14)


def by_role(picks):
    return {p["role"]: p for p in picks}


def test_the_trio_is_picked_by_role_with_candidate_counts():
    picks = by_role(pick_demo_houses(KIT, TODAY))
    # for sale: 9001 and 9002 qualify; 9015 is for rent only, 9003 is off market, 9007 is in
    # Austin, 9008 was just rented, 9010 is hidden, 9011 is a condo, 9012 has no model.
    assert (picks["for_sale"]["propertyId"], picks["for_sale"]["candidates"]) == (9001, 2)
    # recently sold: 9004 (closeDate) and 9005 (NewlySold). 9006 sold in 2025, 9009 was rented.
    assert (picks["recently_sold"]["propertyId"], picks["recently_sold"]["candidates"]) == (9004, 2)
    # decoy: same zip as the for-sale pick (77001), not 9000 in 77099 with a smaller id
    assert picks["decoy"]["propertyId"] != 9000
    assert picks["decoy"]["propertyId"] == 9002
    assert {p["rule"] for p in picks.values()} == {"first by propertyId"}
    assert not any(p["indexed"] for p in picks.values())


def test_a_tie_on_property_id_picks_the_smaller_listing_id_in_any_file_order(tmp_path):
    lines = (KIT / "residential-listings.jsonl").read_text().splitlines()
    (tmp_path / "enums.json").write_text((KIT / "enums.json").read_text())
    (tmp_path / "residential-listings.jsonl").write_text("\n".join(reversed(lines)) + "\n")
    forward = by_role(pick_demo_houses(KIT, TODAY))
    backward = by_role(pick_demo_houses(tmp_path, TODAY))
    assert forward == backward
    assert forward["for_sale"]["models"] == ["fx-fs-a"]  # listing 5001, not 5002


def test_an_indexed_twin_beats_a_smaller_property_id(tmp_path):
    index = tmp_path / "index" / "demo"
    index.mkdir(parents=True)
    # 9002's Matterport key (media type 234) is indexed; 9001's is not
    (index / "index.json").write_text(json.dumps({"entries": [{"model_id": "fx-fs-c"}]}))
    assert indexed_model_ids(tmp_path) == {"fx-fs-c"}
    picks = by_role(pick_demo_houses(KIT, TODAY, indexed_model_ids(tmp_path)))
    assert picks["for_sale"]["propertyId"] == 9002
    assert picks["for_sale"]["rule"] == "indexed twin" and picks["for_sale"]["indexed"]
    assert picks["decoy"]["propertyId"] == 9001  # 9002 is taken: the next 77001 home


def test_the_recent_window_moves_with_today():
    # on 2027-05-01 the October close dates are over 180 days old; nothing is recently sold
    assert pick_demo_houses(KIT, date(2027, 5, 1)) is None


def test_written_file_holds_only_property_id_and_role_and_stdout_has_no_ids(tmp_path, capsys):
    out = write_demo_house(KIT, tmp_path / "data", TODAY)
    assert out == tmp_path / "data" / "demo" / "house.json"
    saved = json.loads(out.read_text())
    assert saved == [
        {"propertyId": 9001, "role": "for_sale"},
        {"propertyId": 9004, "role": "recently_sold"},
        {"propertyId": 9002, "role": "decoy"},
    ]
    printed = capsys.readouterr().out
    assert "for_sale: rule=first by propertyId, candidates=2, indexed=no" in printed
    assert "written to data/demo/house.json" in printed
    for secret in ("9001", "9004", "9002", "Fixture Way", str(tmp_path), "fx-"):
        assert secret not in printed


def test_missing_kit_exits_1_without_a_path(tmp_path, capsys):
    code = main(["--kit", str(tmp_path / "nowhere"), "--data", str(tmp_path / "data")])
    printed = capsys.readouterr().out
    assert code == 1
    assert printed.strip() == "kit not found (residential-listings.jsonl)"
    assert not (tmp_path / "data").exists()


def test_nothing_qualifying_exits_1_and_writes_nothing(tmp_path, capsys):
    (tmp_path / "residential-listings.jsonl").write_text("")
    code = main(["--kit", str(tmp_path), "--data", str(tmp_path / "data"), "--today", "2026-11-14"])
    assert code == 1
    assert not (tmp_path / "data" / "demo" / "house.json").exists()
    assert "no Houston" in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["2026-11-14"])
def test_today_flag_makes_the_cli_deterministic(tmp_path, flag, capsys):
    code = main(["--kit", str(KIT), "--data", str(tmp_path), "--today", flag])
    assert code == 0
    assert json.loads((tmp_path / "demo" / "house.json").read_text())[0]["propertyId"] == 9001
