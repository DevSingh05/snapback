"""The aerial can hold a case. It never fails one on its own and never clears one.

Behind SNAPBACK_VEXCEL_IN_VERDICT (off by default): when on and the aerial says the ad's
building is not the claimed one, the case is held. Code sets the state (decide()).
"""

import json
from pathlib import Path

import pytest

from snapback.card import strings
from snapback.contracts import Evidence, ModuleEvidence, VerdictState
from snapback.settings import get_settings
from snapback.verdict import REASON_ORDER, decide, to_evidence

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
WRONG = {"status": "wrong_building", "distance_m": 180.0}
RIGHT = {"status": "right_building", "distance_m": 3.0}


def modules(**sections) -> ModuleEvidence:
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    return ModuleEvidence.model_validate(raw | sections)


@pytest.fixture
def setting(monkeypatch):
    def put(on: bool | None):
        if on is None:
            monkeypatch.delenv("SNAPBACK_VEXCEL_IN_VERDICT", raising=False)
        else:
            monkeypatch.setenv("SNAPBACK_VEXCEL_IN_VERDICT", "true" if on else "false")
        get_settings.cache_clear()

    yield put
    get_settings.cache_clear()


def test_the_setting_is_off_by_default(setting):
    setting(None)
    assert get_settings().snapback_vexcel_in_verdict is False


def test_off_the_aerial_changes_nothing(setting):
    setting(False)
    base = decide(to_evidence(modules()))
    with_aerial = decide(to_evidence(modules(aerial=WRONG)))
    assert to_evidence(modules(aerial=WRONG)).aerial_wrong_building_flag is False
    assert with_aerial == base


def test_on_a_wrong_building_holds_the_case(setting):
    setting(True)
    evidence = to_evidence(modules(aerial=WRONG))
    assert evidence.aerial_wrong_building_flag is True
    verdict = decide(evidence)
    assert verdict.state is VerdictState.HOLD
    assert strings.text("reason.aerial_wrong_building") in verdict.reasons


def test_on_a_wrong_building_never_gives_dont_pay_alone():
    # Even with nothing else known, the aerial alone is HOLD, never DONT_PAY.
    verdict = decide(Evidence(case_id="c", source="fixture", aerial_wrong_building_flag=True))
    assert verdict.state is VerdictState.HOLD


def test_a_right_building_never_clears_a_case(setting):
    setting(True)
    base = decide(to_evidence(modules()))
    assert decide(to_evidence(modules(aerial=RIGHT))) == base
    assert to_evidence(modules(aerial=RIGHT)).aerial_wrong_building_flag is False


def test_a_wrong_building_stops_a_case_that_would_verify(setting):
    setting(True)
    flagged = Evidence(
        case_id="c",
        source="fixture",
        photos=[{"photo_id": "l1", "status": "located_in_claimed"}],
        authority="matches_record",
        presence="proven",
        phone_confirmed=True,
        aerial_wrong_building_flag=True,
    )
    assert decide(flagged).state is VerdictState.HOLD
    assert decide(flagged.model_copy(update={"aerial_wrong_building_flag": False})).state is (
        VerdictState.VERIFIED
    )


def test_proof_still_outranks_the_aerial():
    forged = Evidence(
        case_id="c", source="fixture", presence="forged", aerial_wrong_building_flag=True
    )
    assert decide(forged).state is VerdictState.DONT_PAY


def test_the_reason_is_placed_and_translated():
    assert "reason.aerial_wrong_building" in REASON_ORDER
    for lang in ("en", "es"):
        assert strings.text("reason.aerial_wrong_building", lang)
