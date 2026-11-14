"""Apply the rules table to the renter's own text, and compare asked rent with the record.

Plain pattern matching, one sentence at a time. No model reads the text here and nothing in
the text can change how it is read: an instruction hidden in a listing is just a sentence that
matches no rule.
"""

import re
from functools import cache

from snapback.agent.rules.table import BELOW_RANGE_RATIO, RULES, Rule
from snapback.contracts import PriceResult, PriceStatus, PropertyRecord, RuleHit

MAX_SPAN = 200

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")
_LINK = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)

# "after you tour the unit ...", "once the lease is signed ...". Looking at photos is not a
# viewing. The words between "after" and the viewing must not themselves be about paying,
# or "once you send the deposit I will arrange a viewing" would excuse itself.
_AFTER_VIEWING = re.compile(
    r"\b(?:after|once)\b(?P<gap>[^,;.!?]{0,60}?)\b(?:"
    r"tour(?:ed|ing)?|visit(?:ed|ing)?|showing|walk-?through|sign(?:ed|ing|s)?|move-?in|"
    r"view(?:ed|ing)?(?! (?:the |my |these |those )?"
    r"(?:photos?|pictures?|pics?|videos?|listing|ad)\b)"
    r")\b",
    re.IGNORECASE,
)
_AT_SIGNING = re.compile(r"\bat (?:the |your )?(?:lease )?signing\b|\bat move-?in\b", re.IGNORECASE)
_ABOUT_PAYING = re.compile(
    r"\b(?:send|sent|pay|paid|deposit|zelle|venmo|wire|transfer|money|fee|cash)\b", re.IGNORECASE
)

# The writer refusing the thing, not telling the renter what to avoid paying someone else.
_REFUSED = re.compile(
    r"\b(?:we|i|they|landlords?|managers?|agents?|staff)\b[^.!?]{0,20}"
    r"\b(?:never|do not|don't|will not|won't|does not|doesn't)\b[^.!?]{0,20}"
    r"\b(?:ask|accept|request|require|take)\b",
    re.IGNORECASE,
)


@cache
def _compiled(rule_id: str) -> re.Pattern[str]:
    rule = next(rule for rule in RULES if rule.rule_id == rule_id)
    return re.compile("|".join(f"(?:{pattern})" for pattern in rule.patterns), re.IGNORECASE)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_BREAK.split(text) if part.strip()]


def _comes_after_a_viewing(sentence: str) -> bool:
    if _AT_SIGNING.search(sentence):
        return True
    return any(
        not _ABOUT_PAYING.search(match.group("gap")) for match in _AFTER_VIEWING.finditer(sentence)
    )


def _fires(rule: Rule, sentence: str) -> bool:
    if rule.needs_link and not _LINK.search(sentence):
        return False
    if not _compiled(rule.rule_id).search(sentence):
        return False
    if rule.excused_after_viewing and _comes_after_a_viewing(sentence):
        return False
    return not (rule.excused_when_refused and _REFUSED.search(sentence))


def apply_rules(text: str, lang: str = "en") -> list[RuleHit]:
    """Every rule that fires on `text`, in table order, at most once each.

    `text` is the renter's own material: the listing text and the poster's messages. The
    evidence span is the first sentence that fired the rule, so the renter can see why.
    """
    sentences = _sentences(text)
    hits = []
    for rule in RULES:
        for sentence in sentences:
            if _fires(rule, sentence):
                hits.append(
                    RuleHit(
                        rule_id=rule.rule_id,
                        category=rule.category,
                        red_flag=rule.red_flag,
                        lang=lang,
                        evidence_span=sentence[:MAX_SPAN],
                    )
                )
                break
    return hits


def check_price(listed_rent: int | None, record: PropertyRecord | None) -> PriceResult:
    """Compare the rent in the listing with the rents on the property record.

    Not checked unless both numbers exist. Below range means well under the lowest rent on
    record (see `BELOW_RANGE_RATIO`); it is a reason to ask, never a verdict on its own.
    """
    reference = None
    if record is not None:
        reference = record.rent_min if record.rent_min is not None else record.rent_median
    if listed_rent is None or record is None or reference is None:
        return PriceResult(status=PriceStatus.NOT_CHECKED, listed_rent=listed_rent)

    below = listed_rent < BELOW_RANGE_RATIO * reference
    return PriceResult(
        status=PriceStatus.BELOW_RANGE if below else PriceStatus.WITHIN_RANGE,
        listed_rent=listed_rent,
        record_median=record.rent_median,
        record_min=record.rent_min,
        record_max=record.rent_max,
        n_floor_plans=len(record.floor_plans) or None,
    )
