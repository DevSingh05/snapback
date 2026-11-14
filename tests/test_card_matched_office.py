"""X1, the card part: a photo placed in a different home names that home's office on CoStar's
record. It is information only: the verdict never reads it."""

import inspect
import random
import re
from datetime import datetime
from pathlib import Path

import pytest

from snapback import verdict
from snapback.agent import CaseSession, FixtureModules, PolicyChooser, Trace, run_case
from snapback.agent.join import KitLookups, matched_office_of
from snapback.contracts import (
    CardRowKind,
    DataSource,
    LocateStatus,
    ModuleEvidence,
)
from snapback.verdict import build_card, decide, to_evidence

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CHECKED_AT = datetime.fromisoformat("2026-11-14T10:00:00-05:00")
OFFICE = "Fixture Property Management Co"
EN = (
    "The home in these photos is listed by its office on CoStar's record: "
    f"{OFFICE}. We can't tell you if it is offered, or at this price."
)
ES = (
    "La vivienda de estas fotos figura con esta oficina en el registro de CoStar: "
    f"{OFFICE}. No podemos decirle si se ofrece, ni a este precio."
)


def evidence(*, elsewhere=True, office=OFFICE) -> ModuleEvidence:
    base = ModuleEvidence.model_validate_json((FIXTURES / "module_evidence_hold.json").read_text())
    photos = [p.model_copy() for p in base.locate.photos]
    if elsewhere:
        photos[0] = photos[0].model_copy(
            update={
                "status": LocateStatus.LOCATED_ELSEWHERE,
                "matched_property_id": "fx-prop-3",
                "matched_model_id": "fx-model-b",
            }
        )
    locate = base.locate.model_copy(update={"photos": photos})
    return base.model_copy(update={"locate": locate, "matched_office": office})


def place_lines(m, lang="en"):
    card = build_card(m, checked_at=CHECKED_AT, lang=lang)
    return next(r for r in card.rows if r.kind is CardRowKind.PLACE).lines


def office_lines(m, lang="en"):
    return [ln for ln in place_lines(m, lang) if OFFICE in ln.text]


def test_a_photo_placed_elsewhere_names_that_homes_office_in_english():
    lines = office_lines(evidence())
    assert [ln.text for ln in lines] == [EN]


def test_and_in_spanish():
    assert [ln.text for ln in office_lines(evidence(), "es")] == [ES]


def test_no_line_without_an_office_or_without_a_photo_placed_elsewhere():
    assert office_lines(evidence(office=None)) == []
    assert office_lines(evidence(elsewhere=False)) == []


def test_the_line_is_information_not_a_finding_and_carries_no_banned_claim():
    (line,) = office_lines(evidence())
    assert line.tone.value == "not_checked"
    low = line.text.lower()
    for word in ("the real one", "available", "—", "–"):
        assert word not in low
    assert "can't tell you if it is offered" in low
    assert not re.search(r"\d{3}[\s.-]\d{3,4}|\b\d+ [A-Z][a-z]+ (St|Ave|Rd)\b", line.text)


def test_the_verdict_never_changes_with_the_office():
    base = decide(to_evidence(evidence(office=None)))
    for office in (OFFICE, "Another Company LLC", "x" * 500):
        v = decide(to_evidence(evidence(office=office)))
        assert v.state == base.state and v.reasons == base.reasons
        assert build_card(evidence(office=office), checked_at=CHECKED_AT).state == base.state


def test_mutant_a_decide_that_read_the_office_would_be_caught():
    # The state-choosing code must not mention the field at all.
    for fn in (verdict.decide, verdict.to_evidence):
        assert "matched_office" not in inspect.getsource(fn)


def test_the_office_comes_from_the_matched_homes_record_company_only():
    lookups = KitLookups(DataSource.FIXTURE)
    locate = evidence().locate
    assert matched_office_of(lookups, locate) == OFFICE
    in_claimed = evidence(elsewhere=False).locate
    assert matched_office_of(lookups, in_claimed) is None
    assert matched_office_of(lookups, None) is None
    assert matched_office_of(None, locate) is None


def test_an_unknown_matched_home_has_no_office():
    locate = evidence().locate
    photos = [p.model_copy(update={"matched_property_id": "fx-nope"}) for p in locate.photos]
    assert (
        matched_office_of(
            KitLookups(DataSource.FIXTURE), locate.model_copy(update={"photos": photos})
        )
        is None
    )


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_case_run_carries_the_office_from_the_modules_to_the_card(lang):
    stand_in = FixtureModules()
    stand_in.evidence = evidence()
    session = CaseSession("fx-1", stand_in, Trace("fx-1", DataSource.FIXTURE), rng=random.Random(3))
    run_case(session, PolicyChooser(), lambda draft: "send")
    assert session.evidence.matched_office == OFFICE
    card = build_card(session.evidence, checked_at=CHECKED_AT, lang=lang)
    assert any(OFFICE in ln.text for r in card.rows for ln in r.lines)


def test_the_card_never_says_for_rent():
    from snapback.card import strings

    for lang in ("en", "es"):
        card = build_card(evidence(), checked_at=CHECKED_AT, lang=lang)
        text = " ".join(ln.text for r in card.rows for ln in r.lines).lower()
        assert "for rent" not in text and "en alquiler" not in text.split(OFFICE.lower())[-1]
    en_table = strings._table("en")
    assert [k for k, v in en_table.items() if "for rent" in str(v).lower()] == []
