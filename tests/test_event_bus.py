"""M3 (plan/map-plan.md, conductor on #8): the event bus, its log and the stream.

An event says that something happened to a place, a renter's session or the pipeline. It
carries only the keys its kind allows, and it always says where it came from: the renter, our
own pipeline, or a script. The kit is a snapshot, so a change to a record is never anything
but SIMULATED.

Everything here is made up.
"""

import json
import threading
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from snapback.api.main import create_app
from snapback.events import (
    PAYLOAD_KEYS,
    Event,
    EventBus,
    EventKind,
    EventRefused,
    EventSource,
    new_event,
)
from snapback.settings import Settings

AT = datetime(2026, 11, 14, 13, 0, tzinfo=UTC)
TOKEN = "fx-events-token-0123456789"


def match(**payload) -> dict:
    return {
        "kind": EventKind.MATCH_FOUND,
        "source": EventSource.PIPELINE,
        "subject": "fx-place-1",
    } | {"payload": {"session": "fx-sess-1", "fits_brief": True} | payload}


def bus(tmp_path) -> EventBus:
    return EventBus(tmp_path / "events" / "log.jsonl")


# --- an event carries only what its kind allows ----------------------------------------------


def test_every_kind_has_an_allow_list():
    assert set(PAYLOAD_KEYS) == set(EventKind)


def test_an_event_keeps_its_allowed_keys_and_says_where_it_came_from():
    event = new_event(**match(), at=AT)
    assert isinstance(event, Event)
    assert (event.kind, event.source, event.subject) == (
        EventKind.MATCH_FOUND,
        EventSource.PIPELINE,
        "fx-place-1",
    )
    assert event.payload == {"session": "fx-sess-1", "fits_brief": True}
    assert event.at == AT and event.id == ""  # the bus numbers it


@pytest.mark.parametrize(
    "payload",
    [
        {"address": "1 Fixture Lane"},
        {"office": "Fixture Living LLC"},
        {"phone": "555-0100"},
        {"note": "anything at all"},
    ],
)
def test_a_key_that_is_not_on_the_list_is_refused(payload):
    with pytest.raises(EventRefused):
        new_event(**match(**payload))


@pytest.mark.parametrize(
    "value",
    [{"nested": 1}, ["a", "list"], b"bytes", "x" * 201, float("nan")],
)
def test_a_value_that_is_not_a_short_plain_one_is_refused(value):
    with pytest.raises(EventRefused):
        new_event(**match(fits_brief=value))


def test_a_subject_is_a_short_id_and_nothing_else():
    for subject in ("", "x" * 81, "1 Fixture Lane, Houston", "a b"):
        with pytest.raises(EventRefused):
            new_event(**(match() | {"subject": subject}))


# --- the honesty rule: the kit is a snapshot -------------------------------------------------


@pytest.mark.parametrize("source", [EventSource.PIPELINE, EventSource.RENTER])
def test_a_record_change_is_never_anything_but_simulated(source):
    with pytest.raises(EventRefused):
        new_event(
            kind=EventKind.PLACE_RECORD_CHANGED,
            source=source,
            subject="fx-place-1",
            payload={"field": "rent_from"},
        )
    kept = new_event(
        kind=EventKind.PLACE_RECORD_CHANGED,
        source=EventSource.SIMULATED,
        subject="fx-place-1",
        payload={"field": "rent_from"},
    )
    assert kept.source is EventSource.SIMULATED


@pytest.mark.parametrize("words", ["Available now", "available  NOW", "it is available right now"])
def test_no_event_says_a_place_is_available_now(words):
    with pytest.raises(EventRefused):
        new_event(
            kind=EventKind.PLACE_RECORD_CHANGED,
            source=EventSource.SIMULATED,
            subject="fx-place-1",
            payload={"field": words},
        )


# --- the bus: numbered, logged, and handed to whoever listens --------------------------------


def test_events_are_numbered_in_order_and_appended_to_the_log(tmp_path):
    events = bus(tmp_path)
    first = events.publish(new_event(**match(), at=AT))
    second = events.publish(new_event(**match(fits_brief=False), at=AT))
    assert (first.id, second.id) == ("ev-000001", "ev-000002")
    lines = (tmp_path / "events" / "log.jsonl").read_text().splitlines()
    assert [json.loads(line)["id"] for line in lines] == ["ev-000001", "ev-000002"]
    assert json.loads(lines[0])["source"] == "pipeline"
    assert events.after(0) == [first, second]
    assert events.after(1) == [second]


def test_the_log_is_only_ever_appended_to_and_the_count_survives_a_restart(tmp_path):
    first = bus(tmp_path)
    first.publish(new_event(**match(), at=AT))
    before = (tmp_path / "events" / "log.jsonl").read_text()
    again = bus(tmp_path)  # a new process reading the same log
    third = again.publish(new_event(**match(), at=AT))
    assert third.id == "ev-000002"
    assert (tmp_path / "events" / "log.jsonl").read_text().startswith(before)
    assert [event.id for event in again.after(0)] == ["ev-000001", "ev-000002"]


def test_a_subscriber_hears_its_kinds_and_can_stop_listening(tmp_path):
    events = bus(tmp_path)
    heard, all_heard = [], []
    stop = events.subscribe(heard.append, kinds={EventKind.MATCH_FOUND})
    events.subscribe(all_heard.append)
    events.publish(new_event(**match(), at=AT))
    events.publish(
        new_event(
            kind=EventKind.CASE_CREATED, source=EventSource.PIPELINE, subject="fx-7Q2M", payload={}
        )
    )
    assert [event.kind for event in heard] == [EventKind.MATCH_FOUND]
    assert len(all_heard) == 2
    stop()
    events.publish(new_event(**match(), at=AT))
    assert len(heard) == 1 and len(all_heard) == 3


def test_a_subscriber_that_breaks_stops_nothing(tmp_path):
    events = bus(tmp_path)
    heard = []

    def broken(event):
        raise RuntimeError("fx: a subscriber failed")

    events.subscribe(broken)
    events.subscribe(heard.append)
    kept = events.publish(new_event(**match(), at=AT))
    assert heard == [kept] and events.after(0) == [kept]


def test_events_published_from_many_threads_get_distinct_numbers(tmp_path):
    events = bus(tmp_path)
    threads = [
        threading.Thread(target=lambda: events.publish(new_event(**match(), at=AT)))
        for _ in range(40)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    ids = [event.id for event in events.after(0)]
    assert ids == sorted(ids) and len(set(ids)) == 40
    assert len((tmp_path / "events" / "log.jsonl").read_text().splitlines()) == 40


def test_an_event_that_was_already_numbered_is_refused(tmp_path):
    events = bus(tmp_path)
    kept = events.publish(new_event(**match(), at=AT))
    with pytest.raises(EventRefused):
        events.publish(kept)


def test_a_broken_line_in_the_log_is_skipped_not_fatal(tmp_path):
    events = bus(tmp_path)
    events.publish(new_event(**match(), at=AT))
    with (tmp_path / "events" / "log.jsonl").open("a") as log:
        log.write("not json\n")
    again = bus(tmp_path)
    assert [event.id for event in again.after(0)] == ["ev-000001"]
    assert again.publish(new_event(**match(), at=AT)).id == "ev-000003"  # never reuses a line


# --- the stream: a header token, never the address -------------------------------------------


def client_for(tmp_path, token: str | None = TOKEN) -> TestClient:
    settings = Settings(snapback_data_dir=tmp_path, snapback_events_token=token)
    return TestClient(create_app(settings))


def read_stream(client: TestClient, headers: dict, stop_after: int) -> list[dict]:
    seen = []
    with client.stream("GET", "/events/stream?follow=false", headers=headers) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data: "):
                seen.append(json.loads(line[6:]))
                if len(seen) == stop_after:
                    break
    return seen


def test_the_stream_gives_every_event_in_order_with_its_number_as_the_id(tmp_path):
    client = client_for(tmp_path)
    events = client.app.state.events
    events.publish(new_event(**match(), at=AT))
    events.publish(new_event(**match(fits_brief=False), at=AT))
    seen = read_stream(client, {"Authorization": f"Bearer {TOKEN}"}, 2)
    assert [item["id"] for item in seen] == ["ev-000001", "ev-000002"]
    assert seen[0]["source"] == "pipeline" and seen[0]["payload"]["fits_brief"] is True


def test_the_stream_resumes_after_the_last_event_the_client_has(tmp_path):
    client = client_for(tmp_path)
    events = client.app.state.events
    for _ in range(3):
        events.publish(new_event(**match(), at=AT))
    headers = {"X-Events-Token": TOKEN, "Last-Event-ID": "ev-000002"}
    assert [item["id"] for item in read_stream(client, headers, 1)] == ["ev-000003"]


@pytest.mark.parametrize(
    "headers, address, status",
    [
        ({}, "/events/stream", 401),
        ({"Authorization": "Bearer wrong"}, "/events/stream", 403),
        ({"Authorization": f"Bearer {TOKEN}"}, f"/events/stream?token={TOKEN}", 401),
        ({}, f"/events/stream?token={TOKEN}", 401),
    ],
)
def test_the_stream_needs_the_token_in_a_header_and_never_in_the_address(
    tmp_path, headers, address, status
):
    assert client_for(tmp_path).get(address, headers=headers).status_code == status


def test_with_no_token_configured_the_stream_is_closed_to_everyone(tmp_path):
    client = client_for(tmp_path, token=None)
    assert client.get("/events/stream", headers={"Authorization": "Bearer "}).status_code == 401
    assert client.get("/events/stream", headers={"Authorization": "Bearer x"}).status_code == 403


# --- review of #226: checked however an event is made, values as well as keys ----------------


def test_an_event_built_by_hand_is_checked_too():
    with pytest.raises(ValueError):
        Event(
            kind=EventKind.MATCH_FOUND,
            at=AT,
            source=EventSource.PIPELINE,
            subject="fx-place-1",
            payload={"address": "1 Fixture Lane", "phone": "555-0100"},
        )


def test_an_event_read_back_from_json_is_checked_too():
    line = json.dumps(
        {
            "kind": "match_found",
            "at": AT.isoformat(),
            "source": "pipeline",
            "subject": "fx-place-1",
            "payload": {"address": "1 Fixture Lane"},
        }
    )
    with pytest.raises(ValueError):
        Event.model_validate_json(line)


def test_publish_refuses_an_event_whose_payload_was_changed_after_it_was_built(tmp_path):
    events = bus(tmp_path)
    event = new_event(**match(), at=AT)
    event.payload["address"] = "1 Fixture Lane"
    with pytest.raises(EventRefused):
        events.publish(event)
    assert events.after(0) == []
    assert not (tmp_path / "events" / "log.jsonl").exists()


@pytest.mark.parametrize(
    "kind, source, payload",
    [
        (EventKind.SESSION_STARTED, EventSource.RENTER, {"lang": "1 Fixture Lane, call 555-0100"}),
        (EventKind.SESSION_STARTED, EventSource.RENTER, {"lang": "fr"}),
        (EventKind.WATCH_ADDED, EventSource.RENTER, {"session": "7135550100", "kind": "place"}),
        (EventKind.WATCH_ADDED, EventSource.RENTER, {"session": "fx-sess-1", "kind": "anything"}),
        (EventKind.MATCH_FOUND, EventSource.PIPELINE, {"fits_brief": "yes"}),
        (EventKind.MATCH_FOUND, EventSource.PIPELINE, {"has_scan": 1}),
        (EventKind.MATCH_FOUND, EventSource.PIPELINE, {"rent_from": "1100"}),
        (EventKind.MATCH_FOUND, EventSource.PIPELINE, {"rent_from": -5}),
        (EventKind.MATCH_FOUND, EventSource.PIPELINE, {"rent_from": True}),
        (EventKind.MATCH_FOUND, EventSource.PIPELINE, {"rent_from": None}),
        (EventKind.PLACE_RECORD_CHANGED, EventSource.SIMULATED, {"field": "owner_name"}),
        (EventKind.INDEX_WARMED, EventSource.PIPELINE, {"twins": 2.5}),
        (EventKind.CASE_CREATED, EventSource.PIPELINE, {"data_source": "kit"}),
        (EventKind.AERIAL_CACHED, EventSource.PIPELINE, {"direction": "up"}),
    ],
)
def test_a_value_is_one_of_a_few_words_a_number_a_yes_or_no_or_an_id(kind, source, payload):
    with pytest.raises(EventRefused):
        new_event(kind=kind, source=source, subject="fx-place-1", payload=payload)


@pytest.mark.parametrize(
    "kind, source, payload",
    [
        (EventKind.SESSION_STARTED, EventSource.RENTER, {"lang": "es"}),
        (EventKind.WATCH_ADDED, EventSource.RENTER, {"session": "fx-sess-1", "kind": "brief"}),
        (EventKind.MATCH_FOUND, EventSource.PIPELINE, {"rent_from": 1100, "has_scan": True}),
        (EventKind.PLACE_RECORD_CHANGED, EventSource.SIMULATED, {"field": "units_reported"}),
        (EventKind.INDEX_WARMED, EventSource.PIPELINE, {"twins": 21, "views": 21528}),
        (EventKind.CASE_CREATED, EventSource.PIPELINE, {"data_source": "fixture"}),
        (EventKind.AERIAL_CACHED, EventSource.PIPELINE, {"direction": "nadir"}),
    ],
)
def test_every_kind_takes_its_own_values(kind, source, payload):
    assert (
        new_event(kind=kind, source=source, subject="fx-place-1", payload=payload).payload
        == payload
    )


@pytest.mark.parametrize("subject", ["7135550100", "77002", "555-0100", "1.5"])
def test_a_subject_made_only_of_digits_is_refused(subject):
    with pytest.raises(EventRefused):
        new_event(**(match() | {"subject": subject}))


def test_half_a_line_left_by_a_crash_does_not_swallow_the_next_event(tmp_path):
    events = bus(tmp_path)
    events.publish(new_event(**match(), at=AT))
    path = tmp_path / "events" / "log.jsonl"
    with path.open("a") as log:
        log.write('{"id": "ev-000002", "kind": "match_fo')  # no newline: the write was cut off
    again = bus(tmp_path)
    kept = again.publish(new_event(**match(), at=AT))
    assert kept.id == "ev-000003"
    lines = path.read_text().splitlines()
    assert len(lines) == 3 and json.loads(lines[2])["id"] == "ev-000003"
    assert [event.id for event in bus(tmp_path).after(0)] == ["ev-000001", "ev-000003"]
