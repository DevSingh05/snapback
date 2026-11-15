"""A13 (#104): each staged demo case, end to end over the API, the way the demo runs it.

With `DEMO_CASE=a|b|c` set, a presenter posts nothing and gets the staged case. These tests
make the same calls the web app and the sidecar make, in order, and pin what comes back: the
headline, every row's lines and what each line says it is (Matches, Doesn't match, ...).

Everything is synthetic: the packs in fixtures/demo, written by the team.
"""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapback.agent.demo import run_demo_case
from snapback.api.main import create_app
from snapback.card import strings
from snapback.contracts import CardRowKind, CardTone
from snapback.settings import Settings

DEMO = Path(__file__).resolve().parent.parent / "fixtures" / "demo"
STAGED = "Staged example."
DRAFT = re.compile(
    r"Before you pay, ask them to send a photo of (?P<spot>.+) with the code "
    r"(?P<code>[A-Z0-9]{4}) written on paper\."
)


def check_the_draft(case: str, draft: str) -> None:
    """The challenge names one spot from the pack and a four-character code. The spot is a
    random draw, never a pick, so which one it is differs from run to run."""
    found = DRAFT.fullmatch(draft)
    assert found, draft
    ranking = json.loads((DEMO / case / "spot_ranking.json").read_text())
    drawable = [s["label"] for s in ranking["spots"] if not s.get("overlaps_listing_photo")]
    assert found["spot"] in drawable


FOR_SALE_LINE = (
    "Listed for sale on Homes.com by Fixture Realty Group since 2026-10-02. Homes for sale "
    "are sometimes also offered for lease, so confirm with that brokerage before you pay."
)

# What each staged card shows: per row, each line's label and the word for its tone.
ROWS = {
    "a": {
        "place": [("Real", "Matches"), ("Unit on record", "Warning")],
        "person": [
            ("Here now", "Doesn't match"),
            ("Allowed to rent it", "Not confirmed"),
            ("Contact on record", "Not confirmed"),
            ("Link", "Doesn't match"),
        ],
        "price": [("Payment ask", "Matches"), ("Rent vs record", "Warning")],
    },
    "b": {
        "place": [
            ("Real", "Doesn't match"),
            ("Home in the photos", "Not checked"),
            ("Unit on record", "Warning"),
        ],
        "person": [
            ("Here now", "Matches"),
            ("Allowed to rent it", "Not confirmed"),
            ("Contact on record", "Not confirmed"),
            ("Link", "Doesn't match"),
        ],
        "price": [("Payment ask", "Matches"), ("Rent vs record", "Warning")],
    },
    "c": {
        "place": [("Real", "Not checked"), ("For sale", "Warning")],
        "person": [("Here now", "Not checked"), ("Allowed to rent it", "Not confirmed")],
        "price": [("Payment ask", "Matches"), ("Rent vs record", "Not checked")],
    },
}


class Staged:
    """One staged case over the API: the client, what POST /cases returned, and helpers."""

    def __init__(self, tmp_path, case: str) -> None:
        settings = Settings(_env_file=None, snapback_data_dir=tmp_path, demo_case=case)
        self.client = TestClient(create_app(settings))
        made = self.client.post("/cases", data={})  # the presenter pastes nothing
        assert made.status_code == 201, made.text
        self.made = made.json()
        self.case_id = self.made["case_id"]
        self.write = {"Authorization": f"Bearer {self.made['token']}"}
        self.read = {"Authorization": f"Bearer {self.made['read_token']}"}

    def get(self, path: str = "", **kwargs):
        return self.client.get(f"/cases/{self.case_id}{path}", **kwargs)

    def card(self, lang: str = "en") -> dict:
        got = self.get("/card", params={"lang": lang})
        assert got.status_code == 200, got.text
        return got.json()

    def approve(self, decision: str = "send") -> dict:
        sent = self.client.post(
            f"/cases/{self.case_id}/challenge/approve",
            json={"decision": decision},
            headers=self.write,
        )
        assert sent.status_code == 200, sent.text
        return sent.json()

    def trace(self) -> list[dict]:
        got = self.get("/trace", headers=self.read)
        assert got.status_code == 200, got.text
        return [
            json.loads(line.removeprefix("data: "))
            for line in got.text.splitlines()
            if line.startswith("data: ")
        ]


def shown(card: dict, lang: str = "en") -> dict[str, list[tuple[str, str]]]:
    """Per row, each line's label and the word a reader sees for its tone."""
    out = {}
    for row in card["rows"]:
        kind = CardRowKind(row["kind"])
        out[row["kind"]] = [
            (line["label"], strings.tone_word(CardTone(line["tone"]), kind, lang))
            for line in row["lines"]
        ]
    return out


def said(card: dict) -> dict[str, str]:
    return {line["label"]: line["text"] for row in card["rows"] for line in row["lines"]}


def check_the_finished_card(run: Staged, case: str, state: str, headline: str) -> dict:
    """What holds for every staged card once its case is done."""
    status = run.get().json()
    assert (status["status"], status["state"]) == ("done", state)

    card = run.card()
    assert card["state"] == state
    assert strings.text(f"state.{card['state']}") == headline
    assert shown(card) == ROWS[case]
    # Staged, synthetic, and says so: FIXTURE on the card, the staged line first in the footer.
    assert card["source"] == "fixture"
    assert card["footer"][0].startswith(STAGED)
    assert card["case_id"] == run.case_id and not run.case_id.startswith("fx-")
    assert card["verify_url"].endswith(f"/c/{run.case_id}")
    assert card["not_checked"] == ["ID", "lease", "ownership"]

    # The same findings in Spanish: the same lines with the same tones, other words.
    spanish = run.card("es")
    assert spanish["state"] == state and spanish["lang"] == "es"
    assert [[line["tone"] for line in row["lines"]] for row in spanish["rows"]] == [
        [line["tone"] for line in row["lines"]] for row in card["rows"]
    ]
    assert spanish["footer"][0] != card["footer"][0]

    # The picture the sidecar sends is the same card.
    picture = run.get("/card.png")
    assert picture.status_code == 200 and picture.content.startswith(b"\x89PNG")
    assert picture.headers["content-type"] == "image/png"

    # The trace ends on the verdict the card shows, and it needs the case's secret.
    assert run.get("/trace").status_code == 401
    events = run.trace()
    assert events and events[-1]["kind"] == "verdict" and events[-1]["pick"] == state
    assert [event["seq"] for event in events] == sorted(event["seq"] for event in events)

    # Over the API the card is the one the pack gives when it is run directly.
    _, direct = run_demo_case(case)
    assert direct.state.value == state
    assert shown(direct.model_dump(mode="json")) == ROWS[case]
    return card


# --- (a) the reply copies one of the listing's own photos ----------------------------------


def test_case_a_over_the_api_ends_in_dont_pay_on_the_copied_reply(tmp_path):
    run = Staged(tmp_path, "a")
    # The photos are placed first, and then the renter is asked before anything is sent.
    assert (run.made["status"], run.made["state"]) == ("waiting_for_approval", None)
    assert run.made["source"] == "fixture"
    draft = run.made["challenge_text"]
    check_the_draft("a", draft)
    # Nothing has been sent yet, so the card holds and says nobody has been asked.
    waiting = run.card()
    assert waiting["state"] == "hold"
    assert said(waiting)["Here now"] == strings.text("here_now.not_requested")
    # The id alone shows no challenge; the read token does.
    assert run.get().json()["challenge"] is None
    assert run.get(headers=run.read).json()["challenge"]["text"] == draft

    done = run.approve()
    assert (done["status"], done["state"]) == ("done", "dont_pay")
    card = check_the_finished_card(run, "a", "dont_pay", "Don't pay. Something here doesn't match.")
    lines = said(card)
    assert lines["Here now"] == "The reply is a copy of listing photo 2. Red flag."
    assert lines["Real"] == (
        "Taken in this building, in the 2 bed / 2 bath floor plan (3 of 3 photos)."
    )
    assert lines["Allowed to rent it"].startswith("Not confirmed. Call Fixture Living LLC")
    assert lines["Rent vs record"].startswith("44% under this building's lowest 2 bed")
    assert card["for_sale"] is None
    # A second answer to the same challenge is refused: there is nothing waiting.
    again = run.client.post(
        f"/cases/{run.case_id}/challenge/approve", json={"decision": "send"}, headers=run.write
    )
    assert again.status_code == 409
    # Proof, so the listing agent's pack has steps and names the photo.
    pack = run.get("/report", headers=run.read).json()
    assert pack["reportable"] is True
    assert pack["proof_lines"] == ["The reply is a copy of listing photo 2."]


# --- (b) one listing photo was taken in another property -----------------------------------


def test_case_b_over_the_api_ends_in_dont_pay_on_a_photo_taken_elsewhere(tmp_path):
    run = Staged(tmp_path, "b")
    assert (run.made["status"], run.made["state"]) == ("waiting_for_approval", None)
    check_the_draft("b", run.made["challenge_text"])
    # A photo placed in another property is proof whatever the poster replies, so the card
    # already says so while the challenge waits.
    assert run.card()["state"] == "dont_pay"

    done = run.approve()
    assert (done["status"], done["state"]) == ("done", "dont_pay")
    card = check_the_finished_card(run, "b", "dont_pay", "Don't pay. Something here doesn't match.")
    lines = said(card)
    assert lines["Real"] == "Taken in a different building (1 of 3 photos). Red flag."
    # Presence was proven and it changes nothing: being inside is not being allowed to rent.
    assert lines["Here now"].startswith("Someone with access to a 2 bed / 2 bath unit here")
    assert "2 of 2 spots" in lines["Here now"]
    pack = run.get("/report", headers=run.read).json()
    assert pack["reportable"] is True
    assert pack["proof_lines"] == ["At least one listing photo was taken in a different property."]
    assert [pair["listing_photo"] for pair in pack["photo_pairs"]]


# --- (c) the house is listed for sale ------------------------------------------------------


def test_case_c_over_the_api_is_held_because_the_house_is_for_sale(tmp_path):
    run = Staged(tmp_path, "c")
    # No 3D scan of a house to place photos in, so nobody is asked anything: it is done at once.
    assert (run.made["status"], run.made["state"]) == ("done", "hold")
    assert run.made["challenge_text"] is None
    nothing_waiting = run.client.post(
        f"/cases/{run.case_id}/challenge/approve", json={"decision": "send"}, headers=run.write
    )
    assert nothing_waiting.status_code == 409

    card = check_the_finished_card(run, "c", "hold", "Hold off for now")
    lines = said(card)
    assert lines["For sale"] == FOR_SALE_LINE
    assert lines["Real"] == "Not checked (we have no 3D scan of this building)."
    assert lines["Here now"] == strings.text("here_now.not_requested")
    assert card["for_sale"] == {
        "status": "active",
        "site": "Homes.com",
        "listed_on": "2026-10-02",
        "changed_on": "2026-10-02",
        "offices": ["Fixture Realty Group"],
    }
    # A warning, never proof: this case can never read "Don't pay".
    assert "red_flag" not in [line["tone"] for row in card["rows"] for line in row["lines"]]
    pack = run.get("/report", headers=run.read).json()
    assert pack["reportable"] is True and pack["status_strip"]["brokerage"] == (
        "Fixture Realty Group"
    )


# --- all three -----------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["a", "b", "c"])
def test_a_staged_case_cancelled_or_left_alone_never_reads_worse_than_its_evidence(tmp_path, case):
    # The renter may say no to sending the challenge. The card then stands on what was found.
    run = Staged(tmp_path, case)
    if run.made["status"] == "waiting_for_approval":
        cancelled = run.approve("cancel")
        assert cancelled["status"] == "done"
    state = run.card()["state"]
    # (a) without the copied reply is a hold; (b) keeps its proof; (c) is held as before.
    assert state == {"a": "hold", "b": "dont_pay", "c": "hold"}[case]
    assert run.card()["footer"][0].startswith(STAGED)


def test_the_three_staged_cases_do_not_share_state(tmp_path):
    # Three presenters on one server each get their own case id, tokens and card.
    runs = []
    for number, case in enumerate("abc"):
        folder = tmp_path / str(number)
        folder.mkdir()
        runs.append(Staged(folder, case))
    assert len({run.case_id for run in runs}) == 3
    assert len({run.made["token"] for run in runs}) == 3
    other = runs[0].client.get(f"/cases/{runs[1].case_id}/card")
    assert other.status_code == 404  # another server's case is not this one's


# --- how the flag and the join meet (fixtures/demo/README.md) -------------------------------


def test_a_building_named_with_the_flag_runs_through_the_join_on_lane_d_s_record(tmp_path):
    # A property_id sent in fixture mode uses that record from lane D's synthetic kit, with
    # the shared stand-ins for the twin and the challenge, not the pack's. The listing read
    # is still the staged one, so the card still says it is staged.
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path, demo_case="a")
    client = TestClient(create_app(settings))
    made = client.post("/cases", data={"property_id": "fx-prop-3"})
    assert made.status_code == 201, made.text
    case = made.json()
    assert case["source"] == "fixture"
    if case["status"] == "waiting_for_approval":
        client.post(
            f"/cases/{case['case_id']}/challenge/approve",
            json={"decision": "send"},
            headers={"Authorization": f"Bearer {case['token']}"},
        )
    card = client.get(f"/cases/{case['case_id']}/card").json()
    lines = said(card)
    # The kit's record, not the pack's: its rents are compared, and the pack's unit list,
    # office phone and website are not there to be compared with.
    assert lines["Rent vs record"].endswith("on record. Ask why; discounts happen.")
    assert lines["Rent vs record"] != said(Staged(tmp_path / "pack", "a").card())["Rent vs record"]
    assert not {"Unit on record", "Contact on record", "Link"} & set(lines)
    # The shared stand-in has no copied reply, so this is never the pack's "Don't pay".
    assert card["state"] == "hold" and card["source"] == "fixture"
    assert card["footer"][0].startswith(STAGED)
    assert client.get(f"/cases/{case['case_id']}").json()["status"] == "done"


def test_a_building_we_hold_no_record_for_is_refused_with_the_flag_too(tmp_path):
    settings = Settings(_env_file=None, snapback_data_dir=tmp_path, demo_case="a")
    client = TestClient(create_app(settings))
    # Neither starts a case, and neither falls back to the pack without saying so.
    unknown = client.post("/cases", data={"property_id": "fx-no-such-building"})
    assert unknown.status_code == 422 and "token" not in unknown.json()
    malformed = client.post("/cases", data={"property_id": "../etc"})
    assert malformed.status_code == 422 and "token" not in malformed.json()
    assert unknown.json()["detail"] != malformed.json()["detail"]
