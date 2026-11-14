"""Search CoStar's researched places by budget and must-haves (council 4 core).

Synthetic data only: every id is fx-... or a fixture number, and the shared fixture kit under
fixtures/adapters/costar-kit/ is team-made. Nothing here reads the real kit.
"""

import json
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from snapback import search as search_module
from snapback.agent.join import KitLookups
from snapback.agent.planner import (
    NO_QUESTION,
    SEARCH_FACT_KEYS,
    TradeOff,
    deep_check_offer,
    plan_search,
    tradeoff_offer,
    tradeoffs_for,
)
from snapback.agent.runner import PolicyChooser
from snapback.contracts import (
    BudgetFit,
    DataSource,
    FloorPlanRent,
    PlaceMatch,
    PropertyRecord,
    RentalHouse,
    RenterBrief,
)
from snapback.search import (
    AmbiguousPlace,
    NoOfficeOnRecord,
    alternatives_for,
    draft_tour_request,
    place_for,
    price_text,
    search,
    search_places,
)

FORBIDDEN = (
    "neighborhood",
    "neighbourhood",
    "school",
    "safe",
    "crime",
    "family",
    "families",
    "kids",
    "children",
    "couple",
    "singles",
    "senior",
    "church",
    "walkable",
    "quiet",
    "good area",
    "downtown",
    "district",
    "desirable",
    "available now",
    "scam",
    "verified",
    "legit",
    "fraud",
)
PHONE = re.compile(r"\+?\d[\d\s().\-]{8,}\d")


class Fake:
    """Lookups with exactly the records a test hands in."""

    def __init__(self, records=(), rentals=(), source=DataSource.FIXTURE):
        self.source = source
        self._records = {r.property_id: r for r in records}
        self._rentals = list(rentals)

    def records(self):
        return self._records

    def rentals(self):
        return self._rentals


def building(pid="fx-b1", plans=(), **kw):
    return PropertyRecord(
        property_id=pid,
        source=DataSource.FIXTURE,
        property_type="multifamily",
        floor_plan_rents=list(plans),
        manager_company=kw.pop("manager_company", "Fixture Office Co"),
        **kw,
    )


def plan(name="1 bed / 1 bath", beds=1, lo=1000, hi=1200, **kw):
    return FloorPlanRent(
        name=name, beds=beds, baths=kw.pop("baths", 1.0), rent_min=lo, rent_max=hi, **kw
    )


@pytest.fixture(scope="module")
def kit():
    return KitLookups(DataSource.FIXTURE)


# --- budget vs the asking price ----------------------------------------------------------------


def test_budget_is_compared_with_the_asking_price_not_a_band():
    # The record's band says $900 to $3,000; only the floor plan's own asking price counts.
    record = building(plans=[plan(lo=1450, hi=1600)], rent_min=900, rent_max=3000, rent_median=1000)
    (hit,) = search_places(RenterBrief(max_rent_month=1600), Fake([record]))
    assert hit.budget_fit is BudgetFit.WITHIN
    assert search_places(RenterBrief(max_rent_month=1400), Fake([record])) == []


def test_low_end_inside_and_high_end_outside_is_starts_within_not_within():
    (hit,) = search_places(
        RenterBrief(max_rent_month=1500), Fake([building(plans=[plan(lo=1450, hi=1600)])])
    )
    assert hit.budget_fit is BudgetFit.STARTS_WITHIN


def test_per_bed_floor_plan_is_never_compared_with_a_whole_unit_budget():
    record = building(plans=[plan(name="4 bed / 4 bath", beds=4, lo=700, hi=850, per_bed=True)])
    assert search_places(RenterBrief(max_rent_month=5000), Fake([record])) == []
    assert search(RenterBrief(max_rent_month=5000), Fake([record])).n_considered == 0


def test_a_missing_price_end_says_no_full_price_and_is_not_within_budget():
    record = building(plans=[plan(lo=1100, hi=None)])
    (hit,) = search_places(RenterBrief(max_rent_month=1500), Fake([record]))
    assert hit.budget_fit is BudgetFit.NO_FULL_PRICE
    assert hit.price_text.startswith("No full price on record")
    assert hit.price_text == price_text(1100, None)


def test_a_known_end_over_budget_removes_a_half_priced_place():
    assert (
        search_places(
            RenterBrief(max_rent_month=1000), Fake([building(plans=[plan(lo=1100, hi=None)])])
        )
        == []
    )
    assert (
        search_places(
            RenterBrief(max_rent_month=1000), Fake([building(plans=[plan(lo=None, hi=1100)])])
        )
        == []
    )


def test_a_place_with_no_price_at_all_is_not_a_place():
    assert search_places(RenterBrief(), Fake([building(plans=[plan(lo=None, hi=None)])])) == []


def test_price_text_carries_the_as_of_label_and_never_an_en_dash():
    assert price_text(1450, 1600) == "$1,450 to $1,600 a month as of CoStar's last research"
    assert price_text(1450, 1450) == "$1,450 a month as of CoStar's last research"
    assert "–" not in price_text(1, 2) and "—" not in price_text(1, 2)


# --- filters -----------------------------------------------------------------------------------


def test_beds_and_baths_minimums():
    record = building(
        plans=[
            plan("studio / 1 bath", 0),
            plan("2 bed / 2 bath", 2, baths=2.0),
            plan("2 bed / 1 bath", 2),
        ]
    )
    got = search_places(RenterBrief(beds_min=2, baths_min=2.0), Fake([record]))
    assert [m.floor_plan for m in got] == ["2 bed / 2 bath"]
    assert len(search_places(RenterBrief(beds_min=0), Fake([record]))) == 3


def test_walkup_need_removes_a_known_walkup_but_keeps_an_unknown_one_labelled():
    walkup = building("fx-w", [plan()], is_walkup=True)
    flat = building("fx-f", [plan()], is_walkup=False, has_elevator=True)
    unknown = building("fx-u", [plan()])
    got = search_places(RenterBrief(needs_no_walkup=True), Fake([walkup, flat, unknown]))
    assert {m.property_id for m in got} == {"fx-f", "fx-u"}
    by_id = {m.property_id: m for m in got}
    assert by_id["fx-f"].musts_met == 1
    assert by_id["fx-u"].musts_met == 0
    assert "not on record" in by_id["fx-u"].must_haves[0].text


def test_parking_and_utilities_lines_come_from_the_record():
    record = building(plans=[plan()], parking_ratio=1.5, metering="individual")
    (hit,) = search_places(RenterBrief(needs_parking=True), Fake([record]))
    keys = {line.key: line for line in hit.must_haves}
    assert keys["parking"].met is True and "1.5 spaces per unit" in keys["parking"].text
    assert "pays their own utilities" in keys["utilities"].text
    master = building("fx-m", [plan()], metering="master")
    (m,) = search_places(RenterBrief(), Fake([master]))
    assert "Master metered" in {line.key: line for line in m.must_haves}["utilities"].text


def test_pets_removes_only_a_house_that_says_no_and_apartments_say_not_on_record():
    yes = RentalHouse(
        property_id="fx-h1", source=DataSource.FIXTURE, rent_min=1500, rent_max=1500, pets_ok=True
    )
    no = yes.model_copy(update={"property_id": "fx-h2", "pets_ok": False})
    apt = building(plans=[plan()])
    got = search_places(RenterBrief(pets=True), Fake([apt], [yes, no]))
    assert {m.property_id for m in got} == {"fx-b1", "fx-h1"}
    apartment = next(m for m in got if m.kind == "apartment")
    assert [line.met for line in apartment.must_haves if line.key == "pets"] == [None]
    assert apartment.musts_met == 0


def test_move_in_by_removes_a_late_house_and_an_apartment_with_none_reported():
    soon = RentalHouse(
        property_id="fx-h1",
        source=DataSource.FIXTURE,
        rent_min=1,
        rent_max=2,
        available_on=date(2026, 12, 1),
    )
    late = soon.model_copy(update={"property_id": "fx-h2", "available_on": date(2027, 3, 1)})
    unknown = soon.model_copy(update={"property_id": "fx-h3", "available_on": None})
    full = building("fx-full", [plan(units_available=0)])
    open_ = building("fx-open", [plan(units_available=2)])
    got = search_places(
        RenterBrief(move_in_by=date(2026, 12, 31)), Fake([full, open_], [soon, late, unknown])
    )
    assert {m.property_id for m in got} == {"fx-h1", "fx-h3", "fx-open"}


def test_availability_text_is_reported_as_of_never_now():
    record = building(
        plans=[
            plan(units_available=3),
            plan("2 bed / 2 bath", 2, units_available=0),
            plan("3 bed / 2 bath", 3),
        ]
    )
    texts = sorted(m.availability_text for m in search_places(RenterBrief(), Fake([record])))
    assert "3 units reported available as of CoStar's last research" in texts
    assert "No units reported available as of CoStar's last research" in texts
    assert "Units available: not on record" in texts
    assert all("now" not in t.lower().split() for t in texts)


def test_three_d_scan_label_is_about_the_building_never_the_floor_plan():
    (hit,) = search_places(RenterBrief(), Fake([building(plans=[plan()], model_ids=["fx-model"])]))
    assert hit.has_3d_scan and hit.scan_text == "a 3D scan in this building"
    (none,) = search_places(RenterBrief(), Fake([building(plans=[plan()])]))
    assert not none.has_3d_scan and none.scan_text is None


def test_office_on_record_is_the_company_name_only():
    (hit,) = search_places(
        RenterBrief(), Fake([building(plans=[plan()], manager_company="Fixture Office Co")])
    )
    assert hit.office_on_record == "Fixture Office Co"


# --- order -------------------------------------------------------------------------------------


def test_order_is_fits_budget_then_cheapest_then_most_must_haves():
    a = building("fx-a", [plan(lo=1200, hi=1300)], is_walkup=False)  # within, dearer, 1 must
    b = building("fx-b", [plan(lo=1000, hi=1100)])  # within, cheapest, 0 musts
    c = building("fx-c", [plan(lo=1000, hi=1100)], is_walkup=False)  # within, same price, 1 must
    d = building("fx-d", [plan(lo=900, hi=1700)])  # starts within: after every within
    e = building("fx-e", [plan(lo=800, hi=None)])  # no full price: last
    brief = RenterBrief(max_rent_month=1400, needs_no_walkup=True)
    got = [m.property_id for m in search_places(brief, Fake([a, b, c, d, e]))]
    assert got == ["fx-c", "fx-b", "fx-a", "fx-d", "fx-e"]


def test_order_is_stable_whatever_order_the_kit_holds_its_records():
    records = [building(f"fx-{i}", [plan(lo=1000, hi=1100)]) for i in range(5)]
    forward = [m.property_id for m in search_places(RenterBrief(), Fake(records))]
    backward = [m.property_id for m in search_places(RenterBrief(), Fake(records[::-1]))]
    assert forward == backward == sorted(forward)


def test_max_results_cuts_the_list_but_the_counts_stay_whole():
    records = [building(f"fx-{i}", [plan()]) for i in range(5)]
    response = search(RenterBrief(max_results=2), Fake(records))
    assert len(response.matches) == 2 and response.n_matches == 5 and response.n_considered == 5


def test_live_search_only_looks_at_houston():
    houston = building("fx-hou", [plan()], market="Houston")
    elsewhere = building("fx-la", [plan()], market="Los Angeles")
    live = search_places(RenterBrief(), Fake([houston, elsewhere], source=DataSource.LIVE))
    assert [m.property_id for m in live] == ["fx-hou"]
    assert len(search_places(RenterBrief(), Fake([houston, elsewhere]))) == 2


# --- LIVE / FIXTURE ----------------------------------------------------------------------------


def test_every_match_and_response_carries_its_source():
    live = search(
        RenterBrief(), Fake([building(plans=[plan()], market="Houston")], source=DataSource.LIVE)
    )
    assert live.source is DataSource.LIVE and {m.source for m in live.matches} == {DataSource.LIVE}
    fixture = search(RenterBrief(), Fake([building(plans=[plan()])]))
    assert fixture.source is DataSource.FIXTURE and {m.source for m in fixture.matches} == {
        DataSource.FIXTURE
    }


# --- the shared fixture kit, through the real adapters -----------------------------------------


def test_fixture_kit_search_reads_apartments_and_house_rentals(kit):
    got = search_places(RenterBrief(max_rent_month=1800), kit)
    kinds = {m.kind for m in got}
    assert kinds == {"apartment", "house"}
    assert all(m.source is DataSource.FIXTURE for m in got)
    # fx-prop-4's per-bed plan and fx-prop-5's per-bed plan never appear.
    assert not any(m.floor_plan == "4 bed / 4 bath" for m in got)
    house = next(m for m in got if m.kind == "house")
    assert house.office_on_record == "Fixture Rentals Realty" and house.has_3d_scan
    assert house.scan_text == "a 3D scan in this home"


def test_fixture_kit_walkup_facts_flow_from_the_kit_rows(kit):
    got = search_places(RenterBrief(needs_no_walkup=True, beds_min=1), kit)
    assert "fx-prop-4" not in {m.property_id for m in got}  # isWalkup true in the kit row
    assert "fx-prop-5" not in {m.property_id for m in got}
    assert "fx-prop-3" in {m.property_id for m in got}


def test_a_house_without_an_office_is_listed_but_cannot_be_drafted(kit):
    (house,) = [m for m in search_places(RenterBrief(), kit) if m.property_id == "880002"]
    assert house.office_on_record is None
    with pytest.raises(NoOfficeOnRecord):
        draft_tour_request(house)


# --- no forbidden words ------------------------------------------------------------------------


def _all_text(kit, brief: RenterBrief) -> str:
    parts: list[str] = []
    for m in search_places(brief, kit):
        parts += [m.price_text, m.availability_text, m.scan_text or "", m.floor_plan or ""]
        parts += [line.text for line in m.must_haves]
        if m.office_on_record:
            # An office's proper name is quoted, not our wording: it is not word-checked.
            parts.append(draft_tour_request(m, brief).text.replace(m.office_on_record, "OFFICE"))
    return "\n".join(parts).lower()


def test_no_neighbourhood_school_or_people_words_anywhere(kit):
    text = _all_text(kit, RenterBrief(pets=True, needs_parking=True, move_in_by=date(2026, 12, 31)))
    assert text.strip()
    for word in FORBIDDEN:
        assert word not in text, word


def test_tradeoff_questions_use_no_forbidden_words(kit):
    brief = RenterBrief(max_rent_month=1500, needs_no_walkup=True, needs_parking=True)
    matches = search_places(brief, kit)
    text = " ".join(t.question for t in tradeoffs_for(brief, kit, matches)).lower()
    for word in FORBIDDEN:
        assert word not in text, word


# --- alternatives ------------------------------------------------------------------------------


def _case(rent, beds, pid):
    listing = SimpleNamespace(listed_rent=rent, beds=beds)
    return SimpleNamespace(listing=listing, evidence=SimpleNamespace(price=None), property_id=pid)


def test_alternatives_are_near_the_ads_price_and_beds_and_exclude_its_own_building():
    own = building("fx-own", [plan(lo=1400, hi=1500)])
    near = building("fx-near", [plan(lo=1350, hi=1450)])
    far = building("fx-far", [plan(lo=700, hi=800)])
    two = building("fx-two", [plan("2 bed / 1 bath", 2, lo=1400, hi=1450)])
    over = building("fx-over", [plan(lo=1900, hi=2000)])
    got = alternatives_for(_case(1500, 1, "fx-own"), None, Fake([own, near, far, two, over]), n=5)
    assert [m.property_id for m in got] == ["fx-near", "fx-far"]
    assert len(alternatives_for(_case(1500, 1, "fx-own"), None, Fake([own, near, far]), n=1)) == 1


def test_alternatives_without_an_ad_price_or_budget_are_empty_not_guessed():
    assert alternatives_for(_case(None, 1, None), None, Fake([building(plans=[plan()])])) == []


def test_alternatives_fall_back_to_the_price_the_check_compared():
    price = SimpleNamespace(listed_rent=1500, compared_beds=1)
    case = SimpleNamespace(
        listing=None, evidence=SimpleNamespace(price=price), property_id="fx-own"
    )
    got = alternatives_for(case, None, Fake([building("fx-near", [plan(lo=1350, hi=1450)])]))
    assert [m.property_id for m in got] == ["fx-near"]


# --- the tour request draft --------------------------------------------------------------------


def _place(office="Fixture Office Co", **kw):
    return PlaceMatch(
        property_id="fx-b1",
        kind="apartment",
        floor_plan="1 bed / 1 bath",
        budget_fit=BudgetFit.WITHIN,
        price_text=price_text(1450, 1600),
        availability_text="x",
        office_on_record=office,
        source=DataSource.FIXTURE,
        **kw,
    )


def test_draft_is_addressed_only_to_the_office_on_record_and_never_sent():
    draft = draft_tour_request(_place("Fixture Office Co"))
    assert draft.addressee == "Fixture Office Co"
    assert draft.text.splitlines()[0] == "To: Fixture Office Co"
    assert draft.status == "draft" and draft.sent is False
    assert "application fee" in draft.text
    assert "$1,450 to $1,600 a month" in draft.text


def test_draft_addressee_follows_the_place_so_a_poster_swap_would_fail_this():
    for office in ("Alpha Rentals LLC", "Beta Living Co"):
        draft = draft_tour_request(_place(office))
        assert draft.addressee == office and office in draft.text
    other = draft_tour_request(_place("Alpha Rentals LLC"))
    assert "Beta" not in other.text


def test_draft_has_no_phone_digits_and_cannot_be_made_without_an_office():
    brief = RenterBrief(pets=True, move_in_by=date(2026, 12, 1))
    text = draft_tour_request(_place(), brief).text
    assert not PHONE.search(text)
    assert "Dec 1, 2026" in text and "pet" in text
    with pytest.raises(NoOfficeOnRecord):
        draft_tour_request(_place(None))
    with pytest.raises(NoOfficeOnRecord):
        draft_tour_request(_place("   "))


def test_place_for_finds_the_place_whatever_the_budget(kit):
    place = place_for("fx-prop-3", "1 bed / 1 bath", kit)
    assert place is not None and place.office_on_record == "Fixture Property Management Co"
    assert place_for("fx-nope", None, kit) is None


# --- the planner hook --------------------------------------------------------------------------


class Scripted:
    """A chooser standing in for a model: records what it was shown, answers as told."""

    chosen_by = "model"

    def __init__(self, answer):
        self.answer = answer
        self.seen = []

    def choose(self, offer):
        self.seen.append(offer)
        return self.answer, "my own reason"


def _matches(kit):
    return search_places(RenterBrief(max_rent_month=2000, max_results=20), kit)


def test_a_model_pick_on_the_list_is_applied_and_stamped_model(kit):
    matches = _matches(kit)
    offer = deep_check_offer(matches)
    assert len(offer.options) >= 2
    chooser = Scripted(offer.aliases[1])
    plan_ = plan_search(matches, [], chooser)
    first = plan_.steps[0]
    assert (
        first.kind == "deep_check" and first.chosen_by == "model" and first.pick == offer.options[1]
    )
    assert plan_.deep_check == list(offer.payload["sets"][offer.options[1]])


def test_one_option_menus_never_go_to_the_model_and_are_stamped_policy(kit):
    chooser = Scripted("anything")
    plan_ = plan_search(
        _matches(kit)[:1], [], chooser
    )  # one match: one deep-check set; no questions
    assert [s.chosen_by for s in plan_.steps] == ["policy", "policy"]
    assert chooser.seen == []
    assert plan_.question is None


def test_an_off_list_pick_or_a_failing_chooser_gets_the_code_policy():
    class Broken:
        chosen_by = "model"

        def choose(self, offer):
            raise RuntimeError("down")

    matches = search_places(
        RenterBrief(),
        Fake([building(f"fx-{i}", [plan(lo=1000 + i, hi=1100 + i)]) for i in range(4)]),
    )
    for chooser in (Broken(), Scripted("a made-up option")):
        result = plan_search(matches, [], chooser)
        assert result.steps[0].chosen_by == "policy"
        assert result.steps[0].pick == deep_check_offer(matches).default


def test_the_tradeoff_choice_asks_one_code_written_question_or_none():
    options = [
        TradeOff("walkup", "$140 a month less with a walk-up building. OK with stairs?", 140, 3),
        TradeOff("budget", "$150 more a month shows 2 more places. Raise the budget?", 0, 2),
    ]
    offer = tradeoff_offer(options, 4)
    assert offer.options[-1] == NO_QUESTION and offer.default == options[0].question
    asked = plan_search([], options, Scripted(offer.aliases[1]))
    assert asked.question == options[1].question and asked.steps[-1].chosen_by == "model"
    nothing = plan_search([], options, Scripted(offer.aliases[2]))
    assert nothing.question is None
    default = plan_search([], options, PolicyChooser())
    assert default.question == options[0].question and default.steps[-1].chosen_by == "policy"
    assert plan_search([], [], Scripted("x")).steps[-1].chosen_by == "policy"  # a menu of one


def test_tradeoffs_come_from_a_second_search_with_one_need_relaxed(kit):
    brief = RenterBrief(max_rent_month=1800, needs_no_walkup=True, beds_min=1)
    matches = search_places(brief, kit)
    options = {t.key: t for t in tradeoffs_for(brief, kit, matches)}
    assert "walkup" not in options or options["walkup"].saves > 0
    assert "budget" in options and options["budget"].extra_places > 0
    cheapest = min(m.rent_min for m in matches)
    relaxed = search_places(brief.model_copy(update={"needs_no_walkup": False}), kit)
    if "walkup" in options:
        assert options["walkup"].saves == cheapest - min(m.rent_min for m in relaxed)


def test_the_chooser_sees_only_allowlisted_derived_facts_and_no_kit_rows(kit):
    matches = _matches(kit)
    brief = RenterBrief(max_rent_month=1800, needs_no_walkup=True, beds_min=1)
    chooser = Scripted("option A")
    plan_search(matches, tradeoffs_for(brief, kit, search_places(brief, kit)), chooser)
    assert len(chooser.seen) >= 1
    secrets_in_kit = {m.property_id for m in matches} | {
        m.office_on_record for m in matches if m.office_on_record
    }
    for offer in chooser.seen:
        assert set(offer.facts) <= SEARCH_FACT_KEYS[offer.kind]
        assert all(isinstance(v, (bool, int)) for v in offer.facts.values())
        assert offer.payload == {}  # code's own map from label to place ids is not handed over
        shown = json.dumps([offer.options, offer.aliases, offer.facts, offer.default_reason])
        for secret in secrets_in_kit:
            assert secret not in shown, secret
        assert not PHONE.search(shown)


def test_every_fact_key_a_chooser_can_see_is_on_the_allowlist(kit):
    offer = deep_check_offer(_matches(kit))
    assert set(offer.facts) == SEARCH_FACT_KEYS["deep_check"]
    assert set(tradeoff_offer([], 0).facts) == SEARCH_FACT_KEYS["tradeoff"]


def test_the_search_module_has_no_model_or_network_import():
    source = Path(search_module.__file__).read_text()
    for name in ("anthropic", "openai", "requests", "httpx", "langchain"):
        assert name not in source


# --- review round 1 ----------------------------------------------------------------------------


def same_label_building():
    return building(
        "fx-twin",
        [plan(lo=1000, hi=1100), plan(lo=1900, hi=2100)],
        manager_company="Twin Plans Co",
    )


def test_two_same_label_plans_each_have_their_own_key_and_the_draft_quotes_the_picked_one():
    lookups = Fake([same_label_building()])
    cheap, dear = sorted(search_places(RenterBrief(), lookups), key=lambda m: m.rent_min)
    assert cheap.plan_key != dear.plan_key
    for picked in (cheap, dear):
        place = place_for("fx-twin", picked.floor_plan, lookups, plan_key_=picked.plan_key)
        assert place is not None and place.price_text == picked.price_text
        assert picked.price_text.split(" a month")[0] in draft_tour_request(place).text


def test_a_label_alone_is_refused_when_it_is_not_unique():
    with pytest.raises(AmbiguousPlace):
        place_for("fx-twin", "1 bed / 1 bath", Fake([same_label_building()]))
    one = Fake([building("fx-one", [plan(lo=1000, hi=1100)])])
    assert place_for("fx-one", "1 bed / 1 bath", one) is not None


def test_price_text_sorts_its_ends():
    assert price_text(1600, 1400) == "$1,400 to $1,600 a month as of CoStar's last research"


def test_tradeoffs_count_buildings_over_the_whole_kit_not_the_callers_list():
    records = [
        building(f"fx-{i}", [plan(lo=1000, hi=1100), plan("2 bed / 2 bath", 2, lo=1050, hi=1100)])
        for i in range(6)
    ]
    records += [building(f"fx-hi{i}", [plan(lo=1200, hi=1300)]) for i in range(3)]
    lookups = Fake(records)
    brief = RenterBrief(max_rent_month=1150, max_results=2)
    cut = search_places(brief, lookups)  # only 2 of 12 plans, as a screen would hold
    options = {t.key: t for t in tradeoffs_for(brief, lookups, cut)}
    assert options["budget"].extra_places == 3  # three new buildings, not plans or list length
    assert "3 more places" in options["budget"].question


def test_a_parking_need_never_makes_a_trade_off_question():
    brief = RenterBrief(max_rent_month=1500, needs_parking=True)
    records = [
        building("fx-a", [plan(lo=1000, hi=1100)], parking_ratio=1.0),
        building("fx-b", [plan(lo=900, hi=1000)]),
    ]
    keys = {t.key for t in tradeoffs_for(brief, Fake(records))}
    assert "parking" not in keys


# --- review round 2 ----------------------------------------------------------------------------


def test_no_label_and_no_key_in_a_multi_plan_building_is_ambiguous_not_the_cheapest():
    with pytest.raises(AmbiguousPlace):
        place_for("fx-twin", None, Fake([same_label_building()]))
    one = Fake([building("fx-one", [plan(lo=1000, hi=1100)])])
    assert place_for("fx-one", None, one) is not None


def test_walkup_question_needs_a_saving_of_at_least_fifty_dollars():
    def options(walkup_low):
        records = [
            building("fx-flat", [plan(lo=1500, hi=1600)], is_walkup=False),
            building("fx-walk", [plan(lo=walkup_low, hi=1600)], is_walkup=True),
        ]
        brief = RenterBrief(max_rent_month=2000, needs_no_walkup=True)
        return {t.key for t in tradeoffs_for(brief, Fake(records))}

    assert "walkup" in options(1450)
    assert "walkup" not in options(1451)
    assert "walkup" not in options(1500)
