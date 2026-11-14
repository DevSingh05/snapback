"""Step 2: a cheap, reproducible text embedding for semantic near-duplicates.

No model, no network, no random state: TF-IDF over unigrams and bigrams, computed with numpy.
Before counting, words that say the same thing in an ad are folded onto one concept token
("remit", "forward" and "transfer" all become PAY; "holding amount", "reservation sum" and
"booking amount" all become MONEY; "ahead of", "prior to", "up front" become BEFORE; "keys",
"handover" and "moving in" become ACCESS). That is how "Kindly remit the holding amount ahead
of receiving the keys" lands next to "The deposit is due before move-in" although they share
almost no words, which a keyword search cannot do.
"""

import re

import numpy as np

# Order matters: longer phrases first.
_FOLDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p, re.IGNORECASE), c)
    for p, c in [
        (
            r"\b(?:holding|reservation|booking)\s+(?:amount|sum|payment|funds|fee)\b|"
            r"\b(?:security\s+)?deposit\b|\bfirst\s+month(?:'s)?(?:\s+rent)?\b|\bmonth'?s\s+rent\b|"
            r"\breservation\s+funds\b|\bbooking\s+amount\b",
            " MONEY ",
        ),
        (
            r"\b(?:ahead\s+of|prior\s+to|before|in\s+advance(?:\s+of)?|up\s*front|upfront)\b",
            " BEFORE ",
        ),
        (
            r"\b(?:the\s+)?keys?\b|\bhand\s?over\b|\bmov(?:e|ing)[- ]in\b|\bcollecting\b|"
            r"\breleased?\b|\breceiving\b",
            " ACCESS ",
        ),
        (r"\b(?:remit|send|forward|transfer|wire|zelle|pay|paid|mail)\b", " PAY "),
    ]
]
_TOKEN = re.compile(r"[A-Za-z']+")
_STOP = frozenset(
    "a an the to of and or is are be it in on for you your i me my will with at by as that this "  # noqa: SIM905
    "then once until so we our".split()
)


def fold(text: str) -> list[str]:
    for pattern, concept in _FOLDS:
        text = pattern.sub(concept, text)
    words = [w if w.isupper() else w.lower() for w in _TOKEN.findall(text)]
    words = [w for w in words if w not in _STOP]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]


class TfIdf:
    """Fit on a list of texts; `matrix` rows are L2-normalised, so a dot product is a cosine."""

    def __init__(self, texts: list[str]) -> None:
        docs = [fold(t) for t in texts]
        vocab = sorted({tok for doc in docs for tok in doc})
        self.index = {tok: i for i, tok in enumerate(vocab)}
        df = np.zeros(len(vocab))
        for doc in docs:
            for tok in set(doc):
                df[self.index[tok]] += 1
        self.idf = np.log((1 + len(docs)) / (1 + df)) + 1.0
        self.matrix = np.vstack([self.vector(t) for t in texts]) if texts else np.zeros((0, 0))

    def vector(self, text: str) -> np.ndarray:
        vec = np.zeros(len(self.index))
        for tok in fold(text):
            i = self.index.get(tok)
            if i is not None:
                vec[i] += 1.0
        vec *= self.idf
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec


def concepts(text: str) -> set[str]:
    """The concept tokens a sentence folds to (MONEY, BEFORE, ACCESS, PAY)."""
    return {t for t in fold(text) if t.isupper()}
