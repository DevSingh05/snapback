"""The whole pipeline in one call, cached for the API: ads -> facts -> graph -> rings."""

from dataclasses import dataclass
from functools import lru_cache

from snapback.forensics.corpus import Corpus, load_corpus
from snapback.forensics.extract import AdFacts, extract_all
from snapback.forensics.graph import LinkGraph, build_graph
from snapback.forensics.rings import Ring, find_rings


@dataclass
class Analysis:
    corpus: Corpus
    facts: dict[int, AdFacts]
    graph: LinkGraph
    rings: list[Ring]

    def ring(self, ring_id: str) -> Ring | None:
        return next((r for r in self.rings if r.id.lower() == ring_id.lower()), None)

    def ring_of(self, ad_id: int) -> Ring | None:
        return next((r for r in self.rings if ad_id in r.ad_ids), None)


def analyze(corpus: Corpus, *, hop: bool = False) -> Analysis:
    facts = extract_all(corpus.ads)
    graph = build_graph(corpus.ads, facts)
    return Analysis(corpus=corpus, facts=facts, graph=graph, rings=find_rings(graph, hop=hop))


@lru_cache(maxsize=1)
def default_analysis() -> Analysis:
    return analyze(load_corpus())
