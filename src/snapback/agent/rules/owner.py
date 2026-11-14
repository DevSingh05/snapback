"""Owner of record (A19, #125): does the poster's claim to own the home fit the owner roll?

Lane D (D12) says who owns the home: a company, by name, or "a person", with no name. For a
person it also says, yes or no, whether the name the poster gave is the owner's; that
comparison happens inside lane D's adapter, so a person's name never reaches this module.

This module adds what the listing says:

- did the poster say they are the owner (intake reads that from their own words);
- for a company owner, is the company the poster named that company;
- does the owner have a rule in the published-rule table (`published.py`).

None of it is proof. A poster who says they own a home a company owns is "not confirmed" and
holds the case; it is never a red flag by itself (ruling, Sat 01:20) and never DON'T PAY. A
match never verifies either: the owner roll is public, so anyone can type the owner's name.
"""

from collections.abc import Sequence
from typing import Protocol

from snapback.agent.rules.contact import _company_words, _distance, same_company
from snapback.agent.rules.published import PUBLISHED_RULES, PublishedRuleRow
from snapback.contracts import OwnerKind, OwnerMatch, OwnerResult

MAX_ROWS = 200
MAX_ALIASES = 50


class OwnerClaims(Protocol):
    """What the listing says about owning the home (`intake.fields.ContactClaims`)."""

    company: str | None
    says_owner: bool


def _joined(name: str) -> str:
    """A company name as one run of letters: no "LLC", no punctuation, no spaces."""
    return "".join(_company_words(name[:200]))


def _near_miss(said: str, on_record: str) -> bool:
    """A different spelling of what may be the same name ("Fixure Homes", "Fixture Home").

    Too close to call a mismatch and too far to call a match (conductor, Sat 03:00): the
    answer for these is "not checked", never a flag.
    """
    ours, theirs = _joined(said), _joined(on_record)
    if not ours or not theirs or ours == theirs:
        return False
    allowed = 1 if min(len(ours), len(theirs)) < 8 else 2
    return abs(len(ours) - len(theirs)) <= allowed and _distance(ours, theirs) <= allowed


def company_match(said: str | None, on_record: str | None) -> OwnerMatch:
    """Is the company the poster named the company on the owner roll?

    "LLC", "Inc" and punctuation are ignored, and a shorter form that starts the same way
    matches. A near-miss spelling is not a "no": it is not checked.
    """
    same = same_company(said, on_record)
    if same is None:
        return OwnerMatch.NOT_CHECKED
    ours, theirs = _joined(said or ""), _joined(on_record or "")
    # "FixtureHomes" and "Fixture Homes" are one name written two ways.
    if same or (ours and ours == theirs):
        return OwnerMatch.YES
    return OwnerMatch.NOT_CHECKED if _near_miss(said or "", on_record or "") else OwnerMatch.NO


def published_rule(
    company: str | None, rules: Sequence[PublishedRuleRow] = PUBLISHED_RULES
) -> PublishedRuleRow | None:
    """The verified rule of the company that owns the home, or None. Never a guess.

    The company matches a row by its own name (as `same_company` reads names) or by one of
    the row's verified other names, compared whole.
    """
    if not company:
        return None
    whole = _joined(company)
    for row in rules[:MAX_ROWS]:
        if same_company(company, row.company):
            return row
        if whole and whole in {_joined(name) for name in row.also_known_as[:MAX_ALIASES]}:
            return row
    return None


def check_owner(
    claims: OwnerClaims,
    owner: OwnerResult | None,
    rules: Sequence[PublishedRuleRow] = PUBLISHED_RULES,
) -> OwnerResult | None:
    """Lane D's owner of record, with what the listing says added. None when there is none."""
    if owner is None:
        return None
    says_owner = bool(getattr(claims, "says_owner", False))

    if owner.kind is OwnerKind.PERSON:
        # The name comparison is lane D's, done where the name is. Nothing of a person is
        # kept here: a `company` on a person owner is dropped, and no table is consulted.
        return owner.model_copy(
            update={"company": None, "poster_says_owner": says_owner, "published_rule": None}
        )

    if not " ".join((owner.company or "").split()):
        # A company owner with no name to show: nothing was compared, so no line and no rule.
        return owner.model_copy(
            update={
                "poster_matches": OwnerMatch.NOT_CHECKED,
                "poster_says_owner": says_owner,
                "published_rule": None,
            }
        )

    matches = company_match(claims.company, owner.company)
    if matches is OwnerMatch.NOT_CHECKED and says_owner and not claims.company:
        # "I am the owner", and the owner is a company the poster does not name.
        matches = OwnerMatch.NO
    row = published_rule(owner.company, rules)
    return owner.model_copy(
        update={
            "poster_matches": matches,
            "poster_says_owner": says_owner,
            "published_rule": row.quoted() if row else None,
        }
    )
