"""The cross-lane fixtures parse against the contracts, so every lane can build against them."""

import json
from pathlib import Path

import pytest

from snapback.contracts import (
    Card,
    CardRowKind,
    MemoryHitKind,
    MemoryResult,
    ModuleEvidence,
    PresenceStatus,
    SpotRanking,
    TraceEvent,
    TraceKind,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"


def load(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.mark.parametrize("name", ["module_evidence_hold.json", "module_evidence_forged.json"])
def test_module_evidence_fixtures_parse_and_round_trip(name):
    evidence = ModuleEvidence.model_validate_json(load(name))
    again = ModuleEvidence.model_validate_json(evidence.model_dump_json())
    assert again == evidence
    assert evidence.source == "fixture"


def test_forged_fixture_carries_every_signal_verdict_needs():
    evidence = ModuleEvidence.model_validate_json(load("module_evidence_forged.json"))
    assert evidence.challenge.presence is PresenceStatus.FORGED
    assert evidence.memory[0].hit is MemoryHitKind.SAME_CASE_LISTING
    assert evidence.recapture[0].blocks_pass


def test_memory_never_names_another_case():
    assert "case_id" not in MemoryResult.model_fields


def test_card_fixture_has_three_rows_in_order_and_no_banned_words():
    card = Card.model_validate_json(load("card_hold.json"))
    assert [row.kind for row in card.rows] == [
        CardRowKind.PLACE,
        CardRowKind.PERSON,
        CardRowKind.PRICE,
    ]
    text = " ".join(line.text for row in card.rows for line in row.lines).lower()
    for banned in ("scam", "safe", "verified"):
        assert banned not in text


def test_trace_fixture_is_ordered_and_covers_the_choices():
    lines = load("trace_events.jsonl").strip().splitlines()
    events = [TraceEvent.model_validate(json.loads(line)) for line in lines]
    assert [e.seq for e in events] == sorted({e.seq for e in events})
    assert events[-1].kind is TraceKind.VERDICT
    choices = {e.choice for e in events if e.choice}
    assert len(choices) == 5


def test_spot_ranking_fixture_has_five_drawable_spots_and_one_excluded():
    ranking = SpotRanking.model_validate_json(load("spot_ranking.json"))
    drawable = [s for s in ranking.spots if not s.overlaps_listing_photo]
    assert len(drawable) == 5
    assert any(s.overlaps_listing_photo for s in ranking.spots)


@pytest.mark.parametrize(
    ("name", "model"),
    [("property_record.json", "PropertyRecord"), ("aerial_tile.json", "AerialTile")],
)
def test_data_fixtures_parse(name, model):
    import snapback.contracts as contracts

    parsed = getattr(contracts, model).model_validate_json(load(name))
    assert parsed.property_id.startswith("fx-")
