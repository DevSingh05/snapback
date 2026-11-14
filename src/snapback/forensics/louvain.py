"""Louvain community detection on a small weighted graph, deterministic and dependency-free.

Plain connected components would glue two rings together whenever one weak link crosses them
(two operators using near-identical wording). Modularity-based communities cut such a bridge,
because each ring is far denser inside than across. Nodes are visited in sorted order and ties
go to the lowest community id, so the result is the same on every run.
"""

from collections import defaultdict

Graph = dict[int, dict[int, float]]


def _local_moving(graph: Graph, m2: float) -> dict[int, int]:
    comm = {n: n for n in graph}
    degree = {n: sum(nbrs.values()) for n, nbrs in graph.items()}
    total = dict(degree)  # community -> total degree
    moved = True
    while moved:
        moved = False
        for n in sorted(graph):
            current = comm[n]
            links: dict[int, float] = defaultdict(float)
            for nbr, w in graph[n].items():
                if nbr != n:
                    links[comm[nbr]] += w
            total[current] -= degree[n]
            best, best_gain = current, links.get(current, 0.0) - total[current] * degree[n] / m2
            for c in sorted(links):
                gain = links[c] - total[c] * degree[n] / m2
                if gain > best_gain + 1e-12:
                    best, best_gain = c, gain
            total[best] += degree[n]
            if best != current:
                comm[n] = best
                moved = True
    return comm


def louvain(graph: Graph) -> dict[int, int]:
    """Node -> community id (the smallest original node id in it)."""
    members = {n: [n] for n in graph}
    work = {n: dict(nbrs) for n, nbrs in graph.items()}
    while True:
        m2 = sum(sum(nbrs.values()) for nbrs in work.values())
        if not m2:
            break
        comm = _local_moving(work, m2)
        if len(set(comm.values())) == len(work):
            break
        merged: dict[int, list[int]] = defaultdict(list)
        for node, c in comm.items():
            merged[c].extend(members[node])
        new_index = {c: min(v) for c, v in merged.items()}
        agg: Graph = {new_index[c]: defaultdict(float) for c in merged}  # type: ignore[assignment]
        for n, nbrs in work.items():
            for nbr, w in nbrs.items():
                agg[new_index[comm[n]]][new_index[comm[nbr]]] += w
        members = {new_index[c]: v for c, v in merged.items()}
        work = {k: dict(v) for k, v in agg.items()}
    result = {}
    for rep, nodes in members.items():
        for n in nodes:
            result[n] = rep
    return result
