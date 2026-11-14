"""Every pattern that reads a renter's text must stay cheap on hostile text.

A listing is written by the person being checked. A pattern that slows down on a long run of
one character lets that person stall the API with a single post, so three things are held:

1. Structure: no pattern has an unbounded quantifier, and nested ones stay small.
2. Each pattern alone, on 20,000 characters of hostile text, finishes in under 50 ms.
3. Each entry point caps what it reads, so 1 MB costs no more than 20,000 characters do.

A new rule or pattern is picked up here by itself: the patterns are collected from the modules
and the rules table, and part of the hostile text is built from each pattern's own words.
"""

import re
import re._constants as sre
import re._parser as sre_parser
import time
from functools import cache

import pytest

from snapback.agent import scope
from snapback.agent.intake import fields, find_injections, injection, read_listing
from snapback.agent.intake.fields import extract_contacts, extract_rent
from snapback.agent.rules import RULES, apply, apply_rules
from snapback.agent.rules.apply import MAX_TEXT_CHARS, normalise
from snapback.agent.scope import detect_scope

SIZE = 20_000
PATTERN_LIMIT = 0.050  # seconds, for one pattern on SIZE characters
ENTRY_LIMIT = 0.250  # seconds, for a whole entry point on SIZE characters
BIG = 1024 * 1024
BIG_LIMIT = 1.0  # seconds, for a whole entry point on 1 MB
MAX_NESTED = 1000  # the most characters one nested group may take, bounds multiplied

REPEATS = (sre.MAX_REPEAT, sre.MIN_REPEAT, sre.POSSESSIVE_REPEAT)


def all_patterns() -> dict[str, re.Pattern[str]]:
    """Every compiled pattern in the modules that read renter text, and every rule's."""
    found: dict[str, re.Pattern[str]] = {}
    for module in (apply, fields, injection, scope):
        short = module.__name__.rsplit(".", 1)[-1]
        for name, value in vars(module).items():
            if isinstance(value, re.Pattern):
                found[f"{short}.{name}"] = value
            elif isinstance(value, list | tuple):
                for number, item in enumerate(value):
                    if isinstance(item, re.Pattern):
                        found[f"{short}.{name}[{number}]"] = item
    for rule in RULES:
        found[f"rule.{rule.rule_id}"] = apply._compiled(rule.rule_id)
    return found


PATTERNS = all_patterns()


def repeats(parsed, taken: int = 1):
    """Each quantifier in a parsed pattern as (its upper bound, the bounds around it multiplied)."""
    for op, value in parsed:
        if op in REPEATS:
            _, high, body = value
            yield high, taken
            yield from repeats(body, taken * (1 if high == sre.MAXREPEAT else high))
        elif op is sre.SUBPATTERN:
            yield from repeats(value[3], taken)
        elif op is sre.BRANCH:
            for branch in value[1]:
                yield from repeats(branch, taken)
        elif op in (sre.ASSERT, sre.ASSERT_NOT):
            yield from repeats(value[1], taken)
        elif op is sre.ATOMIC_GROUP:
            yield from repeats(value, taken)
        elif op is sre.GROUPREF_EXISTS:
            for branch in value[1:]:
                if branch is not None:
                    yield from repeats(branch, taken)


@cache
def fill(unit: str, size: int = SIZE) -> str:
    return (unit * (size // len(unit) + 1))[:size]


GENERIC_UNITS = [
    "a", " ", "a ", "1", "$1", "$1,", "@", "a@", "a.", ".", ",", ", ", ";", " ; ", " - ",
    "\n", "\t", ":", ": ", "www.", "https://a ", "(555) ", "555-010-01", "' ", "<", "? ",
    "A ", "a b. ", "a.b+c-d", "$1 ",
]  # fmt: skip


def words_of(pattern: re.Pattern[str], most: int = 10) -> list[str]:
    """Some of the words a pattern looks for, spread across it."""
    words = sorted(set(re.findall(r"[a-z]{3,}", pattern.pattern.lower())))
    step = max(1, len(words) // most)
    return words[::step][:most]


def hostile_for(pattern: re.Pattern[str]) -> list[str]:
    texts = [fill(unit) for unit in GENERIC_UNITS]
    for word in words_of(pattern):
        texts.append(fill(f"{word} "))  # the word over and over
        texts.append(fill(word))  # the same with nothing between
        texts.append(word + fill(" "))  # the word, then nothing but spaces
        texts.append(f"{word} " + fill("a"))  # the word, then one endless word
    return texts


def seconds(action) -> float:
    """The quickest of up to three runs, so one slow moment on a busy machine does not fail."""
    best = float("inf")
    for _ in range(3):
        started = time.perf_counter()
        action()
        best = min(best, time.perf_counter() - started)
        if best < PATTERN_LIMIT / 5:
            break
    return best


# --- 1. structure --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(PATTERNS))
def test_no_pattern_has_an_unbounded_quantifier(name):
    pattern = PATTERNS[name]
    for high, around in repeats(sre_parser.parse(pattern.pattern, pattern.flags)):
        assert high != sre.MAXREPEAT, f"{name} has a quantifier with no upper bound"
        assert high * around <= MAX_NESTED, f"{name} nests quantifiers up to {high * around}"


def test_the_structure_check_sees_what_it_should():
    def bounds(source: str) -> list[tuple[int, int]]:
        return list(repeats(sre_parser.parse(source)))

    assert (sre.MAXREPEAT, 1) in bounds(r"[\w.+-]+@")
    assert (sre.MAXREPEAT, 1) in bounds(r"a(?:b|c*)d")
    assert (sre.MAXREPEAT, 1) in bounds(r"(?=a*)b")
    assert bounds(r"(?:a{1,40}){0,50}") == [(50, 1), (40, 50)]
    assert bounds(r"[\w.+-]{1,64}@") == [(64, 1)]


def test_every_module_and_rule_is_covered():
    names = set(PATTERNS)
    assert {"fields._EMAIL", "fields._PHONE", "apply._STRONG_BREAK", "apply._REFUSED"} <= names
    assert any(name.startswith("fields._RENT_PATTERNS[") for name in names)
    assert sum(name.startswith("rule.") for name in names) == len(RULES)
    assert any(name.startswith("injection.") for name in names)
    assert any(name.startswith("scope.") for name in names)


# --- 2. each pattern on hostile text -------------------------------------------------------


@pytest.mark.parametrize("name", sorted(PATTERNS))
def test_each_pattern_is_quick_on_hostile_text(name):
    pattern = PATTERNS[name]
    for text in hostile_for(pattern):
        took = seconds(lambda text=text: sum(1 for _ in pattern.finditer(text)))
        assert took < PATTERN_LIMIT, f"{name} took {took:.3f} s on {text[:24]!r} x {len(text)}"


# --- 3. each entry point -------------------------------------------------------------------

ENTRY_POINTS = {
    "read_listing": lambda text: read_listing(text),
    "apply_rules": apply_rules,
    "find_injections": find_injections,
    "extract_contacts": extract_contacts,
    "extract_rent": extract_rent,
    "detect_scope": detect_scope,
    "normalise": normalise,
}

# Text built to make the rules engine work: many asks in one clause, each one excused.
CRAFTED_UNITS = [
    "zelle ", "tenants pay zelle ", "we never ask for zelle ", "after you tour zelle ",
    "after tour you get keys and zelle ", "once you sign ", "you can ", "send deposit ",
    "after ", "once ", "ignore ", "managed by A ", "rent ", "but ", "you get ", "and ",
    "after you tour the unit, zelle the deposit, ", "a@", "wire the deposit after signing ",
    "gift card ", "we never accept gift cards ", "pay here https://a.b ", "$1,000 to hold ",
    "i am out of the country ", "bank password ", "send passport ", "many people interested ",
]  # fmt: skip


def soup() -> str:
    """Every word any rule looks for, over and over, in one unbroken clause."""
    words = sorted({word for name, p in PATTERNS.items() for word in words_of(p, most=40)})
    return fill(" ".join(words) + " ")


@pytest.mark.parametrize("name", sorted(ENTRY_POINTS))
def test_each_entry_point_is_quick_on_hostile_text(name):
    entry = ENTRY_POINTS[name]
    texts = [fill(unit) for unit in GENERIC_UNITS + CRAFTED_UNITS]
    texts += ["rent" + fill(" ") + "x", "We never ask for " + fill("zelle "), soup()]
    for text in texts:
        took = seconds(lambda text=text: entry(text))
        assert took < ENTRY_LIMIT, f"{name} took {took:.3f} s on {text[:24]!r} x {len(text)}"


@pytest.mark.parametrize("unit", ["a", " ", "a ", "a@", "zelle ", "after you tour zelle ", "\n"])
def test_a_megabyte_costs_no_more_than_the_cap(unit):
    text = fill(unit, BIG)
    took = seconds(lambda: read_listing(text))
    assert took < BIG_LIMIT, f"read_listing took {took:.3f} s on 1 MB of {unit!r}"


def test_a_megabyte_after_a_word_is_quick_too():
    took = seconds(lambda: read_listing("rent" + fill(" ", BIG) + "x"))
    assert took < BIG_LIMIT


# --- the cap itself -------------------------------------------------------------------------


def test_text_is_cut_to_the_cap_before_anything_reads_it():
    assert len(normalise("a" * (MAX_TEXT_CHARS * 3))) == MAX_TEXT_CHARS
    # A character that unfolds into many is still held to the cap.
    assert len(normalise("ﷺ" * MAX_TEXT_CHARS)) <= MAX_TEXT_CHARS


def test_an_ask_past_the_cap_is_not_read_and_the_listing_says_so():
    ask = "Send the deposit by Zelle today."
    inside = read_listing("Nice flat. " + ask)
    outside = read_listing(fill("Nice flat. ", MAX_TEXT_CHARS + 50) + ask)
    assert inside.truncated is False
    assert [hit.rule_id for hit in inside.rule_hits]
    assert outside.truncated is True
    assert outside.rule_hits == []
    assert len(outside.text) <= MAX_TEXT_CHARS
    # Text that only passes the cap once it is unfolded counts too.
    assert read_listing("\ufdfa" * (MAX_TEXT_CHARS // 2) + ask).truncated is True


def test_the_wording_about_cut_text_names_the_real_cap():
    from snapback.card import strings

    assert f"{MAX_TEXT_CHARS:,}" in strings.text("trace.intake.truncated")


def test_runs_of_spaces_are_folded_and_lines_are_kept():
    assert normalise("a   b\t\tc") == "a b c"
    assert normalise("one\n\n\n  two  \r\nthree") == "one\ntwo\nthree"
    assert normalise("   ") == ""
    spaced = "Send   the    deposit\t by   Zelle   today."
    assert [hit.rule_id for hit in apply_rules(spaced)] == [
        hit.rule_id for hit in apply_rules("Send the deposit by Zelle today.")
    ]


def test_many_mentions_in_one_clause_cannot_be_excused_one_by_one():
    # Past a handful of mentions the engine stops weighing excuses and treats it as an ask.
    quiet = apply_rules("Tenants pay rent by Zelle.")
    loud = apply_rules("Tenants pay rent by " + "Zelle " * 40)
    assert [hit.rule_id for hit in quiet] == []
    assert "payment.zelle_before_viewing" in [hit.rule_id for hit in loud]
