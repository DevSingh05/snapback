"""A21 (#127): the reasons answer the renter's two questions first.

"Is this person allowed to rent it to me?" and "Is this home even for rent?" come before
where the photos were taken and what the rent is. Only the order changes: every state is what
it was.
"""

import json
from pathlib import Path

import pytest

from snapback.agent.demo import run_demo_case
from snapback.card import strings
from snapback.contracts import Evidence, ModuleEvidence, VerdictState
from snapback.verdict import REASON_ORDER, decide, to_evidence

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"

WHO = {
    "reason.authority_matches",
    "reason.authority_unknown",
    "reason.phone_flag",
    "reason.lookalike_link",
}
AVAILABILITY = {"reason.for_sale"}
PRESENCE = {
    "reason.presence_proven",
    "reason.presence_proven_not_authority",
    "reason.presence_missing",
}
PLACE = {"reason.located", "reason.not_located", "reason.not_indexed", "reason.unit_flag"}
PRICE_AND_REST = {"reason.price_flag", "reason.payment_flag", "reason.rule_flag"}
GROUPS = [WHO, AVAILABILITY, PRESENCE, PLACE, PRICE_AND_REST]


def key_of(reason: str) -> str:
    """The string-table key of a reason, so tests can speak of kinds, not sentences.

    A reason may carry a number ("listing photo 2"), so a template matches by its fixed start.
    """
    table = {k: v for k, v in strings.TABLES["en"].items() if k.startswith("reason.")}
    for key, template in table.items():
        if reason == template:
            return key
    for key, template in table.items():
        if "{" in template and reason.startswith(template.split("{")[0]):
            return key
    raise AssertionError(f"not a reason from the string table: {reason!r}")


def keys_of(reasons: list[str]) -> list[str]:
    return [key_of(reason) for reason in reasons]


def group_of(key: str) -> int:
    return next(index for index, group in enumerate(GROUPS) if key in group)


def evidence(**sections) -> ModuleEvidence:
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    return ModuleEvidence.model_validate(raw | sections)


def everything_at_once() -> ModuleEvidence:
    """A held case with one of every kind of reason."""
    return evidence(
        authority={"status": "unknown", "office_phone_match": "no", "link_domain": "lookalike"},
        for_sale={"status": "active"},
        price={"status": "below_range", "listed_rent": 900, "unit": "not_on_record"},
    )


# --- the order -----------------------------------------------------------------------------


def test_the_order_is_who_then_availability_then_presence_then_place_then_the_rest():
    verdict = decide(to_evidence(everything_at_once()))
    assert verdict.state is VerdictState.HOLD
    keys = keys_of(verdict.reasons)
    assert set(keys) >= {
        "reason.authority_unknown",
        "reason.phone_flag",
        "reason.lookalike_link",
        "reason.for_sale",
        "reason.located",
        "reason.unit_flag",
        "reason.price_flag",
        "reason.payment_flag",
    }
    groups = [group_of(key) for key in keys]
    assert groups == sorted(groups), keys
    assert keys[0] == "reason.authority_unknown"  # the first thing said is about who


def test_within_who_authority_comes_before_the_contact_lines():
    keys = keys_of(decide(to_evidence(everything_at_once())).reasons)
    who = [key for key in keys if key in WHO]
    assert who == ["reason.authority_unknown", "reason.phone_flag", "reason.lookalike_link"]


def test_a_passing_case_also_answers_who_first():
    passing = evidence(
        authority={
            "status": "matches_record",
            "manager_on_record": "Fixture Living LLC",
            "office_phone_match": "yes",
        },
        rules=[],
        price=None,
    )
    verdict = decide(to_evidence(passing))
    assert verdict.state is VerdictState.VERIFIED
    assert keys_of(verdict.reasons) == [
        "reason.authority_matches",
        "reason.presence_proven",
        "reason.located",
    ]


def test_when_nothing_could_be_placed_who_and_availability_still_come_first():
    unplaced = ModuleEvidence.model_validate(
        {
            "case_id": "fx-1",
            "source": "fixture",
            "authority": {"status": "unknown", "link_domain": "lookalike"},
            "price": {"status": "not_checked", "unit": "not_on_record"},
        }
    )
    verdict = decide(to_evidence(unplaced))
    assert verdict.state is VerdictState.HOLD  # red flags outrank "could not place" (#10)
    assert keys_of(verdict.reasons) == [
        "reason.lookalike_link",
        "reason.not_indexed",
        "reason.unit_flag",
    ]

    for_sale = ModuleEvidence.model_validate(
        {
            "case_id": "fx-1",
            "source": "fixture",
            "authority": {"status": "unknown", "office_phone_match": "no"},
            "for_sale": {"status": "active"},
        }
    )
    held = decide(to_evidence(for_sale))
    assert held.state is VerdictState.HOLD
    assert keys_of(held.reasons) == [
        "reason.phone_flag",
        "reason.for_sale",
        "reason.not_indexed",
    ]


def test_every_reason_the_verdict_can_give_has_a_place_in_the_order():
    ordered = set(REASON_ORDER)
    for key in strings.TABLES["en"]:
        if key.startswith("reason."):
            assert key in ordered, f"{key} has no place in REASON_ORDER"
    assert len(REASON_ORDER) == len(ordered)  # and none is listed twice


# --- only the order changed ----------------------------------------------------------------

STATES_ON_MAIN = {"a": VerdictState.DONT_PAY, "b": VerdictState.DONT_PAY, "c": VerdictState.HOLD}


@pytest.mark.parametrize("case_id", ["a", "b", "c"])
def test_the_demo_cases_keep_their_states_and_lead_with_who_or_availability(case_id):
    verdict, _ = run_demo_case(case_id)
    assert verdict.state is STATES_ON_MAIN[case_id]
    keys = keys_of(verdict.reasons)
    asked_first = WHO | AVAILABILITY
    if any(key in asked_first for key in keys):
        assert keys[0] in asked_first, keys


def test_case_c_leads_with_the_house_being_for_sale():
    verdict, _ = run_demo_case("c")
    assert keys_of(verdict.reasons) == ["reason.for_sale", "reason.not_indexed"]


def test_dont_pay_still_gives_only_its_proof():
    # Proof is the whole reason for DON'T PAY. Nothing is added to it, so nothing is reordered.
    for case_id, key in (("a", "reason.forged_copy"), ("b", "reason.photo_elsewhere")):
        verdict, _ = run_demo_case(case_id)
        assert keys_of(verdict.reasons) == [key]


@pytest.mark.parametrize(
    "flags",
    [
        {},
        {"price_flag": True},
        {"payment_flag": True},
        {"rule_flag": True},
        {"for_sale_flag": True},
        {"phone_flag": True},
        {"lookalike_link_flag": True},
        {"unit_flag": True},
        {"price_flag": True, "phone_flag": True, "for_sale_flag": True, "unit_flag": True},
    ],
)
def test_the_same_reasons_are_given_as_before_in_a_new_order(flags):
    base = to_evidence(evidence(rules=[], price=None)).model_dump()
    case = Evidence.model_validate(base | flags)
    verdict = decide(case)
    groups = [group_of(key) for key in keys_of(verdict.reasons)]
    assert groups == sorted(groups)
    assert len(verdict.reasons) == len(set(verdict.reasons))  # nothing said twice
    # One reason for each thing raised, plus where the photos are, who, and presence.
    raised = sum(bool(value) for key, value in flags.items() if key != "rule_flag")
    raised += 1 if flags.get("rule_flag") and not flags.get("payment_flag") else 0
    assert len(verdict.reasons) == 3 + raised
