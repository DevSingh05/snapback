"""A20 (#126): `GET /cases/{id}/report`, the "Report this copy" evidence pack.

For a listing agent whose listing was copied: one pack to take to the platform. Everything in
it is a fact from code. It holds no score, no hash and no image bytes, and it calls nobody
anything. The cases here are the staged ones in fixtures/demo; nothing is from a sponsor.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.agent.demo import run_demo_case
from snapback.api.main import create_app
from snapback.api.report import build_report
from snapback.card import strings
from snapback.contracts import ModuleEvidence, ReportPlatform, ReportResponse, VerdictState
from snapback.settings import Settings
from snapback.verdict import build_card

CONTRACTS = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")
HEX_RUN = re.compile(r"[0-9a-fA-F]{16,}")
NUMBER_WORDS = ("score", "inlier", "threshold", "confidence", "distance", "hash", "model_id")


def client_for(tmp_path, **settings) -> TestClient:
    made = Settings(_env_file=None, snapback_data_dir=tmp_path, **settings)
    return TestClient(create_app(made))


def staged(tmp_path, case: str, **settings) -> tuple[TestClient, dict]:
    """One of the staged demo cases, started over the API. Returns the client and the case."""
    client = client_for(tmp_path, demo_case=case, **settings)
    made = client.post("/cases", data={})
    assert made.status_code == 201, made.text
    return client, made.json()


def report(client: TestClient, case: dict, token: str | None = "read_token", **params):
    headers = {"Authorization": f"Bearer {case[token]}"} if token else {}
    return client.get(f"/cases/{case['case_id']}/report", headers=headers, params=params)


def keys_of(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in keys_of(item)}
    if isinstance(value, list):
        return {key for item in value for key in keys_of(item)}
    return set()


def numbers_in(value) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, int | float):
        return [value]
    if isinstance(value, dict):
        return [n for item in value.values() for n in numbers_in(item)]
    if isinstance(value, list):
        return [n for item in value for n in numbers_in(item)]
    return []


# --- who may read it -----------------------------------------------------------------------


def test_the_read_token_in_the_header_gives_the_pack(tmp_path):
    client, case = staged(tmp_path, "c")
    got = report(client, case)
    assert got.status_code == 200, got.text
    pack = ReportResponse.model_validate(got.json())
    assert pack.case_id == case["case_id"] and pack.source.value == "fixture"
    # Whoever may write may read, and the other header is accepted as on every case route.
    assert report(client, case, token="token").status_code == 200
    by_other_header = client.get(
        f"/cases/{case['case_id']}/report", headers={"X-Case-Token": case["read_token"]}
    )
    assert by_other_header.status_code == 200


def test_a_token_in_the_address_is_refused_even_the_right_one(tmp_path):
    client, case = staged(tmp_path, "c")
    in_address = client.get(
        f"/cases/{case['case_id']}/report", params={"token": case["read_token"]}
    )
    assert in_address.status_code == 401
    assert "header" in in_address.json()["detail"].lower()
    # Even beside a good header: the address is what servers log, so it must not carry one.
    both = client.get(
        f"/cases/{case['case_id']}/report",
        headers={"Authorization": f"Bearer {case['read_token']}"},
        params={"token": "x"},
    )
    assert both.status_code == 401
    assert case["read_token"] not in in_address.text


def test_no_token_and_a_wrong_token_are_refused(tmp_path):
    client, case = staged(tmp_path, "c")
    assert report(client, case, token=None).status_code == 401
    wrong = client.get(
        f"/cases/{case['case_id']}/report", headers={"Authorization": "Bearer not-the-token"}
    )
    assert wrong.status_code == 403


def test_an_unknown_case_is_not_found(tmp_path):
    client, case = staged(tmp_path, "c")
    got = client.get("/cases/ZZZZ/report", headers={"Authorization": f"Bearer {case['token']}"})
    assert got.status_code == 404


def test_the_public_card_is_as_it_was(tmp_path):
    client, case = staged(tmp_path, "c")
    assert client.get(f"/cases/{case['case_id']}/card").status_code == 200


# --- what is in it -------------------------------------------------------------------------


def test_the_for_sale_case_shows_the_status_strip_and_the_brokerage(tmp_path):
    client, case = staged(tmp_path, "c")
    pack = report(client, case).json()
    assert pack["state"] == "hold" and pack["reportable"] is True
    assert pack["status_strip"] == {
        "status": "active",
        "site": "Homes.com",
        "listed_on": "2026-10-02",
        "changed_on": "2026-10-02",
        "brokerage": "Fixture Realty Group",
    }
    # The proof lines are decide()'s own reasons, in its order.
    verdict, card = run_demo_case("c")
    # Only the reasons about the listing and the record go in the pack, in decide()'s order.
    assert verdict.reasons == [strings.text("reason.for_sale"), strings.text("reason.not_indexed")]
    assert pack["proof_lines"] == [strings.text("reason.for_sale")]
    assert pack["proof_lines"][0] == strings.text("reason.for_sale")
    assert pack["not_checked"] == card.not_checked
    assert [steps["platform"] for steps in pack["platforms"]] == [
        "facebook",
        "zillow",
        "craigslist",
    ]


def test_a_copied_reply_is_reportable_and_names_the_photo(tmp_path):
    client, case = staged(tmp_path, "a")  # the reply is a copy of listing photo 2
    client.post(
        f"/cases/{case['case_id']}/challenge/approve",
        json={"decision": "send"},
        headers={"Authorization": f"Bearer {case['token']}"},
    )
    pack = report(client, case).json()
    assert pack["state"] == "dont_pay" and pack["reportable"] is True
    assert pack["proof_lines"] == ["The reply is a copy of listing photo 2."]
    assert pack["photo_pairs"] == [
        {
            "listing_photo": 2,
            "finding": "The reply is a copy of listing photo 2.",
            "listing_image_url": None,
            "match_image_url": None,
        }
    ]
    assert pack["status_strip"] is None  # this home's record was not for sale


def test_a_photo_taken_in_another_property_is_a_pair_too(tmp_path):
    client, case = staged(tmp_path, "b")
    pack = report(client, case).json()
    assert pack["state"] == "dont_pay" and pack["reportable"] is True
    assert pack["photo_pairs"], "the photos placed elsewhere are listed"
    for pair in pack["photo_pairs"]:
        assert (
            pair["finding"]
            == f"Listing photo {pair['listing_photo']} was taken in a different property."
        )
        assert pair["listing_image_url"] is None and pair["match_image_url"] is None


def test_a_case_with_nothing_that_shows_a_copy_gets_no_report_steps(tmp_path):
    # A hold on something not confirmed is not a copy. The poster may be a real agent, so the
    # pack hands nobody report steps.
    client = client_for(tmp_path)
    case = client.post("/cases", data={"text": "2 bed near the park, $1,400 a month."}).json()
    if case["status"] == "waiting_for_approval":
        client.post(
            f"/cases/{case['case_id']}/challenge/approve",
            json={"decision": "cancel"},
            headers={"Authorization": f"Bearer {case['token']}"},
        )
    pack = report(client, case).json()
    assert pack["state"] != "dont_pay" and pack["reportable"] is False
    assert pack["platforms"] == [] and pack["photo_pairs"] == []
    assert pack["status_strip"] is None


# --- what is never in it -------------------------------------------------------------------


@pytest.mark.parametrize("case_id", ["a", "b", "c"])
def test_the_pack_has_no_hash_no_score_and_no_number(tmp_path, case_id):
    client, case = staged(tmp_path, case_id)
    if case["status"] == "waiting_for_approval":
        client.post(
            f"/cases/{case['case_id']}/challenge/approve",
            json={"decision": "send"},
            headers={"Authorization": f"Bearer {case['token']}"},
        )
    got = report(client, case)
    body, pack = got.text, got.json()
    assert not HEX_RUN.search(body), "a long hex run looks like a hash"
    keys = keys_of(pack)
    assert not [key for key in keys if any(word in key.lower() for word in NUMBER_WORDS)]
    # The only numbers are which listing photo a pair is about.
    assert numbers_in(pack) == [pair["listing_photo"] for pair in pack["photo_pairs"]]
    # No secret of the case, no image bytes, and no address that is not one of our routes.
    assert case["token"] not in body and case["read_token"] not in body
    assert "base64" not in body and "data:image" not in body
    for address in re.findall(r"https?://[^\s\"']+", body):
        raise AssertionError(f"an outside address in the pack: {address}")
    if pack["aerial_url"] is not None:
        assert pack["aerial_url"] == f"/cases/{case['case_id']}/aerial"


def test_the_pack_carries_nothing_about_the_renter(tmp_path):
    # Conductor, Sat 03:15: no renter id and none of the text they sent. Listing facts only.
    # The thread here fires a payment rule and names a poster, so there is something to leak.
    client = client_for(tmp_path, demo_case="c")
    renter = "imsg-" + "0a1b2c3d4e5f" * 2
    words = "Fxposter here, send the deposit by Zelle today. Ask for Fxrenter at the door."
    made = client.post("/cases", data={"text": words, "renter_id": renter})
    assert made.status_code == 201, made.text
    case = made.json()
    # The rule did fire, and the card (which is the renter's own) says so.
    card = client.get(f"/cases/{case['case_id']}/card").json()
    said = " ".join(line["text"] for row in card["rows"] for line in row["lines"])
    assert "Zelle" in said

    got = report(client, case)
    assert got.status_code == 200, got.text
    body, pack = got.text, got.json()
    assert pack["reportable"] is True  # the record shows the home for sale
    assert renter not in body and renter.removeprefix("imsg-") not in body
    # Not the names in the thread, not the sentence that fired the rule, not a word of it.
    for word in ("Fxposter", "Fxrenter", "Zelle", "deposit", "door"):
        assert word.lower() not in body.lower(), word
    # And not the reasons that came from the thread.
    for key in ("reason.payment_flag", "reason.rule_flag", "reason.price_flag"):
        assert strings.text(key) not in pack["proof_lines"]
    assert pack["proof_lines"] == [strings.text("reason.for_sale")]
    about_the_renter = ("renter", "owner_id", "client", "thread", "message", "text", "cookie")
    assert not [
        key for key in keys_of(pack) if any(word in key.lower() for word in about_the_renter)
    ]
    assert not HEX_RUN.search(body)


def test_the_twin_link_is_given_only_when_a_photo_was_placed(tmp_path):
    client, case = staged(tmp_path, "b")  # photos placed in another property
    assert report(client, case).json()["twin_url"] == f"/case/{case['case_id']}/twin"
    other = tmp_path / "c"
    other.mkdir()
    client, case = staged(other, "c")  # nothing could be placed
    assert report(client, case).json()["twin_url"] is None


def test_the_pack_never_says_what_the_card_must_not():
    for case_id in ("a", "b", "c"):
        for lang, banned in (
            ("en", ("scammer", "fraudster", "criminal", "safe", "verified")),
            ("es", ("estafador", "delincuente", "seguro", "verificado")),
        ):
            _, card = run_demo_case(case_id, lang=lang)
            modules = ModuleEvidence.model_validate(json.loads(_evidence_of(case_id)))
            pack = build_report(modules, card, case_id=card.case_id, lang=lang, aerial=False)
            said = " ".join(
                [*pack.proof_lines, *(pair.finding for pair in pack.photo_pairs)]
                + [step for steps in pack.platforms for step in steps.steps]
            ).lower()
            assert not any(word in said for word in banned), said
            assert "—" not in said


def _evidence_of(case_id: str) -> str:
    from snapback.agent import CaseSession, PolicyChooser, Trace, run_case
    from snapback.agent.demo import demo_modules, load_demo_case
    from snapback.agent.intake import read_listing
    from snapback.contracts import DataSource

    demo = load_demo_case(case_id)
    session = CaseSession(
        f"fx-{case_id}",
        demo_modules(demo, read_listing(demo.listing_text)),
        Trace(f"fx-{case_id}", DataSource.FIXTURE),
    )
    run_case(session, PolicyChooser(), lambda draft: "send")
    return session.evidence.model_dump_json()


# --- the steps, in both languages ----------------------------------------------------------


def test_the_steps_name_each_platform_s_own_report_path(tmp_path):
    client, case = staged(tmp_path, "c")
    by_platform = {steps["platform"]: steps for steps in report(client, case).json()["platforms"]}
    assert by_platform["facebook"]["name"] == "Facebook Marketplace"
    assert any("Report listing" in step for step in by_platform["facebook"]["steps"])
    # The card's standing rule holds here too: the banned word is in no string we write,
    # not even as a platform's menu label.
    every = [step for steps in by_platform.values() for step in steps["steps"]]
    assert not any("scam" in step.lower() for step in every)
    assert any("Report listing" in step for step in by_platform["zillow"]["steps"])
    assert any("prohibited" in step for step in by_platform["craigslist"]["steps"])
    assert set(by_platform) == {platform.value for platform in ReportPlatform}
    for steps in by_platform.values():
        assert 2 <= len(steps["steps"]) <= 5


def test_the_pack_is_in_spanish_when_asked(tmp_path):
    client, case = staged(tmp_path, "c")
    english, spanish = report(client, case).json(), report(client, case, lang="es").json()
    assert spanish["lang"] == "es" and english["lang"] == "en"
    assert spanish["proof_lines"][0] == strings.text("reason.for_sale", "es")
    assert spanish["platforms"][0]["steps"] != english["platforms"][0]["steps"]
    assert spanish["status_strip"] == english["status_strip"]  # facts, not words
    assert set(strings.TABLES["es"]) == set(strings.TABLES["en"])
    assert report(client, case, lang="fr").status_code == 422


# --- it is built by code from the evidence -------------------------------------------------


def test_the_state_in_the_pack_is_the_card_s_own(tmp_path):
    for case_id in ("a", "b", "c"):
        verdict, card = run_demo_case(case_id)
        modules = ModuleEvidence.model_validate(json.loads(_evidence_of(case_id)))
        pack = build_report(modules, card, case_id=card.case_id, lang="en", aerial=False)
        assert pack.state is card.state is verdict.state
        # decide()'s own reasons, in its order, less everything that is not about the
        # listing or the record.
        assert pack.proof_lines == [reason for reason in verdict.reasons if reason in LISTING]
        assert pack.proof_lines, "each staged case has a listing fact to report"
        assert pack.reportable is (verdict.state is VerdictState.DONT_PAY or case_id == "c")


LISTING = {
    strings.text("reason.for_sale"),
    strings.text("reason.photo_elsewhere"),
    strings.text("reason.forged_copy", n=2),
}


def pack_for(lang="en", **sections):
    """A pack built straight from evidence, for cases the staged ones do not cover."""
    raw = json.loads((CONTRACTS / "module_evidence_hold.json").read_text())
    modules = ModuleEvidence.model_validate(raw | sections)
    card = build_card(modules, checked_at=CHECKED_AT)
    return build_report(modules, card, case_id=card.case_id, lang=lang, aerial=False)


@pytest.mark.parametrize("lang", ["en", "es"])
@pytest.mark.parametrize(
    "authority",
    [
        None,  # the hold fixture's own authority, poster_said "Fixture Living LLC"
        {"status": "mismatch", "poster_said": "Fxposter Rentals LLC"},
    ],
)
def test_the_pack_leaks_no_poster_name_and_no_thread_text(authority, lang):
    # The fixture's payment rule fired on a sentence from the thread and the poster named
    # themselves. Neither may appear anywhere in the pack, in any field or language.
    sections = {"for_sale": {"status": "active", "site": "Homes.com"}}
    if authority is not None:
        sections["authority"] = authority
    pack = pack_for(lang=lang, **sections)
    assert pack.reportable is True  # a pack that is not reportable would hide a leak
    body = pack.model_dump_json()
    said = ["Fixture Living LLC", "Fxposter Rentals LLC"]
    spans = ["send the deposit by Zelle and I will mail the keys", "Zelle"]
    for leak in said + spans:
        assert leak.lower() not in body.lower(), leak


def test_the_proof_lines_are_an_allowlist_of_listing_and_record_reasons():
    # A held case with a reason of every other kind: who, presence, place, price, the thread.
    pack = pack_for(
        authority={"status": "unknown", "office_phone_match": "no", "link_domain": "lookalike"},
        for_sale={"status": "active", "site": "Homes.com"},
        price={"status": "below_range", "listed_rent": 900, "unit": "not_on_record"},
    )
    assert pack.state is VerdictState.HOLD and pack.reportable is True
    assert pack.proof_lines == [strings.text("reason.for_sale")]
    kept_out = [
        "reason.payment_flag",
        "reason.rule_flag",
        "reason.price_flag",
        "reason.phone_flag",
        "reason.lookalike_link",
        "reason.unit_flag",
        "reason.located",
        "reason.authority_unknown",
        "reason.presence_proven_not_authority",
        "reason.presence_missing",
    ]
    for key in kept_out:
        assert strings.text(key) not in pack.proof_lines, key


@pytest.mark.parametrize(
    "authority",
    [
        # The phone is not the office's: not confirmed, and the poster may be a real agent.
        {"status": "matches_record", "office_phone_match": "no"},
        # The name is not the one on record: the same.
        {"status": "mismatch", "poster_said": "Other Fixture Rentals"},
        {"status": "unknown"},
    ],
)
def test_a_hold_on_something_not_confirmed_is_not_reportable(authority):
    pack = pack_for(authority=authority, rules=[], price=None)
    assert pack.state is VerdictState.HOLD
    assert pack.reportable is False
    assert pack.platforms == [] and pack.photo_pairs == [] and pack.proof_lines == []


def test_for_sale_by_the_office_on_record_is_not_reportable():
    # Ruling, Sat 03:36: the record shows the home for sale and the ad's phone is the
    # office's on record. That is the brokerage itself offering it, not a copy.
    for_sale = {"status": "active", "site": "Homes.com", "offices": ["Fixture Realty Group"]}
    theirs = pack_for(
        authority={"status": "matches_record", "office_phone_match": "yes"}, for_sale=for_sale
    )
    assert theirs.reportable is False and theirs.platforms == []
    assert theirs.status_strip is not None  # the facts are still there to read
    for match in ("no", "not_checked"):
        other = pack_for(
            authority={"status": "matches_record", "office_phone_match": match},
            for_sale=for_sale,
        )
        assert other.reportable is True and len(other.platforms) == 3
