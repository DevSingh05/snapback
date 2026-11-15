"""Robustness attack on the ring finder: reword every ad so ring members no longer share text.

    uv run python -m snapback.forensics.paraphrase [--out FILE] [--seed N]

SYNTHETIC data only. The operator behind a ring keeps one template and rewords it; here the
reword is pushed as far as a text-only edit can go, and the finder is run again. The question:
does the finder still link the ring, or did it only ever match shared words?

The rewrite is deterministic (one `random.Random` per ad, seeded from the run seed and the ad
id), so CI gets the same bytes every time:

- an ask for money (what `extract.pressure_sentences` would call one) is replaced by a sentence
  built from parts, so two members almost never share it;
- the pretext line and the sign-off are replaced from a larger pool than the generator uses;
- the remaining sentences are reordered and a few words are swapped for equivalents;
- a dollar amount is rewritten in another format (none appear in the default corpus; the rule
  is covered by a test).

Phone numbers, photo ids and links are NOT changed: a text edit does not change them. A second
stress variant (`photos_reshot`) also gives every ring ad fresh photo ids, as if the operator had
re-shot the pictures. A third (`wording_only`) strips phones and photos from the finder's view
altogether, to show how much the wording alone carries.

An optional LIVE variant asks a hosted model to reword the ask sentences. It runs only when the
key is already in the environment, never prints it, is labelled LIVE and is not run in CI.
"""

import argparse
import json
import os
import random
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from snapback.forensics import SYNTHETIC_LABEL
from snapback.forensics.corpus import Ad, Corpus
from snapback.forensics.evaluate import _score, keyword_groups
from snapback.forensics.extract import extract_facts, pressure_sentences
from snapback.forensics.generate import _hash
from snapback.forensics.pipeline import analyze
from snapback.forensics.rings import MIN_ADS
from snapback.forensics.stream import DEFAULT_SEED, generate_stream

RESULTS_PATH = (
    Path(__file__).resolve().parents[3] / "eval" / "forensics" / "paraphrase_results.json"
)

# An ask is built as: lead + payment + timing + outcome. Some parts use the words the finder folds
# onto one concept (remit, ahead of, keys); many do not (settle, charge, beforehand, door code),
# which is what a human rewriter or a model would also produce.
_LEAD = [
    "Please",
    "Kindly",
    "You need to",
    "I will need you to",
    "Just",
    "To proceed,",
    "Go ahead and",
    "First,",
    "Quickly",
    "To lock it in,",
]
_VERB = [
    "settle",
    "get",
    "pay",
    "send over",
    "arrange",
    "put down",
    "clear",
    "wire",
    "transfer",
    "deliver",
    "submit",
    "complete",
]
_THING = [
    "the reservation charge",
    "the holding deposit",
    "your first month",
    "the booking amount",
    "the move-in funds",
    "a small hold fee",
    "the advance",
    "the security amount",
    "the initial rent",
    "the commitment payment",
]
_TIMING = [
    "beforehand",
    "ahead of any viewing",
    "before we meet",
    "today",
    "right away",
    "up front",
    "in advance",
    "before the walk-through",
    "first of all",
    "by tomorrow",
]
_OUTCOME = [
    "and the door code is yours",
    "then the place is held in your name",
    "and I will courier the keys",
    "and the unit comes off the market for you",
    "after that I send the lease",
    "so nobody else gets it",
    "and the lockbox number follows",
    "and you are first in line",
]
_PRETEXT = [
    "I am travelling for work and cannot show it in person.",
    "The landlord lives abroad, so I handle everything remotely.",
    "I am away on a long assignment and can only reply by message.",
    "We are between managers right now, so no one is on site to show it.",
    "I cannot meet anyone in person because I am posted overseas.",
]
_SIGNOFF = [
    "Best wishes, Owner's Office.",
    "Thanks and regards, Office of the Owner.",
    "Kind regards.",
    "Cheers from the owner's desk.",
    "",
]
_SWAP = [
    (r"\bbright\b", "sunny"),
    (r"\bsunny\b", "bright"),
    (r"\bwell kept\b", "nicely maintained"),
    (r"\bwelcome to\b", "come and see"),
    (r"\bhome\b", "place"),
    (r"\bapartment\b", "flat"),
    (r"\bquiet\b", "peaceful"),
    (r"\bsmall\b", "compact"),
]
_MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?")

Rewriter = Callable[[str, random.Random], str]


def _price(match: re.Match[str], rng: random.Random) -> str:
    amount = int(match.group(1).replace(",", ""))
    return rng.choice([f"{amount} dollars", f"USD {amount:,}", f"${amount}", f"{amount:,} USD"])


def reformat_prices(text: str, rng: random.Random) -> str:
    return _MONEY.sub(lambda m: _price(m, rng), text)


def build_ask(rng: random.Random) -> str:
    """One new payment-first sentence from parts; about 10^6 combinations."""
    lead = rng.choice(_LEAD)
    verb, thing, timing = rng.choice(_VERB), rng.choice(_THING), rng.choice(_TIMING)
    ask = f"{lead} {verb} {thing} {timing}, {rng.choice(_OUTCOME)}."
    return ask[0].upper() + ask[1:]


def _swap_words(sentence: str, rng: random.Random) -> str:
    for pattern, repl in _SWAP:
        if rng.random() < 0.5:
            sentence = re.sub(pattern, repl, sentence, count=1, flags=re.IGNORECASE)
    return sentence


def paraphrase_ad(ad: Ad, seed: int, *, is_ring: bool, rewrite_ask: Rewriter | None = None) -> Ad:
    """A reworded copy of `ad`. Honest ads keep every sentence's meaning (a guarded deposit line
    stays guarded); ring ads also get a new ask, pretext and sign-off."""
    rng = random.Random(f"{seed}:{ad.id}")
    facts = extract_facts(ad)
    asks = {s for s, _ in pressure_sentences(facts)} if is_ring else set()
    pretexts = _pretext_lines()
    out: list[str] = []
    for sentence in facts.sentences:
        if sentence in asks:
            sentence = rewrite_ask(sentence, rng) if rewrite_ask else build_ask(rng)
        elif is_ring and sentence in pretexts:
            sentence = rng.choice(_PRETEXT)
        elif is_ring and sentence in _signoffs():
            sentence = rng.choice(_SIGNOFF)
        else:
            sentence = _swap_words(sentence, rng)
        if sentence:
            out.append(reformat_prices(sentence, rng))
    if len(out) > 2:
        head, tail = out[0], out[1:]
        rng.shuffle(tail)
        out = [head, *tail]  # the opener stays first, the rest is reordered
    return ad.model_copy(update={"text": " ".join(out)})


def _pretext_lines() -> set[str]:
    from snapback.forensics.generate import PRETEXT

    return {p for p in PRETEXT if p}


def _signoffs() -> set[str]:
    from snapback.forensics.generate import SIGNOFFS

    return {p for p in SIGNOFFS if p}


def paraphrase_corpus(
    corpus: Corpus, ring_ids: set[int], seed: int, rewrite_ask: Rewriter | None = None
) -> Corpus:
    ads = [
        paraphrase_ad(ad, seed, is_ring=ad.id in ring_ids, rewrite_ask=rewrite_ask)
        for ad in corpus.ads
    ]
    return corpus.model_copy(update={"ads": ads})


def reshoot_photos(corpus: Corpus, ring_ids: set[int], seed: int) -> Corpus:
    """Stress: every ring ad gets fresh, unrelated photo ids (the operator re-shot them)."""
    rng = random.Random(f"{seed}:photos")
    ads = [
        ad.model_copy(update={"photos": [_hash(rng) for _ in ad.photos]})
        if ad.id in ring_ids
        else ad
        for ad in corpus.ads
    ]
    return corpus.model_copy(update={"ads": ads})


def wording_only(corpus: Corpus) -> Corpus:
    """Stress: hide every phone and photo from the finder, so only wording can link ads."""
    ads = [
        ad.model_copy(update={"phone": f"555-{ad.id:04d}", "photos": [f"ph-{ad.id:016x}"]})
        for ad in corpus.ads
    ]
    return corpus.model_copy(update={"ads": ads})


def rings_found(found: list[set[int]], truth: dict[str, set[int]]) -> int:
    """A ring counts as found when at least MIN_ADS of its ads sit in the groups reported (the
    same bar `detect.first_union_flag_day` uses for 'flagged')."""
    called = set().union(*found) if found else set()
    return sum(len(members & called) >= MIN_ADS for members in truth.values())


def score_variant(corpus: Corpus, truth: dict[str, set[int]]) -> dict[str, Any]:
    """`pipeline` is the finder as shipped, with the phone and photo-copy fallback;
    `pipeline_wording_seeds` is the same finder seeded by wording only (`hop=False`);
    `keyword_baseline` is the payment-words search."""
    n = len(corpus.ads)
    pipeline = [set(r.ad_ids) for r in analyze(corpus).rings]
    wording = [set(r.ad_ids) for r in analyze(corpus, hop=False).rings]
    keyword = keyword_groups(corpus)
    out: dict[str, Any] = {}
    for name, groups in (
        ("pipeline", pipeline),
        ("pipeline_wording_seeds", wording),
        ("keyword_baseline", keyword),
    ):
        s = _score(groups, truth, n)
        out[name] = {
            "rings_found": rings_found(groups, truth),
            "n_rings": len(truth),
            "rings_told_apart": s["rings_recovered"],
            "ring_ads_flagged": round(s["ad_recall"] * sum(len(v) for v in truth.values())),
            "n_ring_ads": sum(len(v) for v in truth.values()),
            "honest_flagged": s["honest_flagged"],
            "n_honest": s["n_honest"],
            "groups_reported": len(groups),
        }
    return out


def text_overlap(corpus: Corpus, truth: dict[str, set[int]]) -> float:
    """Share of ring-ad pairs, inside one ring, that have an identical payment-first sentence.
    The thing the paraphrase is meant to remove."""
    by_id = corpus.by_id()
    same = total = 0
    for members in truth.values():
        asks = []
        for i in sorted(members):
            facts = extract_facts(by_id[i])
            asks.append({s for s, _ in pressure_sentences(facts)})
        for a in range(len(asks)):
            for b in range(a + 1, len(asks)):
                if asks[a] and asks[b]:
                    total += 1
                    same += bool(asks[a] & asks[b])
    return round(same / total, 3) if total else 0.0


def live_rewriter(post: Callable[[str], str] | None = None, cap: int = 150) -> Rewriter | None:
    """A rewriter backed by a hosted model, or None when no key is configured. Reads the key
    from the environment only and never prints it. `post` is injectable for tests. LIVE output is
    not reproducible."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if post is None:
        if not key:
            return None
        post = _anthropic_post(key)
    calls = {"n": 0}

    def rewrite(sentence: str, rng: random.Random) -> str:
        if calls["n"] >= cap:
            return build_ask(rng)
        calls["n"] += 1
        try:
            reply = post(sentence).strip()
        except Exception:
            return build_ask(rng)
        return reply.splitlines()[0] if reply else build_ask(rng)

    return rewrite


def _anthropic_post(key: str) -> Callable[[str], str]:
    import httpx

    def post(sentence: str) -> str:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json={
                "model": os.environ.get("PARAPHRASE_MODEL", "claude-haiku-4-5"),
                "max_tokens": 80,
                "messages": [
                    {
                        "role": "user",
                        "content": "This is a line from a SYNTHETIC test ad. Reword it in "
                        "different words, same meaning, one sentence, no quotes:\n" + sentence,
                    }
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    return post


def run(seed: int = DEFAULT_SEED, *, live: bool = False) -> dict[str, Any]:
    data, truth_raw = generate_stream(seed)
    corpus = Corpus.model_validate(data)
    truth = {k: {int(i) for i in v} for k, v in truth_raw["rings"].items()}  # type: ignore[union-attr]
    ring_ids = set().union(*truth.values())
    para = paraphrase_corpus(corpus, ring_ids, seed)
    variants: dict[str, Corpus] = {
        "original": corpus,
        "paraphrased": para,
        "paraphrased_photos_reshot": reshoot_photos(para, ring_ids, seed),
        "paraphrased_wording_only": wording_only(para),
    }
    results = {name: score_variant(c, truth) for name, c in variants.items()}
    for name, c in variants.items():
        results[name]["same_ask_pairs_in_ring"] = text_overlap(c, truth)
    out: dict[str, Any] = {
        "label": SYNTHETIC_LABEL,
        "synthetic": True,
        "source": "stream.generate_stream (SYNTHETIC), deterministic paraphrase",
        "seed": seed,
        "n_ads": len(corpus.ads),
        "n_rings": len(truth),
        "n_ring_ads": len(ring_ids),
        "n_honest": len(corpus.ads) - len(ring_ids),
        "found_means": f"a ring is found when at least {MIN_ADS} of its ads are in reported groups",
        "variants": results,
        "live": None,
    }
    if live:
        rewrite = live_rewriter()
        if rewrite is None:
            out["live"] = {"label": "LIVE", "ran": False, "why": "no model key in the environment"}
        else:
            lc = paraphrase_corpus(corpus, ring_ids, seed, rewrite_ask=rewrite)
            out["live"] = {
                "label": "LIVE model paraphrase, not reproducible, not run in CI",
                "ran": True,
                **score_variant(lc, truth),
            }
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=RESULTS_PATH)
    parser.add_argument(
        "--live", action="store_true", help="also run the LIVE variant if a key is set"
    )
    args = parser.parse_args()
    made = run(args.seed, live=args.live)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(made, indent=1, sort_keys=True) + "\n")
    for name, v in made["variants"].items():
        p, h, k = v["pipeline"], v["pipeline_wording_seeds"], v["keyword_baseline"]
        print(
            f"SYNTHETIC {name}: pipeline {p['rings_found']}/{p['n_rings']} rings, "
            f"wording-only seeds {h['rings_found']}/{h['n_rings']}, "
            f"keyword {k['rings_found']}/{k['n_rings']}, "
            f"honest flagged {p['honest_flagged']}/{p['n_honest']} "
            f"({h['honest_flagged']} wording-only seeds)"
        )
    print(f"wrote {args.out}")
