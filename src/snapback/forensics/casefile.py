"""The ring case file and the guided case study, both built from the detector's own output.

An investigator needs three things that a ring summary does not give: the ads in posting order,
the link that tied each one to the ones before it (with the evidence behind that link), and how
long the ring was posting before the detector flagged it. This module computes them.

    build_case_file(analysis, "A")   one flagged ring as a document: ads, links, signals, gaps
    build_case_study(analysis)       the same detector replayed day by day over one ring

Nothing here is written by hand. Every link comes from `LinkGraph` (the number, the photo-set
node, the phrasing node, a shared site) and every "flagged on" date comes from running
`analyze` again on only the ads posted up to that day, the same way `detect.py` does for the
90-day stream. Everything is SYNTHETIC (`fixtures/forensics/`): 555 numbers, made-up places.
"""

import re
from datetime import date
from typing import Any

from snapback.forensics import SYNTHETIC_LABEL
from snapback.forensics.corpus import Corpus
from snapback.forensics.extract import pressure_sentences
from snapback.forensics.graph import LinkGraph, hamming
from snapback.forensics.pipeline import Analysis, analyze, default_analysis
from snapback.forensics.rings import MIN_ADS, MIN_PHONES, W_PHONE, W_PHOTO, W_PHRASE, Ring

SCHEMA = "snapback.case_file.v1"
# A site named in an ad is context for the investigator; the ring finder does not link on it.
W_LINK = 0
WEIGHTS = {"phone": W_PHONE, "photo": W_PHOTO, "wording": W_PHRASE, "link": W_LINK}
KIND_NAME = {
    "phone": "shared phone",
    "photo": "shared photo hash",
    "wording": "shared wording",
    "link": "shared link",
}
_URL = re.compile(r"https?://([^/\s]+)")
_MONEY = re.compile(r"\$\s?(\d[\d,]*)")
_FIRST_MONTH = re.compile(r"first month|month'?s rent", re.IGNORECASE)
_DEPOSIT = re.compile(r"deposit|booking|holding|reserv", re.IGNORECASE)

# What no amount of ad text can tell an investigator. These are always true of this data.
ALWAYS_UNKNOWN = [
    "Who operates the ring. Every number is a fictional 555 number and every place is made up, "
    "so no person or account is identified.",
    "Whether any renter paid. The corpus holds ads only: no replies, no payments, no reports.",
    "Whether two numbers are one person. A shared number, photo or wording is a link between "
    "ads, never proof about who posted them.",
    "Ads that were never collected. The ring is what the detector links inside this corpus; "
    "there may be more ads outside it.",
]


def _days_between(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _hosts(text: str) -> set[str]:
    return {h.lower() for h in _URL.findall(text)}


def _min_bits(graph: LinkGraph, a: int, b: int, nodes: list[str]) -> int:
    best = 64
    for node in nodes:
        for p in graph.ad_photos[a][node]:
            for q in graph.ad_photos[b][node]:
                best = min(best, hamming(p, q))
    return best


def pair_ties(graph: LinkGraph, a: int, b: int) -> list[dict[str, Any]]:
    """Every signal tying ad `a` (older) to ad `b` (newer), each with its evidence."""
    ads = graph.ads
    ties: list[dict[str, Any]] = []
    if ads[a].phone == ads[b].phone:
        ties.append(
            {"kind": "phone", "weight": W_PHONE, "evidence": {"phone": ads[a].phone}},
        )
    nodes = graph.shared_photo_nodes(a, b)
    if nodes:
        ties.append(
            {
                "kind": "photo",
                "weight": W_PHOTO,
                "evidence": {
                    "photo_sets": len(nodes),
                    "ids_older": [p for n in nodes for p in graph.ad_photos[a][n]],
                    "ids_newer": [p for n in nodes for p in graph.ad_photos[b][n]],
                    "closest_bits": _min_bits(graph, a, b, nodes),
                    # one shared picture alone can be stock; the ring finder needs two
                    "strong": len(nodes) >= 2,
                },
            }
        )
    older = {link.node: link for link in graph.phrase_links.get(a, [])}
    for link in graph.phrase_links.get(b, []):
        if link.node in older:
            ties.append(
                {
                    "kind": "wording",
                    "weight": W_PHRASE,
                    "evidence": {
                        "span_older": older[link.node].sentence,
                        "span_newer": link.sentence,
                        "reworded": older[link.node].sentence != link.sentence,
                    },
                }
            )
            break
    hosts = _hosts(ads[a].text) & _hosts(ads[b].text)
    if hosts:
        ties.append(
            {"kind": "link", "weight": W_LINK, "evidence": {"hosts": sorted(hosts)}},
        )
    return ties


def first_ties(
    graph: LinkGraph, ad_id: int, earlier: list[int], only: set[str] | None = None
) -> list[dict[str, Any]]:
    """For one ad, the earliest older ring ad it shares each kind of signal with. One link per
    kind keeps the file readable: a ring of 22 ads has 231 pairs, and the first tie is the one
    an investigator follows back."""
    out: list[dict[str, Any]] = []
    done: set[str] = set()
    for other in earlier:
        for tie in pair_ties(graph, other, ad_id):
            if tie["kind"] in done or (only and tie["kind"] not in only):
                continue
            done.add(tie["kind"])
            out.append({"from_ad": other, "to_ad": ad_id, **tie})
    return out


def amount_asked(graph: LinkGraph, ad_id: int) -> dict[str, Any]:
    """The payment ask in an ad: the sentence, and an amount only when the ad gives one. A
    booking fee with no figure stays `None`: guessing a number would be inventing evidence."""
    ad = graph.ads[ad_id]
    sentences = pressure_sentences(graph.facts[ad_id])
    if not sentences:
        return {"sentence": None, "item": None, "usd": None, "basis": "no payment ask found"}
    sentence = sentences[0][0]
    stated = _MONEY.search(sentence)
    if stated:
        return {
            "sentence": sentence,
            "item": "amount stated in the ad",
            "usd": int(stated.group(1).replace(",", "")),
            "basis": "stated in the ad",
        }
    if _FIRST_MONTH.search(sentence):
        return {
            "sentence": sentence,
            "item": "first month's rent",
            "usd": ad.rent,
            "basis": "equals the listed monthly rent",
        }
    item = "deposit or booking amount" if _DEPOSIT.search(sentence) else "payment before viewing"
    return {"sentence": sentence, "item": item, "usd": None, "basis": "amount not stated"}


# ---- the replay -----------------------------------------------------------------------------


_PREFIX_CACHE: dict[tuple[int, str], Analysis] = {}


def analysis_through(corpus: Corpus, through: str) -> Analysis:
    """The ring finder run on only the ads posted up to and including `through`."""
    key = (id(corpus), through)
    if key not in _PREFIX_CACHE:
        seen = [ad for ad in corpus.ads if ad.posted_at <= through]
        prefix = Corpus(label=corpus.label, seed=corpus.seed, ads=seen)
        _PREFIX_CACHE[key] = analyze(prefix)
    return _PREFIX_CACHE[key]


def replay(analysis: Analysis, ring: Ring) -> dict[str, Any]:
    """Run the detector on each posting day of the ring. Returns the days (with the group the
    detector reported that overlaps the ring) and the first day it held `MIN_ADS` ring ads."""
    members = set(ring.ad_ids)
    dates = sorted({analysis.graph.ads[a].posted_at for a in ring.ad_ids})
    days: list[dict[str, Any]] = []
    flagged_on: str | None = None
    for d in dates:
        prefix = analysis_through(analysis.corpus, d)
        best: set[int] = set()
        for group in prefix.rings:
            overlap = set(group.ad_ids) & members
            if len(overlap) > len(best & members):
                best = set(group.ad_ids)
        hit = len(best & members) >= MIN_ADS
        days.append(
            {
                "date": d,
                "ads_in_corpus": len(prefix.corpus.ads),
                "group_size": len(best) if hit else 0,
                "ring_ads_in_group": len(best & members) if hit else 0,
                "flagged": hit,
                "graph": prefix.graph,
            }
        )
        if hit and flagged_on is None:
            flagged_on = d
    return {"days": days, "flagged_on": flagged_on}


def _ring_ads_by_day(analysis: Analysis, ring: Ring) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for a in ring.ad_ids:  # ring.ad_ids is already in posting order
        out.setdefault(analysis.graph.ads[a].posted_at, []).append(a)
    return out


def _ad_row(graph: LinkGraph, ad_id: int) -> dict[str, Any]:
    ad = graph.ads[ad_id]
    return {
        "id": ad.id,
        "posted_at": ad.posted_at,
        "phone": ad.phone,
        "hood": ad.hood,
        "beds": ad.beds,
        "rent": ad.rent,
        "title": ad.title,
        "text": ad.text,
        "photos": ad.photos,
        "amount_asked": amount_asked(graph, ad_id),
    }


# ---- the case file --------------------------------------------------------------------------


def build_case_file(analysis: Analysis, ring_id: str) -> dict[str, Any] | None:
    ring = analysis.ring(ring_id)
    if ring is None:
        return None
    graph = analysis.graph
    run = replay(analysis, ring)
    flagged_on = run["flagged_on"]
    by_day = _ring_ads_by_day(analysis, ring)
    order = list(ring.ad_ids)
    first_ad = order[0]
    first_date = graph.ads[first_ad].posted_at

    links: list[dict[str, Any]] = []
    for i, ad_id in enumerate(order[1:], start=1):
        ties = first_ties(graph, ad_id, order[:i])
        links += ties
    # A tie counts in both directions: an earlier ad that a later ad reuses is tied too.
    tied: set[int] = set()
    for i, older in enumerate(order):
        for newer in order[i + 1 :]:
            if any(t["weight"] > 0 for t in pair_ties(graph, older, newer)):
                tied.update((older, newer))
    untied = [a for a in order if a not in tied]

    signals = []
    for kind, weight in WEIGHTS.items():
        mine = [lk for lk in links if lk["kind"] == kind]
        signals.append(
            {
                "kind": kind,
                "label": KIND_NAME[kind],
                "weight": weight,
                "n_links": len(mine),
                "strength": len(mine) * weight,
                "ads": sorted({x for lk in mine for x in (lk["from_ad"], lk["to_ad"])}),
            }
        )
    ranked = [s for s in sorted(signals, key=lambda s: -s["strength"]) if s["strength"] > 0]
    strongest = [s["kind"] for s in ranked[:2]]

    before = [a for a in order if flagged_on and graph.ads[a].posted_at < flagged_on]
    flag_ads = by_day.get(flagged_on or "", [])
    detection: dict[str, Any] = {
        "first_ad_id": first_ad,
        "first_ad_date": first_date,
        "flagged_on": flagged_on,
        "flag_ad_id": flag_ads[-1] if flag_ads else None,
        "days_first_ad_to_flag": None
        if flagged_on is None
        else _days_between(first_date, flagged_on),
        "ads_up_before_flag": len(before),
        "ads_total": len(order),
        "method": (
            f"The ring finder was run once for each day the ring posted, on only the ads posted "
            f"up to that day. The flag is the first day it reported a group holding at least "
            f"{MIN_ADS} of this ring's ads."
        ),
    }

    not_known = list(ALWAYS_UNKNOWN)
    if flagged_on is None:
        not_known.append("The flag day. The detector never reported this ring on its own days.")
    if untied:
        if len(untied) == 1:
            subject, verb = f"ad {untied[0]}", "carries"
        else:
            subject, verb = f"ads {', '.join(map(str, untied))}", "carry"
        not_known.append(
            f"Why {subject} belong{'s' if len(untied) == 1 else ''}. "
            f"{'It' if len(untied) == 1 else 'They'} {verb} no number, photo, wording or site "
            f"tie to any other ad in the ring."
        )
    weak = [lk for lk in links if lk["kind"] == "photo" and not lk["evidence"]["strong"]]
    if weak:
        not_known.append(
            f"{len(weak)} photo link(s) rest on one shared picture, which can be stock."
        )
    if ring.sources:
        not_known.append(
            f"Where the photos came from. {len(ring.sources)} honest older ads (first "
            f"{', '.join(map(str, ring.sources[:5]))}) had photos the ring reused; they are not "
            f"part of the ring."
        )
    if not any(lk["kind"] == "link" for lk in links):
        not_known.append(
            "Any shared website. No ad in this corpus names one, so that signal was checked "
            "and found empty, not skipped."
        )

    phones: dict[str, list[int]] = {}
    for a in order:
        phones.setdefault(graph.ads[a].phone, []).append(a)

    return {
        "schema": SCHEMA,
        "label": SYNTHETIC_LABEL,
        "synthetic": True,
        "source": "FIXTURE",
        "ring": {
            "id": ring.id,
            "label": ring.label,
            "n_ads": len(order),
            "n_phones": len(phones),
            "first_seen": ring.first_seen,
            "last_seen": ring.last_seen,
            "score": ring.score,
        },
        "detection": detection,
        "timeline": [_ad_row(graph, a) for a in order],
        "contacts": [{"phone": p, "ad_ids": ids} for p, ids in sorted(phones.items())],
        "links": links,
        "signals": signals,
        "strongest": strongest,
        "findings": [
            {"kind": f.kind, "title": f.title, "summary": f.summary, "score": f.score}
            for f in ring.findings
        ],
        "sources": ring.sources,
        "not_known": not_known,
    }


# ---- the case study -------------------------------------------------------------------------


def _tie_sentence(tie: dict[str, Any]) -> str:
    ev = tie["evidence"]
    other = tie["from_ad"]
    if tie["kind"] == "phone":
        return f"It uses the same number as ad {other} ({ev['phone']})."
    if tie["kind"] == "photo":
        strength = "" if ev["strong"] else " (one picture only: could be stock)"
        recrop = ", re-cropped" if ev["closest_bits"] > 0 else ""
        return (
            f"It reuses {ev['photo_sets']} photo set(s) from ad {other}{recrop}: the closest "
            f"pair differs by {ev['closest_bits']} of 64 bits{strength}."
        )
    if tie["kind"] == "wording":
        return (
            f"Its payment ask matches ad {other}: “{ev['span_newer']}” against “{ev['span_older']}”"
        )
    return f"It names the same site as ad {other} ({', '.join(ev['hosts'])})."


def build_case_study(analysis: Analysis, ring_id: str | None = None) -> dict[str, Any] | None:
    """Walk one ring from its first ad to the day the detector flagged it."""
    ring = pick_study_ring(analysis) if ring_id is None else analysis.ring(ring_id)
    if ring is None:
        return None
    graph = analysis.graph
    run = replay(analysis, ring)
    flagged_on = run["flagged_on"]
    by_day = _ring_ads_by_day(analysis, ring)
    first_date = ring.first_seen
    seen: list[int] = []
    seen_phones: set[str] = set()
    steps: list[dict[str, Any]] = []
    for day in run["days"]:
        d = day["date"]
        prefix_graph: LinkGraph = day["graph"]
        lines: list[str] = []
        ties_today: list[dict[str, Any]] = []
        for ad_id in by_day[d]:
            ad = graph.ads[ad_id]
            fresh_phone = ad.phone not in seen_phones
            if not seen:
                lines.append(
                    f"Ad {ad_id} goes up from {ad.phone}: {ad.hood}, ${ad.rent}/month. "
                    f"The detector has one ad. There is nothing to compare it with."
                )
            else:
                number = "a new number" if fresh_phone else "a number already used"
                lines.append(
                    f"Ad {ad_id} goes up from {ad.phone} ({number}): {ad.hood}, ${ad.rent}/month."
                )
                ties = first_ties(prefix_graph, ad_id, seen)
                ties_today += ties
                if ties:
                    lines += [_tie_sentence(t) for t in ties]
                else:
                    lines.append("No number, photo or wording ties it to an earlier ad yet.")
            seen.append(ad_id)
            seen_phones.add(ad.phone)
        n_seen = len(seen)
        if day["flagged"]:
            verdict = (
                f"FLAGGED. Run on the {day['ads_in_corpus']} ads posted so far, the detector "
                f"reports a group of {day['group_size']} ads that holds {day['ring_ads_in_group']} "
                f"of this ring's {n_seen}."
            )
        else:
            noun = "ad" if n_seen == 1 else "ads"
            verdict = (
                f"Not flagged. The detector sees {n_seen} {noun} of this ring among "
                f"{day['ads_in_corpus']} posted so far; a ring needs at least {MIN_ADS} ads on "
                f"{MIN_PHONES} different numbers and linked by shared signals."
            )
        steps.append(
            {
                "step": len(steps) + 1,
                "date": d,
                "day_no": _days_between(first_date, d) + 1,
                "ad_ids": list(by_day[d]),
                "ring_ads_so_far": n_seen,
                "numbers_so_far": len(seen_phones),
                "ties": ties_today,
                "lines": lines,
                "detector": verdict,
                "flagged": day["flagged"],
            }
        )
        if day["flagged"]:
            break
    after = [a for a in ring.ad_ids if flagged_on and graph.ads[a].posted_at > flagged_on]
    case_file = build_case_file(analysis, ring.id)
    assert case_file is not None
    return {
        "schema": "snapback.case_study.v1",
        "label": SYNTHETIC_LABEL,
        "synthetic": True,
        "source": "FIXTURE",
        "ring": {"id": ring.id, "label": ring.label, "n_ads": len(ring.ad_ids)},
        "flagged_on": flagged_on,
        "days_first_ad_to_flag": case_file["detection"]["days_first_ad_to_flag"],
        "steps": steps,
        "after": {
            "n_ads": len(after),
            "last_date": graph.ads[after[-1]].posted_at if after else None,
            "text": (
                f"{len(after)} more ad(s) from this ring followed after the flag, up to "
                f"{graph.ads[after[-1]].posted_at}."
                if after
                else "No ad of this ring was posted after the flag."
            ),
        },
        "strongest": case_file["strongest"],
        "not_known": case_file["not_known"],
    }


def pick_study_ring(analysis: Analysis) -> Ring | None:
    """The ring whose story is easiest to follow: the smallest ring the detector flags that
    reaches the flag with a photo tie among the ads before it. Falls back to the smallest."""
    scored = []
    for ring in analysis.rings:
        run = replay(analysis, ring)
        if run["flagged_on"] is None:
            continue
        by_day = _ring_ads_by_day(analysis, ring)
        seen: list[int] = []
        photo = False
        for day in run["days"]:
            for a in by_day[day["date"]]:
                if seen and any(t["kind"] == "photo" for t in first_ties(day["graph"], a, seen)):
                    photo = True
                seen.append(a)
            if day["flagged"]:
                break
        scored.append((not photo, len(ring.ad_ids), ring.id, ring))
    if not scored:
        return None
    return sorted(scored, key=lambda s: s[:3])[0][3]


def default_case_file(ring_id: str) -> dict[str, Any] | None:
    return build_case_file(default_analysis(), ring_id)
