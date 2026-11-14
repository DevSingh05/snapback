"""The three-row card: every word from the string table, every state from decide()."""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from snapback.card import strings
from snapback.contracts import Card, CardRowKind, CardTone, ModuleEvidence
from snapback.verdict import build_card, decide, to_evidence

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
BANNED = ("safe", "verified", "scam")
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")
BASE_URL = "http://localhost:5173"


def raw(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def modules(name: str = "module_evidence_hold.json", **top_level) -> ModuleEvidence:
    """A fixture with some top-level sections replaced (None removes a section)."""
    return ModuleEvidence.model_validate(raw(name) | top_level)


def card_for(evidence: ModuleEvidence) -> Card:
    return build_card(evidence, checked_at=CHECKED_AT, verify_base_url=BASE_URL)


def lines(card: Card, kind: CardRowKind):
    return next(row for row in card.rows if row.kind is kind).lines


def line(card: Card, kind: CardRowKind, label: str):
    return next(item for item in lines(card, kind) if item.label == label)


def all_text(card: Card) -> str:
    parts = [item.text for row in card.rows for item in row.lines]
    return " ".join(parts + card.not_checked + card.footer)


VARIANTS = {
    "hold": modules(),
    "forged": modules("module_evidence_forged.json"),
    "nothing_at_all": ModuleEvidence(case_id="fx-0000", source="fixture"),
    "no_challenge": modules(challenge=None, recapture=[], memory=[]),
    "waiting": modules(
        challenge=raw("module_evidence_hold.json")["challenge"] | {"presence": "waiting"}
    ),
    "recapture_block": modules(
        recapture=[
            {
                "photo_id": "r1",
                "label": "screen",
                "score": 0.93,
                "blocks_pass": True,
                "model_version": "v0",
            }
        ]
    ),
    "authority_matches": modules(
        authority={"status": "matches_record", "manager_on_record": "Fixture Living LLC"}
    ),
    "rent_in_range": modules(price={"status": "within_range", "listed_rent": 1900}),
    "no_rules": modules(rules=[]),
    "photo_elsewhere": modules(
        locate={
            "case_id": "fx-7Q2M",
            "photos": [
                {"photo_id": "l1", "status": "located_in_claimed"},
                {"photo_id": "l2", "status": "located_elsewhere"},
            ],
            "thresholds_version": "fx-thresholds-0",
        }
    ),
    "not_indexed": modules(
        locate={
            "case_id": "fx-7Q2M",
            "photos": [{"photo_id": "l1", "status": "not_indexed"}],
            "thresholds_version": "fx-thresholds-0",
        }
    ),
    "not_located": modules(
        locate={
            "case_id": "fx-7Q2M",
            "photos": [{"photo_id": "l1", "status": "not_located"}],
            "thresholds_version": "fx-thresholds-0",
        }
    ),
    "seen_in_another_check": modules(
        memory=[
            {
                "photo_id": "l2",
                "hit": "other_check",
                "method": "embedding",
                "first_seen_on": "2026-11-12",
            },
            {"photo_id": "r1", "hit": "other_check", "method": "phash"},
        ]
    ),
}


def test_hold_fixture_card_matches_card_hold_json():
    built = card_for(modules())
    expected = Card.model_validate(raw("card_hold.json"))

    def shape(card: Card):
        return [(row.kind, [(item.label, item.tone) for item in row.lines]) for row in card.rows]

    assert shape(built) == shape(expected)


def test_hold_fixture_card_equals_card_hold_json_word_for_word():
    assert card_for(modules()) == Card.model_validate(raw("card_hold.json"))


@pytest.mark.parametrize("name", VARIANTS)
def test_rows_are_always_place_person_price_in_that_order(name):
    kinds = [row.kind for row in card_for(VARIANTS[name]).rows]
    assert kinds == [CardRowKind.PLACE, CardRowKind.PERSON, CardRowKind.PRICE]


@pytest.mark.parametrize("name", VARIANTS)
def test_card_state_is_whatever_decide_says(name):
    evidence = VARIANTS[name]
    assert card_for(evidence).state is decide(to_evidence(evidence)).state


@pytest.mark.parametrize("name", VARIANTS)
def test_every_card_string_comes_from_the_table(name, monkeypatch):
    # Swap every table entry for a marker. If any prose were written in code, it would show up
    # here as text that is not a marker.
    markers = {key: f"<{key}>" for key in strings.TABLES["en"]}
    monkeypatch.setitem(strings.TABLES, "en", markers)
    card = card_for(VARIANTS[name])
    shown = [item.label for row in card.rows for item in row.lines]
    shown += [item.text for row in card.rows for item in row.lines]
    shown += card.not_checked + card.footer
    assert shown
    for text in shown:
        assert re.fullmatch(r"<[a-z0-9_.]+>", text), text


@pytest.mark.parametrize("lang", strings.TABLES)
def test_no_string_contains_a_banned_word(lang):
    for key, text in strings.TABLES[lang].items():
        for banned in BANNED:
            assert banned not in text.lower(), f"{lang}:{key} contains {banned!r}"


@pytest.mark.parametrize("name", VARIANTS)
def test_tone_is_always_carried_by_words_too(name):
    # Colour never carries meaning alone: the wording of a line has to give its tone away.
    for row in card_for(VARIANTS[name]).rows:
        for item in row.lines:
            if item.tone is CardTone.RED_FLAG:
                assert item.text.endswith("Red flag."), item.text
            else:
                assert "red flag" not in item.text.lower(), item.text
            if item.tone is CardTone.NOT_SHOWN:
                assert item.text.startswith("NOT SHOWN."), item.text
            if item.tone is CardTone.NOT_CHECKED:
                assert item.text.startswith("Not checked"), item.text


def test_forged_fixture_card_names_the_copied_listing_photo():
    card = card_for(VARIANTS["forged"])
    here_now = line(card, CardRowKind.PERSON, "Here now")
    assert here_now.tone is CardTone.RED_FLAG
    assert "copy of listing photo 1" in here_now.text


def test_card_never_repeats_what_the_poster_called_themselves():
    # The poster may have given a person's name. The card says yes or no about the record only.
    card = card_for(VARIANTS["forged"])
    assert "John" not in all_text(card)
    allowed = line(card, CardRowKind.PERSON, "Allowed to rent it")
    assert allowed.tone is CardTone.RED_FLAG


def test_recapture_block_asks_for_a_new_photo_without_a_red_flag():
    card = card_for(VARIANTS["recapture_block"])
    here_now = line(card, CardRowKind.PERSON, "Here now")
    assert here_now.tone is CardTone.HOLD
    assert "new photo" in here_now.text


def test_no_reply_yet_is_a_hold_line():
    here_now = line(card_for(VARIANTS["waiting"]), CardRowKind.PERSON, "Here now")
    assert here_now.tone is CardTone.HOLD


def test_no_challenge_yet_is_not_checked_rather_than_a_failure():
    here_now = line(card_for(VARIANTS["no_challenge"]), CardRowKind.PERSON, "Here now")
    assert here_now.tone is CardTone.NOT_CHECKED


def test_manager_match_turns_the_authority_line_ok():
    allowed = line(
        card_for(VARIANTS["authority_matches"]), CardRowKind.PERSON, "Allowed to rent it"
    )
    assert allowed.tone is CardTone.OK


def test_photo_from_another_building_is_a_red_flag_on_the_place_row():
    place = lines(card_for(VARIANTS["photo_elsewhere"]), CardRowKind.PLACE)
    assert place[0].tone is CardTone.RED_FLAG


@pytest.mark.parametrize(
    ("name", "tone"),
    [("not_indexed", CardTone.NOT_CHECKED), ("not_located", CardTone.NOT_SHOWN)],
)
def test_place_row_says_when_photos_could_not_be_checked_or_placed(name, tone):
    assert lines(card_for(VARIANTS[name]), CardRowKind.PLACE)[0].tone is tone


def test_rent_below_range_is_a_hold_line_never_a_red_flag():
    card = card_for(VARIANTS["forged"])
    assert line(card, CardRowKind.PRICE, "Rent vs record").tone is CardTone.HOLD


def test_rent_line_never_prints_figures_from_the_record():
    # The record's rents are sponsor data. The card says how the asked rent compares, no more.
    card = card_for(VARIANTS["forged"])
    for figure in ("1850", "1600", "2300"):
        assert figure not in all_text(card)


def test_no_payment_ask_found_is_an_ok_line():
    card = card_for(VARIANTS["no_rules"])
    assert line(card, CardRowKind.PRICE, "Payment ask").tone is CardTone.OK


def test_other_check_memory_hit_adds_dated_line_without_case_id():
    card = card_for(VARIANTS["seen_in_another_check"])
    place = line(card, CardRowKind.PLACE, "Seen before")
    assert "2026-11-12" in place.text
    assert place.tone is CardTone.HOLD
    # The reply photo was seen too, with no date on record: still a line, still no case named.
    person = line(card, CardRowKind.PERSON, "Seen before")
    assert person.tone is CardTone.HOLD
    for text in (place.text, person.text):
        assert "fx-" not in text
        assert "7Q2M" not in text


def test_card_expires_24_hours_after_it_was_checked():
    card = card_for(modules())
    assert card.expires_at - card.checked_at == timedelta(hours=24)


def test_verify_link_uses_the_short_public_id():
    card = card_for(modules())
    assert card.case_id == "7Q2M"
    assert card.verify_url == "http://localhost:5173/c/7Q2M"
    assert build_card(modules(), checked_at=CHECKED_AT).verify_url is None


def test_card_carries_the_data_source_label():
    assert card_for(modules(source="live")).source == "live"
