"""Your listing is being copied: the draft note for the leasing office (positioning idea 1)."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from snapback.contracts import CopyAlert, DataSource, LocateStatus, PhoneMatch
from snapback.copy_alert import copy_alert
from snapback.real_listing import rent_percent_under
from test_real_listing import (
    ELSE,
    IN,
    PHONE,
    STREET,
    ZELLE,
    _case,
    _client,
    _Lookups,
    modules,
    photo,
    plan,
    record,
    settings,
)


def alert(mods, claimed, matched=None, **kw):
    return copy_alert(mods, claimed, matched, settings(), case_id="7Q2M", **kw)


def test_it_fires_for_the_claimed_building_when_photos_sit_in_its_scan_and_the_phone_is_not_its():
    got = alert(modules([photo(1, IN), photo(2, IN), photo(3, IN)], phone=PhoneMatch.NO), record())
    assert got.fires is True and got.why_not is None
    assert got.which == "claimed" and got.manager_company == "Fixture Living LLC"
    assert (got.photos_in_scan, got.photos_total) == (3, 3)
    assert got.phone_is_office is PhoneMatch.NO
    assert "3 of its 3 photos sit in CoStar's own 3D scan of your building" in got.draft_body
    assert "The number in the ad is not the office's number on record." in got.draft_body
    assert got.draft_body.startswith("To the leasing office at Fixture Living LLC,")
    assert got.draft_subject == "An ad using photos of your building was checked"
    assert got.report_url == "/cases/7Q2M/report" and got.case_id == "7Q2M"


def test_it_does_not_fire_without_photos_in_the_scan():
    got = alert(modules([photo(1, LocateStatus.NOT_LOCATED)], phone=PhoneMatch.NO), record())
    assert got.fires is False and got.why_not == "no_photos_in_scan" and got.draft_body is None
    assert alert(modules(), record()).why_not == "no_photos_in_scan"  # no locate at all


def test_it_does_not_fire_when_the_phone_is_the_offices_or_unchecked():
    yes = alert(modules([photo(1, IN)], phone=PhoneMatch.YES), record())
    assert yes.fires is False and yes.why_not == "phone_is_office"
    unknown = alert(modules([photo(1, IN)], phone=PhoneMatch.NOT_CHECKED), record())
    assert unknown.fires is False and unknown.why_not == "phone_not_checked"


def test_it_fires_for_a_matched_building_and_says_nothing_about_the_phone():
    other = record("fx-prop-3", manager_company="Other Mgmt Co", website_host="other.example")
    got = alert(
        modules([photo(1, ELSE, "fx-prop-3"), photo(2, ELSE, "fx-prop-3")], phone=PhoneMatch.NO),
        record(),
        other,
    )
    assert got.fires is True and got.which == "matched" and got.property_id == "fx-prop-3"
    assert got.manager_company == "Other Mgmt Co"
    assert "though the ad names a different one" in got.draft_body
    assert "number" not in got.draft_body.lower()
    assert got.phone_is_office is PhoneMatch.NOT_CHECKED


def test_it_says_how_far_under_in_percent_and_never_gives_a_record_rent():
    got = alert(
        modules([photo(1, IN)], phone=PhoneMatch.NO, rent=1190),
        record(floor_plan_rents=[plan(1, 1700, 1900)]),
        ad_beds=1,
    )
    assert got.rent_percent_under == 30
    assert "Its asked rent is 30% under your listed plan." in got.draft_body
    assert "1,700" not in got.model_dump_json() and "1700" not in got.draft_body


def test_no_percent_when_the_rent_is_not_far_enough_under_or_the_plan_is_per_bed():
    near = alert(modules([photo(1, IN)], phone=PhoneMatch.NO, rent=1600), record(), ad_beds=1)
    assert near.rent_percent_under is None and "asked rent" not in near.draft_body
    per_bed = record(floor_plan_rents=[plan(2, 900, 900, per_bed=True)])
    assert rent_percent_under(per_bed, 300, 2, None) is None
    assert rent_percent_under(record(), None, 1, None) is None


def test_no_record_gives_a_quiet_no():
    got = alert(modules([photo(1, IN)], phone=PhoneMatch.NO), None, None)
    assert got.fires is False and got.why_not == "no_record"


def test_it_is_a_draft_that_never_sends_and_names_no_one():
    got = alert(modules([photo(1, IN)], phone=PhoneMatch.NO, rules=[ZELLE], rent=900), record())
    assert got.draft_only is True and got.sent is False
    text = got.model_dump_json()
    assert "Nothing has been sent" in got.draft_body
    assert not PHONE.search(text) and not STREET.search(text)
    assert "Fixture Row" not in text and "fx-hash" not in text
    low = text.lower()
    assert "scam" not in low and "fraud" not in low and "criminal" not in low
    # the payment ask is the renter's own thread: it never goes in a note to the office
    assert "zelle" not in low


def test_the_module_cannot_send_anything():
    source = Path(__import__("snapback.copy_alert", fromlist=["x"]).__file__).read_text()
    code = "\n".join(
        ln for ln in source.splitlines() if ln.strip().startswith(("import ", "from "))
    )
    for banned in ("smtplib", "email", "httpx", "requests", "socket", "urllib", "aiohttp"):
        assert banned not in code


def test_spanish_draft():
    got = copy_alert(
        modules([photo(1, IN)], phone=PhoneMatch.NO),
        record(),
        None,
        settings(),
        case_id="7Q2M",
        lang="es",
    )
    assert got.fires and got.draft_body.startswith("A la oficina de arrendamiento de")
    assert "No se ha enviado nada" in got.draft_body


# --- the route ---------------------------------------------------------------------------------


def test_the_route_needs_a_header_token_and_is_never_cached(tmp_path):
    client = _client(tmp_path, _Lookups({"fx-prop-1": record()}))
    case = _case(client)
    url = f"/cases/{case['case_id']}/copy-alert"
    assert client.get(url).status_code == 401
    assert client.get(url, params={"token": case["read_token"]}).status_code == 401
    assert client.get(url, headers={"X-Case-Token": "fx-wrong"}).status_code == 403
    ok = client.get(url, headers={"Authorization": f"Bearer {case['read_token']}"})
    assert ok.status_code == 200
    assert ok.headers["cache-control"] == "no-store"
    body = CopyAlert.model_validate(ok.json())
    assert body.case_id == case["case_id"] and body.sent is False and body.draft_only is True
    if body.fires:
        assert body.report_url == f"/cases/{case['case_id']}/report"
    assert not PHONE.search(ok.text) and "Fixture Row" not in ok.text


def test_the_route_answers_503_when_the_kit_is_missing(tmp_path):
    lookups = _Lookups({"fx-prop-1": record()})
    client: TestClient = _client(tmp_path, lookups)
    case = _case(client)
    lookups.missing = True
    got = client.get(
        f"/cases/{case['case_id']}/copy-alert", headers={"X-Case-Token": case["read_token"]}
    )
    assert got.status_code == 503


def test_the_route_does_not_fire_without_placed_photos(tmp_path):
    client = _client(tmp_path, _Lookups({"fx-prop-1": record()}))
    case = _case(client)
    got = client.get(
        f"/cases/{case['case_id']}/copy-alert", headers={"X-Case-Token": case["read_token"]}
    ).json()
    assert got["fires"] is False and got["why_not"] in ("no_photos_in_scan", "phone_not_checked")
    assert got["source"] in (DataSource.FIXTURE, "fixture")
    assert re.fullmatch(r"[A-Za-z0-9]+", got["case_id"])


def test_the_recorded_example_case_answers_both_routes(tmp_path):
    from snapback.agent.join import KitLookups
    from snapback.api.main import create_app
    from snapback.settings import Settings

    made = Settings(_env_file=None, snapback_data_dir=tmp_path)
    client = TestClient(create_app(made, lookups=KitLookups(DataSource.FIXTURE)))
    panel = client.get("/cases/7Q2M/real-listing")
    assert panel.status_code == 200 and panel.json()["photos_in_scan"] == 3
    assert panel.headers["cache-control"] == "no-store"
    note = client.get("/cases/7Q2M/copy-alert")
    assert note.status_code == 200 and note.json()["sent"] is False
    assert note.json()["photos_in_scan"] == 3 and note.json()["fires"] is False
