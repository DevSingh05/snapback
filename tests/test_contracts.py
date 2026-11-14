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


def test_create_case_fixtures_parse_and_keep_the_secret_out_of_the_request():
    import snapback.contracts as contracts

    request = contracts.CreateCaseRequest.model_validate_json(load("create_case_request.json"))
    response = contracts.CreateCaseResponse.model_validate_json(load("create_case_response.json"))
    assert request.link and request.text
    assert "token" not in contracts.CreateCaseRequest.model_fields
    assert response.source == "fixture"
    assert response.token.startswith("fx-")  # a fixture value, never a real secret
    assert response.read_token and response.read_token.startswith("fx-")
    assert response.read_token != response.token
    assert response.challenge_text


def test_the_a7_contact_fields_are_optional_and_their_fixtures_parse():
    # A7 (#67) and D7 (#66): everything added is optional, so records written before it
    # still parse and say "not checked".
    import snapback.contracts as contracts

    old = contracts.PropertyRecord.model_validate_json(load("property_record.json"))
    assert (old.site_phone_hash, old.website_host, old.floor_plan_rents, old.units) == (
        None, None, [], [],
    )  # fmt: skip

    record = contracts.PropertyRecord.model_validate_json(load("property_record_contact.json"))
    assert record.property_id.startswith("fx-") and record.website_host.endswith(".example")
    assert record.site_phone_hash.startswith("fx-")  # a stand-in for a hash, never digits
    assert [plan.per_bed for plan in record.floor_plan_rents] == [False, False, True]
    assert {unit.unit for unit in record.units} == {"101", "204", "4B"}

    for_sale = contracts.ForSaleMatch.model_validate_json(load("for_sale_match.json"))
    assert for_sale.status is contracts.ForSaleStatus.ACTIVE and for_sale.site == "Homes.com"

    hold = contracts.ModuleEvidence.model_validate_json(load("module_evidence_hold.json"))
    assert hold.for_sale is None
    if hold.authority is not None:
        assert hold.authority.office_phone_match is contracts.PhoneMatch.NOT_CHECKED
        assert hold.authority.link_domain is contracts.LinkDomain.NOT_CHECKED
    if hold.price is not None:
        assert hold.price.unit is contracts.UnitStatus.NOT_CHECKED and hold.price.per_bed is False
    evidence = contracts.Evidence(case_id="fx-1", source="fixture")
    assert not any(
        (
            evidence.for_sale_flag,
            evidence.recently_rented_flag,
            evidence.phone_flag,
            evidence.lookalike_link_flag,
            evidence.unit_flag,
        )
    )


def test_the_a10_join_fields_are_optional():
    # A10: a card can mix a real record with stand-ins, so a line can say where it came from.
    import snapback.contracts as contracts

    card = contracts.Card.model_validate_json(load("card_hold.json"))
    assert all(line.source is None for row in card.rows for line in row.lines)
    line = card.rows[0].lines[0].model_copy(update={"source": contracts.DataSource.LIVE})
    assert contracts.CardLine.model_validate_json(line.model_dump_json()).source == "live"

    evidence = contracts.ModuleEvidence.model_validate_json(load("module_evidence_hold.json"))
    assert evidence.record_source is None

    request = contracts.CreateCaseRequest.model_validate_json(load("create_case_request.json"))
    assert request.property_id is None
    assert contracts.CreateCaseRequest(property_id="fx-prop-3").property_id == "fx-prop-3"


def test_the_a14_reply_shapes_parse_and_waiting_for_a_reply_is_a_progress_value():
    import snapback.contracts as contracts

    reply = contracts.ReplyResponse.model_validate_json(load("reply_response.json"))
    assert reply.check is contracts.ReplyCheck.COPY_OF_LISTING_PHOTO
    assert (reply.presence, reply.state, reply.status) == ("forged", "dont_pay", "done")

    waiting = contracts.ReplyResponse(
        case_id="7Q2M",
        source="fixture",
        status=contracts.CaseProgress.WAITING_FOR_REPLY,
        check=contracts.ReplyCheck.CODE_READ_SPOT_NOT_CHECKED,
        presence=contracts.PresenceStatus.WAITING,
    )
    assert waiting.state is None and waiting.challenge_text is None
    # The honest middle: a right code that is not a copy is never called proven.
    assert contracts.ReplyCheck.CODE_READ_SPOT_NOT_CHECKED != contracts.ReplyCheck.PROVEN
    # Cases made before this still report the three values they knew.
    created = contracts.CreateCaseResponse.model_validate_json(load("create_case_response.json"))
    assert created.status in set(contracts.CaseProgress)


# --- E0: the evidence file and the agent's trace kinds -----------------------------------------


def test_evidence_fixture_validates_and_keeps_points_a_bounded_sample():
    from snapback.contracts import EvidenceFile

    doc = EvidenceFile.model_validate_json(
        (FIXTURES.parent / "demo" / "evidence.fixture.json").read_text()
    )
    assert doc.source.value == "fixture" and doc.written_by == "code"
    assert [p.alias for p in doc.photos] == ["P1", "P2", "P3", "P4"]
    assert all(p.points is None or len(p.points.sampled) <= 48 for p in doc.photos)
    near_miss = doc.photos[2]  # not placed by the base search, placed on a retry the model picked
    assert [(s.option, s.chosen_by, s.result) for s in near_miss.searches] == [
        ("base", "policy", "not_placed"),
        ("focus_scan:S2", "model", "placed"),
    ]
    assert doc.photos[3].bar_failed == "inliers" and doc.photos[3].status.value == "not_located"
    again = EvidenceFile.model_validate_json(doc.model_dump_json())
    assert again == doc


def test_evidence_points_refuse_more_than_48_pairs():
    from pydantic import ValidationError

    from snapback.contracts import EvidencePoints

    with pytest.raises(ValidationError):
        EvidencePoints(n_total=60, sampled=[(0.1, 0.1, 0.1, 0.1)] * 49)


def test_new_trace_kinds_are_additive_and_old_ones_unchanged():
    assert {k.value for k in TraceKind} >= {"choice", "tool", "status", "hitl", "verdict", "error"}
    assert {"todo", "agent", "file", "unsure"} <= {k.value for k in TraceKind}


def test_photo_location_evidence_fields_are_optional():
    from snapback.contracts import PhotoLocation

    p = PhotoLocation(photo_id="x", status="not_located")
    assert p.spread is None and p.rival_ratio is None and p.bar_failed is None
