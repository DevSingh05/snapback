"""A10 (#97): lane D's record and lookups feed the price, unit and contact rules.

Everything here is synthetic: lane D's invented kit in fixtures/adapters/costar-kit, and
invented records marked LIVE to exercise what a live run does.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.agent import CaseSession, FixtureModules, PolicyChooser, Trace, run_case
from snapback.agent.intake import read_listing
from snapback.agent.join import JoinedModules, KitLookups, KitMissing
from snapback.agent.rules.contact import FIXTURE_PHONE_SALT, phone_hash
from snapback.api.main import create_app
from snapback.contracts import (
    AuthorityStatus,
    CardRowKind,
    CardTone,
    DataSource,
    ForSaleMatch,
    LinkDomain,
    PhoneMatch,
    PriceStatus,
    PropertyRecord,
    UnitStatus,
    VerdictState,
)
from snapback.settings import Settings
from snapback.verdict import build_card

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")
OFFICE, OTHER = "(555) 010-0142", "555-010-0177"  # 555-01xx numbers are reserved for fiction
KIT_MANAGER = "Fixture Property Management Co"  # the manager of fx-prop-3 in lane D's kit


def contact_record(source: DataSource = DataSource.LIVE, **changes) -> PropertyRecord:
    """An invented record with the D7 fields, marked as if it were read from the real kit."""
    raw = json.loads((CONTRACTS / "property_record_contact.json").read_text())
    raw |= {"source": source.value, "site_phone_hash": phone_hash(OFFICE, FIXTURE_PHONE_SALT)}
    return PropertyRecord.model_validate(raw | changes)


class Injected:
    """Stand-in for lane D's adapters: one record by id, one for-sale answer."""

    def __init__(self, record: PropertyRecord | None = None, for_sale: ForSaleMatch | None = None):
        self._record, self._for_sale = record, for_sale
        self.asked: list[str] = []

    def record(self, property_id: str) -> PropertyRecord | None:
        self.asked.append(property_id)
        found = self._record
        return found if found is not None and found.property_id == property_id else None

    def for_sale(self, listing_text: str) -> ForSaleMatch | None:
        return self._for_sale


def joined(text: str, record=None, for_sale=None, source=None) -> JoinedModules:
    return JoinedModules(
        stand_in=FixtureModules(),
        listing=read_listing(text),
        record=record,
        for_sale=for_sale,
        salt=FIXTURE_PHONE_SALT,
        record_source=source,
    )


def run(modules: JoinedModules):
    case = CaseSession("fx-JOIN", modules, Trace("fx-JOIN", DataSource.FIXTURE))
    verdict = run_case(case, PolicyChooser(), lambda draft: "send")
    return verdict, build_card(case.evidence, checked_at=CHECKED_AT), case


def lines(card) -> dict:
    return {item.label: item for row in card.rows for item in row.lines}


# --- lane D's kit, read through lane D's parser --------------------------------------------


def test_a_record_is_found_by_our_id_through_lane_ds_adapter():
    lookups = KitLookups(DataSource.FIXTURE)
    record = lookups.record("fx-prop-3")
    assert record is not None and record.source is DataSource.FIXTURE
    assert record.manager_company == KIT_MANAGER and record.rent_min == 1400
    assert lookups.record("fx-no-such-building") is None


def test_the_kit_is_read_once_however_many_cases_ask(monkeypatch):
    from snapback.adapters import costar_jsonl

    calls = []
    real = costar_jsonl.load_records

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(costar_jsonl, "load_records", counting)
    lookups = KitLookups(DataSource.FIXTURE)
    for _ in range(5):
        lookups.record("fx-prop-3")
        lookups.record("fx-prop-1")
    assert len(calls) == 1


def test_a_missing_kit_is_a_clear_error_that_names_no_path(tmp_path):
    lookups = KitLookups(DataSource.LIVE, kit_dir=tmp_path / "nothing-here")
    with pytest.raises(KitMissing) as error:
        lookups.record("anything")
    assert str(tmp_path) not in str(error.value)
    assert "kit" in str(error.value).lower()


def test_a_for_sale_lookup_that_cannot_run_is_not_a_lookup():
    # Until lane D's lookup (D7, #95) is on main there is nothing to ask, and that must read
    # as "not looked up", never as "looked up and found nothing".
    found = KitLookups(DataSource.FIXTURE).for_sale("3 bedroom house at 12 Fixture Lane")
    assert found is None or isinstance(found, ForSaleMatch)


# --- the rules run on the record -----------------------------------------------------------


def test_rent_and_manager_are_compared_with_the_kit_record():
    record = KitLookups(DataSource.FIXTURE).record("fx-prop-3")
    text = "2 bed, $900 a month. Managed by Fixture Property Management."
    modules = joined(text, record, source=record.source)

    price, authority = modules.price("fx-1"), modules.authority("fx-1")
    assert price.status is PriceStatus.BELOW_RANGE  # 900 is under 75% of the record's 1,400
    assert authority.status is AuthorityStatus.MATCHES_RECORD
    assert authority.manager_on_record == KIT_MANAGER

    other = joined("2 bed, $1,900 a month. Managed by Sunrise Homes.", record)
    assert other.price("fx-1").status is PriceStatus.WITHIN_RANGE
    assert other.authority("fx-1").status is AuthorityStatus.MISMATCH


def test_phone_link_and_unit_are_compared_when_the_record_has_them():
    text = (
        "Unit 999, 2 bed, $900 a month. Managed by Fixture Living LLC. "
        f"Text me at {OTHER}. Apply at https://fixtureliving-apply.example/now"
    )
    modules = joined(text, contact_record())
    authority, price = modules.authority("fx-1"), modules.price("fx-1")
    assert authority.office_phone_match is PhoneMatch.NO
    assert authority.link_domain is LinkDomain.LOOKALIKE
    assert price.unit is UnitStatus.NOT_ON_RECORD
    assert (price.status, price.compared_beds) == (PriceStatus.BELOW_RANGE, 2)


def test_with_no_record_nothing_is_claimed():
    modules = joined("2 bed, $900 a month. Managed by Fixture Living LLC.")
    assert modules.price("fx-1").status is PriceStatus.NOT_CHECKED
    assert modules.price("fx-1").listed_rent == 900
    assert modules.authority("fx-1").status is AuthorityStatus.UNKNOWN
    assert modules.for_sale("fx-1") is None
    assert modules.record_source("fx-1") is None


def test_the_twin_and_the_challenge_still_come_from_the_stand_in():
    stand_in = FixtureModules()
    modules = JoinedModules(
        stand_in=stand_in,
        listing=read_listing("2 bed, $1,700 a month."),
        record=contact_record(),
        for_sale=None,
        salt=FIXTURE_PHONE_SALT,
        record_source=DataSource.LIVE,
    )
    assert modules.locate("fx-1") == stand_in.locate("fx-1")
    assert modules.spot_ranking("fx-1", None) == stand_in.spot_ranking("fx-1", None)
    assert modules.photo_count("fx-1") == stand_in.photo_count("fx-1")


def test_a_real_building_with_no_scan_is_never_given_placed_photos():
    # The stand-in twin would say "3 of 3 photos placed". For a record with no 3D model that
    # would be a claim about a real building that nothing checked.
    no_scan = contact_record(model_ids=[], floor_plans=[])
    verdict, card, _ = run(joined("2 bed, $1,700 a month.", no_scan, source=DataSource.LIVE))
    assert verdict.state is VerdictState.UNVERIFIED
    place = next(row for row in card.rows if row.kind is CardRowKind.PLACE)
    assert place.lines[0].tone is not CardTone.OK


# --- LIVE or FIXTURE, line by line ---------------------------------------------------------


def test_lines_from_a_real_record_say_so_and_the_card_as_a_whole_does_not():
    text = (
        "Unit 999, 2 bed, $900 a month. Managed by Fixture Living LLC. "
        f"Text me at {OTHER}. Apply at https://fixtureliving-apply.example/now"
    )
    for_sale = ForSaleMatch(status="active")
    modules = joined(text, contact_record(), for_sale, source=DataSource.LIVE)
    _, card, case = run(modules)

    assert case.evidence.record_source is DataSource.LIVE
    assert card.source is DataSource.FIXTURE  # the twin and the challenge are stand-ins
    said = lines(card)
    from_record = ("For sale", "Unit on record", "Allowed to rent it", "Contact on record", "Link")
    for label in (*from_record, "Rent vs record"):
        assert said[label].source is DataSource.LIVE, label
    for label in ("Real", "Here now", "Payment ask"):
        assert said[label].source is None, label


def test_in_a_fixture_run_no_line_needs_a_label_of_its_own():
    record = KitLookups(DataSource.FIXTURE).record("fx-prop-3")
    text = "2 bed, $900 a month. Managed by Fixture Property Management."
    _, card, _ = run(joined(text, record, source=DataSource.FIXTURE))
    assert card.source is DataSource.FIXTURE
    assert all(item.source is None for row in card.rows for item in row.lines)


def test_a_rent_line_that_checked_nothing_is_not_marked_as_from_the_record():
    bare = contact_record(rent_min=None, rent_median=None, rent_max=None, floor_plan_rents=[])
    _, card, _ = run(joined("2 bed, $900 a month.", bare, source=DataSource.LIVE))
    rent = lines(card)["Rent vs record"]
    assert rent.tone is CardTone.NOT_CHECKED and rent.source is None


def test_the_picture_marks_the_lines_that_came_from_the_record():
    from snapback.card.render import render_card_png

    text = "2 bed, $900 a month. Managed by Fixture Living LLC."
    _, live_card, _ = run(joined(text, contact_record(), source=DataSource.LIVE))
    _, plain_card, _ = run(joined(text, contact_record(DataSource.FIXTURE), source=None))
    assert render_card_png(live_card) != render_card_png(plain_card)


# --- through the API -----------------------------------------------------------------------


def client_for(tmp_path, lookups=None, **settings) -> TestClient:
    made = Settings(_env_file=None, snapback_data_dir=tmp_path, **settings)
    return TestClient(create_app(made, lookups=lookups))


def finish(client: TestClient, form: dict) -> dict:
    made = client.post("/cases", data=form)
    assert made.status_code == 201, made.text
    case = made.json()
    if case["status"] == "waiting_for_approval":
        approved = client.post(
            f"/cases/{case['case_id']}/challenge/approve",
            json={"decision": "send"},
            headers={"Authorization": f"Bearer {case['token']}"},
        )
        assert approved.status_code == 200
    return client.get(f"/cases/{case['case_id']}/card").json()


def test_a_check_with_a_property_id_runs_on_that_record(tmp_path):
    client = client_for(tmp_path)
    card = finish(
        client,
        {
            "text": "2 bed, $900 a month. Managed by Fixture Property Management.",
            "property_id": "fx-prop-3",
        },
    )
    said = {line["label"]: line for row in card["rows"] for line in row["lines"]}
    assert said["Rent vs record"]["tone"] == "hold"
    assert KIT_MANAGER in said["Allowed to rent it"]["text"]
    assert card["source"] == "fixture"


def test_a_check_with_no_property_id_has_no_record_to_compare_with(tmp_path):
    card = finish(client_for(tmp_path), {"text": "2 bed, $900 a month."})
    said = {line["label"]: line for row in card["rows"] for line in row["lines"]}
    assert said["Rent vs record"]["tone"] == "not_checked"


@pytest.mark.parametrize("bad", ["fx-no-such-building", "../../etc/passwd", "x" * 200, "a b"])
def test_an_id_we_do_not_have_or_cannot_be_one_is_refused(tmp_path, bad):
    client = client_for(tmp_path)
    response = client.post("/cases", data={"text": "2 bed.", "property_id": bad})
    assert response.status_code == 422
    assert bad not in response.text  # the answer does not repeat what was sent


def test_a_refused_id_costs_none_of_the_days_checks(tmp_path):
    client = client_for(tmp_path, snapback_daily_limit=1)
    assert client.post("/cases", data={"text": "x", "property_id": "fx-nope"}).status_code == 422
    assert client.post("/cases", data={"text": "2 bed."}).status_code == 201


def test_live_mode_starts_a_case_and_marks_only_the_record_lines_live(tmp_path):
    lookups = Injected(contact_record(), ForSaleMatch(status="active"))
    client = client_for(tmp_path, lookups, snapback_data_source="live")
    assert client.get("/healthz").json()["data_source"] == "live"
    card = finish(
        client,
        {
            "text": f"Unit 204, 2 bed, $1,700 a month. Call {OFFICE}.",
            "property_id": "fx-prop-2",
        },
    )
    assert lookups.asked == ["fx-prop-2"]
    assert card["source"] == "fixture"  # stand-ins are still in it
    said = {line["label"]: line for row in card["rows"] for line in row["lines"]}
    assert said["For sale"]["source"] == "live"
    assert said["Contact on record"]["source"] == "live"
    assert said["Rent vs record"]["source"] == "live"
    assert said["Real"]["source"] is None and said["Here now"]["source"] is None


def test_live_mode_without_the_kit_says_so_when_a_record_is_asked_for(tmp_path):
    missing = KitLookups(DataSource.LIVE, kit_dir=tmp_path / "no-kit")
    client = client_for(tmp_path, missing, snapback_data_source="live")
    response = client.post("/cases", data={"text": "2 bed.", "property_id": "any-id"})
    assert response.status_code == 503
    assert str(tmp_path) not in response.text
    # With no record asked for, there is nothing to read from the kit.
    assert client.post("/cases", data={"text": "2 bed."}).status_code == 201


def test_nothing_from_the_record_is_logged_or_traced(tmp_path, caplog):
    lookups = Injected(contact_record(manager_company="Quiet Manager Co"))
    client = client_for(tmp_path, lookups, snapback_data_source="live")
    with caplog.at_level(logging.DEBUG):
        made = client.post(
            "/cases", data={"text": "2 bed, $900 a month.", "property_id": "fx-prop-2"}
        ).json()
        events = client.app.state.store.get(made["case_id"]).events()
    logged = " ".join(record.getMessage() for record in caplog.records)
    traced = " ".join(event.model_dump_json() for event in events)
    for secret in ("Quiet Manager", "fixtureliving.example", "1600", "fx-prop-2"):
        assert secret not in logged and secret not in traced
