"""Office confirmation, part 3: the one-time link, the outbox, and the routes. Fixture mode."""

import hashlib
import re
import smtplib
import socket
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from snapback.agent.join import KitLookups
from snapback.api.main import create_app
from snapback.contracts import DataSource
from snapback.office.proof import OfficeProofs, Outcome, RateLimited
from snapback.settings import Settings

PHONE = re.compile(r"\+?\d[\d\s().\-]{8,}\d")
DOMAIN = "fixtureliving.example"  # fx-prop-4's website on the fixture record
TEXT = "Nice 1 bed, $1,500 a month, pets ok"


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def make(tmp_path):
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    clock = Clock()
    app = create_app(settings, lookups=KitLookups(DataSource.FIXTURE))
    return TestClient(app), clock


@pytest.fixture
def client(tmp_path) -> TestClient:
    return make(tmp_path)[0]


def new_case(client, property_id="fx-prop-4"):
    made = client.post("/cases", data={"text": TEXT, "property_id": property_id})
    assert made.status_code == 201, made.text
    return made.json()


def answer(client, token, decision="yes"):
    return client.post("/office/answer", json={"token": token, "decision": decision})


def peek(client, token):
    return client.post("/office/peek", json={"token": token})


def write(case):
    return {"X-Case-Token": case["token"]}


def outbox_files(tmp_path):
    return sorted((tmp_path / "outbox").glob("*.txt")) if (tmp_path / "outbox").exists() else []


def token_in(path: Path) -> str:
    return re.search(r"/confirm#([A-Za-z0-9_\-]+)", path.read_text()).group(1)


# --- proofs, unit level -------------------------------------------------------------------


def proofs(tmp_path, clock=None):
    clock = clock or Clock()
    return OfficeProofs(tmp_path / "outbox", "http://localhost:5173", clock=clock), clock


def test_a_token_is_random_hashed_at_rest_single_use_and_expires_in_30_minutes(tmp_path):
    store, clock = proofs(tmp_path)
    store.request("CASE1", "leasing@" + DOMAIN, DOMAIN)
    (file,) = list((tmp_path / "outbox").glob("*.txt"))
    token = token_in(file)
    assert len(token) >= 43  # 256 bits, urlsafe
    # Only the hash is held in memory: the raw token is in no stored value.
    held = repr(store._entries)
    assert token not in held
    assert hashlib.sha256(token.encode()).hexdigest() in held
    first = store.redeem(token)
    assert first.outcome is Outcome.CONFIRMED and first.case_id == "CASE1"
    assert first.domain == DOMAIN
    assert store.redeem(token).outcome is Outcome.USED

    store.request("CASE2", "leasing@" + DOMAIN, DOMAIN)
    second = token_in(sorted((tmp_path / "outbox").glob("*.txt"))[-1])
    clock.now += 30 * 60 + 1
    assert store.redeem(second).outcome is Outcome.EXPIRED


def test_a_token_still_works_just_before_it_expires(tmp_path):
    store, clock = proofs(tmp_path)
    store.request("CASE1", "a@" + DOMAIN, DOMAIN)
    token = token_in(next((tmp_path / "outbox").glob("*.txt")))
    clock.now += 30 * 60 - 1
    assert store.redeem(token).outcome is Outcome.CONFIRMED


def test_an_unknown_token_is_unknown_and_a_new_request_voids_the_old_token(tmp_path):
    store, _ = proofs(tmp_path)
    assert store.redeem("nope").outcome is Outcome.UNKNOWN
    store.request("CASE1", "a@" + DOMAIN, DOMAIN)
    old = token_in(next((tmp_path / "outbox").glob("*.txt")))
    store.request("CASE1", "b@" + DOMAIN, DOMAIN)
    assert store.redeem(old).outcome is not Outcome.CONFIRMED


def test_an_old_token_does_not_survive_a_new_request_after_quiet_sweeps(tmp_path):
    store, clock = proofs(tmp_path)
    store.request("CASE1", "a@" + DOMAIN, DOMAIN)
    old = token_in(next((tmp_path / "outbox").glob("CASE1-*.txt")))
    clock.now += 16 * 60
    store.request("CASE2", "a@" + DOMAIN, DOMAIN)  # a sweep runs with CASE1 quiet for 16 min
    clock.now += 60
    store.request("CASE1", "b@" + DOMAIN, DOMAIN)  # t = 17 min, the old token is still live
    assert store.redeem(old).outcome is not Outcome.CONFIRMED


def test_requests_are_rate_limited_per_case(tmp_path):
    store, clock = proofs(tmp_path)
    for _ in range(3):
        store.request("CASE1", "a@" + DOMAIN, DOMAIN)
    with pytest.raises(RateLimited):
        store.request("CASE1", "a@" + DOMAIN, DOMAIN)
    store.request("CASE2", "a@" + DOMAIN, DOMAIN)  # another case is not affected
    clock.now += 16 * 60
    store.request("CASE1", "a@" + DOMAIN, DOMAIN)


def test_the_outbox_file_is_written_private_and_names_no_phone(tmp_path):
    store, _ = proofs(tmp_path)
    store.request("CASE1", "leasing@" + DOMAIN, DOMAIN)
    (file,) = list((tmp_path / "outbox").glob("*.txt"))
    assert file.stat().st_mode & 0o077 == 0
    body = file.read_text()
    assert "To: leasing@" + DOMAIN in body
    assert "FIXTURE" in body and "not sent" in body.lower()
    assert not PHONE.search(re.sub(r"/confirm#\S+", "", body))


def test_an_unsafe_case_id_cannot_escape_the_outbox_folder(tmp_path):
    store, _ = proofs(tmp_path)
    store.request("../../evil", "a@" + DOMAIN, DOMAIN)
    assert not (tmp_path.parent / "evil").exists()
    assert all(p.parent == tmp_path / "outbox" for p in (tmp_path / "outbox").iterdir())


def test_nothing_is_sent_over_any_network_client(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the outbox must never touch the network")

    for target in (smtplib.SMTP, smtplib.SMTP_SSL):
        monkeypatch.setattr(target, "__init__", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(httpx.Client, "send", boom)
    monkeypatch.setattr(httpx.AsyncClient, "send", boom)
    store, _ = proofs(tmp_path)
    store.request("CASE1", "a@" + DOMAIN, DOMAIN)
    assert store.redeem(token_in(next((tmp_path / "outbox").glob("*.txt")))).outcome is (
        Outcome.CONFIRMED
    )


def test_the_proof_code_imports_no_mail_or_http_client():
    import snapback.office.proof as proof_module

    source = Path(proof_module.__file__).read_text()
    for name in ("smtplib", "httpx", "requests", "urllib", "socket", "aiohttp", "email.mime"):
        assert f"import {name}" not in source and f"from {name}" not in source


# --- the routes ---------------------------------------------------------------------------


def test_office_status_shows_the_domain_on_record_and_labels_fixture(client):
    case = new_case(client)
    read = {"Authorization": f"Bearer {case['read_token']}"}
    status = client.get(f"/cases/{case['case_id']}/office", headers=read).json()
    assert status["domain"] == DOMAIN and status["offered"] is True
    assert status["confirmed"] is False and status["source"] == "fixture"
    assert status["delivery"] == "outbox"


def test_a_house_with_no_domain_on_record_is_not_offered_and_says_to_call(client):
    case = new_case(client, property_id="fx-prop-1")
    read = {"Authorization": f"Bearer {case['read_token']}"}
    status = client.get(f"/cases/{case['case_id']}/office", headers=read).json()
    assert status["domain"] is None and status["offered"] is False
    assert "call the office on a number you look up yourself" in status["guidance"].lower()
    sent = client.post(
        f"/cases/{case['case_id']}/confirm-office",
        json={"address": "a@" + DOMAIN},
        headers=write(case),
    )
    assert sent.status_code == 422
    assert "number you look up yourself" in sent.json()["detail"]


def test_office_status_needs_a_read_token_and_confirm_needs_the_write_token(client):
    case = new_case(client)
    url = f"/cases/{case['case_id']}/confirm-office"
    body = {"address": "a@" + DOMAIN}
    assert client.post(url, json=body).status_code == 401
    read_only = {"Authorization": f"Bearer {case['read_token']}"}
    assert client.post(url, json=body, headers=read_only).status_code == 403
    assert client.get(f"/cases/{case['case_id']}/office").status_code == 401
    # Tokens travel in headers only.
    assert client.post(url + f"?token={case['token']}", json=body).status_code == 401


def test_an_address_at_another_domain_is_refused_and_nothing_is_written(client, tmp_path):
    case = new_case(client)
    url = f"/cases/{case['case_id']}/confirm-office"
    for address in (
        "a@example.com",
        "a@gmail.com",
        f"a@{DOMAIN}.evil.com",
        "a@evil-" + DOMAIN,
        "not an address",
    ):
        response = client.post(url, json={"address": address}, headers=write(case))
        assert response.status_code == 422, address
    assert outbox_files(tmp_path) == []


def test_the_full_flow_writes_the_outbox_then_the_link_confirms_once(client, tmp_path):
    case = new_case(client)
    url = f"/cases/{case['case_id']}/confirm-office"
    sent = client.post(url, json={"address": "Leasing@" + DOMAIN}, headers=write(case))
    assert sent.status_code == 202, sent.text
    body = sent.json()
    assert body["sent"] is False and body["delivery"] == "outbox"
    assert body["domain"] == DOMAIN and body["source"] == "fixture"
    assert body["expires_in_minutes"] == 30
    (file,) = outbox_files(tmp_path)
    token = token_in(file)
    assert token not in sent.text  # the link goes to the mailbox, never back to the requester

    read = {"Authorization": f"Bearer {case['read_token']}"}
    before = client.get(f"/cases/{case['case_id']}/office", headers=read).json()
    assert before["confirmed"] is False

    ok = answer(client, token)
    assert ok.status_code == 200 and DOMAIN in ok.json()["message"]
    after = client.get(f"/cases/{case['case_id']}/office", headers=read).json()
    assert after["confirmed"] is True and after["confirmed_domain"] == DOMAIN

    again = answer(client, token)
    assert again.status_code == 410 and "already" in again.json()["detail"].lower()
    assert answer(client, "not-a-token").status_code == 404


def test_an_expired_link_says_so(tmp_path):
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    clock = Clock()
    app = create_app(settings, lookups=KitLookups(DataSource.FIXTURE), office_clock=clock)
    client = TestClient(app)
    case = new_case(client)
    client.post(
        f"/cases/{case['case_id']}/confirm-office",
        json={"address": "a@" + DOMAIN},
        headers=write(case),
    )
    token = token_in(outbox_files(tmp_path)[0])
    clock.now += timedelta(minutes=31).total_seconds()
    gone = answer(client, token)
    assert gone.status_code == 410 and "expired" in gone.json()["detail"].lower()
    read = {"Authorization": f"Bearer {case['read_token']}"}
    assert client.get(f"/cases/{case['case_id']}/office", headers=read).json()["confirmed"] is False


def test_rate_limit_per_case_returns_429(client):
    case = new_case(client)
    url = f"/cases/{case['case_id']}/confirm-office"
    codes = [
        client.post(url, json={"address": "a@" + DOMAIN}, headers=write(case)).status_code
        for _ in range(5)
    ]
    assert codes[:3] == [202] * 3 and codes[3] == 429


def test_confirming_adds_the_card_line_and_leaves_the_verdict_alone(client, tmp_path):
    case = new_case(client)
    cid = case["case_id"]
    card_before = client.get(f"/cases/{cid}/card").json()
    client.post(
        f"/cases/{cid}/confirm-office", json={"address": "a@" + DOMAIN}, headers=write(case)
    )
    answer(client, token_in(outbox_files(tmp_path)[0]))
    card_after = client.get(f"/cases/{cid}/card").json()
    texts = [line["text"] for row in card_after["rows"] for line in row["lines"]]
    assert any(t.startswith("Confirmed by the office") and DOMAIN in t for t in texts)
    assert card_after["state"] == card_before["state"]  # this case lacks the other proofs
    spanish = client.get(f"/cases/{cid}/card", params={"lang": "es"}).json()
    assert any(
        "Confirmado por la oficina" in line["text"] for r in spanish["rows"] for line in r["lines"]
    )
    assert card_before["source"] == card_after["source"] == "fixture"


def test_a_recorded_case_cannot_be_confirmed(client):
    recorded = client.get("/cases/7Q2M/card")
    if recorded.status_code != 200:
        pytest.skip("no recorded case on this build")
    response = client.post("/cases/7Q2M/confirm-office", json={"address": "a@" + DOMAIN})
    assert response.status_code in (404, 409, 422)


def test_the_ads_own_domain_never_counts(client, tmp_path):
    text = (
        f"Great 1 bed, email me at pat@evil-landlord.example or visit evil-landlord.example. {TEXT}"
    )
    made = client.post("/cases", data={"text": text, "property_id": "fx-prop-4"}).json()
    url = f"/cases/{made['case_id']}/confirm-office"
    assert (
        client.post(
            url, json={"address": "pat@evil-landlord.example"}, headers=write(made)
        ).status_code
        == 422
    )
    assert outbox_files(tmp_path) == []


def test_the_case_status_and_the_card_agree_after_the_confirmation(client, tmp_path):
    case = new_case(client)
    cid = case["case_id"]
    read = {"Authorization": f"Bearer {case['read_token']}"}
    client.post(
        f"/cases/{cid}/confirm-office", json={"address": "a@" + DOMAIN}, headers=write(case)
    )
    answer(client, token_in(outbox_files(tmp_path)[0]))
    status = client.get(f"/cases/{cid}", headers=read).json()
    card = client.get(f"/cases/{cid}/card").json()
    assert status["state"] in (None, card["state"])


def test_peeking_changes_nothing_and_only_an_answer_burns_the_token(client, tmp_path):
    case = new_case(client)
    cid = case["case_id"]
    read = {"Authorization": f"Bearer {case['read_token']}"}
    client.post(
        f"/cases/{cid}/confirm-office", json={"address": "a@" + DOMAIN}, headers=write(case)
    )
    token = token_in(outbox_files(tmp_path)[0])
    for _ in range(3):  # a mail scanner opening the page, again and again
        page = peek(client, token)
        assert page.status_code == 200 and page.json()["domain"] == DOMAIN
    assert client.get(f"/cases/{cid}/office", headers=read).json()["confirmed"] is False
    assert answer(client, token).status_code == 200
    assert client.get(f"/cases/{cid}/office", headers=read).json()["confirmed"] is True
    assert answer(client, token).status_code == 410
    assert peek(client, token).status_code == 410  # used


def test_the_tokens_are_never_in_an_address(client, tmp_path):
    # The link carries the token in the fragment (never sent to a server), and the API takes
    # it in a body, so no access log line holds one.
    case = new_case(client)
    client.post(
        f"/cases/{case['case_id']}/confirm-office",
        json={"address": "a@" + DOMAIN},
        headers=write(case),
    )
    token = token_in(outbox_files(tmp_path)[0])
    assert f"/confirm#{token}" in outbox_files(tmp_path)[0].read_text()
    assert client.get(f"/confirm/{token}").status_code in (404, 405)
    assert client.post(f"/confirm/{token}").status_code in (404, 405)


def test_the_page_and_the_email_say_which_ad_it_is(client, tmp_path):
    text = (
        "Unit 204, $1,500 a month. Managed by Fixture Living LLC, email "
        "leasing@fixture-rentals.example or visit fixture-rentals.example"
    )
    made = client.post("/cases", data={"text": text, "property_id": "fx-prop-4"}).json()
    client.post(
        f"/cases/{made['case_id']}/confirm-office",
        json={"address": "a@" + DOMAIN},
        headers=write(made),
    )
    file = outbox_files(tmp_path)[0]
    mail = file.read_text()
    for needed in (
        "Fixture Living Lofts",
        "100 Fixture Way, Fixture City, TX 00000",
        "204",
        "$1,500 a month",
        "Posted by: Fixture Living LLC",
        "leasing@fixture-rentals.example",
        "Not ours",
    ):
        assert needed in mail, needed
    shown = peek(client, token_in(file)).json()["listing"]
    assert shown["building"] == "Fixture Living Lofts"
    assert shown["address"] == "100 Fixture Way, Fixture City, TX 00000"
    assert shown["unit"] == "204" and shown["rent"] == 1500
    assert shown["poster"] == "Fixture Living LLC"
    assert "leasing@fixture-rentals.example" in shown["emails"]


def test_not_ours_never_confirms_and_the_card_says_the_office_did_not_recognise_the_ad(
    client, tmp_path
):
    case = new_case(client)
    cid = case["case_id"]
    read = {"Authorization": f"Bearer {case['read_token']}"}
    client.post(
        f"/cases/{cid}/confirm-office", json={"address": "a@" + DOMAIN}, headers=write(case)
    )
    token = token_in(outbox_files(tmp_path)[0])
    result = answer(client, token, "no")
    assert result.status_code == 200 and result.json()["decision"] == "no"
    assert client.get(f"/cases/{cid}/office", headers=read).json()["confirmed"] is False
    card = client.get(f"/cases/{cid}/card").json()
    texts = [line["text"] for row in card["rows"] for line in row["lines"]]
    assert any("does not recognise this ad" in t for t in texts)
    assert not any(t.startswith("Confirmed by the office") for t in texts)
    assert card["state"] != "verified"
    assert answer(client, token, "yes").status_code == 410  # the token is spent
    assert client.get(f"/cases/{cid}/office", headers=read).json()["confirmed"] is False


def test_the_answer_must_be_yes_or_no(client, tmp_path):
    assert (
        client.post("/office/answer", json={"token": "x", "decision": "maybe"}).status_code == 422
    )


class MemoryRegistry:
    def __init__(self):
        self.cases: dict[str, list[str]] = {}

    def register_case(self, case_id: str, renter_id: str) -> None:
        self.cases.setdefault(renter_id, []).append(case_id)

    def cases_of(self, renter_id: str) -> list[str]:
        return list(self.cases.get(renter_id, []))


def test_a_deleted_case_cannot_be_answered(tmp_path):
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path)
    registry = MemoryRegistry()
    client = TestClient(
        create_app(settings, lookups=KitLookups(DataSource.FIXTURE), registry=registry)
    )
    case = new_case(client)
    client.post(
        f"/cases/{case['case_id']}/confirm-office",
        json={"address": "a@" + DOMAIN},
        headers=write(case),
    )
    token = token_in(outbox_files(tmp_path)[0])
    assert peek(client, token).status_code == 200
    registry.cases.clear()  # the renter deleted everything
    assert peek(client, token).status_code == 404
    assert answer(client, token).status_code == 404


def test_an_answer_adds_a_verdict_event_to_the_trace(client, tmp_path):
    case = new_case(client)
    cid = case["case_id"]
    client.post(
        f"/cases/{cid}/confirm-office", json={"address": "a@" + DOMAIN}, headers=write(case)
    )
    answer(client, token_in(outbox_files(tmp_path)[0]), "no")
    read = {"Authorization": f"Bearer {case['read_token']}"}
    stream = client.get(f"/cases/{cid}/trace", headers=read).text
    # The trace ends with a verdict event for the new answer, so it matches the card.
    last = stream.strip().split("event: trace")[-1]
    assert '"kind":"verdict"' in last.replace(" ", "")


def test_a_not_ours_is_sticky_a_later_yes_never_clears_it(client, tmp_path):
    case = new_case(client)
    cid = case["case_id"]
    read = {"Authorization": f"Bearer {case['read_token']}"}
    url = f"/cases/{cid}/confirm-office"
    client.post(url, json={"address": "a@" + DOMAIN}, headers=write(case))
    first = token_in(outbox_files(tmp_path)[0])
    assert answer(client, first, "no").status_code == 200
    # "Email jane@ instead": a second link, and this time the answer is yes.
    assert (
        client.post(url, json={"address": "jane@" + DOMAIN}, headers=write(case)).status_code == 202
    )
    second = token_in(outbox_files(tmp_path)[-1])
    assert answer(client, second, "yes").status_code == 200

    status = client.get(f"/cases/{cid}/office", headers=read).json()
    assert status["declined"] is True and status["declined_domain"] == DOMAIN
    assert status["confirmed"] is True  # the yes is recorded too; the card shows both
    card = client.get(f"/cases/{cid}/card").json()
    texts = [line["text"] for row in card["rows"] for line in row["lines"]]
    assert any("does not recognise this ad" in t for t in texts)
    assert any(t.startswith("Confirmed by the office") for t in texts)
    assert card["state"] != "verified"
    # And a "no" after a "yes" does clear the confirmation (declining may clear it).
    client.post(url, json={"address": "b@" + DOMAIN}, headers=write(case))
    answer(client, token_in(outbox_files(tmp_path)[-1]), "no")
    status = client.get(f"/cases/{cid}/office", headers=read).json()
    assert status["declined"] is True and status["confirmed"] is False
