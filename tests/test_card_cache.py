"""A12 (#103): the card picture is drawn once per distinct card, and card times name the
building's zone."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from snapback.api.card_cache import CardPictures
from snapback.api.main import create_app
from snapback.card.render import render_card_png
from snapback.contracts import Card, VerdictState
from snapback.settings import Settings

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CARD = Card.model_validate_json((FIXTURES / "card_hold.json").read_text())


def counting():
    drawn = []

    def draw(card: Card) -> bytes:
        drawn.append(card.case_id)
        return render_card_png(card)

    return draw, drawn


# --- the cache -----------------------------------------------------------------------------


def test_the_same_card_is_drawn_once():
    draw, drawn = counting()
    pictures = CardPictures(draw=draw)
    first, second = pictures.png(CARD), pictures.png(CARD)
    assert first == second == render_card_png(CARD)
    assert len(drawn) == 1


def test_a_card_that_says_something_else_is_drawn_again():
    draw, drawn = counting()
    pictures = CardPictures(draw=draw)
    pictures.png(CARD)
    spanish = CARD.model_copy(update={"lang": "es"})
    other_state = CARD.model_copy(update={"state": VerdictState.DONT_PAY})
    later = CARD.model_copy(update={"checked_at": CARD.checked_at + timedelta(minutes=5)})
    for changed in (spanish, other_state, later):
        assert pictures.etag(changed) != pictures.etag(CARD)
        pictures.png(changed)
    assert len(drawn) == 4


def test_a_card_restamped_within_the_same_minute_is_the_same_picture():
    # A case that is still running is stamped "now" on every read. The picture shows the
    # time to the minute, so within a minute it is the same picture.
    draw, drawn = counting()
    pictures = CardPictures(draw=draw)
    base = CARD.checked_at.replace(second=0, microsecond=0)
    for seconds in (1, 20, 59):
        moment = base + timedelta(seconds=seconds, microseconds=123)
        pictures.png(CARD.model_copy(update={"checked_at": moment}))
    assert len(drawn) == 1


def test_the_cache_keeps_a_bounded_number_of_pictures():
    draw, drawn = counting()
    pictures = CardPictures(size=3, draw=draw)
    cards = [CARD.model_copy(update={"case_id": f"C{n}"}) for n in range(5)]
    for card in cards:
        pictures.png(card)
    assert len(pictures) == 3
    pictures.png(cards[4])  # still held
    assert len(drawn) == 5
    pictures.png(cards[0])  # dropped to make room, so drawn again
    assert len(drawn) == 6


def test_a_picture_just_asked_for_is_not_the_one_dropped():
    draw, drawn = counting()
    pictures = CardPictures(size=2, draw=draw)
    one, two, three = (CARD.model_copy(update={"case_id": f"C{n}"}) for n in range(3))
    pictures.png(one)
    pictures.png(two)
    pictures.png(one)  # used again, so `two` is now the oldest
    pictures.png(three)
    pictures.png(one)
    assert len(drawn) == 3


# --- over the API --------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, snapback_data_dir=tmp_path)))


def test_a_repeat_request_is_not_drawn_again(client, monkeypatch):
    import snapback.api.card_cache as card_cache

    calls = []
    real = card_cache.render_card_png
    monkeypatch.setattr(card_cache, "render_card_png", lambda card: calls.append(1) or real(card))
    fresh = TestClient(create_app(Settings(_env_file=None)))
    first = fresh.get("/cases/7Q2M/card.png")
    for _ in range(5):
        assert fresh.get("/cases/7Q2M/card.png").content == first.content
    assert len(calls) == 1
    fresh.get("/cases/7Q2M/card.png", params={"lang": "es"})
    assert len(calls) == 2


def test_the_picture_has_a_tag_and_an_unchanged_one_is_not_sent_twice(client):
    first = client.get("/cases/7Q2M/card.png")
    tag = first.headers["etag"]
    assert first.status_code == 200 and tag.startswith('"') and len(tag) >= 18
    assert first.headers["cache-control"] == "no-cache"

    again = client.get("/cases/7Q2M/card.png", headers={"If-None-Match": tag})
    assert again.status_code == 304 and again.content == b""
    assert again.headers["etag"] == tag

    spanish = client.get("/cases/7Q2M/card.png", params={"lang": "es"})
    assert spanish.headers["etag"] != tag
    stale = client.get("/cases/7Q2M/card.png", headers={"If-None-Match": '"something-else"'})
    assert stale.status_code == 200 and stale.content == first.content


def test_an_unknown_case_is_still_a_404(client):
    assert client.get("/cases/ZZZZ/card.png").status_code == 404


# --- the card's clock ----------------------------------------------------------------------


def new_card(client: TestClient) -> dict:
    case = client.post("/cases", data={"text": "Two bed near the park."}).json()
    return client.get(f"/cases/{case['case_id']}/card").json()


def test_a_new_card_is_stamped_in_houston_time_by_default(client):
    card = new_card(client)
    checked = datetime.fromisoformat(card["checked_at"])
    houston = ZoneInfo("America/Chicago")
    assert checked.utcoffset() == datetime.now(houston).utcoffset()
    assert Settings(_env_file=None).snapback_card_timezone == "America/Chicago"


def test_the_zone_can_be_set_and_an_unknown_one_is_refused(tmp_path):
    settings = Settings(
        _env_file=None, snapback_data_dir=tmp_path, snapback_card_timezone="America/Los_Angeles"
    )
    card = new_card(TestClient(create_app(settings)))
    checked = datetime.fromisoformat(card["checked_at"])
    assert checked.utcoffset() == datetime.now(ZoneInfo("America/Los_Angeles")).utcoffset()
    with pytest.raises(ValueError, match="time zone"):
        Settings(_env_file=None, snapback_card_timezone="Mars/Olympus_Mons")


def test_the_recorded_houston_card_is_served_on_houston_time_in_both_languages(client):
    # XO review of #106: it was saved on an Eastern clock and read "21:42 UTC-05:00".
    for lang in ("en", "es"):
        card = client.get("/cases/7Q2M/card", params={"lang": lang}).json()
        checked = datetime.fromisoformat(card["checked_at"])
        expires = datetime.fromisoformat(card["expires_at"])
        assert (checked.hour, checked.minute) == (20, 42)  # 21:42 Eastern is 20:42 Central
        assert checked.utcoffset() == timedelta(hours=-6) == expires.utcoffset()
        assert checked == CARD.checked_at  # the same moment, read on another clock
        # The time of the reply, inside the line, is on the same clock as the card.
        here_now = card["rows"][1]["lines"][0]["text"]
        assert "20:44" in here_now and "21:44" not in here_now


def test_the_recorded_cards_picture_reads_cst(client):
    from snapback.card.render import _stamp

    card = Card.model_validate(client.get("/cases/7Q2M/card").json())
    served = card.checked_at.astimezone(ZoneInfo("America/Chicago"))
    assert _stamp(served) == "2026-11-13 20:42 CST"
    assert client.get("/cases/7Q2M/card.png").status_code == 200


def test_a_recorded_case_with_no_zone_is_served_exactly_as_saved():
    import json

    from snapback.api.cases import RecordedCase
    from snapback.contracts import ModuleEvidence

    evidence = ModuleEvidence.model_validate(
        json.loads((FIXTURES / "module_evidence_hold.json").read_text())
    )
    assert RecordedCase("fx-7Q2M", CARD, [], evidence).card("http://localhost:5173") is CARD


def test_a_new_renderer_makes_a_new_picture_of_the_same_card(client, monkeypatch):
    # Without this, a client holding the old picture's tag would be told "unchanged".
    from snapback.card import render

    before = client.get("/cases/7Q2M/card.png")
    monkeypatch.setattr(render, "RENDER_VERSION", "test-next")
    after = client.get("/cases/7Q2M/card.png", headers={"If-None-Match": before.headers["etag"]})
    assert after.status_code == 200
    assert after.headers["etag"] != before.headers["etag"]

    pictures = CardPictures()
    old = pictures.etag(CARD)
    monkeypatch.setattr(render, "RENDER_VERSION", "test-after-that")
    assert pictures.etag(CARD) != old


def test_the_picture_names_the_zone_and_not_a_bare_offset():
    from snapback.card.render import _stamp

    houston = datetime(2026, 11, 14, 0, 30, tzinfo=ZoneInfo("America/Chicago"))
    summer = datetime(2026, 7, 4, 12, 0, tzinfo=ZoneInfo("America/Chicago"))
    assert _stamp(houston) == "2026-11-14 00:30 CST"
    assert _stamp(summer) == "2026-07-04 12:00 CDT"
