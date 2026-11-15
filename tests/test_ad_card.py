"""Ad vs record, step 4: the card row, the plan option, and the rule that a note never moves a
verdict. Synthetic records only."""

import json
import random
import re
from datetime import date, datetime
from pathlib import Path

import pytest

from snapback.agent import CaseSession, FixtureModules, PolicyChooser, Trace, run_case
from snapback.agent.demo import demo_case_ids, demo_modules, load_demo_case
from snapback.agent.intake import read_listing
from snapback.agent.join import JoinedModules, KitLookups
from snapback.agent.planner import PlanKind
from snapback.agent.rules.contact import FIXTURE_PHONE_SALT
from snapback.card import strings
from snapback.contracts import (
    AdNote,
    Card,
    CardRowKind,
    CardTone,
    ChoiceKind,
    DataSource,
    ModuleEvidence,
    PropertyRecord,
)
from snapback.verdict import build_card, decide, to_evidence

TODAY = date(2026, 11, 14)
CHECKED_AT = datetime.fromisoformat("2026-11-14T10:00:00-05:00")
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
KIT = Path(__file__).resolve().parents[1] / "fixtures" / "adapters" / "costar-claims-kit"
CLAIMS = CardRowKind.CLAIMS

CARPET_HOME = PropertyRecord(
    property_id="fx-home-1",
    source=DataSource.FIXTURE,
    floors_photos=["carpet"],
    floor_photo_count=4,
    floors_listing=["carpet", "tile"],
    pool_on_record=False,
    manager_since=date(2019, 3, 1),
    sale_history_known=True,
)
AD = "Hardwood floors, private pool. Now under new management! The house just sold."


def modules_for(ad: str, record: PropertyRecord = CARPET_HOME) -> FixtureModules:
    stand_in = FixtureModules(ad_text=ad, today=TODAY)
    stand_in.record = record
    return stand_in


def run(modules: FixtureModules, lang: str = "en") -> tuple[CaseSession, Card]:
    session = CaseSession("fx-1", modules, Trace("fx-1", DataSource.FIXTURE), rng=random.Random(3))
    run_case(session, PolicyChooser(), lambda draft: "send")
    return session, build_card(session.evidence, checked_at=CHECKED_AT, lang=lang)


def claims_lines(card: Card) -> list[tuple[CardTone, str]]:
    row = next((r for r in card.rows if r.kind is CLAIMS), None)
    return [(item.tone, item.text) for item in row.lines] if row else []


# --- the row ----------------------------------------------------------------------------------


def test_the_ad_says_x_and_the_record_shows_y_in_a_fourth_row():
    _, card = run(modules_for(AD))
    assert [row.kind for row in card.rows] == [
        CardRowKind.PLACE,
        CardRowKind.PERSON,
        CardRowKind.PRICE,
        CLAIMS,
    ]
    shown = claims_lines(card)
    assert len(shown) == 3  # the cap: four things disagree, three are said
    assert all(tone is CardTone.NOT_SHOWN for tone, _ in shown)
    assert shown[0][1] == (
        "Not confirmed. The ad says new management. CoStar's record shows the same property "
        "manager since 2019 (as of CoStar's last research)."
    )
    assert shown[1][1] == (
        "Not confirmed. The ad says the home just sold. CoStar's record shows no sale in the "
        "last 12 months (as of CoStar's last research)."
    )
    assert shown[2][1] == (
        "Not confirmed. The ad says hardwood floors. CoStar's photos of this home are labelled "
        "carpet (as of CoStar's last research)."
    )


def test_the_same_lines_in_spanish():
    _, card = run(modules_for(AD), "es")
    shown = claims_lines(card)
    assert len(shown) == 3 and card.lang == "es"
    assert all(text.startswith("Sin confirmar. El anuncio dice") for _, text in shown)
    assert "según la última investigación de CoStar" in shown[0][1]
    row = next(r for r in card.rows if r.kind is CLAIMS)
    assert strings.text("row.claims", "es") == "LO QUE DICE EL ANUNCIO" and row.lines


def test_a_quiet_confirming_line_reads_plainly_and_is_alone():
    record = PropertyRecord(
        property_id="fx-home-2",
        source=DataSource.FIXTURE,
        floors_listing=["wood"],
        pool_on_record=True,
        yard_on_record=True,
    )
    _, card = run(modules_for("Hardwood floors, pool and a fenced yard", record))
    shown = claims_lines(card)
    (tone, text) = shown[0]
    # one confirming line, then the aerial date the exterior claims earn (a date, not a claim)
    assert len(shown) == 2 and tone is CardTone.OK
    assert shown[1][1].startswith("Not checked. An aerial photo of this property from 2025-06-01")
    assert text == (
        "The ad says hardwood floors. CoStar's record of this home also names hardwood floors "
        "(as of CoStar's last research)."
    )


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        (
            "en",
            "The ad says 3 bedrooms. CoStar's record of this home agrees (as of CoStar's last "
            "research).",
        ),
        ("es", "3 recámaras"),
    ],
)
def test_a_bedroom_count_that_matches_names_the_number(lang, expected):
    # Issue #10 (Jeffrey's live dry run): the line read "The ad says  bedrooms".
    record = PropertyRecord(property_id="fx-home-3", source=DataSource.FIXTURE, beds_range=(3, 3))
    _, card = run(modules_for("3 bed house near the park", record), lang)
    texts = [text for _, text in claims_lines(card)]
    assert any(expected in text for text in texts), texts
    assert not any("  " in text for text in texts)


@pytest.mark.parametrize(
    ("lang", "expected"),
    [("en", ("The ad says 1 bedroom.", "1 bathroom.")), ("es", ("1 recámara.", "1 baño."))],
)
def test_one_bedroom_and_one_bathroom_are_singular(lang, expected):
    # Review of #257 (L1): the line read "The ad says 1 bedrooms".
    # Beds agree (the one quiet confirmation), baths differ, so both lines are shown.
    record = PropertyRecord(
        property_id="fx-home-4", source=DataSource.FIXTURE, beds_range=(1, 1), baths_range=(3, 3)
    )
    _, card = run(modules_for("1 bed, 1 bath condo near the park", record), lang)
    texts = " ".join(text for _, text in claims_lines(card))
    for words in expected:
        assert words in texts, texts
    assert "1 bedrooms" not in texts and "1 bathrooms" not in texts
    assert "1 recámaras" not in texts and "1 baños" not in texts


def test_no_claims_row_when_the_record_is_silent_or_the_ad_says_nothing_checkable():
    quiet = PropertyRecord(property_id="fx-home-3", source=DataSource.FIXTURE)
    for ad, record in (("Hardwood floors, pool", quiet), ("Nice home near the park", CARPET_HOME)):
        _, card = run(modules_for(ad, record))
        assert len(card.rows) == 3 and claims_lines(card) == []


def test_the_pretext_line_names_the_office_and_never_the_person():
    record = PropertyRecord(
        property_id="fx-bldg-9",
        source=DataSource.FIXTURE,
        website_host="fx-oak.example",
        manager_company="Fixture Living LLC",
    )
    _, card = run(
        modules_for("Owner is out of town so I can't show it. Text Dana at 555-0100.", record)
    )
    shown = claims_lines(card)
    assert len(shown) == 1
    text = shown[0][1]
    assert "leasing office" in text and "Dana" not in text and "Fixture Living" not in text
    assert "scam" not in text.lower() and "lying" not in text.lower()


def test_every_claims_word_comes_from_the_string_table(monkeypatch):
    markers = {key: f"<{key}>" for key in strings.TABLES["en"]}
    monkeypatch.setitem(strings.TABLES, "en", markers)
    _, card = run(modules_for(AD))
    row = next(r for r in card.rows if r.kind is CLAIMS)
    for item in row.lines:
        assert re.fullmatch(r"<[a-z0-9_.]+>", item.text) and re.fullmatch(r"<[a-z_.]+>", item.label)


BAD = ("safe", "verified", "scam", "estafa", "seguro", "verificado", "fraud", "liar", "lying")
FAIR_HOUSING = ("neighborhood", "neighbourhood", "school", "crime", "tenant", "family", "vecind")


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_claims_wording_has_no_forbidden_word(lang):
    table = strings.TABLES[lang]
    mine = {k: v for k, v in table.items() if k.startswith(("claims.", "claimword.", "kind."))}
    assert mine
    for key, value in mine.items():
        low = value.lower()
        assert not any(word in low for word in BAD + FAIR_HOUSING), key
        assert "\u2014" not in value and "\u2013" not in value, key


def test_english_and_spanish_have_the_same_keys_and_blanks():
    def blanks(text: str) -> set[str]:
        return set(re.findall(r"\{(\w+)\}", text))

    en, es = strings.TABLES["en"], strings.TABLES["es"]
    mine = {k for k in en if k.startswith(("claims.", "claimword.", "kind.", "list."))}
    assert mine == {k for k in es if k.startswith(("claims.", "claimword.", "kind.", "list."))}
    for key in mine:
        assert blanks(en[key]) == blanks(es[key]), key


# --- the verdict never moves -------------------------------------------------------------------


def test_a_mismatch_alone_leaves_the_verdict_and_the_other_rows_identical():
    plain_session, plain = run(modules_for("Nice home near the park"))
    session, card = run(modules_for(AD))
    assert claims_lines(card) and not claims_lines(plain)
    assert session.verdict == plain_session.verdict
    assert card.state == plain.state
    assert card.rows[:3] == plain.rows[:3]


@pytest.mark.parametrize("case_id", ["a", "b", "c"])
def test_the_staged_cases_decide_the_same_with_a_mismatch_added(case_id):
    case = load_demo_case(case_id)
    listing = read_listing(case.listing_text)

    def go(extra: list[AdNote]):
        session = CaseSession(
            f"fx-demo-{case_id}",
            demo_modules(case, listing),
            Trace(f"fx-demo-{case_id}", DataSource.FIXTURE),
            rng=random.Random(3),
        )
        verdict = run_case(session, PolicyChooser(), lambda draft: "send")
        evidence = session.evidence.model_copy(update={"ad_notes": extra})
        return verdict, decide(to_evidence(evidence)), build_card(evidence, checked_at=CHECKED_AT)

    note = AdNote(key="sale_none", claim="just_sold", pretext=True)
    base, base_decided, base_card = go([])
    moved, moved_decided, moved_card = go([note, AdNote(key="pool_none", claim="pool")])
    assert moved == base and moved_decided == base_decided
    assert moved_card.state == base_card.state
    assert moved_card.rows[:3] == base_card.rows[:3] and len(moved_card.rows) == 4
    assert case_id in demo_case_ids()


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("module_evidence_*.json")))
def test_decide_ignores_the_notes_for_every_evidence_fixture(name):
    base = ModuleEvidence.model_validate_json((FIXTURES / name).read_text())
    notes = [
        AdNote(key="sale_none", claim="just_sold", pretext=True),
        AdNote(key="manager_same", claim="new_management", pretext=True, year=2019),
        AdNote(key="floor_photos", claim="floor_wood", record=["carpet"]),
    ]
    with_notes = base.model_copy(update={"ad_notes": notes})
    assert decide(to_evidence(with_notes)) == decide(to_evidence(base))


# --- the plan option ---------------------------------------------------------------------------


def test_the_comparison_is_offered_only_with_claims_the_record_answers():
    def options(modules: FixtureModules) -> list[str]:
        case = CaseSession("fx-1", modules, Trace("fx-1", DataSource.FIXTURE), rng=random.Random(3))
        case.choose_default()
        offer = case.offer()
        assert offer is not None and offer.kind is ChoiceKind.NEXT_CHECK
        return list(offer.options)

    assert PlanKind.CLAIMS.value in options(modules_for(AD))
    assert PlanKind.CLAIMS.value not in options(modules_for("Nice home"))
    assert PlanKind.CLAIMS.value not in options(FixtureModules())  # no ad text at all


def test_a_comparison_that_breaks_is_not_offered_and_the_case_still_finishes():
    class Broken(FixtureModules):
        def ad_notes(self, case_id):
            raise RuntimeError("boom")

    session, card = run(Broken(ad_text=AD, today=TODAY))
    assert claims_lines(card) == [] and session.verdict is not None


class Model:
    chosen_by = "model"

    def choose(self, offer):
        return offer.options[-1], "Chosen for the facts shown."


def test_a_model_may_reorder_it_but_the_evidence_and_the_notes_are_the_same():
    policy, _ = run(modules_for(AD))
    session = CaseSession(
        "fx-1", modules_for(AD), Trace("fx-1", DataSource.FIXTURE), rng=random.Random(3)
    )
    run_case(session, Model(), lambda draft: "send")
    assert session.evidence.ad_notes == policy.evidence.ad_notes
    assert session.verdict == policy.verdict


def test_the_plan_step_is_stamped_by_code_where_the_menu_has_one_option():
    session, _ = run(modules_for(AD))
    steps = [e for e in session.trace.events if e.choice is ChoiceKind.NEXT_CHECK]
    picked = next(e for e in steps if e.pick == PlanKind.CLAIMS.value)
    assert picked.chosen_by == "policy"


# --- the live join -----------------------------------------------------------------------------


def test_the_joined_modules_compare_the_ad_with_the_kit_record():
    lookups = KitLookups(DataSource.FIXTURE, KIT)
    listing = read_listing("Hardwood floors, private pool, pet friendly. 2 bed, 1,100 sq ft.")
    joined = JoinedModules(
        stand_in=None,
        listing=listing,
        record=lookups.record("9101"),
        for_sale=None,
        salt=FIXTURE_PHONE_SALT,
        record_source=DataSource.FIXTURE,
    )
    keys = [n.key for n in joined.ad_notes("fx-1")]
    assert keys == ["floor_photos", "pool_none", "pets_no"]


def test_the_ad_notes_json_roundtrips():
    note = AdNote(key="floor_photos", claim="floor_wood", record=["carpet"])
    assert AdNote.model_validate(json.loads(note.model_dump_json())) == note


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_card_picture_draws_the_claims_row(lang):
    from snapback.card.render import render_card

    with_row = run(modules_for(AD), lang)[1]
    without = run(modules_for("Nice home near the park"), lang)[1]
    drawn, plain = render_card(with_row), render_card(without)
    assert drawn.png.startswith(b"\x89PNG") and drawn.height > plain.height


def test_a_buildings_parking_and_the_aerial_date_in_both_languages():
    record = PropertyRecord(
        property_id="fx-bldg-9",
        source=DataSource.FIXTURE,
        parking_ratio=1.5,
        pool_on_record=False,
    )
    ad = "Covered parking and a private pool"
    en = [text for _, text in claims_lines(run(modules_for(ad, record))[1])]
    es = [text for _, text in claims_lines(run(modules_for(ad, record), "es")[1])]
    assert len(en) == len(es) == 3
    assert en[0].startswith("Not confirmed. The ad says a pool.")
    assert "about 1.5 spaces per unit (as of CoStar's last research)" in en[1]
    assert en[2] == (
        "Not checked. An aerial photo of this property from 2025-06-01 (Vexcel) is on file; "
        "nothing is read from it."
    )
    assert "unos 1.5 lugares por unidad" in es[1]
    assert es[2].startswith(
        "No comprobado. Hay una foto aérea de esta propiedad del 2025-06-01 (Vexcel)"
    )


def test_the_aerial_line_has_a_neutral_tone_and_the_pool_line_names_no_photos():
    record = PropertyRecord(property_id="fx-h", source=DataSource.FIXTURE, pool_on_record=False)
    shown = claims_lines(run(modules_for("Private pool", record))[1])
    assert [tone for tone, _ in shown] == [CardTone.NOT_SHOWN, CardTone.NOT_CHECKED]
    assert shown[0][1] == (
        "Not confirmed. The ad says a pool. CoStar's record of this home does not list or show "
        "a pool (as of CoStar's last research)."
    )
    assert "photos" not in shown[0][1]


def test_running_the_claims_step_adds_only_the_notes():
    from snapback.agent.planner import Plan

    plan = Plan(modules_for(AD), "fx-1")
    assert set(plan.run(PlanKind.CLAIMS)) == {"ad_notes"}


def test_a_note_leaves_a_case_that_reaches_hold_exactly_as_it_was():
    from snapback.contracts import ForSaleMatch, ForSaleStatus, VerdictState

    def hold(ad: str):
        modules = modules_for(ad)
        modules._for_sale = ForSaleMatch(status=ForSaleStatus.ACTIVE, offices=["Fixture Realty"])
        return run(modules)

    plain_session, plain = hold("Nice home near the park")
    session, card = hold(AD)
    assert plain.state is VerdictState.HOLD and card.state is VerdictState.HOLD
    assert claims_lines(card) and session.verdict == plain_session.verdict
    assert card.rows[:3] == plain.rows[:3]
