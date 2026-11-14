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
    "Not checked. The home in these photos is listed by its office on CoStar's record: "
    f"{OFFICE}. We can't tell you if it is offered, or at this price."
)
ES = (
    "No comprobado. La vivienda de estas fotos figura con esta oficina en el registro de CoStar: "
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


class StubLookups:
    """Records by id, as the real lookups return them."""

    def __init__(self, companies):
        from snapback.contracts import PropertyRecord

        self._records = {
            pid: PropertyRecord(property_id=pid, source=DataSource.FIXTURE, manager_company=name)
            for pid, name in companies.items()
        }

    def record(self, pid):
        return self._records.get(pid)


@pytest.mark.parametrize(
    "name",
    [
        "1234 Main Street",
        "500 Westheimer Rd Suite 4",
        "77 Sunset Blvd",
        "9 Oak Ln",
        "  100 N Loop Fwy W  ",
        "1 Kirby Drive Management",
    ],
)
def test_an_office_shaped_like_a_street_address_is_never_shown(name):
    locate = evidence().locate  # photo 0 is elsewhere, matched to fx-prop-3
    assert matched_office_of(StubLookups({"fx-prop-3": name}), locate) is None


@pytest.mark.parametrize(
    "name",
    ["4821 Quillfeather LLC", "77 Maple Holdings", "123456 Oak Partners", "9 Heron Group Inc"],
)
def test_a_name_that_starts_with_a_bare_number_is_never_shown(name):
    # "<number> <street> LLC" is an address wearing a company suffix.
    assert matched_office_of(StubLookups({"fx-prop-3": name}), evidence().locate) is None


def test_a_name_whose_first_two_words_are_the_records_street_address_is_never_shown():
    from snapback.contracts import PropertyRecord

    class Lookups:
        def record(self, pid):
            return PropertyRecord(
                property_id=pid,
                source=DataSource.FIXTURE,
                manager_company="One Quillfeather Partners",
                street_address="One Quillfeather Plaza",
            )

    assert matched_office_of(Lookups(), evidence().locate) is None


def test_a_name_that_only_shares_one_word_with_the_street_address_is_kept():
    from snapback.contracts import PropertyRecord

    class Lookups:
        def record(self, pid):
            return PropertyRecord(
                property_id=pid,
                source=DataSource.FIXTURE,
                manager_company="Quillfeather Partners",
                street_address="One Quillfeather Plaza",
            )

    assert matched_office_of(Lookups(), evidence().locate) == "Quillfeather Partners"


def test_demo_case_b_shows_the_office_of_the_home_its_third_photo_was_placed_in():
    from snapback.agent.demo import run_demo_case

    _, card = run_demo_case("b", checked_at=CHECKED_AT)
    place = next(r for r in card.rows if r.kind is CardRowKind.PLACE)
    lines = [ln for ln in place.lines if ln.label == "Home in the photos"]
    assert len(lines) == 1
    assert "Lantern Row Property Group" in lines[0].text
    assert "for rent" not in lines[0].text.lower()


@pytest.mark.parametrize(
    "name", ["Fixture Property Management Co", "Greystar Real Estate Partners", "ABC 123 Homes LLC"]
)
def test_a_company_name_is_kept(name):
    assert matched_office_of(StubLookups({"fx-prop-3": name}), evidence().locate) == name


def test_only_a_photo_placed_elsewhere_counts_not_one_placed_in_the_claimed_home():
    base = evidence().locate
    claimed = base.photos[0].model_copy(
        update={
            "status": LocateStatus.LOCATED_IN_CLAIMED,
            "matched_property_id": "fx-prop-4",  # a stray id on a claimed photo
        }
    )
    elsewhere = base.photos[0].model_copy(
        update={
            "photo_id": "l9",
            "status": LocateStatus.LOCATED_ELSEWHERE,
            "matched_property_id": "fx-prop-3",
        }
    )
    locate = base.model_copy(update={"photos": [claimed, elsewhere]})
    lookups = KitLookups(DataSource.FIXTURE)
    assert matched_office_of(lookups, locate) == OFFICE  # fx-prop-3, not fx-prop-4's company
    only_claimed = base.model_copy(update={"photos": [claimed]})
    assert matched_office_of(lookups, only_claimed) is None


def test_joined_modules_matched_office_is_the_real_path():
    from snapback.agent.intake import read_listing
    from snapback.agent.join import JoinedModules

    lookups = KitLookups(DataSource.FIXTURE)
    listing = read_listing("Nice 1 bed, $1,500 a month", [])
    modules = JoinedModules(
        stand_in=None,
        listing=listing,
        record=None,
        for_sale=None,
        salt="x",
        record_source=None,
        lookups=lookups,
    )
    assert modules.matched_office("fx-1", evidence().locate) == OFFICE
    assert modules.matched_office("fx-1", None) is None

    class Broken:
        def record(self, pid):
            raise RuntimeError("lookup down")

    broken = JoinedModules(
        stand_in=None,
        listing=listing,
        record=None,
        for_sale=None,
        salt="x",
        record_source=None,
        lookups=Broken(),
    )
    assert broken.matched_office("fx-1", evidence().locate) is None  # the line is left out
