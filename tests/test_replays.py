"""D8 #71: every demo/replays/<slug>.json fits the shape lane T's replay view reads
(apps/web/src/replay/types.ts) and follows the locked rules."""

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import pytest

REPLAYS = sorted((Path(__file__).resolve().parents[1] / "demo" / "replays").glob("*.json"))
STEP_KINDS = {"listing", "chat", "hold_request", "payment", "discovery"}
STATUSES = {"matches", "doesnt_match", "not_confirmed", "warning", "not_checked", "red_flag"}
# Places named in the sources, street addresses and phone numbers: never in a replay
NEVER = re.compile(
    r"Fullerton|Conroe|\d+\s+\w+\s+(St|Ave|Rd|Ln|Dr)\b"
    r"|\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"  # a phone number, with or without (area code)
    r"|\b\d{3}-\d{4}\b"  # a 7-digit number
)
# The people named in the sources, as SHA-256 of the lowercased word, so their names are not
# written anywhere in this public repo (LOCKED 05:08 rule) while the guard still catches them.
NAME_DIGESTS = {
    "32bec227dacfaec2694e69e77ea19d2d22f9b944d6b99452e179a409d9467f11",
    "b74b842c67d77cc0c07a234fa89065180322c3950d2a904c1333e30c4ce3e892",
    "d86dc6e60b0632e30f2a78abe922c238e913dd5c74f76df6dc935f1ec73a5df6",
    "ee96e48ac867ab59efb688ad1eaef6ef54d06bc565785570164bd9bbb03d67e3",
    "b76aefa8fe4304f650962fb4af77b4db4b13d34ac9615391126027232ec16822",
}
REPLAY_LISTINGS = sorted(
    (Path(__file__).resolve().parents[1] / "fixtures" / "demo").glob("replay-*/listing.txt")
)


def names_a_person(text: str) -> bool:
    return any(
        hashlib.sha256(word.lower().encode()).hexdigest() in NAME_DIGESTS
        for word in re.findall(r"\w+", text)
    )


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_there_are_replays():
    assert len(REPLAYS) >= 1


@pytest.mark.parametrize("path", REPLAYS, ids=[p.stem for p in REPLAYS])
def test_shape_matches_the_replay_view(path):
    r = _load(path)
    assert r["slug"] == path.stem
    assert r["pattern"] in {"place", "person", "price"}
    assert isinstance(r["amount_usd"], int) and r["amount_usd"] > 0
    for step in r["steps"]:
        assert step["kind"] in STEP_KINDS
        if step["reported_on"]:  # empty when the source gives no date for the step
            date.fromisoformat(step["reported_on"])
        assert step["label"] and step["detail"]
    for finding in r["snapback"]["findings"]:
        assert finding["status"] in STATUSES and finding["text"]
    assert r["cant_catch"]  # every replay says plainly what SNAPBACK cannot catch


@pytest.mark.parametrize("path", REPLAYS, ids=[p.stem for p in REPLAYS])
def test_exactly_one_payment_and_the_stop_comes_before_it(path):
    r = _load(path)
    ids = [s["id"] for s in r["steps"]]
    payments = [s["id"] for s in r["steps"] if s["kind"] == "payment"]
    assert len(payments) == 1
    assert r["snapback"].get("stop_before", payments[0]) == payments[0]
    pay_at = ids.index(payments[0])
    for finding in r["snapback"]["findings"]:
        assert ids.index(finding["step_id"]) < pay_at  # SNAPBACK only saw what came before


@pytest.mark.parametrize("path", REPLAYS, ids=[p.stem for p in REPLAYS])
def test_dont_pay_only_on_proof(path):
    r = _load(path)
    proof = any(f["status"] == "doesnt_match" for f in r["snapback"]["findings"])
    assert r["snapback"]["verdict"] in {"dont_pay", "hold"}
    if r["snapback"]["verdict"] == "dont_pay":
        assert proof


@pytest.mark.parametrize("path", REPLAYS, ids=[p.stem for p in REPLAYS])
def test_a_sourced_replay_has_a_link_and_a_date_and_a_fictional_one_has_none(path):
    r = _load(path)
    if r["fictional"]:
        assert "source" not in r
    else:
        source = r["source"]
        assert source["name"] and source["url"].startswith("https://")
        date.fromisoformat(source["published_on"])


@pytest.mark.parametrize("path", REPLAYS, ids=[p.stem for p in REPLAYS])
def test_no_victim_name_or_street_address(path):
    text = path.read_text(encoding="utf-8")
    assert not NEVER.search(text.replace(_load(path).get("source", {}).get("url", ""), ""))
    assert not names_a_person(text)
    assert not {"name", "victim", "address"} & set(_load(path))


@pytest.mark.parametrize("path", REPLAY_LISTINGS, ids=[p.parent.name for p in REPLAY_LISTINGS])
def test_no_name_or_phone_in_a_replay_listing(path):
    text = path.read_text(encoding="utf-8")
    assert not NEVER.search(text) and not names_a_person(text)


def test_the_name_guard_catches_a_named_person_without_naming_them(monkeypatch):
    # a synthetic word stands in for a person: its digest joins the set for this test only
    word_digest = hashlib.sha256(b"fxvictim").hexdigest()
    monkeypatch.setattr(f"{__name__}.NAME_DIGESTS", NAME_DIGESTS | {word_digest})
    assert names_a_person("The renter, FxVictim, paid by Zelle.")
    assert not names_a_person("The renter paid by Zelle.")


def _status_of(kind: str, tone: str) -> str:
    """Card tone to the replay view's finding status (the locked row words)."""
    if tone == "hold":
        return "not_confirmed" if kind == "person" else "warning"
    return {
        "ok": "matches",
        "not_shown": "not_confirmed",
        "red_flag": "red_flag",
        "not_checked": "not_checked",
    }[tone]


@pytest.mark.parametrize("path", REPLAYS, ids=[p.stem for p in REPLAYS])
def test_every_finding_is_a_line_the_real_card_shows(path):
    from snapback.agent.demo import run_demo_case

    r = _load(path)
    verdict, card = run_demo_case(r["case_id"])
    assert verdict.state.value == r["snapback"]["verdict"]
    shown = {
        (line.text, _status_of(row.kind.value, line.tone.value))
        for row in card.rows
        for line in row.lines
    }
    for finding in r["snapback"]["findings"]:
        assert (finding["text"], finding["status"]) in shown, finding["text"]


@pytest.mark.parametrize(
    "phone",
    [
        "713-555-0199",
        "(713) 555-0199",
        "(713) 555.0199",
        "(713) 555 0199",
        "713.555.0199",
        "713 555 0199",
        "555-0142",
    ],
)
def test_the_guard_catches_every_phone_number_format(phone):
    assert NEVER.search(f"Text the poster at {phone} today.")


def test_the_guard_does_not_flag_ordinary_amounts_or_dates():
    assert not NEVER.search("A $2,500 deposit and a $75 fee in 2026.")
