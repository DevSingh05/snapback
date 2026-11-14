"""Step 4: communities (rings), their findings with evidence pointers, and their timelines.

How a ring is found, in order:

1. Seeds are the ads that ask for money first (`extract.pressure_sentences`).
2. Two seeds are linked when they share a phone number, a phrasing node, or two or more
   photo-sets (one shared picture alone is not enough: it can be stock). Louvain communities on
   those weighted links give the candidates; a single weak link between two rings is cut.
3. A quiet ad (no payment ask of its own) is attached only on strong evidence: it shares a phone
   with the community AND it is a copier (it reposted photos that an older ad under a different
   number posted), or it shares at least `ATTACH_WEIGHT` worth of links with the community.
   An older ad whose photos were copied is the *source*, never a member: honest listings that
   were copied stay out of the ring and are reported as the source of a copy.
4. A community is a ring when it has at least `MIN_ADS` ads and `MIN_PHONES` different numbers:
   one operator rotating numbers. One number with many ads is a property manager, not a ring.

Every finding carries pointers: ad ids, the matched sentence or the photo ids, and a score.
"""

from collections import Counter
from datetime import date

from pydantic import BaseModel, Field

from snapback.forensics.graph import LinkGraph, hamming
from snapback.forensics.louvain import louvain

MIN_ADS = 4
MIN_PHONES = 2
ATTACH_WEIGHT = 4
W_PHONE, W_PHRASE, W_PHOTO, W_COPIER = 2, 2, 3, 2
BRIDGE_SHARE = 0.5


class Evidence(BaseModel):
    ad_id: int
    span: str | None = None  # the matched sentence
    photo_ids: list[str] = Field(default_factory=list)
    phone: str | None = None
    rule_id: str | None = None
    score: float | None = None


class Finding(BaseModel):
    id: str
    kind: str  # photo_reuse | phone_rotation | shared_phrasing | copied_listing | pretext
    title: str
    summary: str
    score: float
    evidence: list[Evidence]


class TimelineEvent(BaseModel):
    date: str
    ad_id: int
    kind: str  # first_ad | new_phone | new_photo_set | ad
    detail: str


class Ring(BaseModel):
    id: str
    label: str  # "Ring A"
    synthetic: bool = True
    ad_ids: list[int]
    phones: list[str]
    photo_sets: list[str]
    first_seen: str
    last_seen: str
    score: float
    sources: list[int] = Field(default_factory=list)  # honest ads whose photos were copied
    findings: list[Finding]
    timeline: list[TimelineEvent]
    weekly: list[tuple[str, int]]  # ISO week start -> ads posted that week


def _pressure(graph: LinkGraph) -> set[int]:
    return {ad_id for ad_id, links in graph.phrase_links.items() if links}


def _strong_photo(graph: LinkGraph, a: int, b: int) -> list[str]:
    shared = graph.shared_photo_nodes(a, b)
    return shared if len(shared) >= 2 else []


def _copiers(graph: LinkGraph) -> dict[int, int]:
    """ad -> the older ad it copied photos from (under a different number)."""
    order = sorted(graph.ads.values(), key=lambda ad: (ad.posted_at, ad.id))
    pos = {ad.id: i for i, ad in enumerate(order)}
    out: dict[int, int] = {}
    by_node = graph.photo_ads()
    for ad in order:
        older = {
            other
            for node in graph.ad_photos[ad.id]
            for other in by_node[node]
            if other != ad.id and pos[other] < pos[ad.id] and _strong_photo(graph, ad.id, other)
        }
        if not older:
            continue
        if any(graph.ads[o].phone == ad.phone for o in older):
            continue  # the owner relisting their own unit
        out[ad.id] = min(older, key=lambda o: pos[o])
    return out


def _merge_bridged(comps: dict[int, set[int]], adj: dict[int, dict[int, float]]):
    """Join two Louvain communities when the links between them touch at least `BRIDGE_SHARE` of
    the smaller one. One operator who rotates numbers and photo pools falls into several dense
    sub-communities with many links among them; two operators who happen to share one template
    are joined by a few ads only, and stay apart."""
    comps = {k: set(v) for k, v in comps.items()}
    while True:
        best = None
        keys = sorted(comps)
        for i, ka in enumerate(keys):
            for kb in keys[i + 1 :]:
                a, b = comps[ka], comps[kb]
                touch_a = {x for x in a if any(y in b for y in adj[x])}
                touch_b = {y for y in b if any(x in a for x in adj[y])}
                share = min(len(touch_a) / len(a), len(touch_b) / len(b))
                if share >= BRIDGE_SHARE and (best is None or share > best[0]):
                    best = (share, ka, kb)
        if best is None:
            return comps
        _, ka, kb = best
        comps[ka] |= comps.pop(kb)


def _week(day: str) -> str:
    d = date.fromisoformat(day)
    return date.fromordinal(d.toordinal() - d.weekday()).isoformat()


def find_rings(graph: LinkGraph) -> list[Ring]:
    seeds = _pressure(graph)
    copiers = _copiers(graph)
    phrase_ads = graph.phrase_ads()
    phone_ads = graph.phone_ads
    order = sorted(graph.ads.values(), key=lambda ad: (ad.posted_at, ad.id))
    pos = {ad.id: i for i, ad in enumerate(order)}

    adj: dict[int, dict[int, float]] = {a: {} for a in seeds}

    def link(a: int, b: int, w: float) -> None:
        adj[a][b] = adj[a].get(b, 0.0) + w
        adj[b][a] = adj[b].get(a, 0.0) + w

    for group in phone_ads.values():
        members = sorted(a for a in group if a in seeds)
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                link(a, b, W_PHONE)
    for group in phrase_ads.values():
        members = sorted(a for a in group if a in seeds)
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                link(a, b, W_PHRASE)
    for group in graph.photo_ads().values():
        members = sorted(a for a in group if a in seeds)
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                if _strong_photo(graph, a, b):
                    link(a, b, W_PHOTO)
    community = louvain(adj)
    comps: dict[int, set[int]] = {}
    for a, c in community.items():
        comps.setdefault(c, set()).add(a)
    comps = _merge_bridged(comps, adj)

    # attach quiet copiers
    for ad in order:
        if ad.id in seeds:
            continue
        best, best_weight = None, 0
        for root, members in comps.items():
            weight = 0
            if any(graph.ads[m].phone == ad.phone for m in members):
                weight += W_PHONE
            if ad.id in copiers:
                weight += W_COPIER
            for m in members:
                if pos[m] < pos[ad.id] and _strong_photo(graph, ad.id, m):
                    weight += W_PHOTO
                    break
            if weight > best_weight:
                best, best_weight = root, weight
        has_phone_link = best is not None and any(
            graph.ads[m].phone == ad.phone for m in comps[best]
        )
        if best is not None and best_weight >= ATTACH_WEIGHT and has_phone_link:
            comps[best].add(ad.id)

    rings = []
    for members in comps.values():
        phones = {graph.ads[a].phone for a in members}
        if len(members) >= MIN_ADS and len(phones) >= MIN_PHONES:
            rings.append(_describe(graph, sorted(members), copiers))
    rings.sort(key=lambda r: (-len(r.ad_ids), r.first_seen))
    for i, ring in enumerate(rings):
        letter = chr(ord("A") + i)
        ring.id, ring.label = letter, f"Ring {letter}"
    return rings


def _describe(graph: LinkGraph, members: list[int], copiers: dict[int, int]) -> Ring:
    ads = sorted((graph.ads[a] for a in members), key=lambda ad: (ad.posted_at, ad.id))
    member_set = set(members)
    phones = Counter(ad.phone for ad in ads)
    findings: list[Finding] = []

    # photo reuse inside the ring
    node_ads = {n: [a for a in v if a in member_set] for n, v in graph.photo_ads().items()}
    reused = {n: v for n, v in node_ads.items() if len(v) >= 2}
    if reused:
        ev = []
        for node, ids in sorted(reused.items(), key=lambda kv: -len(kv[1])):
            for a in ids:
                ev.append(Evidence(ad_id=a, photo_ids=graph.ad_photos[a][node]))
        spread = max(len(v) for v in reused.values())
        findings.append(
            Finding(
                id="photo_reuse",
                kind="photo_reuse",
                title="Photo-sets reused across ads",
                summary=(
                    f"{len(reused)} photo-set(s) appear in {sum(len(v) for v in reused.values())} "
                    f"ad postings of this ring; the same pictures are re-cropped between ads "
                    f"(ids within {_max_bits(graph, reused)} bits)."
                ),
                score=round(min(1.0, spread / 6), 2),
                evidence=ev[:40],
            )
        )

    # phone rotation
    if len(phones) >= 2:
        findings.append(
            Finding(
                id="phone_rotation",
                kind="phone_rotation",
                title="Contact numbers rotate",
                summary=(
                    f"{len(phones)} different numbers across {len(ads)} ads; "
                    f"each number serves {min(phones.values())} to {max(phones.values())} of them."
                ),
                score=round(min(1.0, len(phones) / 6), 2),
                evidence=[Evidence(ad_id=ad.id, phone=ad.phone) for ad in ads],
            )
        )

    # shared payment-first phrasing
    phr: dict[str, list[Evidence]] = {}
    for ad in ads:
        for link in graph.phrase_links.get(ad.id, []):
            phr.setdefault(link.node, []).append(
                Evidence(
                    ad_id=ad.id,
                    span=link.sentence,
                    rule_id=None if link.why == "concept" else link.why,
                    score=round(link.score, 2),
                )
            )
    for node, ev in sorted(phr.items(), key=lambda kv: -len(kv[1])):
        if len(ev) < 2:
            continue
        reworded = len({e.span for e in ev})
        findings.append(
            Finding(
                id=f"phrasing_{node.split('-')[1]}",
                kind="shared_phrasing",
                title="Pay-before-move-in wording, reworded",
                summary=(
                    f"{len(ev)} ads ask for money before the keys in {reworded} wordings "
                    f"of one template."
                ),
                score=round(sum(e.score or 0 for e in ev) / len(ev), 2),
                evidence=ev,
            )
        )

    # copied listings
    sources = sorted({copiers[a] for a in members if a in copiers and copiers[a] not in member_set})
    copied = [a for a in members if a in copiers and copiers[a] not in member_set]
    if copied:
        ev = []
        for a in copied:
            src = copiers[a]
            node = graph.shared_photo_nodes(a, src)[0]
            ev.append(
                Evidence(
                    ad_id=a,
                    photo_ids=graph.ad_photos[a][node],
                    span=f"photos first posted in ad {src} ({graph.ads[src].phone}), "
                    f"{graph.ads[src].posted_at}",
                )
            )
            ev.append(Evidence(ad_id=src, photo_ids=graph.ad_photos[src][node]))
        findings.append(
            Finding(
                id="copied_listing",
                kind="copied_listing",
                title="Photos copied from older listings under new contact details",
                summary=f"{len(copied)} ads reuse photos from {len(sources)} older ads with a "
                f"different number.",
                score=round(min(1.0, len(copied) / 8), 2),
                evidence=ev[:40],
            )
        )

    # shared pretext claims
    pre = [(ad.id, k) for ad in ads for k in graph.facts[ad.id].pretext]
    if len({a for a, _ in pre}) >= 3:
        kinds = Counter(k for _, k in pre)
        findings.append(
            Finding(
                id="pretext",
                kind="pretext",
                title="The same reasons for not showing the home",
                summary="Ads explain why nobody can show it: "
                + ", ".join(f"{k.replace('_', ' ')} ({n})" for k, n in kinds.most_common()),
                score=round(min(1.0, len({a for a, _ in pre}) / len(ads)), 2),
                evidence=[
                    Evidence(ad_id=a, span=f"claim: {k.replace('_', ' ')}") for a, k in pre[:40]
                ],
            )
        )

    # timeline
    seen_phone: set[str] = set()
    seen_photo: set[str] = set()
    timeline: list[TimelineEvent] = []
    for i, ad in enumerate(ads):
        if i == 0:
            timeline.append(
                TimelineEvent(
                    date=ad.posted_at,
                    ad_id=ad.id,
                    kind="first_ad",
                    detail=f"first ad, number {ad.phone}",
                )
            )
        elif ad.phone not in seen_phone:
            timeline.append(
                TimelineEvent(
                    date=ad.posted_at,
                    ad_id=ad.id,
                    kind="new_phone",
                    detail=f"new number {ad.phone}",
                )
            )
        for node in graph.ad_photos[ad.id]:
            if node not in seen_photo and len(node_ads.get(node, [])) >= 2:
                timeline.append(
                    TimelineEvent(
                        date=ad.posted_at,
                        ad_id=ad.id,
                        kind="new_photo_set",
                        detail=f"photo-set {node} first used",
                    )
                )
        seen_phone.add(ad.phone)
        seen_photo.update(graph.ad_photos[ad.id])
        timeline.append(
            TimelineEvent(
                date=ad.posted_at,
                ad_id=ad.id,
                kind="ad",
                detail=f"ad {ad.id} posted from {ad.phone}",
            )
        )
    weekly = Counter(_week(ad.posted_at) for ad in ads)
    score = round(
        min(1.0, 0.2 + 0.1 * len(findings) + min(len(ads), 20) / 50 + min(len(phones), 6) / 30), 2
    )
    return Ring(
        id="?",
        label="?",
        ad_ids=[ad.id for ad in ads],
        phones=sorted(phones),
        photo_sets=sorted(reused),
        first_seen=ads[0].posted_at,
        last_seen=ads[-1].posted_at,
        score=score,
        sources=sources,
        findings=findings,
        timeline=timeline,
        weekly=sorted(weekly.items()),
    )


def _max_bits(graph: LinkGraph, reused: dict[str, list[int]]) -> int:
    worst = 0
    for node, ids in reused.items():
        photos = [p for a in ids for p in graph.ad_photos[a][node]]
        for i, p in enumerate(photos):
            for q in photos[i + 1 :]:
                worst = max(worst, hamming(p, q))
    return worst
