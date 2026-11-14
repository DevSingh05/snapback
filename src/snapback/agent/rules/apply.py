"""Apply the rules table to the renter's own text, and compare asked rent with the record.

Plain pattern matching. No model reads the text here and nothing in the text can change how
it is read: an instruction hidden in a listing is just a sentence that matches no rule.

How a rule fires:

1. The text is normalised (compatibility forms folded, curly quotes straightened, zero-width
   characters removed), so odd characters cannot hide a word.
2. It is split into sentences, and each sentence into clauses. A clause ends at "but", "so",
   a semicolon, or a comma that starts something new ("I don't take checks, Zelle the deposit").
   A comma inside a list ("Zelle, wire transfer or gift card") does not end one.
3. A rule's pattern has to match inside one clause.
4. A match can be excused, and each excuse is tied to the clause the match is in:
   - refused: the writer refuses or warns against the thing earlier in the same clause;
   - rent terms: the clause describes how tenants pay rent and asks for nothing now;
   - after a viewing: the clause puts the ask after a tour or a signed lease, and does not
     demand payment "today" or "now".

The evidence span is the whole sentence, so the renter sees the ask in context.
"""

import re
import unicodedata
from functools import cache

from snapback.agent.rules.table import BELOW_RANGE_RATIO, RULES, Rule
from snapback.contracts import PriceResult, PriceStatus, PropertyRecord, RuleHit

MAX_SPAN = 200

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"))
_STRAIGHT_QUOTES = str.maketrans({"‘": "'", "’": "'", "ʼ": "'", "′": "'", "“": '"', "”": '"'})

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")
_LINK = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)

# A colon that introduces a link does not end a clause: "Pay here: https://...".
_STRONG_BREAK = re.compile(
    r"\s*;\s*"
    r"|:\s+(?!https?://|www\.)"
    r"|\s+[-–—]\s+"
    r"|,?\s+\b(?:but|however|so|because|then)\b\s+",
    re.IGNORECASE,
)
_COMMA = re.compile(r",\s+")
# What a new clause starts with after a comma. A list item does not start this way.
_CLAUSE_OPENER = re.compile(
    r"(?:only|just|instead|rather|except|please|send|pay|text|mail|use|bring|call|"
    r"i|i'm|i'll|we|we're|we'll|you|you'll|they|it|after|once|before|when|if|while)\b"
    r"|(?:zelle|venmo|wire|cash ?app)\s+(?:(?:me|us|the|it|your|my|a)\b|\$)",
    re.IGNORECASE,
)
_LIST_WORD = re.compile(r"(?:or|and)$", re.IGNORECASE)

# The writer refusing the thing ("we never ask for ..."), or warning the renter off it
# ("never pay by ..."). Only counts when it comes before the match, in the same clause.
_REFUSED = re.compile(
    r"\b(?:we|i|they|landlords?|managers?|agents?|staff|owners?)\b[^,;.!?]{0,20}"
    r"\b(?:never|do not|don't|dont|will not|won't|wont|does not|doesn't)\b[^,;.!?]{0,20}"
    r"\b(?:ask|accept|request|require|take|charge|collect)\b"
    r"|\b(?:never|do not|don't|dont)\s+(?:ever\s+)?"
    r"(?:pay|send|wire|zelle|venmo|transfer|give|share|use|accept)\b",
    re.IGNORECASE,
)

# How tenants pay rent, as opposed to an ask for money now.
_RENT_TERMS = re.compile(
    r"\b(?:tenants?|residents?)\b[^,;.!?]{0,20}\bpay\b"
    r"|\brent (?:is|can be|may be|will be)\b[^,;.!?]{0,15}\b(?:paid|payable|due)\b"
    r"|\b(?:we|they) accept\b",
    re.IGNORECASE,
)
_ASKS_NOW = re.compile(
    r"\b(?:deposit|hold|holding|reserve|secure|fee|today|tonight|now|asap|immediately|"
    r"right away|me|my|first month)\b",
    re.IGNORECASE,
)

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
# Payment demanded first, whatever else is promised for later.
_URGENT = re.compile(
    r"\b(?:today|tonight|now|right away|immediately|asap|up ?front|in advance)\b", re.IGNORECASE
)
# A subject and a verb of its own: "after signing YOU GET the keys". The "after" then belongs
# to that, not to the payment.
_OWN_CLAUSE = re.compile(
    r"\b(?:you|i|we|they|he|she|it)\b(?:\s+\w+)?\s+"
    r"(?:get|gets|will|can|could|may|might|should|must|receive|have|has|are|is|do|would)\b"
    r"|\b(?:you|i|we|they)'ll\b",
    re.IGNORECASE,
)
_OWN_CLAUSE_THEN_AND = re.compile(f"(?:{_OWN_CLAUSE.pattern}).*\\band\\b", re.IGNORECASE)


def normalise(text: str) -> str:
    """Fold look-alike characters so a rule sees the word a person would read."""
    folded = unicodedata.normalize("NFKC", text)
    return folded.translate(_ZERO_WIDTH).translate(_STRAIGHT_QUOTES)


@cache
def _compiled(rule_id: str) -> re.Pattern[str]:
    rule = next(rule for rule in RULES if rule.rule_id == rule_id)
    return re.compile("|".join(f"(?:{pattern})" for pattern in rule.patterns), re.IGNORECASE)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_BREAK.split(text) if part.strip()]


def _continues_a_list(chunk: str) -> bool:
    words = chunk.split()
    if not words or _CLAUSE_OPENER.match(chunk):
        return False
    return len(words) <= 3 or any(_LIST_WORD.match(word) for word in words[:4])


def _clauses(sentence: str) -> list[str]:
    clauses: list[str] = []
    for piece in _STRONG_BREAK.split(sentence):
        chunks = _COMMA.split(piece)
        current = chunks[0]
        for chunk in chunks[1:]:
            if _continues_a_list(chunk):
                current = f"{current}, {chunk}"
            else:
                clauses.append(current)
                current = chunk
        clauses.append(current)
    return [clause.strip() for clause in clauses if clause.strip()]


def _viewing_phrases(clause: str) -> list[re.Match[str]]:
    """Each "after/once ... viewing" in the clause that is not itself about paying."""
    return [m for m in _AFTER_VIEWING.finditer(clause) if not _ABOUT_PAYING.search(m.group("gap"))]


def _comes_after_a_viewing(clauses: list[str], index: int, match: re.Match[str]) -> bool:
    clause = clauses[index]
    if _URGENT.search(clause):
        return False
    if _AT_SIGNING.search(clause):
        return True

    for phrase in _viewing_phrases(clause):
        # "After signing the lease you can Zelle the deposit."
        if phrase.end() <= match.start():
            between = clause[phrase.end() : match.start()]
            if not _OWN_CLAUSE_THEN_AND.search(between):
                return True
        # "You can pay by Zelle after your tour."
        elif phrase.start() >= match.end() and not _OWN_CLAUSE.search(clause[phrase.end() :]):
            return True

    # "After you tour the unit and we both sign the lease, you can pay by Zelle."
    if index > 0:
        before = clauses[index - 1]
        if any(not _OWN_CLAUSE.search(before[p.end() :]) for p in _viewing_phrases(before)):
            return True

    # "The deposit can be paid by Zelle, after your tour."
    if index + 1 < len(clauses):
        after = clauses[index + 1]
        if any(
            p.start() <= 4 and not _OWN_CLAUSE.search(after[p.end() :])
            for p in _viewing_phrases(after)
        ):
            return True
    return False


def _excused(rule: Rule, clauses: list[str], index: int, match: re.Match[str]) -> bool:
    clause = clauses[index]
    if rule.excused_when_refused and _REFUSED.search(clause[: match.start()]):
        return True
    if rule.excused_as_rent_terms and _RENT_TERMS.search(clause) and not _ASKS_NOW.search(clause):
        return True
    return rule.excused_after_viewing and _comes_after_a_viewing(clauses, index, match)


def _fires(rule: Rule, sentence: str) -> bool:
    clauses = _clauses(sentence)
    pattern = _compiled(rule.rule_id)
    for index, clause in enumerate(clauses):
        if rule.needs_link and not _LINK.search(clause):
            continue
        for match in pattern.finditer(clause):
            if not _excused(rule, clauses, index, match):
                return True
    return False


def apply_rules(text: str, lang: str = "en") -> list[RuleHit]:
    """Every rule that fires on `text`, in table order, at most once each.

    `text` is the renter's own material: the listing text and the poster's messages. The
    evidence span is the first sentence that fired the rule, so the renter can see why.
    """
    sentences = _sentences(normalise(text))
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
