"""Fields read from a listing's text by pattern: the rent, and what the poster says they are.

Contact claims are claims. They are never used to contact anyone, and a company name that
matches the record does not prove the poster works there.

Every quantifier here has an upper bound and every function bounds its text first (see
`normalise`), because the text is written by the person being checked.
"""

import re

from pydantic import BaseModel, Field

from snapback.agent.rules.apply import normalise
from snapback.agent.rules.contact import MAX_LINKS, host_of

MIN_RENT = 200
MAX_RENT = 30_000

_AMOUNT = r"(\d{1,2},\d{3}|\d{3,5})(?:\.\d{2})?"
_PER_MONTH = r"(?:/|per|a|each)\s{0,3}(?:mo\b|month)|monthly"
# In order of how sure the wording is that the figure is the rent.
_RENT_PATTERNS = [
    re.compile(rf"\$\s?{_AMOUNT}\s{{0,3}}(?:{_PER_MONTH})", re.IGNORECASE),
    re.compile(rf"\brent(?:\s{{1,3}}is)?\s{{0,3}}:?\s{{0,3}}\$\s?{_AMOUNT}", re.IGNORECASE),
    re.compile(rf"\b{_AMOUNT}\s{{0,3}}(?:{_PER_MONTH})", re.IGNORECASE),
]

_PHONE = re.compile(r"(?<![\d$])(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]\d{4}(?!\d)")
# The name part starts where a name can start, so a long run of letters with no "@" is tried
# once, not once per letter.
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,8}")
_COMPANY = re.compile(
    r"\b(?i:managed|listed|offered|leased|represented|presented) by\s{1,3}"
    r"([A-Z][\w&'-]{0,40}(?:\s{1,3}[A-Z&][\w&'-]{0,40}){0,5})"
)


# A link as written: with a scheme or "www.", or a bare name ending in a common ending. The
# bare form does not start inside an email address or a longer name.
_LINK = re.compile(r"(?:https?://|\bwww\.)([^\s/?#]{1,253})", re.IGNORECASE)
_ENDINGS = (
    "com|net|org|co|io|app|info|biz|us|me|xyz|online|site|live|link|page|shop|top|club|pro|"
    "rent|homes|apartments"
)
_BARE_LINK = re.compile(
    rf"(?<![\w.@/-])((?:[\w-]{{1,63}}\.){{1,4}}(?:{_ENDINGS}))(?![\w-])", re.IGNORECASE
)

_UNIT = re.compile(
    r"\b(?:unit|apt|apartment|suite|ste)\b\.?\s{0,3}#?\s{0,3}([a-z]?\d{1,5}[a-z]?)\b"
    r"|(?<![\w#])#\s{0,3}(\d{1,5}[a-z]?)\b",
    re.IGNORECASE,
)
_BEDS = re.compile(
    r"(?<![\w.$,])(\d{1,2})\s{0,3}-?\s{0,3}(?:bed(?:room)?s?|br|bd|bdrm)\b|\b(studio)\b",
    re.IGNORECASE,
)
MAX_BEDS = 10


class ContactClaims(BaseModel):
    """What the poster says about who they are. Unchecked."""

    company: str | None = None
    phones: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)  # where each link goes, not the full link


def extract_rent(text: str) -> int | None:
    """The monthly rent the listing states, in whole dollars, or None if it states none."""
    text = normalise(text)
    for pattern in _RENT_PATTERNS:
        for match in pattern.finditer(text):
            rent = int(match.group(1).replace(",", ""))
            if MIN_RENT <= rent <= MAX_RENT:
                return rent
    return None


def extract_unit(text: str) -> str | None:
    """The unit the listing names ("Unit 204", "Apt #4B"), upper-cased, or None."""
    found = _UNIT.search(normalise(text))
    return (found.group(1) or found.group(2)).upper() if found else None


def extract_beds(text: str) -> int | None:
    """The bedroom count the listing states. A studio is 0. None if it states none."""
    for found in _BEDS.finditer(normalise(text)):
        if found.group(2):
            return 0
        beds = int(found.group(1))
        if beds <= MAX_BEDS:
            return beds
    return None


def _links(text: str) -> list[str]:
    """Where each link in the text goes, in the order written, each one once."""
    found = [(m.start(1), m.group(1)) for m in _LINK.finditer(text)]
    found += [(m.start(1), m.group(1)) for m in _BARE_LINK.finditer(text)]
    hosts: list[str] = []
    for _, written in sorted(found):
        host = host_of(written)
        if host and host not in hosts:
            hosts.append(host)
        if len(hosts) == MAX_LINKS:
            break
    return hosts


def extract_contacts(text: str) -> ContactClaims:
    text = normalise(text)
    company = _COMPANY.search(text)
    return ContactClaims(
        company=company.group(1).strip() if company else None,
        phones=[match.group(0).strip() for match in _PHONE.finditer(text)],
        emails=[match.group(0).rstrip(".") for match in _EMAIL.finditer(text)],
        links=_links(text),
    )
