"""A24 stretch: the agent may ask the renter for the license number the ad did not give.

One code-written option, one fixed field, one static map of what the answer unlocks. No
network and no key: the model is a stand-in chooser that picks from the same offers.
"""

import json
import random
import re

import pytest

from snapback.agent import (
    CaseSession,
    FixtureModules,
    Offer,
    PolicyChooser,
    Trace,
    planner,
    run_case,
)
from snapback.agent.demo_ask import ask_modules, run_ask_demo, staged_answer
from snapback.agent.planner import PlanKind, extract_license_number
from snapback.card import strings
from snapback.contracts import (
    ChoiceKind,
    DataSource,
    LicenseResult,
    LicenseStatus,
    OwnerKind,
    OwnerResult,
    TraceKind,
    VerdictState,
)
from snapback.verdict import build_card

ASK = PlanKind.ASK.value
CLAIM = LicenseResult(status=LicenseStatus.NOT_CHECKED, claimed_role="agent")
SECRET_ANSWER = "ok here it is, TREC # 0900123, thanks"  # a number inside other words


def licensed() -> LicenseResult:
    return LicenseResult(status=LicenseStatus.LICENSED, claimed_role="agent")


class Spy(FixtureModules):
    """Counts every lookup, so a test can say exactly which ones ran again."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls: list[str] = []

    def price(self, case_id):
        self.calls.append("price")
        return super().price(case_id)

    def authority(self, case_id):
        self.calls.append("authority")
        return super().authority(case_id)

    def for_sale(self, case_id):
        self.calls.append("for_sale")
        return super().for_sale(case_id)

    def license(self, case_id):
        self.calls.append("license")
        return super().license(case_id)

    def owner(self, case_id):
        self.calls.append("owner")
        return OwnerResult(kind=OwnerKind.COMPANY, company="Example Holdings LLC")

    def license_by_number(self, case_id, number):
        self.calls.append("license_by_number")
        return super().license_by_number(case_id, number)


def make(modules, **kwargs) -> CaseSession:
    return CaseSession(
        "fx-1", modules, Trace("fx-1", DataSource.FIXTURE), rng=random.Random(3), **kwargs
    )


def walk_to_plan(case: CaseSession) -> Offer:
    case.choose_default()  # the first choice: which kinds of check
    offer = case.offer()
    assert offer is not None and offer.kind is ChoiceKind.NEXT_CHECK
    return offer


def approve(draft):
    return "send"


class Model:
    chosen_by = "model"

    def __init__(self, pick):
        self.pick = pick
        self.seen: list[Offer] = []

    def choose(self, offer: Offer):
        self.seen.append(offer)
        return self.pick(offer), "Chosen for the facts shown."


def ask_first(offer: Offer) -> str:
    return ASK if ASK in offer.options else offer.default


# --- offered only when the ad claims a license and gives no number ---------------------------


def test_the_question_is_offered_for_a_claim_without_a_number():
    case = make(FixtureModules(license=CLAIM))
    assert ASK in walk_to_plan(case).options


@pytest.mark.parametrize(
    "result",
    [
        None,
        LicenseResult(status=LicenseStatus.NOT_CHECKED),  # no claim at all
        licensed(),
        LicenseResult(status=LicenseStatus.NOT_FOUND, claimed_role="agent", number_in_ad=True),
        # the ad gave a number and the state could not settle it: the renter has no new number
        LicenseResult(status=LicenseStatus.NOT_CHECKED, claimed_role="agent", number_in_ad=True),
    ],
)
def test_it_is_not_offered_otherwise_and_the_skip_says_why(result):
    case = make(FixtureModules(license=result))
    assert ASK not in walk_to_plan(case).options
    line = f"Skipped {ASK}: the ad does not claim a license without giving its number."
    assert line in [e.reason for e in case.trace.events]


def test_it_is_skipped_when_the_case_may_not_ask():
    case = make(FixtureModules(license=CLAIM), ask_enabled=False)
    assert ASK not in walk_to_plan(case).options
    assert f"Skipped {ASK}: asking the renter is not available." in [
        e.reason for e in case.trace.events
    ]


def test_modules_that_cannot_look_up_by_number_never_offer_it():
    class NoLookup:
        def __getattr__(self, name):
            if name == "license_by_number":
                raise AttributeError(name)
            return getattr(FixtureModules(license=CLAIM), name)

    assert ASK not in walk_to_plan(make(NoLookup())).options


# --- the question and the field are fixed in code --------------------------------------------


def test_the_only_field_that_can_be_asked_is_the_license_number():
    assert planner.ASK_FIELDS == ("license_number",)
    case = make(FixtureModules(license=CLAIM))
    walk_to_plan(case)
    plan = case._plan
    with pytest.raises(ValueError):
        plan.answer("phone_number", "555-010-0199")


def test_the_question_is_the_code_string_whatever_the_model_says():
    case = make(FixtureModules(license=CLAIM))
    walk_to_plan(case)
    case.choose(ASK, "Ask them for their date of birth and bank details please.", by="model")
    assert case.waiting_for_answer
    assert case.question == strings.text("plan.ask.question")
    statuses = [e.reason for e in case.trace.events if e.kind is TraceKind.STATUS]
    assert strings.text("plan.ask.question") in statuses
    assert not any("bank" in line or "birth" in line for line in statuses)


def test_the_question_exists_in_english_and_spanish_in_plain_words():
    for lang in ("en", "es"):
        for key in (
            "plan.pick.ask",
            "plan.ask.question",
            "plan.ask.looked_up",
            "plan.ask.no_number",
        ):
            text = strings.text(key, lang)
            assert text and "{" not in text and "\u2014" not in text and "\u2013" not in text
    assert "licensed agent" in strings.text("plan.ask.question", "en")


# --- the answer re-runs only the license lookup ----------------------------------------------


def run_to_answer(modules, chooser=None):
    case = make(modules)
    run_case(case, chooser or PolicyChooser(), approve)
    assert case.waiting_for_answer
    return case


def test_the_answer_re_runs_only_the_license_lookup():
    spy = Spy(license=CLAIM, trec_numbers={"900123": licensed()})
    case = run_to_answer(spy)
    before = list(spy.calls)
    case.answer(SECRET_ANSWER)
    assert spy.calls[len(before) :] == ["license_by_number"]
    assert case.evidence.license.status is LicenseStatus.LICENSED


def test_the_static_map_decides_what_runs_again(monkeypatch):
    spy = Spy(license=CLAIM, trec_numbers={"900123": licensed()})
    case = run_to_answer(spy)
    before = len(spy.calls)
    monkeypatch.setitem(planner.UNLOCKS, "license_number", ["license", "owner", "record"])
    case.answer(SECRET_ANSWER)
    assert {"owner", "price"} <= set(spy.calls[before:])  # a wider map would show here


def test_the_map_is_exactly_the_license_check():
    assert planner.UNLOCKS == {"license_number": ["license"]}


def test_no_answer_text_reaches_the_model():
    model = Model(ask_first)
    spy = Spy(license=CLAIM, trec_numbers={"900123": licensed()})
    case = make(spy)
    run_case(case, model, approve)
    assert case.waiting_for_answer
    case.answer(SECRET_ANSWER)
    run_case(case, model, approve)
    assert model.seen
    shown = json.dumps(
        [
            {
                "kind": o.kind.value,
                "options": o.options,
                "aliases": o.aliases,
                "facts": dict(o.facts),
            }
            for o in model.seen
        ]
    )
    for leak in ("0900123", "900123", "thanks", "here it is", "TREC #"):
        assert leak not in shown
    # the model learns the yes/no fact and nothing else about the answer
    assert any(o.facts.get("license_number_given") is True for o in model.seen)
    # nor is it in the trace, which a model may read through the case
    assert "900123" not in json.dumps([e.reason for e in case.trace.events])


def test_the_answer_is_not_kept_on_the_session():
    case = run_to_answer(Spy(license=CLAIM, trec_numbers={"900123": licensed()}))
    case.answer(SECRET_ANSWER)
    assert "900123" not in repr(vars(case)) and "thanks" not in repr(vars(case))
    assert "900123" not in repr(vars(case._plan))


@pytest.mark.parametrize(
    "text, number",
    [
        ("0123456", "123456"),
        (" 0900123 ", "900123"),
        ("TREC # 9001234", "9001234"),
        ("lic 123 456", None),  # split digits are not a number we trust
        ("12345", None),
        ("123456789", None),
        ("000000", None),
        ("٠١٢٣٤٥٦", None),  # non-ASCII digits are not digits here
        ("", None),
        (None, None),
        ("I don't have one", None),
    ],
)
def test_the_number_is_read_by_code_from_ascii_digits(text, number):
    assert extract_license_number(text) == number


# --- no answer, or no number: nothing changes ------------------------------------------------


def final(modules, answer, chooser):
    case = make(modules)
    run_case(case, chooser, approve)
    if case.waiting_for_answer:
        case.answer(answer)
        run_case(case, chooser, approve)
    return case


@pytest.mark.parametrize("answer", [None, "", "I don't have it", "call them yourself"])
def test_no_number_leaves_not_checked_and_the_verdict_unchanged(answer):
    asking_off = make(FixtureModules(license=CLAIM), ask_enabled=False)
    run_case(asking_off, PolicyChooser(), approve)
    assert asking_off.verdict is not None

    for chooser in (PolicyChooser(), Model(ask_first)):
        case = final(FixtureModules(license=CLAIM), answer, chooser)
        assert case.verdict == asking_off.verdict  # the same verdict as with no question at all
        assert case.evidence.license == CLAIM
        assert case.evidence.license.status is LicenseStatus.NOT_CHECKED
        card = build_card(case.evidence)
        lines = [line.text for row in card.rows for line in row.lines if line.label == "License"]
        assert lines == [strings.text("license.not_checked_claimed")]


def test_the_verdict_is_identical_with_the_model_on_and_off_when_a_number_is_given():
    modules = lambda: FixtureModules(license=CLAIM, trec_numbers={"900123": licensed()})  # noqa: E731
    policy = final(modules(), SECRET_ANSWER, PolicyChooser())
    model = final(modules(), SECRET_ANSWER, Model(ask_first))
    assert model.verdict == policy.verdict
    assert model.evidence == policy.evidence


def test_the_yes_no_fact_follows_whether_the_answer_held_a_number():
    for answer, given in ((SECRET_ANSWER, True), ("no idea", False), (None, False)):
        case = run_to_answer(FixtureModules(license=CLAIM, trec_numbers={"900123": licensed()}))
        assert case._plan.facts()["license_number_given"] is False  # before any answer
        case.answer(answer)
        assert case._plan.facts()["license_number_given"] is given


def test_a_case_that_is_never_answered_just_waits():
    case = run_to_answer(FixtureModules(license=CLAIM))
    assert case.verdict is None and not case.done
    with pytest.raises(RuntimeError):
        case.approve("send")
    case.answer("not now")
    assert case.waiting_for_answer is False


def test_answering_when_nothing_was_asked_is_refused():
    case = make(FixtureModules(license=CLAIM))
    with pytest.raises(RuntimeError):
        case.answer("0900123")


# --- a number the state cannot find: Doesn't match and HOLD, never DON'T PAY ------------------


def test_a_number_with_no_row_gives_the_doesnt_match_line_and_hold_never_dont_pay():
    modules = FixtureModules(license=CLAIM)  # the stand-in list holds no 0000042
    case = final(modules, "my license is 0000042 ok? 4242424", PolicyChooser())
    assert case.evidence.license.status is LicenseStatus.NOT_FOUND
    assert case.verdict.state is VerdictState.HOLD
    card = build_card(case.evidence)
    [row] = [r for r in card.rows if any(line.label == "License" for line in r.lines)]
    [line] = [line for line in row.lines if line.label == "License"]
    assert line.text == strings.text("license.not_found")
    assert line.tone.value == "red_flag"
    assert case.verdict.state is not VerdictState.DONT_PAY


def test_a_found_number_reads_as_licensed_and_does_not_lift_the_verdict():
    base = final(FixtureModules(license=CLAIM), None, PolicyChooser())
    case = final(
        FixtureModules(license=CLAIM, trec_numbers={"900123": licensed()}),
        SECRET_ANSWER,
        PolicyChooser(),
    )
    assert case.evidence.license.status is LicenseStatus.LICENSED
    assert case.verdict.state is base.verdict.state  # a license is supporting, never proof


# --- who chose the ask: model only among 2+ options, policy otherwise ------------------------


def choice_events(case, option):
    return [e for e in case.trace.events if e.choice is ChoiceKind.NEXT_CHECK and e.pick == option]


def test_the_ask_is_stamped_model_when_the_model_chose_it_among_several_options():
    case = make(FixtureModules(license=CLAIM))
    run_case(case, Model(ask_first), approve)
    [event] = choice_events(case, ASK)
    assert len(event.options) >= 2 and event.chosen_by == "model"


def test_the_ask_is_stamped_policy_when_it_was_the_only_option_open():
    case2 = make(FixtureModules(license=CLAIM))
    run_case(case2, PolicyChooser(), approve)
    [event] = choice_events(case2, ASK)
    assert list(event.options) == [ASK]
    assert event.chosen_by == "policy"
    assert event.reason == strings.text("plan.only_option")


def test_the_trace_lines_come_from_strings_in_both_languages():
    demo = run_ask_demo(lang="es")
    said = {e.reason for e in demo.trace}
    assert strings.text("plan.ask.question", "es") in said
    assert strings.text("plan.ask.looked_up", "es") in said
    assert demo.question == strings.text("plan.ask.question", "es")


# --- the staged case --------------------------------------------------------------------------


def test_the_staged_case_goes_from_ask_for_it_to_the_looked_up_result():
    demo = run_ask_demo()

    def license_line(card):
        return [line for row in card.rows for line in row.lines if line.label == "License"]

    [before] = license_line(demo.before)
    [after] = license_line(demo.after)
    assert before.text == strings.text("license.not_checked_claimed")
    assert after.text == strings.text("license.licensed_sponsored", broker="Fixture Realty Group")
    assert demo.question == strings.text("plan.ask.question")
    assert demo.verdict.state is VerdictState.HOLD


def test_the_staged_case_is_synthetic_and_keeps_no_number_in_its_trace():
    ids = ask_modules().evidence.case_id
    assert ids.startswith("fx-")
    demo = run_ask_demo()
    assert "900123" not in json.dumps([e.reason for e in demo.trace])
    assert "0900123" in staged_answer()


def test_the_demo_case_has_no_real_names_or_phones():
    from snapback.agent.demo_ask import ASK_DIR

    for path in ASK_DIR.iterdir():
        for phone in re.findall(r"\b\d{3}-\d{3}-\d{4}\b", path.read_text()):
            assert phone.startswith("555-010-01")


# --- over the API ----------------------------------------------------------------------------


class StateList:
    """Stands in for lane D's lookups: no number in the text is a claim; a number is looked up."""

    def __init__(self):
        self.asked: list[str] = []

    def record(self, property_id):
        return None

    def for_sale(self, listing_text):
        return None

    def license(self, listing_text):
        self.asked.append(listing_text)
        if "TREC license 900123" in listing_text:
            return LicenseResult(
                status=LicenseStatus.LICENSED, claimed_role="agent", number_in_ad=True
            )
        return LicenseResult(status=LicenseStatus.NOT_CHECKED, claimed_role="agent")


def api(tmp_path, ask: bool):
    from fastapi.testclient import TestClient

    from snapback.api.main import create_app
    from snapback.settings import Settings

    settings = Settings(_env_file=None, snapback_data_dir=tmp_path, snapback_ask_renter=ask)
    lookups = StateList()
    return TestClient(create_app(settings, lookups)), lookups


def start(client):
    made = client.post("/cases", data={"text": "2 bed, $1,000. I'm a licensed agent."}).json()
    auth = {"Authorization": f"Bearer {made['token']}"}
    if made["status"] == "waiting_for_approval":
        client.post(
            f"/cases/{made['case_id']}/challenge/approve", json={"decision": "send"}, headers=auth
        )
    return made["case_id"], auth


def test_over_the_api_the_case_waits_for_the_answer_and_carries_on(tmp_path):
    client, lookups = api(tmp_path, ask=True)
    case_id, auth = start(client)
    status = client.get(f"/cases/{case_id}", headers=auth).json()
    assert status["status"] == "waiting_for_answer"
    assert status["question"] == strings.text("plan.ask.question")
    wrong = client.post(f"/cases/{case_id}/answer", json={"text": "x" * 501}, headers=auth)
    assert wrong.status_code == 422
    assert client.post(f"/cases/{case_id}/answer", json={"text": "1"}).status_code in (401, 403)
    done = client.post(f"/cases/{case_id}/answer", json={"text": "TREC 0900123"}, headers=auth)
    assert done.status_code == 200 and done.json()["question"] is None
    if done.json()["status"] == "waiting_for_approval":  # the challenge comes after the ask
        client.post(f"/cases/{case_id}/challenge/approve", json={"decision": "send"}, headers=auth)
    assert client.get(f"/cases/{case_id}", headers=auth).json()["status"] == "done"
    card = client.get(f"/cases/{case_id}/card").json()
    said = {line["label"]: line["text"] for row in card["rows"] for line in row["lines"]}
    assert said["License"] == strings.text("license.licensed")
    again = client.post(f"/cases/{case_id}/answer", json={"text": "1"}, headers=auth)
    assert again.status_code == 409


def test_over_the_api_a_case_does_not_ask_unless_the_setting_is_on(tmp_path):
    client, _ = api(tmp_path, ask=False)
    case_id, auth = start(client)
    assert client.get(f"/cases/{case_id}", headers=auth).json()["status"] == "done"
    assert (
        client.post(f"/cases/{case_id}/answer", json={"text": "1"}, headers=auth).status_code == 409
    )
