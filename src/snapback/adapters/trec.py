"""D10 (lane D, #128): does a poster who claims to be a real estate agent hold a Texas license?

Runs only when the poster's own words claim the role (agent, realtor, broker or locator) and
give a name, or name a brokerage or management company ("listed by Fxample Realty"). One query
to TREC's public licensee data on Socrata (`data.texas.gov/resource/s7ft-44qi.json`, no key),
5 s budget, no retry on 429. Field names were read from the source (`$limit=1`), not guessed.

A false NOT_FOUND becomes a red flag against a real agent, so it must be rare (#41 ruling):
- A person is looked up by LAST name only, then first names are compared allowing initials,
  common nicknames and middle names.
- LICENSED: an ACTIVE license (status "Active" or a "... - Active" variant) with a compatible
  first name. The sponsoring broker is named only when the sponsor is a company.
- NOT_FOUND: a claim, and no active licensee with that last name and a compatible first name
  (inactive or expired matches only count as not found).
- NOT_CHECKED: no claim, no name, more than 25 rows, an initial that fits different people, or
  any failure (timeout, error, rate limit).
- A named company is looked up among Broker Company licenses by its name, with the same outcomes.

Never kept anywhere (result, cache, trace, log): the license number or any person's name. The
cache under `data/trec/` is keyed by a hash of the query and holds only the answer.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from snapback.contracts import LicenseResult, LicenseStatus
from snapback.safety.paths import resolve_data_dir
from snapback.settings import get_settings

TREC_URL = "https://data.texas.gov/resource/s7ft-44qi.json"
TIMEOUT_S = 5.0
MAX_TEXT = 2_000  # the claim is in the poster's message, not in a 2 MB paste
MAX_ROWS = 25

# A first name may be an initial ("F."); a last name is a word.
_NAME = r"([A-Z](?:[A-Za-z'\-]{1,30}|\.))\s+([A-Z][A-Za-z'\-]{1,30})"
_ROLE = r"(?i:(?:licensed\s+)?(?:real\s+estate\s+)?(agent|realtor|broker|locator))\b"
_ARTICLE = r"(?i:(?:a|an|the|your)\s+)?"
_SELF_ROLE = re.compile(r"(?i:\b(?:i'?m|i\s+am|as)\s+)" + _ARTICLE + _ROLE)
_NAMED_ROLE = re.compile(_NAME + r",?\s+" + _ARTICLE + _ROLE)
_LABEL = re.compile(r"(?i:\b(agent|realtor|broker|locator))\s*:\s*" + _NAME)
_NAME_INTRO = re.compile(r"(?i:\b(?:my\s+name\s+is|i'?m|i\s+am|this\s+is)\s+)" + _NAME)
_SIGNATURE = re.compile(r"[-\u2013\u2014]\s*" + _NAME + r"\s*$")
# "Listed by Fxample Realty Group" (capitalised words; a sentence's full stop ends it)
_COMPANY = re.compile(
    r"(?i:\b(?:listed|managed|marketed|represented|offered)\s+by\s+)"
    r"([A-Z][\w&'\-]*(?:\s+(?:[A-Z&][\w&'\-]*|of|and)){0,6})"
)

_ROLE_OF = {"realtor": "agent", "agent": "agent", "broker": "broker", "locator": "locator"}
_NICKNAMES = [
    {"MICHAEL", "MIKE", "MICKEY"},
    {"ROBERT", "BOB", "ROB", "BOBBY", "ROBBIE"},
    {"ELIZABETH", "LIZ", "BETH", "LIZZIE", "BETTY", "ELIZA"},
    {"WILLIAM", "BILL", "WILL", "BILLY", "LIAM"},
    {"RICHARD", "RICK", "RICH", "DICK", "RICKY"},
    {"JAMES", "JIM", "JIMMY", "JAMIE"},
    {"JOHN", "JACK", "JOHNNY"},
    {"JOSEPH", "JOE", "JOEY"},
    {"KATHERINE", "CATHERINE", "KATE", "KATIE", "KATHY", "CATHY", "KAT"},
    {"MARGARET", "MAGGIE", "PEGGY", "MEG"},
    {"JENNIFER", "JEN", "JENNY"},
    {"CHRISTOPHER", "CHRIS"},
    {"CHRISTINA", "CHRISTINE", "CHRIS", "TINA"},
    {"ANTHONY", "TONY"},
    {"DANIEL", "DAN", "DANNY"},
    {"DAVID", "DAVE"},
    {"EDWARD", "ED", "EDDIE", "TED"},
    {"THOMAS", "TOM", "TOMMY"},
    {"STEVEN", "STEPHEN", "STEVE"},
    {"PATRICIA", "PAT", "PATTY", "TRISH"},
    {"ALEXANDER", "ALEX", "XANDER"},
    {"ALEXANDRA", "ALEX", "SASHA"},
    {"SAMUEL", "SAM", "SAMANTHA"},
    {"BENJAMIN", "BEN"},
    {"NICHOLAS", "NICK"},
    {"JOSHUA", "JOSH"},
    {"MATTHEW", "MATT"},
    {"ANDREW", "ANDY", "DREW"},
    {"DEBORAH", "DEBRA", "DEB", "DEBBIE"},
    {"SUSAN", "SUE", "SUZY"},
    {"ROSA", "ROSIE"},
    {"JOSE", "PEPE"},
    {"FRANCISCO", "PANCHO", "FRANK", "PACO"},
]
_COMPANY_SUFFIXES = {"LLC", "INC", "LP", "LLP", "CO", "LTD", "PLLC", "CORP", "COMPANY"}


@dataclass(frozen=True)
class Claim:
    role: str
    first: str | None = None
    last: str | None = None
    company: str | None = None


def detect_claim(text: str) -> Claim | None:
    """The poster's own claim to be an agent, broker or locator (and the name they give), or a
    brokerage they say lists the home. Only the first 2,000 characters are read, and no pattern
    can backtrack badly."""
    text = text[:MAX_TEXT]
    for pattern, role_group, first_group in ((_NAMED_ROLE, 3, 1), (_LABEL, 1, 2)):
        m = pattern.search(text)
        if m:
            role = _ROLE_OF[m.group(role_group).lower()]
            return Claim(role, m.group(first_group), m.group(first_group + 1))
    m = _SELF_ROLE.search(text)
    if m:
        role = _ROLE_OF[m.group(1).lower()]
        named = _NAME_INTRO.search(text) or _SIGNATURE.search(text.strip())
        return Claim(role, named.group(1), named.group(2)) if named else Claim(role)
    m = _COMPANY.search(text)
    if m:
        return Claim("company", company=m.group(1).strip())
    return None


def _active(status: str) -> bool:
    s = status.strip()
    return s == "Active" or s.endswith("- Active")


def _first_names(name: str) -> set[str]:
    """A first name and its common nicknames, upper case."""
    name = name.upper()
    out = {name}
    for group in _NICKNAMES:
        if name in group:
            out |= group
    return out


def _compatible(claimed: str, row: dict) -> bool:
    """Could this licensee be the person who signed with `claimed`? Initials, nicknames, the
    middle name, and a shortened first name ('Chris' for 'Christopher') all count."""
    first = str(row.get("first_name") or "").upper().strip()
    middle = str(row.get("middle_name") or "").upper().strip()
    claimed = claimed.upper().rstrip(".")
    if len(claimed) == 1:
        return first.startswith(claimed) or middle.startswith(claimed)
    for candidate in (first, middle):
        if not candidate:
            continue
        if candidate in _first_names(claimed):
            return True
        if len(claimed) >= 3 and (candidate.startswith(claimed) or claimed.startswith(candidate)):
            return True
    return False


def _company_key(name: str) -> str:
    words = re.findall(r"[A-Z0-9&]+", name.upper())
    return " ".join(w for w in words if w not in _COMPANY_SUFFIXES)


def _soql(value: str) -> str:
    return value.upper().replace("'", "''")


def _get_rows(where: str, client: httpx.Client) -> list[dict] | None:
    try:
        r = client.get(
            TREC_URL,
            params={"$where": where, "$limit": str(MAX_ROWS + 1)},
            timeout=httpx.Timeout(TIMEOUT_S),
        )
        if r.status_code != 200:
            return None
        rows = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(rows, list):
        return None
    return [row for row in rows if isinstance(row, dict)]


Answer = tuple[LicenseStatus, str | None]


def _lookup_person(first: str, last: str, client: httpx.Client) -> Answer:
    rows = _get_rows(f"upper(last_name)='{_soql(last)}'", client)
    if rows is None or len(rows) > MAX_ROWS:
        return LicenseStatus.NOT_CHECKED, None  # failed, or too common a name to say
    fits = [row for row in rows if _compatible(first, row)]
    if len(first.rstrip(".")) == 1:
        people = {
            (str(r.get("first_name", "")).upper(), str(r.get("middle_name", "")).upper())
            for r in fits
        }
        if len(people) > 1:
            return LicenseStatus.NOT_CHECKED, None  # an initial that fits different people
    active = [row for row in fits if _active(str(row.get("status", "")))]
    if not active:
        return LicenseStatus.NOT_FOUND, None
    sponsor = next(
        (
            str(row["related_license_full_name"]).strip()
            for row in active
            if row.get("related_license_type") == "Broker Company"
            and row.get("related_license_full_name")
        ),
        None,
    )
    return LicenseStatus.LICENSED, sponsor


def _lookup_company(company: str, client: httpx.Client) -> Answer:
    key = _company_key(company)
    if not key:
        return LicenseStatus.NOT_CHECKED, None
    prefix = re.sub(r"[%_']", "", key.split(" ")[0])
    rows = _get_rows(f"license_type='Broker Company' AND upper(full_name) like '{prefix}%'", client)
    if rows is None or len(rows) > MAX_ROWS:
        return LicenseStatus.NOT_CHECKED, None
    same = [row for row in rows if _company_key(str(row.get("full_name", ""))) == key]
    if any(_active(str(row.get("status", ""))) for row in same):
        return LicenseStatus.LICENSED, None
    return LicenseStatus.NOT_FOUND, None


_shared_client: httpx.Client | None = None


def _client() -> httpx.Client:
    """One client per process: its connection pool is reused, so only the first lookup pays for
    setting up the connection (about 5 s measured on one Windows machine, 0.1 to 0.4 s after)."""
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.Client()
    return _shared_client


def check_license(
    text: str, *, client: httpx.Client | None = None, cache_dir: Path | None = None
) -> LicenseResult:
    claim = detect_claim(text)
    if claim is None:
        return LicenseResult(status=LicenseStatus.NOT_CHECKED)
    if claim.company is None and (not claim.first or not claim.last):
        return LicenseResult(status=LicenseStatus.NOT_CHECKED, claimed_role=claim.role)

    query = (
        f"company|{claim.company.upper()}"
        if claim.company
        else (f"person|{claim.first.upper()}|{claim.last.upper()}")
    )
    cache_dir = cache_dir or resolve_data_dir(get_settings().snapback_data_dir) / "trec"
    cached = cache_dir / f"{hashlib.sha256(query.encode()).hexdigest()[:32]}.json"
    answer: Answer | None = None
    try:
        if cached.is_file():
            saved = json.loads(cached.read_text(encoding="utf-8"))
            answer = (LicenseStatus(saved["status"]), saved.get("sponsor"))
    except (OSError, ValueError, KeyError, TypeError):
        answer = None
    if answer is None:
        http = client or _client()
        if claim.company:
            answer = _lookup_company(claim.company, http)
        else:
            answer = _lookup_person(claim.first or "", claim.last or "", http)
        if answer[0] is not LicenseStatus.NOT_CHECKED:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(
                json.dumps({"status": answer[0].value, "sponsor": answer[1]}), encoding="utf-8"
            )

    status, sponsor = answer
    return LicenseResult(
        status=status,
        claimed_role=claim.role,
        sponsor_broker=sponsor if status is LicenseStatus.LICENSED else None,
    )
