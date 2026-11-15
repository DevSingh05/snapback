"""Time to detect on the SYNTHETIC 90-day stream: the ring finder run once per day, in posting
order, on only the ads posted so far.

    uv run python -m snapback.forensics.detect [--out FILE]

It answers the investigator's first question about a ring: how long was it posting before we
linked it? For every group the finder reports on day 90 it records

- the day its first ad was posted,
- the day it was first flagged: the first day on which the finder, seeing only the ads posted
  up to then, reports a group that shares at least `MIN_ADS` ads with it,
- the gap in days, the ads and ad-days that were up before the flag, and an ESTIMATE of the
  renters who saw them (`VIEWS_PER_AD_DAY` is an assumption, not a measurement),
- the shared signals that link its ads (number, photo-set, wording, site), each with the weight
  the ring finder gives it and the ads that share it.

The seeded answer key is read here only to score the result (`_against_truth`); the finder never
sees it. The output is `fixtures/forensics/stream_timeline.json`, which the web view draws.
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

from snapback.forensics import SYNTHETIC_LABEL
from snapback.forensics.corpus import FIXTURE_DIR, Corpus
from snapback.forensics.graph import LinkGraph
from snapback.forensics.pipeline import Analysis, analyze
from snapback.forensics.rings import MIN_ADS, W_PHONE, W_PHOTO, W_PHRASE, Ring
from snapback.forensics.stream import DAYS, DEFAULT_SEED, START, generate_stream

TIMELINE_PATH = FIXTURE_DIR / "stream_timeline.json"
# ASSUMPTION, not a measurement: how many renters open one ad on each day it is up. It turns
# "ad-days before the flag" into a number of people, and is shown beside every such number.
VIEWS_PER_AD_DAY = 30
# A site named in an ad is context for the investigator; the ring finder does not link on it.
W_SITE = 0
SIGNAL_WEIGHTS = {"phone": W_PHONE, "photo": W_PHOTO, "wording": W_PHRASE, "site": W_SITE}
_SITE = re.compile(r"https?://([^/\s]+)")


def day_index(posted_at: str, start: date = START) -> int:
    """Day 0 is the stream's first day."""
    return (date.fromisoformat(posted_at) - start).days


def daily_groups(corpus: Corpus, days: int = DAYS, start: date = START) -> list[list[set[int]]]:
    """For each day, the groups the ring finder reports when it sees only the ads posted up to
    and including that day."""
    out = []
    for day in range(days):
        seen = [ad for ad in corpus.ads if day_index(ad.posted_at, start) <= day]
        prefix = Corpus(label=corpus.label, seed=corpus.seed, ads=seen)
        out.append([set(r.ad_ids) for r in analyze(prefix).rings] if seen else [])
    return out


def first_flag_day(
    members: set[int], daily: list[list[set[int]]], need: int = MIN_ADS
) -> int | None:
    """The first day one reported group shares at least `need` ads with `members`."""
    for day, groups in enumerate(daily):
        if any(len(group & members) >= need for group in groups):
            return day
    return None


def first_union_flag_day(
    members: set[int], daily: list[list[set[int]]], need: int = MIN_ADS
) -> int | None:
    """The first day at least `need` of `members` sit inside reported groups, whichever groups
    they are. Used for a seeded ring, which the finder may split across groups."""
    for day, groups in enumerate(daily):
        flagged = set().union(*groups) if groups else set()
        if len(flagged & members) >= need:
            return day
    return None


def ad_flag_days(daily: list[list[set[int]]]) -> dict[int, int]:
    """ad id -> the first day it sat inside any reported group."""
    out: dict[int, int] = {}
    for day, groups in enumerate(daily):
        for group in groups:
            for ad_id in group:
                out.setdefault(ad_id, day)
    return out


def exposure(ad_days: list[int], flag_day: int | None, views: int = VIEWS_PER_AD_DAY) -> dict:
    """What was up before the flag. `ad_days` are the posting days of the group's ads. An ad
    posted on day 3 and flagged on day 7 was up, unflagged, for 4 days. With no flag, every ad
    counts to the end of the stream."""
    end = DAYS if flag_day is None else flag_day
    before = [d for d in ad_days if d < end]
    days_up = sum(end - d for d in before)
    return {
        "ads_before_flag": len(before),
        "ad_days_before_flag": days_up,
        "renters_est": days_up * views,
    }


def detection(ad_days: list[int], flag_day: int | None) -> dict:
    first = min(ad_days)
    return {
        "first_day": first,
        "flag_day": flag_day,
        "gap_days": None if flag_day is None else flag_day - first,
        **exposure(ad_days, flag_day),
    }


def signals(graph: LinkGraph, ring: Ring) -> list[dict[str, Any]]:
    """Every value two or more of the ring's ads share, as (kind, key, weight, ads). Ads are in
    posting order, so a link can be drawn on the day its second ad appears."""
    members = set(ring.ad_ids)
    pos = {ad_id: i for i, ad_id in enumerate(ring.ad_ids)}

    def inside(ids: list[int]) -> list[int]:
        return sorted({a for a in ids if a in members}, key=pos.__getitem__)

    out: list[dict[str, Any]] = []
    for phone in ring.phones:
        ids = inside(graph.phone_ads[phone])
        if len(ids) >= 2:
            out.append({"kind": "phone", "key": phone, "label": phone, "ad_ids": ids})
    for node, all_ids in sorted(graph.photo_ads().items()):
        ids = inside(all_ids)
        if len(ids) >= 2:
            out.append(
                {"kind": "photo", "key": node, "label": f"photo-set {node[6:]}", "ad_ids": ids}
            )
    for node, all_ids in sorted(graph.phrase_ads().items()):
        ids = inside(all_ids)
        if len(ids) >= 2:
            first = next(link for link in graph.phrase_links[ids[0]] if link.node == node)
            out.append({"kind": "wording", "key": node, "label": first.sentence, "ad_ids": ids})
    sites: dict[str, list[int]] = {}
    for ad_id in ring.ad_ids:
        for host in sorted(set(_SITE.findall(graph.ads[ad_id].text))):
            sites.setdefault(host, []).append(ad_id)
    for host, ids in sorted(sites.items()):
        if len(ids) >= 2:
            out.append({"kind": "site", "key": host, "label": host, "ad_ids": ids})
    for s in out:
        s["weight"] = SIGNAL_WEIGHTS[s["kind"]]
        s["n_ads"] = len(s["ad_ids"])
    return out


def summarize_signals(items: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Per kind: how many shared values, how many different ads they link, and the weight."""
    out: dict[str, dict[str, int]] = {}
    for kind, weight in SIGNAL_WEIGHTS.items():
        of_kind = [s for s in items if s["kind"] == kind]
        if of_kind:
            out[kind] = {
                "values": len(of_kind),
                "ads": len({a for s in of_kind for a in s["ad_ids"]}),
                "weight": weight,
            }
    return out


def _against_truth(
    analysis: Analysis, daily: list[list[set[int]]], truth: dict[str, Any], days_of: dict[int, int]
) -> dict[str, Any]:
    from snapback.forensics.evaluate import _score

    seeded = {name: {int(i) for i in ids} for name, ids in truth["rings"].items()}
    found = [set(r.ad_ids) for r in analysis.rings]
    score = _score(found, seeded, len(analysis.corpus.ads))
    rows = []
    for name, members in seeded.items():
        flag = first_union_flag_day(members, daily)
        rows.append(
            {
                "name": name,
                "n_ads": len(members),
                "flagged_ads": len(members & set().union(*found)) if found else 0,
                "separated": score["per_ring"][name]["recovered"],
                **detection([days_of[a] for a in members], flag),
            }
        )
    gaps = [r["gap_days"] for r in rows if r["gap_days"] is not None]
    return {
        "n_seeded": len(seeded),
        "seeded_flagged": len(gaps),
        "seeded_separated": score["rings_recovered"],
        "median_gap_days": median(gaps) if gaps else None,
        "n_gap": len(gaps),
        "ring_ads": sum(len(m) for m in seeded.values()),
        "ring_ads_flagged": sum(r["flagged_ads"] for r in rows),
        "honest_flagged": score["honest_flagged"],
        "n_honest": score["n_honest"],
        "seeded": rows,
    }


def build_timeline(
    corpus: Corpus,
    truth: dict[str, Any],
    days: int = DAYS,
    start: date = START,
    daily: list[list[set[int]]] | None = None,
) -> dict[str, Any]:
    """The whole view as one plain dict: groups with their ads, signals and detection, the daily
    counts, and the score against the answer key."""
    analysis = analyze(corpus)
    daily = daily if daily is not None else daily_groups(corpus, days, start)
    days_of = {ad.id: day_index(ad.posted_at, start) for ad in corpus.ads}
    flagged_on = ad_flag_days(daily)
    seeded_of = {int(a): name for name, ids in truth["rings"].items() for a in ids}
    groups = []
    for ring in analysis.rings:
        members = set(ring.ad_ids)
        found = signals(analysis.graph, ring)
        mix: dict[str, int] = {}
        for ad_id in ring.ad_ids:
            name = seeded_of.get(ad_id, "honest")
            mix[name] = mix.get(name, 0) + 1
        groups.append(
            {
                "id": ring.id,
                "label": ring.label,
                "n_ads": len(ring.ad_ids),
                "n_phones": len(ring.phones),
                "score": ring.score,
                **detection([days_of[a] for a in ring.ad_ids], first_flag_day(members, daily)),
                "ads": [
                    {
                        "id": a,
                        "day": days_of[a],
                        "flag_day": flagged_on.get(a, days - 1),
                        "phone": analysis.graph.ads[a].phone,
                        "hood": analysis.graph.ads[a].hood,
                        "rent": analysis.graph.ads[a].rent,
                    }
                    for a in ring.ad_ids
                ],
                "signals": found,
                "by_kind": summarize_signals(found),
                "findings": [
                    {"kind": f.kind, "title": f.title, "summary": f.summary, "score": f.score}
                    for f in ring.findings
                ],
                "answer_key": dict(sorted(mix.items())),
            }
        )
    in_group = {a for g in groups for a in (ad["id"] for ad in g["ads"])}
    other = [0] * days
    for ad in corpus.ads:
        if ad.id not in in_group:
            other[days_of[ad.id]] += 1
    gaps = [g["gap_days"] for g in groups if g["gap_days"] is not None]
    return {
        "label": SYNTHETIC_LABEL,
        "synthetic": True,
        "source": "FIXTURE",
        "seed": corpus.seed,
        "start": start.isoformat(),
        "days": days,
        "n_ads": len(corpus.ads),
        "min_ads": MIN_ADS,
        "views_per_ad_day": VIEWS_PER_AD_DAY,
        "weights": SIGNAL_WEIGHTS,
        "groups": groups,
        "other_ads_by_day": other,
        "flagged_ads_by_day": [len(set().union(*g)) if g else 0 for g in daily],
        "groups_by_day": [len(g) for g in daily],
        "summary": {
            "groups_found": len(groups),
            "median_gap_days": median(gaps) if gaps else None,
            "n_gap": len(gaps),
            "renters_est": sum(g["renters_est"] for g in groups),
        },
        "answer_key": _against_truth(analysis, daily, truth, days_of),
    }


def default_timeline(seed: int = DEFAULT_SEED) -> dict[str, Any]:
    data, truth = generate_stream(seed)
    return build_timeline(Corpus.model_validate(data), truth)


def load_timeline(path: Path = TIMELINE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=TIMELINE_PATH)
    args = parser.parse_args()
    made = default_timeline(args.seed)
    args.out.write_text(json.dumps(made, indent=1, sort_keys=True) + "\n")
    key = made["answer_key"]
    print(
        f"SYNTHETIC stream, seed {args.seed}: {made['n_ads']} ads over {made['days']} days; "
        f"{made['summary']['groups_found']} groups, median time to detect "
        f"{made['summary']['median_gap_days']} days (n={made['summary']['n_gap']}); "
        f"seeded rings flagged {key['seeded_flagged']} of {key['n_seeded']}, "
        f"told apart {key['seeded_separated']} of {key['n_seeded']}; "
        f"ring ads flagged {key['ring_ads_flagged']} of {key['ring_ads']}; "
        f"honest ads flagged {key['honest_flagged']} of {key['n_honest']}"
    )
    print(f"wrote {args.out}")
