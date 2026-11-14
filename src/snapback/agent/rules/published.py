"""What big owners publish about how they rent, as data (A19, #125).

Some companies that own many homes say in public where they take applications and money. When
the owner of record of a home is one of them, the card quotes that rule, so the renter knows
where the real door is.

How to read a row:

- `company`: the company, as it names itself.
- `rule`: its own words, quoted exactly, about where it takes applications and money. Short:
  a sentence or part of one, never a passage.
- `source_url`: the page it is published on. The company's own site.
- `checked_on`: the day one of us read the rule on that page.
- `also_known_as`: other names the county owner roll uses for the same company (the legal
  entities that hold the deeds). Only names someone has verified. Empty is fine.

VERIFIED ROWS ONLY. A row goes in after someone has read the rule at `source_url` and written
down the day. An owner with no row gets no rule: nothing is guessed, and nothing is carried
over from a similar company. To add a row, read the page, quote it, and date it.

Nothing here runs. `owner.py` reads this table.
"""

from dataclasses import dataclass
from datetime import date

from snapback.contracts import PublishedRule


@dataclass(frozen=True)
class PublishedRuleRow:
    company: str
    rule: str
    source_url: str
    checked_on: date
    also_known_as: tuple[str, ...] = ()

    def quoted(self) -> PublishedRule:
        """The row as it travels with a case: the quote, where it is from and when it was read."""
        return PublishedRule(
            company=self.company,
            rule=self.rule,
            source_url=self.source_url,
            checked_on=self.checked_on,
        )


PUBLISHED_RULES: tuple[PublishedRuleRow, ...] = (
    PublishedRuleRow(
        company="Invitation Homes",
        rule="we only accept applications and leasing funds through invitationhomes.com",
        source_url="https://www.invitationhomes.com/preventing-leasing-fraud",
        checked_on=date(2026, 11, 14),
    ),
)
