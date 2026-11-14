"""GET /replays serves demo/replays/*.json; a replay demo case names its source on its card."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback import replays
from snapback.agent.demo import run_demo_case
from snapback.api.main import create_app
from snapback.settings import Settings

SOURCE_FILES = sorted(replays.REPLAYS_DIR.glob("*.json"))


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(_env_file=None, snapback_data_dir=tmp_path))
    return TestClient(app)


def test_the_list_is_every_file_in_the_folder_not_a_hardcoded_pair(client):
    served = {r["slug"] for r in client.get("/replays").json()}
    assert served == {p.stem for p in SOURCE_FILES}
    assert len(served) >= 1


def test_a_replay_added_later_is_served_without_a_code_change(tmp_path):
    src = SOURCE_FILES[0]
    data = json.loads(src.read_text())
    data["slug"] = "added-later"
    (tmp_path / "added-later.json").write_text(json.dumps(data))
    shutil.copy(src, tmp_path / src.name)
    assert {r.slug for r in replays.load_replays(tmp_path)} == {"added-later", src.stem}


def test_one_replay_by_slug_and_unknown_or_odd_slugs_are_404(client):
    slug = SOURCE_FILES[0].stem
    assert client.get(f"/replays/{slug}").json()["slug"] == slug
    assert client.get("/replays/no-such-replay").status_code == 404
    assert client.get("/replays/..%2Fsecrets").status_code == 404


def test_a_file_with_a_victim_name_field_is_not_served(tmp_path):
    data = json.loads(SOURCE_FILES[0].read_text())
    data["victim"] = "Someone"
    (tmp_path / f"{data['slug']}.json").write_text(json.dumps(data))
    assert replays.load_replays(tmp_path) == []


def test_a_reported_case_without_a_source_is_not_served(tmp_path):
    data = json.loads(SOURCE_FILES[0].read_text())
    data.pop("source")
    (tmp_path / f"{data['slug']}.json").write_text(json.dumps(data))
    assert replays.load_replays(tmp_path) == []


@pytest.mark.parametrize(
    "lang,expect", [("en", "Replay of a reported case ("), ("es", "Repetición")]
)
def test_the_card_footer_for_a_replay_case_names_source_and_date(lang, expect):
    replay = next(r for r in replays.load_replays() if not r.fictional)
    _, card = run_demo_case(replay.case_id, lang=lang)
    first = card.footer[0]
    assert first.startswith(expect)
    assert replay.source.name in first
    assert replays.long_date(replay.source.published_on, lang) in first
    assert "Staged example" not in " ".join(card.footer)
    if lang == "en":
        assert first.endswith("The listing and house are re-created; no real names.")


def test_a_plain_staged_case_keeps_the_staged_footer():
    _, card = run_demo_case("a")
    assert card.footer[0].startswith("Staged example.")


def test_long_dates():
    assert replays.long_date(date(2025, 2, 15), "en") == "Feb 15, 2025"
    assert replays.long_date(date(2025, 2, 15), "es") == "15 feb 2025"


def test_every_replay_with_a_demo_folder_is_a_replay_case():
    folder = Path(__file__).resolve().parents[1] / "fixtures" / "demo"
    for r in replays.load_replays():
        assert (folder / r.case_id).is_dir() or r.fictional


def _make_case(client, **fields):
    return client.post("/cases", data=fields)


def test_run_this_case_starts_the_replay_case_and_its_card_names_the_source(client):
    replay = next(r for r in replays.load_replays() if not r.fictional)
    made = _make_case(client, demo_case=replay.case_id)
    assert made.status_code == 201
    card = client.get(f"/cases/{made.json()['case_id']}/card").json()
    assert card["footer"][0].startswith("Replay of a reported case (")
    assert replay.source.name in card["footer"][0]


def test_run_this_case_refuses_any_demo_case_that_is_not_a_replay(client):
    assert _make_case(client, demo_case="a").status_code == 422
    assert _make_case(client, demo_case="../x").status_code == 422
