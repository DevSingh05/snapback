"""A24: the evidence-driven plan and the who-chose stamp on every trace step.

No network, no key: the model is a stand-in chooser that picks from the same offers.
"""

import random

import pytest

from snapback.agent import CaseSession, FixtureModules, Offer, PolicyChooser, Trace, run_case
from snapback.agent.demo import demo_case_ids, demo_modules, load_demo_case
from snapback.agent.intake import read_listing
from snapback.agent.planner import PlanKind
from snapback.contracts import (
    ChoiceKind,
    DataSource,
    ForSaleMatch,
    ForSaleStatus,
    LicenseResult,
    LicenseStatus,
    TraceEvent,
    TraceKind,
    VerdictState,
)


def sale(status: ForSaleStatus) -> ForSaleMatch:
    return ForSaleMatch(status=status, offices=["Example Realty"])


class WithLicense(FixtureModules):
    def license(self, case_id):
        return LicenseResult(status=LicenseStatus.LICENSED)


class WithOwner(FixtureModules):
    def owner_of_record(self, case_id):
        return "a company"  # opaque to the plan


def make(modules) -> CaseSession:
    return CaseSession("fx-1", modules, Trace("fx-1", DataSource.FIXTURE), rng=random.Random(3))


def offered(case: CaseSession) -> list[str]:
    """Walk to the plan and return the options it offers first."""
    case.choose_default()  # the first choice: which kinds of check
    offer = case.offer()
    assert offer is not None and offer.kind is ChoiceKind.NEXT_CHECK
    return list(offer.options)


def skipped_lines(case: CaseSession) -> list[str]:
    return [e.reason for e in case.trace.events if e.reason.startswith("Skipped ")]


def reversed_plan(offer: Offer) -> str:
    """The opposite order of the policy for the plan; the policy's pick for everything else."""
    return offer.options[-1] if offer.kind is ChoiceKind.NEXT_CHECK else offer.default


class Model:
    """Stands in for a language model: a pick function plus a reason, stamped "model"."""

    chosen_by = "model"

    def __init__(self, pick):
        self.pick = pick

    def choose(self, offer: Offer):
        return self.pick(offer), "Chosen for the facts shown."


# --- each option is offered only when its evidence exists ------------------------------------


def test_record_is_offered_and_the_unavailable_options_are_skipped_with_reasons():
    case = make(FixtureModules())
    assert offered(case) == ["home record"]
    lines = skipped_lines(case)
    assert "Skipped listing brokerage: the home is not listed for sale right now." in lines
    assert "Skipped TREC license: the ad names no license to look up." in lines
    assert "Skipped owner of record: owner lookup not available." in lines


def test_brokerage_needs_an_active_for_sale_listing():
    assert "listing brokerage" in offered(make(FixtureModules(for_sale=sale(ForSaleStatus.ACTIVE))))
    for status in (ForSaleStatus.NONE, ForSaleStatus.RECENTLY_RENTED):
        assert "listing brokerage" not in offered(make(FixtureModules(for_sale=sale(status))))


def test_license_option_needs_a_module_that_looked_up_a_license():
    assert "TREC license" in offered(make(WithLicense()))
    assert "TREC license" not in offered(make(FixtureModules()))


def test_owner_option_shows_as_skipped_until_a_module_offers_it():
    case = make(FixtureModules())
    assert "owner of record" not in offered(case)
    assert any("owner lookup not available" in line for line in skipped_lines(case))
    assert "owner of record" in offered(make(WithOwner()))


def test_report_pack_opens_only_after_every_other_check_has_run():
    case = make(WithLicense(for_sale=sale(ForSaleStatus.ACTIVE)))
    assert offered(case) == ["home record", "listing brokerage", "TREC license"]
    seen = []
    while (offer := case.offer()) is not None and offer.kind is ChoiceKind.NEXT_CHECK:
        seen.append(offer.default)
        case.choose(offer.default, offer.default_reason)
    assert seen == ["home record", "listing brokerage", "TREC license", "report pack"]


# --- who chose ---------------------------------------------------------------------------------


def test_the_code_policy_stamps_every_step_policy():
    case = make(FixtureModules())
    run_case(case, PolicyChooser(), lambda draft: "send")
    assert case.trace.events
    assert {e.chosen_by for e in case.trace.events} == {"policy"}


def test_a_models_pick_is_stamped_model_and_the_code_steps_stay_policy():
    case = make(WithLicense(for_sale=sale(ForSaleStatus.ACTIVE)))
    # Always the last open option: a different order from the policy's.
    run_case(case, Model(reversed_plan), lambda draft: "send")
    plan = [e for e in case.trace.events if e.choice is ChoiceKind.NEXT_CHECK]
    assert [e.pick for e in plan] == [
        "TREC license",
        "listing brokerage",
        "home record",
        "report pack",
    ]
    # The last two menus held one option each, so nobody chose them.
    assert [e.chosen_by for e in plan] == ["model", "model", "policy", "policy"]
    for event in case.trace.events:
        if event.choice is ChoiceKind.WHICH_SPOT or event.kind in (
            TraceKind.HITL,
            TraceKind.VERDICT,
        ):
            assert event.chosen_by == "policy"


def test_an_off_list_pick_falls_back_to_the_policy_and_is_stamped_policy():
    case = make(FixtureModules())
    run_case(case, Model(lambda offer: "report pack first"), lambda draft: "send")
    choices = [e for e in case.trace.events if e.kind is TraceKind.CHOICE]
    assert choices and {e.chosen_by for e in choices} == {"policy"}
    assert any(e.kind is TraceKind.ERROR for e in case.trace.events)


def test_a_model_that_raises_falls_back_to_the_policy_and_is_stamped_policy():
    def boom(offer):
        raise RuntimeError("no connection")

    case = make(WithLicense())
    run_case(case, Model(boom), lambda draft: "send")
    assert case.done
    assert {e.chosen_by for e in case.trace.events if e.kind is TraceKind.CHOICE} == {"policy"}


def test_chosen_by_is_in_the_serialised_trace_event():
    case = make(FixtureModules())
    run_case(case, Model(lambda offer: offer.default), lambda draft: "send")
    wire = case.trace.events[0].model_dump(mode="json")
    assert wire["chosen_by"] == "model"
    assert TraceEvent.model_validate(wire).chosen_by == "model"


# --- the model never moves the verdict ----------------------------------------------------------


@pytest.mark.parametrize("case_id", ["a", "b", "c"])
def test_the_verdict_and_card_are_identical_with_the_model_on_and_off(case_id):
    """a and b are the apartment cases, c is the house. The model picks the opposite order."""
    case = load_demo_case(case_id)
    listing = read_listing(case.listing_text)

    def run(chooser):
        session = make(demo_modules(case, listing))
        verdict = run_case(session, chooser, lambda draft: "send")
        return session, verdict

    off, verdict_off = run(PolicyChooser())
    on, verdict_on = run(Model(reversed_plan))
    assert verdict_on == verdict_off
    assert on.evidence == off.evidence
    stamps = {e.chosen_by for e in on.trace.events if e.choice is ChoiceKind.NEXT_CHECK}
    assert ("model" in stamps) is (case_id == "c")  # only the house had a menu worth picking from
    assert case_id in demo_case_ids()


def test_the_plan_runs_on_the_apartment_and_the_house_cases():
    for case_id in ("a", "b", "c"):
        case = load_demo_case(case_id)
        session = make(demo_modules(case, read_listing(case.listing_text)))
        run_case(session, PolicyChooser(), lambda draft: "send")
        picks = [e.pick for e in session.trace.events if e.choice is ChoiceKind.NEXT_CHECK]
        assert picks[0] == PlanKind.RECORD.value or picks[0] == PlanKind.BROKERAGE.value
        assert picks[-1] == PlanKind.REPORT.value, case_id


# --- the model is shown derived facts only, and never a menu of one ------------------------------

PLAN_FACT_KEYS = {
    "home_record_found",
    "for_sale_listing_active",
    "ad_names_a_license",
    "owner_on_public_record",
    "checks_run",
    "checks_left",
}


class Recorder(Model):
    def __init__(self):
        super().__init__(reversed_plan)
        self.offers: list[Offer] = []

    def choose(self, offer: Offer):
        self.offers.append(offer)
        return super().choose(offer)


@pytest.mark.parametrize("case_id", ["a", "b", "c"])
def test_the_offers_a_model_receives_never_carry_the_verdict(case_id):
    case = load_demo_case(case_id)
    session = make(demo_modules(case, read_listing(case.listing_text)))
    model = Recorder()
    run_case(session, model, lambda draft: "send")
    plan_offers = [o for o in model.offers if o.kind is ChoiceKind.NEXT_CHECK]
    assert all(set(o.facts) == PLAN_FACT_KEYS for o in plan_offers)
    states = {state.value for state in VerdictState}
    for offer in model.offers:
        seen = [
            *offer.options,
            *offer.aliases,
            offer.default,
            *offer.facts,
            *map(str, offer.facts.values()),
        ]
        for text in seen:
            assert "verdict" not in text.lower()
            assert text not in states


def test_a_menu_of_one_is_not_sent_to_the_model_and_is_stamped_policy():
    session = make(FixtureModules())  # only "home record" is open, then only "report pack"
    model = Recorder()
    run_case(session, model, lambda draft: "send")
    assert all(len(o.options) > 1 for o in model.offers)
    plan = [e for e in session.trace.events if e.choice is ChoiceKind.NEXT_CHECK]
    assert [e.pick for e in plan] == ["home record", "report pack"]
    assert {e.chosen_by for e in plan} == {"policy"}
    assert {e.reason for e in plan} == {"Only one option was open."}


# --- the words live in strings.py, in both languages ---------------------------------------------


def test_the_plans_words_exist_in_english_and_spanish():
    from snapback.agent.planner import PICK_KEY
    from snapback.card import strings

    keys = {key for key in strings.TABLES["en"] if key.startswith("plan.")}
    assert keys == {key for key in strings.TABLES["es"] if key.startswith("plan.")}
    assert set(PICK_KEY.values()) <= keys
    assert {"plan.skipped", "plan.only_option"} <= keys
    for lang in ("en", "es"):
        line = strings.text(
            "plan.skipped", lang, option="x", reason=strings.text("plan.skip.owner_off", lang)
        )
        assert line.endswith(".") and "{" not in line


def test_the_plan_speaks_spanish_when_the_case_does():
    session = CaseSession(
        "fx-1", FixtureModules(), Trace("fx-1", DataSource.FIXTURE), rng=random.Random(3), lang="es"
    )
    run_case(session, PolicyChooser(), lambda draft: "send")
    assert any(e.reason.startswith("Omitido ") for e in session.trace.events)
    assert any(e.reason == "Solo había una opción abierta." for e in session.trace.events)


# --- a lookup that found nothing to look up is not a license claim -------------------------------


def test_a_no_claim_license_result_is_kept_as_evidence_but_is_not_an_option():
    nothing = LicenseResult(status=LicenseStatus.NOT_CHECKED)  # what a live ad with no claim gives
    case = make(FixtureModules(license=nothing))
    assert offered(case) == ["home record"]
    assert "Skipped TREC license: the ad names no license to look up." in skipped_lines(case)
    offer = case.offer()
    assert offer is not None and offer.facts["ad_names_a_license"] is False
    run_case(case, PolicyChooser(), lambda draft: "send")
    assert case.evidence.license == nothing  # the card reads it exactly as before the plan


def test_a_license_claim_with_a_role_is_an_option_even_when_not_checked():
    claim = LicenseResult(status=LicenseStatus.NOT_CHECKED, claimed_role="agent")
    assert "TREC license" in offered(make(FixtureModules(license=claim)))
