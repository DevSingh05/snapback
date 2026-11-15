"""What the deep agent did, member by member: the record behind the trace cards.

While the agent runs, a callback (`graph.WorkWatch`) notes every model call and every tool call,
with the name of the member that made it (the main agent is the planner). From that this module
builds one card per member: what it was asked, the tools it called in order with a one-line
result each, what it said back, how long it took and how many model calls it made.

The log only reads. It cannot move a case, and `decide()` never sees it. Everything on a card
that a model or a tool wrote is cleaned on the way out (`plain`): no phone number, address or
rent figure, no run of three or more digits (so no record figure, whatever the figures switch
says), no result word, and never a prompt. A card is an explanation, not a result.

This module does not import langchain or deepagents, so the package works without the `agent`
extra.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from snapback.agent.trace import clean_reason
from snapback.card import strings

PLANNER = "planner"
MAX_TOOLS = 24  # per member; a card is a summary, the raw trace has the rest


class TraceTool(BaseModel):
    tool: str  # the tool's own name, for anyone matching it to the raw trace
    label: str  # what it did, in plain words
    result: str  # one short line of what came back


class MemberTrace(BaseModel):
    """One member's card on `GET /cases/{id}/timeline`."""

    kind: str  # "planner", or the sub-agent's name ("record", "owner", "place", ...)
    model: str  # what ran it: "Claude Sonnet", "Claude Haiku", ...
    asked: str | None = None  # the planner's instruction to it, cleaned; None for the planner
    tools: list[TraceTool] = []
    said: str | None = None  # what it handed back, cleaned and trimmed
    took_ms: int | None = None  # from its first call to its last
    model_calls: int = 0


@dataclass
class _Use:
    run_id: str
    tool: str
    args: dict[str, Any]
    output: str | None = None


@dataclass
class _Member:
    asked: str | None = None
    said: str | None = None
    calls: int = 0
    uses: list[_Use] = field(default_factory=list)
    first: float | None = None
    last: float | None = None

    def touch(self, now: float) -> None:
        if self.first is None:
            self.first = now
        self.last = now


OTHER = "other"


def member_kind(name: str | None) -> str:
    """Which card a call belongs to. The planner writes the name of the member it hands work to,
    so that name is a model's text: only a name the roster knows is ever kept. Anything else
    (a made-up member, a sentence, a number) is filed under "other" and never shown as written."""
    if not name or name == PLANNER:
        return PLANNER
    from snapback.agent.roster import card_for

    return name if card_for(name) is not None else OTHER


def _target(use: _Use) -> str | None:
    raw = str(use.args.get("subagent_type") or "")
    return member_kind(raw) if raw else None


class AgentWork:
    """The running log for one case. Safe to write from the agent's threads."""

    def __init__(self, clock: Any = time.monotonic) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._members: dict[str, _Member] = {}
        self._open: dict[str, tuple[str, _Use]] = {}  # run id -> (member, use)

    def _member(self, name: str | None) -> _Member:
        return self._members.setdefault(member_kind(name), _Member())

    def model_call(self, member: str | None) -> None:
        with self._lock:
            who = self._member(member)
            who.calls += 1
            who.touch(self._clock())

    def tool_start(self, run_id: str, member: str | None, tool: str, args: Any) -> None:
        with self._lock:
            who = self._member(member)
            who.touch(self._clock())
            use = _Use(run_id, tool, args if isinstance(args, dict) else {})
            if len(who.uses) < MAX_TOOLS:
                who.uses.append(use)
            self._open[run_id] = (member_kind(member), use)
            if tool == "task":
                # A hand-off: the instruction belongs on the card of the member it went to.
                target = _target(use)
                if target:
                    self._member(target).asked = str(use.args.get("description") or "")

    def tool_end(self, run_id: str, output: Any) -> None:
        with self._lock:
            found = self._open.pop(run_id, None)
            if found is None:
                return
            name, use = found
            use.output = _text(output)
            self._member(name).touch(self._clock())
            if use.tool == "task":
                target = _target(use)
                if target:
                    self._member(target).said = use.output

    def snapshot(self) -> dict[str, _Member]:
        with self._lock:
            return dict(self._members)


def _text(output: Any) -> str:
    """A tool's output as text: a message's content, a command's last message, or the thing."""
    content = getattr(output, "content", None)
    if content is None:
        update = getattr(output, "update", None)
        messages = update.get("messages") if isinstance(update, dict) else None
        if messages:
            content = getattr(messages[-1], "content", None)
    if content is None:
        content = output
    if isinstance(content, list):
        parts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
        content = " ".join(parts)
    return str(content or "")


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_K_MONEY = re.compile(r"\b\d+(?:\.\d+)?\s?k\b", re.IGNORECASE)
_KEY = re.compile(r"\b(?:sk-ant|lsv2_|sk-)[\w-]{4,}", re.IGNORECASE)


def plain(text: object, fallback: str) -> str:
    """One short line a renter may read: no result word, phone, address, rent or long number,
    and no email, web address, "1.5k" money shorthand or anything shaped like a key."""
    from snapback.agent.casework import _banned  # a note's rule: it never announces a result
    from snapback.agent.timeline import scrub  # timeline imports this module for its models

    line = clean_reason(text, fallback)
    if _banned(line):
        line = fallback
    for pattern in (_KEY, _EMAIL, _URL, _K_MONEY):
        line = pattern.sub("…", line)
    return scrub(line, fallback, model=True)


_READ_TOOLS = {
    "read_record_facts": "worklog.tool.record",
    "read_office_facts": "worklog.tool.office",
    "read_owner_facts": "worklog.tool.owner",
    "read_place_facts": "worklog.tool.place",
    "search_places": "worklog.tool.search",
    "write_todos": "worklog.tool.todos",
    "write_file": "worklog.tool.write",
    "read_file": "worklog.tool.read",
    "ls": "worklog.tool.read",
    "open_choice": "worklog.tool.open",
    "choose_option": "worklog.tool.choose",
    "draw_spot": "worklog.tool.spot",
    "send_challenge": "worklog.tool.challenge",
    "place_state": "worklog.tool.place",
    "place_open_choice": "worklog.tool.open",
    "place_choose_option": "worklog.tool.choose",
    "walk_open_choice": "worklog.tool.open",
    "walk_choose_option": "worklog.tool.choose",
}


def tool_label(tool: str, args: dict[str, Any], lang: str) -> str:
    """What a tool call did, in plain words. A tool this table does not know still gets words."""
    if tool == "task":
        from snapback.agent.roster import card_for  # the member's own name, never the raw text

        card = card_for(str(args.get("subagent_type") or ""), lang)
        if card is None:
            return strings.text("worklog.tool.task_other", lang)
        return strings.text("worklog.tool.task", lang, name=card.name)
    return strings.text(_READ_TOOLS.get(tool, "worklog.tool.other"), lang)


def _result(use: _Use, lang: str) -> str:
    done = strings.text("worklog.result.done", lang)
    if use.output is None:
        return strings.text("worklog.result.running", lang)
    if use.tool == "write_file":
        return strings.text("worklog.result.saved", lang)
    if use.tool == "write_todos":
        todos = use.args.get("todos")
        count = len(todos) if isinstance(todos, list) else 0
        finished = sum(
            1 for t in todos or [] if isinstance(t, dict) and t.get("status") == "completed"
        )
        return strings.text("worklog.result.todos", lang, done=finished, count=count)
    # The first lines that say something, joined: facts come as "Key: value" lines.
    # The label already names the source, so the "Source:" line is left out.
    lines = [ln.strip() for ln in use.output.splitlines() if ln.strip()]
    said = [ln for ln in lines if not ln.lower().startswith(("source:", "fuente:"))] or lines
    return plain(_readable("; ".join(said[:2])), done)


_CODE_WORDS = (("_", " "), (": None", ": none"), (": False", ": no"), (": True", ": yes"))


def _readable(line: str) -> str:
    """A facts line as words: statuses are written for code (`not_checked`, `False`)."""
    for old, new in _CODE_WORDS:
        line = line.replace(old, new)
    return line


def member_traces(
    work: AgentWork | None, by: dict[str, str], lang: str = strings.DEFAULT_LANG
) -> list[MemberTrace]:
    """The cards, the planner first and then each member in the order work reached it. `by` says
    what runs the planner and the sub-agents on this server (`roster.runners`)."""
    if work is None:
        return []
    members = work.snapshot()
    if not members:
        return []
    order = sorted(members, key=lambda n: (n != PLANNER, members[n].first or 0.0))
    cards: list[MemberTrace] = []
    for name in order:
        m = members[name]
        took = (
            int((m.last - m.first) * 1000) if m.first is not None and m.last is not None else None
        )
        ask = strings.text("worklog.asked.fallback", lang)
        said = strings.text("worklog.said.fallback", lang)
        cards.append(
            MemberTrace(
                kind=name,
                model=by["planner" if name == PLANNER else "sub"],
                asked=None if name == PLANNER or m.asked is None else plain(m.asked, ask),
                tools=[
                    TraceTool(
                        tool=u.tool, label=tool_label(u.tool, u.args, lang), result=_result(u, lang)
                    )
                    for u in m.uses
                ],
                said=None if m.said is None else plain(m.said, said),
                took_ms=max(0, took) if took is not None else None,
                model_calls=m.calls,
            )
        )
    return cards
