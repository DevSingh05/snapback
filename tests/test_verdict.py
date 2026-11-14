import itertools
import json
from pathlib import Path

import pytest

from snapback.card import strings
from snapback.contracts import (
    AuthorityStatus,
    DataSource,
    Evidence,
    LocateStatus,
    ModuleEvidence,
    PhotoLocation,
    PresenceStatus,
    RuleCategory,
    VerdictState,
)
from snapback.verdict import decide, to_evidence

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"


def modules(name: str = "module_evidence_hold.json", **top_level) -> ModuleEvidence:
    """A cross-lane fixture with some top-level sections replaced."""
    data = json.loads((FIXTURES / name).read_text())
    return ModuleEvidence.model_validate(data | top_level)


def blocked_reply(photo_id: str = "r1", label: str = "screen") -> dict:
    return {
        "photo_id": photo_id,
        "label": label,
        "score": 0.93,
        "blocks_pass": True,
        "model_version": "v0",
    }


def rule(rule_id: str, category: str, red_flag: bool = True) -> dict:
    return {"rule_id": rule_id, "category": category, "red_flag": red_flag}


def photo(status: LocateStatus, photo_id: str = "p1") -> PhotoLocation:
    return PhotoLocation(photo_id=photo_id, status=status)


def evidence(**overrides) -> Evidence:
    base = {
        "case_id": "case-1",
        "source": DataSource.FIXTURE,
        "photos": [photo(LocateStatus.LOCATED_IN_CLAIMED)],
    }
    return Evidence(**(base | overrides))


def test_located_photos_alone_are_only_hold():
    # The trap this product exists for: real photos prove nothing about the poster.
    assert decide(evidence()).state is VerdictState.HOLD


def test_no_reply_yet_is_hold_not_failure():
    result = decide(evidence(presence=PresenceStatus.WAITING, authority=AuthorityStatus.MISMATCH))
    assert result.state is VerdictState.HOLD


def test_presence_without_authority_stays_hold():
    result = decide(evidence(presence=PresenceStatus.PROVEN, authority=AuthorityStatus.UNKNOWN))
    assert result.state is VerdictState.HOLD


def test_presence_with_record_mismatch_stays_hold():
    result = decide(evidence(presence=PresenceStatus.PROVEN, authority=AuthorityStatus.MISMATCH))
    assert result.state is VerdictState.HOLD


def test_presence_and_authority_together_verify():
    result = decide(
        evidence(presence=PresenceStatus.PROVEN, authority=AuthorityStatus.MATCHES_RECORD)
    )
    assert result.state is VerdictState.VERIFIED


def test_forged_reply_is_dont_pay_with_its_reason():
    result = decide(
        evidence(presence=PresenceStatus.FORGED, forgery_reason="Reply is listing photo 3.")
    )
    assert result.state is VerdictState.DONT_PAY
    assert result.reasons == ["Reply is listing photo 3."]


def test_photo_from_another_property_is_dont_pay():
    photos = [photo(LocateStatus.LOCATED_IN_CLAIMED), photo(LocateStatus.LOCATED_ELSEWHERE, "p2")]
    assert decide(evidence(photos=photos)).state is VerdictState.DONT_PAY


@pytest.mark.parametrize("flag", ["price_flag", "payment_flag", "rule_flag"])
def test_record_mismatch_is_hold_even_with_a_red_flag(flag):
    # A mismatch is not proof: owners live elsewhere and agents act for them.
    result = decide(evidence(authority=AuthorityStatus.MISMATCH, **{flag: True}))
    assert result.state is VerdictState.HOLD


@pytest.mark.parametrize("flag", ["price_flag", "payment_flag", "rule_flag"])
def test_any_red_flag_blocks_the_top_state(flag):
    result = decide(
        evidence(
            presence=PresenceStatus.PROVEN,
            authority=AuthorityStatus.MATCHES_RECORD,
            **{flag: True},
        )
    )
    assert result.state is VerdictState.HOLD
    assert len(result.reasons) == 4  # the three findings plus the flag that held it back


def test_dont_pay_needs_proof_and_the_top_state_needs_everything():
    # Every combination that has no forged reply and no photo from another building.
    not_forged = [PresenceStatus.NOT_REQUESTED, PresenceStatus.WAITING, PresenceStatus.PROVEN]
    flags = [False, True]
    for authority, presence, price, payment, rules in itertools.product(
        AuthorityStatus, not_forged, flags, flags, flags
    ):
        state = decide(
            evidence(
                authority=authority,
                presence=presence,
                price_flag=price,
                payment_flag=payment,
                rule_flag=rules,
            )
        ).state
        assert state is not VerdictState.DONT_PAY
        everything = (
            presence is PresenceStatus.PROVEN
            and authority is AuthorityStatus.MATCHES_RECORD
            and not (price or payment or rules)
        )
        assert (state is VerdictState.VERIFIED) == everything


def test_red_flag_without_a_mismatch_is_not_dont_pay():
    assert decide(evidence(price_flag=True, payment_flag=True)).state is VerdictState.HOLD


@pytest.mark.parametrize(
    "photos",
    [[], [photo(LocateStatus.NOT_INDEXED)], [photo(LocateStatus.NOT_LOCATED)]],
)
def test_nothing_located_in_the_claimed_property_is_unverified(photos):
    assert decide(evidence(photos=photos)).state is VerdictState.UNVERIFIED


def test_verdict_keeps_the_data_source_label():
    assert decide(evidence(source=DataSource.LIVE)).source is DataSource.LIVE


def test_no_verdict_ever_says_scam():
    cases = [
        evidence(),
        evidence(presence=PresenceStatus.FORGED),
        evidence(photos=[photo(LocateStatus.LOCATED_ELSEWHERE)]),
        evidence(authority=AuthorityStatus.MISMATCH, price_flag=True),
        evidence(photos=[]),
    ]
    for case in cases:
        assert all("scam" not in reason.lower() for reason in decide(case).reasons)


def test_decide_reasons_come_from_the_string_table(monkeypatch):
    markers = {key: f"<{key}>" for key in strings.TABLES["en"]}
    monkeypatch.setitem(strings.TABLES, "en", markers)
    cases = [
        evidence(),
        evidence(presence=PresenceStatus.FORGED),
        evidence(photos=[photo(LocateStatus.LOCATED_ELSEWHERE)]),
        evidence(authority=AuthorityStatus.MISMATCH, price_flag=True, payment_flag=True),
        evidence(authority=AuthorityStatus.MATCHES_RECORD, rule_flag=True),
        evidence(photos=[]),
        evidence(photos=[photo(LocateStatus.NOT_LOCATED)]),
        evidence(presence=PresenceStatus.PROVEN, authority=AuthorityStatus.MATCHES_RECORD),
        evidence(presence=PresenceStatus.PROVEN, authority=AuthorityStatus.MISMATCH),
    ]
    for case in cases:
        reasons = decide(case).reasons
        assert reasons
        assert all(reason.startswith("<") and reason.endswith(">") for reason in reasons)


# --- ModuleEvidence -> Evidence -> decide() ------------------------------------------------------


def test_forged_fixture_is_dont_pay():
    verdict = decide(to_evidence(modules("module_evidence_forged.json")))
    assert verdict.state is VerdictState.DONT_PAY
    assert verdict.reasons == ["The reply is a copy of listing photo 1."]


def test_hold_fixture_is_hold():
    assert decide(to_evidence(modules())).state is VerdictState.HOLD


def test_module_evidence_with_nothing_in_it_is_unverified():
    empty = ModuleEvidence(case_id="fx-0000", source=DataSource.FIXTURE)
    assert decide(to_evidence(empty)).state is VerdictState.UNVERIFIED


def test_challenge_presence_and_authority_are_lifted_as_they_are():
    flat = to_evidence(modules())
    assert flat.case_id == "fx-7Q2M"
    assert flat.source is DataSource.FIXTURE
    assert flat.presence is PresenceStatus.PROVEN
    assert flat.authority is AuthorityStatus.UNKNOWN
    assert [p.photo_id for p in flat.photos] == ["l1", "l2", "l3"]


def test_no_challenge_means_presence_was_not_requested():
    flat = to_evidence(modules(challenge=None, recapture=[], memory=[]))
    assert flat.presence is PresenceStatus.NOT_REQUESTED


def test_same_case_memory_hit_forges_presence_and_names_the_photo():
    hit = {
        "photo_id": "r2",
        "hit": "same_case_listing",
        "method": "phash",
        "matched_listing_photo_id": "l3",
    }
    flat = to_evidence(modules(memory=[hit]))
    assert flat.presence is PresenceStatus.FORGED
    assert flat.forgery_reason == "The reply is a copy of listing photo 3."
    assert decide(flat).state is VerdictState.DONT_PAY


def test_same_case_memory_hit_without_a_known_photo_still_forges_presence():
    hit = {"photo_id": "r2", "hit": "same_case_listing", "method": "phash"}
    flat = to_evidence(modules(memory=[hit]))
    assert flat.presence is PresenceStatus.FORGED
    assert flat.forgery_reason


def test_other_check_memory_hit_does_not_change_the_state():
    hit = {"photo_id": "l1", "hit": "other_check", "method": "phash", "first_seen_on": "2026-11-12"}
    assert decide(to_evidence(modules(memory=[hit]))).state is VerdictState.HOLD


def test_recapture_block_stops_presence_becoming_proven():
    flat = to_evidence(modules(recapture=[blocked_reply()]))
    assert flat.presence is PresenceStatus.WAITING


@pytest.mark.parametrize("label", ["screen", "print", "paste", "unknown"])
def test_recapture_alone_never_dont_pay(label):
    # A recapture flag can only stop a pass. Even with every other row clean it is a HOLD.
    clean = modules(
        recapture=[blocked_reply(label=label), blocked_reply("r2", label)],
        rules=[],
        authority={"status": "matches_record", "manager_on_record": "Fixture Living LLC"},
    )
    assert decide(to_evidence(clean)).state is VerdictState.HOLD
    # And it does not turn a waiting challenge into a failure either.
    waiting = json.loads((FIXTURES / "module_evidence_hold.json").read_text())["challenge"]
    waiting["presence"] = "waiting"
    still_waiting = modules(challenge=waiting, recapture=[blocked_reply(label=label)])
    assert decide(to_evidence(still_waiting)).state is VerdictState.HOLD


def test_recapture_that_does_not_block_leaves_presence_proven():
    assert to_evidence(modules()).presence is PresenceStatus.PROVEN


@pytest.mark.parametrize("category", ["payment_method", "fee_ask", "data_ask"])
def test_red_flag_rule_about_money_or_data_sets_the_payment_flag(category):
    flat = to_evidence(modules(rules=[rule("fx.rule", category)]))
    assert flat.payment_flag is True


@pytest.mark.parametrize("category", ["pressure", "link"])
def test_pressure_and_link_rules_do_not_set_the_payment_flag(category):
    flat = to_evidence(modules(rules=[rule("fx.rule", category)]))
    assert flat.payment_flag is False
    assert flat.rule_flag is True


MATCHES = {"status": "matches_record", "manager_on_record": "Fixture Living LLC"}
IN_RANGE = {"status": "within_range", "listed_rent": 1900}


def test_authority_match_with_a_zelle_red_flag_is_hold():
    # The hold fixture has proven presence and a Zelle-before-viewing hit.
    assert decide(to_evidence(modules(authority=MATCHES))).state is VerdictState.HOLD


@pytest.mark.parametrize("category", [category.value for category in RuleCategory])
def test_a_red_flag_rule_in_any_category_blocks_the_top_state(category):
    flagged = modules(authority=MATCHES, price=IN_RANGE, rules=[rule("fx.rule", category)])
    assert decide(to_evidence(flagged)).state is VerdictState.HOLD


def test_a_rule_that_is_not_a_red_flag_does_not_block_the_top_state():
    noted = modules(
        authority=MATCHES, price=IN_RANGE, rules=[rule("fx.rule", "pressure", red_flag=False)]
    )
    assert to_evidence(noted).rule_flag is False
    assert decide(to_evidence(noted)).state is VerdictState.VERIFIED


def test_clean_case_with_presence_and_authority_reaches_the_top_state():
    clean = modules(authority=MATCHES, price=IN_RANGE, rules=[])
    assert decide(to_evidence(clean)).state is VerdictState.VERIFIED


def test_mismatch_with_a_low_rent_and_a_payment_ask_is_hold_without_a_forgery():
    # The forged fixture minus its forgery: mismatch and a rent far under the record.
    data = json.loads((FIXTURES / "module_evidence_forged.json").read_text())
    data["memory"] = []
    data["recapture"] = []
    data["challenge"]["presence"] = "proven"
    data["rules"] = [rule("payment.zelle_before_viewing", "payment_method")]
    assert decide(to_evidence(ModuleEvidence.model_validate(data))).state is VerdictState.HOLD


def test_rule_that_is_not_a_red_flag_does_not_set_the_payment_flag():
    flat = to_evidence(modules(rules=[rule("fx.rule", "payment_method", red_flag=False)]))
    assert flat.payment_flag is False


def test_below_range_sets_the_price_flag_but_is_not_dont_pay_alone():
    below = modules(price={"status": "below_range", "listed_rent": 900}, rules=[])
    flat = to_evidence(below)
    assert flat.price_flag is True
    assert decide(flat).state is VerdictState.HOLD


@pytest.mark.parametrize("status", ["within_range", "not_checked"])
def test_other_price_statuses_do_not_set_the_price_flag(status):
    assert to_evidence(modules(price={"status": status})).price_flag is False
