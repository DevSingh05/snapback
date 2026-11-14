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

Cost. The text comes from the person being checked, so reading it must stay cheap whatever it
holds:

- `normalise` cuts the text to `MAX_TEXT_CHARS` and folds every run of spaces into one, before
  any pattern runs;
- every quantifier in every pattern has an upper bound, so no pattern can backtrack over a
  long run of one character (tests/test_pattern_speed.py checks both the structure and the
  time);
- what a clause says about itself (rent terms, a viewing, a link) is worked out once and
  shared by all the rules, and a rule weighs at most `MAX_MATCHES_PER_CLAUSE` matches in a
  clause. More mentions than that in one clause count as an ask.
"""

import re
import unicodedata
from functools import cache, cached_property
from typing import NamedTuple

from snapback.agent.rules.table import BELOW_RANGE_RATIO, RULES, Rule
from snapback.contracts import PriceResult, PriceStatus, PropertyRecord, RuleHit

MAX_SPAN = 200
# A long listing is a few thousand characters. Anything past this is not read, and intake
# says so (`Listing.truncated`).
MAX_TEXT_CHARS = 20_000
MAX_MATCHES_PER_CLAUSE = 8
MAX_PHRASES_PER_CLAUSE = 4

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"))
_STRAIGHT_QUOTES = str.maketrans({"‘": "'", "’": "'", "ʼ": "'", "′": "'", "“": '"', "”": '"'})

# `normalise` leaves no run of spaces longer than one, so the small bounds below lose nothing.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s{1,3}|\n{1,3}")
_LINK = re.compile(r"(?:https?://|www\.)\S", re.IGNORECASE)

# A colon that introduces a link does not end a clause: "Pay here: https://...".
_STRONG_BREAK = re.compile(
    r"\s{0,3};\s{0,3}"
    r"|:\s{1,3}(?!https?://|www\.)"
    r"|\s{1,3}[-–—]\s{1,3}"
    r"|,?\s{1,3}\b(?:but|however|so|because|then)\b\s{1,3}",
    re.IGNORECASE,
)
_COMMA = re.compile(r",\s{1,3}")
# What a new clause starts with after a comma. A list item does not start this way.
_CLAUSE_OPENER = re.compile(
    r"(?:only|just|instead|rather|except|please|send|pay|text|mail|use|bring|call|"
    r"i|i'm|i'll|we|we're|we'll|you|you'll|they|it|after|once|before|when|if|while)\b"
    r"|(?:zelle|venmo|wire|cash ?app)\s{1,3}(?:(?:me|us|the|it|your|my|a)\b|\$)",
    re.IGNORECASE,
)
_LIST_WORD = re.compile(r"(?:or|and)$", re.IGNORECASE)

# The writer refusing the thing ("we never ask for ..."), or warning the renter off it
# ("never pay by ..."). Only counts when it comes before the match, in the same clause.
_REFUSED = re.compile(
    r"\b(?:we|i|they|landlords?|managers?|agents?|staff|owners?)\b[^,;.!?]{0,20}"
    r"\b(?:never|do not|don't|dont|will not|won't|wont|does not|doesn't)\b[^,;.!?]{0,20}"
    r"\b(?:ask|accept|request|require|take|charge|collect)\b"
    r"|\b(?:never|do not|don't|dont)\s{1,3}(?:ever\s{1,3})?"
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
    r"\b(?:you|i|we|they|he|she|it)\b(?:\s{1,3}\w{1,30})?\s{1,3}"
    r"(?:get|gets|will|can|could|may|might|should|must|receive|have|has|are|is|do|would)\b"
    r"|\b(?:you|i|we|they)'ll\b",
    re.IGNORECASE,
)
_AND = re.compile(r"\band\b", re.IGNORECASE)


def normalise(text: str) -> str:
    """Fold look-alike characters so a rule sees the word a person would read.

    This is also where the text is bounded, so every reader of renter text calls it first:
    the text is cut to `MAX_TEXT_CHARS`, each run of spaces becomes one space, and each run
    of line breaks becomes one line break. Calling it twice changes nothing.
    """
    return _fold(text)[:MAX_TEXT_CHARS]


def exceeds_cap(text: str) -> bool:
    """True when `normalise` leaves part of `text` unread."""
    return len(text) > MAX_TEXT_CHARS or len(_fold(text)) > MAX_TEXT_CHARS


def _fold(text: str) -> str:
    # The first cut bounds the work below. Folding can make text longer (one compatibility
    # character can unfold into several), which is why `normalise` cuts again.
    folded = unicodedata.normalize("NFKC", text[:MAX_TEXT_CHARS])
    folded = folded.translate(_ZERO_WIDTH).translate(_STRAIGHT_QUOTES)
    lines = (" ".join(line.split()) for line in folded.splitlines())
    return "\n".join(line for line in lines if line)


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


class _Phrase(NamedTuple):
    """An "after/once ... viewing" in a clause that is not itself about paying."""

    start: int
    end: int
    own_clause_after: bool  # "after signing YOU GET the keys": the "after" belongs to that


class _Clause:
    """One clause, with what it says about itself worked out once for all the rules."""

    def __init__(self, text: str) -> None:
        self.text = text

    @cached_property
    def has_link(self) -> bool:
        return _LINK.search(self.text) is not None

    @cached_property
    def is_rent_terms(self) -> bool:
        return bool(_RENT_TERMS.search(self.text)) and not _ASKS_NOW.search(self.text)

    @cached_property
    def is_urgent(self) -> bool:
        return _URGENT.search(self.text) is not None

    @cached_property
    def is_at_signing(self) -> bool:
        return _AT_SIGNING.search(self.text) is not None

    @cached_property
    def viewing_phrases(self) -> list[_Phrase]:
        phrases: list[_Phrase] = []
        for found in _AFTER_VIEWING.finditer(self.text):
            if _ABOUT_PAYING.search(found.group("gap")):
                continue
            own = _OWN_CLAUSE.search(self.text, found.end()) is not None
            phrases.append(_Phrase(found.start(), found.end(), own))
            if len(phrases) == MAX_PHRASES_PER_CLAUSE:
                break
        return phrases

    @cached_property
    def excuses_the_next_clause(self) -> bool:
        """ "After you tour the unit and we both sign the lease, you can pay by Zelle." """
        return any(not phrase.own_clause_after for phrase in self.viewing_phrases)

    @cached_property
    def excuses_the_clause_before(self) -> bool:
        """ "The deposit can be paid by Zelle, after your tour." """
        return any(
            phrase.start <= 4 and not phrase.own_clause_after for phrase in self.viewing_phrases
        )

    def refused_before(self, position: int) -> bool:
        return _REFUSED.search(self.text, 0, position) is not None

    def own_clause_then_and(self, start: int, end: int) -> bool:
        """Between two places: a subject and verb of its own, and then an "and"."""
        own = _OWN_CLAUSE.search(self.text, start, end)
        return own is not None and _AND.search(self.text, own.end(), end) is not None


def _parse(sentence: str) -> list[_Clause]:
    return [_Clause(clause) for clause in _clauses(sentence)]


def _comes_after_a_viewing(clauses: list[_Clause], index: int, match: re.Match[str]) -> bool:
    clause = clauses[index]
    if clause.is_urgent:
        return False
    if clause.is_at_signing:
        return True

    for phrase in clause.viewing_phrases:
        # "After signing the lease you can Zelle the deposit."
        if phrase.end <= match.start():
            if not clause.own_clause_then_and(phrase.end, match.start()):
                return True
        # "You can pay by Zelle after your tour."
        elif phrase.start >= match.end() and not phrase.own_clause_after:
            return True

    if index > 0 and clauses[index - 1].excuses_the_next_clause:
        return True
    return index + 1 < len(clauses) and clauses[index + 1].excuses_the_clause_before


def _excused(rule: Rule, clauses: list[_Clause], index: int, match: re.Match[str]) -> bool:
    clause = clauses[index]
    if rule.excused_when_refused and clause.refused_before(match.start()):
        return True
    if rule.excused_as_rent_terms and clause.is_rent_terms:
        return True
    return rule.excused_after_viewing and _comes_after_a_viewing(clauses, index, match)


def _fires(rule: Rule, clauses: list[_Clause]) -> bool:
    pattern = _compiled(rule.rule_id)
    for index, clause in enumerate(clauses):
        if rule.needs_link and not clause.has_link:
            continue
        for seen, match in enumerate(pattern.finditer(clause.text)):
            # Each match is weighed on its own, which costs time. A clause that names the
            # thing more often than this is not weighed further: it counts as an ask.
            if seen == MAX_MATCHES_PER_CLAUSE or not _excused(rule, clauses, index, match):
                return True
    return False


def apply_rules(text: str, lang: str = "en") -> list[RuleHit]:
    """Every rule that fires on `text`, in table order, at most once each.

    `text` is the renter's own material: the listing text and the poster's messages. The
    evidence span is the first sentence that fired the rule, so the renter can see why.
    """
    sentences = _sentences(normalise(text))
    parsed = [_parse(sentence) for sentence in sentences]
    hits = []
    for rule in RULES:
        for sentence, clauses in zip(sentences, parsed, strict=True):
            if _fires(rule, clauses):
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
