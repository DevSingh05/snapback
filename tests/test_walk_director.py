"""W6: the tour director picks among options code wrote; facts never depend on the pick."""

from snapback.contracts import DataSource, LocateResult, LocateStatus, PhotoLocation, Pose
from snapback.tour import (
    MAX_DWELL,
    MAX_LEAD,
    WALK_FACT_KEYS,
    TourFact,
    build_tour,
    choose_walk,
    fixture_sweeps,
    map_locate,
    policy_director,
    walk_offers,
)

L = LocateStatus


def walk_plan(with_claim=True):
    plan = build_tour(
        property_id="fx-prop-3",
        kind="apartment",
        source=DataSource.FIXTURE,
        sweeps=fixture_sweeps("fx-model-a"),
        has_scan=True,
    )
    photos = [
        PhotoLocation(photo_id="p1", status=L.LOCATED_IN_CLAIMED, pano_id="fx-sweep-03"),
        PhotoLocation(photo_id="p2", status=L.LOCATED_IN_CLAIMED, pano_id="fx-sweep-04"),
    ]
    poses = {
        p.photo_id: Pose(sweep_id=p.pano_id, position=(0, 0, 0), rotation_quat=(0, 0, 0, 1))
        for p in photos
    }
    plan, _ = map_locate(
        plan, LocateResult(case_id="c", photos=photos, poses=poses, thresholds_version="t")
    )
    if with_claim:
        stops = [
            s.model_copy(
                update={
                    "claims": [
                        TourFact(
                            text="Not confirmed. The ad says hardwood.", source="CoStar record"
                        )
                    ]
                }
            )
            if s.title == "Living room"
            else s
            for s in plan.stops
        ]
        plan = plan.model_copy(update={"stops": stops})
    return plan


class Pick:
    def __init__(self, index, by="model"):
        self.index, self.chosen_by = index, by
        self.seen = []

    def choose(self, offer):
        self.seen.append(offer)
        return offer.options[self.index], "because"


def facts_of(plan):
    d = plan.model_dump()
    d.pop("director")
    return d


def test_offers_are_aliased_capped_and_each_has_two_or_more_options():
    offers = walk_offers(walk_plan(), must_have_kinds=("bath",))
    assert {o.kind for o in offers} == {"dwell", "lead"}
    for o in offers:
        assert len(o.options) >= 2 and len(set(o.options)) == len(o.options)
        assert all(
            len(keys) <= (MAX_DWELL if o.kind == "dwell" else MAX_LEAD)
            for keys in o.payload.values()
        )


def test_a_menu_of_one_is_not_offered_so_it_stays_policy():
    plan = walk_plan(with_claim=False).model_copy(update={"stops": []})
    assert walk_offers(plan) == []
    assert choose_walk(plan, Pick(0)).director.stamp == "policy"


def test_walk_director_model_vs_policy_same_facts():
    plan = walk_plan()
    policy = choose_walk(plan, None, ("bath",))
    assert policy.director.stamp == "policy" and policy.director.dwell
    outcomes = set()
    for index in (0, 1, 2):
        out = choose_walk(plan, Pick(index), ("bath",))
        assert facts_of(out) == facts_of(policy)  # stops, facts, coverage, tips: identical
        assert out.director.stamp == "model"
        outcomes.add((tuple(out.director.dwell), tuple(out.director.lead_checks)))
    assert len(outcomes) > 1  # the pick does change which rooms and checks lead


def test_off_list_pick_is_policy():
    class Bad:
        chosen_by = "model"

        def choose(self, offer):
            return "Skip the rooms entirely", "x"

    plan = walk_plan()
    out = choose_walk(plan, Bad(), ("bath",))
    assert out.director == choose_walk(plan, None, ("bath",)).director
    assert out.director.stamp == "policy"


def test_a_chooser_that_raises_gets_the_policy():
    class Boom:
        chosen_by = "model"

        def choose(self, offer):
            raise RuntimeError("down")

    plan = walk_plan()
    assert choose_walk(plan, Boom()).director.stamp == "policy"


def test_director_sees_aliases_only():
    plan = walk_plan()
    pick = Pick(0)
    choose_walk(plan, pick, ("bath",))
    blob = ""
    for offer in pick.seen:
        assert set(offer.facts) <= WALK_FACT_KEYS and offer.payload == {}
        assert all(isinstance(v, int) for v in offer.facts.values())
        blob += " ".join(offer.options + offer.aliases)
    assert not any(s.sweep_id and s.sweep_id in blob for s in plan.stops)
    assert "fx-prop" not in blob and "photo-" not in blob and "p1" not in blob.split()


def test_policy_order_is_contradicted_then_hidden():
    plan = walk_plan()
    d = policy_director(plan)
    living = next(s.key for s in plan.stops if s.title == "Living room")
    assert d.dwell[0] == living and len(d.dwell) <= MAX_DWELL
    assert d.lead_checks[0] == living and len(d.lead_checks) <= MAX_LEAD
