"""The investigator view's API: rings found in the SYNTHETIC ad corpus, one ring, and a question.

    GET  /forensics/rings           every ring (summary), the corpus label and the measured numbers
    GET  /forensics/rings/{id}      one ring in full: findings with evidence, timeline, graph
    POST /forensics/ask             {"question": "..."} -> an answer that cites its evidence
    GET  /forensics/stream          the 90-day stream: groups, shared signals, time to detect
    GET  /forensics/rings/{id}/case-file   one ring as an exportable case file (JSON)
    GET  /forensics/case-study      the detector replayed day by day over one ring

Everything here is FIXTURE data (`fixtures/forensics/`), labelled SYNTHETIC in every response.
The answer comes from the evidence graph in fixture mode; no model is called from this route.
"""

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from snapback.forensics import SYNTHETIC_LABEL
from snapback.forensics.casefile import build_case_file, build_case_study
from snapback.forensics.detect import load_timeline
from snapback.forensics.evaluate import evaluate
from snapback.forensics.investigator import EXAMPLES, Answer, ask
from snapback.forensics.pipeline import Analysis, default_analysis
from snapback.forensics.rings import Ring

router = APIRouter(prefix="/forensics", tags=["forensics"])

MAX_QUESTION = 300


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION)


def _ring_summary(ring: Ring) -> dict:
    return {
        "id": ring.id,
        "label": ring.label,
        "n_ads": len(ring.ad_ids),
        "n_phones": len(ring.phones),
        "first_seen": ring.first_seen,
        "last_seen": ring.last_seen,
        "score": ring.score,
        "finding_kinds": sorted({f.kind for f in ring.findings}),
    }


def _graph_for(analysis: Analysis, ring: Ring) -> dict:
    """Nodes and edges to draw: ads, plus the phone, photo-set and phrasing nodes they share."""
    graph = analysis.graph
    members = set(ring.ad_ids)
    nodes = [
        {"id": f"ad-{a}", "type": "ad", "label": str(a), "date": graph.ads[a].posted_at}
        for a in ring.ad_ids
    ]
    edges = []
    for phone in ring.phones:
        ids = [a for a in graph.phone_ads[phone] if a in members]
        if len(ids) >= 2:
            nodes.append({"id": f"phone-{phone}", "type": "phone", "label": phone})
            edges += [{"source": f"ad-{a}", "target": f"phone-{phone}"} for a in ids]
    for node, ids in graph.photo_ads().items():
        inside = [a for a in ids if a in members]
        if len(inside) >= 2:
            nodes.append({"id": node, "type": "photo", "label": "photos"})
            edges += [{"source": f"ad-{a}", "target": node} for a in inside]
    for node, ids in graph.phrase_ads().items():
        inside = [a for a in ids if a in members]
        if len(inside) >= 2:
            nodes.append({"id": node, "type": "phrase", "label": "wording"})
            edges += [{"source": f"ad-{a}", "target": node} for a in inside]
    return {"nodes": nodes, "edges": edges}


def _ad_cards(analysis: Analysis, ring: Ring) -> list[dict]:
    return [
        {
            "id": a,
            "posted_at": analysis.graph.ads[a].posted_at,
            "phone": analysis.graph.ads[a].phone,
            "hood": analysis.graph.ads[a].hood,
            "rent": analysis.graph.ads[a].rent,
            "text": analysis.graph.ads[a].text,
            "photos": analysis.graph.ads[a].photos,
        }
        for a in ring.ad_ids
    ]


@router.get("/rings")
def list_rings() -> dict:
    analysis = default_analysis()
    metrics = evaluate(analysis)
    ring_ad = analysis.rings[0].ad_ids[3] if analysis.rings else 1
    return {
        "label": SYNTHETIC_LABEL,
        "synthetic": True,
        "source": "FIXTURE",
        "n_ads": len(analysis.corpus.ads),
        "rings": [_ring_summary(r) for r in analysis.rings],
        "metrics": {
            "n_ads": metrics["n_ads"],
            "n_true_rings": metrics["n_true_rings"],
            "pipeline": {k: v for k, v in metrics["pipeline"].items() if k != "per_ring"},
            "keyword_baseline": {
                k: v for k, v in metrics["keyword_baseline"].items() if k != "per_ring"
            },
        },
        "example_questions": [
            q.format(ad=ring_ad, ring=analysis.rings[0].id if analysis.rings else "A")
            for q in EXAMPLES
        ],
    }


@router.get("/rings/{ring_id}")
def get_ring(ring_id: str) -> dict:
    analysis = default_analysis()
    ring = analysis.ring(ring_id)
    if ring is None:
        raise HTTPException(status_code=404, detail="No ring with that id.")
    return {
        "label": SYNTHETIC_LABEL,
        "synthetic": True,
        "source": "FIXTURE",
        "ring": ring.model_dump(),
        "graph": _graph_for(analysis, ring),
        "ads": _ad_cards(analysis, ring),
    }


@router.post("/ask")
def post_ask(body: AskBody) -> Answer:
    return ask(default_analysis(), body.question)


@router.get("/stream")
def get_stream() -> dict:
    """The day-by-day run over the SYNTHETIC 90-day stream, computed ahead of time by
    `snapback.forensics.detect` (the finder is run once per day; about two minutes)."""
    return load_timeline()


@lru_cache(maxsize=16)
def _case_file(ring_id: str) -> dict | None:
    return build_case_file(default_analysis(), ring_id.upper())


@router.get("/rings/{ring_id}/case-file")
def get_case_file(ring_id: str) -> dict:
    """Everything an investigator needs about one flagged ring, as one document. The replay that
    finds the flag day runs the ring finder once per posting day, so the first call is slow."""
    out = _case_file(ring_id)
    if out is None:
        raise HTTPException(status_code=404, detail="No ring with that id.")
    return out


@lru_cache(maxsize=1)
def _case_study() -> dict | None:
    return build_case_study(default_analysis())


@router.get("/case-study")
def get_case_study() -> dict:
    out = _case_study()
    if out is None:
        raise HTTPException(status_code=404, detail="No flagged ring to walk through.")
    return out
