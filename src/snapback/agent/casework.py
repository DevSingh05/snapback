"""A case's working notes: derived text per check family, kept in the deepagents file system.

The deep agent (`graph.py`) delegates each check family to its own sub-agent. A sub-agent reads
only its family's facts (below), writes a short note to `/case/<id>/<stem>.md` in the agent's
virtual file system, and the main agent reads the notes to write the plain-language explanation
and the tour-prep questions.

What a note may hold: statuses, counts and short facts with their source. Never an image, a
raw kit row, a listing photo, a person's name, a phone number, a licence number or an address.
The fact functions here build text from `ModuleEvidence`, which already carries only derived
values, so a note written from them cannot hold more. A note a model writes is cleaned again
(`clean_note`) before it is kept or served, and a note a model did not write is written by code
(`refresh_policy_notes`), so every case has the same notes whoever drove it.

Notes never set a state. `decide()` is the only place a state is chosen; nothing here is read
by it, and the card is built from evidence alone.

This module does not import deepagents, so the package works without the `agent` extra.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from snapback.agent.trace import _BANNED_IN_REASONS
from snapback.card import strings
from snapback.contracts import DataSource, ModuleEvidence

# stem -> (sub-agent name, what the note is about). The order is the order notes are shown.
RECORD, OFFICE, OWNER, PLACE, PLACES = "record", "office", "owner", "place", "places"
STEMS = (RECORD, OFFICE, OWNER, PLACE, PLACES)
# The main agent's own notes, written after it has read the others.
# The walk note exists only for a case that has a walk plan (the T lane's tour).
WALK = "walk"
WEB = "web"  # W1: exists only for a case whose web checks were started
EXPLANATION, TOUR_PREP = "explanation", "tour_prep"
MAIN_STEMS = (EXPLANATION, TOUR_PREP)

AGENT_NAMES: dict[str, str] = {
    RECORD: "record",
    OFFICE: "office-and-licence",
    OWNER: "owner",
    PLACE: "place",
    PLACES: "search",
    WALK: "walk",
    WEB: "web",
}
MAX_NOTE_CHARS = 1500
MAX_LINE_CHARS = 280


def _plain(text: str) -> str:
    """Lowercase, NFKC, straight quotes, single spaces: so a curly apostrophe, a double space
    or a non-breaking space cannot hide a phrase."""
    flat = unicodedata.normalize("NFKC", text).lower()
    for curly in ("\u2019", "\u2018", "\u02bc", "\u00b4", "`"):
        flat = flat.replace(curly, "'")
    return " ".join(flat.split())


def _headline_phrases() -> tuple[str, ...]:
    """Every result headline the card can print, in each language, a sentence at a time."""
    out: list[str] = []
    for table in strings.TABLES.values():
        for key, value in table.items():
            if key.startswith("state."):
                out += [_plain(part).strip(" .") for part in value.split(".") if part.strip()]
    return tuple(out)


# Words a note never uses: the trace's list, a note must not announce a result or tell the renter
# to pay, so every result headline (EN and ES) is on it too.
_BANNED_IN_NOTES = (
    *(_plain(w) for w in _BANNED_IN_REASONS),
    "don't pay",
    "do not pay",
    "checks passed",
    "safe to pay",
    "data:image",
    "base64",
    *_headline_phrases(),
)
# The same phrases with apostrophes dropped, to catch "dont pay".
_BANNED_NO_APOS = tuple(w.replace("'", "") for w in _BANNED_IN_NOTES)


def _banned(line: str) -> bool:
    flat = _plain(line)
    bare = flat.replace("'", "")
    return any(w in flat for w in _BANNED_IN_NOTES) or any(w in bare for w in _BANNED_NO_APOS)


By = Literal["model", "policy"]


@dataclass(frozen=True)
class Note:
    path: str
    stem: str
    text: str
    by: By


class CaseNote(BaseModel):
    path: str
    stem: str
    agent: str  # which sub-agent wrote it, or "main" for the explanation and tour prep
    text: str
    written_by: By


class CaseNotes(BaseModel):
    """`GET /cases/{id}/notes`: the notes the agent wrote, read-only."""

    case_id: str
    source: DataSource
    notes: list[CaseNote]
    footer: str = "Working notes. The result on the card is worked out by code from the evidence."


def note_path(case_id: str, stem: str) -> str:
    return f"/case/{case_id}/{stem}.md"


def stem_of(case_id: str, path: str) -> str | None:
    """`record` for `/case/<id>/record.md`; None for any other path."""
    prefix = f"/case/{case_id}/"
    if not path.startswith(prefix) or not path.endswith(".md"):
        return None
    stem = path[len(prefix) : -3]
    return stem if stem in (*STEMS, WALK, WEB, *MAIN_STEMS) else None


def clean_note(text: object) -> str:
    """Keep a note short and plain: drop lines with banned words, long lines, and the rest past
    the cap. A note that is empty after cleaning is empty."""
    kept: list[str] = []
    for raw in str(text or "").splitlines():
        line = raw.rstrip()
        if _banned(line):
            continue
        if len(line) > MAX_LINE_CHARS:
            line = line[: MAX_LINE_CHARS - 1].rstrip() + "…"
        kept.append(line)
    body = "\n".join(kept).strip()
    if len(body) > MAX_NOTE_CHARS:
        body = body[: MAX_NOTE_CHARS - 1].rstrip() + "…"
    return body


# --- the facts each sub-agent may read ----------------------------------------------------------
# One function per family. Each returns lines of "label: value". Values are statuses, counts and
# company names that `ModuleEvidence` already holds; none of these reads a photo or a kit row.


def _val(x: object) -> str:
    return "not checked" if x is None else str(getattr(x, "value", x))


def record_facts(ev: ModuleEvidence) -> str:
    lines = ["Source: CoStar property record and the ad's own words (as of CoStar's last research)"]
    p = ev.price
    if p is None:
        lines.append("Rent check: not checked (no rent on record for this building)")
    else:
        band = (
            f"{p.record_min} to {p.record_max}, median {p.record_median}"
            if p.record_median is not None
            else "no band"
        )
        lines.append(f"Rent check: {_val(p.status)}; ad says {p.listed_rent}; record {band}")
        lines.append(f"Floor plans on record: {p.n_floor_plans}; per-bed pricing: {p.per_bed}")
        lines.append(f"Unit on record: {_val(p.unit)}")
    fs = ev.for_sale
    if fs is None:
        lines.append("For-sale lookup: not looked up")
    else:
        lines.append(f"For-sale lookup: {_val(fs.status)} on {fs.site}")
    hits = [f"{h.rule_id}{' (red flag)' if h.red_flag else ''}" for h in ev.rules]
    lines.append("Rules that fired on the ad's wording: " + (", ".join(hits) if hits else "none"))
    return "\n".join(lines)


def office_facts(ev: ModuleEvidence) -> str:
    lines = ["Source: CoStar office on record, TREC licence lookup, the building's website"]
    a = ev.authority
    if a is None:
        lines.append("Office on record: not checked")
    else:
        lines.append(
            f"Poster vs office on record: {_val(a.status)}; office: "
            f"{a.manager_on_record or 'none on record'}; brokerage-only comparison: "
            f"{a.brokerage_only}"
        )
        lines.append(f"Phone vs office phone: {_val(a.office_phone_match)}")
        lines.append(f"Link vs the building's own website: {_val(a.link_domain)}")
    lic = ev.license
    if lic is None:
        lines.append("Licence lookup (TREC): not looked up")
    else:
        lines.append(
            f"Licence lookup (TREC): {_val(lic.status)}; role claimed: "
            f"{lic.claimed_role or 'none'}; number from: {lic.number_from or 'none given'}; "
            f"sponsor: {lic.sponsor_broker or 'none'}"
        )
    if ev.for_sale and ev.for_sale.offices:
        lines.append("Listing offices on record: " + ", ".join(ev.for_sale.offices))
    return "\n".join(lines)


def owner_facts(ev: ModuleEvidence) -> str:
    o = ev.owner
    if o is None:
        return "Source: county owner of record\nOwner of record: no owner data for this address"
    name = o.company if (o.company_known and o.company) else None
    who = (
        f"a company ({name})"
        if name
        else ("a company" if o.kind.value == "company" else "a private owner")
    )
    lines = [
        "Source: county owner of record (HCAD)",
        f"Owner of record: {who}",
        f"Poster matches the owner of record: {_val(o.poster_matches)}",
        f"Poster says they are the owner: {o.poster_says_owner}",
        "Owner has a published payment rule: "
        + (f"yes ({o.published_rule.company})" if o.published_rule else "no"),
    ]
    return "\n".join(lines)


def place_facts(ev: ModuleEvidence) -> str:
    loc = ev.locate
    if loc is None:
        return "Source: 3D scan placement of the listing photos\nPlacement: not run"
    by_status = Counter(p.status.value for p in loc.photos)
    rooms = Counter(p.room_label for p in loc.photos if p.room_label)
    lines = [
        "Source: 3D scan placement of the listing photos (results only, no images)",
        f"Photos: {len(loc.photos)}; "
        + (", ".join(f"{n} {s}" for s, n in sorted(by_status.items())) or "none"),
        "Rooms the placed photos fall in: "
        + (", ".join(f"{label} x{n}" for label, n in sorted(rooms.items())) or "none"),
        f"Home identified by the scan alone: {loc.identified_by_scan}",
    ]
    if loc.chosen is not None:
        lines.append(f"Floor plan chosen: {loc.chosen.floor_plan}")
    return "\n".join(lines)


FACTS: dict[str, Callable[[ModuleEvidence], str]] = {
    RECORD: record_facts,
    OFFICE: office_facts,
    OWNER: owner_facts,
    PLACE: place_facts,
}


def places_text(response: Any) -> str:
    """The search's findings as text, from an `AlternativesResponse` or `SearchResponse`.

    No building id, address or company name: kind, size, price, how it fits the budget, whether
    a 3D scan exists, and who made each choice."""
    lines = [
        f"Source: researched places (as of CoStar's last research); {len(response.matches)} found"
    ]
    for i, m in enumerate(response.matches, start=1):
        size = f"{m.beds} bed" if m.beds is not None else m.kind
        lines.append(
            f"Place {i}: {m.kind}, {size}, {m.price_text}; budget: {_val(m.budget_fit)}; "
            f"must-haves met: {m.musts_met}; 3D scan: {m.has_3d_scan}; deep check: {m.checked}"
        )
    for d in response.decisions:
        lines.append(f"Decision {d.kind}: picked {d.pick} (chosen by {d.chosen_by}): {d.reason}")
    if response.question:
        lines.append(f"Trade-off question: {response.question}")
    return "\n".join(lines)


# --- keeping the notes on the session -------------------------------------------------------------


def keep_note(case: Any, path: str, text: object, by: By) -> Note | None:
    """Clean `text` and keep it as the case's note at `path`. None when the path is not one of
    ours or nothing is left after cleaning. A model's note replaces a code note, never the
    other way round."""
    stem = stem_of(case.case_id, path)
    body = clean_note(text)
    if stem is None or not body:
        return None
    old = case.notes.get(stem)
    if old is not None and old.by == "model" and by == "policy":
        return None
    if old is not None and old.text == body and old.by == by:
        return None  # nothing new
    note = Note(path=path, stem=stem, text=body, by=by)
    case.notes[stem] = note
    return note


def refresh_policy_notes(case: Any) -> None:
    """Write, from code, every family note a model has not written. Safe to call again as the
    case moves on: a code note is rewritten from the evidence as it stands."""
    for stem, build in FACTS.items():
        keep_note(case, note_path(case.case_id, stem), build(case.evidence), "policy")
    refresh_walk_note(case)
    refresh_web_note(case)
    search = getattr(case, "search_places", None)
    held = case.notes.get(PLACES)
    if search is not None and not (held is not None and held.by == "model"):
        # Code notes use the code policy only: a model's search is paid for once, by the
        # search sub-agent, never again on every advance.
        try:
            body = search()
        except Exception:
            body = ""
        keep_note(case, note_path(case.case_id, PLACES), body, "policy")


def refresh_walk_note(case: Any) -> None:
    """If the case has a walk plan, settle the director (a model's picks if it made them, the
    code policy for the rest) and write the walk note from code unless a model wrote one."""
    plan_fn = getattr(case, "walk_plan", None)
    if plan_fn is None:
        return
    try:
        from snapback.agent.walk_agent import WalkDesk

        desk = getattr(case, "walk_desk", None) or WalkDesk(plan_fn)
        case.walk_desk = desk
        director = desk.director()
        case.walk_director = director
        keep_note(case, note_path(case.case_id, WALK), desk.text(director), "policy")
    except Exception:  # no tour on this install, or the plan could not be built: no walk note
        return


def _yes_no(value: bool | None) -> str:
    return "unknown" if value is None else ("yes" if value else "no")


def web_text(facts: Any) -> str:
    """The web checks' facts as note lines: statuses, yes/no and counts. No digits of a phone,
    no name, no page text. `facts` is a WebFacts, or None while the checks run."""
    if facts is None:
        return "Source: web checks\nStatus: still running"
    site, link, other = facts.site, facts.link, facts.elsewhere
    lines = [f"Source: web checks ({facts.source.value})"]
    lines.append(
        f"Building's own site: {site.status.value}"
        + (
            f"; host {site.host}; lists the ad's plan or unit: {_yes_no(site.lists_unit)}; "
            f"shows the office phone on record: {_yes_no(site.phone_matches)}"
            if site.status.value == "done"
            else ""
        )
    )
    lines.append(
        f"The ad's link (Browser Use): {link.status.value}"
        + (
            f"; ends at {link.final_host}; that is the building's own site: "
            f"{_yes_no(link.same_as_record)}; against the record's website: "
            f"{link.link_domain.value if link.link_domain else 'not checked'}"
            f"; asks for payment on the page: "
            f"{_yes_no(link.asks_payment_on_page)}"
            if link.status.value == "done"
            else ""
        )
    )
    if other.status.value == "done":
        posted = (
            f"{other.postings} found; one shows a different phone: {_yes_no(other.poster_differs)}"
            if other.postings is not None
            else "not checked"
        )
        lines.append(f"The ad's own words posted elsewhere (web search): {posted}")
        if other.nearby is not None:
            rents = (
                f", asked rent {other.rent_low} to {other.rent_high}"
                if other.rent_low is not None
                else ""
            )
            lines.append(
                f"Rentals this size nearby (Apify, not the same home): {other.nearby}{rents}"
            )
    else:
        lines.append(
            f"Posted elsewhere and rentals nearby (web search, Apify): {other.status.value}"
        )
    return "\n".join(lines)


def refresh_web_note(case: Any) -> None:
    """The web note from code, unless the web sub-agent wrote one. Never waits on the checks."""
    facts_fn = getattr(case, "web_facts", None)
    if facts_fn is None:
        return
    try:
        facts = facts_fn()
    except Exception:
        return
    keep_note(case, note_path(case.case_id, WEB), web_text(facts), "policy")


def notes_view(case: Any) -> CaseNotes:
    """What the API serves: the notes in a fixed order, each with who wrote it."""
    order = (*STEMS, WALK, WEB, *MAIN_STEMS)
    kept = [case.notes[s] for s in order if s in case.notes]
    return CaseNotes(
        case_id=case.case_id,
        source=case.trace.source,
        notes=[
            CaseNote(
                path=n.path,
                stem=n.stem,
                agent=AGENT_NAMES.get(n.stem, "main"),
                text=n.text,
                written_by=n.by,
            )
            for n in kept
        ],
    )
