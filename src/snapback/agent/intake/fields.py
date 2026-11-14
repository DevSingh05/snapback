"""Fields read from a listing's text by pattern: the rent, and what the poster says they are.

Contact claims are claims. They are never used to contact anyone, and a company name that
matches the record does not prove the poster works there.

Every quantifier here has an upper bound and every function bounds its text first (see
`normalise`), because the text is written by the person being checked.
"""

import re

from pydantic import BaseModel, Field

from snapback.agent.rules.apply import normalise

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


class ContactClaims(BaseModel):
    """What the poster says about who they are. Unchecked."""

    company: str | None = None
    phones: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)


def extract_rent(text: str) -> int | None:
    """The monthly rent the listing states, in whole dollars, or None if it states none."""
    text = normalise(text)
    for pattern in _RENT_PATTERNS:
        for match in pattern.finditer(text):
            rent = int(match.group(1).replace(",", ""))
            if MIN_RENT <= rent <= MAX_RENT:
                return rent
    return None


def extract_contacts(text: str) -> ContactClaims:
    text = normalise(text)
    company = _COMPANY.search(text)
    return ContactClaims(
        company=company.group(1).strip() if company else None,
        phones=[match.group(0).strip() for match in _PHONE.finditer(text)],
        emails=[match.group(0).rstrip(".") for match in _EMAIL.finditer(text)],
    )
