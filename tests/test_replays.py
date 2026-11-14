"""D8 #71: every demo/replays/<slug>.json fits the shape lane T's replay view reads
(apps/web/src/replay/types.ts) and follows the locked rules."""

import json
import re
from datetime import date
from pathlib import Path

import pytest

REPLAYS = sorted((Path(__file__).resolve().parents[1] / "demo" / "replays").glob("*.json"))
STEP_KINDS = {"listing", "chat", "hold_request", "payment", "discovery"}
STATUSES = {"matches", "doesnt_match", "not_confirmed", "warning", "not_checked"}
# Victims and places named in the sources: never in a replay (no name or address field, and none
# smuggled into free text either)
NEVER = re.compile(
    r"Yeager|Reiling|Patricia|\bPam\b|Leonard|Fullerton|Conroe|\d+\s+\w+\s+(St|Ave|Rd|Ln|Dr)\b"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_there_are_replays():
    assert len(REPLAYS) >= 2


@pytest.mark.parametrize("path", REPLAYS, ids=[p.stem for p in REPLAYS])
def test_shape_matches_the_replay_view(path):
    r = _load(path)
    assert r["slug"] == path.stem
    assert r["pattern"] in {"place", "person", "price"}
    assert isinstance(r["amount_usd"], int) and r["amount_usd"] > 0
    for step in r["steps"]:
        assert step["kind"] in STEP_KINDS
        date.fromisoformat(step["reported_on"])
        assert step["label"] and step["detail"]
    for finding in r["snapback"]["findings"]:
        assert finding["status"] in STATUSES and finding["text"]


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
    assert not {"name", "victim", "address"} & set(_load(path))
