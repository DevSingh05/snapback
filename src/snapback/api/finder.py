"""The finder's routes (M9): a session, a message, the state, and the renter's yes or no.

    POST /finder/sessions                       a new session: its id and write token (shown once)
    POST /finder/{session}/message              signals and/or text in; reply, proposals, picks out
    GET  /finder/{session}/state                applied and proposed prefs, picks, notes, trace
    POST /finder/{session}/proposals/{id}       {"decision": "accept" | "decline"}

The token goes in `Authorization: Bearer` or `X-Finder-Token`, never in the address. Nothing a
sub-agent proposes applies until the accept route runs.
"""

from __future__ import annotations

import secrets
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request

from snapback.agent.finder import FinderSession, load_fixture_places, read_text, run_turn
from snapback.api.limits import PerMinuteLimit
from snapback.contracts import (
    FinderDecision,
    FinderMessageRequest,
    FinderProposal,
    FinderReply,
    FinderSessionStarted,
    FinderState,
)
from snapback.events import EventBus

MAX_SESSIONS = 200
MESSAGE_PER_MINUTE = 20


def make_router(events: EventBus, model: Any = None, places: Any = None) -> APIRouter:
    """`model`: a chat model for deepagents mode, or None for the policy. `places`: a function
    returning the researched places (the M1 feed); the fixture places by default."""
    router = APIRouter()
    sessions: dict[str, FinderSession] = {}
    lock = threading.Lock()
    limit = PerMinuteLimit(MESSAGE_PER_MINUTE)

    def token_of(authorization: str | None, header: str | None) -> str | None:
        if authorization and authorization.lower().startswith("bearer "):
            return authorization[7:].strip()
        return header

    def find(request: Request, session_id: str, authorization: str | None, header: str | None):
        if "token" in request.query_params:
            raise HTTPException(
                status_code=401, detail="Send the finder token in a header, not in the address."
            )
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="No finder session with that id.")
        sent = token_of(authorization, header)
        if sent is None:
            raise HTTPException(status_code=401, detail="This needs the session's token.")
        if not secrets.compare_digest(sent.encode(), session.token.encode()):
            raise HTTPException(status_code=403, detail="That token is not for this session.")
        return session

    @router.post("/finder/sessions", status_code=201)
    def start(request: Request) -> FinderSessionStarted:
        """A new finder session; shows LIVE or FIXTURE and the mode (policy or deepagents)."""
        address = request.client.host if request.client else "unknown"
        if not limit.allow(f"new:{address}"):
            raise HTTPException(status_code=429, detail="Too many sessions. Try again in a minute.")
        found = places() if places else load_fixture_places()
        with lock:
            while len(sessions) >= MAX_SESSIONS:
                sessions.pop(next(iter(sessions)))
            session = FinderSession(f"fs-{secrets.token_hex(4)}", events, found, model=model)
            sessions[session.id] = session
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
        return run_turn(session, [*body.signals, *read_text(body.text)])

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
        except ValueError as refused:
            raise HTTPException(status_code=409, detail=str(refused)) from None

    return router
