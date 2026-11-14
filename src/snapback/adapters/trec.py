"""D10 (lane D, #128): does a poster who claims to be a real estate agent hold a Texas license?

TREC's public licensee data on Socrata (`data.texas.gov/resource/s7ft-44qi.json`, no key). Field
names were read from the source (`$limit=1`), not guessed. Every lookup has one 5 s deadline for
the whole call (headers included), and any failure is NOT_CHECKED.

NOT_FOUND turns into a red flag against a person, and flagging a real agent is the one outcome we
cannot ship. So NOT_FOUND is rare by design (ruling on #134, 02:50). It needs ALL of:
  (a) an explicit, well-formed claim: "I'm / My name is <First Last>, a licensed agent" (realtor,
      broker or locator), or a "<First Last>, Realtor" signature with a separator;
  (b) a name of exactly two tokens, neither a company word nor a particle;
  (c) zero ACTIVE licensees with that last name, and zero active ones whose last name ends with
      it (a compound surname such as "De La X").
Anyone active sharing the last name, a looser claim, a longer name, more than 25 rows, or any
failure is NOT_CHECKED. LICENSED needs an active licensee with that last name and a compatible
first name (exact, initial, nickname, middle name); the sponsor is named only when exactly one
person fits and the sponsor is a company.

A brokerage the poster names ("listed by Fxample Realty") is looked up among Broker Company
licenses: an active exact match is LICENSED, zero rows on the name's prefix is NOT_FOUND, and
anything in between is NOT_CHECKED.

Never kept anywhere (result, cache, trace, log): a license number or any person's name. The cache
under `data/trec/` is keyed by a hash of the query and holds only the answer; NOT_FOUND answers
expire after 24 h.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
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
MAX_BODY_BYTES = 2 * 1024 * 1024  # 26 rows are a few KB
READ_SLICE_S = 2.0
NOT_FOUND_TTL_S = 24 * 3600
_monotonic = time.monotonic  # replaced in tests
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="trec")

_SP = r"[ \t]+"  # spaces and tabs only: a name never runs across a line break
_TOKEN = r"[A-Z][A-Za-z'\-]{1,30}"
_FIRST = r"[A-Z](?:[A-Za-z'\-]{1,30}|\.)"  # a first name may be an initial: "F."
_NAME = r"(" + _FIRST + r")" + _SP + r"(" + _TOKEN + r")"
_ROLE = r"(?i:(?:licensed[ \t]+)?(?:real[ \t]+estate[ \t]+)?(agent|realtor|broker|locator))\b"
_ARTICLE = r"(?i:(?:a|an|the|your)[ \t]+)"
# a role word only counts after a separator or an article ("Email Listing Agent" is not a claim)
_SEP = (
    r"(?:,[ \t]*"
    + _ARTICLE
    + r"?|[ \t]*[|\-\u2013\u2014][ \t]*"
    + _ARTICLE
    + r"?|"
    + _SP
    + _ARTICLE
    + r")"
)

# Strict claims, the only ones that can end NOT_FOUND
_STRICT_INTRO = re.compile(
    r"(?i:\b(?:i'?m|i[ \t]+am|my[ \t]+name[ \t]+is))"
    + _SP
    + _NAME
    + r","
    + r"[ \t]*"
    + _ARTICLE
    + r"?"
    + _ROLE
)
_STRICT_SIGNATURE = re.compile(
    r"(?:^|[\n|\-\u2013\u2014])[ \t]*" + _NAME + r",[ \t]*" + _ROLE + r"[ \t.!]*(?:$|\n)"
)
# Looser claims: can be LICENSED, never NOT_FOUND
_NAMED_ROLE = re.compile(_NAME + _SEP + _ROLE)
_LABEL = re.compile(r"(?i:\b(agent|realtor|broker|locator))[ \t]*:[ \t]*" + _NAME)
_SELF_ROLE = re.compile(r"(?i:\b(?:i'?m|i[ \t]+am|as))" + _SP + _ARTICLE + r"?" + _ROLE)
_ALSO_ROLE = re.compile(r"(?i:\b(?:and|also)(?:[ \t]+also)?)" + _SP + _ARTICLE + _ROLE)
_MY_NAME = re.compile(r"(?i:\bmy[ \t]+name[ \t]+is)" + _SP + _NAME)
_SIGNATURE = re.compile(r"[-\u2013\u2014][ \t]*" + _NAME + r"[ \t]*$")
_THIS_IS = re.compile(r"(?i:\bthis[ \t]+is)" + _SP + _NAME)
_IM = re.compile(r"(?i:\b(?:i'?m|i[ \t]+am))" + _SP + _NAME)
_COMPANY = re.compile(
    r"(?i:\b(?:listed|managed|marketed|represented|offered)[ \t]+by)[ \t]+"
    r"([A-Z][\w&'\-]*(?:[ \t]+(?:[A-Z&][\w&'\-]*|of|and)){0,6})"
)

# Words that start labels and slogans, never a person's name
_STOPWORDS = {
    "REAL", "ESTATE", "APARTMENT", "APARTMENTS", "LICENSED", "YOUR", "OUR", "PLEASE",
    "CONTACT", "FREE", "VERY", "USE", "CALL", "TEXT", "EMAIL", "THE", "THIS", "BEST", "TOP",
    "LOCAL", "PROFESSIONAL", "EXPERIENCED", "CERTIFIED", "TRUSTED", "PROPERTY", "LEASING",
    "LISTING", "RENTAL", "RENTALS", "RENT", "FAST", "HOME", "HOUSE", "TEXAS", "HOUSTON",
    "DALLAS", "AUSTIN", "SAN", "NEW", "LUXURY", "AFFORDABLE", "SO", "SUPER", "REALLY", "HAPPY",
    "EXCITED", "AVAILABLE", "NOW", "TODAY", "HELLO", "HI", "DEAR", "THANKS", "THANK", "AN", "A",
    "LANDLORD", "PAYS", "OWNER", "TENANT",
}  # fmt: skip
# A trailing company word makes it a company, never a person
_COMPANY_WORDS = {
    "REALTY", "REALTORS", "PROPERTIES", "GROUP", "HOMES", "MANAGEMENT", "TEAM", "PARTNERS",
    "ASSOCIATES", "LLC", "INC", "CO", "CORP", "COMPANY", "LTD", "LP", "LLP", "PLLC",
    "BROKERAGE", "REALTY.", "INVESTMENTS", "LIVING", "RESIDENTIAL",
}  # fmt: skip
_PARTICLES = {"DE", "LA", "DEL", "DELA", "DI", "DA", "DOS", "DAS", "VAN", "VON", "LE", "ST", "MAC"}
_COMPANY_SUFFIXES = {"LLC", "INC", "LP", "LLP", "CO", "LTD", "PLLC", "CORP", "COMPANY"}
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
    {"SAMUEL", "SAM"},
    {"SAMANTHA", "SAM"},
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


@dataclass(frozen=True)
class Claim:
    role: str
    first: str | None = None
    last: str | None = None
    company: str | None = None
    strict: bool = False  # only a strict claim can end NOT_FOUND


def _is_person(first: str, last: str) -> bool:
    """Two tokens, neither a slogan word, a company word nor a particle."""
    f, ln = first.upper().rstrip("."), last.upper()
    bad = _STOPWORDS | _COMPANY_WORDS | _PARTICLES
    return f not in bad and ln not in bad


def _name_in(text: str) -> tuple[str, str] | None:
    """The poster's own name, most reliable source first: 'my name is', a signature at the end,
    'this is', and only then a bare "I'm X Y" (often 'I'm Very Excited')."""
    for found in (
        _MY_NAME.finditer(text),
        _SIGNATURE.finditer(text.strip()),
        _THIS_IS.finditer(text),
        _IM.finditer(text),
    ):
        for m in found:
            if _is_person(m.group(1), m.group(2)):
                return m.group(1), m.group(2)
    return None


def detect_claim(text: str) -> Claim | None:
    """The poster's own claim to be an agent, broker or locator (and the name they give), or a
    brokerage they say lists the home. Only the first 2,000 characters are read, and no pattern
    can backtrack badly."""
    text = text[:MAX_TEXT]
    for pattern in (_STRICT_INTRO, _STRICT_SIGNATURE):
        for m in pattern.finditer(text):
            if _is_person(m.group(1), m.group(2)):
                role = _ROLE_OF[m.group(3).lower()]
                return Claim(role, m.group(1), m.group(2), strict=True)
    for pattern, role_group, first_group in ((_NAMED_ROLE, 3, 1), (_LABEL, 1, 2)):
        for m in pattern.finditer(text):
            role = _ROLE_OF[m.group(role_group).lower()]
            if role == "locator" and pattern is _NAMED_ROLE:
                continue  # "Free Apartment Locator" is a service label, not a self-claim
            if _is_person(m.group(first_group), m.group(first_group + 1)):
                return Claim(role, m.group(first_group), m.group(first_group + 1))
    m = _SELF_ROLE.search(text) or _ALSO_ROLE.search(text)
    if m:
        role = _ROLE_OF[m.group(1).lower()]
        name = _name_in(text)
        return Claim(role, *name) if name else Claim(role)
    m = _COMPANY.search(text)
    if m:
        return Claim("company", company=m.group(1).strip())
    return None


def _active(status: str) -> bool:
    s = status.strip()
    return s == "Active" or s.endswith("- Active")


def _first_names(name: str) -> set[str]:
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
    return re.sub(r"[%_]", "", value.upper().replace("'", "''"))


def _read_rows(where: str, client: httpx.Client, deadline: float) -> list[dict] | None:
    with client.stream(
        "GET",
        TREC_URL,
        params={"$where": where, "$limit": str(MAX_ROWS + 1)},
        timeout=httpx.Timeout(TIMEOUT_S, read=min(READ_SLICE_S, TIMEOUT_S)),
    ) as r:
        if r.status_code != 200:
            return None
        chunks: list[bytes] = []
        size = 0
        for chunk in r.iter_bytes():
            size += len(chunk)
            if size > MAX_BODY_BYTES or _monotonic() > deadline:
                return None
            chunks.append(chunk)
    rows = json.loads(b"".join(chunks))
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else None


def _get_rows(where: str, client: httpx.Client, deadline: float) -> list[dict] | None:
    """One query, on a worker thread, waited for only until the shared deadline: slow headers
    are bounded too, since httpx timeouts apply per phase."""
    remaining = deadline - _monotonic()
    if remaining <= 0:
        return None
    future = _POOL.submit(_read_rows, where, client, deadline)
    try:
        return future.result(timeout=remaining)
    except (FuturesTimeout, httpx.HTTPError, ValueError):
        return None


Answer = tuple[LicenseStatus, str | None]
_NOT_CHECKED: Answer = (LicenseStatus.NOT_CHECKED, None)


def _lookup_person(claim: Claim, client: httpx.Client, deadline: float) -> Answer:
    first, last = claim.first or "", claim.last or ""
    rows = _get_rows(f"upper(last_name)='{_soql(last)}'", client, deadline)
    if rows is None or len(rows) > MAX_ROWS:
        return _NOT_CHECKED  # failed, or too common a name to say
    active = [row for row in rows if _active(str(row.get("status", "")))]
    fits = [row for row in active if _compatible(first, row)]
    if fits:
        people = {
            (str(r.get("first_name", "")).upper(), str(r.get("middle_name", "")).upper())
            for r in fits
        }
        if len(people) > 1:
            return LicenseStatus.LICENSED, None  # several people fit: name no sponsor
        sponsor = next(
            (
                str(row["related_license_full_name"]).strip()
                for row in fits
                if row.get("related_license_type") == "Broker Company"
                and row.get("related_license_full_name")
            ),
            None,
        )
        return LicenseStatus.LICENSED, sponsor
    if not claim.strict or active:
        return _NOT_CHECKED  # someone active shares the name, or the claim is not explicit
    compound = _get_rows(f"upper(last_name) like '% {_soql(last)}'", client, deadline)
    if compound is None or len(compound) > MAX_ROWS:
        return _NOT_CHECKED
    if any(_active(str(row.get("status", ""))) for row in compound):
        return _NOT_CHECKED  # "De La X": a compound surname ending with the claimed one
    return LicenseStatus.NOT_FOUND, None


def _lookup_company(company: str, client: httpx.Client, deadline: float) -> Answer:
    key = _company_key(company)
    if not key:
        return _NOT_CHECKED
    prefix = _soql(key.split(" ")[0])
    rows = _get_rows(
        f"license_type='Broker Company' AND upper(full_name) like '{prefix}%'", client, deadline
    )
    if rows is None or len(rows) > MAX_ROWS:
        return _NOT_CHECKED
    if not rows:
        return LicenseStatus.NOT_FOUND, None  # no brokerage starts with that name at all
    same = [row for row in rows if _company_key(str(row.get("full_name", ""))) == key]
    if any(_active(str(row.get("status", ""))) for row in same):
        return LicenseStatus.LICENSED, None
    return _NOT_CHECKED  # near misses or inactive: not enough to accuse anyone


_shared_client: httpx.Client | None = None


def _client() -> httpx.Client:
    """One client per process: its connection pool is reused, so only the first lookup pays for
    setting up the connection (about 5 s measured on one Windows machine, 0.1 to 0.4 s after)."""
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.Client()
    return _shared_client


def _read_cache(path: Path) -> Answer | None:
    try:
        if not path.is_file():
            return None
        saved = json.loads(path.read_text(encoding="utf-8"))
        status = LicenseStatus(saved["status"])
        if status is LicenseStatus.NOT_FOUND and time.time() - saved["at"] > NOT_FOUND_TTL_S:
            return None  # a NOT_FOUND is looked up again after 24 h
        return status, saved.get("sponsor")
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(path: Path, answer: Answer) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"status": answer[0].value, "sponsor": answer[1], "at": time.time()}),
            encoding="utf-8",
        )
    except OSError:
        pass  # a read-only data dir loses the cache, never the answer


def check_license(
    text: str, *, client: httpx.Client | None = None, cache_dir: Path | None = None
) -> LicenseResult:
    claim = detect_claim(text)
    if claim is None:
        return LicenseResult(status=LicenseStatus.NOT_CHECKED)
    if claim.company is None and (not claim.first or not claim.last):
        return LicenseResult(status=LicenseStatus.NOT_CHECKED, claimed_role=claim.role)

    if claim.company:
        query = f"company|{claim.company.upper()}"
    else:
        query = (
            f"person|{int(claim.strict)}|{(claim.first or '').upper()}|{(claim.last or '').upper()}"
        )
    cache_dir = cache_dir or resolve_data_dir(get_settings().snapback_data_dir) / "trec"
    cached = cache_dir / f"{hashlib.sha256(query.encode()).hexdigest()[:32]}.json"
    answer = _read_cache(cached)
    if answer is None:
        deadline = _monotonic() + TIMEOUT_S
        http = client or _client()
        if claim.company:
            answer = _lookup_company(claim.company, http, deadline)
        else:
            answer = _lookup_person(claim, http, deadline)
        if answer[0] is not LicenseStatus.NOT_CHECKED:
            _write_cache(cached, answer)

    status, sponsor = answer
    return LicenseResult(
        status=status,
        claimed_role=claim.role,
        sponsor_broker=sponsor if status is LicenseStatus.LICENSED else None,
    )
