"""A loose match (#10): enough matched points to name a building, too few of them consistent.
A ChatGPT-edited photo looked like this. It is not placed, and the card says why."""

from datetime import UTC, datetime

import pytest

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
from snapback.vision.locate.locate import loose, passes_strict
from snapback.vision.locate.thresholds import load_thresholds
from snapback.vision.locate.verify import Verification

T = load_thresholds()
CHECKED_AT = datetime(2026, 11, 14, tzinfo=UTC)
LABEL = {"en": "Loose match", "es": "Coincidencia débil"}


def test_the_edited_photo_is_a_near_miss_not_a_placement():
    edited = Verification(matches=140, inliers=60, homography=None, spread=0.163)
    assert loose(edited, T) and not passes_strict(edited, T)


def test_an_honest_match_and_noise_are_not_loose():
    honest = Verification(matches=602, inliers=582, homography=None, spread=0.333)
    noise = Verification(matches=40, inliers=7, homography=None, spread=0.02)
    assert not loose(honest, T) and not loose(noise, T)
    few = Verification(matches=100, inliers=40, homography=None, spread=0.3)  # under 50 inliers
    narrow = Verification(matches=140, inliers=60, homography=None, spread=0.1)
    assert not loose(few, T) and not loose(narrow, T)


def modules_for(*photos: PhotoLocation) -> ModuleEvidence:
    return ModuleEvidence(
        case_id="fx-loose",
        source=DataSource.FIXTURE,
        locate=LocateResult(
            case_id="fx-loose",
            claimed_property_id=None,
            photos=list(photos),
            thresholds_version="fx-thresholds",
        ),
    )


def place_lines(modules: ModuleEvidence, lang: str):
    card = build_card(modules, checked_at=CHECKED_AT, lang=lang)
    return next(row.lines for row in card.rows if row.kind is CardRowKind.PLACE)


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_loose_photo_gets_a_hold_line_with_counts(lang):
    modules = modules_for(
        PhotoLocation(photo_id="p1", status=LocateStatus.NOT_LOCATED, bar_failed="loose"),
        PhotoLocation(photo_id="p2", status=LocateStatus.NOT_LOCATED, bar_failed="inliers"),
    )
    lines = [line for line in place_lines(modules, lang) if line.label == LABEL[lang]]
    assert len(lines) == 1
    assert lines[0].tone is CardTone.HOLD
    assert "1" in lines[0].text and "2" in lines[0].text


@pytest.mark.parametrize("lang", ["en", "es"])
def test_no_loose_photo_no_line(lang):
    modules = modules_for(
        PhotoLocation(photo_id="p1", status=LocateStatus.NOT_LOCATED, bar_failed="inliers")
    )
    assert not any(line.label == LABEL[lang] for line in place_lines(modules, lang))


def test_the_line_never_changes_the_verdict():
    """Code sets the verdict from the evidence; the loose line only explains a non-placement."""
    loose_case = modules_for(
        PhotoLocation(photo_id="p1", status=LocateStatus.NOT_LOCATED, bar_failed="loose")
    )
    plain_case = modules_for(
        PhotoLocation(photo_id="p1", status=LocateStatus.NOT_LOCATED, bar_failed="inliers")
    )
    assert decide(to_evidence(loose_case)) == decide(to_evidence(plain_case))


@pytest.mark.parametrize("lang", ["en", "es"])
def test_with_nothing_placed_the_loose_match_leads_the_row(lang):
    """The iMessage reply shows a row's first line; the reason has to be that line."""
    modules = modules_for(
        PhotoLocation(photo_id="p1", status=LocateStatus.NOT_LOCATED, bar_failed="loose")
    )
    assert place_lines(modules, lang)[0].label == LABEL[lang]


@pytest.mark.parametrize("lang", ["en", "es"])
def test_an_honest_low_ratio_photo_does_not_get_the_edited_line(lang):
    """An ad that gives its address checks the claimed home, where a plain ratio miss sets "ratio".
    That is an honest photo that just fell short; it must never read 'may be edited or AI-made'."""
    modules = modules_for(
        PhotoLocation(photo_id="p1", status=LocateStatus.NOT_LOCATED, bar_failed="ratio")
    )
    lines = place_lines(modules, lang)
    assert not any(line.label == LABEL[lang] for line in lines)
    assert not any("AI" in line.text or "IA" in line.text for line in lines)
