"""A18 (#124, floor item F2): the licence line on the card, from lane D's TREC lookup (D10).

No real person or licence is in here: the lookup's result holds no name and no number, and
every result below is written by the test.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.agent.join import KitLookups
from snapback.api.main import create_app
from snapback.card import strings
from snapback.contracts import (
    CardRowKind,
    CardTone,
    DataSource,
    LicenseResult,
    LicenseStatus,
    ModuleEvidence,
    VerdictState,
)
from snapback.settings import Settings
from snapback.verdict import REASON_ORDER, build_card, decide, to_evidence

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")
MATCHES = {
    "status": "matches_record",
    "manager_on_record": "Fixture Living LLC",
    "office_phone_match": "yes",
}
NOT_FOUND = {"status": "not_found", "claimed_role": "agent"}
LICENSED = {"status": "licensed", "claimed_role": "agent", "sponsor_broker": "Fixture Realty Group"}
NOT_FOUND_TEXT = (
    "Says they're a licensed agent. We found no active Texas license under that name. "
    "Ask for their license number and look it up yourself at trec.texas.gov. Red flag."
)


def evidence(**sections) -> ModuleEvidence:
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    return ModuleEvidence.model_validate(raw | sections)


def passing(**sections) -> ModuleEvidence:
    """A case that is VERIFIED unless something in `sections` holds it."""
    return evidence(**({"authority": MATCHES, "rules": [], "price": None} | sections))


def state(modules: ModuleEvidence) -> VerdictState:
    return decide(to_evidence(modules)).state


def person(modules: ModuleEvidence, lang: str = "en") -> dict[str, tuple[CardTone, str]]:
    card = build_card(modules, checked_at=CHECKED_AT, lang=lang)
    row = next(row for row in card.rows if row.kind is CardRowKind.PERSON)
    return {item.label: (item.tone, item.text) for item in row.lines}


# --- claims to be licensed, and is not -----------------------------------------------------


def test_a_claimed_licence_that_is_not_found_is_a_red_flag_and_holds_the_case():
    assert state(passing()) is VerdictState.VERIFIED
    modules = passing(license=NOT_FOUND)
    assert to_evidence(modules).license_flag is True
    verdict = decide(to_evidence(modules))
    assert verdict.state is VerdictState.HOLD
    assert strings.text("reason.license_not_found") in verdict.reasons
    assert person(modules)["License"] == (CardTone.RED_FLAG, NOT_FOUND_TEXT)


@pytest.mark.parametrize("role", ["agent", "broker", "locator"])
def test_the_line_names_the_role_they_claimed(role):
    line = person(passing(license={"status": "not_found", "claimed_role": role}))["License"][1]
    assert line.startswith(f"Says they're a licensed {role}.")


def test_a_brokerage_named_in_the_listing_gets_its_own_wording():
    # D10, amendment 2: "listed by X Realty" is looked up as a company.
    company = {"status": "not_found", "claimed_role": "company"}
    assert person(passing(license=company))["License"] == (
        CardTone.RED_FLAG,
        "Says a brokerage lists this home. We found no active Texas license under that "
        "company's name. Ask for its license number and look it up yourself at "
        "trec.texas.gov. Red flag.",
    )
    assert state(passing(license=company)) is VerdictState.HOLD
    found = {"status": "licensed", "claimed_role": "company"}
    assert person(passing(license=found))["License"] == (
        CardTone.OK,
        "The brokerage they named is licensed in Texas.",
    )
    assert state(passing(license=found)) is VerdictState.VERIFIED


def test_the_poster_s_own_words_are_never_put_on_the_card():
    # `claimed_role` is typed as text. Only our three roles and "company" are ever said; any
    # other value gets the general wording, and the value itself goes nowhere.
    odd = {"status": "not_found", "claimed_role": "Fx Person <b>agent</b>"}
    tone, text = person(passing(license=odd))["License"]
    assert tone is CardTone.RED_FLAG
    assert text.startswith("Says they're licensed. We found no active Texas license")
    said = build_card(passing(license=odd), checked_at=CHECKED_AT).model_dump_json()
    assert "Fx Person" not in said and "<b>" not in said


def test_a_sponsor_name_is_folded_and_cut_to_a_sane_length():
    long = {"status": "licensed", "claimed_role": "agent", "sponsor_broker": "Fx  Realty\n" * 40}
    text = person(passing(license=long))["License"][1]
    assert "\n" not in text and "  " not in text
    assert len(text) <= len("Licensed in Texas, sponsored by .") + 80


def test_no_licence_is_never_dont_pay_whatever_else_is_true():
    # DON'T PAY needs proof. Not finding a licence is not proof of anything.
    assert state(evidence(license=NOT_FOUND)) is VerdictState.HOLD
    assert state(evidence(license=NOT_FOUND, challenge=None)) is VerdictState.HOLD
    nothing_placed = ModuleEvidence(case_id="fx-1", source="fixture", license=NOT_FOUND)
    verdict = decide(to_evidence(nothing_placed))
    assert verdict.state is VerdictState.UNVERIFIED
    assert strings.text("reason.license_not_found") in verdict.reasons


# --- licensed ------------------------------------------------------------------------------


def test_a_licence_is_a_supporting_line_and_never_lifts_authority():
    # Licensed, presence proven, nothing flagged, and still nobody on the record named: the
    # licence does not answer "allowed to rent it", so the case holds exactly as without it.
    unknown = {"status": "unknown"}
    without = passing(authority=unknown)
    licensed = passing(authority=unknown, license=LICENSED)
    assert state(without) is state(licensed) is VerdictState.HOLD
    assert person(licensed)["License"] == (
        CardTone.OK,
        "Licensed in Texas, sponsored by Fixture Realty Group.",
    )
    assert person(licensed)["Allowed to rent it"] == person(without)["Allowed to rent it"]
    assert to_evidence(licensed).license_flag is False


def test_a_licence_does_not_get_in_the_way_of_a_passing_case():
    assert state(passing(license=LICENSED)) is VerdictState.VERIFIED


def test_a_licence_with_no_company_sponsor_names_no_one():
    lone = {"status": "licensed", "claimed_role": "broker", "sponsor_broker": None}
    assert person(passing(license=lone))["License"] == (CardTone.OK, "Licensed in Texas.")


# --- not checked ---------------------------------------------------------------------------


def test_no_claim_is_not_checked_and_changes_nothing():
    no_claim = {"status": "not_checked", "claimed_role": None}
    modules = passing(license=no_claim)
    assert state(modules) is VerdictState.VERIFIED
    tone, text = person(modules)["License"]
    assert tone is CardTone.NOT_CHECKED
    assert text == "Not checked (the poster did not say they are an agent, broker or locator)."


def test_a_lookup_that_failed_is_not_checked_and_never_a_flag():
    # A timeout, a rate limit or an ambiguous answer: the poster claimed a role and we could
    # not look them up. That says nothing about them.
    failed = {"status": "not_checked", "claimed_role": "agent"}
    modules = passing(license=failed)
    assert state(modules) is VerdictState.VERIFIED
    assert to_evidence(modules).license_flag is False
    tone, text = person(modules)["License"]
    assert tone is CardTone.NOT_CHECKED
    assert text == "Not checked (we could not look the poster up in the Texas license list)."


def test_a_case_that_was_never_looked_up_has_no_licence_line():
    assert "License" not in person(passing())
    assert "License" not in person(evidence())


# --- the phone, and the D10 hook from #121 -------------------------------------------------


def test_a_phone_mismatch_and_no_licence_together_are_a_red_flag_again():
    # By itself a number that is not the office's is Not confirmed (#121). An agent often
    # uses their own. A poster who claims a licence they do not hold has no such excuse.
    differs = MATCHES | {"office_phone_match": "no"}
    alone = person(passing(authority=differs))["Contact on record"]
    assert alone[0] is CardTone.NOT_SHOWN

    both = person(passing(authority=differs, license=NOT_FOUND))["Contact on record"]
    assert both[0] is CardTone.RED_FLAG
    # The manager is named on the "Allowed to rent it" line, so this one does not say "call".
    assert both[1] == (
        "This number is not the leasing office's on record, and we found no active Texas "
        "license under the name they gave. Red flag."
    )
    unnamed = {"status": "unknown", "office_phone_match": "no"}
    assert person(passing(authority=unnamed, license=NOT_FOUND))["Contact on record"] == (
        CardTone.RED_FLAG,
        "This number is not the leasing office's on record, and we found no active Texas "
        "license under the name they gave. Call the office on record yourself. Red flag.",
    )
    # The verdict counts it as a red flag too, and the reason is still said once.
    verdict = decide(to_evidence(passing(authority=differs, license=NOT_FOUND)))
    assert verdict.state is VerdictState.HOLD
    assert verdict.reasons.count(strings.text("reason.phone_flag")) == 1
    # A licence that IS found leaves the phone line as it was.
    assert person(passing(authority=differs, license=LICENSED))["Contact on record"] == alone


# --- wording, order, Spanish ---------------------------------------------------------------


def test_the_licence_reason_sits_with_who_after_the_contact_lines():
    order = list(REASON_ORDER)
    assert order.index("reason.lookalike_link") < order.index("reason.license_not_found")
    assert order.index("reason.license_not_found") < order.index("reason.for_sale")
    differs = {"status": "unknown", "office_phone_match": "no"}
    verdict = decide(
        to_evidence(evidence(authority=differs, license=NOT_FOUND, for_sale={"status": "active"}))
    )
    said = verdict.reasons
    assert said.index(strings.text("reason.phone_flag")) < said.index(
        strings.text("reason.license_not_found")
    )
    assert said.index(strings.text("reason.license_not_found")) < said.index(
        strings.text("reason.for_sale")
    )


@pytest.mark.parametrize(
    "result",
    [
        NOT_FOUND,
        LICENSED,
        {"status": "not_checked"},
        {"status": "not_checked", "claimed_role": "x"},
    ],
)
def test_every_licence_line_follows_the_wording_rules_in_both_languages(result):
    differs = MATCHES | {"office_phone_match": "no"}
    for lang, red, unchecked, banned in (
        ("en", "Red flag.", "Not checked", ("safe", "verified", "scam")),
        ("es", "Señal de alerta.", "No comprobado", ("estafa", "seguro", "verificado")),
    ):
        lines = person(passing(authority=differs, license=result), lang)
        for tone, text in lines.values():
            assert not any(word in text.lower() for word in banned), text
            assert "—" not in text
            assert text.endswith(red) == (tone is CardTone.RED_FLAG), text
            if tone is CardTone.NOT_CHECKED:
                assert text.startswith(unchecked), text
    assert set(strings.TABLES["es"]) == set(strings.TABLES["en"])


def test_nothing_about_the_licence_names_a_person_or_a_number():
    modules = passing(license=LICENSED)
    card = build_card(modules, checked_at=CHECKED_AT)
    assert set(LicenseResult.model_fields) == {"status", "claimed_role", "sponsor_broker", "state"}
    said = card.model_dump_json()
    assert "Fixture Realty Group" in said  # a company, which is allowed
    assert not any(ch.isdigit() for ch in person(modules)["License"][1])


# --- through the join ----------------------------------------------------------------------


class Lookups:
    """Stand-in for lane D's adapters with a licence answer."""

    def __init__(self, license: LicenseResult | None = None, fail: bool = False) -> None:
        self._license, self._fail = license, fail
        self.asked: list[str] = []

    def record(self, property_id: str):
        return None

    def for_sale(self, listing_text: str):
        return None

    def license(self, listing_text: str) -> LicenseResult | None:
        self.asked.append(listing_text)
        if self._fail:
            raise RuntimeError("the licence list did not answer")
        return self._license


def card_from(tmp_path, lookups) -> dict:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    client = TestClient(create_app(settings, lookups))
    made = client.post("/cases", data={"text": "2 bed. I am a licensed agent."}).json()
    if made["status"] == "waiting_for_approval":
        client.post(
            f"/cases/{made['case_id']}/challenge/approve",
            json={"decision": "send"},
            headers={"Authorization": f"Bearer {made['token']}"},
        )
    return client.get(f"/cases/{made['case_id']}/card").json()


def test_the_lookup_result_reaches_the_card(tmp_path):
    lookups = Lookups(LicenseResult(status=LicenseStatus.NOT_FOUND, claimed_role="agent"))
    card = card_from(tmp_path, lookups)
    assert lookups.asked == ["2 bed. I am a licensed agent."]
    said = {line["label"]: line for row in card["rows"] for line in row["lines"]}
    assert said["License"]["tone"] == "red_flag" and said["License"]["text"] == NOT_FOUND_TEXT
    assert card["state"] == "hold"


def test_a_lookup_that_breaks_leaves_no_line_and_stops_nothing(tmp_path):
    card = card_from(tmp_path, Lookups(fail=True))
    labels = [line["label"] for row in card["rows"] for line in row["lines"]]
    assert "License" not in labels and card["state"] in ("hold", "verified", "unverified")


def test_lookups_from_before_d10_still_work(tmp_path):
    class Older:
        def record(self, property_id: str):
            return None

        def for_sale(self, listing_text: str):
            return None

    card = card_from(tmp_path, Older())
    assert "License" not in [line["label"] for row in card["rows"] for line in row["lines"]]


def test_a_live_run_asks_lane_d_s_lookup_and_no_test_touches_the_network(monkeypatch):
    import snapback.adapters.trec as trec

    asked = []

    def stand_in(text, **kwargs):
        asked.append(text)
        return LicenseResult(status=LicenseStatus.LICENSED, claimed_role="agent")

    monkeypatch.setattr(trec, "check_license", stand_in)
    found = KitLookups(DataSource.LIVE).license("I am a licensed agent, Fx Person")
    assert found is not None and found.status is LicenseStatus.LICENSED
    assert asked == ["I am a licensed agent, Fx Person"]


def test_a_fixture_run_never_calls_the_licence_list(monkeypatch):
    # The real lookup goes out to a public list. A fixture run, and so every test, must not.
    import snapback.adapters.trec as trec

    def no_network(*args, **kwargs):
        raise AssertionError("the licence list was called in a fixture run")

    monkeypatch.setattr(trec, "check_license", no_network)
    assert KitLookups(DataSource.FIXTURE).license("I am a licensed agent, Fx Person") is None
