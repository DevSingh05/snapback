"""Leak checks that cannot match by chance.

A "nothing leaked" test searches captured output for the record's values. Short needles
("1600", "0123", "4B", "999") also occur inside trace timestamps and random tokens, which
made those tests fail about one run in a few hundred. `leaked` masks timestamps, UUIDs and
long random-looking tokens before looking for a short needle, and searches long needles
(hashes, hostnames, names) in the raw text so a real leak of those is never hidden.
"""

import re

SHORT = 8  # needles shorter than this are searched in the masked text only

_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?"
)
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{16,}")


def masked(text: str) -> str:
    """The text with timestamps, UUIDs and long random-looking tokens blanked out."""
    for pattern in (_TIMESTAMP, _UUID, _TOKEN):
        text = pattern.sub(" ", text)
    return text


def leaked(needles, *texts: str) -> list[str]:
    """The needles that appear in any of the texts (None needles are skipped)."""
    raw = " ".join(texts)
    clean = masked(raw)
    return [n for n in needles if n is not None and (n in raw if len(n) >= SHORT else n in clean)]
