"""The finder's routes (M9): a session, a message, the state, and the renter's yes or no.

    POST /finder/sessions                       a new session: its id and write token (shown once)
    POST /finder/{session}/message              signals and/or text in; reply, proposals, picks out
    GET  /finder/{session}/state                applied and proposed prefs, picks, notes, trace
    POST /finder/{session}/proposals/{id}       {"decision": "accept" | "decline"}
    POST /finder/{session}/watch                {"channel": "imessage"}: watch this session's brief

The token goes in `Authorization: Bearer` or `X-Finder-Token`, never in the address. Nothing a
sub-agent proposes applies until the accept route runs. Sessions live in `finder.SESSIONS`, so
other routes can look one up and check its token with `SESSIONS.get(sid, token)`.
"""

from __future__ import annotations

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request

from snapback.agent.finder import (
    SESSIONS,
    FinderAccess,
    FinderBusy,
    FinderSession,
    SessionStore,
    load_fixture_places,
    read_text,
    run_turn,
)
from snapback.api.limits import DailyLimit, PerMinuteLimit
from snapback.contracts import (
    FinderDecision,
    FinderMessageRequest,
    FinderProposal,
    FinderReply,
    FinderSessionStarted,
    FinderState,
    FinderWatchRequest,
    FinderWatchStatus,
)
from snapback.events import EventBus

MESSAGE_PER_MINUTE = 20
MODEL_TURNS_PER_DAY = 40  # turns that call a model, per address per day; policy turns are free


def make_router(
    events: EventBus,
    model: Any = None,
    places: Any = None,
    *,
    store: SessionStore = SESSIONS,
    model_turns_per_day: int = MODEL_TURNS_PER_DAY,
) -> APIRouter:
    """`model`: a chat model for deepagents mode, or None for the policy. `places`: a function
    returning the researched places (the M1 feed); the fixture places by default. `store`: where
    sessions live, shared with every other route that needs one."""
    router = APIRouter()
    limit = PerMinuteLimit(MESSAGE_PER_MINUTE)
    model_turns = DailyLimit(model_turns_per_day)

    def token_of(authorization: str | None, header: str | None) -> str | None:
        if authorization and authorization.lower().startswith("bearer "):
            return authorization[7:].strip()
        return header

    def find(
        request: Request, session_id: str, authorization: str | None, header: str | None
    ) -> FinderSession:
        if "token" in request.query_params:
            raise HTTPException(
                status_code=401, detail="Send the finder token in a header, not in the address."
            )
        try:
            return store.get(session_id, token_of(authorization, header))
        except FinderAccess as refused:
            raise HTTPException(status_code=refused.status, detail=refused.detail) from None

    @router.post("/finder/sessions", status_code=201)
    def start(request: Request) -> FinderSessionStarted:
        """A new finder session; shows LIVE or FIXTURE and the mode (policy or deepagents)."""
        address = request.client.host if request.client else "unknown"
        if not limit.allow(f"new:{address}"):
            raise HTTPException(status_code=429, detail="Too many sessions. Try again in a minute.")
        found = places() if places else load_fixture_places()
        session = store.add(FinderSession(f"fs-{secrets.token_hex(4)}", events, found, model=model))
        return FinderSessionStarted(
            session_id=session.id, token=session.token, source=session.source, mode=session.mode
        )

    @router.post("/finder/{session_id}/message")
    def message(
        session_id: str,
        body: FinderMessageRequest,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_finder_token: Annotated[str | None, Header()] = None,
    ) -> FinderReply:
        """The renter acted or said something. Their text is read by code into signals; a model
        never sees it. Returns the reply, the new proposals (nothing applied) and the picks."""
        session = find(request, session_id, authorization, x_finder_token)
        address = request.client.host if request.client else "unknown"
        if not limit.allow(f"msg:{address}"):
            raise HTTPException(status_code=429, detail="Too many messages. Try again in a minute.")
        if session.model is not None and not model_turns.reserve(address):
            raise HTTPException(
                status_code=429,
                detail=f"The finder has answered {model_turns.per_day} messages from here today. "
                "Try again tomorrow.",
            )
        try:
            return run_turn(session, [*body.signals, *read_text(body.text)])
        except FinderBusy as busy:
            if session.model is not None:
                model_turns.release(address)  # no model ran, so it costs nothing
            raise HTTPException(status_code=409, detail=str(busy)) from None

    @router.get("/finder/{session_id}/state")
    def state(
        session_id: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_finder_token: Annotated[str | None, Header()] = None,
    ) -> FinderState:
        return find(request, session_id, authorization, x_finder_token).state()

    @router.post("/finder/{session_id}/proposals/{proposal_id}")
    def answer(
        session_id: str,
        proposal_id: str,
        body: FinderDecision,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_finder_token: Annotated[str | None, Header()] = None,
    ) -> FinderProposal:
        """The renter's yes or no. Accepting is the only thing that changes a preference."""
        session = find(request, session_id, authorization, x_finder_token)
        try:
            return session.decide(proposal_id, body.decision == "accept")
        except KeyError:
            raise HTTPException(status_code=404, detail="No proposal with that id.") from None
        except (ValueError, FinderBusy) as refused:
            raise HTTPException(status_code=409, detail=str(refused)) from None

    @router.post("/finder/{session_id}/watch", status_code=201)
    def watch(
        session_id: str,
        body: FinderWatchRequest,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_finder_token: Annotated[str | None, Header()] = None,
    ) -> FinderWatchStatus:
        """Watch this session's brief on iMessage. Records the watch on the session and
        publishes `watch_added` (subject and payload.session: the session id; kind: brief) once.
        A second call returns the same watch. Nothing is texted from here."""
        session = find(request, session_id, authorization, x_finder_token)
        return session.add_watch(body.channel)

    return router
