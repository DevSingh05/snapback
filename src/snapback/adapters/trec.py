"""D10 (lane D, #128): does a poster who claims to be a real estate agent hold a Texas license?

Runs only when the poster's own words claim the role (agent, realtor, broker or locator) and
give a name. One filtered query to TREC's public licensee data on Socrata
(`data.texas.gov/resource/s7ft-44qi.json`, no key), a 5 s budget, no retry on 429. Field names
were read from the source (`$limit=1`), not guessed: `first_name`, `last_name`, `status`,
`related_license_type`, `related_license_full_name`.

- An ACTIVE license (status "Active", or one of the "... - Active" variants) -> LICENSED, with
  the sponsoring broker only when the sponsor is a company.
- A claim and no active license under that name -> NOT_FOUND.
- No claim, no name, or any failure (timeout, error, rate limit) -> NOT_CHECKED.

Never kept anywhere (result, cache, trace, log): the license number or any person's name. The
cache under `data/trec/` is keyed by a hash of the name and holds only the answer.
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

_NAME = r"([A-Z][A-Za-z'\-]{1,30})\s+([A-Z][A-Za-z'\-]{1,30})"
_ROLE = r"(?i:(?:licensed\s+)?(?:real\s+estate\s+)?(agent|realtor|broker|locator))\b"
_ARTICLE = r"(?i:(?:a|an|the|your)\s+)?"
# "I'm a licensed realtor", "I am the broker"
_SELF_ROLE = re.compile(r"(?i:\b(?:i'?m|i\s+am|as)\s+)" + _ARTICLE + _ROLE)
# "Fxname Fxperson, a licensed realtor"
_NAMED_ROLE = re.compile(_NAME + r",?\s+" + _ARTICLE + _ROLE)
# "Broker: Fxname Fxperson"
_LABEL = re.compile(r"(?i:\b(agent|realtor|broker|locator))\s*:\s*" + _NAME)
# "My name is Fxname Fxperson", "I'm Fxname Fxperson"
_NAME_INTRO = re.compile(r"(?i:\b(?:my\s+name\s+is|i'?m|i\s+am|this\s+is)\s+)" + _NAME)
# a signature at the end: "- Fxname Fxperson"
_SIGNATURE = re.compile(r"[-\u2013\u2014]\s*" + _NAME + r"\s*$")

_shared_client: httpx.Client | None = None


def _client() -> httpx.Client:
    """One client per process: its connection pool is reused, so only the first lookup pays for
    setting up the connection (about 5 s measured on one Windows machine, 0.1 to 0.4 s after)."""
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.Client()
    return _shared_client


_ROLE_OF = {"realtor": "agent", "agent": "agent", "broker": "broker", "locator": "locator"}


@dataclass(frozen=True)
class Claim:
    role: str
    first: str | None = None
    last: str | None = None


def detect_claim(text: str) -> Claim | None:
    """The poster's own claim to be an agent, broker or locator, and the name they give.
    Bounded: only the first 2,000 characters are read, and no pattern can backtrack badly."""
    text = text[:MAX_TEXT]
    for pattern, role_group, first_group in ((_NAMED_ROLE, 3, 1), (_LABEL, 1, 2)):
        m = pattern.search(text)
        if m:
            role = _ROLE_OF[m.group(role_group).lower()]
            return Claim(role, m.group(first_group), m.group(first_group + 1))
    m = _SELF_ROLE.search(text)
    if not m:
        return None
    role = _ROLE_OF[m.group(1).lower()]
    named = _NAME_INTRO.search(text) or _SIGNATURE.search(text.strip())
    return Claim(role, named.group(1), named.group(2)) if named else Claim(role)


def _active(status: str) -> bool:
    s = status.strip()
    return s == "Active" or s.endswith("- Active")


def _cache_path(cache_dir: Path, first: str, last: str) -> Path:
    key = hashlib.sha256(f"{first.upper()}|{last.upper()}".encode()).hexdigest()[:32]
    return cache_dir / f"{key}.json"


def _soql(value: str) -> str:
    return value.upper().replace("'", "''")


def _lookup(first: str, last: str, client: httpx.Client) -> tuple[bool, str | None] | None:
    """(an active license exists, the sponsoring broker company or None). None: lookup failed."""
    where = f"upper(first_name)='{_soql(first)}' AND upper(last_name)='{_soql(last)}'"
    try:
        r = client.get(
            TREC_URL,
            params={"$where": where, "$limit": str(MAX_ROWS)},
            timeout=httpx.Timeout(TIMEOUT_S),
        )
        if r.status_code != 200:
            return None
        rows = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(rows, list):
        return None
    active = [row for row in rows if isinstance(row, dict) and _active(str(row.get("status", "")))]
    sponsor = next(
        (
            str(row["related_license_full_name"]).strip()
            for row in active
            if row.get("related_license_type") == "Broker Company"
            and row.get("related_license_full_name")
        ),
        None,
    )
    return bool(active), sponsor


def check_license(
    text: str, *, client: httpx.Client | None = None, cache_dir: Path | None = None
) -> LicenseResult:
    claim = detect_claim(text)
    if claim is None:
        return LicenseResult(status=LicenseStatus.NOT_CHECKED)
    if not claim.first or not claim.last:
        return LicenseResult(status=LicenseStatus.NOT_CHECKED, claimed_role=claim.role)

    cache_dir = cache_dir or resolve_data_dir(get_settings().snapback_data_dir) / "trec"
    cached = _cache_path(cache_dir, claim.first, claim.last)
    found: tuple[bool, str | None] | None = None
    try:
        if cached.is_file():
            saved = json.loads(cached.read_text(encoding="utf-8"))
            found = (bool(saved["active"]), saved.get("sponsor"))
    except (OSError, ValueError, KeyError, TypeError):
        found = None
    if found is None:
        found = _lookup(claim.first, claim.last, client or _client())
        if found is None:
            return LicenseResult(status=LicenseStatus.NOT_CHECKED, claimed_role=claim.role)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps({"active": found[0], "sponsor": found[1]}), encoding="utf-8")

    active, sponsor = found
    if not active:
        return LicenseResult(status=LicenseStatus.NOT_FOUND, claimed_role=claim.role)
    return LicenseResult(
        status=LicenseStatus.LICENSED, claimed_role=claim.role, sponsor_broker=sponsor
    )
