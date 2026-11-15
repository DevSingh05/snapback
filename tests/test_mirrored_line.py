"""Mirrored matches add a card warning and evidence detail without changing the verdict."""

from datetime import UTC, datetime

import pytest

from snapback.agent.place import write_evidence_file
from snapback.card import strings
from snapback.contracts import (
    CardRowKind,
    CardTone,
    DataSource,
    LocateResult,
    LocateStatus,
    ModuleEvidence,
    PhotoLocation,
)
from snapback.verdict import build_card, decide, to_evidence

CHECKED_AT = datetime(2026, 11, 14, tzinfo=UTC)
PLACED = (LocateStatus.LOCATED_IN_CLAIMED, LocateStatus.LOCATED_ELSEWHERE)
UNPLACED = (LocateStatus.NOT_LOCATED, LocateStatus.NOT_INDEXED)
EXPECTED = {
    "en": (
        "Mirrored",
        "{flipped} of {total} photos match this building only when flipped left to right. "
        "Copied ads are often mirrored to dodge photo checks.",
    ),
    "es": (
        "Invertida",
        "{flipped} de {total} fotos coinciden con este edificio solo al invertirlas de "
        "izquierda a derecha. Los anuncios copiados suelen invertirse para evadir la "
        "comprobación de fotos.",
    ),
}


def modules_for(*photos: PhotoLocation) -> ModuleEvidence:
    return ModuleEvidence(
        case_id="fx-mirrored",
        source=DataSource.FIXTURE,
        locate=LocateResult(
            case_id="fx-mirrored",
            claimed_property_id="fx-building",
            photos=list(photos),
            thresholds_version="fx-thresholds",
        ),
    )


@pytest.mark.parametrize("lang", ["en", "es"])
@pytest.mark.parametrize("status", PLACED)
def test_mirrored_line_follows_real_with_hold_tone(lang, status):
    modules = modules_for(PhotoLocation(photo_id="fx-photo", status=status, flipped=True))
    card = build_card(modules, checked_at=CHECKED_AT, lang=lang)
    lines = next(row.lines for row in card.rows if row.kind is CardRowKind.PLACE)
    label, text = EXPECTED[lang]
    assert lines[0].label == strings.text("label.real", lang)
    assert lines[1].label == label
    assert lines[1].tone is CardTone.HOLD
    assert lines[1].text == text.format(flipped=1, total=1)
    assert sum(line.label == label for line in lines) == 1


@pytest.mark.parametrize("lang", ["en", "es"])
def test_one_mirrored_line_counts_only_photos_placed_here_and_uses_all_photos_as_total(lang):
    """\"Match this building\": a flipped photo placed in ANOTHER building is not counted (it has the
    red different-building line already)."""
    photos = [
        PhotoLocation(photo_id=f"fx-photo-{i}", status=status, flipped=flipped)
        for i, (status, flipped) in enumerate(
            [
                (LocateStatus.LOCATED_IN_CLAIMED, True),
                (LocateStatus.LOCATED_ELSEWHERE, True),
                (LocateStatus.NOT_LOCATED, True),
                (LocateStatus.NOT_INDEXED, True),
                (LocateStatus.LOCATED_IN_CLAIMED, False),
            ]
        )
    ]
    modules = modules_for(*photos)
    modules.matched_office = "Fixture Office LLC"
    card = build_card(modules, checked_at=CHECKED_AT, lang=lang)
    lines = next(row.lines for row in card.rows if row.kind is CardRowKind.PLACE)
    label, text = EXPECTED[lang]
    assert lines[1].label == label
    assert lines[1].text == text.format(flipped=1, total=5)
    assert sum(line.label == label for line in lines) == 1
    assert lines[2].label == strings.text("label.matched_home", lang)


@pytest.mark.parametrize("lang", ["en", "es"])
@pytest.mark.parametrize("status", PLACED)
@pytest.mark.parametrize("flipped", [None, False])
def test_no_mirrored_line_without_a_flipped_match(lang, status, flipped):
    modules = modules_for(PhotoLocation(photo_id="fx-photo", status=status, flipped=flipped))
    card = build_card(modules, checked_at=CHECKED_AT, lang=lang)
    assert all(line.label != EXPECTED[lang][0] for row in card.rows for line in row.lines)


@pytest.mark.parametrize("status", UNPLACED)
def test_unplaced_flipped_photo_does_not_add_mirrored_line(status):
    modules = modules_for(PhotoLocation(photo_id="fx-photo", status=status, flipped=True))
    card = build_card(modules, checked_at=CHECKED_AT)
    assert all(line.label != "Mirrored" for row in card.rows for line in row.lines)


@pytest.mark.parametrize("status", [*PLACED, *UNPLACED])
@pytest.mark.parametrize("flipped", [None, False])
def test_flipped_does_not_change_decide_or_card_state(status, flipped):
    photo = PhotoLocation(photo_id="fx-photo", status=status, flipped=flipped)
    plain = modules_for(photo)
    mirrored = modules_for(photo.model_copy(update={"flipped": True}))
    assert decide(to_evidence(mirrored)) == decide(to_evidence(plain))
    assert (
        build_card(mirrored, checked_at=CHECKED_AT).state
        == build_card(plain, checked_at=CHECKED_AT).state
    )


def test_write_evidence_file_preserves_flipped_for_each_photo():
    modules = modules_for(
        *[
            PhotoLocation(
                photo_id=f"fx-photo-{i}",
                status=LocateStatus.LOCATED_IN_CLAIMED,
                flipped=flipped,
            )
            for i, flipped in enumerate([True, False, None])
        ]
    )
    evidence = write_evidence_file(modules.case_id, modules.source, modules.locate)
    assert [photo.flipped for photo in evidence.photos] == [True, False, None]
