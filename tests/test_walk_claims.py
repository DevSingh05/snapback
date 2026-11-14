"""W2: the ad's claims on the stops, and the scan count lines."""

from snapback.contracts import AdNote, DataSource
from snapback.tour import TourSweep, attach_claims, build_tour, claim_text, fixture_sweeps


def plan_of(sweeps=None):
    return build_tour(
        property_id="fx-prop-3",
        kind="apartment",
        source=DataSource.FIXTURE,
        sweeps=sweeps or fixture_sweeps("fx-model-a"),
        has_scan=True,
    )


def note(key, claim, **kw):
    return AdNote(key=key, claim=claim, **kw)


def stop(plan, title):
    return next(s for s in plan.stops if s.title == title)


def test_floor_claim_lands_on_the_living_room_with_the_cards_own_words():
    n = note("floor_photos", "floor_wood", record=["carpet"])
    out = attach_claims(plan_of(), [n])
    living = stop(out, "Living room")
    assert [c.text for c in living.claims] == [claim_text(n)]
    assert living.claims[0].text.startswith("Not confirmed. The ad says hardwood floors.")
    assert living.claims[0].source == "CoStar record"
    assert all(not s.claims for s in out.stops if s.title != "Living room")


def test_every_note_lands_on_exactly_one_stop():
    notes = [
        note("floor_photos", "floor_wood", record=["carpet"]),
        note("wd_listing", "washer_dryer", record=["hookup"]),  # no laundry room: the arrival
        note("pool_none", "pool"),  # not a room: the arrival
        note("parking_none", "garage"),  # no garage stop: the arrival
    ]
    out = attach_claims(plan_of(), notes)
    assert sum(len(s.claims) for s in out.stops) == len(notes)
    assert len(stop(out, "Arrive outside").claims) == 3
    assert len(stop(out, "Living room").claims) == 1


def test_washer_dryer_goes_to_the_laundry_room_when_the_scan_has_one():
    sweeps = fixture_sweeps("fx-model-a") + [
        TourSweep("fx-sweep-09", (20.0, 1.4, 20.0), (0, 0, 0, 1), "Laundry room")
    ]
    out = attach_claims(plan_of(sweeps), [note("wd_listing", "washer_dryer", record=["hookup"])])
    assert len(stop(out, "Laundry room").claims) == 1


def test_a_note_with_no_words_is_left_out():
    out = attach_claims(plan_of(), [note("no_such_key", "pool")])
    assert all(not s.claims for s in out.stops)


def test_count_line_is_info_and_only_when_the_ad_number_differs_from_the_scan():
    notes = [note("beds_differ", "beds", ad_value="3", record_value="2")]
    out = attach_claims(plan_of(), notes)  # the fixture scan has two Bedroom rooms
    lines = [c.text for c in stop(out, "Bedroom 1").claims]
    assert any(
        t == "The ad says 3 bedrooms. This scan has 2 rooms labelled Bedroom. "
        "Labels can be wrong, so count them in person."
        for t in lines
    )
    assert all(
        not c.text.startswith("Not confirmed")
        for s in out.stops
        for c in s.claims
        if "labelled" in c.text
    )
    same = attach_claims(plan_of(), [note("beds_differ", "beds", ad_value="2", record_value="3")])
    assert not any("labelled" in c.text for s in same.stops for c in s.claims)


def test_no_count_line_without_room_labels_or_when_the_floor_plan_differs():
    unlabelled = [TourSweep(f"s{i}", (i * 2.0, 1.4, 0.0), (0, 0, 0, 1), None) for i in range(5)]
    n = [note("beds_differ", "beds", ad_value="3", record_value="2")]
    assert not any(
        "labelled" in c.text for s in attach_claims(plan_of(unlabelled), n).stops for c in s.claims
    )
    from snapback.contracts import LocateResult
    from snapback.tour import map_locate

    mismatched, _ = map_locate(
        plan_of(),
        LocateResult(case_id="c", photos=[], thresholds_version="t"),
        scan_plan="2 bed / 2 bath",
        ad_plan="1 bed / 1 bath",
    )
    assert mismatched.coverage.plan_mismatch is True
    out = attach_claims(mismatched, n)
    assert not any("labelled" in c.text for s in out.stops for c in s.claims)


def test_claims_never_change_a_verdict_or_the_other_fields():
    plan = plan_of()
    out = attach_claims(plan, [note("floor_photos", "floor_wood", record=["carpet"])])
    a, b = plan.model_dump(), out.model_dump()
    for d in (a, b):
        for s in d["stops"]:
            s.pop("claims")
    assert a == b
