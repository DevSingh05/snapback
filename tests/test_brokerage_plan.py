"""A15 (#132) in the plan (A24): the listing brokerage on record counts as a marketer.

A home that is for sale usually has no property record at all. The for-sale lookup still
names its listing brokerages, so "who is on record" comes from them, and in the plan it is
the "listing brokerage" step that finds it. Everything here is lane D's synthetic kit.
"""

import random

import pytest

from snapback.agent import CaseSession, FixtureModules, PolicyChooser, Trace, run_case
from snapback.agent.intake import read_listing
from snapback.agent.join import JoinedModules, KitLookups
from snapback.agent.planner import PlanKind
from snapback.agent.rules.contact import FIXTURE_PHONE_SALT
from snapback.contracts import (
    AuthorityStatus,
    ChoiceKind,
    DataSource,
    ForSaleStatus,
    VerdictState,
)

# In fixtures/adapters/costar-kit: for sale, listed by Fixture Realty Group and Sample Homes
# Brokerage, with no property record. 200 Sample Street was rented recently. All invented.
FOR_SALE_HOME = "House at 100 Fixture Lane Apt 2, 3 bed, $1,400 a month."
RENTED_HOME = "House at 200 Sample Street, 2 bed, $1,500 a month."
RECORD, BROKERAGE = PlanKind.RECORD.value, PlanKind.BROKERAGE.value


def case_for(text: str) -> CaseSession:
    """A case on lane D's real for-sale lookup over its synthetic kit, with no property
    record: the usual shape of a house that is for sale."""
    listing = read_listing(text)
    modules = JoinedModules(
        stand_in=FixtureModules(),
        listing=listing,
        record=None,
        for_sale=KitLookups(DataSource.FIXTURE).for_sale(listing.text),
        salt=FIXTURE_PHONE_SALT,
        record_source=DataSource.FIXTURE,
    )
    return CaseSession("fx-1", modules, Trace("fx-1", DataSource.FIXTURE), rng=random.Random(3))


def at_the_plan(case: CaseSession) -> list[str]:
    case.choose_default()  # the first choice: which kinds of check
    offer = case.offer()
    assert offer is not None and offer.kind is ChoiceKind.NEXT_CHECK
    return list(offer.options)


def test_for_an_active_sale_who_is_on_record_arrives_with_the_listing_brokerage_step():
    case = case_for(f"{FOR_SALE_HOME} Listed by Fixture Realty Group.")
    assert at_the_plan(case) == [RECORD, BROKERAGE]

    case.choose(RECORD)
    # The home's own record has nothing to say about who may market it: there is none.
    assert case.evidence.authority is None and case.evidence.for_sale is None

    case.choose(BROKERAGE)
    assert case.evidence.for_sale.status is ForSaleStatus.ACTIVE
    found = case.evidence.authority
    assert found.status is AuthorityStatus.MATCHES_RECORD
    assert found.manager_on_record == "Fixture Realty Group"


@pytest.mark.parametrize(
    ("named", "status", "who"),
    [
        ("Listed by Fixture Realty Group.", AuthorityStatus.MATCHES_RECORD, "Fixture Realty Group"),
        (
            "Listed by Sample Homes Brokerage.",
            AuthorityStatus.MATCHES_RECORD,
            "Sample Homes Brokerage",
        ),
        ("Listed by Somebody Else Realty.", AuthorityStatus.MISMATCH, None),
        ("", AuthorityStatus.UNKNOWN, None),
    ],
)
def test_the_finding_is_the_same_whichever_step_runs_first(named, status, who):
    # The pick changes the order of the checks, never what they find (A24).
    ends = []
    for order in ((RECORD, BROKERAGE), (BROKERAGE, RECORD)):
        case = case_for(f"{FOR_SALE_HOME} {named}")
        at_the_plan(case)
        for step in order:
            case.choose(step)
        assert (case.evidence.authority.status, case.evidence.authority.manager_on_record) == (
            status,
            who,
        )
        verdict = run_case(case, PolicyChooser(), lambda draft: "send")
        ends.append((verdict.state, verdict.reasons, case.evidence.model_dump(mode="json")))
    assert ends[0] == ends[1]
    # The for-sale flag stands whoever the listing names, and a name is never proof.
    assert ends[0][0] is VerdictState.HOLD


def test_a_home_that_is_not_for_sale_now_keeps_the_finding_with_its_own_record():
    # Rented recently: there is no listing to check, so the brokerage step is not offered
    # and who is on record comes with the home's record, as before.
    case = case_for(f"{RENTED_HOME} Listed by Fixture Realty Group.")
    assert at_the_plan(case) == [RECORD]
    case.choose(RECORD)
    assert case.evidence.for_sale.status is ForSaleStatus.RECENTLY_RENTED
    # The office on that record still counts as a marketer (ruling, Sat 01:20).
    assert case.evidence.authority.status is AuthorityStatus.MATCHES_RECORD


def test_the_trace_says_the_listing_office_was_checked():
    case = case_for(f"{FOR_SALE_HOME} Listed by Fixture Realty Group.")
    run_case(case, PolicyChooser(), lambda draft: "send")
    picks = [event.pick for event in case.trace.events if event.choice is ChoiceKind.NEXT_CHECK]
    assert picks[:2] == [RECORD, BROKERAGE]
    # No name from the listing or the record is in what the plan says.
    said = " ".join(event.reason for event in case.trace.events)
    assert "Fixture Realty" not in said and "Somebody Else" not in said
