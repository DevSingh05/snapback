"""The roster: one card per agent, every sub-agent name and timeline kind on a card, GET /agents.

The roster is a view. It names who does what; it runs nothing and sets no result.
"""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.agent import casework, roster, timeline
from snapback.agent.join import KitLookups
from snapback.api.main import create_app
from snapback.contracts import DataSource
from snapback.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
WEB_COPY = ROOT / "apps" / "web" / "src" / "proofroom" / "roster.json"
# The report's checks (apps/web/src/case/answer.ts CHECK_ORDER); the page lights a desk per check.
ANSWER_TS = ROOT / "apps" / "web" / "src" / "case" / "answer.ts"


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(create_app(settings, lookups=KitLookups(DataSource.FIXTURE)))


def timeline_kinds() -> set[str]:
    """Every `kind` a timeline step can carry: the check kinds, the tool kinds, and each literal
    `kind="..."` in the module, so a kind added later without a card turns this file red."""
    source = Path(timeline.__file__).read_text(encoding="utf-8")
    literals = set(re.findall(r'kind="([a-z_-]+)"', source))
    return {*timeline._CHECK_KINDS.values(), *timeline._TOOL_KEYS, *literals}


def test_the_cards_the_brief_names_are_all_there() -> None:
    by_team: dict[str, list[str]] = {}
    for card in roster.cards():
        by_team.setdefault(card.team, []).append(card.id)
    assert by_team == {
        "planner": ["planner"],
        "scam_check": ["rules", "record", "phone_office", "owner_licence", "photo", "web"],
        "listing_help": ["finder", "tour_prep"],
        "decider": ["decider"],
    }


def test_every_sub_agent_name_has_a_card() -> None:
    for name in casework.AGENT_NAMES.values():
        assert roster.card_for(name) is not None, name


def test_every_timeline_kind_has_a_card() -> None:
    kinds = timeline_kinds()
    assert {"record", "rent", "phone", "locate", "claims", "report", "reply"} <= kinds
    for kind in kinds:
        assert roster.card_for(kind) is not None, kind


def test_every_report_check_has_a_card() -> None:
    block = re.search(r"CHECK_ORDER[^=]*=\s*\[(.*?)\]", ANSWER_TS.read_text(), re.S)
    assert block is not None
    checks = re.findall(r'"([a-z]+)"', block.group(1))
    assert len(checks) >= 6
    owners = {check: [c.id for c in roster.cards() if check in c.checks] for check in checks}
    assert all(len(ids) == 1 for ids in owners.values()), owners


def test_every_card_is_reachable_and_no_kind_sits_on_two_cards() -> None:
    known = {*casework.AGENT_NAMES.values(), *timeline_kinds()}
    seen: dict[str, str] = {}
    for card in roster.cards():
        for kind in card.kinds:
            assert kind not in seen, f"{kind} is on {seen.get(kind)} and {card.id}"
            seen[kind] = card.id
        if card.team == "planner":
            continue  # lit by the timeline's mode, plan and todos, not by a step kind
        assert card.kinds, f"{card.id} has no step that can light it"
        live = [k for k in card.kinds if k in known]
        # A card nothing on main can light yet must say when it becomes available.
        assert live or card.availability, card.id
        if card.availability is None:
            assert live == card.kinds, f"{card.id} lists a kind nothing emits"


def test_only_the_decider_sets_the_verdict_and_it_is_code() -> None:
    cards = roster.cards()
    decider = next(c for c in cards if c.team == "decider")
    assert decider.model == "code"
    assert "verdict" in decider.job
    assert next(c for c in cards if c.id == "rules").model == "code"
    for card in cards:
        assert card.job and card.role and card.doing and card.tools and card.never, card.id
    # The role sits under a small mark, about 98 px wide on a phone: both languages must fit.
    for lang in ("en", "es"):
        for card in roster.cards(lang):
            assert 0 < len(card.role) <= 18, (lang, card.role)


def models(by: dict) -> dict[str, str]:
    return {c.id: c.model for c in roster.cards("en", by)}


def test_with_the_policy_no_card_claims_a_model() -> None:
    assert set(models(roster.runners("policy")).values()) == {"code"}


def test_the_deep_agent_on_the_request_path_runs_sub_agents_on_the_planners_model() -> None:
    got = models(roster.runners("deepagents", "claude-sonnet-5-5", "claude-haiku-5-5"))
    assert got["planner"] == "Claude Sonnet"
    assert got["record"] == got["photo"] == got["finder"] == "Claude Sonnet"
    assert got["rules"] == got["decider"] == "code"


def test_the_background_agent_gives_sub_agents_the_small_model_and_follows_overrides() -> None:
    got = models(roster.runners("deepagents_async", "claude-sonnet-5-5", "claude-haiku-5-5"))
    assert (got["planner"], got["record"], got["rules"]) == (
        "Claude Sonnet",
        "Claude Haiku",
        "code",
    )
    swapped = models(roster.runners("deepagents_async", "claude-opus-5-5", "some-other-model"))
    assert (swapped["planner"], swapped["web"]) == ("Claude Opus", "some-other-model")
    # Left out, the models are the settings' own defaults, never a second hard-coded copy.
    assert models(roster.runners("deepagents_async")) == got


def test_the_web_agent_says_when_it_is_available() -> None:
    web = next(c for c in roster.cards() if c.id == "web")
    assert web.availability == "Available when the web checks are on"
    assert set(web.tools) == {"Bright Data", "Apify", "Browser Use"}


def test_spanish_keeps_ids_and_changes_the_words() -> None:
    en, es = roster.cards("en"), roster.cards("es")
    assert [c.id for c in en] == [c.id for c in es]
    assert [c.kinds for c in en] == [c.kinds for c in es]
    assert all(a.job != b.job for a, b in zip(en, es, strict=True))


def test_no_card_carries_a_dash_a_phone_or_a_rent() -> None:
    for lang in ("en", "es"):
        text = roster.roster(lang).model_dump_json()
        assert "—" not in text and "–" not in text
        assert not re.search(r"\d{3}\D{0,2}\d{3}\D?\d{4}", text)
        assert "$" not in text


def test_get_agents_is_public_and_static(client: TestClient) -> None:
    r = client.get("/agents")
    assert r.status_code == 200
    body = r.json()
    # The test server runs the policy: no model runs, so no card claims one.
    assert body == json.loads(roster.roster("en", roster.runners("policy")).model_dump_json())
    assert {a["model"] for a in body["agents"]} == {"code"}
    assert [t["id"] for t in body["teams"]] == ["planner", "scam_check", "listing_help", "decider"]
    assert client.get("/agents").json() == body


def test_get_agents_names_the_models_this_server_runs(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        snapback_data_dir=tmp_path,
        snapback_agent="deepagents_async",
        snapback_agent_model="claude-opus-5-5",
    )
    app = create_app(settings, lookups=KitLookups(DataSource.FIXTURE))
    by_id = {a["id"]: a["model"] for a in TestClient(app).get("/agents").json()["agents"]}
    assert by_id["planner"] == "Claude Opus"
    assert by_id["record"] == "Claude Haiku"
    assert by_id["decider"] == "code"


def test_get_agents_in_spanish(client: TestClient) -> None:
    body = client.get("/agents?lang=es").json()
    assert body["lang"] == "es"
    assert body["agents"][0]["name"] == "Planificador"
    assert client.get("/agents?lang=fr").status_code == 422


def test_a_real_case_only_uses_kinds_the_roster_knows(client: TestClient) -> None:
    made = client.post("/cases", data={"text": "2 bed apartment, send the deposit by Zelle"})
    assert made.status_code in (200, 201), made.text
    case = made.json()
    steps = client.get(
        f"/cases/{case['case_id']}/timeline",
        headers={"Authorization": f"Bearer {case['read_token']}"},
    ).json()["steps"]
    assert steps
    for step in steps:
        if step["kind"] is not None:
            assert roster.card_for(step["kind"]) is not None, step["kind"]


def test_the_web_apps_copy_is_the_roster() -> None:
    """The page works with no API (the static front end), from a copy written by
    `uv run python -m snapback.agent.roster`. It must be the roster, word for word."""
    assert json.loads(WEB_COPY.read_text(encoding="utf-8")) == roster.web_copy()
