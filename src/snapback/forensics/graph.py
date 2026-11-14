"""Step 3: the link graph. Ads on one side; photo-sets, phone numbers and phrasings on the other.

- photo-set node: photos whose perceptual-hash-like ids are within `PHOTO_HAMMING` bits of each
  other are the same picture (a re-crop or re-compression flips a few bits), grouped by union-find.
- phone node: the exact number.
- phrasing node: payment-first sentences (see `extract.pressure_sentences`) whose concept-folded
  TF-IDF vectors have cosine >= `PHRASE_COSINE`, grouped by union-find. This is the node that
  joins "Kindly remit the holding amount ahead of the keys" to a reworded twin.

Every link keeps the pointer an investigator needs: the photo ids, the number, the sentence.
"""

from dataclasses import dataclass, field

import numpy as np

from snapback.forensics.corpus import Ad
from snapback.forensics.embed import TfIdf
from snapback.forensics.extract import AdFacts, pressure_sentences

PHOTO_HAMMING = 6  # bits of 64; random hashes sit near 32, so this never joins strangers
PHRASE_COSINE = 0.7


class _Union:
    def __init__(self, items: list) -> None:
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a, b) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)  # the smaller id wins: stable names


def hamming(a: str, b: str) -> int:
    return bin(int(a[3:], 16) ^ int(b[3:], 16)).count("1")


@dataclass
class PhraseLink:
    node: str
    ad_id: int
    sentence: str
    why: str  # a rule id, or "concept"
    score: float  # mean cosine to the cluster's other sentences, 1.0 for a lone one


@dataclass
class LinkGraph:
    ads: dict[int, Ad]
    facts: dict[int, AdFacts]
    photo_node: dict[str, str]  # photo id -> photo-set node id
    ad_photos: dict[int, dict[str, list[str]]] = field(default_factory=dict)  # ad -> node -> ids
    phone_ads: dict[str, list[int]] = field(default_factory=dict)
    phrase_links: dict[int, list[PhraseLink]] = field(default_factory=dict)  # ad -> links

    def photo_ads(self) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for ad_id, nodes in self.ad_photos.items():
            for node in nodes:
                out.setdefault(node, []).append(ad_id)
        return {k: sorted(v) for k, v in out.items()}

    def phrase_ads(self) -> dict[str, list[int]]:
        out: dict[str, set[int]] = {}
        for ad_id, links in self.phrase_links.items():
            for link in links:
                out.setdefault(link.node, set()).add(ad_id)
        return {k: sorted(v) for k, v in out.items()}

    def shared_photo_nodes(self, a: int, b: int) -> list[str]:
        return sorted(set(self.ad_photos.get(a, {})) & set(self.ad_photos.get(b, {})))


def build_graph(ads: list[Ad], facts: dict[int, AdFacts]) -> LinkGraph:
    by_id = {ad.id: ad for ad in ads}
    photos = sorted({p for ad in ads for p in ad.photos})
    union = _Union(photos)
    for i, a in enumerate(photos):
        for b in photos[i + 1 :]:
            if hamming(a, b) <= PHOTO_HAMMING:
                union.join(a, b)
    photo_node = {p: f"photo-{union.find(p)[3:11]}" for p in photos}
    graph = LinkGraph(ads=by_id, facts=facts, photo_node=photo_node)
    for ad in ads:
        nodes: dict[str, list[str]] = {}
        for p in ad.photos:
            nodes.setdefault(photo_node[p], []).append(p)
        graph.ad_photos[ad.id] = nodes
        graph.phone_ads.setdefault(ad.phone, []).append(ad.id)

    sentences = [s for f in facts.values() for s in f.sentences]
    tfidf = TfIdf(sentences)
    pressed = [(ad_id, s, why) for ad_id, f in facts.items() for s, why in pressure_sentences(f)]
    if not pressed:
        return graph
    vectors = np.vstack([tfidf.vector(s) for _, s, _ in pressed])
    cos = vectors @ vectors.T
    cu = _Union(list(range(len(pressed))))
    for i in range(len(pressed)):
        for j in range(i + 1, len(pressed)):
            if cos[i, j] >= PHRASE_COSINE and pressed[i][0] != pressed[j][0]:
                cu.join(i, j)
    members: dict[int, list[int]] = {}
    for i in range(len(pressed)):
        members.setdefault(cu.find(i), []).append(i)
    for root, idxs in members.items():
        for i in idxs:
            others = [cos[i, j] for j in idxs if j != i]
            ad_id, sentence, why = pressed[i]
            graph.phrase_links.setdefault(ad_id, []).append(
                PhraseLink(
                    f"phrase-{root}",
                    ad_id,
                    sentence,
                    why,
                    float(np.mean(others)) if others else 1.0,
                )
            )
    return graph
