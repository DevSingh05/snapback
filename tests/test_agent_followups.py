"""The Planner's follow-ups (agent/followups.py): after code ran every check, the agent may pick
at most two more checks from a fixed menu, each for one gap on the card and with a reason. The
results are information lines naming their source; `decide()` and the card's state never move.

No network, no key: the menu's runners are stand-ins with recorded answers.
"""

import threading
import time

import pytest

from snapback.agent import CaseSession, FixtureModules, PolicyChooser, Trace, casework, run_case
from snapback.agent import followups as fu
from snapback.agent.timeline import build_timeline
from snapback.contracts import DataSource, PublicStatus, TraceKind
from snapback.verdict import build_card, decide, to_evidence


def _case(runners=None, case_id="fx-FU1") -> CaseSession:
    session = CaseSession(case_id, FixtureModules(), Trace(case_id, DataSource.FIXTURE))
    run_case(session, PolicyChooser())
    session.followup_runners = runners if runners is not None else _runners()
    return session


def _runners(**over):
    found = {
        "lens": lambda: fu.Outcome(PublicStatus.FOUND, DataSource.FIXTURE),
        "phrase_search": lambda: fu.Outcome(PublicStatus.FOUND, DataSource.FIXTURE, count=3),
    }
    found.update(over)
    return found


def _gap(case, key):
    return next(g.alias for g in fu.card_gaps(case) if g.key == key)


def _snapshot(case):
    card = build_card(case.evidence, checked_at=None)
    verdict = decide(to_evidence(case.evidence))
    return verdict, card.state, card.headline, card.summary, card.checks_out, card.does_not


# --- the menu and its limits --------------------------------------------------------------------


def test_the_menu_offers_only_attached_checks_that_cover_an_open_gap():
    case = _case(_runners(census=lambda: fu.Outcome(PublicStatus.FOUND, DataSource.LIVE)))
    offer = fu.desk_of(case).offer()
    # census covers only the address line, which this card does not have open
    assert set(offer["menu"]) == {"lens", "phrase_search"}
    assert offer["picks_left"] == fu.MAX_PICKS == 2
    here = _gap(case, "label.here_now")
    assert here in offer["menu"]["lens"]["for_gaps"]
    # the model sees the label and a status word only, never a line's own text
    assert all(":" in words and len(words) < 60 for words in offer["gaps"].values())


def test_at_most_two_picks_run_and_a_third_is_refused():
    calls = []
    runners = _runners(
        lens=lambda: calls.append("lens") or fu.Outcome(PublicStatus.NO_MATCH, DataSource.FIXTURE),
        phrase_search=lambda: (
            calls.append("phrase") or fu.Outcome(PublicStatus.FOUND, DataSource.FIXTURE, count=2)
        ),
        census=lambda: calls.append("census") or fu.Outcome(PublicStatus.FOUND, DataSource.LIVE),
    )
    case = _case(runners)
    desk = fu.desk_of(case)
    here, allowed = _gap(case, "label.here_now"), _gap(case, "label.allowed")
    assert "not found" in desk.choose("lens", here, "The photos are unconfirmed, search them.")
    assert "2 other posts" in desk.choose(
        "phrase_search", allowed, "The poster is not confirmed, look for the ad elsewhere."
    )
    third = desk.choose("lens", here, "Again.")
    assert third.startswith("Refused") and "budget" in third
    assert calls == ["lens", "phrase"]
    assert len(case.evidence.followups) == 2
    assert desk.offer()["menu"] == {}


def test_a_pick_off_the_menu_or_for_a_gap_it_cannot_cover_is_refused_and_costs_nothing():
    case = _case()
    desk = fu.desk_of(case)
    here = _gap(case, "label.here_now")
    lease = _gap(case, "not_checked.lease")
    assert desk.choose("zillow_scrape", here, "More data.").startswith("Refused")
    assert desk.choose("census", here, "Try it.").startswith("Refused")  # no runner attached
    assert desk.choose("lens", "G99", "No such gap.").startswith("Refused")
    assert desk.choose("lens", lease, "Photos say nothing of the lease.").startswith("Refused")
    assert desk.picks_left() == 2 and case.evidence.followups == []


@pytest.mark.parametrize("reason", ["", "   ", None, "This is a scam, check it."])
def test_a_pick_needs_a_plain_reason(reason):
    case = _case()
    desk = fu.desk_of(case)
    said = desk.choose("lens", _gap(case, "label.here_now"), reason)
    assert said.startswith("Refused") and "reason" in said
    assert desk.picks_left() == 2 and case.evidence.followups == []


# --- the verdict never moves


@pytest.mark.parametrize(
    "status", [PublicStatus.FOUND, PublicStatus.NO_MATCH, PublicStatus.NOT_CHECKED]
)
def test_follow_up_results_never_change_decide_or_the_card_state(status):
    case = _case(
        _runners(
            lens=lambda: fu.Outcome(status, DataSource.FIXTURE),
            phrase_search=lambda: fu.Outcome(status, DataSource.FIXTURE, count=9),
        )
    )
    before = _snapshot(case)
    desk = fu.desk_of(case)
    desk.choose("lens", _gap(case, "label.here_now"), "The photos are the open question.")
    desk.choose("phrase_search", _gap(case, "label.allowed"), "The poster is not confirmed.")
    assert len(case.evidence.followups) == 2
    assert _snapshot(case) == before
    # the evidence decide() reads is the same object field for field
    assert to_evidence(case.evidence) == to_evidence(
        case.evidence.model_copy(update={"followups": []})
    )


def test_results_land_on_the_card_as_info_lines_naming_their_source():
    case = _case()
    fu.desk_of(case).choose("lens", _gap(case, "label.here_now"), "The photos are unconfirmed.")
    card = build_card(case.evidence, checked_at=None)
    lines = [line for row in card.rows for line in row.lines if line.key == "label.followup"]
    assert len(lines) == 1
    assert lines[0].source_name == "Google Lens" and lines[0].tone.value == "not_checked"
    assert lines[0].text == "The ad's photos were found on a listing page"
    # a follow-up line is never itself a gap to follow up
    assert all(g.key != "label.followup" for g in fu.card_gaps(case))


def test_the_trace_and_timeline_show_the_pick_its_reason_and_the_result():
    case = _case()
    here = _gap(case, "label.here_now")
    fu.desk_of(case).choose("lens", here, "The photos are unconfirmed, search them.", by="model")
    choice = [e for e in case.trace.events if e.kind is TraceKind.CHOICE][-1]
    assert choice.reason.startswith(
        "Planner chose: Google Lens search of the ad's photos because Here now: Not checked."
    )
    assert choice.chosen_by == "model" and choice.pick == "lens"
    ran = case.trace.events[-1]
    assert ran.kind is TraceKind.TOOL and "(source: Google Lens)" in ran.reason
    steps = build_timeline(case.case_id, DataSource.FIXTURE, case.trace.events, case.evidence).steps
    pick = next(s for s in steps if s.kind == "followup" and s.label.startswith("Planner chose"))
    assert pick.label == (
        "Planner chose: Google Lens search of the ad's photos because Here now: Not checked"
    )
    assert pick.by == "agent" and pick.source_name == "Google Lens"
    assert any(s.label == "Follow-up check" and "Google Lens" in s.result for s in steps)
    assert "Google Lens" in case.notes[casework.FOLLOWUPS].text


# --- time limits


def test_a_check_past_its_limit_is_not_checked():
    release = threading.Event()

    def slow():
        release.wait(5)
        return fu.Outcome(PublicStatus.FOUND, DataSource.FIXTURE)

    case = _case(_runners(lens=slow))
    desk = fu.FollowUpDesk(case, check_timeout_s=0.05)
    started = time.monotonic()
    said = desk.choose("lens", _gap(case, "label.here_now"), "The photos are unconfirmed.")
    release.set()
    assert time.monotonic() - started < 1.0
    assert "not checked" in said
    assert case.evidence.followups[0].status is PublicStatus.NOT_CHECKED


def test_no_check_runs_once_the_agent_deadline_has_passed():
    ran = []
    case = _case(
        _runners(lens=lambda: ran.append(1) or fu.Outcome(PublicStatus.FOUND, DataSource.FIXTURE))
    )
    desk = fu.FollowUpDesk(case, deadline=time.monotonic() - 1)
    desk.choose("lens", _gap(case, "label.here_now"), "The photos are unconfirmed.")
    assert ran == [] and case.evidence.followups[0].status is PublicStatus.NOT_CHECKED


def test_a_check_that_breaks_is_not_checked():
    def broken():
        raise RuntimeError("no connection")

    case = _case(_runners(lens=broken))
    fu.desk_of(case).choose("lens", _gap(case, "label.here_now"), "The photos are unconfirmed.")
    assert case.evidence.followups[0].status is PublicStatus.NOT_CHECKED


# --- with no model: the recorded pick


def test_the_recorded_pick_is_the_same_every_time_and_labelled_fixture():
    runs = []
    for _ in range(3):
        case = _case()
        before = _snapshot(case)
        lines = fu.run_recorded(case)
        runs.append([(x.check, x.gap, x.reason, x.status, x.chosen_by) for x in lines])
        assert _snapshot(case) == before
        picks = [e for e in case.trace.events if e.kind is TraceKind.CHOICE and e.pick in fu.MENU]
        assert all("Recorded pick (FIXTURE)" in e.reason for e in picks)
        assert all(e.chosen_by == "policy" for e in picks)
    assert runs[0] == runs[1] == runs[2]
    assert [r[0] for r in runs[0]] == ["lens", "phrase_search"]
    assert all(r[4] == "fixture" for r in runs[0])


def test_the_recorded_pick_depends_on_the_ad():
    only_lens = _case({"lens": lambda: fu.Outcome(PublicStatus.FOUND, DataSource.FIXTURE)})
    nothing = _case({})
    assert fu.recorded_picks(only_lens) == [("lens", _gap(only_lens, "label.here_now"))]
    assert fu.recorded_picks(nothing) == []
    assert fu.run_recorded(nothing) == []


def test_fixture_lens_runs_only_on_a_recorded_answer():
    from snapback.settings import Settings

    s = Settings(_env_file=None)
    text = "Nice house https://images.example.test/ad/house-1.jpg"
    assert "lens" in fu.build_runners(text, DataSource.FIXTURE, s)
    assert fu.build_runners("Nice house https://x.example/p.jpg", DataSource.FIXTURE, s) == {}
    out = fu.build_runners(text, DataSource.FIXTURE, s)["lens"]()
    assert out.source is DataSource.FIXTURE and out.status in (
        PublicStatus.FOUND,
        PublicStatus.NO_MATCH,
    )


# --- the deep agent makes the pick (scripted model, no network) ----------------------------------


def test_the_advisory_agent_chooses_a_follow_up_and_the_trace_shows_plan_pick_run_and_note():
    pytest.importorskip("deepagents")
    import json

    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    from snapback.agent.graph import build_advisory_agent, run_advisory

    n = [0]

    def call(name, **args):
        n[0] += 1
        return AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": f"f{n[0]}", "type": "tool_call"}],
        )

    class Planner(BaseChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        @property
        def _llm_type(self):
            return "planner"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            done = {m.name: m for m in messages if isinstance(m, ToolMessage)}
            if "write_todos" not in done:
                todos = [{"content": "Choose follow-ups", "status": "in_progress"}]
                reply = call("write_todos", todos=todos)
            elif "followup_open_choice" not in done:
                reply = call("followup_open_choice")
            elif "followup_choose" not in done:
                offer = json.loads(done["followup_open_choice"].content)
                gap = offer["menu"]["lens"]["for_gaps"][0]
                reply = call(
                    "followup_choose",
                    check="lens",
                    gap=gap,
                    reason="No photo was placed, so search the web for the ad's photos.",
                )
            elif "write_file" not in done:
                path = casework.note_path(case.case_id, casework.FOLLOWUPS)
                reply = call(
                    "write_file", file_path=path, content="lens: " + done["followup_choose"].content
                )
            elif "next_step_open_choice" not in done:
                reply = call("next_step_open_choice")
            elif "next_step_choose" not in done:
                steps = json.loads(done["next_step_open_choice"].content)["steps"]
                step, info = next(iter(steps.items()))
                reply = call(
                    "next_step_choose",
                    step=step,
                    gap=info["for_gaps"][0],
                    reason="This gap is still open, so the renter should act on it next.",
                )
            else:
                reply = AIMessage(content="Done.")
            return ChatResult(generations=[ChatGeneration(message=reply)])

    case = _case()
    before = _snapshot(case)
    agent = build_advisory_agent(case, Planner(), subagent_model=Planner())
    assert run_advisory(case, agent, deadline_s=20) is True
    assert _snapshot(case) == before
    kinds = [e.kind for e in case.trace.events]
    assert TraceKind.TODO in kinds and TraceKind.FILE in kinds
    pick = next(e for e in case.trace.events if e.pick == "lens")
    assert pick.chosen_by == "model" and pick.reason.startswith("Planner chose: Google Lens")
    assert "No photo was placed" in pick.reason
    assert [f.check for f in case.evidence.followups] == ["lens"]
    assert case.notes[casework.FOLLOWUPS].by == "model"
    drafted = next(e for e in case.trace.events if e.pick in fu.NEXT_STEPS)
    assert drafted.chosen_by == "model" and drafted.reason.startswith("Planner drafted")


# --- the next step: drafted for the renter, never sent


def test_the_planner_drafts_one_next_step_for_a_gap_and_the_verdict_does_not_move():
    case = _case()
    before = _snapshot(case)
    offer = fu.next_step_offer(case)
    assert offer["steps"], offer
    assert "ask_licence" in offer["steps"]
    allowed = _gap(case, "label.allowed")
    said = fu.choose_next_step(case, "ask_licence", allowed, "The licence is not confirmed.")
    assert said.startswith("Drafted for the renter, not sent:")
    assert fu.choose_next_step(case, "tour_questions", "G1", "Again.").startswith("Refused")
    assert fu.next_step_offer(case)["steps"] == {}
    pick = [e for e in case.trace.events if e.pick == "ask_licence"][-1]
    assert pick.reason.startswith(
        "Planner drafted the next step: ask the poster for their Texas licence number because"
    )
    assert "Draft:" in case.notes[casework.NEXT_STEP].text
    assert _snapshot(case) == before
    steps = build_timeline(case.case_id, DataSource.FIXTURE, case.trace.events, case.evidence).steps
    assert any(s.label.startswith("Planner drafted: ask the poster") for s in steps)


def test_a_next_step_needs_a_reason_and_a_gap_it_covers():
    case = _case()
    here = _gap(case, "label.here_now")
    assert fu.choose_next_step(case, "ask_licence", here, "x").startswith("Refused")
    assert fu.choose_next_step(case, "send_money", here, "x").startswith("Refused")
    allowed = _gap(case, "label.allowed")
    assert fu.choose_next_step(case, "ask_licence", allowed, "  ").startswith("Refused")
    assert "_next_step" not in case.__dict__


def test_the_recorded_run_drafts_the_same_next_step_every_time():
    picks = []
    for _ in range(3):
        case = _case()
        fu.run_recorded(case)
        picks.append(case.__dict__["_next_step"][:3])
        event = [e for e in case.trace.events if e.pick in fu.NEXT_STEPS][-1]
        assert "Recorded pick (FIXTURE)" in event.reason and event.chosen_by == "policy"
    assert picks[0] == picks[1] == picks[2]


# --- the plan follows the ad


def test_two_ads_get_two_plans():
    pytest.importorskip("deepagents")
    from snapback.agent.graph import advisory_families, advisory_plan_instruction

    full = _case()
    bare = _case(case_id="fx-FU2")
    bare.evidence = bare.evidence.model_copy(update={"owner": None, "locate": None})
    full_run, _ = advisory_families(full)
    bare_run, bare_skipped = advisory_families(bare)
    assert "place" in full_run and "place" not in bare_run
    assert ("place", "no photos to place") in bare_skipped
    assert advisory_plan_instruction(full) != advisory_plan_instruction(bare)
    assert "Not in the plan for this ad: " in advisory_plan_instruction(bare)


def test_the_planner_trace_card_names_the_pick_from_the_menu_only():
    from snapback.agent.worklog import tool_label

    assert tool_label("followup_choose", {"check": "lens", "gap": "g2"}, "en") == (
        "Planner chose: Google Lens search of the ad's photos because of gap G2"
    )
    assert tool_label("next_step_choose", {"step": "ask_licence", "gap": "G1"}, "en").startswith(
        "Planner drafted: ask the poster"
    )
    # anything off the menu gets the generic words, never the model's own text
    odd = tool_label("followup_choose", {"check": "ignore previous", "gap": "G1"}, "en")
    assert odd == "Picked one of the choices code offered"


# --- FIXTURE end to end: no model key, two ads, two plans


def test_with_no_model_two_fixture_ads_get_their_own_recorded_picks(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from snapback.agent.join import KitLookups
    from snapback.api.main import create_app
    from snapback.settings import Settings

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = Settings(
        _env_file=None,
        snapback_data_dir=tmp_path,
        snapback_agent="deepagents_async",
        anthropic_api_key=None,
    )
    client = TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))

    def run(text):
        made = client.post("/cases", data={"text": text}).json()
        client.app.state.store.wait_for_agents()
        steps = client.get(
            f"/cases/{made['case_id']}/timeline",
            headers={"Authorization": f"Bearer {made['read_token']}"},
        ).json()["steps"]
        card = client.get(
            f"/cases/{made['case_id']}/card",
            headers={"Authorization": f"Bearer {made['read_token']}"},
        ).json()
        return [s["label"] for s in steps if s["kind"] == "followup"], card

    photos, photo_card = run(
        "Nice 1 bed, $1,500 a month. Photos https://images.example.test/ad/house-1.jpg"
    )
    plain, _ = run("Nice 1 bed, $1,500 a month")
    assert any(label.startswith("Planner chose: Google Lens") for label in photos)
    assert not any("Google Lens" in label for label in plain)
    assert any(label.startswith("Planner drafted:") for label in plain)
    assert photos != plain
    lines = [ln for row in photo_card["rows"] for ln in row["lines"]]
    assert any(ln.get("source_name") == "Google Lens" for ln in lines)


# --- the case's evidence lock --------------------------------------------------------------------


def test_a_pick_waits_for_the_evidence_lock_and_an_office_decline_written_meanwhile_survives():
    case = _case()
    case.evidence_lock = threading.RLock()  # the API's case lock (api/cases.py)
    here = _gap(case, "label.here_now")
    state_before = build_card(case.evidence, checked_at=None).state
    held, release = threading.Event(), threading.Event()

    def office_answers():
        with case.evidence_lock:
            held.set()
            release.wait(5)
            case.decline_office("example-office.test")

    office = threading.Thread(target=office_answers)
    office.start()
    held.wait(5)
    picker = threading.Thread(
        target=lambda: fu.desk_of(case).choose("lens", here, "The photos are unconfirmed.")
    )
    picker.start()
    picker.join(0.3)
    assert picker.is_alive()  # it waits for the lock before it writes
    assert case.evidence.followups == []
    release.set()
    office.join(5)
    picker.join(5)
    assert not picker.is_alive()
    assert case.evidence.office_declined_domain == "example-office.test"
    assert [f.check for f in case.evidence.followups] == ["lens"]
    after = build_card(case.evidence, checked_at=None)
    assert after.state == decide(to_evidence(case.evidence)).state
    assert after.state == state_before or after.state.value == "hold"


def test_two_next_step_picks_at_once_only_one_wins(monkeypatch):
    case = _case()
    case.evidence_lock = threading.RLock()
    allowed = _gap(case, "label.allowed")
    real_gaps = fu.card_gaps

    def slow_gaps(c):  # widen the window between the check and the set
        time.sleep(0.05)
        return real_gaps(c)

    monkeypatch.setattr(fu, "card_gaps", slow_gaps)
    start = threading.Barrier(8)
    said: list[str] = []

    def pick(step):
        start.wait(5)
        said.append(fu.choose_next_step(case, step, allowed, "The poster is not confirmed."))

    steps = ["ask_licence", "call_office", "ask_poster", "ask_licence"] * 2
    threads = [threading.Thread(target=pick, args=(s,)) for s in steps]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert sum(1 for s in said if s.startswith("Drafted")) == 1
    assert len([e for e in case.trace.events if e.pick in fu.NEXT_STEPS]) == 1
