"""The MCP server, against a fake SNAPBACK API (httpx.MockTransport) and fake photo hosts.

Each tool is called through a real MCP client connected in-process, so the schemas, the
argument checks and the error mapping are the ones an agent sees.
"""

from __future__ import annotations

import asyncio
import json
import socket
from typing import Any

import httpx
import pytest
from mcp import Client

from snapback.mcp_server import TOKEN_HELD, Snapback, build_server, photo_client, vetted_address

WRITE = "write-secret-0123456789abcdef"
READ = "read-secret-0123456789abcdef"
FINDER = "finder-secret-0123456789abcdef"
SECRETS = (WRITE, READ, FINDER)
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64

CARD = {
    "case_id": "7Q2M",
    "source": "fixture",
    "state": "dont_pay",
    "checked_at": "2026-11-14T16:00:00Z",
    "expires_at": "2026-11-15T16:00:00Z",
    "rows": [
        {
            "kind": "place",
            "lines": [
                {"label": "Here now", "text": "Photo 1 was taken elsewhere.", "tone": "red_flag"}
            ],
        },
        {
            "kind": "price",
            "lines": [
                {
                    "label": "Payment ask",
                    "text": "Asks for Zelle before a viewing.",
                    "tone": "red_flag",
                    "source": "live",
                }
            ],
        },
    ],
    "summary": [
        "Photo 1 was taken in a different building.",
        "It asks for Zelle before a viewing.",
    ],
    "checks_out": ["Rent: close to the record."],
    "does_not": ["Here now: Photo 1 was taken elsewhere."],
    "not_checked": ["ID", "lease", "ownership"],
    "footer": ["Two rules: never pay before a signed lease and a viewing."],
    "verify_url": "http://localhost:5173/c/7Q2M",
}

WALK = {
    "plan": {
        "property_id": "fx-prop-1",
        "kind": "apartment",
        "source": "fixture",
        "has_scan": True,
        "rooms_note": "Rooms are labelled in the scan.",
        "stops": [
            {"kind": "arrive", "key": "a", "title": "Outside"},
            {
                "kind": "room",
                "key": "k",
                "title": "Kitchen",
                "sweep_id": "SWEEP-SECRET",
                "position": [1.0, 2.0, 3.0],
                "photos": [{"photo_id": "ph1", "alias": "P1", "sweep_id": "SWEEP-SECRET"}],
                "ad_view": "placed",
                "tip": "Open the oven.",
            },
            {
                "kind": "room",
                "key": "b",
                "title": "Bedroom",
                "photos": [],
                "ad_view": "none_placed",
            },
        ],
        "links": {"tour_prep": "x", "tour_prep_api": "y", "tour_draft_hint": "z"},
        "coverage": {"counted": "rooms", "total": 2, "with_photo": 1, "line": "1 of 2 rooms."},
    },
    "model_id": "MODEL-SECRET",
    "locate": {
        "case_id": "7Q2M",
        "thresholds_version": "t1",
        "photos": [
            {"photo_id": "ph1", "status": "located_in_claimed", "inliers": 812},
            {"photo_id": "ph2", "status": "located_elsewhere", "matched_property_id": "fx-2"},
        ],
    },
}

PROPOSAL = {
    "id": "pr-1",
    "key": "propose_no_walkup",
    "update": {"no_walkup": True},
    "text": "Skip walk-ups from now on?",
    "evidence": "you passed on 3 of 3 walk-ups",
    "reason": "Three passes in a row.",
    "chosen_by": "policy",
    "status": "proposed",
    "at": "2026-11-14T16:00:00Z",
}

PICK = {
    "pid": "fx-prop-1",
    "rank": 1,
    "kind": "apartment",
    "has_scan": True,
    "line": "1 bed from 1,450 a month, elevator.",
    "why": "Under budget with a scan.",
    "chosen_by": "policy",
    "rent_from": 1450,
    "walkup": False,
    "parking": None,
}


REAL = {
    "headline": "The record lists a 1 bed at $1,450 a month; the ad says $1,350.",
    "provenance": "1 of 1 photos are in the scan.",
    "cta_label": "See the real listing",
    "cta_url": "https://example-apts.test",
}


TIMELINE = {
    "case_id": "7Q2M",
    "source": "fixture",
    "mode": "policy",
    "fell_back": False,
    "steps": [
        {
            "step": 0,
            "label": "Read the ad",
            "started_ms": 0,
            "took_ms": 120,
            "result": "1 photo, 1 claim",
            "source": "fixture",
            "by": "code",
        },
        {
            "step": 1,
            "label": "Placed the photos",
            "started_ms": 120,
            "took_ms": 0,
            "result": "photo 1 is in another building",
            "source": "fixture",
            "by": "agent",
        },
    ],
    "todos": [],
    "plan": [],
}


class FakeApi:
    """SNAPBACK's routes, as far as the MCP server uses them. Records every request."""

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []
        self.finder = True
        self.real = True
        self.timeline = False
        self.live = False
        self.post_status = "waiting_for_approval"
        self.status = "done"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        path, method = request.url.path, request.method
        auth = request.headers.get("authorization")
        if "token" in request.url.params:
            return httpx.Response(401, json={"detail": "Send the token in a header."})
        if method == "POST" and path == "/cases":
            return httpx.Response(
                201,
                json={
                    "case_id": "7Q2M",
                    "source": "fixture",
                    "token": WRITE,
                    "read_token": READ,
                    "status": self.post_status,
                    "state": None,
                    "challenge_text": "Please hold up a paper with 4821.",
                    "photos": 1,
                    "screenshots": 0,
                    "injection_noticed": False,
                },
            )
        if method == "POST" and path == "/cases/7Q2M/preferences":
            if auth != f"Bearer {WRITE}":
                return httpx.Response(403, json={"detail": "That token cannot write to this case."})
            return httpx.Response(200, json={"max_rent": json.loads(request.content)["max_rent"]})
        if method == "GET" and path == "/cases/7Q2M/card":
            return httpx.Response(200, json={**CARD, "source": "live"} if self.live else CARD)
        if method == "GET" and path == "/cases/7Q2M":
            return httpx.Response(
                200, json={"case_id": "7Q2M", "source": "fixture", "status": self.status}
            )
        if method == "GET" and path == "/cases/7Q2M/real-listing" and self.real:
            if auth != f"Bearer {READ}":
                return httpx.Response(401, json={"detail": "This needs the case's read token."})
            return httpx.Response(200, json=REAL)
        if method == "GET" and path == "/cases/7Q2M/timeline" and self.timeline:
            if auth != f"Bearer {READ}":
                return httpx.Response(401, json={"detail": "This needs the case's read token."})
            return httpx.Response(200, json=TIMELINE)
        if method == "GET" and path == "/cases/7Q2M/office":
            if auth != f"Bearer {READ}":
                return httpx.Response(401, json={"detail": "This needs the case's read token."})
            return httpx.Response(
                200, json={"domain": "example-apts.test", "guidance": "Call the office yourself."}
            )
        if method == "GET" and path == "/cases/NOPE/card":
            return httpx.Response(404, json={"detail": "No case with that id."})
        if method == "GET" and path == "/cases/7Q2M/walk":
            if auth != f"Bearer {READ}":
                return httpx.Response(401, json={"detail": "This needs the case's read token."})
            return httpx.Response(200, json=WALK)
        if method == "POST" and path == "/cases/7Q2M/tour-draft":
            if auth != f"Bearer {WRITE}":
                return httpx.Response(403, json={"detail": "That token cannot write to this case."})
            return httpx.Response(
                200,
                json={
                    "property_id": "fx-prop-1",
                    "addressee": "Fixture Leasing Co",
                    "text": "Hello, I would like to tour unit 1 this week.",
                    "status": "draft",
                    "sent": False,
                    "source": "fixture",
                },
            )
        if path.startswith("/finder") and not self.finder:
            return httpx.Response(404, json={"detail": "Not Found"})
        if method == "POST" and path == "/finder/sessions":
            return httpx.Response(
                201,
                json={"session_id": "fs-1", "token": FINDER, "source": "fixture", "mode": "policy"},
            )
        if path.startswith("/finder/fs-1/") and request.headers.get("x-finder-token") != FINDER:
            return httpx.Response(401, json={"detail": "This needs the finder token."})
        if method == "POST" and path == "/finder/fs-1/message":
            return httpx.Response(
                200,
                json={
                    "session_id": "fs-1",
                    "source": "fixture",
                    "mode": "policy",
                    "reply": "Here are 1 place under 1,500 with no walk-up.",
                    "reply_by": "policy",
                    "proposals": [PROPOSAL],
                    "picks": [PICK],
                },
            )
        if method == "POST" and path == "/finder/fs-1/proposals/pr-1":
            decision = json.loads(request.content)["decision"]
            status = "accepted" if decision == "accept" else "declined"
            return httpx.Response(200, json={**PROPOSAL, "status": status})
        if method == "POST" and path.startswith("/finder/fs-1/proposals/"):
            return httpx.Response(404, json={"detail": "No proposal with that id."})
        return httpx.Response(500, json={"detail": None})


def photo_host(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/big.jpg":
        return httpx.Response(
            200, headers={"content-type": "image/jpeg"}, content=b"0" * (11 << 20)
        )
    if request.url.path == "/page.html":
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>")
    if request.url.path == "/hop":
        return httpx.Response(302, headers={"location": "http://10.0.0.5/inside.jpg"})
    return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def app(api: FakeApi) -> Snapback:
    return Snapback(
        httpx.Client(base_url="http://api.test", transport=httpx.MockTransport(api)),
        httpx.Client(transport=httpx.MockTransport(photo_host)),
        "http://localhost:5173",
        resolve=lambda host, port: "93.184.216.34" if host == "photos.example" else None,
    )


def call(app: Snapback, *steps: tuple[str, dict[str, Any]]) -> list[Any]:
    """Run the tool calls in order through one MCP client session; return each result."""

    async def run() -> list[Any]:
        async with Client(build_server(app)) as client:
            return [await client.call_tool(name, args) for name, args in steps]

    return asyncio.run(run())


def text_of(result: Any) -> str:
    return " ".join(getattr(block, "text", "") for block in result.content)


def body(result: Any) -> dict[str, Any]:
    assert not result.is_error, text_of(result)
    return json.loads(text_of(result))


def no_secret(result: Any) -> None:
    dumped = text_of(result) + json.dumps(getattr(result, "structured_content", None) or {})
    for secret in SECRETS:
        assert secret not in dumped
        assert secret[:12] not in dumped


# --- the tool list -------------------------------------------------------------------------------


def test_tool_list_and_schemas(app: Snapback) -> None:
    async def run() -> list[Any]:
        async with Client(build_server(app)) as client:
            return (await client.list_tools()).tools

    tools = {t.name: t for t in asyncio.run(run())}
    assert set(tools) == {
        "snapback_check_listing",
        "snapback_get_verdict",
        "snapback_find_places",
        "snapback_accept_preference",
        "snapback_walk_summary",
        "snapback_draft_tour_request",
        "snapback_why",
        "snapback_what_to_do",
    }
    schema = {name: tool.input_schema for name, tool in tools.items()}
    check = schema["snapback_check_listing"]
    assert check["required"] == ["ad_text"]
    assert check["properties"]["photo_urls"]["type"] == "array"
    assert check["properties"]["photo_urls"]["items"] == {"type": "string"}
    assert {"type": "integer"} in check["properties"]["max_rent"]["anyOf"]
    assert schema["snapback_get_verdict"]["required"] == ["case_id"]
    assert schema["snapback_find_places"]["required"] == ["brief"]
    accept = schema["snapback_accept_preference"]
    assert accept["required"] == ["proposal_id", "yes"]
    assert accept["properties"]["yes"]["type"] == "boolean"
    assert schema["snapback_walk_summary"]["required"] == ["case_id"]
    assert schema["snapback_draft_tour_request"]["required"] == ["case_id", "place_id"]
    for tool in tools.values():
        assert tool.description and len(tool.description) > 80
    assert "explicitly" in tools["snapback_accept_preference"].description
    assert "never by a" in tools["snapback_get_verdict"].description
    assert "nothing is ever sent" in tools["snapback_draft_tour_request"].description


# --- check_listing -------------------------------------------------------------------------------


def test_check_listing_creates_a_case_and_keeps_the_tokens(app: Snapback, api: FakeApi) -> None:
    [result] = call(
        app,
        (
            "snapback_check_listing",
            {
                "ad_text": "1 bed, $1,400. Zelle the deposit today.",
                "photo_urls": ["https://photos.example/a.jpg"],
                "max_rent": 1500,
            },
        ),
    )
    out = body(result)
    no_secret(result)
    assert out["case_id"] == "7Q2M"
    assert out["source"] == "FIXTURE"
    assert out["status"] == "waiting_for_approval"
    assert out["read_token"] == TOKEN_HELD
    assert out["result_url"] == "http://localhost:5173/case/7Q2M"
    assert out["challenge_drafted"] is True
    assert "1500" in out["budget"]
    assert out["next_action"]
    assert app.vault.read_tokens["7Q2M"] == READ
    made = next(r for r in api.seen if r.url.path == "/cases")
    assert b"Zelle the deposit" in made.content and JPEG in made.content
    prefs = next(r for r in api.seen if r.url.path.endswith("/preferences"))
    assert prefs.headers["authorization"] == f"Bearer {WRITE}"
    assert all("token" not in r.url.params for r in api.seen)


def test_check_listing_refuses_private_and_bad_photos(app: Snapback) -> None:
    results = call(
        app,
        ("snapback_check_listing", {"ad_text": "ad", "photo_urls": ["http://10.0.0.5/a.jpg"]}),
        ("snapback_check_listing", {"ad_text": "ad", "photo_urls": ["file:///etc/passwd"]}),
        (
            "snapback_check_listing",
            {"ad_text": "ad", "photo_urls": ["https://photos.example/page.html"]},
        ),
        (
            "snapback_check_listing",
            {"ad_text": "ad", "photo_urls": ["https://photos.example/big.jpg"]},
        ),
        ("snapback_check_listing", {"ad_text": "ad", "photo_urls": ["https://photos.example/hop"]}),
        ("snapback_check_listing", {"ad_text": "   "}),
    )
    words = [text_of(r) for r in results]
    assert all(r.is_error for r in results)
    assert "private or unknown address" in words[0]
    assert "not an http or https link" in words[1]
    assert "not an image" in words[2]
    assert "over 10 MB" in words[3]
    assert "private or unknown address" in words[4]  # the redirect target is vetted too
    assert "Give the listing's text" in words[5]


# --- get_verdict --------------------------------------------------------------------------------


def test_get_verdict_returns_the_card_lines(app: Snapback) -> None:
    [result] = call(app, ("snapback_get_verdict", {"case_id": "7Q2M"}))
    out = body(result)
    assert out["source"] == "FIXTURE"
    assert out["verdict"] == "Don't pay. Something here doesn't match."
    assert "code" in out["verdict_set_by"]
    assert out["checks"][0] == {
        "row": "PLACE",
        "check": "Here now",
        "status": "Doesn't match",
        "says": "Photo 1 was taken elsewhere.",
        "source": "FIXTURE",
    }
    assert out["checks"][1]["status"] == "Warning"  # a red flag on PRICE is a warning
    assert out["checks"][1]["source"] == "LIVE"
    assert out["not_checked"] == ["ID", "lease", "ownership"]
    assert out["next_action"].startswith("Do not send money")
    assert "scam" not in json.dumps(out).lower()


def test_check_listing_returns_the_proof_and_the_real_listing_link(
    app: Snapback, api: FakeApi
) -> None:
    api.post_status = "done"
    [result] = call(app, ("snapback_check_listing", {"ad_text": "1 bed, Zelle today"}))
    out = body(result)
    assert out["case_id"] == "7Q2M"
    assert out["summary"][0] == "Photo 1 was taken in a different building."
    assert out["checks_out"] == ["Rent: close to the record."]
    assert out["does_not"] == ["Here now: Photo 1 was taken elsewhere."]
    assert out["real_listing"]["link"] == "https://example-apts.test"
    assert out["source"] == "FIXTURE"
    no_secret(result)


def test_no_real_listing_link_when_the_api_has_none(app: Snapback, api: FakeApi) -> None:
    api.real = False
    api.post_status = "done"
    [result] = call(app, ("snapback_check_listing", {"ad_text": "1 bed, Zelle today"}))
    assert body(result)["real_listing"] is None


def test_why_gives_reasons_and_steps_when_the_api_has_them(app: Snapback, api: FakeApi) -> None:
    api.timeline = True
    [made, result] = call(
        app,
        ("snapback_check_listing", {"ad_text": "1 bed"}),
        ("snapback_why", {"case_id": "7Q2M"}),
    )
    out = body(result)
    assert out["reasons"] == CARD["summary"]
    assert out["steps"] == [
        "Read the ad - 1 photo, 1 claim",
        "Placed the photos - photo 1 is in another building",
    ]
    assert any(
        r.url.path == "/cases/7Q2M/timeline" and r.headers["authorization"] == f"Bearer {READ}"
        for r in api.seen
    )
    assert out["verdict_set_by"].startswith("code")
    no_secret(result)


def test_why_survives_a_missing_timeline(app: Snapback) -> None:
    [result] = call(app, ("snapback_why", {"case_id": "7Q2M"}))
    out = body(result)
    assert out["steps"] is None
    assert out["steps_note"]
    assert out["reasons"] == CARD["summary"]


def test_what_to_do_relays_the_apis_words(app: Snapback) -> None:
    [_, result] = call(
        app,
        ("snapback_check_listing", {"ad_text": "1 bed"}),
        ("snapback_what_to_do", {"case_id": "7Q2M"}),
    )
    out = body(result)
    assert out["next_steps"] == CARD["footer"]
    assert out["office_on_record"] == "Call the office yourself."
    assert out["real_listing_link"] == "https://example-apts.test"
    assert out["next_action"].startswith("Do not send money")
    no_secret(result)


def test_what_to_do_for_a_case_this_server_did_not_start(app: Snapback) -> None:
    [result] = call(app, ("snapback_what_to_do", {"case_id": "7Q2M"}))
    out = body(result)
    assert out["office_on_record"] is None  # no token held, so no office read
    assert out["next_steps"] == CARD["footer"]


def test_a_live_case_passes_no_record_figures_and_no_link(app: Snapback, api: FakeApi) -> None:
    api.live = True
    api.post_status = "done"
    [made, verdict] = call(
        app,
        ("snapback_check_listing", {"ad_text": "1 bed"}),
        ("snapback_get_verdict", {"case_id": "7Q2M"}),
    )
    for result in (made, verdict):
        out = body(result)
        assert out["real_listing"] == {"provenance": REAL["provenance"]}
        dumped = text_of(result)
        assert "$1,450" not in dumped
        assert "example-apts.test" not in dumped
    [again] = call(app, ("snapback_what_to_do", {"case_id": "7Q2M"}))
    assert body(again)["real_listing_link"] is None


def test_proof_fields_wait_until_the_case_is_done(app: Snapback, api: FakeApi) -> None:
    api.status = "waiting_for_approval"
    [result] = call(app, ("snapback_get_verdict", {"case_id": "7Q2M"}))
    out = body(result)
    assert out["summary"] is None and out["real_listing"] is None
    assert out["checks_out"] is None and out["does_not"] is None


def test_why_and_what_to_do_say_plain_errors(app: Snapback) -> None:
    for name in ("snapback_why", "snapback_what_to_do"):
        [result] = call(app, (name, {"case_id": "NOPE"}))
        assert result.is_error
        assert text_of(result) == "No case with that id."


# --- find_places and accept_preference ----------------------------------------------------------


def test_find_places_then_accept(app: Snapback, api: FakeApi) -> None:
    first, second, yes, no = call(
        app,
        ("snapback_find_places", {"brief": "1 bed under 1500, no walk-ups"}),
        ("snapback_find_places", {"brief": "and near a park"}),
        ("snapback_accept_preference", {"proposal_id": "pr-1", "yes": True}),
        ("snapback_accept_preference", {"proposal_id": "pr-1", "yes": False}),
    )
    for result in (first, second, yes, no):
        no_secret(result)
    out = body(first)
    assert out["session"] == "started" and body(second)["session"] == "continued"
    assert out["source"] == "FIXTURE"
    assert out["needs_renter_yes"] is True
    assert out["proposals"][0]["proposal_id"] == "pr-1"
    assert out["proposals"][0]["question"] == "Skip walk-ups from now on?"
    assert out["picks"][0]["place_id"] == "fx-prop-1"
    assert out["picks"][0]["walk_it_first_url"] == "http://localhost:5173/tour/fx-prop-1"
    assert body(yes)["status"] == "accepted" and body(yes)["source"] == "FIXTURE"
    assert body(no)["status"] == "declined"
    sessions = [r for r in api.seen if r.url.path == "/finder/sessions"]
    assert len(sessions) == 1
    decisions = [json.loads(r.content) for r in api.seen if "/proposals/" in r.url.path]
    assert decisions == [{"decision": "accept"}, {"decision": "decline"}]
    assert all(
        r.headers["x-finder-token"] == FINDER
        for r in api.seen
        if r.url.path.startswith("/finder/fs-1")
    )


@pytest.mark.parametrize("value", ["yes", "true", 1, None])
def test_accept_preference_needs_a_real_boolean(app: Snapback, api: FakeApi, value: Any) -> None:
    _, result = call(
        app,
        ("snapback_find_places", {"brief": "1 bed"}),
        ("snapback_accept_preference", {"proposal_id": "pr-1", "yes": value}),
    )
    assert result.is_error
    assert not [r for r in api.seen if "/proposals/" in r.url.path]


def test_accept_preference_without_yes_is_refused(app: Snapback, api: FakeApi) -> None:
    [result] = call(app, ("snapback_accept_preference", {"proposal_id": "pr-1"}))
    assert result.is_error
    assert not [r for r in api.seen if "/proposals/" in r.url.path]


def test_accept_before_any_finder_session(app: Snapback) -> None:
    [result] = call(app, ("snapback_accept_preference", {"proposal_id": "pr-1", "yes": True}))
    assert result.is_error
    assert text_of(result) == "There is no Finder session yet. Call snapback_find_places first."


def test_find_places_on_an_api_without_the_finder(app: Snapback, api: FakeApi) -> None:
    api.finder = False
    [result] = call(app, ("snapback_find_places", {"brief": "1 bed"}))
    assert result.is_error
    assert "has no Finder yet" in text_of(result)


# --- walk_summary and the tour draft ------------------------------------------------------------


def test_walk_summary(app: Snapback, api: FakeApi) -> None:
    _, result = call(
        app,
        ("snapback_check_listing", {"ad_text": "1 bed, $1,400."}),
        ("snapback_walk_summary", {"case_id": "7Q2M"}),
    )
    out = body(result)
    no_secret(result)
    assert out["source"] == "FIXTURE"
    assert [room["room"] for room in out["rooms"]] == ["Kitchen", "Bedroom"]
    assert out["rooms"][0]["ad_photos_here"] == ["P1"]
    assert out["ad_photos"] == [
        {"photo": "P1", "where": "placed in the home the ad claims", "room": "Kitchen"},
        {"photo": "P2", "where": "taken in a different property", "room": None},
    ]
    assert out["coverage"] == "1 of 2 rooms."
    assert out["walk_it_first_url"] == "http://localhost:5173/tour/fx-prop-1?case=7Q2M"
    dumped = json.dumps(out)
    for raw in ("SWEEP-SECRET", "MODEL-SECRET", "812", "position", "fx-2"):
        assert raw not in dumped  # scan internals and other buildings stay in the API
    walk = next(r for r in api.seen if r.url.path.endswith("/walk"))
    assert walk.headers["authorization"] == f"Bearer {READ}"


def test_walk_summary_for_a_case_this_server_did_not_start(app: Snapback) -> None:
    [result] = call(app, ("snapback_walk_summary", {"case_id": "ZZZZ"}))
    assert result.is_error
    assert "did not start case ZZZZ" in text_of(result)


def test_draft_tour_request_is_draft_only(app: Snapback) -> None:
    _, result = call(
        app,
        ("snapback_check_listing", {"ad_text": "1 bed, $1,400."}),
        ("snapback_draft_tour_request", {"case_id": "7Q2M", "place_id": "fx-prop-1"}),
    )
    out = body(result)
    no_secret(result)
    assert out["sent"] is False and out["status"] == "draft"
    assert out["to"] == "Fixture Leasing Co"
    assert out["source"] == "FIXTURE"


# --- errors are plain sentences -----------------------------------------------------------------


def test_api_errors_come_back_as_plain_sentences(app: Snapback) -> None:
    [result] = call(app, ("snapback_get_verdict", {"case_id": "NOPE"}))
    assert result.is_error
    assert text_of(result) == "No case with that id."


def test_unreachable_api_is_a_plain_sentence() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    app = Snapback(
        httpx.Client(base_url="http://api.test", transport=httpx.MockTransport(down)),
        httpx.Client(transport=httpx.MockTransport(photo_host)),
        "http://localhost:5173",
    )
    [result] = call(app, ("snapback_get_verdict", {"case_id": "7Q2M"}))
    assert result.is_error
    assert text_of(result) == (
        "SNAPBACK's API is not reachable at http://api.test. Start it with `make api`."
    )


def test_status_without_a_detail_gets_a_plain_sentence(app: Snapback, api: FakeApi) -> None:
    [result] = call(app, ("snapback_get_verdict", {"case_id": "BOOM"}))
    assert result.is_error
    assert text_of(result) == "SNAPBACK's API failed (HTTP 500). Try again."
    assert "Traceback" not in text_of(result)


def test_bad_arguments_get_a_plain_sentence(app: Snapback) -> None:
    accept, verdict = call(
        app,
        ("snapback_accept_preference", {"proposal_id": "pr-1", "yes": "true"}),
        ("snapback_get_verdict", {}),
    )
    assert accept.is_error and verdict.is_error
    assert text_of(accept).startswith("snapback_accept_preference needs a proposal_id and yes")
    for result in (accept, verdict):
        assert "pydantic" not in text_of(result) and "Error executing" not in text_of(result)


def test_http_mode_needs_its_bearer_token(app: Snapback) -> None:
    from snapback.mcp_server import BearerGate

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    gate = BearerGate(inner, "local-run-token")

    async def run() -> list[int]:
        transport = httpx.ASGITransport(app=gate)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as c:
            return [
                (await c.post("/mcp")).status_code,
                (await c.post("/mcp", headers={"Authorization": "Bearer wrong"})).status_code,
                (
                    await c.post("/mcp", headers={"Authorization": "Bearer local-run-token"})
                ).status_code,
            ]

    assert asyncio.run(run()) == [401, 401, 200]


# --- photo fetches cannot be rebound to a private address ---------------------------------------


def answers(*addresses: str):
    """A stand-in for socket.getaddrinfo that gives each lookup the next address in turn."""
    queue = list(addresses)
    calls: list[str] = []

    def getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any) -> list[Any]:
        calls.append(host)
        ip = queue.pop(0) if len(queue) > 1 else queue[0]
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]

    return getaddrinfo, calls


def real_resolver_app(seen: list[httpx.Request]) -> Snapback:
    def host(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/hop":
            return httpx.Response(302, headers={"location": "/second.jpg"})
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)

    return Snapback(  # the real vetted_address, the default
        httpx.Client(base_url="http://api.test", transport=httpx.MockTransport(FakeApi())),
        httpx.Client(transport=httpx.MockTransport(host)),
        "http://localhost:5173",
    )


def test_a_rebinding_name_is_fetched_from_the_address_that_was_vetted(monkeypatch) -> None:
    # The first lookup says public, every later one says localhost: the fetch must still go
    # to the public address, with the name only in the Host header and SNI.
    lookup, calls = answers("93.184.216.34", "127.0.0.1")
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    seen: list[httpx.Request] = []
    name, data, kind = real_resolver_app(seen).fetch_photo("https://rebind.example/a.jpg?w=2", 1)
    assert data == JPEG and kind == "image/jpeg"
    assert calls == ["rebind.example"]  # resolved once
    [request] = seen
    assert str(request.url) == "https://93.184.216.34/a.jpg?w=2"  # port 443, normalised away
    assert request.headers["host"] == "rebind.example"
    assert request.extensions["sni_hostname"] == "rebind.example"  # TLS checks the name


def test_each_redirect_hop_is_resolved_and_vetted_again(monkeypatch) -> None:
    lookup, calls = answers("93.184.216.34", "127.0.0.1")
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    seen: list[httpx.Request] = []
    with pytest.raises(Exception, match="private or unknown address"):
        real_resolver_app(seen).fetch_photo("http://rebind.example/hop", 1)
    assert calls == ["rebind.example", "rebind.example"]
    assert [r.url.host for r in seen] == ["93.184.216.34"]  # localhost was never reached


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "169.254.169.254",
        "::1",
        "::ffff:127.0.0.1",
        "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
        "2002:7f00:1::1",  # 6to4 of 127.0.0.1
        "::7f00:1",  # IPv4-compatible 127.0.0.1
        "64:ff9b:1::7f00:1",  # local-use NAT64
        "fec0::1",  # site-local
    ],
)
def test_private_and_tunnelled_addresses_are_refused(monkeypatch, address: str) -> None:
    lookup, _ = answers(address)
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    assert vetted_address("photos.example", 443) is None


def test_a_name_with_any_private_answer_is_refused(monkeypatch) -> None:
    def mixed(host: str, port: Any, *args: Any, **kwargs: Any) -> list[Any]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", mixed)
    assert vetted_address("photos.example", 443) is None


def test_a_public_address_is_kept(monkeypatch) -> None:
    lookup, _ = answers("2606:2800:220:1:248:1893:25c8:1946")
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    assert vetted_address("photos.example", 443) == "2606:2800:220:1:248:1893:25c8:1946"


def recording_app(seen: list[httpx.Request], address: str) -> Snapback:
    def host(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)

    return Snapback(
        httpx.Client(base_url="http://api.test", transport=httpx.MockTransport(FakeApi())),
        httpx.Client(transport=httpx.MockTransport(host)),
        "http://localhost:5173",
        resolve=lambda name, port: address,
    )


def test_an_ipv6_address_is_bracketed_and_the_name_kept() -> None:
    seen: list[httpx.Request] = []
    recording_app(seen, "2606:4700::1").fetch_photo("https://photos.example/a.jpg", 1)
    [request] = seen
    assert str(request.url) == "https://[2606:4700::1]/a.jpg"
    assert request.headers["host"] == "photos.example"
    assert request.extensions["sni_hostname"] == "photos.example"


def test_an_international_name_goes_out_as_punycode() -> None:
    seen: list[httpx.Request] = []
    asked: list[str] = []
    app = recording_app(seen, "93.184.216.34")
    app.resolve = lambda name, port: asked.append(name) or "93.184.216.34"
    app.fetch_photo("https://bücher.test:8443/a.jpg", 1)
    [request] = seen
    assert asked == ["xn--bcher-kva.test"]
    assert request.headers["host"] == "xn--bcher-kva.test:8443"
    assert request.extensions["sni_hostname"] == "xn--bcher-kva.test"


def test_a_name_idna_cannot_encode_is_a_plain_refusal() -> None:
    app = recording_app([], "93.184.216.34")
    with pytest.raises(Exception, match="not an http or https link"):
        app.fetch_photo("https://" + "a" * 70 + ".test/a.jpg", 1)  # a label over 63 characters


def test_two_names_on_one_address_never_share_a_tls_connection(tmp_path) -> None:
    """A keep-alive HTTP/1.1 TLS server on 127.0.0.1 with a certificate for photos.test only.
    The second name must open its own connection and fail its own certificate check."""
    import datetime
    import ssl
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "photos.test")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("photos.test")]), False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    class Photo(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # keep-alive by default

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(JPEG)))
            self.end_headers()
            self.wfile.write(JPEG)

        def log_message(self, *args: Any) -> None:
            pass

    connections: list[Any] = []

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def get_request(self) -> Any:
            sock, address = self.socket.accept()
            connections.append(address)  # counted before the handshake, which may fail
            return context.wrap_socket(sock, server_side=True), address

    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(cert_file, key_file)
    server = Server(("127.0.0.1", 0), Photo)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        trust = ssl.create_default_context(cafile=str(cert_file))
        app = Snapback(
            httpx.Client(base_url="http://api.test", transport=httpx.MockTransport(FakeApi())),
            photo_client(verify=trust),
            "http://localhost:5173",
            resolve=lambda host, p: "127.0.0.1",
        )
        assert app.fetch_photo(f"https://photos.test:{port}/a.jpg", 1)[1] == JPEG
        with pytest.raises(Exception, match="could not be downloaded"):
            app.fetch_photo(f"https://wrong.test:{port}/a.jpg", 2)
        assert len(connections) == 2  # the first, verified session was not reused
    finally:
        server.shutdown()
        server.server_close()
