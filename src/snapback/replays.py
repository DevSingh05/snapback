"""The replays of reported cases: demo/replays/*.json, read as they are and validated.

A replay carries no case data: no victim name, no address, no contact. The API serves these
files read-only (`GET /replays`) and the card footer for a replay demo case names its source
from the same file, so the web index, the replay page and the card never disagree.
"""

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl

from snapback.card import strings

log = logging.getLogger("snapback.replays")

REPLAYS_DIR = Path(__file__).resolve().parents[2] / "demo" / "replays"
SLUG = re.compile(r"^[A-Za-z0-9_-]{1,100}$")

_MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


class ReplaySource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    url: HttpUrl
    published_on: date


class ReplayStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: Literal["listing", "chat", "hold_request", "payment", "discovery"]
    reported_on: str  # YYYY-MM-DD, or empty when the source gives no date for the step
    label: str
    detail: str


class ReplayFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str
    status: Literal[
        "matches", "doesnt_match", "not_confirmed", "warning", "not_checked", "red_flag"
    ]
    text: str


class ReplaySnapback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["dont_pay", "hold"]
    stop_before: str | None = None
    findings: list[ReplayFinding]


class Replay(BaseModel):
    # Unknown top-level fields (a name, an address) are refused, not passed through.
    model_config = ConfigDict(extra="forbid")
    slug: str
    case_id: str
    title: str
    pattern: Literal["place", "person", "price"]
    fictional: bool
    source: ReplaySource | None = None
    amount_usd: int
    steps: list[ReplayStep]
    snapback: ReplaySnapback
    cant_catch: str


def load_replays(directory: Path | None = None) -> list[Replay]:
    """Every valid replay file, sorted by slug. A file that fails validation is logged and
    left out, so one bad file never takes the others down."""
    found: list[Replay] = []
    for path in sorted((directory or REPLAYS_DIR).glob("*.json")):
        try:
            replay = Replay.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            log.warning("replay %s is not valid and is not served", path.name)
            continue
        if replay.slug != path.stem or not SLUG.match(replay.slug):
            log.warning("replay %s: slug does not match the file name", path.name)
            continue
        if not replay.fictional and replay.source is None:
            log.warning("replay %s: a reported case needs a source", path.name)
            continue
        found.append(replay)
    return found


def replay_for_case(case_id: str, directory: Path | None = None) -> Replay | None:
    return next((r for r in load_replays(directory) if r.case_id == case_id), None)


def long_date(day: date, lang: str) -> str:
    if lang == "es":
        return f"{day.day} {_MONTHS_ES[day.month - 1]} {day.year}"
    return f"{_MONTHS_EN[day.month - 1]} {day.day}, {day.year}"


def replay_note(replay: Replay, lang: str = strings.DEFAULT_LANG) -> str | None:
    """The one sentence every replay page and replay card says; None for a fictional one."""
    if replay.source is None:
        return None
    return strings.text(
        "footer.replay",
        lang,
        source=replay.source.name,
        date=long_date(replay.source.published_on, lang),
    )
