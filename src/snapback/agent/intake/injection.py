"""Find text in a listing that is addressed to an AI system rather than to a renter.

A listing is written by the person being checked, so it is the obvious place to hide
"ignore previous instructions". Nothing in SNAPBACK acts on listing text: the rules are
patterns, the fields are patterns, and the state is code. So an injected sentence already
changes nothing. This module is the other half: it notices the attempt, so it can be logged
and turned into an eval case.

The sentence is never removed. A real ask sitting next to it must still be read.
"""

import re

from snapback.agent.rules.apply import normalise

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")

_ADDRESSED_TO_AN_AI = re.compile(
    r"\b(?:ignore|disregard|forget)\b[^.!?\n]{0,20}"
    r"\b(?:previous|prior|above|earlier|your|all)\b[^.!?\n]{0,15}"
    r"\b(?:instructions?|prompts?|rules?|messages?|guidelines?)\b"
    r"|^\W{0,3}(?:system|assistant|developer)(?:\s+(?:prompt|message|note))?\s*:"
    r"|</?(?:system|instructions?|prompt|assistant)>"
    r"|\byou are (?:now )?(?:an? |the )?[^.!?\n]{0,30}\b(?:assistant|ai|model|agent|chatbot|bot)\b"
    r"|\bnew instructions?\b"
    r"|\bas an? (?:ai|language model|assistant)\b"
    r"|\b(?:prompt injection|jailbreak|developer mode)\b"
    r"|\bmark (?:this|it|the listing)\b[^.!?\n]{0,30}"
    r"\b(?:verified|safe|legit|legitimate|approved|trusted|clean|real)\b"
    r"|\bset (?:the )?(?:state|status|verdict|result|card)\b[^.!?\n]{0,20}\bto\b"
    r"|\b(?:do not|don't|never) (?:flag|warn about|report)\b"
    r"|(?:^|[.!?]\s+)(?:agent|assistant|ai|bot|snapback)\s*[:,]\s*"
    r"(?:choose|pick|select|skip|approve|return|output|say|respond|mark|set)\b",
    re.IGNORECASE,
)


def find_injections(text: str) -> list[str]:
    """Each sentence that reads as an instruction to an AI system, in order."""
    found = []
    for sentence in _SENTENCE_BREAK.split(normalise(text)):
        sentence = sentence.strip()
        if sentence and _ADDRESSED_TO_AN_AI.search(sentence):
            found.append(sentence)
    return found
