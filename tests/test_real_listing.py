"""The real listing: the ad's building as CoStar's record has it (proof plan 3.1 and 3.5)."""

import re

import pytest
from fastapi.testclient import TestClient

from snapback.api.main import create_app
from snapback.card import strings
from snapback.contracts import (
    AuthorityResult,
    AuthorityStatus,
    DataSource,
    FloorPlanRent,
    LocateResult,
    LocateStatus,
    ModuleEvidence,
    PhoneMatch,
    PhotoLocation,
    PriceResult,
    PriceStatus,
    PropertyRecord,
    RealListing,
    RuleCategory,
    RuleHit,
    UnitOnRecord,
)
from snapback.real_listing import real_listing, rent_percent_under
from snapback.settings import Settings

PHONE = re.compile(r"\d{3}[-. )]*\d{3}[-. ]*\d{4}")
STREET = re.compile(
    r"\b\d{1,5}\s+\w+(\s\w+)?\s(street|st|avenue|ave|road|rd|drive|dr|blvd|lane|ln|row)\b", re.I
)


def plan(beds, low, high, *, per_bed=False, units=2, url=None, name=None):
    return FloorPlanRent(
        name=name or f"{beds} bed",
        beds=beds,
        baths=1.0,
        rent_min=low,
        rent_max=high,
        per_bed=per_bed,
        units_available=units,
        availability_url=url,
    )


def record(pid="fx-prop-1", source=DataSource.FIXTURE, **fields):
    base = {
        "property_id": pid,
        "source": source,
        "building_name": "Fixture Court",
        "street_address": "1 Fixture Row, Houston TX",
        "manager_company": "Fixture Living LLC",
        "website_host": "fixtureliving.example",
        "site_phone_hash": "fx-hash",
        "floor_plan_rents": [
            plan(1, 1700, 1900, url="https://fixtureliving.example/avail/1"),
            plan(2, 2300, 2600),
            plan(2, 900, 900, per_bed=True),
        ],
    }
    return PropertyRecord(**(base | fields))


def photo(n, status, matched=None):
    return PhotoLocation(photo_id=f"p{n}", status=status, matched_property_id=matched)


def modules(photos=(), source=DataSource.FIXTURE, rent=1200, phone=PhoneMatch.NO, rules=()):
    return ModuleEvidence(
        case_id="fx-7Q2M",
        source=source,
        locate=LocateResult(case_id="fx-7Q2M", photos=list(photos), thresholds_version="fx-1")
        if photos
        else None,
        price=PriceResult(status=PriceStatus.BELOW_RANGE, listed_rent=rent),
        authority=AuthorityResult(status=AuthorityStatus.MISMATCH, office_phone_match=phone),
        rules=list(rules),
    )


def settings(**kw):
    return Settings(_env_file=None, **kw)


ZELLE = RuleHit(rule_id="payment.zelle", category=RuleCategory.PAYMENT_METHOD, red_flag=True)
IN = LocateStatus.LOCATED_IN_CLAIMED
ELSE = LocateStatus.LOCATED_ELSEWHERE


def test_the_claimed_building_is_shown_when_no_photo_is_elsewhere():
    got = real_listing(
        modules([photo(1, IN), photo(2, IN), photo(3, LocateStatus.NOT_LOCATED)]),
        record(),
        None,
        settings(),
        ad_beds=1,
    )
    assert got.which == "claimed" and got.property_id == "fx-prop-1"
    assert (got.photos_in_scan, got.photos_total) == (2, 3)
    assert "2 of 3 of the ad's photos are in CoStar's own scan of this building" in got.provenance


def test_the_matched_building_wins_over_the_claimed_one():
    other = record("fx-prop-3", manager_company="Other Mgmt Co", website_host="other.example")
    got = real_listing(
        modules([photo(1, ELSE, "fx-prop-3"), photo(2, ELSE, "fx-prop-3"), photo(3, IN)]),
        record(),
        other,
        settings(),
        ad_beds=1,
    )
    assert got.which == "matched" and got.property_id == "fx-prop-3"
    assert got.manager_company == "Other Mgmt Co" and got.website_host == "other.example"
    assert (got.photos_in_scan, got.photos_total) == (2, 3)
    assert "different building" in got.provenance


def test_a_claimed_record_missing_still_shows_the_matched_one_and_neither_gives_none():
    other = record("fx-prop-3")
    assert real_listing(modules(), None, other, settings()).which == "matched"
    assert real_listing(modules(), None, None, settings()) is None


def test_plans_are_narrowed_to_the_ads_beds_and_per_bed_plans_are_left_out():
    got = real_listing(modules(), record(), None, settings(), ad_beds=2)
    assert [(p.beds, p.rent_min, p.rent_max) for p in got.plans] == [(2, 2300, 2600)]
    both = real_listing(modules(), record(), None, settings(), ad_beds=None)
    assert sorted(p.beds for p in both.plans) == [1, 2]  # still no per-bed plan
    assert all(p.rent_min != 900 for p in both.plans)


def test_the_ads_unit_on_record_narrows_to_its_own_plan():
    rec = record(units=[UnitOnRecord(unit="4B", beds=1, floor_plan="1 bed")])
    got = real_listing(modules(), rec, None, settings(), ad_beds=2, ad_unit="4B")
    assert [p.beds for p in got.plans] == [1]


def test_a_fixture_case_always_shows_the_figures():
    got = real_listing(modules(), record(), None, settings(), ad_beds=1, lang="en")
    assert got.figures_shown is True
    assert (got.plans[0].rent_min, got.plans[0].rent_max) == (1700, 1900)
    assert got.plans[0].availability_host == "fixtureliving.example"
    assert got.cta_url == "https://fixtureliving.example/avail/1"
    assert "$1,700 to $1,900" in got.headline and "Fixture Living LLC" in got.headline
    assert "The ad asks $1,200 a month" in got.headline


def test_live_with_the_flag_off_hides_rents_units_and_the_name_but_keeps_the_link():
    live = record(source=DataSource.LIVE)
    got = real_listing(modules(source=DataSource.LIVE), live, None, settings(), ad_beds=1)
    assert got.figures_shown is False
    assert got.source is DataSource.LIVE
    assert all(
        (p.rent_min, p.rent_max, p.units_available, p.availability_host) == (None,) * 4
        for p in got.plans
    )
    assert got.building_name is None
    # The hand-off link and its label stay: only the rent figures sit behind the flag.
    assert got.cta_url == "https://fixtureliving.example/avail/1"
    assert got.cta_label == "See the real listing"
    # company and host still show
    assert got.manager_company == "Fixture Living LLC"
    assert got.website_host == "fixtureliving.example"
    assert "1,700" not in got.model_dump_json() and "1,900" not in got.model_dump_json()
    assert "not shown here" in got.headline


def test_live_with_the_flag_on_shows_the_figures():
    live = record(source=DataSource.LIVE)
    got = real_listing(
        modules(source=DataSource.LIVE),
        live,
        None,
        settings(snapback_show_record_figures=True),
        ad_beds=1,
    )
    assert got.figures_shown is True and got.plans[0].rent_min == 1700
    assert got.building_name == "Fixture Court"
    assert got.cta_url == "https://fixtureliving.example/avail/1"
    assert got.cta_label == "See the real listing"


def test_the_link_falls_back_to_the_availability_page_then_the_website_then_nothing():
    no_link = record(floor_plan_rents=[plan(1, 1700, 1900)])
    got = real_listing(modules(), no_link, None, settings(), ad_beds=1)
    assert got.cta_url == "https://fixtureliving.example"
    page = record(floor_plan_rents=[plan(1, 1700, 1900)], availability_url="https://x.example/a")
    assert real_listing(modules(), page, None, settings(), ad_beds=1).cta_url == (
        "https://x.example/a"
    )
    bare = record(floor_plan_rents=[plan(1, 1700, 1900)], website_host=None)
    got = real_listing(modules(), bare, None, settings(), ad_beds=1)
    assert got.cta_url is None and got.cta_label is None


def test_phone_is_yes_or_no_and_not_claimed_for_the_matched_building():
    yes = real_listing(modules(phone=PhoneMatch.YES), record(), None, settings())
    assert yes.phone_is_office is PhoneMatch.YES
    assert "is the office's on record" in yes.phone_line
    no = real_listing(modules(phone=PhoneMatch.NO), record(), None, settings())
    assert no.phone_is_office is PhoneMatch.NO
    assert "is not the office's on record" in no.phone_line
    elsewhere = modules([photo(1, ELSE, "fx-prop-3")], phone=PhoneMatch.NO)
    got = real_listing(elsewhere, record(), record("fx-prop-3"), settings())
    assert got.phone_is_office is PhoneMatch.NOT_CHECKED and got.phone_line is None


def test_an_irreversible_payment_ask_is_reported_from_the_rule_hits():
    asked = real_listing(modules(rules=[ZELLE]), record(), None, settings())
    assert asked.ad_asks_irreversible is True
    assert "cannot be taken back" in asked.headline
    soft = RuleHit(rule_id="pressure.urgent", category=RuleCategory.PRESSURE, red_flag=False)
    assert real_listing(modules(rules=[soft]), record(), None, settings()).ad_asks_irreversible is (
        False
    )


def test_spanish_words_and_deterministic_output():
    a = real_listing(modules([photo(1, IN)]), record(), None, settings(), ad_beds=1, lang="es")
    b = real_listing(modules([photo(1, IN)]), record(), None, settings(), ad_beds=1, lang="es")
    assert a == b
    assert "El anuncio pide" in a.headline and a.cta_label == "Ver el anuncio real"
    assert "escaneo" in a.provenance


@pytest.mark.parametrize("source", [DataSource.FIXTURE, DataSource.LIVE])
@pytest.mark.parametrize("flag", [False, True])
def test_no_phone_digits_or_street_address_in_the_json(source, flag):
    rec = record(source=source)
    got = real_listing(
        modules([photo(1, IN)], source=source, rules=[ZELLE]),
        rec,
        record("fx-prop-3", source=source),
        settings(snapback_show_record_figures=flag),
        ad_beds=1,
    )
    text = got.model_dump_json()
    assert not PHONE.search(text)
    assert not STREET.search(text)
    assert "Fixture Row" not in text and "fx-hash" not in text
    assert "street_address" not in text and "site_phone" not in text


# --- the route -----------------------------------------------------------------------------


class _Lookups:
    def __init__(self, records):
        self._records = records
        self.missing = False  # flip after the case exists: the kit "goes away"

    def record(self, property_id):
        if self.missing:
            from snapback.agent.join import KitMissing

            raise KitMissing()
        return self._records.get(property_id)

    def records(self):
        return self._records

    def for_sale(self, listing_text):
        return None


def _client(tmp_path, lookups, **kw):
    made = Settings(_env_file=None, snapback_data_dir=tmp_path, **kw)
    return TestClient(create_app(made, lookups=lookups))


def _case(client, property_id="fx-prop-1"):
    made = client.post(
        "/cases",
        data={"text": "Two bed. 2 bed, $1,200 a month. Zelle only.", "property_id": property_id},
    )
    assert made.status_code == 201
    return made.json()


def test_the_route_needs_a_header_token_and_is_never_cached(tmp_path):
    lookups = _Lookups({"fx-prop-1": record()})
    client = _client(tmp_path, lookups)
    case = _case(client)
    url = f"/cases/{case['case_id']}/real-listing"
    assert client.get(url).status_code == 401
    assert client.get(url, params={"token": case["read_token"]}).status_code == 401
    assert client.get(url, headers={"X-Case-Token": "fx-wrong"}).status_code == 403
    ok = client.get(url, headers={"Authorization": f"Bearer {case['read_token']}"})
    assert ok.status_code == 200
    assert ok.headers["cache-control"] == "no-store"
    body = RealListing.model_validate(ok.json())
    assert body.case_id == case["case_id"] and body.property_id == "fx-prop-1"
    assert not PHONE.search(ok.text) and "Fixture Row" not in ok.text


def test_the_route_answers_503_when_the_kit_is_missing(tmp_path):
    lookups = _Lookups({"fx-prop-1": record()})
    client = _client(tmp_path, lookups)
    case = _case(client)
    lookups.missing = True
    got = client.get(
        f"/cases/{case['case_id']}/real-listing", headers={"X-Case-Token": case["read_token"]}
    )
    assert got.status_code == 503


def test_the_route_answers_404_when_there_is_no_record_to_show(tmp_path):
    client = _client(tmp_path, _Lookups({}))
    made = client.post("/cases", data={"text": "Two bed near the park."}).json()
    got = client.get(
        f"/cases/{made['case_id']}/real-listing", headers={"X-Case-Token": made["read_token"]}
    )
    assert got.status_code == 404


def test_the_route_honours_the_language(tmp_path):
    client = _client(tmp_path, _Lookups({"fx-prop-1": record()}))
    case = _case(client)
    got = client.get(
        f"/cases/{case['case_id']}/real-listing",
        params={"lang": "es"},
        headers={"X-Case-Token": case["read_token"]},
    )
    assert got.status_code == 200 and "según la última investigación" in got.json()["as_of"]


def test_a_live_route_hides_the_figures_unless_the_flag_is_on(tmp_path):
    live = {"fx-prop-1": record(source=DataSource.LIVE)}
    for flag, shown in ((False, False), (True, True)):
        client = _client(
            tmp_path,
            _Lookups(live),
            snapback_data_source=DataSource.LIVE,
            snapback_show_record_figures=flag,
        )
        case = _case(client)
        got = client.get(
            f"/cases/{case['case_id']}/real-listing", headers={"X-Case-Token": case["read_token"]}
        )
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["source"] == "live" and body["figures_shown"] is shown
        # The hand-off link is not a record figure: it comes back with the switch on or off,
        # while the rents come back only with it on.
        assert body["cta_url"].startswith("https://fixtureliving.example")
        assert body["cta_label"] == "See the real listing"
        assert any(p["rent_min"] is not None for p in body["plans"]) is shown
        assert ("2,300" in got.text or "2300" in got.text) is shown


def test_a_per_bed_unit_plan_is_not_swapped_for_a_whole_unit_plan_of_the_same_beds():
    # The ad's unit sits in a per-bed plan: narrow first (as check_price does), then drop per-bed,
    # so nothing is compared rather than the whole-unit 2-bed band.
    rec = record(
        floor_plan_rents=[
            plan(2, 2300, 2600, name="Whole 2"),
            plan(2, 900, 900, per_bed=True, name="Student 2x2"),
        ],
        units=[UnitOnRecord(unit="3A", beds=2, floor_plan="Student 2x2")],
    )
    got = real_listing(modules(rent=800), rec, None, settings(), ad_beds=2, ad_unit="3A")
    assert got.plans == []
    assert "2,300" not in got.headline
    assert rent_percent_under(rec, 800, 2, "3A") is None


def test_live_with_the_flag_off_and_no_plans_does_not_say_figures_are_hidden():
    bare = record(source=DataSource.LIVE, floor_plan_rents=[])
    for lang, hidden in (("en", "not shown here"), ("es", "no se muestran")):
        got = real_listing(
            modules(source=DataSource.LIVE), bare, None, settings(), ad_beds=1, lang=lang
        )
        assert hidden not in got.headline
        assert strings.text("real.record_no_plan", lang) in got.headline
    per_bed = [plan(2, 900, 900, per_bed=True)]
    only_per_bed = record(source=DataSource.LIVE, floor_plan_rents=per_bed)
    got = real_listing(modules(source=DataSource.LIVE), only_per_bed, None, settings(), ad_beds=2)
    assert "not shown here" not in got.headline


def test_the_route_uses_the_building_the_scan_identified_when_the_form_named_none(tmp_path):
    client = _client(tmp_path, _Lookups({"fx-prop-1": record()}))
    made = client.post("/cases", data={"text": "Two bed. 2 bed, $1,200 a month. Zelle only."})
    made = made.json()
    case = client.app.state.store.get(made["case_id"])
    assert case.property_id is None
    ev = case.session.evidence
    ev.locate = LocateResult(
        case_id=ev.case_id,
        photos=[photo(1, IN), photo(2, IN)],
        thresholds_version="fx-1",
        claimed_property_id="fx-prop-1",
        identified_by_scan=True,
    )
    headers = {"X-Case-Token": made["read_token"]}
    panel = client.get(f"/cases/{made['case_id']}/real-listing", headers=headers)
    assert panel.status_code == 200, panel.text
    assert panel.json()["property_id"] == "fx-prop-1" and panel.json()["photos_in_scan"] == 2
    note = client.get(f"/cases/{made['case_id']}/copy-alert", headers=headers).json()
    assert note["why_not"] != "no_record" and note["property_id"] == "fx-prop-1"


def test_the_hand_off_link_shows_with_the_flag_off_and_no_rent_number_leaves_with_it():
    live = record(source=DataSource.LIVE)
    for flag in (False, True):
        got = real_listing(
            modules(source=DataSource.LIVE),
            live,
            None,
            settings(snapback_show_record_figures=flag),
            ad_beds=1,
        )
        assert got.cta_url == "https://fixtureliving.example/avail/1"
        assert got.cta_label == "See the real listing"
        dump = got.model_dump_json()
        assert ("1,700" in dump or "1700" in dump) is flag
        assert ("1,900" in dump or "1900" in dump) is flag


def test_with_the_flag_off_the_link_falls_back_to_the_website_and_es_has_its_label():
    live = record(source=DataSource.LIVE, floor_plan_rents=[plan(1, 1700, 1900)])
    got = real_listing(
        modules(source=DataSource.LIVE), live, None, settings(), ad_beds=1, lang="es"
    )
    assert got.cta_url == "https://fixtureliving.example"
    assert got.cta_label == "Ver el anuncio real"
