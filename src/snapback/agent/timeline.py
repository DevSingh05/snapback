"""What the agent did: the case's trace, read back as plain steps (GET /cases/{id}/timeline).

Each step is one thing that happened, in the order it happened, with when it started and how
long it took (measured from the trace's own clock), who made it happen ("agent" when a language
model picked from code-written options or ran its own plan and sub-agents, "code" for the
policy, every check code ran, every fallback and always the result), and whether the data was
LIVE or FIXTURE.

Labels come from `strings` (en/es) and carry only counts. Results are short lines from the
trace with phone numbers, addresses and rents taken out. When the deep agent ran, its todo list
(as last written) and the sub-agents it handed work to come with the steps.

The case's event bus carries Finder events only, so the trace is the one source for a case.
Nothing here can change a case; it only reads.
"""

import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from snapback.agent.planner import PlanKind
from snapback.card import strings
from snapback.contracts import (
    ChoiceKind,
    DataSource,
    LocateStatus,
    ModuleEvidence,
    PhoneMatch,
    TraceEvent,
    TraceKind,
)

MAX_RESULT = 120

By = Literal["agent", "code"]


class TimelineStep(BaseModel):
    step: int = Field(ge=0)
    label: str  # plain words, from strings (en/es); counts only, never a phone, address or rent
    started_ms: int = Field(ge=0)  # since the case's first trace event
    took_ms: int = Field(ge=0)  # until the next step began (0 for the last, and derived lines)
    result: str  # one short line
    source: DataSource
    by: By


class TimelineTodo(BaseModel):
    content: str
    done: bool


class CaseTimeline(BaseModel):
    """`GET /cases/{id}/timeline`: the steps in order, and the agent's plan when it ran."""

    case_id: str
    source: DataSource
    mode: Literal["policy", "deepagents"]
    fell_back: bool  # the agent stopped (error or time limit) and code finished the case
    steps: list[TimelineStep]
    todos: list[TimelineTodo] = Field(default_factory=list)  # the agent's last todo list
    plan: list[str] = Field(default_factory=list)  # sub-agents handed work, in order


# --- scrubbing -----------------------------------------------------------------------------------

_PHONE = re.compile(r"\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_MONEY = re.compile(r"\$\s?\d[\d,]*(\.\d+)?(\s?(/|a|per)\s?(mo|month|mes))?", re.IGNORECASE)
_STREET_WORDS = (
    r"St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Lane|Ln|Way|Ct|Court|Pkwy|Parkway"
    r"|Pl|Place|Hwy|Highway|Calle|Avenida"
)
_ADDRESS = re.compile(
    rf"\b\d{{1,6}}\s+(?:[A-Z0-9][\w'-]*\s+){{0,4}}(?:{_STREET_WORDS})\b\.?", re.IGNORECASE
)
_LONG_NUMBER = re.compile(r"\d[\d,.\s-]{5,}\d")
_RENT_WORDS = re.compile(r"\b\d[\d,]{2,}\s?(dollars|dólares|/mo|a month|al mes)\b", re.IGNORECASE)


def scrub(text: object, fallback: str = "") -> str:
    """One short plain line with phone numbers, addresses and rents taken out."""
    line = " ".join(str(text or "").split())
    for pattern in (_ADDRESS, _PHONE, _MONEY, _RENT_WORDS, _LONG_NUMBER):
        line = pattern.sub("…", line)
    line = re.sub(r"(…[\s,]*)+", "… ", line).strip(" ,")
    if not line or line == "…":
        line = fallback
    if len(line) > MAX_RESULT:
        line = line[: MAX_RESULT - 1].rstrip() + "…"
    return line


# --- labels --------------------------------------------------------------------------------------

_CHECK_KEYS = {
    PlanKind.RECORD.value: "timeline.record",
    PlanKind.BROKERAGE.value: "timeline.for_sale",
    PlanKind.LICENSE.value: "timeline.license",
    PlanKind.OWNER.value: "timeline.owner",
    PlanKind.CLAIMS.value: "timeline.claims",
    PlanKind.ASK.value: "timeline.ask_license",
    PlanKind.REPORT.value: "timeline.report",
}
_CHOICE_KEYS = {
    ChoiceKind.WHICH_CHECKS: "timeline.which_checks",
    ChoiceKind.WHICH_FLOOR_PLAN: "timeline.floor_plan",
    ChoiceKind.WHICH_SPOT: "timeline.spot",
    ChoiceKind.RETRY_OR_STOP: "timeline.retry",
    ChoiceKind.ASK_HUMAN: "timeline.approval",
    ChoiceKind.NEXT_SEARCH: "timeline.retry_search",
    ChoiceKind.WHICH_PHOTO: "timeline.retry_search",
    ChoiceKind.DWELL_ROOMS: "timeline.walk",
    ChoiceKind.LEAD_CHECKS: "timeline.walk",
}
_TOOL_KEYS = {"license": "timeline.license", "reply": "timeline.reply"}


def _is_fallback(reason: str) -> bool:
    """The agent as a whole stopped (failed or ran out of time), as opposed to one bad pick."""
    keys = ("trace.error.model_failed", "trace.error.model_timeout")
    return any(reason == strings.text(k, lang) for k in keys for lang in strings.TABLES)


def _placed(evidence: ModuleEvidence) -> tuple[int, int] | None:
    locate = evidence.locate
    if locate is None or not locate.photos:
        return None
    placed = sum(1 for p in locate.photos if p.status is LocateStatus.LOCATED_IN_CLAIMED)
    return placed, len(locate.photos)


class _Builder:
    def __init__(self, source: DataSource, evidence: ModuleEvidence, lang: str) -> None:
        self.source = source
        self.evidence = evidence
        self.lang = lang
        self.steps: list[dict] = []

    def say(self, key: str, **values: object) -> str:
        return strings.text(key, self.lang, **values)

    def add(self, key: str, at_ms: int, result: str, by: By, *, took: int | None = None, **v):
        self.steps.append(
            {
                "label": self.say(key, **v),
                "started_ms": at_ms,
                "took_ms": took,  # None: filled from the next step's start
                "result": scrub(result, self.say("timeline.result.done")),
                "by": by,
                "derived": took is not None,
            }
        )

    def record_lines(self, at_ms: int) -> None:
        """What the home-record step found, one derived line each (timed with that step)."""
        price = self.evidence.price
        if price is not None and price.n_floor_plans:
            self.add(
                "timeline.rent",
                at_ms,
                self.say(f"timeline.result.rent.{price.status.value}"),
                "code",
                took=0,
                n=price.n_floor_plans,
            )
        authority = self.evidence.authority
        if authority is not None and authority.office_phone_match is not PhoneMatch.NOT_CHECKED:
            self.add(
                "timeline.phone",
                at_ms,
                self.say(f"timeline.result.phone.{authority.office_phone_match.value}"),
                "code",
                took=0,
            )


def build_timeline(
    case_id: str,
    source: DataSource,
    events: Sequence[TraceEvent],
    evidence: ModuleEvidence,
    lang: str = strings.DEFAULT_LANG,
) -> CaseTimeline:
    """The case's steps in trace order. Reads only; never changes the case."""
    b = _Builder(source, evidence, lang)
    events = sorted(events, key=lambda e: e.seq)
    t0 = events[0].at if events else None

    def ms(event: TraceEvent) -> int:
        return max(0, int((event.at - t0).total_seconds() * 1000)) if t0 else 0

    b.add("timeline.read_ad", 0, b.say("timeline.result.read_ad"), "code", took=0)
    todos: list[TimelineTodo] = []
    plan: list[str] = []
    open_handoffs: dict[str, int] = {}  # sub-agent -> index of its step
    ran_agent = fell_back = False

    for event in events:
        at = ms(event)
        by: By = "agent" if event.chosen_by == "model" else "code"
        if event.kind is TraceKind.TODO:
            ran_agent = True
            todos = [
                TimelineTodo(
                    content=scrub(item[4:] if item[:1] == "[" else item, "step"),
                    done=item.startswith("[x]"),
                )
                for item in event.options
            ]
            b.add(
                "timeline.plan",
                at,
                b.say("timeline.result.plan"),
                "agent",
                done=sum(t.done for t in todos),
                count=len(todos),
            )
        elif event.kind is TraceKind.AGENT:
            ran_agent = True
            pick = event.pick or ""
            if pick.startswith("sub-agent done: "):
                name = pick.removeprefix("sub-agent done: ")
                index = open_handoffs.pop(name, None)
                if index is not None:
                    step = b.steps[index]
                    step["took_ms"] = at - step["started_ms"]
                    step["result"] = b.say("timeline.result.returned")
            else:
                name = pick.removeprefix("sub-agent: ")
                plan.append(name)
                b.add("timeline.delegate", at, b.say("timeline.result.handed"), "agent", name=name)
                open_handoffs[name] = len(b.steps) - 1
        elif event.kind is TraceKind.FILE:
            ran_agent = True
            b.add("timeline.note", at, b.say("timeline.result.note"), "agent", took=0)
        elif event.kind is TraceKind.ERROR:
            if _is_fallback(event.reason):
                fell_back = True
                b.add("timeline.fallback", at, event.reason, "code")
            else:
                b.add("timeline.error", at, event.reason, "code")
        elif event.kind is TraceKind.VERDICT:
            b.add("timeline.verdict", at, b.say("timeline.result.verdict"), "code", took=0)
        elif event.kind is TraceKind.TOOL and event.pick == "locate":
            counts = _placed(evidence)
            if counts is None:
                b.add("timeline.locate_none", at, event.reason, "code")
            else:
                b.add(
                    "timeline.locate", at, event.reason, "code", placed=counts[0], total=counts[1]
                )
        elif event.kind is TraceKind.TOOL:
            b.add(_TOOL_KEYS.get(event.pick or "", "timeline.tool"), at, event.reason, "code")
        elif event.kind is TraceKind.STATUS and event.pick in _CHECK_KEYS:
            # a check the plan skipped: say which, and why
            skip_key = _CHECK_KEYS[event.pick].replace("timeline.", "timeline.skip.")
            b.add(skip_key, at, event.reason, "code")
        elif event.kind is TraceKind.STATUS:
            b.add("timeline.status", at, event.reason, "code")
        elif event.kind is TraceKind.HITL:
            b.add("timeline.approval", at, event.reason, "code")
        elif event.kind is TraceKind.UNSURE:
            b.add("timeline.unsure", at, event.reason, "code")
        elif event.kind is TraceKind.CHOICE and event.choice is ChoiceKind.NEXT_CHECK:
            key = _CHECK_KEYS.get(event.pick or "", "timeline.tool")
            if key == "timeline.record" and evidence.price is None and evidence.authority is None:
                key = "timeline.record_missing"
            b.add(key, at, event.reason, by)
            if key == "timeline.record":
                b.record_lines(at)
        elif event.kind is TraceKind.CHOICE:
            b.add(_CHOICE_KEYS.get(event.choice, "timeline.tool"), at, event.reason, by)
        if by == "agent":
            ran_agent = True

    # Each step lasted until the next one began; derived lines and the last step keep theirs.
    for i, step in enumerate(b.steps):
        if step["took_ms"] is None:
            later = [s["started_ms"] for s in b.steps[i + 1 :] if not s["derived"]]
            step["took_ms"] = max(0, later[0] - step["started_ms"]) if later else 0

    return CaseTimeline(
        case_id=case_id,
        source=source,
        mode="deepagents" if ran_agent else "policy",
        fell_back=fell_back,
        steps=[
            TimelineStep(step=i, source=source, **{k: v for k, v in step.items() if k != "derived"})
            for i, step in enumerate(b.steps)
        ],
        todos=todos,
        plan=plan,
    )
