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
from snapback.agent.session import UPDATED
from snapback.agent.worklog import AgentWork, MemberTrace, member_traces
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
    # Which check or sub-agent the step belongs to (a module id such as "record", "owner",
    # "locate", or a sub-agent's own name), so a page can tie a reason to the step behind it.
    # None for steps that are not one check (reading the ad, the verdict, a retry).
    kind: str | None = None
    skipped: bool = False  # the plan left this check out; `result` says why
    # Which source answered the step: "CoStar record", "HUD", "Census", "HCAD", "RDAP", "TREC".
    # None for a step no outside source answered (reading the ad, the verdict).
    source_name: str | None = None


class TimelineTodo(BaseModel):
    content: str
    done: bool


class CaseTimeline(BaseModel):
    """`GET /cases/{id}/timeline`: the steps in order, and the agent's plan when it ran."""

    case_id: str
    source: DataSource
    mode: Literal["policy", "deepagents"]
    fell_back: bool  # the agent stopped (error or time limit) and code finished the case
    running: bool = False  # the deep agent is still working this case in the background
    steps: list[TimelineStep]
    todos: list[TimelineTodo] = Field(default_factory=list)  # the agent's last todo list
    plan: list[str] = Field(default_factory=list)  # sub-agents handed work, in order
    # The trace cards, when the deep agent ran: the planner, then each member in the order work
    # reached it, with what it was asked, the tools it called, what it said and its model calls.
    # Empty with the policy (no model ran), and for a case whose run this server did not see.
    members: list[MemberTrace] = Field(default_factory=list)
    # Where the run's full trace can be opened in LangSmith, when the server names a project
    # page. A plain address with no key or token in it. None when there is none.
    trace_url: str | None = None


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


_BARE_NUMBER = re.compile(r"\d[\d,]{2,}")


def scrub(text: object, fallback: str = "", *, model: bool = False) -> str:
    """One short plain line with phone numbers, addresses and rents taken out. Text a model
    wrote (`model`) also loses every run of three or more digits, commas included: a model can
    quote a bare rent, deposit or street number that no pattern above would recognise."""
    line = " ".join(str(text or "").split())
    patterns = [_ADDRESS, _PHONE, _MONEY, _RENT_WORDS, _LONG_NUMBER]
    if model:
        patterns.append(_BARE_NUMBER)
    for pattern in patterns:
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
_CHECK_KINDS = {
    PlanKind.RECORD.value: "record",
    PlanKind.BROKERAGE.value: "for_sale",
    PlanKind.LICENSE.value: "license",
    PlanKind.OWNER.value: "owner",
    PlanKind.CLAIMS.value: "claims",
    PlanKind.ASK.value: "ask_license",
    PlanKind.REPORT.value: "report",
}
# Which source answers each check, named on its step.
_CHECK_SOURCES = {
    PlanKind.RECORD.value: "CoStar record",
    PlanKind.BROKERAGE.value: "CoStar record",
    PlanKind.CLAIMS.value: "CoStar record",
    PlanKind.LICENSE.value: "TREC",
    PlanKind.OWNER.value: "HCAD",
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
    ChoiceKind.FOLLOW_UP: "timeline.followup",
    ChoiceKind.NEXT_STEP: "timeline.next_step",
}


def _followup_name(check: str) -> str:
    from snapback.agent.followups import MENU

    item = MENU.get(check)
    return item.name if item is not None else check


def _followup_source(evidence: ModuleEvidence, pick: str) -> str | None:
    check = pick.removeprefix("followup:")
    return next((f.source_name for f in evidence.followups if f.check == check), None)


_TOOL_KEYS = {"license": "timeline.license", "reply": "timeline.reply"}


_FALLBACKS = {
    "trace.error.model_failed": "failed",
    "trace.error.model_timeout": "timeout",
    "trace.error.model_nokey": "nokey",
    "trace.error.model_busy": "busy",
    "trace.error.model_stuck": "stuck",
}


def _fallback_reason(reason: str) -> str | None:
    """Why the agent as a whole stopped (failed, no key, out of time, kept waiting, stuck), as
    opposed to one bad pick: the short key of the reason, else None."""
    for key, short in _FALLBACKS.items():
        if any(reason == strings.text(key, lang) for lang in strings.TABLES):
            return short
    return None


def _is_fallback(reason: str) -> bool:
    return _fallback_reason(reason) is not None


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

    def add(
        self,
        key: str,
        at_ms: int,
        result: str,
        by: By,
        *,
        took: int | None = None,
        model: bool = False,
        source: DataSource | None = None,
        kind: str | None = None,
        skipped: bool = False,
        source_name: str | None = None,
        **v: object,
    ) -> None:
        self.steps.append(
            {
                "label": self.say(key, **v),
                "started_ms": at_ms,
                "took_ms": took,  # None: filled from the next step's start
                "result": scrub(result, self.say("timeline.result.done"), model=model),
                "source": source or self.source,
                "by": by,
                "kind": kind,
                "skipped": skipped,
                "source_name": source_name,
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
                source=self.evidence.record_source,
                kind="rent",
                source_name="CoStar record",
                n=price.n_floor_plans,
            )
        if price is not None and price.baseline_source == "hud_safmr":
            self.add(
                "timeline.rent_hud",
                at_ms,
                self.say(f"timeline.result.rent_hud.{price.status.value}"),
                "code",
                took=0,
                kind="rent",
                source_name="HUD",
            )
        place = self.evidence.place_check
        if place is not None:
            self.add(
                "timeline.census",
                at_ms,
                self.say(f"timeline.result.census.{place.status.value}"),
                "code",
                took=0,
                source=place.source,
                kind="place_check",
                source_name="Census",
            )
        domain = self.evidence.domain_check
        if domain is not None:
            self.add(
                "timeline.rdap",
                at_ms,
                self.say(f"timeline.result.rdap.{domain.status.value}"),
                "code",
                took=0,
                source=domain.source,
                kind="link_domain",
                source_name="RDAP",
            )
        authority = self.evidence.authority
        if authority is not None and authority.office_phone_match is not PhoneMatch.NOT_CHECKED:
            self.add(
                "timeline.phone",
                at_ms,
                self.say(f"timeline.result.phone.{authority.office_phone_match.value}"),
                "code",
                took=0,
                source=self.evidence.record_source,
                kind="phone",
                source_name="CoStar record",
            )


def build_timeline(
    case_id: str,
    source: DataSource,
    events: Sequence[TraceEvent],
    evidence: ModuleEvidence,
    lang: str = strings.DEFAULT_LANG,
    *,
    running: bool = False,
    work: AgentWork | None = None,
    runners: dict[str, str] | None = None,
    trace_url: str | None = None,
) -> CaseTimeline:
    """The case's steps in trace order. Reads only; never changes the case. `running` says the
    deep agent is still at work on it (SNAPBACK_AGENT=deepagents_async)."""
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
                    content=scrub(item[4:] if item[:1] == "[" else item, "step", model=True),
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
                b.add(
                    "timeline.delegate",
                    at,
                    b.say("timeline.result.handed"),
                    "agent",
                    kind=name,
                    name=name,
                )
                open_handoffs[name] = len(b.steps) - 1
        elif event.kind is TraceKind.FILE:
            ran_agent = True
            b.add("timeline.note", at, b.say("timeline.result.note"), "agent", took=0)
        elif event.kind is TraceKind.ERROR:
            why = _fallback_reason(event.reason)
            if why is not None:
                fell_back = True
                b.add(
                    "timeline.fallback",
                    at,
                    event.reason,
                    "code",
                    reason=b.say(f"timeline.fallback.{why}"),
                )
            else:
                b.add("timeline.error", at, event.reason, "code")
        elif event.kind is TraceKind.VERDICT:
            b.add("timeline.verdict", at, b.say("timeline.result.verdict"), "code", took=0)
        elif event.kind is TraceKind.TOOL and event.pick == "locate":
            counts = _placed(evidence)
            if counts is None:
                b.add("timeline.locate_none", at, event.reason, "code", kind="locate")
            else:
                b.add(
                    "timeline.locate",
                    at,
                    event.reason,
                    "code",
                    kind="locate",
                    placed=counts[0],
                    total=counts[1],
                )
        elif event.kind is TraceKind.TOOL and (event.pick or "").startswith("followup:"):
            b.add(
                "timeline.followup_result",
                at,
                event.reason,
                by,
                model=by == "agent",
                kind="followup",
                source_name=_followup_source(evidence, event.pick or ""),
            )
        elif event.kind is TraceKind.TOOL:
            b.add(
                _TOOL_KEYS.get(event.pick or "", "timeline.tool"),
                at,
                event.reason,
                "code",
                kind=event.pick if event.pick in _TOOL_KEYS else None,
            )
        elif event.kind is TraceKind.STATUS and event.pick == UPDATED:
            b.add("timeline.updated", at, event.reason, "code")
        elif event.kind is TraceKind.STATUS and event.pick in _CHECK_KEYS:
            # a check the plan skipped: say which, and why
            skip_key = _CHECK_KEYS[event.pick].replace("timeline.", "timeline.skip.")
            b.add(skip_key, at, event.reason, "code", kind=_CHECK_KINDS[event.pick], skipped=True)
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
            on_record = key in ("timeline.record", "timeline.record_missing")
            b.add(
                key,
                at,
                event.reason,
                by,
                model=by == "agent",
                source=evidence.record_source if on_record else None,
                kind=_CHECK_KINDS.get(event.pick or ""),
                source_name=_CHECK_SOURCES.get(event.pick or ""),
            )
            if key == "timeline.record":
                b.record_lines(at)
        elif event.kind is TraceKind.CHOICE and event.choice is ChoiceKind.FOLLOW_UP:
            picked = next((f for f in evidence.followups if f.check == event.pick), None)
            b.add(
                "timeline.followup",
                at,
                picked.reason if picked is not None else event.reason,
                by,
                model=by == "agent",
                kind="followup",
                source_name=picked.source_name if picked is not None else None,
                check=_followup_name(event.pick or ""),
                gap=picked.gap if picked is not None else "",
            )
        elif event.kind is TraceKind.CHOICE and event.choice is ChoiceKind.NEXT_STEP:
            from snapback.agent.followups import NEXT_STEPS

            item = NEXT_STEPS.get(event.pick or "")
            gap = event.options[0] if event.options else ""
            b.add(
                "timeline.next_step",
                at,
                event.reason,
                by,
                model=by == "agent",
                kind="followup",
                step=item.name if item is not None else (event.pick or ""),
                gap=gap,
            )
        elif event.kind is TraceKind.CHOICE:
            b.add(
                _CHOICE_KEYS.get(event.choice, "timeline.tool"),
                at,
                event.reason,
                by,
                model=by == "agent",
            )
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
        mode="deepagents" if ran_agent or running else "policy",
        fell_back=fell_back,
        running=running,
        steps=[
            TimelineStep(step=i, **{k: v for k, v in step.items() if k != "derived"})
            for i, step in enumerate(b.steps)
        ],
        todos=todos,
        plan=plan,
        # Cards only for a run the model took part in, and only with the server's own word
        # for what ran it.
        members=member_traces(work, runners, lang) if ran_agent and runners else [],
        trace_url=trace_url if ran_agent else None,
    )
