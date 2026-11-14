"""E1 and E6: the place desk. A stub searcher stands in for `Locator.search` (E2a, lane V).

No model, no network. The model's side is a scripted chooser behind the same `Chooser` shape.
"""

import dataclasses
import json
import random
from datetime import UTC, datetime

import pytest

from snapback.agent import CaseSession, FixtureModules, PolicyChooser, Trace, run_case
from snapback.agent.place import (
    PLACE_FACT_KEYS,
    PlaceDesk,
    PlaceOffer,
    SearchOption,
    SearchOutcome,
    search_thresholds,
)
from snapback.agent.planner import _decide
from snapback.contracts import (
    ChoiceKind,
    DataSource,
    EvidencePoints,
    LocateResult,
    LocateStatus,
    PhotoLocation,
    TraceKind,
)
from snapback.verdict import build_card, decide, to_evidence
from snapback.vision.locate.thresholds import load_thresholds

BASE = load_thresholds()
LOC = LocateStatus


def located(**over) -> LocateResult:
    photos = [
        PhotoLocation(photo_id="l1", status=LOC.LOCATED_IN_CLAIMED, model_id="m1", inliers=142),
        PhotoLocation(
            photo_id="l2",
            status=LOC.NOT_LOCATED,
            inliers=24,
            inlier_ratio=0.18,
            spread=0.03,
            rival_ratio=0.4,
            bar_failed="inliers",
        ),
        PhotoLocation(
            photo_id="l3",
            status=LOC.NOT_LOCATED,
            inliers=40,
            inlier_ratio=0.3,
            spread=0.09,
            rival_ratio=3.5,
            bar_failed="ambiguity",
        ),
    ]
    return LocateResult(
        case_id="fx-1",
        photos=photos,
        claimed_property_id="fx-prop-1",
        thresholds_version=BASE.version,
        **over,
    )


def placed(photo_id: str, model_id: str = "m2") -> SearchOutcome:
    return SearchOutcome(
        PhotoLocation(
            photo_id=photo_id,
            status=LOC.LOCATED_IN_CLAIMED,
            model_id=model_id,
            inliers=88,
            inlier_ratio=0.41,
            spread=0.31,
        ),
        points=EvidencePoints(n_total=88, sampled=[(0.1, 0.2, 0.1, 0.2)]),
        seconds=2.0,
    )


def missed(photo_id: str) -> SearchOutcome:
    return SearchOutcome(
        PhotoLocation(photo_id=photo_id, status=LOC.NOT_LOCATED, inliers=10, bar_failed="inliers"),
        seconds=2.0,
    )


class StubSearcher:
    """Deterministic and order-free: l2 places on a `focus_scan:S2` retry, nothing else does."""

    def __init__(self, seconds: float = 2.0) -> None:
        self.calls: list[tuple[str, str]] = []
        self.thresholds_seen: list = []
        self.seconds = seconds

    def search(self, photo_id, option, claimed_property_id, thresholds, deadline_s=None):
        self.calls.append((photo_id, option.label))
        self.thresholds_seen.append(thresholds)
        if photo_id == "l2" and option.label == "focus_scan:S2":
            return dataclasses.replace(
                placed(photo_id, option.scan_model_id or "m2"), seconds=self.seconds
            )
        return dataclasses.replace(missed(photo_id), seconds=self.seconds)


class Scripted:
    """A chooser that picks by a fixed rule, standing in for a model."""

    def __init__(self, rule, by="model"):
        self.rule, self.chosen_by, self.seen = rule, by, []

    def choose(self, offer):
        self.seen.append(offer)
        return self.rule(offer), "Because of the facts shown."


SCANS = {"S1": "m1", "S2": "m2"}


def desk(searcher=None, **kw) -> PlaceDesk:
    return PlaceDesk(located(), searcher or StubSearcher(), scans=SCANS, thresholds=BASE, **kw)


def drive(d: PlaceDesk, chooser) -> None:
    while d.offer() is not None:
        d.choose(chooser)


# --- E6 test 1: a retry changes retrieval only; a lowered bar must fail -----------------------


def assert_retrieve_only(fn) -> None:
    allowed = {"top_k", "top_k_claimed"}
    options = [
        SearchOption("focus_scan", "S2", "m2"),
        SearchOption("wider_index"),
        SearchOption("deeper_claimed"),
    ]
    for option in options:
        got = fn(BASE, option)
        for f in dataclasses.fields(BASE):
            if f.name not in allowed:
                assert getattr(got, f.name) == getattr(BASE, f.name), (option.label, f.name)


def test_every_search_option_differs_from_the_base_only_in_retrieve():
    assert_retrieve_only(search_thresholds)
    wider = search_thresholds(BASE, SearchOption("wider_index"))
    assert wider.top_k > BASE.top_k and wider.top_k_claimed == BASE.top_k_claimed
    deeper = search_thresholds(BASE, SearchOption("deeper_claimed"))
    assert deeper.top_k_claimed > BASE.top_k_claimed and deeper.top_k == BASE.top_k


def test_a_mutant_that_lowers_a_bar_is_caught():
    def lowers_min_inliers(base, option):
        return dataclasses.replace(
            search_thresholds(base, option), min_inliers=base.min_inliers - 10
        )

    def loosens_spread(base, option):
        return dataclasses.replace(search_thresholds(base, option), claimed_min_spread=0.0)

    for mutant in (lowers_min_inliers, loosens_spread):
        with pytest.raises(AssertionError):
            assert_retrieve_only(mutant)


# --- E6 test 2: a retry never touches a placed photo --------------------------------------------


def test_a_retry_never_touches_a_placed_photo():
    class Claims:
        """A searcher that insists l1 is in another scan, or in another building."""

        def search(self, photo_id, option, claimed_property_id, thresholds, deadline_s=None):
            loc = PhotoLocation(
                photo_id=photo_id,
                status=LOC.LOCATED_ELSEWHERE,
                model_id="m9",
                inliers=200,
                inlier_ratio=0.6,
                spread=0.5,
            )
            return SearchOutcome(loc, seconds=1.0)

    d = desk(Claims(), max_searches=10, max_seconds=100)
    before = d.base.photos[0]
    d._search("P1", SearchOption("wider_index"), "policy")  # forced, past the desk's own menu
    assert d.located().photos[0] == before
    assert d.rows["l1"].steps[-1].result == "not_placed"
    drive(d, PolicyChooser_for_desk())
    assert d.located().photos[0] == before


class PolicyChooser_for_desk(Scripted):
    def __init__(self):
        super().__init__(lambda offer: offer.default, by="policy")


# --- the budget -----------------------------------------------------------------------------------


def test_the_budget_is_two_searches():
    searcher = StubSearcher()
    d = desk(searcher)
    drive(d, Scripted(lambda o: o.options[0]))
    assert len(searcher.calls) == 2 and d.offer() is None


def test_the_budget_is_ten_seconds():
    searcher = StubSearcher(seconds=11.0)
    d = desk(searcher)
    drive(d, Scripted(lambda o: o.options[0]))
    assert len(searcher.calls) == 1  # the first search spent the whole clock


def test_a_failing_searcher_costs_budget_and_changes_nothing():
    class Boom:
        def search(self, *a):
            raise RuntimeError("index offline")

    d = desk(Boom())
    drive(d, Scripted(lambda o: o.options[0]))
    assert d.located().photos == d.base.photos and d.searches_used == 2


# --- E6 test 3: with enough budget, model order and policy order end the same -----------------


def test_model_order_and_policy_order_end_in_the_same_located_result():
    by_policy, by_reversed_model = (
        desk(max_searches=10, max_seconds=100),
        desk(max_searches=10, max_seconds=100),
    )
    drive(by_policy, PolicyChooser_for_desk())

    def reversed_pick(offer):
        return next(o for o in reversed(offer.options) if o != "stop")

    drive(by_reversed_model, Scripted(reversed_pick))
    assert by_policy.located() == by_reversed_model.located()
    assert by_policy.located().photos[1].status is LOC.LOCATED_IN_CLAIMED  # l2 placed on S2
    assert by_policy.located().photos[2].status is LOC.NOT_LOCATED  # l3 never does


# --- E6 test 4: a chooser sees only the allow-list ------------------------------------------------


def test_chooser_payloads_are_subsets_of_the_allow_lists():
    chooser = Scripted(lambda o: o.options[0])
    d = desk(max_searches=1)  # two unplaced photos, one search: D2 comes first
    drive(d, chooser)
    kinds = {offer.kind for offer in chooser.seen}
    assert kinds == {ChoiceKind.WHICH_PHOTO.value, ChoiceKind.NEXT_SEARCH.value}
    for offer in chooser.seen:
        shown = offer.for_chooser() if isinstance(offer, PlaceOffer) else offer
        for key in shown.facts:
            bare = key.split(" ", 1)[1] if key.startswith("P") and " " in key else key
            assert bare in PLACE_FACT_KEYS, key
        blob = json.dumps({"o": shown.options, "f": dict(shown.facts)})
        for banned in ("points", "sampled", "photo_id", "model_id", "fx-", "m1", "m2", "bytes"):
            assert banned not in blob, banned


def test_the_offer_given_to_a_chooser_drops_a_fact_outside_the_list():
    offer = PlaceOffer(
        "next_search", ("stop", "x"), ("stop", "x"), {"best_inliers": 3, "points": 9}, "stop", "r"
    )
    assert offer.for_chooser().facts == {"best_inliers": 3}


# --- E6 test 5: off-list and menu-of-one are policy --------------------------------------


def test_an_off_list_pick_and_a_chooser_that_fails_are_policy():
    d = desk()
    step, _ = d.choose(Scripted(lambda o: "make it 99 points"))
    assert step.chosen_by == "policy" and step.pick == step.pick.strip()
    boom = Scripted(lambda o: (_ for _ in ()).throw(RuntimeError("down")))
    step, _ = desk().choose(boom)
    assert step.chosen_by == "policy"


def test_a_menu_of_one_is_policy_and_never_asked():
    one = PlaceOffer("next_search", ("stop",), ("stop",), {}, "stop", "r")
    chooser = Scripted(lambda o: pytest.fail("asked a chooser about a menu of one"))
    label, step = _decide(one, chooser)
    assert (label, step.chosen_by) == ("stop", "policy")


def test_when_only_stop_is_left_the_desk_closes_without_asking():
    d = desk(max_searches=10, max_seconds=100)
    d.rows["l2"].tried |= {"focus_scan:S1", "focus_scan:S2", "wider_index", "deeper_claimed"}
    d.rows["l3"].tried |= {"focus_scan:S1", "focus_scan:S2", "wider_index", "deeper_claimed"}
    assert d.offer() is None and d.unplaced() == []


# --- the evidence file ----------------------------------------------------------------------------


def test_the_evidence_file_records_every_search_and_who_chose_it():
    d = desk(max_searches=10, max_seconds=100)
    drive(d, Scripted(lambda o: next(x for x in o.options if x != "stop")))
    ev = d.evidence_file("fx-1", DataSource.FIXTURE)
    p2 = next(p for p in ev.photos if p.alias == "P2")
    assert p2.status is LOC.LOCATED_IN_CLAIMED and p2.scan_alias == "S2"
    assert [(s.option, s.chosen_by) for s in p2.searches][0] == ("base", "policy")
    assert any(s.option == "focus_scan:S2" and s.result == "placed" for s in p2.searches)
    assert ev.bars["min_inliers"] == BASE.min_inliers and ev.written_by == "code"


# --- inside a case --------------------------------------------------------------------------------


class RetryModules(FixtureModules):
    def __init__(self):
        super().__init__()
        self.evidence = self.evidence.model_copy(
            update={"locate": located(chosen=None, alternatives=[])}
        )


def make_case(searcher=None) -> CaseSession:
    ticks = iter(datetime(2026, 11, 14, 12, 0, s, tzinfo=UTC) for s in range(60))
    case = CaseSession(
        "fx-1",
        RetryModules(),
        Trace("fx-1", DataSource.FIXTURE, clock=lambda: next(ticks)),
        rng=random.Random(5),
    )
    case.place_searcher, case.place_scans = searcher, SCANS
    return case


def test_without_a_searcher_nothing_changes():
    a, b = make_case(None), make_case(None)
    assert run_case(a, PolicyChooser(), lambda d: "send") == run_case(
        b, PolicyChooser(), lambda d: "send"
    )
    assert a.place_desk is None and all(e.choice != ChoiceKind.NEXT_SEARCH for e in a.trace.events)


def test_a_case_spends_the_retry_budget_and_stamps_every_step():
    case = make_case(StubSearcher())
    run_case(case, PolicyChooser(), lambda d: "send")
    events = case.trace.events
    assert any(e.kind is TraceKind.UNSURE and "fell short" in e.reason for e in events)
    picks = [e for e in events if e.choice in (ChoiceKind.NEXT_SEARCH, ChoiceKind.WHICH_PHOTO)]
    assert picks and all(e.chosen_by == "policy" for e in picks)
    assert any(e.kind is TraceKind.TOOL and (e.pick or "").startswith("search: ") for e in events)
    # the policy spends both searches on the nearest miss (l3, 40 points); l2 is left as it was
    searched = [e.pick for e in events if (e.pick or "").startswith("search: ")]
    assert searched == ["search: wider_index", "search: deeper_claimed"]
    assert case.evidence.locate.photos[1].status is LOC.NOT_LOCATED


# --- E6 test 6: the card is decide() on the final evidence, whatever the model picked ---------


@pytest.mark.parametrize("pick", ["first", "last", "stop"])
def test_the_result_is_decide_on_the_final_evidence_whatever_the_pick(pick):
    case = make_case(StubSearcher())
    rule = {
        "first": lambda o: o.options[0],
        "last": lambda o: o.options[-1],
        "stop": lambda o: "stop" if "stop" in o.options else o.options[0],
    }[pick]
    chooser = Scripted(rule)
    verdict = run_case(case, chooser, lambda d: "send")
    assert verdict == decide(to_evidence(case.evidence))
    when = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
    assert build_card(case.evidence, checked_at=when) == build_card(
        case.evidence.model_copy(deep=True), checked_at=when
    )


# --- review of #222: the desk re-checks every retry result against the bars ---------------------


def one_result(location: PhotoLocation):
    class Fixed:
        def search(self, photo_id, option, claimed_property_id, thresholds, deadline_s=None):
            return SearchOutcome(location.model_copy(update={"photo_id": photo_id}), seconds=1.0)

    return Fixed()


def strict_elsewhere(**over) -> PhotoLocation:
    fields = dict(
        photo_id="x",
        status=LOC.LOCATED_ELSEWHERE,
        model_id="m9",
        inliers=60,
        inlier_ratio=0.3,
        spread=0.2,
    )
    return PhotoLocation(**{**fields, **over})


def run_state(searcher, **kw):
    case = make_case(searcher)
    verdict = run_case(case, PolicyChooser(), lambda d: "send")
    return verdict.state.value, case


def test_a_retry_that_only_looks_elsewhere_stays_hold_and_a_strict_one_is_dont_pay():
    baseline, _ = run_state(None)
    assert baseline == "hold"
    weak = strict_elsewhere(
        inliers=31, spread=0.06
    )  # the base search would not call this elsewhere
    assert run_state(one_result(weak))[0] == "hold"
    assert run_state(one_result(strict_elsewhere()))[0] == "dont_pay"


def test_each_strict_bar_is_checked_on_its_own():
    for weak in (
        strict_elsewhere(inliers=49),
        strict_elsewhere(spread=0.14),
        strict_elsewhere(inlier_ratio=0.2),
        strict_elsewhere(inliers=None),
        strict_elsewhere(spread=None),
    ):
        assert run_state(one_result(weak))[0] == "hold", weak


def test_a_retry_cannot_place_a_photo_below_the_claimed_bars():
    d = desk(
        one_result(
            PhotoLocation(
                photo_id="x",
                status=LOC.LOCATED_IN_CLAIMED,
                model_id="m2",
                inliers=29,
                inlier_ratio=0.5,
                spread=0.3,
            )
        ),
        max_searches=10,
        max_seconds=100,
    )
    drive(d, Scripted(lambda o: next(x for x in o.options if x != "stop")))
    assert all(p.status is not LOC.LOCATED_IN_CLAIMED for p in d.located().photos[1:])


def test_with_retry_can_find_elsewhere_off_a_strict_result_stays_not_placed():
    d = desk(one_result(strict_elsewhere()), retry_can_find_elsewhere=False)
    drive(d, Scripted(lambda o: o.options[0]))
    assert [p.status for p in d.located().photos[1:]] == [LOC.NOT_LOCATED, LOC.NOT_LOCATED]


# --- the searcher gets the base bars with retrieval changed only ----------------------------------


def test_the_searcher_receives_the_base_bars_with_only_retrieval_changed():
    searcher = StubSearcher()
    d = desk(searcher, max_searches=10, max_seconds=100)
    drive(d, Scripted(lambda o: next(x for x in o.options if x != "stop")))
    assert searcher.thresholds_seen
    for got in searcher.thresholds_seen:
        for f in dataclasses.fields(BASE):
            if f.name not in ("top_k", "top_k_claimed"):
                assert getattr(got, f.name) == getattr(BASE, f.name), f.name
    assert any(
        t.top_k != BASE.top_k or t.top_k_claimed != BASE.top_k_claimed
        for t in searcher.thresholds_seen
    )


# --- the budget -----------------------------------------------------------------------------------


def test_the_wall_clock_is_charged_when_the_searcher_under_reports():
    ticks = iter([0.0, 6.0, 6.0, 12.0, 12.0, 18.0, 18.0, 24.0])

    class Sneaky:
        def search(self, photo_id, option, claimed_property_id, thresholds, deadline_s=None):
            return dataclasses.replace(missed(photo_id), seconds=0.1)  # says 0.1 s, takes 6 s

    d = PlaceDesk(
        located(),
        Sneaky(),
        scans=SCANS,
        thresholds=BASE,
        clock=lambda: next(ticks),
        max_searches=10,
    )
    drive(d, Scripted(lambda o: o.options[0]))
    assert d.searches_used == 2 and d.seconds_spent >= 10  # the second 6 s search closed the desk


def test_the_case_clock_caps_the_retry_budget():
    d = PlaceDesk(
        located(),
        StubSearcher(seconds=4.0),
        scans=SCANS,
        thresholds=BASE,
        case_seconds_left=5.0,
        max_searches=10,
    )
    drive(d, Scripted(lambda o: o.options[0]))
    assert d.searches_used == 2 and d.max_seconds == 5.0  # 4 s + 4 s passes 5 s: stop after two
    assert (
        PlaceDesk(
            located(), StubSearcher(), scans=SCANS, thresholds=BASE, case_seconds_left=0
        ).offer()
        is None
    )
