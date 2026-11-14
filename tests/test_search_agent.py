"""The search agent: the model picks what to check and ask, code sets every result (judge 09:35)."""

import json

import pytest
from fastapi.testclient import TestClient

from snapback.agent.join import KitLookups
from snapback.agent.planner import SEARCH_FACT_KEYS, plan_search
from snapback.agent.search_agent import ModelSearchChooser, agentic_search
from snapback.api.main import create_app
from snapback.contracts import DataSource, RenterBrief
from snapback.preferences import MEMORY_FACT_KEYS
from snapback.settings import Settings
from test_search import Fake, building, plan


class Scripted:
    """A fake model: answers with the alias at `index` for every offer with 2+ options."""

    chosen_by = "model"

    def __init__(self, index=1):
        self.index = index
        self.seen = []

    def choose(self, offer):
        self.seen.append(offer)
        return offer.aliases[min(self.index, len(offer.aliases) - 1)], "I would look at these."


@pytest.fixture
def kit():
    return KitLookups(DataSource.FIXTURE)


def make_client(tmp_path, chooser=None):
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    return TestClient(
        create_app(settings, lookups=KitLookups(DataSource.FIXTURE), search_chooser=chooser)
    )


def new_case(client):
    made = client.post("/cases", data={"text": "Nice 1 bed, $1,500 a month, pets ok"})
    assert made.status_code == 201
    return made.json()


def six_buildings():
    # the last three have a 3D scan, so "the 3 with a scan" differs from "the first 3"
    return Fake(
        [
            building(
                f"fx-{i}",
                [plan(lo=1000 + 90 * i, hi=1100 + 90 * i)],
                model_ids=["m"] if i >= 3 else [],
            )
            for i in range(6)
        ]
    )


def test_search_reports_decisions_with_stamps_and_reasons(tmp_path):
    client = make_client(tmp_path, Scripted(1))
    body = client.post("/search", json={"max_rent_month": 2500}).json()
    kinds = [d["kind"] for d in body["decisions"]]
    assert kinds[0] == "deep_check" and "tradeoff" in kinds and kinds[-1] == "tour_gate"
    deep = body["decisions"][0]
    assert deep["chosen_by"] == "model" and deep["reason"] and deep["pick"] in deep["options"]
    for d in body["decisions"]:
        assert d["chosen_by"] == ("policy" if len(d["options"]) == 1 else "model")
        assert d["reason"]


def test_default_chooser_is_the_policy_and_checks_at_most_three(tmp_path):
    body = make_client(tmp_path).post("/search", json={"max_rent_month": 2500}).json()
    assert {d["chosen_by"] for d in body["decisions"]} == {"policy"}
    checked = [m for m in body["matches"] if m["checked"]]
    assert 1 <= len(checked) <= 3
    assert all(m["check_line"].startswith("Checked:") for m in checked)
    assert all(m["check_line"] is None for m in body["matches"] if not m["checked"])


def test_model_on_and_off_may_check_different_places_but_each_place_reads_the_same(kit):
    brief = RenterBrief(max_rent_month=2500, max_results=6)
    off = agentic_search(brief, six_buildings(), plan_policy())
    on = agentic_search(brief, six_buildings(), Scripted(1))
    off_set = {m.property_id for m in off.matches if m.checked}
    on_set = {m.property_id for m in on.matches if m.checked}
    assert off_set != on_set  # the model chose a different set
    by_off = {m.property_id: m for m in off.matches}
    for m in on.matches:
        if m.checked and by_off[m.property_id].checked:
            assert m.check_line == by_off[m.property_id].check_line
    # the same place deep-checked under a different chooser is identical, field for field
    both = off_set & on_set
    for pid in both:
        assert by_off[pid] == next(m for m in on.matches if m.property_id == pid)


def plan_policy():
    from snapback.agent.runner import PolicyChooser

    return PolicyChooser()


def test_one_option_menus_never_reach_the_model_and_are_stamped_policy():
    chooser = Scripted(1)
    one = Fake([building("fx-1", [plan()])])
    response = agentic_search(RenterBrief(), one, chooser)
    assert chooser.seen == []
    assert [d.chosen_by for d in response.decisions] == ["policy"] * len(response.decisions)
    assert response.question is None


def test_the_model_sees_only_allowlisted_facts_and_option_text_never_ids_or_offices():
    chooser = Scripted(0)
    kit_ = six_buildings()
    agentic_search(RenterBrief(max_rent_month=2500, max_results=6), kit_, chooser)
    assert chooser.seen
    for offer in chooser.seen:
        assert set(offer.facts) <= SEARCH_FACT_KEYS[offer.kind] | MEMORY_FACT_KEYS
        assert all(isinstance(v, (bool, int)) for v in offer.facts.values())
        text = json.dumps([offer.options, offer.aliases, offer.facts])
        assert "fx-" not in text and "Fixture Office Co" not in text
        assert offer.payload == {}  # the code-side payload never goes along


def test_a_scripted_model_chooser_parses_json_and_off_list_falls_back_to_policy():
    class Reply:
        def __init__(self, content):
            self.content = content

    class Model:
        def __init__(self, content):
            self.content = content
            self.sent = None

        def invoke(self, messages):
            self.sent = messages
            return Reply(self.content)

    good = Model('Sure: {"option": "option B", "reason": "Cheaper places first."}')
    out = agentic_search(
        RenterBrief(max_rent_month=2500, max_results=6), six_buildings(), ModelSearchChooser(good)
    )
    assert (
        out.decisions[0].chosen_by == "model" and out.decisions[0].reason == "Cheaper places first."
    )
    assert "fx-" not in json.dumps(good.sent)
    bad = Model("not json at all")
    out = agentic_search(
        RenterBrief(max_rent_month=2500, max_results=6), six_buildings(), ModelSearchChooser(bad)
    )
    assert {d.chosen_by for d in out.decisions} == {"policy"}


def test_the_search_never_gives_a_verdict(monkeypatch, tmp_path):
    import snapback.verdict as verdict

    def boom(*a, **k):
        raise AssertionError("decide() must not run during a search")

    monkeypatch.setattr(verdict, "decide", boom)
    client = make_client(tmp_path, Scripted(1))
    body = client.post("/search", json={"max_rent_month": 2500}).json()
    assert "state" not in body and all("state" not in m for m in body["matches"])


def test_a_house_is_checked_against_the_for_sale_records_and_an_apartment_by_its_office():
    from snapback.search import deep_check

    kit_ = six_buildings()
    apartment = agentic_search(RenterBrief(max_rent_month=2500), kit_, plan_policy()).matches[0]
    line = deep_check(apartment, kit_).check_line
    assert "Fixture Office Co" in line and "as of CoStar's last research" in line
    assert "apartment" in line
    unknown = deep_check(apartment.model_copy(update={"office_on_record": None}), kit_)
    assert unknown.checked is False and unknown.check_line is None


# --- agent memory -------------------------------------------------------------------------------


def test_preferences_need_the_write_token_and_a_recorded_case_cannot_be_written(tmp_path):
    client = make_client(tmp_path)
    case = new_case(client)
    url = f"/cases/{case['case_id']}/preferences"
    assert client.post(url, json={"no_walkup": True}).status_code == 401
    read = {"Authorization": f"Bearer {case['read_token']}"}
    assert client.post(url, json={"no_walkup": True}, headers=read).status_code == 403
    write = {"Authorization": f"Bearer {case['token']}"}
    ok = client.post(url, json={"no_walkup": True, "max_rent": 1900}, headers=write)
    assert (
        ok.status_code == 200 and ok.json()["no_walkup"] is True and ok.json()["max_rent"] == 1900
    )
    assert client.post(url, json={"anything": "else"}, headers=write).status_code == 422
    assert client.post(url, json={"max_rent": 2500}, headers=write).json()["max_rent"] == 1900


def test_a_rejected_walkup_never_comes_back_in_later_searches(tmp_path):
    client = make_client(tmp_path)
    case = new_case(client)
    read = {"Authorization": f"Bearer {case['read_token']}"}
    write = {"Authorization": f"Bearer {case['token']}"}
    before = client.post(f"/search?case_id={case['case_id']}", json={}, headers=read).json()
    assert before["remembered"] == []
    client.post(f"/cases/{case['case_id']}/preferences", json={"no_walkup": True}, headers=write)
    after = client.post(f"/search?case_id={case['case_id']}", json={}, headers=read).json()
    assert after["remembered"] == ["no_walkup"]
    assert after["n_matches"] <= before["n_matches"]
    for m in after["matches"]:
        walk = [line for line in m["must_haves"] if line["key"] == "walkup"]
        assert all(line["met"] is not False for line in walk)
        assert not any("Walk-up building" in line["text"] and line["met"] is None for line in walk)
    assert all(
        "walkup" not in d["pick"].lower() or "stairs" not in d["pick"] for d in after["decisions"]
    )
    assert after["question"] is None or "walk-up" not in after["question"]


def test_a_rejected_place_never_reappears_in_search_or_alternatives(tmp_path):
    client = make_client(tmp_path)
    case = new_case(client)
    read = {"Authorization": f"Bearer {case['read_token']}"}
    write = {"Authorization": f"Bearer {case['token']}"}
    first = client.post(f"/search?case_id={case['case_id']}", json={}, headers=read).json()
    gone = first["matches"][0]["property_id"]
    alt_before = client.get(f"/cases/{case['case_id']}/alternatives?n=10", headers=read).json()
    client.post(
        f"/cases/{case['case_id']}/preferences", json={"avoid_property_id": gone}, headers=write
    )
    again = client.post(f"/search?case_id={case['case_id']}", json={}, headers=read).json()
    assert gone not in {m["property_id"] for m in again["matches"]}
    alt = client.get(f"/cases/{case['case_id']}/alternatives?n=10", headers=read).json()
    assert gone not in {m["property_id"] for m in alt["matches"]}
    assert alt["remembered"] == ["avoid_property_id"] and alt_before["remembered"] == []


def test_the_model_sees_preference_keys_as_flags_and_counts_never_ids():
    from snapback.contracts import CasePreferences

    chooser = Scripted(0)
    prefs = CasePreferences(no_walkup=True, max_rent=2000, avoid_property_ids=["fx-3"])
    agentic_search(RenterBrief(max_results=6), six_buildings(), chooser, prefs)
    for offer in chooser.seen:
        assert offer.facts["remembers_no_walkup"] is True
        assert offer.facts["remembers_avoided"] == 1
        assert "fx-3" not in json.dumps(offer.facts) and "2000" not in json.dumps(offer.facts)


def test_search_with_a_case_id_needs_the_read_token_in_a_header_not_the_address(tmp_path):
    client = make_client(tmp_path)
    case = new_case(client)
    url = f"/search?case_id={case['case_id']}"
    assert client.post(url, json={}).status_code == 401
    assert client.post(f"{url}&token={case['read_token']}", json={}).status_code == 401
    assert client.post("/search?case_id=nope", json={}).status_code == 404


def test_the_search_rate_limit_is_unchanged(tmp_path):
    from snapback.api.main import SEARCH_PER_MINUTE

    client = make_client(tmp_path)
    codes = [client.post("/search", json={}).status_code for _ in range(SEARCH_PER_MINUTE + 1)]
    assert codes[:SEARCH_PER_MINUTE] == [200] * SEARCH_PER_MINUTE and codes[-1] == 429


def test_tour_gate_asks_first_only_with_a_question_and_a_checked_office():
    from snapback.agent.planner import ASK_FIRST, TradeOff

    matches = agentic_search(
        RenterBrief(max_rent_month=2500), six_buildings(), plan_policy()
    ).matches
    q = [TradeOff("walkup", "$140 a month less with a walk-up building. OK with stairs?", 140, 3)]
    asked = plan_search(matches, q, plan_policy())
    assert asked.ask_first is True and asked.steps[-1].pick == ASK_FIRST
    assert plan_search(matches, [], plan_policy()).ask_first is False


def test_a_house_line_is_set_by_the_for_sale_record_status():
    from snapback.contracts import ForSaleMatch, ForSaleStatus, PropertyRecord, RentalHouse
    from snapback.search import deep_check, search_places

    class Houses(Fake):
        status = ForSaleStatus.NONE

        def record(self, pid):
            return PropertyRecord(property_id=pid, source=DataSource.FIXTURE, lat=29.7, lon=-95.4)

        def for_sale_at(self, text, lat, lon):
            return ForSaleMatch(status=self.status, offices=["Sale Office Co"])

    house = RentalHouse(
        property_id="h-1", source=DataSource.FIXTURE, rent_min=1500, rent_max=1500,
        office="Rent Office Co",
    )  # fmt: skip
    kit_ = Houses(rentals=[house])
    (place,) = search_places(RenterBrief(), kit_)
    lines = {}
    for status in ForSaleStatus:
        kit_.status = status
        done = deep_check(place, kit_)
        assert done.checked
        lines[status] = done.check_line
    assert "not listed for sale" in lines[ForSaleStatus.NONE]
    assert "Rent Office Co" in lines[ForSaleStatus.NONE]
    assert "also listed for sale by Sale Office Co" in lines[ForSaleStatus.ACTIVE]
    assert "rented out recently" in lines[ForSaleStatus.RECENTLY_RENTED]
    assert all(line.endswith("as of CoStar's last research.") for line in lines.values())
