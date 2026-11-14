"""Code-owned rules over the renter's own text, and the rent-versus-record check.

`table.py` is the rules as data. `apply.py` runs them and compares rent and unit with the
record. `contact.py` compares the poster's company, phone and links with the record. Wording
for the card lives in `snapback.card.strings`.
"""

from snapback.agent.rules.apply import apply_rules, check_price, check_unit
from snapback.agent.rules.table import BELOW_RANGE_RATIO, RULES, Rule

__all__ = ["BELOW_RANGE_RATIO", "RULES", "Rule", "apply_rules", "check_price", "check_unit"]
