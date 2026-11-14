"""A9 (#73): three staged demo cases that run end to end to a card. Synthetic stand-ins only."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.agent.demo import DEMO_DIR, demo_case_ids, load_demo_case, run_demo_case
from snapback.agent.rules.contact import FIXTURE_PHONE_SALT, phone_hash
from snapback.api.main import create_app
from snapback.card import strings
from snapback.contracts import (
    CardRowKind,
    CardTone,
    ModuleEvidence,
    PropertyRecord,
    VerdictState,
)
from snapback.settings import Settings

OFFICE = "(555) 010-0142"  # 555-01xx numbers are reserved for fiction
PLACEHOLDER = re.compile(r"\\\{\w{1,20}\\\}")


def lines(card, kind: CardRowKind) -> dict[str, tuple[CardTone, str]]:
    row = next(row for row in card.rows if row.kind is kind)
    return {item.label: (item.tone, item.text) for item in row.lines}


def from_the_string_table(text: str) -> bool:
    """Is `text` one of the string table's sentences, with its blanks filled in?"""
    for template in strings.TABLES["en"].values():
        pattern = PLACEHOLDER.sub(".{1,200}", re.escape(template))
        if re.fullmatch(pattern, text):
            return True
    return False


# --- the pack itself -----------------------------------------------------------------------


def test_there_are_three_cases_each_with_every_file():
    assert demo_case_ids() == ["a", "b", "c"]
    for case_id in demo_case_ids():
        folder = DEMO_DIR / case_id
        for name in ("case.json", "listing.txt", "module_evidence.json", "property_record.json"):
            assert (folder / name).is_file(), f"{case_id}/{name}"
        case = load_demo_case(case_id)
        assert case.case_id == case_id and case.title and case.listing_text.strip()


def test_everything_in_the_pack_is_marked_synthetic():
    for case_id in demo_case_ids():
        folder = DEMO_DIR / case_id
        evidence = ModuleEvidence.model_validate_json((folder / "module_evidence.json").read_text())
        record = PropertyRecord.model_validate_json((folder / "property_record.json").read_text())
        assert evidence.case_id.startswith("fx-") and evidence.source == "fixture"
        assert record.property_id.startswith("fx-") and record.source == "fixture"
        assert (record.lat, record.lon) == (0.0, 0.0)  # no real place
        for host in (record.website_host,):
            assert host is None or host.endswith(".example")
        for phone in re.findall(r"\d{3}-\d{3}-\d{4}", (folder / "listing.txt").read_text()):
            assert phone.startswith("555-010-01"), phone


def test_the_readme_says_what_is_staged_and_what_is_real():
    readme = (DEMO_DIR / "README.md").read_text()
    assert "staged poster, real CoStar records" in readme
    assert "synthetic" in readme.lower()


def test_the_office_phone_is_kept_only_as_a_hash():
    record = PropertyRecord.model_validate_json(
        (DEMO_DIR / "a" / "property_record.json").read_text()
    )
    assert record.site_phone_hash == phone_hash(OFFICE, FIXTURE_PHONE_SALT)
    for case_id in demo_case_ids():
        for path in (DEMO_DIR / case_id).iterdir():
            assert "0142" not in path.read_text(), path  # the office's digits are in no file


# --- (a) everything about the poster is off, and the reply is a copied photo ----------------


def test_case_a_is_dont_pay_on_the_copied_reply_and_shows_every_other_finding():
    verdict, card = run_demo_case("a")
    assert verdict.state is VerdictState.DONT_PAY
    assert verdict.reasons == [strings.text("reason.forged_copy", n=2)]

    place, person, price = (lines(card, kind) for kind in CardRowKind)
    assert place["Real"][0] is CardTone.OK  # the photos are of the real building
    assert place["Unit on record"][0] is CardTone.HOLD
    assert person["Here now"] == (
        CardTone.RED_FLAG,
        strings.text("here_now.forged_copy", n=2),
    )
    assert person["Allowed to rent it"][0] is CardTone.NOT_SHOWN
    assert person["Contact on record"][0] is CardTone.HOLD
    assert person["Link"][0] is CardTone.RED_FLAG
    assert price["Rent vs record"] == (
        CardTone.HOLD,
        "44% under this building's lowest 2 bed on record. Ask why; discounts happen.",
    )


# --- (b) the same listing, one photo from another building ---------------------------------


def test_case_b_is_dont_pay_because_a_photo_was_taken_elsewhere():
    verdict, card = run_demo_case("b")
    assert verdict.state is VerdictState.DONT_PAY
    assert verdict.reasons == [strings.text("reason.photo_elsewhere")]
    place = lines(card, CardRowKind.PLACE)
    assert place["Real"] == (
        CardTone.RED_FLAG,
        strings.text("place.elsewhere", elsewhere=1, total=3),
    )
    # The reply itself was genuine: the proof here is the photo, not the person.
    assert lines(card, CardRowKind.PERSON)["Here now"][0] is CardTone.OK


def test_cases_a_and_b_are_the_same_listing():
    assert load_demo_case("a").listing_text == load_demo_case("b").listing_text


# --- (c) a house for sale, posted as a rental ----------------------------------------------


def test_case_c_cannot_be_placed_and_says_the_house_is_for_sale():
    verdict, card = run_demo_case("c")
    # For sale is a red flag, not proof, and there is no 3D scan to place the photos in.
    assert verdict.state is VerdictState.UNVERIFIED
    assert verdict.reasons == [
        strings.text("reason.not_indexed"),
        strings.text("reason.for_sale"),
    ]
    place = lines(card, CardRowKind.PLACE)
    assert place["Real"] == (CardTone.NOT_CHECKED, strings.text("place.not_indexed"))
    assert place["For sale"] == (
        CardTone.RED_FLAG,
        "This home is listed for sale on Homes.com, not for rent. Red flag.",
    )
    assert lines(card, CardRowKind.PERSON)["Here now"][0] is CardTone.NOT_CHECKED


# --- all three -----------------------------------------------------------------------------


@pytest.mark.parametrize("case_id", ["a", "b", "c"])
def test_every_word_on_a_demo_card_comes_from_the_string_table(case_id):
    verdict, card = run_demo_case(case_id)
    for row in card.rows:
        for item in row.lines:
            assert from_the_string_table(item.label), item.label
            assert from_the_string_table(item.text), item.text
    for said in (*card.not_checked, *card.footer, *verdict.reasons):
        assert from_the_string_table(said), said


@pytest.mark.parametrize("case_id", ["a", "b", "c"])
def test_no_demo_card_shows_a_phone_a_hash_a_site_or_a_unit_number(case_id):
    verdict, card = run_demo_case(case_id)
    said = card.model_dump_json(exclude={"checked_at", "expires_at"}) + verdict.model_dump_json()
    record = PropertyRecord.model_validate_json(
        (DEMO_DIR / case_id / "property_record.json").read_text()
    )
    for secret in ("0177", "0188", "999", "fixtureliving", record.site_phone_hash):
        assert secret is None or secret not in said


@pytest.mark.parametrize("case_id", ["a", "b", "c"])
def test_a_demo_card_is_the_same_every_time(case_id):
    first, second = run_demo_case(case_id), run_demo_case(case_id)
    assert first[0] == second[0]
    assert first[1].rows == second[1].rows


@pytest.mark.parametrize("case_id", ["a", "b", "c"])
def test_a_demo_card_can_be_had_in_spanish_with_the_same_findings(case_id):
    (verdict, english), (verdicto, spanish) = (
        run_demo_case(case_id),
        run_demo_case(case_id, lang="es"),
    )
    assert spanish.lang == "es" and verdicto.state is verdict.state
    for en_row, es_row in zip(english.rows, spanish.rows, strict=True):
        assert [item.tone for item in es_row.lines] == [item.tone for item in en_row.lines]
        for en_line, es_line in zip(en_row.lines, es_row.lines, strict=True):
            assert es_line.text != en_line.text


@pytest.mark.parametrize("case_id", ["a", "b", "c"])
def test_a_demo_card_draws_as_a_picture(case_id):
    from snapback.card.render import render_card_png

    _, card = run_demo_case(case_id)
    assert render_card_png(card).startswith(b"\x89PNG\r\n\x1a\n")


def test_an_unknown_demo_case_is_a_clear_error():
    with pytest.raises(LookupError, match="a, b, c"):
        load_demo_case("z")
    with pytest.raises(LookupError):
        load_demo_case("../contracts")


# --- the DEMO_CASE flag --------------------------------------------------------------------


def client_for(tmp_path, demo_case: str | None) -> TestClient:
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path, demo_case=demo_case)
    return TestClient(create_app(settings))


def test_the_flag_is_read_from_the_environment_and_empty_means_off(monkeypatch):
    monkeypatch.setenv("DEMO_CASE", "B")
    assert Settings(_env_file=None).demo_case == "b"
    monkeypatch.setenv("DEMO_CASE", "")
    assert Settings(_env_file=None).demo_case is None
    monkeypatch.delenv("DEMO_CASE")
    assert Settings(_env_file=None).demo_case is None
    with pytest.raises(ValueError, match="a, b, c"):
        Settings(_env_file=None, demo_case="z")


def test_with_the_flag_a_post_with_no_text_runs_the_staged_listing(tmp_path):
    client = client_for(tmp_path, "a")
    made = client.post("/cases", data={})
    assert made.status_code == 201, made.text
    case = made.json()
    assert case["status"] == "waiting_for_approval"  # a challenge is drafted, nothing sent yet

    approved = client.post(
        f"/cases/{case['case_id']}/challenge/approve",
        json={"decision": "send"},
        headers={"Authorization": f"Bearer {case['token']}"},
    )
    assert approved.status_code == 200
    card = client.get(f"/cases/{case['case_id']}/card").json()
    assert card["state"] == "dont_pay" and card["source"] == "fixture"
    labels = [line["label"] for row in card["rows"] for line in row["lines"]]
    assert {"Unit on record", "Contact on record", "Link"} <= set(labels)


def test_with_the_flag_the_for_sale_house_finishes_without_a_challenge(tmp_path):
    client = client_for(tmp_path, "c")
    case = client.post("/cases", data={}).json()
    assert case["status"] == "done" and case["state"] == "unverified"
    card = client.get(f"/cases/{case['case_id']}/card").json()
    assert "For sale" in [line["label"] for line in card["rows"][0]["lines"]]


def test_with_the_flag_text_the_presenter_pastes_is_what_gets_read(tmp_path):
    client = client_for(tmp_path, "b")
    pasted = "2 bed in Unit 204, $1,700 a month. Send the deposit by Zelle today."
    case = client.post("/cases", data={"text": pasted}).json()
    client.post(
        f"/cases/{case['case_id']}/challenge/approve",
        json={"decision": "send"},
        headers={"Authorization": f"Bearer {case['token']}"},
    )
    card = client.get(f"/cases/{case['case_id']}/card").json()
    said = json.dumps(card)
    assert "Zelle before a viewing. Red flag." in said  # the pasted text was read
    assert card["state"] == "dont_pay"  # and the staged photo evidence still decides


def test_without_the_flag_nothing_changes(tmp_path):
    client = client_for(tmp_path, None)
    case = client.post("/cases", data={"text": "Two bed near the park."}).json()
    card = client.get(f"/cases/{case['case_id']}/card").json()
    labels = [line["label"] for row in card["rows"] for line in row["lines"]]
    assert "For sale" not in labels and "Unit on record" not in labels


# --- the session keeps what it learned about photos it could not place ----------------------


def test_photos_of_a_building_with_no_scan_are_not_reported_as_no_photos():
    _, card = run_demo_case("c")
    text = lines(card, CardRowKind.PLACE)["Real"][1]
    assert text == strings.text("place.not_indexed")
    assert text != strings.text("place.no_photos")


def test_the_demo_folder_holds_only_the_pack():
    names = {path.name for path in Path(DEMO_DIR).iterdir()}
    assert names == {"README.md", "a", "b", "c"}
