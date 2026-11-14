"""Step 5: a measured number. Ring precision and recall on the seeded ground truth, next to a
keyword-search baseline run on the same ads.

The baseline is what an investigator does without the pipeline: search the ads for the obvious
payment-first words, then group the hits that share an exact phone number or an exact photo id.
Both are scored the same way:

- ad level: of the ads called "in a ring", how many truly are (precision), and of the true ring
  ads, how many were called (recall);
- ring level: a true ring is *recovered* when one found group holds at least 70 percent of its
  ads and at least 70 percent of that group is the ring. Ring precision is recovered groups over
  found groups; ring recall is recovered true rings over true rings.

The truth is only read here; the pipeline never sees it. All of it is SYNTHETIC data.
"""

import re
from typing import Any

from snapback.forensics.corpus import Corpus, load_truth
from snapback.forensics.graph import _Union
from snapback.forensics.pipeline import Analysis, analyze
from snapback.forensics.rings import MIN_ADS

OVERLAP = 0.7

KEYWORDS = re.compile(
    r"zelle|\bwire\b|western union|gift ?card|cash ?app|venmo|bitcoin|"
    r"before move-?in|before moving in|prior to move-?in|deposit first",
    re.IGNORECASE,
)


def keyword_groups(corpus: Corpus) -> list[set[int]]:
    """Keyword hits, grouped by exact phone or exact photo id; groups of MIN_ADS or more."""
    hits = [ad for ad in corpus.ads if KEYWORDS.search(ad.text)]
    union = _Union([ad.id for ad in hits])
    by_key: dict[str, int] = {}
    for ad in hits:
        for key in [ad.phone, *ad.photos]:
            if key in by_key:
                union.join(by_key[key], ad.id)
            else:
                by_key[key] = ad.id
    groups: dict[int, set[int]] = {}
    for ad in hits:
        groups.setdefault(union.find(ad.id), set()).add(ad.id)
    return [g for g in groups.values() if len(g) >= MIN_ADS]


def _score(found: list[set[int]], truth: dict[str, set[int]]) -> dict[str, Any]:
    called = set().union(*found) if found else set()
    real = set().union(*truth.values())
    tp = len(called & real)
    recovered = 0
    per_ring = {}
    for name, members in truth.items():
        best = max(found, key=lambda g: len(g & members), default=set())
        overlap = len(best & members)
        ok = bool(best) and overlap / len(members) >= OVERLAP and overlap / len(best) >= OVERLAP
        per_ring[name] = {
            "ads": len(members),
            "found_ads": overlap,
            "recovered": ok,
        }
        recovered += ok
    return {
        "ad_precision": round(tp / len(called), 3) if called else 0.0,
        "ad_recall": round(tp / len(real), 3),
        "ring_precision": round(recovered / len(found), 3) if found else 0.0,
        "ring_recall": round(recovered / len(truth), 3),
        "rings_found": len(found),
        "rings_recovered": recovered,
        "per_ring": per_ring,
    }


def evaluate(analysis: Analysis | None = None, truth: dict[str, list[int]] | None = None) -> dict:
    from snapback.forensics.corpus import load_corpus
    from snapback.forensics.pipeline import default_analysis

    analysis = analysis or default_analysis()
    truth = truth if truth is not None else load_truth()
    truth_sets = {k: set(v) for k, v in truth.items()}
    found = [set(r.ad_ids) for r in analysis.rings]
    corpus = analysis.corpus or load_corpus()
    return {
        "synthetic": True,
        "n_ads": len(corpus.ads),
        "n_true_rings": len(truth_sets),
        "n_true_ring_ads": sum(len(v) for v in truth_sets.values()),
        "pipeline": _score(found, truth_sets),
        "keyword_baseline": _score(keyword_groups(corpus), truth_sets),
    }


def evaluate_seed(seed: int) -> dict:
    """Generate a fresh corpus with `seed` in memory and score the pipeline on it."""
    from snapback.forensics.corpus import Corpus
    from snapback.forensics.generate import generate

    data, truth = generate(seed)
    corpus = Corpus.model_validate(data)
    return evaluate(analyze(corpus), {k: list(v) for k, v in truth["rings"].items()})  # type: ignore[union-attr]
