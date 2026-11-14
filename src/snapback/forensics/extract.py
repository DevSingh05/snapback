"""Step 1: claims and rule hits per ad, from the code the card already uses.

`apply_rules` (the rule table, including `fee.money_before_move_in` and the payment-method
rules) and `extract_claims` (the pretext vocabulary: "the owner is out of town", "I can't show
it") run unchanged on each ad's text. Their evidence spans are the seeds the later steps grow
from, and the pointers every finding cites.
"""

import re
from dataclasses import dataclass, field

from snapback.agent.intake.claims import PRETEXT, extract_claims
from snapback.agent.rules.apply import apply_rules
from snapback.forensics.corpus import Ad
from snapback.forensics.embed import concepts

# The rules that mean "money first". Honest ads fire none of these on their usual wording
# ("deposit at lease signing", "rent by Zelle once you have moved in").
MONEY_FIRST_PREFIXES = ("payment.", "fee.money_before_move_in")

_SENTENCE = re.compile(r"(?<=[.!?;])\s+")


@dataclass
class AdFacts:
    ad: Ad
    sentences: list[str]
    rule_hits: dict[str, str] = field(default_factory=dict)  # rule_id -> evidence span
    pretext: list[str] = field(default_factory=list)  # claim kinds such as "owner_away"

    @property
    def money_first_spans(self) -> list[tuple[str, str]]:
        return [
            (rule_id, span)
            for rule_id, span in self.rule_hits.items()
            if rule_id.startswith(MONEY_FIRST_PREFIXES)
        ]


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text) if s.strip()]


def extract_facts(ad: Ad) -> AdFacts:
    hits = {h.rule_id: h.evidence_span or "" for h in apply_rules(ad.text)}
    kinds = extract_claims(ad.text).kinds()
    return AdFacts(
        ad=ad,
        sentences=split_sentences(ad.text),
        rule_hits=hits,
        pretext=sorted(k.value for k in kinds if k in PRETEXT),
    )


def extract_all(ads: list[Ad]) -> dict[int, AdFacts]:
    return {ad.id: extract_facts(ad) for ad in ads}


# Wording that makes an ask for money ordinary: it comes after the viewing, at signing, through a
# portal, or it is a promise not to ask. A sentence with one of these is not payment-first.
_GUARD = re.compile(
    r"\bafter\b|\bonce\b|\bat (?:the )?(?:lease )?signing\b|\bsigning table\b|"
    r"\bon move-in day\b|\bportal\b|\bnever\b|\bno wire\b|\bwalk-through\b",
    re.IGNORECASE,
)
# What a payment-first ask has to say besides naming money: that it comes first, or gates the
# keys, or is wanted today, or is paid in a way that cannot be taken back.
_FIRST = {"BEFORE", "ACCESS", "PAY"}
_URGENT = re.compile(r"\btoday\b|\bnow\b|\bimmediately\b|\bfirst\b|\bheld for you\b", re.I)


def pressure_sentences(facts: AdFacts) -> list[tuple[str, str]]:
    """Sentences that ask for money first, as (sentence, why). `why` is the rule id when one of
    the existing money rules fired on it, else "concept" (the folded words say the same thing in
    other words). A guarded sentence ("deposit due at lease signing, after you tour") is not one,
    even when a rule's wording matches: the rule table marks `fee.money_before_move_in` as a
    trace-only signal because honest ads use the same words."""
    by_span = {span: rule_id for rule_id, span in facts.money_first_spans}
    found = []
    for sentence in facts.sentences:
        if _GUARD.search(sentence):
            continue
        rule_id = by_span.get(sentence)
        have = concepts(sentence)
        if rule_id:
            found.append((sentence, rule_id))
        elif "MONEY" in have and (have & _FIRST or _URGENT.search(sentence)):
            found.append((sentence, "concept"))
    return found
